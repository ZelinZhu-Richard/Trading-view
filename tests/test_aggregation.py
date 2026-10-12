from datetime import UTC, datetime

from backend.models import Bar, Instrument
from backend.normalization import aggregate


def test_daily_to_weekly_marks_missing_days_and_partial_week_incomplete():
    instrument = Instrument(id='EXAMPLE:X', symbol='X', name='X', exchange='EXAMPLE', asset_class='other',
                            quote_currency='USD', timezone='UTC')
    start = int(datetime(2025, 1, 6, tzinfo=UTC).timestamp())
    bars = [Bar(start=start + i * 86400, end=start + (i + 1) * 86400, open=10 + i,
                high=12 + i, low=9 + i, close=11 + i, volume=1, source='fixture', feed='test') for i in range(7)]
    complete = aggregate(bars, '1d', '1w', instrument)
    assert len(complete) == 1 and complete[0].complete
    assert (complete[0].open, complete[0].high, complete[0].low, complete[0].close, complete[0].volume) == (10, 18, 9, 17, 7)
    missing = aggregate(bars[:3] + bars[4:], '1d', '1w', instrument)
    assert not missing[0].complete and missing[0].volume == 6
    partial = aggregate(bars[:2], '1d', '1w', instrument)
    assert not partial[0].complete
    assert partial[0].end == start + 7 * 86400  # Must not become available at Wednesday's start.


def test_intraday_aggregation_keeps_lunch_break_and_null_volume():
    instrument = Instrument(id='CSV:CHINA', symbol='CHINA', name='China fixture', exchange='SH',
                            asset_class='stock', quote_currency='CNY', timezone='Asia/Shanghai', calendar='XSHG')
    start = int(datetime(2025, 1, 6, 1, 30, tzinfo=UTC).timestamp())
    # Four half-hour morning bars; afternoon has a separate origin.
    bars = [Bar(start=start + i * 1800, end=start + (i + 1) * 1800, open=10,
                high=12, low=9, close=11, volume=None if i == 0 else 1, source='fixture', feed='test') for i in range(4)]
    result = aggregate(bars, '30m', '4h', instrument)
    assert len(result) == 1 and result[0].complete
    assert result[0].end == start + 7200 and result[0].volume is None
