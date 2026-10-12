from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Interval = Literal['1m', '5m', '15m', '30m', '1h', '4h', '1d', '1w', '1mo']
Adjustment = Literal['raw', 'split', 'total-return', 'unknown']
Finite = Annotated[float, Field(allow_inf_nan=False)]
Positive = Annotated[float, Field(gt=0, allow_inf_nan=False)]


class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid', json_schema_serialization_defaults_required=True)
    schema_version: Literal[1] = 1


class Instrument(Contract):
    id: str = Field(min_length=1, max_length=160, pattern=r'^[\w.:/\-]+$')
    symbol: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1)
    exchange: str
    asset_class: Literal['stock', 'etf', 'equity', 'crypto', 'forex', 'other']
    base_currency: str | None = None
    quote_currency: str = Field(pattern=r'^[A-Z]{3,12}$')
    timezone: str
    calendar: str = '24/7'
    session: Literal['regular', 'provider-day', 'continuous'] = 'regular'
    price_tick: Decimal = Field(default=Decimal('0.01'), gt=0, allow_inf_nan=False)
    quantity_step: Decimal = Field(default=Decimal(1), gt=0, allow_inf_nan=False)
    provider_symbols: dict[str, str] = Field(default_factory=dict)

    @field_validator('timezone')
    @classmethod
    def valid_zone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError('Choose an IANA timezone, such as America/New_York') from exc
        return value


class Bar(Contract):
    start: int
    end: int
    open: Positive
    high: Positive
    low: Positive
    close: Positive
    volume: Annotated[float, Field(ge=0, allow_inf_nan=False)] | None = None
    complete: bool = True
    source: str
    feed: str
    adjustment: Adjustment = 'raw'

    @model_validator(mode='after')
    def validate_bar(self):
        if self.end <= self.start:
            raise ValueError('Bar end must follow its start')
        if self.low > min(self.open, self.close) or self.high < max(self.open, self.close):
            raise ValueError('OHLC must satisfy low ≤ open/close ≤ high')
        return self


class Quote(Contract):
    instrument_id: str
    price: Positive
    timestamp: int
    source: str
    feed: str
    freshness: Literal['live', 'delayed', 'historical', 'imported', 'stale', 'unavailable']


class ProviderCapabilities(Contract):
    id: str
    name: str
    markets: list[str]
    intervals: list[Interval]
    streaming: bool
    requires_keys: bool
    history: str
    limitations: list[str]
    status: Literal['not-configured', 'available', 'connected', 'disconnected', 'throttled']


class Dataset(Contract):
    id: str
    hash: str
    instrument: Instrument
    interval: Interval
    source: str
    feed: str
    adjustment: Adjustment
    created_at: str
    first_start: int
    last_end: int
    row_count: int
    limitations: list[str] = Field(default_factory=list)
    parent_id: str | None = None


class CandleStatus(Contract):
    active: bool = False
    series_id: str
    dataset: Dataset
    status: Literal['waiting', 'updating', 'current', 'catching-up', 'stale']
    message: str
    last_success: str | None = None
    next_check: float = 0
    revised_history: bool = False


class DatasetView(Contract):
    dataset: Dataset
    bars: list[Bar]


class ImportRequest(Contract):
    csv_text: str = Field(max_length=30_000_000)
    instrument: Instrument
    interval: Interval = '1d'
    timezone: str | None = None
    timestamp_format: str | None = None
    columns: dict[str, str] = Field(default_factory=lambda: {
        'timestamp': 'timestamp', 'open': 'open', 'high': 'high',
        'low': 'low', 'close': 'close', 'volume': 'volume',
    })
    adjustment: Adjustment = 'raw'
    conflict_policy: Literal['reject', 'first', 'last'] = 'reject'


class ImportIssue(Contract):
    row: int
    message: str


class ImportPreview(Contract):
    token: str
    columns: list[str]
    preview: list[Bar]
    valid_rows: int
    invalid_rows: int
    exact_duplicates: int
    conflicting_duplicates: int
    errors: list[ImportIssue]
    warnings: list[str]
    can_commit: bool


class Anchor(Contract):
    time: Finite = Field(ge=-62135596800, le=253402300799)
    price: Positive


DrawingKind = Literal[
    'trend', 'ray', 'extended', 'horizontal', 'horizontal-ray', 'vertical', 'cross',
    'parallel-channel', 'regression-channel', 'pitchfork', 'fib-retracement',
    'fib-extension', 'rectangle', 'ellipse', 'triangle', 'brush', 'path', 'arrow',
    'text', 'price-range', 'date-range', 'date-price-range', 'long-position', 'short-position',
]


