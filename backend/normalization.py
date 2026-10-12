from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from itertools import pairwise

import exchange_calendars as xcals
import pandas as pd

from .models import Bar, ImportIssue, ImportPreview, ImportRequest, Instrument, Interval

SECONDS = {'1m': 60, '5m': 300, '15m': 900, '30m': 1800, '1h': 3600, '4h': 14400, '1d': 86400}


@lru_cache(maxsize=32)
def calendar(name: str):
    # Precomputed calendars have real coverage boundaries; never extrapolate holidays.
    if name not in xcals.get_calendar_names():
        raise ValueError(f'Unknown exchange calendar: {name}')
    base = xcals.get_calendar(name)
    start = max(pd.Timestamp('1990-01-01'), base.bound_min() or pd.Timestamp('1990-01-01'))
    end = min(pd.Timestamp('2040-12-31'), base.bound_max() or pd.Timestamp('2040-12-31'))
    return xcals.get_calendar(name, start=start, end=end)


def timestamp(value: str, zone: str | None, fmt: str | None) -> pd.Timestamp:
    t = pd.Timestamp(datetime.strptime(value, fmt)) if fmt else pd.Timestamp(value)
    if pd.isna(t):
        raise ValueError('Timestamp is missing')
    if t.tzinfo is None:
        if not zone:
            raise ValueError('Timezone is required for timestamps without an offset')
        # Reject ambiguous and nonexistent local times; never guess a DST fold.
        try:
            t = t.tz_localize(zone, ambiguous='raise', nonexistent='raise')
        except Exception as exc:
            raise ValueError(f'Invalid or ambiguous local timestamp in {zone}: {value}') from exc
    return t.tz_convert('UTC')


def bar_window(t: pd.Timestamp, interval: Interval, instrument: Instrument) -> tuple[int, int]:
    local_day = t.tz_convert(instrument.timezone).date()
    duration = SECONDS.get(interval)
    if interval in ('1w', '1mo'):
        raise ValueError('Import base daily or intraday bars; derive weekly/monthly intervals explicitly')
    if instrument.calendar in ('24/7', '24/5'):
        if instrument.calendar == '24/5' and local_day.weekday() >= 5:
            raise ValueError('Timestamp falls outside the configured weekday session')
        start = int(t.timestamp())
        if interval == '1d':
            start = int(pd.Timestamp(local_day, tz=instrument.timezone).timestamp())
            end = int(pd.Timestamp(local_day + timedelta(days=1), tz=instrument.timezone).timestamp())
        else:
            end = start + duration
        return start, end
    cal = calendar(instrument.calendar)
    day = pd.Timestamp(local_day)
    if not cal.is_session(day):
        raise ValueError('Timestamp falls on a closed exchange session')
    op, cl = cal.session_open(day), cal.session_close(day)
    if interval == '1d':
        if instrument.session == 'provider-day':
            start = pd.Timestamp(local_day, tz=instrument.timezone)
            end = pd.Timestamp(local_day + timedelta(days=1), tz=instrument.timezone)
            return int(start.timestamp()), int(end.timestamp())
        return int(op.timestamp()), int(cl.timestamp())
    if not op <= t < cl:
        raise ValueError('Timestamp is outside regular exchange hours')
    br_start, br_end = cal.session_break_start(day), cal.session_break_end(day)
    if not pd.isna(br_start) and br_start <= t < br_end:
        raise ValueError('Timestamp falls within the exchange lunch break')
    boundary = br_start if not pd.isna(br_start) and t < br_start else cl
    return int(t.timestamp()), int(min(t + pd.Timedelta(seconds=duration), boundary).timestamp())


