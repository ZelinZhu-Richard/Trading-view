"""One event-driven execution and accounting implementation for every research mode.

No broker adapters are imported. Monetary state is Decimal; chart transforms never
enter this module. Public SDK access is defined separately from owned input series.
"""
from __future__ import annotations

from bisect import bisect_right
from collections import defaultdict
from collections.abc import Callable
from decimal import Decimal, localcontext

from .fx import FXBook, MissingConversion
from .models import Bar, DatasetView
from .money import decimal, price_to_tick, quantity_to_step
from .research_models import (
    CorporateAction,
    EquityPoint,
    ExecutionSettings,
    Fill,
    OrderRequest,
    Portfolio,
    Position,
    SimulationOrder,
    Trade,
)

ENGINE_VERSION = '1.0.0'
ZERO = Decimal(0)


class Simulation:
    def __init__(self, datasets: list[DatasetView], settings: ExecutionSettings,
                 actions: list[CorporateAction] | None = None):
        if not datasets:
            raise ValueError('Select at least one dataset')
        self.settings = settings.model_copy(deep=True)
        self.views = {}
        self.starts, self.ends, self.action_times = defaultdict(dict), defaultdict(dict), defaultdict(list)
        self.history = {}
        self.positions = {}
        self.orders: list[SimulationOrder] = []
        self.fills: list[Fill] = []
        self.trades: list[Trade] = []
        self.cash = {settings.reporting_currency: settings.initial_capital}
        self.conversions = []
        self.action_log = []
        self.equity: list[EquityPoint] = []
        self.peak = settings.initial_capital
        self.entry_fees = defaultdict(lambda: ZERO)
        self.clock = 0
        for value in datasets:
            view = value.model_copy(deep=True)
            instrument = view.dataset.instrument
            if instrument.id in self.views:
                raise ValueError('Select exactly one interval/source dataset per instrument')
            if not settings.allow_fixture_data and any(b.source == 'fixture' for b in view.bars):
                raise ValueError('Synthetic fixtures require the explicit demonstration setting')
            self.views[instrument.id] = view
            self.history[instrument.id] = []
            self.positions[instrument.id] = Position(instrument_id=instrument.id, quote_currency=instrument.quote_currency)
            prior_end = None
            for bar in view.bars:
                if (bar.source, bar.feed, bar.adjustment) != (view.dataset.source, view.dataset.feed, view.dataset.adjustment):
                    raise ValueError('A dataset must preserve its source, feed, and adjustment basis')
                if prior_end is not None and bar.start < prior_end:
                    raise ValueError('Research inputs must be ordered, nonoverlapping bars')
                prior_end = bar.end
                if not bar.complete:
                    continue
                self.starts[bar.start][instrument.id] = bar
                self.ends[bar.end][instrument.id] = bar
        if not self.starts:
            raise ValueError('There are no completed bars in the selected inputs')
        self.start = settings.start if settings.start is not None else min(self.starts)
        self.end = settings.end if settings.end is not None else max(self.ends)
        if self.end < self.start:
            raise ValueError('No research interval remains inside the requested range')
        self.clock = self.start
        self.opening_processed_at = self.start-1
        self.pending_open = False
        for action in sorted(actions or [], key=lambda a: (a.time, a.instrument_id, a.kind)):
            if action.instrument_id not in self.views:
                raise ValueError(f'Corporate action instrument is not selected: {action.instrument_id}')
            self.action_times[action.time].append(action.model_copy(deep=True))
        self.fx = FXBook(list(self.views.values()), settings.fx_max_age_seconds)
        # Historical inputs may warm up indicators; no orders or portfolio state are carried in.
        for time in sorted(t for t in self.ends if t <= self.start):
            self._publish(self.ends[time])
        self.times = sorted(t for t in set(self.starts) | set(self.ends) | set(self.action_times)
                            if self.start <= t <= self.end)
        self.cursor = 0
        self._record()

    def _publish(self, bars: dict[str, Bar]):
        for identity, bar in sorted(bars.items()):
            history = self.history[identity]
            if not history or history[-1].end < bar.end:
                history.append(bar)
            position = self.positions[identity]
            position.last_price, position.last_price_time = decimal(bar.close), bar.end

    def submit(self, request: OrderRequest, *, at: int | None = None, order_id: str | None = None) -> SimulationOrder:
        if request.instrument_id not in self.views:
            raise ValueError('Order instrument is not in this run')
        instrument = self.views[request.instrument_id].dataset.instrument
        request = request.model_copy(deep=True)
        request.quantity = quantity_to_step(request.quantity, instrument.quantity_step)
        if request.quantity <= 0:
            raise ValueError('Order quantity is smaller than the instrument quantity step')
        for field in ('limit_price', 'stop_price', 'take_profit', 'stop_loss'):
            value = getattr(request, field)
            if value is not None:
                rounded = price_to_tick(value, instrument.price_tick)
                if rounded <= 0:
                    raise ValueError('Order prices must remain positive after tick rounding')
                setattr(request, field, rounded)
        request = OrderRequest.model_validate(request.model_dump())
        sequence = len(self.orders)+1
        submitted = self.clock if at is None else max(at, self.clock)
        order = SimulationOrder(id=order_id or f'order-{sequence}', sequence=sequence, request=request, submitted_at=submitted,
            eligible_from=max(submitted, self.clock if self.opening_processed_at < self.clock else self.clock+1))
        self.orders.append(order)
        return order.model_copy(deep=True)

    def cancel(self, order_id: str, reason: str = 'Cancelled by script', *, at: int | None = None) -> bool:
        order = next((o for o in self.orders if o.id == order_id), None)
        if order is None or order.status != 'pending':
            return False
        order.status, order.reason, order.completed_at = 'cancelled', reason, self.clock if at is None else max(at, self.clock)
        return True

    def _reject(self, order: SimulationOrder, reason: str):
        order.status, order.reason, order.completed_at = 'rejected', reason, self.clock

    def _fund(self, cash: dict, currency: str, required: Decimal, at: int):
        if required <= cash.get(currency, ZERO):
            return None
        reporting = self.settings.reporting_currency
        if currency == reporting:
            raise ValueError(f'Insufficient free {currency} cash: need {required}, have {cash.get(currency, ZERO)}')
        shortfall = required-cash.get(currency, ZERO)
        conversion = self.fx.conversion(reporting, currency, at, 'fund order')
        cost = shortfall/conversion.rate
        if cost > cash.get(reporting, ZERO):
            raise ValueError(f'Insufficient free {reporting} cash for currency conversion')
        cash[reporting] = cash.get(reporting, ZERO)-cost
        cash[currency] = cash.get(currency, ZERO)+shortfall
        return conversion

    def _price(self, order: SimulationOrder, bar: Bar, phase: str):
        request = order.request
        kind = request.entry_kind if request.kind == 'bracket' else request.kind
        buy = request.side == 'buy'
        opened, high, low = decimal(bar.open), decimal(bar.high), decimal(bar.low)
        if phase == 'open':
            if kind == 'market':
                return opened
            if kind == 'limit' and (opened <= request.limit_price if buy else opened >= request.limit_price):
                return opened
            if kind == 'stop' and (opened >= request.stop_price if buy else opened <= request.stop_price):
                return opened
        elif kind == 'limit' and (low <= request.limit_price if buy else high >= request.limit_price):
            return request.limit_price
        elif kind == 'stop' and (high >= request.stop_price if buy else low <= request.stop_price):
            return request.stop_price
        return None

    def _eligible(self, order: SimulationOrder, bar: Bar, phase: str):
        if order.status != 'pending':
            return False
        if order.parent_id:
            if order.activated_bar_start is None or order.activated_bar_start > bar.start:
                return False
            if order.activated_bar_start == bar.start:
                if phase == 'open':
                    return False
                # After a touched entry, path order is unknown: only adverse protection
                # can execute in that same bar. The favorable target waits one bar.
                if order.activation_phase == 'touch' and order.request.kind == 'limit':
                    return False
            return True
        return order.eligible_from <= bar.start and bar.start >= self.start

    def _process(self, bars: dict[str, Bar], phase: str):
        # Orders are append-only and retain sequence order. Bracket children are
        # appended stop first, then target. Iteration includes newly appended
        # children, so other earlier orders keep their capital-allocation priority.
        for order in self.orders:
            bar = bars.get(order.request.instrument_id)
            if bar is None or not self._eligible(order, bar, phase):
                continue
            price = self._price(order, bar, phase)
            if price is not None:
                self._fill(order, bar, price, phase)

    def _fill(self, order: SimulationOrder, bar: Bar, raw_price: Decimal, phase: str):
        with localcontext() as context:
            context.prec = 34
            request = order.request
            identity = request.instrument_id
            view = self.views[identity]
            instrument = view.dataset.instrument
            direction = Decimal(1) if request.side == 'buy' else Decimal(-1)
            kind = request.entry_kind if request.kind == 'bracket' else request.kind
            price = raw_price*(1+direction*self.settings.slippage_bps/10000)
            price = price_to_tick(price, instrument.price_tick)
            if kind == 'limit':
                price = min(price, request.limit_price) if direction > 0 else max(price, request.limit_price)
            if price <= 0:
                self._reject(order, 'Fill price is not positive after tick rounding')
                return
            position = self.positions[identity].model_copy(deep=True)
            quantity = request.quantity
            if order.parent_id:
                if position.quantity*direction >= 0:
                    self.cancel(order.id, 'Protective exit no longer has a matching position')
                    return
                quantity = min(quantity, abs(position.quantity))
            if request.kind == 'bracket' and position.quantity:
                self._reject(order, 'A bracket entry requires a flat instrument position')
                return
            if request.kind == 'bracket' and not (
                request.stop_loss < price < request.take_profit if direction > 0 else request.take_profit < price < request.stop_loss
            ):
                self._reject(order, 'Opening fill is outside the bracket stop/target levels')
                return
            close_quantity = min(quantity, abs(position.quantity)) if position.quantity*direction < 0 else ZERO
            open_quantity = quantity-close_quantity
            if direction < 0 and open_quantity and not self.settings.allow_short:
                self._reject(order, 'Short selling is disabled')
                return
            if open_quantity and self.portfolio().insolvent:
                self._reject(order, 'Account is insolvent; new exposure is disabled')
                return
            fee = price*quantity*self.settings.fee_bps/10000+self.settings.fee_per_order
            cash = dict(self.cash)
            currency = instrument.quote_currency
            cash.setdefault(currency, ZERO)
            quote_at = self.clock if phase == 'open' else bar.start
            try:
                conversion = self.fx.conversion(currency, self.settings.reporting_currency, quote_at, 'fill and realized P/L')
                old_quantity, old_average = position.quantity, position.average_price
                gross = ZERO
                allocated_entry_fee = ZERO
                if close_quantity:
                    fraction = close_quantity/abs(old_quantity)
                    allocated_entry_fee = self.entry_fees[identity]*fraction
                    gross = (price-old_average)*close_quantity*(1 if old_quantity > 0 else -1)
                    if old_quantity > 0:
                        cash[currency] += price*close_quantity
                    else:
                        collateral = position.short_collateral*fraction
                        proceeds = position.short_proceeds*fraction
                        cash[currency] += collateral+proceeds-price*close_quantity
                        position.short_collateral -= collateral
                        position.short_proceeds -= proceeds
                    position.quantity += direction*close_quantity
                    position.realized_gross += gross
                required = price*open_quantity+fee
                # Pure risk-reducing closes may exceed available collateral after a
                # gap. Keep their deficit visible instead of refusing the close.
                funding = None
                if open_quantity:
                    funding = self._fund(cash, currency, required, quote_at)
                elif cash[currency] < fee and currency != self.settings.reporting_currency:
                    try:
                        funding = self._fund(cash, currency, fee, quote_at)
                    except ValueError:
                        pass  # realised deficit is retained, and new exposure is blocked
                cash[currency] -= required
                if open_quantity:
                    prior = abs(position.quantity)
                    position.average_price = (position.average_price*prior+price*open_quantity)/(prior+open_quantity)
                    position.quantity += direction*open_quantity
                    if direction < 0:
                        position.short_collateral += price*open_quantity
                        position.short_proceeds += price*open_quantity
                elif not position.quantity:
                    position.average_price = ZERO
                position.fees += fee
                if phase == 'open':
                    position.last_price, position.last_price_time = decimal(bar.open), bar.start
            except (MissingConversion, ValueError) as exc:
                self._reject(order, str(exc))
                return
            self.cash, self.positions[identity] = cash, position
            self.entry_fees[identity] -= allocated_entry_fee
            self.entry_fees[identity] += fee*open_quantity/quantity
            if funding:
                self.conversions.append(funding)
            self.conversions.append(conversion)
            if close_quantity:
                allocated_fee = allocated_entry_fee+fee*close_quantity/quantity
                self.trades.append(Trade(id=f'trade-{len(self.trades)+1}', instrument_id=identity,
                    time=self.clock, direction='long' if old_quantity > 0 else 'short', quantity=close_quantity,
                    entry_price=old_average, exit_price=price, gross_pnl=gross, allocated_fees=allocated_fee,
                    net_pnl=gross-allocated_fee, quote_currency=currency,
                    reporting_pnl=(gross-allocated_fee)*conversion.rate, conversion=conversion))
            self.fills.append(Fill(id=f'fill-{len(self.fills)+1}', order_id=order.id, instrument_id=identity,
                side=request.side, quantity=quantity, price=price, fee=fee, quote_currency=currency,
                time=self.clock, bar_start=bar.start, phase=phase, dataset_id=view.dataset.id,
                source=view.dataset.source, feed=view.dataset.feed, conversion=conversion))
            order.status, order.completed_at = 'filled', self.clock
            if order.sibling_id:
                self.cancel(order.sibling_id, 'Sibling protective exit filled')
            elif request.kind != 'bracket':
                for child in self.orders:
                    if child.parent_id and child.request.instrument_id == identity:
                        self.cancel(child.id, 'Position changed by another order; protective quantity invalidated')
            if request.kind == 'bracket':
                children = []
                for child_kind, field, value in (('stop', 'stop_price', request.stop_loss), ('limit', 'limit_price', request.take_profit)):
                    child = self.submit(OrderRequest(instrument_id=identity, side='sell' if direction > 0 else 'buy',
                        quantity=quantity, kind=child_kind, **{field: value}, tag=request.tag))
                    actual = self.orders[child.sequence-1]
                    actual.parent_id, actual.activated_bar_start, actual.activation_phase = order.id, bar.start, phase
                    children.append(actual)
                children[0].sibling_id, children[1].sibling_id = children[1].id, children[0].id

    def _action(self, action: CorporateAction):
        view = self.views[action.instrument_id]
        adjustment = view.dataset.adjustment
        if adjustment == 'unknown':
            raise ValueError('Corporate actions require an explicit dataset adjustment basis')
        skipped = (action.kind == 'split' and adjustment in ('split', 'total-return')) or (action.kind == 'dividend' and adjustment == 'total-return')
        record = {**action.model_dump(mode='json'), 'applied': not skipped,
                  'reason': 'Already included in adjusted bars' if skipped else 'Supplied cash-effective event'}
        self.action_log.append(record)
        if skipped:
            return
        position = self.positions[action.instrument_id]
        if action.kind == 'dividend':
            amount = position.quantity*action.value
            self.cash[position.quote_currency] = self.cash.get(position.quote_currency, ZERO)+amount
            position.dividends += amount
        else:
            position.quantity *= action.value
            position.average_price /= action.value
            if position.last_price is not None:
                position.last_price /= action.value
            for order in self.orders:
                if order.status != 'pending' or order.request.instrument_id != action.instrument_id:
                    continue
                request = order.request
                request.quantity *= action.value
                # Retain fractional entitlements exactly; execution still rounds prices
                # to the instrument tick. No fabricated cash-in-lieu transaction.
                for field in ('limit_price', 'stop_price', 'take_profit', 'stop_loss'):
                    value = getattr(request, field)
                    if value is not None:
                        setattr(request, field, value/action.value)

    def portfolio(self) -> Portfolio:
        with localcontext() as context:
            context.prec = 34
            restricted = defaultdict(lambda: ZERO)
            amounts = defaultdict(lambda: ZERO, self.cash)
            positions, errors, conversions = [], [], []
            exposure = ZERO
            for source in self.positions.values():
                position = source.model_copy(deep=True)
                restricted[position.quote_currency] += position.short_collateral+position.short_proceeds
                if position.quantity:
                    if position.last_price is None:
                        errors.append(f'Missing valuation for {position.instrument_id}')
                    else:
                        position.market_value = position.quantity*position.last_price
                        position.unrealized = (position.last_price-position.average_price)*position.quantity
                        amounts[position.quote_currency] += position.market_value
                        try:
                            fx = self.fx.conversion(position.quote_currency, self.settings.reporting_currency, self.clock, 'position exposure')
                            exposure += abs(position.market_value)*fx.rate
                            conversions.append(fx)
                        except MissingConversion as exc:
                            errors.append(str(exc))
                else:
                    position.unrealized, position.market_value = ZERO, ZERO
                if position.quantity or position.fees or position.realized_gross or position.dividends:
                    positions.append(position)
            for currency, amount in restricted.items():
                amounts[currency] += amount
            total = ZERO
            for currency, amount in sorted(amounts.items()):
                if not amount:
                    continue
                try:
                    fx = self.fx.conversion(currency, self.settings.reporting_currency, self.clock, 'portfolio valuation')
                    total += amount*fx.rate
                    conversions.append(fx)
                except MissingConversion as exc:
                    errors.append(str(exc))
            return Portfolio(time=self.clock, reporting_currency=self.settings.reporting_currency,
                cash=dict(self.cash), restricted_cash=dict(restricted), positions=positions,
                equity=None if errors else total, gross_exposure=None if errors else exposure,
                valuation_errors=sorted(set(errors)), conversions=conversions,
                insolvent=any(value < 0 for value in self.cash.values()) or (not errors and total < 0))

    def _record(self):
        portfolio = self.portfolio()
        equity = portfolio.equity
        drawdown = None
        if equity is not None:
            self.peak = max(self.peak, equity)
            drawdown = float((equity-self.peak)/self.peak)
        point = EquityPoint(time=self.clock, equity=equity, gross_exposure=portfolio.gross_exposure,
            drawdown=drawdown, valuation_errors=portfolio.valuation_errors)
        if self.equity and self.equity[-1].time == self.clock:
            self.equity[-1] = point
        else:
            self.equity.append(point)

    def _finish_open(self):
        if self.clock < self.end:
            opening = self.starts.get(self.clock, {})
            for identity, bar in opening.items():
                position = self.positions[identity]
                position.last_price, position.last_price_time = decimal(bar.open), bar.start
            self._process(opening, 'open')
        self.opening_processed_at = self.clock
        self.pending_open = False
        self._record()

    def advance(self, until: int | None = None, on_bars: Callable | None = None,
                on_progress: Callable | None = None, pause_before_open: bool = False,
                on_event: Callable | None = None):
        """Advance monotonically; seeking backward requires a fresh engine instance."""
        if until is not None and until < self.clock:
            raise ValueError('Backward replay requires rebuilding simulation state')
        limit = self.end if until is None else min(until, self.end)
        with localcontext() as context:
            context.prec = 34
            if self.pending_open:
                if limit == self.clock and pause_before_open:
                    return self.portfolio()
                self._finish_open()
            while self.cursor < len(self.times) and self.times[self.cursor] <= limit:
                self.clock = self.times[self.cursor]
                self.cursor += 1
                ending = self.ends.get(self.clock, {}) if self.clock > self.start else {}
                self._process(ending, 'touch')
                self._publish(ending)
                if ending and on_bars:
                    on_bars({key: value.model_copy(deep=True) for key, value in ending.items()})
                for action in self.action_times.get(self.clock, []):
                    self._action(action)
                if on_event:
                    on_event(self.clock)
                if pause_before_open and self.clock == limit:
                    self.pending_open = True
                    self._record()
                else:
                    self._finish_open()
                if on_progress:
                    on_progress(self.cursor, len(self.times))
        return self.portfolio()

    def next_completion(self):
        values = sorted(self.ends)
        index = bisect_right(values, self.clock)
        return values[index] if index < len(values) and values[index] <= self.end else None
