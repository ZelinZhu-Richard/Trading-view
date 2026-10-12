"""Reproducible portfolio metrics with explicit undefinedness and reconciliation."""
import math
from decimal import Decimal, localcontext

import pandas as pd

from .fx import MissingConversion
from .research_models import Contribution, Metric, ResearchResult
from .simulation import ENGINE_VERSION, Simulation


def metric(value, unit, convention, reason=None):
    if value is not None and not math.isfinite(float(value)):
        value, reason = None, 'Calculation is outside the finite numeric range'
    return Metric(value=None if value is None else float(value), unit=unit,
                  convention=convention, undefined_reason=reason if value is None else None)


def build_result(simulation: Simulation, logs=None, plots=None) -> ResearchResult:
    portfolio = simulation.portfolio()
    settings = simulation.settings
    capital = settings.initial_capital
    final = portfolio.equity
    elapsed = simulation.clock-simulation.start
    complete = bool(simulation.equity) and all(point.equity is not None for point in simulation.equity)
    metrics = {}
    total = None if final is None else (final-capital)/capital
    metrics['total_return'] = metric(total, 'fraction', 'Final equity / initial capital − 1', 'Final currency valuation is unavailable')
    annual = None
    annual_reason = 'Annualized return requires at least 30 calendar days and positive final equity'
    if total is not None and final > 0 and elapsed >= 30*86400:
        try:
            annual = math.expm1(math.log(float(final/capital))*365.25*86400/elapsed)
        except OverflowError:
            annual_reason = 'Annualized return exceeds the finite numeric range'
    metrics['annualized_return'] = metric(annual, 'fraction/year', 'Geometric return; 365.25 calendar days/year; minimum 30-day observation', annual_reason)
    volatility, sharpe = None, None
    risk_reason = 'At least two valid UTC daily returns with positive preceding equity are required'
    if complete and simulation.equity:
        observed = pd.Series([float(point.equity) for point in simulation.equity],
            index=pd.to_datetime([point.time for point in simulation.equity], unit='s', utc=True))
        daily = observed.resample('1D').last().ffill()
        # Include the initial capital as the preceding value for the first daily close.
        previous = daily.shift(1)
        previous.iloc[0] = float(capital)
        if (previous > 0).all():
            returns = daily/previous-1
            if len(returns) >= 2:
                deviation = float(returns.std(ddof=1))
                volatility = deviation*math.sqrt(365.25)
                if deviation > 0:
                    sharpe = float(returns.mean())/deviation*math.sqrt(365.25)
                else:
                    risk_reason = 'Daily return standard deviation is zero'
    if not complete:
        risk_reason = 'Equity contains unavailable valuations'
    metrics['volatility'] = metric(volatility, 'fraction/year', 'Sample standard deviation of UTC daily equity returns × √365.25; closed days carry last equity', risk_reason)
    metrics['sharpe'] = metric(sharpe, 'ratio', 'Mean UTC daily return / sample standard deviation × √365.25; risk-free return explicitly 0', risk_reason)
    drawdown = -min((point.drawdown for point in simulation.equity if point.drawdown is not None), default=0) if complete else None
    metrics['max_drawdown'] = metric(drawdown, 'fraction', 'Largest decline from an event-time equity peak, including initial capital', 'Equity contains unavailable valuations')
    turnover = sum((fill.quantity*fill.price*fill.conversion.rate for fill in simulation.fills), Decimal(0))/capital
    metrics['turnover'] = metric(turnover, 'multiple', 'Total absolute executed notional at fill-time FX / initial capital; buys and sells both count')
    exposure = None
    if complete and elapsed > 0 and all(point.equity > 0 and point.gross_exposure is not None for point in simulation.equity):
        exposure = sum(float(a.gross_exposure/a.equity)*(b.time-a.time)
            for a, b in zip(simulation.equity, simulation.equity[1:]))/elapsed
    metrics['exposure'] = metric(exposure, 'fraction', 'Time-weighted gross marked exposure / equity, held until the next engine event', 'Positive, available equity and a nonzero duration are required')
    wins = [trade.reporting_pnl for trade in simulation.trades if trade.reporting_pnl > 0]
    losses = [-trade.reporting_pnl for trade in simulation.trades if trade.reporting_pnl < 0]
    metrics['win_rate'] = metric(len(wins)/len(simulation.trades) if simulation.trades else None, 'fraction',
        'Profitable average-cost closing fills / all closing fills; entry and exit fees allocated proportionally', 'No closing trades')
    metrics['profit_factor'] = metric(sum(wins)/sum(losses) if losses else None, 'ratio',
        'Sum of positive net closing-trade P/L / absolute sum of negative net P/L, converted at close-time FX', 'No losing closing trades')
    contributions, conversion_records = [], list(simulation.conversions)
    with localcontext() as context:
        context.prec = 34
        for position in portfolio.positions:
            reporting = None
            if position.unrealized is not None:
                try:
                    conversion = simulation.fx.conversion(position.quote_currency, settings.reporting_currency,
                        simulation.clock, 'instrument contribution at final FX')
                    reporting = (position.realized_gross+position.unrealized+position.dividends-position.fees)*conversion.rate
                    conversion_records.append(conversion)
                except MissingConversion:
                    pass
            contributions.append(Contribution(instrument_id=position.instrument_id, quote_currency=position.quote_currency,
                realized_gross=position.realized_gross, unrealized=position.unrealized, fees=position.fees,
                dividends=position.dividends, reporting_pnl=reporting))
        currency_translation = final-capital-sum((c.reporting_pnl for c in contributions), Decimal(0)) if final is not None and all(c.reporting_pnl is not None for c in contributions) else None
    limitations = [
        'Bar-based fills are not tick-accurate. Full quantity fills assume no liquidity or market impact limit.',
        'Market/stop slippage is adverse; limit fills never exceed their limit. Costs are configured assumptions.',
        'Shorts reserve 100% initial notional plus sale proceeds. No borrow availability or borrow fee model; short gaps can cause insolvency.',
        'Bracket entries require a flat instrument position. Other position changes cancel protective children; partial fills are not modeled.',
        'Intrabar touches are reported at bar end with bar-opening FX. For touched entries, same-bar profit exits are deferred; stops may execute.',
        'Contributions translate local-currency P/L at final FX. Currency translation is the residual reconciling total portfolio P/L, including foreign cash and historical-rate effects.',
        'Split fractional entitlements are retained; cash-in-lieu is not invented. Dividend timestamps are supplied cash-effective times.',
        f'Corporate-action coverage: {settings.corporate_action_coverage}.',
    ]
    if not settings.fee_bps and not settings.fee_per_order and not settings.slippage_bps:
        limitations.append('Zero fees and zero slippage are selected; this is not an estimate of actual trading costs.')
    if settings.allow_fixture_data:
        limitations.append('Synthetic fixture data is explicitly allowed for this demonstration run.')
    if any(order.status == 'pending' for order in simulation.orders):
        limitations.append('Orders still pending at the end are retained unfilled; no future bar or forced liquidation is invented.')
    return ResearchResult(engine_version=ENGINE_VERSION, settings=settings, final_portfolio=portfolio,
        orders=simulation.orders, fills=simulation.fills, trades=simulation.trades,
        equity=simulation.equity, metrics=metrics, contributions=contributions,
        currency_translation=currency_translation, conversions=conversion_records,
        corporate_actions=simulation.action_log, logs=logs or [], plots=plots or [], limitations=limitations)
