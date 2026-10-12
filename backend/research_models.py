"""Versioned contracts shared by backtests, replay, and paper accounts."""
from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field, model_validator

from .models import Contract, Dataset, Finite, StrategyDefinition

Money = Annotated[Decimal, Field(allow_inf_nan=False)]
NonnegativeMoney = Annotated[Decimal, Field(ge=0, allow_inf_nan=False)]
PositiveMoney = Annotated[Decimal, Field(gt=0, allow_inf_nan=False)]
Currency = Annotated[str, Field(pattern=r'^[A-Z]{3,12}$')]


class ExecutionSettings(Contract):
    initial_capital: PositiveMoney = Decimal(100000)
    reporting_currency: Currency = 'USD'
    fee_bps: NonnegativeMoney = Field(default=Decimal(0), le=10000)
    fee_per_order: NonnegativeMoney = Decimal(0)
    slippage_bps: NonnegativeMoney = Field(default=Decimal(0), lt=10000)
    allow_short: bool = True
    allow_fixture_data: bool = False
    seed: int = 0
    start: int | None = None
    end: int | None = None
    fx_max_age_seconds: int | None = Field(default=None, gt=0)
    corporate_action_coverage: Literal['unknown', 'supplied-complete', 'supplied-partial'] = 'unknown'

    @model_validator(mode='after')
    def date_order(self):
        if self.start is not None and self.end is not None and self.start >= self.end:
            raise ValueError('Run end must follow start')
        return self


class OrderRequest(Contract):
    instrument_id: str
    side: Literal['buy', 'sell']
    quantity: PositiveMoney
    kind: Literal['market', 'limit', 'stop', 'bracket'] = 'market'
    entry_kind: Literal['market', 'limit', 'stop'] = 'market'
    limit_price: PositiveMoney | None = None
    stop_price: PositiveMoney | None = None
    take_profit: PositiveMoney | None = None
    stop_loss: PositiveMoney | None = None
    tag: str = Field(default='', max_length=200)

    @model_validator(mode='after')
    def order_prices(self):
        actual = self.entry_kind if self.kind == 'bracket' else self.kind
        if actual == 'limit' and self.limit_price is None:
            raise ValueError('Limit orders require limit_price')
        if actual == 'stop' and self.stop_price is None:
            raise ValueError('Stop orders require stop_price')
        if actual != 'limit' and self.limit_price is not None:
            raise ValueError('limit_price is only valid for a limit entry')
        if actual != 'stop' and self.stop_price is not None:
            raise ValueError('stop_price is only valid for a stop entry')
        if self.kind == 'bracket':
            if self.take_profit is None or self.stop_loss is None:
                raise ValueError('Bracket orders require take_profit and stop_loss')
            if (self.take_profit-self.stop_loss) * (1 if self.side == 'buy' else -1) <= 0:
                raise ValueError('Bracket target and stop must be on opposite sides of the entry direction')
        elif self.take_profit is not None or self.stop_loss is not None or self.entry_kind != 'market':
            raise ValueError('Bracket fields require kind=bracket')
        return self


class SimulationOrder(Contract):
    id: str
    sequence: int
    request: OrderRequest
    submitted_at: int
    eligible_from: int
    status: Literal['pending', 'filled', 'cancelled', 'rejected'] = 'pending'
    reason: str | None = None
    parent_id: str | None = None
    sibling_id: str | None = None
    activated_bar_start: int | None = None
    activation_phase: Literal['open', 'touch'] | None = None
    completed_at: int | None = None


class FXLeg(Contract):
    from_currency: str
    to_currency: str
    rate: PositiveMoney
    instrument_id: str
    dataset_id: str
    dataset_hash: str
    source: str
    feed: str
    available_at: int
    age_seconds: int
    inverse: bool


class FXConversion(Contract):
    at: int
    from_currency: str
    to_currency: str
    rate: PositiveMoney
    legs: list[FXLeg] = Field(default_factory=list)
    purpose: str


class Fill(Contract):
    id: str
    order_id: str
    instrument_id: str
    side: Literal['buy', 'sell']
    quantity: PositiveMoney
    price: PositiveMoney
    fee: NonnegativeMoney
    quote_currency: str
    time: int
    bar_start: int
    phase: Literal['open', 'touch']
    dataset_id: str
    source: str
    feed: str
    conversion: FXConversion


class Position(Contract):
    instrument_id: str
    quote_currency: str
    quantity: Money = Decimal(0)
    average_price: NonnegativeMoney = Decimal(0)
    realized_gross: Money = Decimal(0)
    fees: NonnegativeMoney = Decimal(0)
    dividends: Money = Decimal(0)
    short_collateral: NonnegativeMoney = Decimal(0)
    short_proceeds: NonnegativeMoney = Decimal(0)
    last_price: PositiveMoney | None = None
    last_price_time: int | None = None
    unrealized: Money | None = None
    market_value: Money | None = None