def parse_import(request: ImportRequest) -> tuple[ImportPreview, list[Bar]]:
    stream = io.StringIO(request.csv_text.lstrip('\ufeff'))
    reader = csv.DictReader(stream)
    columns = reader.fieldnames or []
    if len(columns) != len(set(columns)):
        raise ValueError('CSV column names must be unique before mapping')
    required = ('timestamp', 'open', 'high', 'low', 'close')
    missing = [key for key in required if request.columns.get(key) not in columns]
    if missing:
        raise ValueError('Map the required columns: ' + ', '.join(missing))
    bars: dict[int, Bar] = {}
    errors, exact, conflicting, invalid = [], 0, 0, 0
    now = int(datetime.now(UTC).timestamp())
    for row_index, row in enumerate(reader, start=2):
        try:
            if None in row:
                raise ValueError('Row has more fields than the header')
            t = timestamp(row[request.columns['timestamp']], request.timezone, request.timestamp_format)
            start, end = bar_window(t, request.interval, request.instrument)
            volume = row.get(request.columns.get('volume', ''), '')
            bar = Bar(
                start=start, end=end,
                **{key: float(row[request.columns[key]]) for key in required[1:]},
                volume=None if volume is None or not volume.strip() else float(volume),
                complete=end <= now, source='csv', feed='user-import', adjustment=request.adjustment,
            )
            if start in bars:
                if bars[start] == bar:
                    exact += 1
                    continue
                conflicting += 1
                if request.conflict_policy == 'reject':
                    raise ValueError('Conflicting duplicate timestamp; choose keep-first or keep-last')
                if request.conflict_policy == 'first':
                    continue
            bars[start] = bar
        except (ValueError, TypeError, KeyError, OverflowError) as exc:
            invalid += 1
            errors.append(ImportIssue(row=row_index, message=str(exc)))
    ordered = sorted(bars.values(), key=lambda b: b.start)
    # A pair of overlapping source bars makes causality ambiguous.
    overlap = any(a.end > b.start for a, b in pairwise(ordered))
    warnings = ['Imported data; corporate-action coverage is supplied by the user.']
    if overlap:
        warnings.append('Overlapping bar windows must be corrected before import.')
    if any(b.volume is None for b in ordered):
        warnings.append('Some volume is missing. Volume-dependent indicators require complete volume.')
    if request.instrument.calendar == '24/5':
        warnings.append('Weekday calendar has no venue-specific holiday schedule.')
    token = hashlib.sha256(request.model_dump_json().encode()).hexdigest()
    return ImportPreview(
        token=token, columns=columns, preview=ordered[:20], valid_rows=len(ordered),
        invalid_rows=invalid, exact_duplicates=exact, conflicting_duplicates=conflicting,
        errors=errors, warnings=warnings, can_commit=bool(ordered) and invalid == 0 and not overlap,
    ), ordered


