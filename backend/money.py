"""Shared decimal price/quantity conventions for drawings and simulated orders."""
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal, localcontext

from .models import Drawing, Instrument


def decimal(value) -> Decimal:
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError('Financial values must be finite')
    return result


def price_to_tick(value, tick) -> Decimal:
    with localcontext() as context:
        context.prec = 34
        step = decimal(tick)
        if step <= 0:
            raise ValueError('Price tick must be positive')
        return (decimal(value)/step).quantize(Decimal(1), rounding=ROUND_HALF_UP)*step


def quantity_to_step(value, step) -> Decimal:
    with localcontext() as context:
        context.prec = 34
        step = decimal(step)
        if step <= 0:
            raise ValueError('Quantity step must be positive')
        return (decimal(value)/step).quantize(Decimal(1), rounding=ROUND_DOWN)*step


def position_measurement(drawing: Drawing, instrument: Instrument) -> dict:
    if drawing.kind not in ('long-position', 'short-position') or len(drawing.anchors) != 3:
        raise ValueError('Position measurement needs entry, stop, and target anchors')
    if drawing.instrument_id != instrument.id:
        raise ValueError('Drawing and instrument identities must match')
    with localcontext() as context:
        context.prec = 34
        entry, stop, target = [price_to_tick(a.price, instrument.price_tick) for a in drawing.anchors]
        quantity = quantity_to_step(drawing.quantity, instrument.quantity_step)
        if quantity <= 0:
            raise ValueError('Quantity is below one instrument step')
        direction = 1 if drawing.kind == 'long-position' else -1
        risk, reward = direction*(entry-stop)*quantity, direction*(target-entry)*quantity
        if risk <= 0 or reward <= 0:
            raise ValueError('Place the stop on the loss side and target on the profit side of entry')
        ratio = reward/risk
        return {'entry': str(entry), 'stop': str(stop), 'target': str(target), 'quantity': str(quantity),
            'risk': str(risk), 'reward': str(reward), 'ratio': str(ratio), 'currency': instrument.quote_currency,
            'label': f'{quantity.normalize():f} units · risk {risk.normalize():f} {instrument.quote_currency} · reward {reward.normalize():f} · R/R {ratio:.2f}',
            'convention': 'Price: nearest tick, half up. Quantity: toward zero to instrument step. Gross values exclude fees/slippage; quote currency only.'}
