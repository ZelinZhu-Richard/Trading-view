"""Independent hand-derived fixtures, edge cases, and prefix availability checks.

Ramp fixture C=100+t,H=C+1,L=C-1,V=2 makes the expected values below
closed-form arithmetic, independent of the implementation's rolling helpers.
These are calculation-contract checks, not TradingView numerical parity.
"""
import math

import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.indicators import (
    DEFINITIONS,
    Inputs,
    calculate,
    evaluate,
    future_slots,
    parameters,
    smooth,
)
from backend.models import Bar, IndicatorInstance, IndicatorRequest, Instrument
from backend.normalization import timestamp
from backend.store import Store

INSTRUMENT = Instrument(id='TEST:RAMP', symbol='RAMP', name='Numerical fixture', exchange='TEST',
    asset_class='other', quote_currency='USD', timezone='UTC', calendar='24/7')
START = 1735689600


def bars(closes=None, count=100, step=86400, volume=2):
    values = list(closes) if closes is not None else [100+i for i in range(count)]
    return [Bar(start=START+i*step, end=START+(i+1)*step, open=c, high=c+1, low=c-1,
                close=c, volume=volume, source='fixture', feed='hand-ramp', adjustment='raw') for i, c in enumerate(values)]


def frame(values=None, interval='1d'):
    return Inputs(values or bars(), INSTRUMENT, interval)


# (identifier, parameters, output, first valid index, hand-derived value there)
CASES = [
    ('sma', {'length': 3}, 'value', 2, 101),
    ('ema', {'length': 3}, 'value', 2, 101),
    ('wma', {'length': 3}, 'value', 2, 101+1/3),
    ('vwma', {'length': 3}, 'value', 2, 101),
    ('dema', {'length': 3}, 'value', 4, 104),
    ('tema', {'length': 3}, 'value', 6, 106),
    ('hma', {'length': 7}, 'value', 7, 107+1/3),
    ('kama', {'length': 3}, 'value', 3, 102+4/9),
    ('alma', {'length': 3, 'offset': .5}, 'value', 2, 101),
    ('bollinger_bands', {'length': 3}, 'upper', 2, 101+2*math.sqrt(2/3)),
    ('keltner_channels', {'length': 3, 'atr_length': 3}, 'upper', 2, 105),
    ('donchian_channels', {'length': 3}, 'upper', 2, 103),
    ('ichimoku', {'conversion': 3, 'base': 5, 'span_b': 7}, 'leading_a', 4, 102.5),
    ('supertrend', {'atr_length': 3, 'factor': 1}, 'line', 2, 104),
    ('parabolic_sar', {}, 'sar', 1, 99),
    ('pivot_points', {}, 'r1', 1, 101),
    ('rsi', {'length': 3}, 'value', 3, 100),
    ('stochastic', {'length': 3, 'k_smoothing': 2, 'd_smoothing': 2}, 'd', 4, 75),
    # Stoch RSI needs a changing RSI; its independent fixture is below.
    ('macd', {'fast': 2, 'slow': 4, 'signal': 2}, 'signal', 4, 1),
    ('cci', {'length': 3}, 'value', 2, 100),
    ('roc', {'length': 3}, 'value', 3, 3),
    ('momentum', {'length': 3}, 'value', 3, 3),
    ('williams_r', {'length': 3}, 'value', 2, -25),
    ('trix', {'length': 2, 'signal_length': 1}, 'value', 4, 100/101.5),
    ('ultimate_oscillator', {'short': 2, 'medium': 3, 'long': 4}, 'value', 4, 50),
    ('awesome_oscillator', {'fast': 2, 'slow': 4}, 'histogram', 3, 1),
    ('atr', {'length': 3}, 'value', 2, 2),
    ('adx_dmi', {'di_length': 3, 'adx_length': 3}, 'adx', 5, 100),
    ('aroon', {'length': 3}, 'down', 3, 0),
    ('standard_deviation', {'length': 3}, 'value', 2, math.sqrt(2/3)),
    ('historical_volatility', {'length': 2, 'bars_per_year': 1}, 'value', 2,
        50*abs(math.log(101/100)-math.log(102/101))),
    ('choppiness_index', {'length': 3}, 'value', 2, 100*math.log10(6/4)/math.log10(3)),
    ('volume', {}, 'volume', 0, 2),
    ('volume_ma', {'length': 3}, 'value', 2, 2),
    ('obv', {}, 'value', 0, 0),
    ('mfi', {'length': 3}, 'value', 3, 100),
    ('cmf', {'length': 3}, 'value', 2, 0),
    ('accumulation_distribution', {}, 'value', 0, 0),
    ('chaikin_oscillator', {'fast': 2, 'slow': 3}, 'value', 2, 0),
    ('anchored_vwap', {'anchor_time': '2025-01-02T00:00:00Z'}, 'value', 1, 101),
]