class Drawing(Contract):
    id: str
    kind: DrawingKind
    instrument_id: str
    anchors: list[Anchor] = Field(min_length=1, max_length=10000)
    color: str = Field(default='#54b4df', pattern=r'^#[0-9a-fA-F]{6}$')
    opacity: float = Field(default=1, ge=0, le=1)
    width: int = Field(default=2, ge=1, le=8)
    label: str = Field(default='', max_length=1000)
    levels: list[Finite] = Field(default_factory=lambda: [0, .236, .382, .5, .618, .786, 1], max_length=30)
    visible: bool = True
    locked: bool = False
    quantity: Decimal = Field(default=Decimal(1), gt=0, allow_inf_nan=False)

    @model_validator(mode='after')
    def complete_anchors(self):
        one = {'horizontal', 'horizontal-ray', 'vertical', 'cross', 'text'}
        three = {'parallel-channel', 'pitchfork', 'fib-extension', 'triangle', 'long-position', 'short-position'}
        required = 1 if self.kind in one else 3 if self.kind in three else 2
        if len(self.anchors) < required or (self.kind not in ('brush', 'path') and len(self.anchors) != required):
            raise ValueError(f'{self.kind} requires {required} anchors' + (' or more' if self.kind in ('brush', 'path') else ''))
        return self


class DrawingMeasurementRequest(Contract):
    instrument: Instrument
    drawings: list[Drawing] = Field(max_length=1000)


class IndicatorInstance(Contract):
    id: str
    definition_id: str
    parameters: dict[str, float | str | bool] = Field(default_factory=dict)
    visible: bool = True
    color: str = '#5fa8ed'
    width: int = Field(default=2, ge=1, le=5)
    pane: int = Field(default=0, ge=0, le=50)


class IndicatorParameter(Contract):
    default: float | str | bool | None
    kind: Literal['integer', 'number', 'choice', 'boolean', 'timestamp', 'fixed']
    minimum: float | None = None
    maximum: float | None = None
    choices: list[str] = Field(default_factory=list)


class IndicatorOutput(Contract):
    id: str
    pane: str
    units: str
    plot_offset_bars: int = 0


class IndicatorDefinition(Contract):
    id: str
    name: str
    category: str
    contract_version: str
    parameters: dict[str, IndicatorParameter]
    outputs: list[IndicatorOutput]
    formula: str
    warmup: str
    edge_cases: str
    notes: list[str]
    source_urls: list[str]
    volume_required: bool


class IndicatorValues(Contract):
    output_id: str
    values: list[float | None]
    plot_offset_bars: int = 0
    plot_times: list[int | None] = Field(default_factory=list)


class IndicatorResult(Contract):
    instance_id: str
    definition_id: str
    status: Literal['ready', 'disabled', 'error']
    message: str = ''
    lines: list[IndicatorValues] = Field(default_factory=list)


class IndicatorRequest(Contract):
    dataset_id: str
    instances: list[IndicatorInstance] = Field(max_length=50)
    cutoff: int | None = None


class IndicatorResponse(Contract):
    dataset_id: str
    contract_version: str
    times: list[int]
    available_at: list[int]
    results: list[IndicatorResult]


class ChartState(Contract):
    id: str
    dataset_id: str | None = None
    kind: Literal['candlestick', 'bar', 'line', 'area', 'baseline', 'heikin-ashi'] = 'candlestick'
    scale: Literal['linear', 'logarithmic', 'percentage'] = 'linear'
    timezone: str = 'UTC'
    indicators: list[IndicatorInstance] = Field(default_factory=list, max_length=50)
    drawings: list[Drawing] = Field(default_factory=list)
    show_volume: bool = True
    follow_live: bool = False
    link_group: str | None = 'main'


class WatchlistItem(Contract):
    instrument_id: str = Field(min_length=1, max_length=160)
    section: str = Field(default='', max_length=100)


