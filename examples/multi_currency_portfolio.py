"""Buy a fixed small quantity of each non-FX instrument once history is available.

Select assets in different quote currencies AND suitable FX datasets. The engine
funds quote cash using causal rates. Inspect rejected orders for missing rates or
insufficient capital. FX datasets supply rates but are not traded by this example.
"""
PARAMETERS = {'quantity': {'type': 'float', 'default': 1, 'minimum': 0.000001}}


def initialize(ctx):
    ctx.state['submitted'] = set()


def on_bars(ctx, bars):
    for identity in sorted(bars):
        instrument = ctx.instruments[identity]
        if instrument.asset_class == 'forex' or identity in ctx.state['submitted']:
            continue
        ctx.order(identity, 'buy', ctx.parameters['quantity'])
        ctx.state['submitted'].add(identity)
        ctx.log('Submitted', identity, 'quoted in', instrument.quote_currency, 'at', ctx.clock)