@pytest.mark.parametrize(('identifier', 'params', 'output', 'first', 'expected'), CASES)
def test_hand_derived_ramp(identifier, params, output, first, expected):
    values = calculate(identifier, frame(), params)[output]
    assert np.isnan(values[:first]).all()
    assert values[first] == pytest.approx(expected, abs=1e-10, rel=1e-9)


def test_smoothing_seed_and_wilder_are_distinct():
    values = np.array([1., 2., 6., 9., np.nan, 4., 6., 8., 10.])
    np.testing.assert_allclose(smooth(values, 3), [np.nan, np.nan, 3, 6, np.nan, np.nan, np.nan, 6, 8], equal_nan=True)
    np.testing.assert_allclose(smooth(values, 3, True), [np.nan, np.nan, 3, 5, np.nan, np.nan, np.nan, 6, 22/3], equal_nan=True)


def test_stochastic_rsi_independent_three_change_fixture():
    # RSI(2) at indices2..4 is [50,75,37.5]. A two-value stochastic
    # window therefore produces [100,0] at3..4, before optional smoothing.
    values = calculate('stochastic_rsi', frame(bars([10, 12, 10, 12, 10])),
        {'rsi_length': 2, 'stochastic_length': 2, 'k_smoothing': 1, 'd_smoothing': 1})
    np.testing.assert_allclose(values['k'], [np.nan, np.nan, np.nan, 100, 0], equal_nan=True)
    np.testing.assert_allclose(values['d'], values['k'], equal_nan=True)


def test_supertrend_strict_cross_and_sar_clamp_reversal():
    values = calculate('supertrend', frame(bars([100, 101, 102, 103, 104, 105, 106, 100])), {'atr_length': 3, 'factor': 1})
    np.testing.assert_allclose(values['line'], [np.nan, np.nan, 104, 104, 104, 103, 104, 103+2/3], equal_nan=True)
    np.testing.assert_allclose(values['direction'][2:], [-1, -1, -1, 1, 1, -1])
    values = calculate('parabolic_sar', frame(bars([100, 101, 102, 103, 97])))
    np.testing.assert_allclose(values['sar'], [np.nan, 99, 99, 99.16, 104], equal_nan=True)
    np.testing.assert_allclose(values['direction'][1:], [1, 1, 1, -1])


def test_volume_weighting_cumulative_gaps_and_zero_are_distinct():
    b = bars([10, 20, 20, 9])
    for item, value in zip(b, [1, 3, 8, 4], strict=True):
        item.volume = value
    assert calculate('vwma', frame(b), {'length': 2})['value'][1] == 17.5
    np.testing.assert_allclose(calculate('obv', frame(b))['value'], [0, 3, 3, -1])
    b[2].volume = None
    assert np.isnan(calculate('obv', frame(b))['value'][2:]).all()
    for identifier in ('vwma', 'mfi', 'cmf'):
        assert np.isnan(calculate(identifier, frame(bars(volume=0)), {'length': 3})['value']).all()
    assert calculate('volume', frame(bars(volume=0)))['volume'][0] == 0
    b = bars([10, 10, 10])
    b[0].high, b[0].low, b[0].volume = 10, 2, 5
    b[1].high, b[1].low, b[1].volume = 18, 10, 3
    b[2].high = b[2].low = 10
    np.testing.assert_allclose(calculate('accumulation_distribution', frame(b))['value'], [5, 2, 2])