class Watchlist(Contract):
    id: str
    name: str = Field(min_length=1, max_length=100)
    items: list[WatchlistItem] = Field(default_factory=list)
    sections: list[str] = Field(default_factory=list)
    sort: Literal['manual', 'symbol', 'last', 'change', 'changePercent'] = 'manual'

    @model_validator(mode='after')
    def unique_items(self):
        ids = [item.instrument_id for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError('A watchlist cannot contain duplicate instrument identities')
        if len(self.sections) != len(set(self.sections)) or any(not s.strip() or len(s) > 100 for s in self.sections):
            raise ValueError('Section names must be nonempty, unique, and at most 100 characters')
        return self


class Workspace(Contract):
    id: str = 'default'
    name: str = 'My workspace'
    revision: int = Field(default=0, ge=0)
    theme: Literal['dark', 'light'] = 'dark'
    layout: Literal[1, 2, 4] = 1
    charts: list[ChartState] = Field(default_factory=lambda: [ChartState(id=f'chart-{i}') for i in range(4)])
    active_chart: int = Field(default=0, ge=0, le=3)
    watchlists: list[Watchlist] = Field(default_factory=lambda: [Watchlist(id='main', name='My watchlist')])
    active_watchlist: str = 'main'
    sidebar_width: int = Field(default=280, ge=200, le=600)
    bottom_height: int = Field(default=250, ge=100, le=800)
    sidebar_open: bool = True
    bottom_open: bool = True
    link_symbol: bool = False
    link_interval: bool = False
    link_crosshair: bool = True
    link_range: bool = True
    indicator_templates: dict[str, list[IndicatorInstance]] = Field(default_factory=dict)

    @model_validator(mode='after')
    def valid_workspace(self):
        if len(self.charts) != 4 or len({c.id for c in self.charts}) != 4:
            raise ValueError('Workspace must retain four uniquely identified chart slots')
        if self.active_chart >= self.layout:
            raise ValueError('Active chart must be visible in the selected layout')
        ids = [w.id for w in self.watchlists]
        if len(ids) != len(set(ids)) or self.active_watchlist not in ids:
            raise ValueError('Active watchlist must name one unique saved list')
        return self


class WatchlistsDocument(Contract):
    workspace_revision: int = Field(ge=0)
    watchlists: list[Watchlist]
    active_watchlist: str


class DrawingsDocument(Contract):
    workspace_revision: int = Field(ge=0)
    drawings: list[Drawing]

    @model_validator(mode='after')
    def unique_objects(self):
        if len({d.id for d in self.drawings}) != len(self.drawings):
            raise ValueError('Drawing identities must be unique within a chart')
        return self


class StrategyDefinition(Contract):
    id: str
    name: str = Field(min_length=1, max_length=120)
    source: str = Field(max_length=500000)
    kind: Literal['strategy', 'indicator']
    revision: int = 0
    parameters: dict[str, float | str | bool] = Field(default_factory=dict)
    subscriptions: list[str] = Field(default_factory=list)


class ScriptParameter(Contract):
    type: Literal['int', 'float', 'bool', 'str']
    default: float | str | bool
    minimum: float | None = None
    maximum: float | None = None
    choices: list[float | str | bool] = Field(default_factory=list)
    description: str = ''


class ScriptDiagnostic(Contract):
    line: int
    column: int
    severity: Literal['error', 'warning']
    message: str


class ScriptAnalysis(Contract):
    valid: bool
    script_hash: str
    diagnostics: list[ScriptDiagnostic]
    parameters: dict[str, ScriptParameter]
    hooks: list[str]


class AlertDefinition(Contract):
    id: str
    revision: int = Field(default=0, ge=0)
    name: str = Field(min_length=1, max_length=100)
    dataset_id: str
    field: Literal['open', 'high', 'low', 'close'] = 'close'
    indicator: IndicatorInstance | None = None
    output_id: str = 'value'
    condition: Literal['above', 'below', 'crosses_above', 'crosses_below'] = 'crosses_above'
    threshold: Finite
    recurring: bool = False
    enabled: bool = True
    completed_bars: Literal[True] = True


class AlertEvent(Contract):
    id: str
    alert_id: str
    alert_name: str
    dataset_id: str
    bar_end: int
    evaluated_at: str
    value: Finite
    threshold: Finite
    condition: str
    source: str
    feed: str


class AlertState(Contract):
    last_end: int
    previous: Finite | None
    fired: bool
    last_dataset_id: str
    message: str
    updated_at: str


class AlertServiceStatus(Contract):
    running: bool
    last_cycle: str | None
    error: str
    states: dict[str, AlertState | None]
    scope: str


def utc_now() -> str:
    from datetime import UTC
    return datetime.now(UTC).isoformat()
