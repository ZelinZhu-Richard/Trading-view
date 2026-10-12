"""Causal indicator calculations shared by charts and research.

Values are indexed by the input bar that computes them. Plot offsets never shift
these arrays; consumers may read a value only after that bar's end timestamp.
The versioned registry and docs/indicator-formulas.md state numerical variants.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from .models import (
    Bar,
    Dataset,
    IndicatorDefinition,
    IndicatorOutput,
    IndicatorParameter,
    IndicatorRequest,
    IndicatorResponse,
    IndicatorResult,
    IndicatorValues,
    Instrument,
)
from .normalization import SECONDS, bar_window, session_segments, timestamp

CONTRACT = json.loads(Path(__file__).with_name('indicator_registry.json').read_text())
VERSION = CONTRACT['version']
RECORDS = {r['id']: r for r in CONTRACT['indicators']}
SOURCES = ['open', 'high', 'low', 'close', 'hl2', 'hlc3', 'ohlc4']
VOLUME_IDS = {'vwma', 'volume', 'volume_ma', 'obv', 'mfi', 'cmf',
              'accumulation_distribution', 'chaikin_oscillator', 'session_vwap', 'anchored_vwap'}
LENGTHS = {'length', 'fast', 'slow', 'atr_length', 'conversion', 'base', 'span_b',
           'displacement', 'k_smoothing', 'd_smoothing', 'rsi_length', 'stochastic_length',
           'signal', 'signal_length', 'short', 'medium', 'long', 'di_length', 'adx_length'}


def registry() -> list[IndicatorDefinition]:
    result = []
    for record in RECORDS.values():
        controls = {}
        for key, default in record['parameters']['defaults'].items():
            if isinstance(default, list):
                continue  # The fixed UO weights are part of the formula, not parameters.
            control = IndicatorParameter(default=default, kind='fixed')
            if key in LENGTHS:
                control.kind, control.minimum, control.maximum = 'integer', 0 if key == 'displacement' else 1, 10000
                if key == 'displacement':
                    control.maximum = 500
                if key == 'length' and record['id'] in ('historical_volatility', 'choppiness_index'):
                    control.minimum = 2
            elif key in ('source', 'period', 'ddof'):
                control.kind = 'choice'
                control.choices = SOURCES if key == 'source' else ['session', 'week', 'month'] if key == 'period' else ['0', '1']
                if record['id'] == 'awesome_oscillator' and key == 'source':
                    control.choices = ['hl2']
            elif key == 'floor_center':
                control.kind = 'boolean'
            elif key in ('multiplier', 'factor', 'offset', 'sigma', 'start', 'increment', 'maximum', 'bars_per_year'):
                control.kind = 'number'
                control.minimum = 0
                control.maximum = 1 if key == 'offset' else None
            elif key == 'anchor_time':
                control.kind = 'timestamp'
            controls[key] = control
        outputs = []
        for item in record['outputs']:
            # Dynamic Ichimoku shifts are resolved from the user's displacement.
            offset = item['plot_offset_bars']
            outputs.append(IndicatorOutput(**{**item, 'plot_offset_bars': offset if isinstance(offset, int) else 0}))
        result.append(IndicatorDefinition(id=record['id'], name=record['name'], category=record['category'],
            contract_version=VERSION, parameters=controls, outputs=outputs,
            formula='\n'.join(record['formula']) if isinstance(record['formula'], list) else record['formula'],
            warmup=record['warmup'], edge_cases=record['edge_cases'], notes=record['unsettled_or_app_choices'],
            source_urls=record['source_urls'], volume_required=record['id'] in VOLUME_IDS))
    return result


DEFINITIONS = {d.id: d for d in registry()}


def parameters(identifier: str, supplied: dict) -> dict:
    if identifier not in DEFINITIONS:
        raise ValueError(f'Unknown indicator: {identifier}')
    definition = DEFINITIONS[identifier]
    if set(supplied) - set(definition.parameters):
        raise ValueError('Unknown parameters: ' + ', '.join(sorted(set(supplied) - set(definition.parameters))))
    result = {}
    for key, control in definition.parameters.items():
        value = supplied.get(key, control.default)
        if control.kind in ('integer', 'number'):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f'{key} must be finite')
            if control.kind == 'integer' and value != int(value):
                raise ValueError(f'{key} must be an integer')
            if (control.minimum is not None and value < control.minimum) or (control.maximum is not None and value > control.maximum):
                raise ValueError(f'{key} is outside its supported range')
            if key in ('factor', 'sigma', 'start', 'increment', 'maximum', 'bars_per_year') and value <= 0:
                raise ValueError(f'{key} must be positive')
            value = int(value) if control.kind == 'integer' else value
        elif control.kind == 'choice':
            if key == 'ddof' and not isinstance(value, bool) and value in (0, 1):
                value = int(value)
            if str(value) not in control.choices:
                raise ValueError(f'{key} must be one of {control.choices}')
            value = int(value) if key == 'ddof' else value
        elif control.kind == 'boolean' and not isinstance(value, bool):
            raise ValueError(f'{key} must be a boolean')
        elif control.kind == 'fixed' and (type(value) is bool or value != control.default):
            # include_current is a true fixed boolean; Python bool/int equality is not sufficient.
            if not (isinstance(control.default, bool) and value is control.default):
                raise ValueError(f'{key} is fixed at {control.default!r} in calculation contract {VERSION}')
        elif control.kind == 'timestamp':
            if not isinstance(value, str) or not value.strip():
                raise ValueError('Choose an explicit anchor timestamp, including timezone')
            value = timestamp(value, None, None).isoformat()
        result[key] = value
    if 'fast' in result and (result['fast'] > result['slow'] if identifier == 'kama' else result['fast'] >= result['slow']):
        raise ValueError('Fast period must be smaller than slow period (KAMA permits equality)')
    if 'short' in result and not result['short'] < result['medium'] < result['long']:
        raise ValueError('Periods must satisfy short < medium < long')
    if 'ddof' in result and result['length'] <= result['ddof']:
        raise ValueError('Length must exceed the standard-deviation degrees of freedom')
    if 'start' in result and result['start'] > result['maximum']:
        raise ValueError('Starting acceleration must not exceed its maximum')
    return result


def roll(x, n, operation='mean', **kwargs):
    window = pd.Series(x).rolling(n, min_periods=n)
    if callable(operation):
        return window.apply(operation, raw=True).to_numpy()
    return getattr(window, operation)(**kwargs).to_numpy()


def divide(a, b):
    a, b = np.broadcast_arrays(a, b)
    return np.divide(a, b, out=np.full(a.shape, np.nan), where=np.isfinite(b) & (b != 0))


def lag(x, n=1):
    result = np.full(len(x), np.nan)
    if n < len(x):
        result[n:] = x[:-n] if n else x
    return result


def smooth(x, n, wilder=False):
    result = np.full(len(x), np.nan)
    alpha = 1 / n if wilder else 2 / (n + 1)
    pending = []
    previous = np.nan
    for i, value in enumerate(x):
        if not np.isfinite(value):
            pending.clear()
            previous = np.nan
        elif np.isfinite(previous):
            previous += alpha * (value - previous)
            result[i] = previous
        else:
            pending.append(value)
            if len(pending) == n:
                previous = math.fsum(pending) / n
                result[i] = previous
                pending.clear()
    return result


def wma(x, n):
    weights = np.arange(1, n + 1, dtype=float)
    return roll(x, n, lambda values: np.dot(values, weights) / weights.sum())


def rsi(x, n):
    delta = x - lag(x)
    gain, loss = smooth(np.maximum(delta, 0), n, True), smooth(np.maximum(-delta, 0), n, True)
    return 100 * divide(gain, gain + loss)


@dataclass
class Inputs:
    bars: list[Bar | None]
    instrument: Instrument
    interval: str

    def __post_init__(self):
        self.columns = {key: np.array([getattr(b, key) if b else np.nan for b in self.bars], dtype=float)
                        for key in ('open', 'high', 'low', 'close', 'volume')}
        self.columns.update(hl2=(self.columns['high'] + self.columns['low']) / 2,
            hlc3=(self.columns['high'] + self.columns['low'] + self.columns['close']) / 3,
            ohlc4=sum(self.columns[k] for k in ('open', 'high', 'low', 'close')) / 4)

    def __getitem__(self, name):
        return self.columns[name]

    def tr(self):
        high, low, previous = self['high'], self['low'], lag(self['close'])
        return np.where(np.isfinite(previous), np.maximum(high - low, np.maximum(abs(high - previous), abs(low - previous))), high - low)


def period_key(bar, instrument, period='session'):
    # Session labels follow instrument semantics; 24/7 VWAP uses UTC explicitly.
    zone = 'UTC' if instrument.calendar == '24/7' else instrument.timezone
    day = pd.Timestamp(bar.start, unit='s', tz='UTC').tz_convert(zone).date()
    if period == 'week':
        return day - timedelta(days=day.weekday())
    if period == 'month':
        return day.replace(day=1)
    return day


def vwap(inputs, x, p, anchored=False):
    out = np.full(len(x), np.nan)
    volume = inputs['volume']
    anchor = int(timestamp(p['anchor_time'], None, None).timestamp()) if anchored else None
    actual = [b for b in inputs.bars if b]
    if anchored and actual and anchor < actual[0].start:
        raise ValueError('The anchor precedes available history; load its complete prefix first')
    if not anchored and inputs.interval in ('1d', '1w', '1mo'):
        raise ValueError('Session VWAP requires intraday data')
    current, valid, pv, q = None, False, 0., 0.
    for i, bar in enumerate(inputs.bars):
        if bar is None:
            valid = False
            continue
        if anchored:
            if bar.start < anchor:
                continue
            key = anchor
            start = bar.start
        else:
            key = period_key(bar, inputs.instrument)
            if inputs.instrument.calendar == '24/7':
                start = int(pd.Timestamp(key, tz='UTC').timestamp())
            else:
                start, _ = bar_window(pd.Timestamp(bar.start, unit='s', tz='UTC'), '1d', inputs.instrument)
        if key != current:
            current, pv, q = key, 0., 0.
            valid = anchored or bar.start == start
        if not np.isfinite(volume[i]) or not np.isfinite(x[i]):
            valid = False
        if valid:
            pv += x[i] * volume[i]
            q += volume[i]
            if q:
                out[i] = pv / q
    return out


def pivots(inputs, p):
    outputs = {key: np.full(len(inputs.bars), np.nan) for key in ('p', 'r1', 's1', 'r2', 's2', 'r3', 's3')}
    if inputs.interval in ('1w', '1mo'):
        raise ValueError('Pivots require daily or finer source bars')
    current, group, previous, gap = None, [], None, False

    def complete_group(group, key, invalid):
        if not group or invalid:
            return None
        end_day = key + timedelta(days=1 if p['period'] == 'session' else 7) if p['period'] != 'month' else (pd.Timestamp(key) + pd.offsets.MonthBegin()).date()
        segments = session_segments(key, end_day, inputs.instrument)
        if not segments:
            return None
        first, last = segments[0][0], segments[-1][1]
        if inputs.instrument.session == 'provider-day':
            first, _ = bar_window(pd.Timestamp(first, unit='s', tz='UTC'), '1d', inputs.instrument)
            _, last = bar_window(pd.Timestamp(last - 1, unit='s', tz='UTC'), '1d', inputs.instrument)
        if group[0].start != first or group[-1].end != last:
            return None
        high, low, close = max(b.high for b in group), min(b.low for b in group), group[-1].close
        pivot = (high + low + close) / 3
        return {'p': pivot, 'r1': 2*pivot-low, 's1': 2*pivot-high, 'r2': pivot+high-low,
                    's2': pivot-high+low, 'r3': 2*pivot+high-2*low, 's3': 2*pivot-2*high+low}

    for i, bar in enumerate(inputs.bars):
        if bar is None:
            gap = True
            continue
        key = period_key(bar, inputs.instrument, p['period'])
        if key != current:
            previous = complete_group(group, current, gap) if current is not None else None
            current, group, gap = key, [], False
        if previous:
            for name, value in previous.items():
                outputs[name][i] = value
        group.append(bar)
    return outputs


def calculate(identifier: str, inputs: Inputs, supplied: dict | None = None) -> dict[str, np.ndarray]:
    """Return source-time arrays. Invalid parameters raise; undefined values are NaN."""
    p = parameters(identifier, supplied or {})
    x = inputs[p.get('source', 'close')]
    h, low, c, v = (inputs[key] for key in ('high', 'low', 'close', 'volume'))
    n = p.get('length', 1)
    out = np.full(len(x), np.nan)
    if identifier in ('sma', 'volume_ma'):
        out = roll(v if identifier == 'volume_ma' else x, n)
    elif identifier == 'ema':
        out = smooth(x, n)
    elif identifier == 'wma':
        out = wma(x, n)
    elif identifier == 'vwma':
        out = divide(roll(x * v, n, 'sum'), roll(v, n, 'sum'))
    elif identifier in ('dema', 'tema'):
        first = smooth(x, n)
        second = smooth(first, n)
        out = 2 * first - second if identifier == 'dema' else 3 * first - 3 * second + smooth(second, n)
    elif identifier == 'hma':
        out = wma(2 * wma(x, max(1, n // 2)) - wma(x, n), max(1, math.isqrt(n)))
    elif identifier == 'kama':
        volatility = roll(abs(x - lag(x)), n, 'sum')
        er = np.where(volatility == 0, 0, divide(abs(x - lag(x, n)), volatility))
        alpha = (er * (2 / (p['fast'] + 1) - 2 / (p['slow'] + 1)) + 2 / (p['slow'] + 1)) ** 2
        previous = np.nan
        for i in range(len(x)):
            if not np.isfinite(alpha[i]):
                previous = np.nan
                continue
            previous = x[i-1] if not np.isfinite(previous) else previous
            previous += alpha[i] * (x[i] - previous)
            out[i] = previous
    elif identifier == 'alma':
        center = p['offset'] * (n - 1)
        center = math.floor(center) if p['floor_center'] else center
        exponents = -((np.arange(n) - center) / (n / p['sigma'])) ** 2 / 2
        weights = np.exp(exponents - exponents.max())
        out = roll(x, n, lambda values: np.dot(values, weights) / weights.sum())
    elif identifier in ('bollinger_bands', 'keltner_channels'):
        if identifier == 'bollinger_bands':
            basis, spread = roll(x, n), roll(x, n, 'std', ddof=p['ddof'])
        else:
            basis, spread = smooth(x, n), smooth(inputs.tr(), p['atr_length'], True)
        spread = spread * p['multiplier']
        return {'basis': basis, 'upper': basis + spread, 'lower': basis - spread}
    elif identifier == 'donchian_channels':
        upper, lower = roll(h, n, 'max'), roll(low, n, 'min')
        return {'upper': upper, 'middle': (upper + lower) / 2, 'lower': lower}
    elif identifier == 'ichimoku':
        def mid(length):
            return (roll(h, length, 'max') + roll(low, length, 'min')) / 2
        conversion, base = mid(p['conversion']), mid(p['base'])
        return {'conversion': conversion, 'base': base, 'leading_a': (conversion+base)/2,
                    'leading_b': mid(p['span_b']), 'lagging_close': c.copy()}
    elif identifier == 'supertrend':
        atr = smooth(inputs.tr(), p['atr_length'], True)
        upper, lower = inputs['hl2'] + p['factor'] * atr, inputs['hl2'] - p['factor'] * atr
        direction = out.copy()
        previous_u = previous_l = previous_d = np.nan
        for i in range(len(x)):
            if not np.isfinite(atr[i]):
                previous_d = np.nan
                continue
            if not np.isfinite(previous_d):
                u, lo, d = upper[i], lower[i], -1
            else:
                u = upper[i] if upper[i] < previous_u or c[i-1] > previous_u else previous_u
                lo = lower[i] if lower[i] > previous_l or c[i-1] < previous_l else previous_l
                d = (1 if c[i] > u else -1) if previous_d == -1 else (-1 if c[i] < lo else 1)
            out[i], direction[i] = lo if d == 1 else u, d
            previous_u, previous_l, previous_d = u, lo, d
        return {'line': out, 'direction': direction}
    elif identifier == 'parabolic_sar':
        direction = out.copy()
        sar = extreme = acceleration = np.nan
        up = False
        for i in range(1, len(x)):
            if not np.isfinite(c[i-1:i+1]).all():
                sar = np.nan
                continue
            if not np.isfinite(sar):
                up = c[i] > c[i-1]
                sar, extreme, acceleration = (low[i-1] if up else h[i-1]), (h[i] if up else low[i]), p['start']
            else:
                candidate = sar + acceleration * (extreme - sar)
                reverse = (low[i] < candidate) if up else (h[i] > candidate)
                if reverse:
                    up = not up
                    sar, extreme, acceleration = extreme, h[i] if up else low[i], p['start']
                else:
                    sar = min(candidate, low[i-1], low[i-2]) if up else max(candidate, h[i-1], h[i-2])
                    if (up and h[i] > extreme) or (not up and low[i] < extreme):
                        extreme = h[i] if up else low[i]
                        acceleration = min(p['maximum'], acceleration + p['increment'])
            out[i], direction[i] = sar, 1 if up else -1
        return {'sar': out, 'direction': direction}
    elif identifier == 'pivot_points':
        return pivots(inputs, p)
    elif identifier == 'rsi':
        out = rsi(x, n)
    elif identifier in ('stochastic', 'stochastic_rsi'):
        if identifier == 'stochastic_rsi':
            r = rsi(x, p['rsi_length'])
            minimum, maximum = roll(r, p['stochastic_length'], 'min'), roll(r, p['stochastic_length'], 'max')
            raw = p['scale'] * divide(r - minimum, maximum - minimum)
        else:
            minimum, maximum = roll(low, n, 'min'), roll(h, n, 'max')
            raw = 100 * divide(c - minimum, maximum - minimum)
        k = roll(raw, p['k_smoothing'])
        return {'k': k, 'd': roll(k, p['d_smoothing'])}
    elif identifier == 'macd':
        macd = smooth(x, p['fast']) - smooth(x, p['slow'])
        signal = smooth(macd, p['signal'])
        return {'macd': macd, 'signal': signal, 'histogram': macd-signal}
    elif identifier == 'cci':
        mean = roll(x, n)
        deviation = roll(x, n, lambda values: np.mean(abs(values - values.mean())))
        out = divide(x - mean, p['constant'] * deviation)
    elif identifier == 'roc':
        out = 100 * divide(x - lag(x, n), lag(x, n))
    elif identifier == 'momentum':
        out = x - lag(x, n)
    elif identifier == 'williams_r':
        maximum, minimum = roll(h, n, 'max'), roll(low, n, 'min')
        out = -100 * divide(maximum - c, maximum - minimum)
    elif identifier == 'trix':
        third = smooth(smooth(smooth(x, n), n), n)
        out = 100 * divide(third - lag(third), lag(third))
        return {'value': out, 'signal': smooth(out, p['signal_length'])}
    elif identifier == 'ultimate_oscillator':
        previous = lag(c)
        bp, tr = c - np.minimum(low, previous), np.maximum(h, previous) - np.minimum(low, previous)
        means = [divide(roll(bp, p[k], 'sum'), roll(tr, p[k], 'sum')) for k in ('short', 'medium', 'long')]
        out = 100 * (4 * means[0] + 2 * means[1] + means[2]) / 7
    elif identifier == 'awesome_oscillator':
        return {'histogram': roll(x, p['fast']) - roll(x, p['slow'])}
    elif identifier == 'atr':
        out = smooth(inputs.tr(), n, True)
    elif identifier == 'adx_dmi':
        up, down = h - lag(h), lag(low) - low
        valid = np.isfinite(up) & np.isfinite(down)
        plus = np.where(valid, np.where((up > down) & (up > 0), up, 0), np.nan)
        minus = np.where(valid, np.where((down > up) & (down > 0), down, 0), np.nan)
        tr = np.where(valid, inputs.tr(), np.nan)
        atr = smooth(tr, p['di_length'], True)
        plus_di = np.where(atr == 0, 0, 100 * divide(smooth(plus, p['di_length'], True), atr))
        minus_di = np.where(atr == 0, 0, 100 * divide(smooth(minus, p['di_length'], True), atr))
        dx = np.where(plus_di + minus_di == 0, 0, 100 * divide(abs(plus_di - minus_di), plus_di + minus_di))
        return {'plus_di': plus_di, 'minus_di': minus_di, 'adx': smooth(dx, p['adx_length'], True)}
    elif identifier == 'aroon':
        return {'up': roll(h, n+1, lambda values: 100*(n-np.argmax(values[::-1]))/n),
                    'down': roll(low, n+1, lambda values: 100*(n-np.argmin(values[::-1]))/n)}
    elif identifier == 'standard_deviation':
        out = roll(x, n, 'std', ddof=p['ddof'])
    elif identifier == 'historical_volatility':
        out = 100 * roll(np.log(divide(x, lag(x))), n, 'std', ddof=p['ddof']) * math.sqrt(p['bars_per_year'])
    elif identifier == 'choppiness_index':
        ratio = divide(roll(inputs.tr(), n, 'sum'), roll(h, n, 'max') - roll(low, n, 'min'))
        out = 100 * np.log10(ratio) / math.log10(n)
    elif identifier == 'volume':
        return {'volume': v.copy()}
    elif identifier == 'obv':
        changes = np.sign(x - lag(x)) * v
        if len(x):
            changes[0] = 0 if np.isfinite(x[0]) and np.isfinite(v[0]) else np.nan
        out = np.cumsum(changes)
    elif identifier == 'mfi':
        delta, flow = x - lag(x), x * v
        positive = np.where(np.isfinite(delta) & np.isfinite(v), np.where(delta > 0, flow, 0), np.nan)
        negative = np.where(np.isfinite(delta) & np.isfinite(v), np.where(delta < 0, flow, 0), np.nan)
        positive, negative = roll(positive, n, 'sum'), roll(negative, n, 'sum')
        out = 100 * divide(positive, positive+negative)
    elif identifier in ('cmf', 'accumulation_distribution', 'chaikin_oscillator'):
        flow = np.where(h == low, 0, divide(2*c-h-low, h-low)) * v
        if identifier == 'cmf':
            out = divide(roll(flow, n, 'sum'), roll(v, n, 'sum'))
        else:
            adl = np.cumsum(flow)
            out = adl if identifier == 'accumulation_distribution' else smooth(adl, p['fast']) - smooth(adl, p['slow'])
    elif identifier in ('session_vwap', 'anchored_vwap'):
        out = vwap(inputs, x, p, identifier == 'anchored_vwap')
    else:
        raise ValueError(f'No calculation for {identifier}')
    return {'value': out}


def with_gap_markers(bars: list[Bar], instrument: Instrument) -> tuple[list[Bar | None], list[int]]:
    """Mark missing open-session history without inventing source candles."""
    if not bars:
        return [], []
    first_day = pd.Timestamp(bars[0].start, unit='s', tz='UTC').tz_convert(instrument.timezone).date()
    last_day = pd.Timestamp(bars[-1].end, unit='s', tz='UTC').tz_convert(instrument.timezone).date()
    segments = session_segments(first_day, last_day + timedelta(days=1), instrument)
    expanded, positions = [], []
    segment_index = 0
    for i, bar in enumerate(bars):
        if i:
            previous = bars[i-1]
            if bar.start < previous.end:
                raise ValueError('Indicators require ordered nonoverlapping bars')
            while segment_index < len(segments) and segments[segment_index][1] <= previous.end:
                segment_index += 1
            if segment_index < len(segments):
                op, cl = segments[segment_index]
                if max(previous.end, op) < min(bar.start, cl):
                    expanded.append(None)
        positions.append(len(expanded))
        expanded.append(bar)
    return expanded, positions


def future_slots(dataset: Dataset, last: Bar, count: int) -> list[int]:
    """Calendar-derived presentation slots only: no forecast or synthetic OHLC."""
    instrument, interval = dataset.instrument, dataset.interval
    cursor = pd.Timestamp(last.end, unit='s', tz='UTC')
    last_start = pd.Timestamp(last.start, unit='s', tz='UTC').tz_convert(instrument.timezone)
    slots = []
    if interval in ('1w', '1mo'):
        day = (last_start.normalize() - pd.Timedelta(days=last_start.weekday())).date() if interval == '1w' else last_start.date().replace(day=1)
        for _ in range(count):
            day = day + timedelta(days=7) if interval == '1w' else (pd.Timestamp(day) + pd.offsets.MonthBegin()).date()
            end = day + timedelta(days=7) if interval == '1w' else (pd.Timestamp(day) + pd.offsets.MonthBegin()).date()
            segments = session_segments(day, end, instrument)
            if not segments:
                break
            first = segments[0][0]
            if instrument.session == 'provider-day':
                first, _ = bar_window(pd.Timestamp(first, unit='s', tz='UTC'), '1d', instrument)
            slots.append(first)
        return slots
    while len(slots) < count:
        day = cursor.tz_convert(instrument.timezone).date()
        segments = session_segments(day, day + timedelta(days=14), instrument)
        found = False
        for op, cl in segments:
            if cl <= cursor.timestamp():
                continue
            if interval == '1d':
                a, b = bar_window(pd.Timestamp(op, unit='s', tz='UTC'), '1d', instrument)
                if a <= last.start or (slots and a <= slots[-1]):
                    continue
                slots.append(a)
                cursor = pd.Timestamp(b, unit='s', tz='UTC')
            else:
                a = max(op, int(cursor.timestamp()))
                slots.append(a)
                cursor = pd.Timestamp(min(a+SECONDS[interval], cl), unit='s', tz='UTC')
            found = True
            break
        if not found:
            break
    return slots


def evaluate(request: IndicatorRequest, dataset: Dataset, bars: list[Bar]) -> IndicatorResponse:
    eligible = [b for b in bars if b.complete and (request.cutoff is None or b.end <= request.cutoff)]
    expanded, positions = with_gap_markers(eligible, dataset.instrument)
    inputs = Inputs(expanded, dataset.instrument, dataset.interval)
    results = []
    future_cache = {}
    for instance in request.instances:
        try:
            p = parameters(instance.definition_id, instance.parameters)
            if instance.definition_id in VOLUME_IDS and not np.isfinite(inputs['volume']).any():
                results.append(IndicatorResult(instance_id=instance.id, definition_id=instance.definition_id,
                    status='disabled', message='Meaningful volume is unavailable for this dataset.'))
                continue
            if (instance.definition_id == 'historical_volatility' and 'bars_per_year' not in instance.parameters
                    and (dataset.interval != '1d' or dataset.instrument.asset_class not in ('stock', 'etf', 'equity'))):
                raise ValueError('Set bars_per_year explicitly for this market and interval')
            values = calculate(instance.definition_id, inputs, p)
            lines = []
            for key, array in values.items():
                offset = p['displacement'] if instance.definition_id == 'ichimoku' and key in ('leading_a', 'leading_b') else -p['displacement'] if instance.definition_id == 'ichimoku' and key == 'lagging_close' else 0
                times = [b.start for b in eligible]
                if offset > 0 and eligible:
                    if offset not in future_cache:
                        future_cache[offset] = future_slots(dataset, eligible[-1], offset)
                    times += future_cache[offset]
                plot_times = [times[i+offset] if 0 <= i+offset < len(times) else None for i in range(len(eligible))]
                lines.append(IndicatorValues(output_id=key, values=[float(array[i]) if np.isfinite(array[i]) else None for i in positions], plot_offset_bars=offset, plot_times=plot_times))
            message = 'Completed bars only.'
            if len(expanded) != len(eligible):
                message += ' Missing trading history resets dependent windows; cumulative studies remain unavailable after a gap.'
            results.append(IndicatorResult(instance_id=instance.id, definition_id=instance.definition_id,
                status='ready', message=message, lines=lines))
        except ValueError as exc:
            results.append(IndicatorResult(instance_id=instance.id, definition_id=instance.definition_id,
                status='error', message=str(exc)))
    return IndicatorResponse(dataset_id=dataset.id, contract_version=VERSION,
        times=[b.start for b in eligible], available_at=[b.end for b in eligible], results=results)