def aggregate(bars: list[Bar], source: Interval, target: Interval, instrument: Instrument) -> list[Bar]:
    if source == target:
        return bars
    if target in SECONDS and (source not in SECONDS or SECONDS[target] <= SECONDS[source]):
        raise ValueError('Cannot derive a finer interval from coarser data')
    if source in ('1w', '1mo') or target not in ('1w', '1mo', *SECONDS.keys()):
        raise ValueError('Unsupported interval transformation')
    identities = {(b.source, b.feed, b.adjustment) for b in bars}
    if len(identities) > 1:
        raise ValueError('Cannot merge differing feeds or adjustment bases')
    if source in SECONDS and target in SECONDS and SECONDS[target] % SECONDS[source]:
        raise ValueError('Target interval must be a whole multiple of the source interval')
    grouped: dict[tuple[int, int], list[Bar]] = {}
    for bar in bars:
        t = pd.Timestamp(bar.start, unit='s', tz='UTC').tz_convert(instrument.timezone)
        if target == '1w':
            day = t.date() - timedelta(days=t.weekday())
            end_day = day + timedelta(days=7)
            segments = session_segments(day, end_day, instrument)
            key = (segments[0][0], segments[-1][1])
        elif target == '1mo':
            day = t.date().replace(day=1)
            end_day = (pd.Timestamp(day) + pd.offsets.MonthBegin(1)).date()
            segments = session_segments(day, end_day, instrument)
            key = (segments[0][0], segments[-1][1])
        elif target == '1d':
            key = bar_window(t, '1d', instrument)
        else:
            # Anchor buckets to the actual session segment, preserving lunch breaks.
            if instrument.calendar in ('24/7', '24/5'):
                origin = t.normalize()
            else:
                cal = calendar(instrument.calendar)
                origin = cal.session_open(pd.Timestamp(t.date()))
                br_end = cal.session_break_end(pd.Timestamp(t.date()))
                if not pd.isna(br_end) and t >= br_end:
                    origin = br_end
            bucket = int((t.timestamp() - origin.timestamp()) // SECONDS[target])
            start = origin + pd.Timedelta(seconds=bucket * SECONDS[target])
            key = bar_window(start, target, instrument)
        if target in ('1w', '1mo') and instrument.session == 'provider-day':
            first = pd.Timestamp(key[0], unit='s', tz='UTC')
            last = pd.Timestamp(key[1] - 1, unit='s', tz='UTC')
            key = (bar_window(first, '1d', instrument)[0], bar_window(last, '1d', instrument)[1])
        if bar.start < key[0] or bar.end > key[1]:
            raise ValueError('Source bar crosses the requested aggregation boundary')
        grouped.setdefault(key, []).append(bar)
    result = []
    for (start, end), group in grouped.items():
        first, last = group[0], group[-1]
        local_start = pd.Timestamp(start, unit='s', tz='UTC').tz_convert(instrument.timezone).date()
        local_end = pd.Timestamp(end - 1, unit='s', tz='UTC').tz_convert(instrument.timezone).date()
        segments = session_segments(local_start, local_end + timedelta(days=1), instrument)
        expected = set()
        if source == '1d':
            for day in pd.date_range(local_start, local_end):
                day_segments = session_segments(day.date(), day.date() + timedelta(days=1), instrument)
                if day_segments:
                    t = pd.Timestamp(day_segments[0][0], unit='s', tz='UTC')
                    a, b = bar_window(t, '1d', instrument)
                    if start <= a and b <= end:
                        expected.add((a, b))
        else:
            for op, cl in segments:
                for a in range(op, cl, SECONDS[source]):
                    b = min(a + SECONDS[source], cl)
                    if start <= a and b <= end:
                        expected.add((a, b))
        complete = all(b.complete for b in group) and {(b.start, b.end) for b in group} == expected
        result.append(Bar(start=start, end=end, open=first.open, high=max(b.high for b in group),
                          low=min(b.low for b in group), close=last.close,
                          volume=None if any(b.volume is None for b in group) else sum(b.volume for b in group),
                          complete=complete, source=first.source,
                          feed=first.feed, adjustment=first.adjustment))
    return result


def session_segments(start_day, end_day, instrument: Instrument) -> list[tuple[int, int]]:
    """Trading segments in [start day, end day), including DST and session breaks."""
    result = []
    for day in pd.date_range(start_day, end_day, inclusive='left'):
        if instrument.calendar in ('24/7', '24/5'):
            if instrument.calendar == '24/5' and day.weekday() >= 5:
                continue
            start = day.tz_localize(instrument.timezone)
            end = (day + pd.Timedelta(days=1)).tz_localize(instrument.timezone)
            result.append((int(start.timestamp()), int(end.timestamp())))
        else:
            cal = calendar(instrument.calendar)
            if not cal.is_session(day):
                continue
            op, cl = cal.session_open(day), cal.session_close(day)
            br_start, br_end = cal.session_break_start(day), cal.session_break_end(day)
            if pd.isna(br_start):
                result.append((int(op.timestamp()), int(cl.timestamp())))
            else:
                result.extend([(int(op.timestamp()), int(br_start.timestamp())),
                               (int(br_end.timestamp()), int(cl.timestamp()))])
    return result


def dataset_digest(instrument: Instrument, interval: Interval, bars: list[Bar]) -> str:
    value = {'instrument': instrument.model_dump(mode='json'), 'interval': interval,
             'bars': [b.model_dump(mode='json') for b in bars]}
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
