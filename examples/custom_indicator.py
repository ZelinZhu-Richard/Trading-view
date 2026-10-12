"""A causal custom indicator. Select any one dataset before running."""
PARAMETERS = {'length': {'type': 'int', 'default': 20, 'minimum': 1, 'maximum': 500}}


def calculate(ctx):
    instrument = ctx.subscriptions[0]
    values = ctx.history(instrument, count=ctx.parameters['length'])
    mean = sum(bar.close for bar in values)/len(values) if len(values) == ctx.parameters['length'] else None
    return {'custom_average': mean}
