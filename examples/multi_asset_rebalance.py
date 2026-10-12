"""Monthly equal-weight rebalance across instruments in the reporting currency.

The cash buffer reduces next-open gap/cost rejections; it cannot prevent them.
Sell orders are submitted before buys. Foreign-currency holdings need the separate
multi-currency example or explicit conversion-aware sizing.
"""
from decimal import Decimal

PARAMETERS = {'invested_fraction': {'type': 'float', 'default': 0.8, 'minimum': 0.1, 'maximum': 0.95}}


def on_bars(ctx, bars):
    month = (ctx.clock.year, ctx.clock.month)
    if ctx.state.get('month') == month:
        return
    universe = [identity for identity in ctx.subscriptions
                if ctx.instruments[identity].quote_currency == ctx.portfolio.reporting_currency]
    if not universe or any(not ctx.history(identity, count=1) for identity in universe):
        return
    portfolio = ctx.portfolio
    if portfolio.equity is None or portfolio.equity <= 0:
        return
    for pending in ctx.orders:
        if pending.status == 'pending':
            ctx.cancel(pending.id)
    target_value = portfolio.equity*Decimal(str(ctx.parameters['invested_fraction']))/len(universe)
    changes = []
    for identity in universe:
        price = Decimal(str(ctx.history(identity, count=1)[-1].close))
        held = next((p.quantity for p in portfolio.positions if p.instrument_id == identity), Decimal(0))
        change = target_value/price-held
        if abs(change) >= ctx.instruments[identity].quantity_step:
            changes.append((change, identity))
    for change, identity in sorted(changes):
        ctx.order(identity, 'buy' if change > 0 else 'sell', abs(change))
    ctx.state['month'] = month
    ctx.log('Rebalanced from completed prices at', ctx.clock)