def test_session_vwap_reset_partial_start_and_gap():
    b = bars([10, 20], step=60)
    b[0].volume, b[1].volume = 1, 3
    np.testing.assert_allclose(calculate('session_vwap', frame(b, '1m'))['value'], [10, 17.5])
    assert np.isnan(calculate('session_vwap', frame(b[1:], '1m'))['value']).all()
    next_day = bars([30], step=60)[0].model_copy(update={'start': START+86400, 'end': START+86460})
    result = calculate('session_vwap', frame([*b, None, next_day], '1m'))['value']
    assert result[-1] == 30
    with pytest.raises(ValueError, match='intraday'):
        calculate('session_vwap', frame(b))


@pytest.mark.parametrize('identifier', list(DEFINITIONS))
def test_all_catalog_values_are_prefix_invariant(identifier):
    # Future suffix includes violent swings; no already-computed value may change.
    b = bars([100 + math.sin(i*.4)*8 + i*.1 for i in range(95)], step=60)
    settings = {'anchor_time': '2025-01-01T00:00:00Z'} if identifier == 'anchored_vwap' else {}
    full = calculate(identifier, frame(b, '1m'), settings)
    prefix = calculate(identifier, frame(b[:70], '1m'), settings)
    assert set(full) == {item.id for item in DEFINITIONS[identifier].outputs}
    for key in full:
        np.testing.assert_allclose(full[key][:70], prefix[key], atol=1e-10, rtol=1e-9, equal_nan=True)
        assert not np.isinf(full[key]).any()


@pytest.mark.parametrize(('identifier', 'params'), [
    ('sma', {'length': 0}), ('ema', {'length': 1.5}), ('ema', {'length': True}),
    ('macd', {'fast': 30, 'slow': 20}), ('standard_deviation', {'length': 1, 'ddof': 1}),
    ('alma', {'sigma': 0}), ('parabolic_sar', {'start': .3, 'maximum': .2}),
    ('rsi', {'smoothing': 'ema'}), ('anchored_vwap', {}),
    ('anchored_vwap', {'anchor_time': '2025-01-01'}), ('sma', {'future': 1}),
])
def test_invalid_parameters_are_rejected(identifier, params):
    with pytest.raises(ValueError):
        parameters(identifier, params)


def test_registry_coverage_and_flat_denominators():
    assert len(DEFINITIONS) == 42
    assert {case[0] for case in CASES} | {'session_vwap', 'stochastic_rsi'} == set(DEFINITIONS)
    flat = [b.model_copy(update={'high': 100, 'low': 100}) for b in bars([100]*100)]
    for identifier in ('rsi', 'stochastic_rsi', 'cci', 'williams_r', 'choppiness_index'):
        assert all(np.isnan(v).all() for v in calculate(identifier, frame(flat)).values())
    assert calculate('adx_dmi', frame(flat))['adx'][-1] == 0
    assert calculate('aroon', frame(flat))['up'][-1] == 100
    assert calculate('standard_deviation', frame(flat))['value'][-1] == 0