class Trade(Contract):
    id: str
    instrument_id: str
    time: int
    direction: Literal['long', 'short']
    quantity: PositiveMoney
    entry_price: PositiveMoney
    exit_price: PositiveMoney
    gross_pnl: Money
    allocated_fees: NonnegativeMoney
    net_pnl: Money
    quote_currency: str
    reporting_pnl: Money
    conversion: FXConversion


class Portfolio(Contract):
    time: int
    reporting_currency: str
    cash: dict[str, Money]
    restricted_cash: dict[str, Money]
    positions: list[Position]
    equity: Money | None
    gross_exposure: NonnegativeMoney | None
    valuation_errors: list[str] = Field(default_factory=list)
    conversions: list[FXConversion] = Field(default_factory=list)
    insolvent: bool = False


class CorporateAction(Contract):
    instrument_id: str
    time: int
    kind: Literal['split', 'dividend']
    value: PositiveMoney
    source: str = Field(min_length=1)


class EquityPoint(Contract):
    time: int
    equity: Money | None
    gross_exposure: NonnegativeMoney | None
    drawdown: Finite | None
    valuation_errors: list[str] = Field(default_factory=list)


class Metric(Contract):
    value: Finite | None
    unit: str
    convention: str
    undefined_reason: str | None = None


class Contribution(Contract):
    instrument_id: str
    quote_currency: str
    realized_gross: Money
    unrealized: Money | None
    fees: NonnegativeMoney
    dividends: Money
    reporting_pnl: Money | None


class ResearchResult(Contract):
    engine_version: str
    settings: ExecutionSettings
    final_portfolio: Portfolio
    orders: list[SimulationOrder]
    fills: list[Fill]
    trades: list[Trade]
    equity: list[EquityPoint]
    metrics: dict[str, Metric]
    contributions: list[Contribution]
    currency_translation: Money | None
    conversions: list[FXConversion]
    corporate_actions: list[dict]
    logs: list[dict]
    plots: list[dict]
    limitations: list[str]


class WorkerLimits(Contract):
    deadline_seconds: int = Field(default=300, ge=1, le=3600)
    memory_mb: int = Field(default=1024, ge=128, le=8192)


class ResearchRequest(Contract):
    name: str = Field(default='Research run', min_length=1, max_length=120)
    script: StrategyDefinition
    dataset_ids: list[str] = Field(min_length=1, max_length=100)
    parameters: dict[str, float | str | bool] = Field(default_factory=dict)
    settings: ExecutionSettings = Field(default_factory=ExecutionSettings)
    actions: list[CorporateAction] = Field(default_factory=list, max_length=100000)
    limits: WorkerLimits = Field(default_factory=WorkerLimits)

    @model_validator(mode='after')
    def unique_datasets(self):
        if len(set(self.dataset_ids)) != len(self.dataset_ids):
            raise ValueError('Dataset selection contains duplicates')
        return self


class ResearchJob(Contract):
    id: str
    name: str
    revision: int = 0
    status: Literal['queued', 'running', 'completed', 'failed', 'cancelled', 'interrupted']
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    snapshot_hash: str
    result_hash: str | None = None
    progress: Finite = 0
    completed_events: int = 0
    total_events: int = 0
    elapsed_seconds: Finite = 0
    peak_memory_bytes: int = 0
    error: str | None = None
    limits: WorkerLimits




class AccountRequest(Contract):
    name: str = Field(min_length=1, max_length=120)
    mode: Literal['replay', 'paper']
    dataset_ids: list[str] = Field(min_length=1, max_length=100)
    settings: ExecutionSettings = Field(default_factory=ExecutionSettings)
    actions: list[CorporateAction] = Field(default_factory=list, max_length=100000)
    cursor: int | None = None


class AccountCommand(Contract):
    time: int
    kind: Literal['order', 'cancel']
    order: OrderRequest | None = None
    order_id: str | None = None


class PaperAccount(Contract):
    paused: bool = False
    id: str
    name: str
    mode: Literal['replay', 'paper']
    revision: int = 0
    dataset_ids: list[str]
    settings: ExecutionSettings
    actions: list[CorporateAction] = Field(default_factory=list)
    commands: list[AccountCommand] = Field(default_factory=list)
    cursor: int
    created_at: str
    error: str | None = None


class AccountView(Contract):
    service_error: str | None = None
    account: PaperAccount
    datasets: list[Dataset]
    portfolio: Portfolio
    orders: list[SimulationOrder]
    fills: list[Fill]
    trades: list[Trade]
    next_time: int | None
    first_time: int
    last_time: int
    completion_times: list[int]


class AccountSeek(Contract):
    time: int
    revision: int


class AccountOrder(Contract):
    order: OrderRequest
    revision: int


class AccountCancel(Contract):
    order_id: str
    revision: int
