"""Long/flat crossover using the same Python EMA calculation as charts."""
PARAMETERS = {
    'fast': {'type': 'int', 'default': 10, 'minimum': 2, 'maximum': 200},
    'slow': {'type': 'int', 'default': 30, 'minimum': 3, 'maximum': 500},
    'quantity': {'type': 'float', 'default': 1, 'minimum': 0.000001},
}


def initialize(ctx):
    if ctx.parameters['fast'] >= ctx.parameters['slow']:
        raise ValueError('Fast length must be shorter than slow length')


def on_bars(ctx, bars):
    for identity in bars:
        fast = ctx.indicator(identity, 'ema', {'length': ctx.parameters['fast']}, count=2)['value']
        slow = ctx.indicator(identity, 'ema', {'length': ctx.parameters['slow']}, count=2)['value']
        if len(fast) < 2 or any(value is None for value in (*fast, *slow)):
            continue
        held = next((p.quantity for p in ctx.portfolio.positions if p.instrument_id == identity), 0)
        pending = any(o.status == 'pending' and o.request.instrument_id == identity for o in ctx.orders)
        if pending:
            continue
        if fast[0] <= slow[0] and fast[1] > slow[1] and not held:
            ctx.order(identity, 'buy', ctx.parameters['quantity'])
        elif fast[0] >= slow[0] and fast[1] < slow[1] and held > 0:
            ctx.order(identity, 'sell', held)
        ctx.plot('fast_ema', fast[-1], identity)
        ctx.plot('slow_ema', slow[-1], identity)