def test_api_availability_cutoff_shift_and_absent_volume(tmp_path):
    store = Store(tmp_path)
    data = store.save_dataset(INSTRUMENT, '1d', bars(volume=None), [])
    with TestClient(create_app(tmp_path)) as client:
        catalog = client.get('/api/indicators').json()
        assert len(catalog) == 42
        response = client.post('/api/indicators/calculate', headers={'X-Workbench-Request': '1'}, json={
            'dataset_id': data.id, 'cutoff': START+60*86400, 'instances': [
                {'id': 'cloud', 'definition_id': 'ichimoku'}, {'id': 'vol', 'definition_id': 'vwma'},
                {'id': 'bad', 'definition_id': 'sma', 'parameters': {'length': -1}},
            ]})
        assert response.status_code == 200, response.text
        result = response.json()
        assert len(result['times']) == 60 and max(result['available_at']) == START+60*86400
        assert result['results'][1]['status'] == 'disabled'
        assert result['results'][2]['status'] == 'error'
        lagging = next(s for s in result['results'][0]['lines'] if s['output_id'] == 'lagging_close')
        assert lagging['plot_offset_bars'] == -26
        assert lagging['values'][59] == 159  # still available only at bar59's end


def test_missing_open_history_resets_windows_without_new_candles(tmp_path):
    store = Store(tmp_path)
    b = bars(count=8)
    del b[3]
    data = store.save_dataset(INSTRUMENT, '1d', b, [])
    result = evaluate(IndicatorRequest(dataset_id=data.id, instances=[
        IndicatorInstance(id='mean', definition_id='sma', parameters={'length': 2}),
        IndicatorInstance(id='flow', definition_id='obv'),
    ]), data, b)
    assert len(result.times) == len(b)
    assert result.results[0].lines[0].values[3:5] == [None, 104.5]
    assert all(v is None for v in result.results[1].lines[0].values[3:])


def test_session_calendars_dst_and_china_lunch(tmp_path):
    def at(when, close, instrument):
        t = int(timestamp(when, instrument.timezone, None).timestamp())
        return bars([close], step=60)[0].model_copy(update={'start': t, 'end': t+60})
    us = INSTRUMENT.model_copy(update={'calendar': 'XNYS', 'timezone': 'America/New_York'})
    b = [at('2025-03-07 09:30', 10, us), at('2025-03-07 09:31', 20, us),
         at('2025-03-10 09:30', 30, us)]
    data = Store(tmp_path).save_dataset(us, '1m', b, [])
    result = evaluate(IndicatorRequest(dataset_id=data.id, instances=[IndicatorInstance(id='v', definition_id='session_vwap')]), data, b)
    assert result.results[0].lines[0].values == [10, 15, 30]
    assert b[2].start - b[0].start == 3*86400 - 3600
    cn = INSTRUMENT.model_copy(update={'calendar': 'XSHG', 'timezone': 'Asia/Shanghai'})
    b = [at('2025-01-06 09:30', 10, cn), at('2025-01-06 11:29', 20, cn), at('2025-01-06 13:00', 30, cn)]
    # Direct calculation here is checking same session identity through lunch,
    # separately from strict missing-history detection in the API.
    np.testing.assert_allclose(calculate('session_vwap', Inputs(b, cn, '1m'))['value'], [10, 15, 20])


def test_pivots_use_complete_previous_week_and_projected_slots_skip_weekend(tmp_path):
    from backend.normalization import bar_window
    us = INSTRUMENT.model_copy(update={'calendar': 'XNYS', 'timezone': 'America/New_York'})
    b = []
    for i, day in enumerate(['2025-03-03', '2025-03-04', '2025-03-05', '2025-03-06', '2025-03-07', '2025-03-10']):
        start, end = bar_window(timestamp(day, us.timezone, None), '1d', us)
        b.append(bars([100+i])[0].model_copy(update={'start': start, 'end': end}))
    values = calculate('pivot_points', Inputs(b, us, '1d'), {'period': 'week'})
    assert np.isnan(values['p'][:5]).all()
    assert values['p'][5] == pytest.approx((105+99+104)/3)
    assert np.isnan(calculate('pivot_points', Inputs(b[1:], us, '1d'), {'period': 'week'})['p']).all()
    data = Store(tmp_path).save_dataset(us, '1d', b, [])
    projected = future_slots(data, b[4], 2)
    assert projected == [b[5].start, int(timestamp('2025-03-11 09:30', us.timezone, None).timestamp())]
