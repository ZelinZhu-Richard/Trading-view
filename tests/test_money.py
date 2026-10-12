from decimal import Decimal

import pytest

from backend.models import Anchor, Drawing, Instrument
from backend.money import position_measurement, price_to_tick, quantity_to_step


def test_tick_and_quantity_rounding_uses_decimal_steps():
    assert price_to_tick('10.125', '.25') == Decimal('10.25')
    assert price_to_tick('10.124', '.25') == Decimal(10)
    assert quantity_to_step('1.239', '.01') == Decimal('1.23')
    assert price_to_tick('.000000015', '.00000001') == Decimal('.00000002')
    with pytest.raises(ValueError):
        price_to_tick('NaN', '.01')


def test_long_short_measurements_and_invalid_orientation():
    instrument = Instrument(id='TEST', symbol='TEST', name='Fixture', exchange='TEST', asset_class='other',
        quote_currency='CNY', timezone='Asia/Shanghai', price_tick='.25', quantity_step='.1')
    drawing = Drawing(id='p', kind='long-position', instrument_id='TEST', quantity='1.29',
        anchors=[Anchor(time=i, price=p) for i, p in enumerate([100.125, 99, 102.5])])
    result = position_measurement(drawing, instrument)
    assert result['entry'] == '100.25' and result['quantity'] == '1.2'
    assert Decimal(result['risk']) == Decimal('1.5')
    assert Decimal(result['reward']) == Decimal('2.7')
    assert Decimal(result['ratio']) == Decimal('1.8') and result['currency'] == 'CNY'
    with pytest.raises(ValueError, match='loss side'):
        position_measurement(drawing.model_copy(update={'kind': 'short-position'}), instrument)
    short = drawing.model_copy(update={'kind': 'short-position', 'anchors': [Anchor(time=i, price=p) for i, p in enumerate([100, 102, 96])]})
    assert Decimal(position_measurement(short, instrument)['ratio']) == 2
