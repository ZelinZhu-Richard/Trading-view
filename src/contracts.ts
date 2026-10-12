// Generated from backend/models.py. Run npm run contracts; do not edit.

export type AccountCancel = {
  "schema_version": 1;
  "order_id": string;
  "revision": number;
};

export type AccountCommand = {
  "schema_version": 1;
  "time": number;
  "kind": "order" | "cancel";
  "order": (OrderRequest | null);
  "order_id": (string | null);
};

export type AccountOrder = {
  "schema_version": 1;
  "order": OrderRequest;
  "revision": number;
};

export type AccountRequest = {
  "schema_version": 1;
  "name": string;
  "mode": "replay" | "paper";
  "dataset_ids": Array<string>;
  "settings": ExecutionSettings;
  "actions": Array<CorporateAction>;
  "cursor": (number | null);
};

export type AccountSeek = {
  "schema_version": 1;
  "time": number;
  "revision": number;
};

export type AccountView = {
  "schema_version": 1;
  "service_error": (string | null);
  "account": PaperAccount;
  "datasets": Array<Dataset>;
  "portfolio": Portfolio;
  "orders": Array<SimulationOrder>;
  "fills": Array<Fill>;
  "trades": Array<Trade>;
  "next_time": (number | null);
  "first_time": number;
  "last_time": number;
  "completion_times": Array<number>;
};

export type AlertDefinition = {
  "schema_version": 1;
  "id": string;
  "revision": number;
  "name": string;
  "dataset_id": string;
  "field": "open" | "high" | "low" | "close";
  "indicator": (IndicatorInstance | null);
  "output_id": string;
  "condition": "above" | "below" | "crosses_above" | "crosses_below";
  "threshold": number;
  "recurring": boolean;
  "enabled": boolean;
  "completed_bars": true;
};

export type AlertEvent = {
  "schema_version": 1;
  "id": string;
  "alert_id": string;
  "alert_name": string;
  "dataset_id": string;
  "bar_end": number;
  "evaluated_at": string;
  "value": number;
  "threshold": number;
  "condition": string;
  "source": string;
  "feed": string;
};

export type AlertServiceStatus = {
  "schema_version": 1;
  "running": boolean;
  "last_cycle": (string | null);
  "error": string;
  "states": Record<string, (AlertState | null)>;
  "scope": string;
};

export type AlertState = {
  "schema_version": 1;
  "last_end": number;
  "previous": (number | null);
  "fired": boolean;
  "last_dataset_id": string;
  "message": string;
  "updated_at": string;
};

export type Anchor = {
  "schema_version": 1;
  "time": number;
  "price": number;
};

export type Bar = {
  "schema_version": 1;
  "start": number;
  "end": number;
  "open": number;
  "high": number;
  "low": number;
  "close": number;
  "volume": (number | null);
  "complete": boolean;
  "source": string;
  "feed": string;
  "adjustment": "raw" | "split" | "total-return" | "unknown";
};

export type CandleStatus = {
  "schema_version": 1;
  "active": boolean;
  "series_id": string;
  "dataset": Dataset;
  "status": "waiting" | "updating" | "current" | "catching-up" | "stale";
  "message": string;
  "last_success": (string | null);
  "next_check": number;
  "revised_history": boolean;
};

export type ChartState = {
  "schema_version": 1;
  "id": string;
  "dataset_id": (string | null);
  "kind": "candlestick" | "bar" | "line" | "area" | "baseline" | "heikin-ashi";
  "scale": "linear" | "logarithmic" | "percentage";
  "timezone": string;
  "indicators": Array<IndicatorInstance>;
  "drawings": Array<Drawing>;
  "show_volume": boolean;
  "follow_live": boolean;
  "link_group": (string | null);
};

export type Contract = {
  "schema_version": 1;
};

export type Contribution = {
  "schema_version": 1;
  "instrument_id": string;
  "quote_currency": string;
  "realized_gross": string;
  "unrealized": (string | null);
  "fees": string;
  "dividends": string;
  "reporting_pnl": (string | null);
};

export type CorporateAction = {
  "schema_version": 1;
  "instrument_id": string;
  "time": number;
  "kind": "split" | "dividend";
  "value": string;
  "source": string;
};

export type Dataset = {
  "schema_version": 1;
  "id": string;
  "hash": string;
  "instrument": Instrument;
  "interval": "1m" | "5m" | "15m" | "30m" | "1h" | "4h" | "1d" | "1w" | "1mo";
  "source": string;
  "feed": string;
  "adjustment": "raw" | "split" | "total-return" | "unknown";
  "created_at": string;
  "first_start": number;
  "last_end": number;
  "row_count": number;
  "limitations": Array<string>;
  "parent_id": (string | null);
};

export type DatasetView = {
  "schema_version": 1;
  "dataset": Dataset;
  "bars": Array<Bar>;
};

export type Drawing = {
  "schema_version": 1;
  "id": string;
  "kind": "trend" | "ray" | "extended" | "horizontal" | "horizontal-ray" | "vertical" | "cross" | "parallel-channel" | "regression-channel" | "pitchfork" | "fib-retracement" | "fib-extension" | "rectangle" | "ellipse" | "triangle" | "brush" | "path" | "arrow" | "text" | "price-range" | "date-range" | "date-price-range" | "long-position" | "short-position";
  "instrument_id": string;
  "anchors": Array<Anchor>;
  "color": string;
  "opacity": number;
  "width": number;
  "label": string;
  "levels": Array<number>;
  "visible": boolean;
  "locked": boolean;
  "quantity": string;
};

export type DrawingMeasurementRequest = {
  "schema_version": 1;
  "instrument": Instrument;
  "drawings": Array<Drawing>;
};

export type DrawingsDocument = {
  "schema_version": 1;
  "workspace_revision": number;
  "drawings": Array<Drawing>;
};

export type EquityPoint = {
  "schema_version": 1;
  "time": number;
  "equity": (string | null);
  "gross_exposure": (string | null);
  "drawdown": (number | null);
  "valuation_errors": Array<string>;
};

export type ExecutionSettings = {
  "schema_version": 1;
  "initial_capital": string;
  "reporting_currency": string;
  "fee_bps": string;
  "fee_per_order": string;
  "slippage_bps": string;
  "allow_short": boolean;
  "allow_fixture_data": boolean;
  "seed": number;
  "start": (number | null);
  "end": (number | null);
  "fx_max_age_seconds": (number | null);
  "corporate_action_coverage": "unknown" | "supplied-complete" | "supplied-partial";
};

export type FXConversion = {
  "schema_version": 1;
  "at": number;
  "from_currency": string;
  "to_currency": string;
  "rate": string;
  "legs": Array<FXLeg>;
  "purpose": string;
};

export type FXLeg = {
  "schema_version": 1;
  "from_currency": string;
  "to_currency": string;
  "rate": string;
  "instrument_id": string;
  "dataset_id": string;
  "dataset_hash": string;
  "source": string;
  "feed": string;
  "available_at": number;
  "age_seconds": number;
  "inverse": boolean;
};

export type Fill = {
  "schema_version": 1;
  "id": string;
  "order_id": string;
  "instrument_id": string;
  "side": "buy" | "sell";
  "quantity": string;
  "price": string;
  "fee": string;
  "quote_currency": string;
  "time": number;
  "bar_start": number;
  "phase": "open" | "touch";
  "dataset_id": string;
  "source": string;
  "feed": string;
  "conversion": FXConversion;
};

export type HistoryRequest = {
  "schema_version": 1;
  "provider": "alpaca" | "coinbase" | "alpha-vantage";
  "instrument": Instrument;
  "interval": "1m" | "5m" | "15m" | "30m" | "1h" | "4h" | "1d" | "1w" | "1mo";
  "start": number;
  "end": number;
};

export type ImportIssue = {
  "schema_version": 1;
  "row": number;
  "message": string;
};

export type ImportPreview = {
  "schema_version": 1;
  "token": string;
  "columns": Array<string>;
  "preview": Array<Bar>;
  "valid_rows": number;
  "invalid_rows": number;
  "exact_duplicates": number;
  "conflicting_duplicates": number;
  "errors": Array<ImportIssue>;
  "warnings": Array<string>;
  "can_commit": boolean;
};

export type ImportRequest = {
  "schema_version": 1;
  "csv_text": string;
  "instrument": Instrument;
  "interval": "1m" | "5m" | "15m" | "30m" | "1h" | "4h" | "1d" | "1w" | "1mo";
  "timezone": (string | null);
  "timestamp_format": (string | null);
  "columns": Record<string, string>;
  "adjustment": "raw" | "split" | "total-return" | "unknown";
  "conflict_policy": "reject" | "first" | "last";
};

export type IndicatorDefinition = {
  "schema_version": 1;
  "id": string;
  "name": string;
  "category": string;
  "contract_version": string;
  "parameters": Record<string, IndicatorParameter>;
  "outputs": Array<IndicatorOutput>;
  "formula": string;
  "warmup": string;
  "edge_cases": string;
  "notes": Array<string>;
  "source_urls": Array<string>;
  "volume_required": boolean;
};

export type IndicatorInstance = {
  "schema_version": 1;
  "id": string;
  "definition_id": string;
  "parameters": Record<string, (number | string | boolean)>;
  "visible": boolean;
  "color": string;
  "width": number;
  "pane": number;
};

export type IndicatorOutput = {
  "schema_version": 1;
  "id": string;
  "pane": string;
  "units": string;
  "plot_offset_bars": number;
};

export type IndicatorParameter = {
  "schema_version": 1;
  "default": (number | string | boolean | null);
  "kind": "integer" | "number" | "choice" | "boolean" | "timestamp" | "fixed";
  "minimum": (number | null);
  "maximum": (number | null);
  "choices": Array<string>;
};

export type IndicatorRequest = {
  "schema_version": 1;
  "dataset_id": string;
  "instances": Array<IndicatorInstance>;
  "cutoff": (number | null);
};

export type IndicatorResponse = {
  "schema_version": 1;
  "dataset_id": string;
  "contract_version": string;
  "times": Array<number>;
  "available_at": Array<number>;
  "results": Array<IndicatorResult>;
};

export type IndicatorResult = {
  "schema_version": 1;
  "instance_id": string;
  "definition_id": string;
  "status": "ready" | "disabled" | "error";
  "message": string;
  "lines": Array<IndicatorValues>;
};

export type IndicatorValues = {
  "schema_version": 1;
  "output_id": string;
  "values": Array<(number | null)>;
  "plot_offset_bars": number;
  "plot_times": Array<(number | null)>;
};

export type Instrument = {
  "schema_version": 1;
  "id": string;
  "symbol": string;
  "name": string;
  "exchange": string;
  "asset_class": "stock" | "etf" | "equity" | "crypto" | "forex" | "other";
  "base_currency": (string | null);
  "quote_currency": string;
  "timezone": string;
  "calendar": string;
  "session": "regular" | "provider-day" | "continuous";
  "price_tick": string;
  "quantity_step": string;
  "provider_symbols": Record<string, string>;
};

export type Metric = {
  "schema_version": 1;
  "value": (number | null);
  "unit": string;
  "convention": string;
  "undefined_reason": (string | null);
};

export type OrderRequest = {
  "schema_version": 1;
  "instrument_id": string;
  "side": "buy" | "sell";
  "quantity": string;
  "kind": "market" | "limit" | "stop" | "bracket";
  "entry_kind": "market" | "limit" | "stop";
  "limit_price": (string | null);
  "stop_price": (string | null);
  "take_profit": (string | null);
  "stop_loss": (string | null);
  "tag": string;
};

export type PaperAccount = {
  "schema_version": 1;
  "paused": boolean;
  "id": string;
  "name": string;
  "mode": "replay" | "paper";
  "revision": number;
  "dataset_ids": Array<string>;
  "settings": ExecutionSettings;
  "actions": Array<CorporateAction>;
  "commands": Array<AccountCommand>;
  "cursor": number;
  "created_at": string;
  "error": (string | null);
};

export type Portfolio = {
  "schema_version": 1;
  "time": number;
  "reporting_currency": string;
  "cash": Record<string, string>;
  "restricted_cash": Record<string, string>;
  "positions": Array<Position>;
  "equity": (string | null);
  "gross_exposure": (string | null);
  "valuation_errors": Array<string>;
  "conversions": Array<FXConversion>;
  "insolvent": boolean;
};

export type Position = {
  "schema_version": 1;
  "instrument_id": string;
  "quote_currency": string;
  "quantity": string;
  "average_price": string;
  "realized_gross": string;
  "fees": string;
  "dividends": string;
  "short_collateral": string;
  "short_proceeds": string;
  "last_price": (string | null);
  "last_price_time": (number | null);
  "unrealized": (string | null);
  "market_value": (string | null);
};

export type ProviderCapabilities = {
  "schema_version": 1;
  "id": string;
  "name": string;
  "markets": Array<string>;
  "intervals": Array<"1m" | "5m" | "15m" | "30m" | "1h" | "4h" | "1d" | "1w" | "1mo">;
  "streaming": boolean;
  "requires_keys": boolean;
  "history": string;
  "limitations": Array<string>;
  "status": "not-configured" | "available" | "connected" | "disconnected" | "throttled";
};

export type ProviderConfig = {
  "schema_version": 1;
  "api_key": string;
  "secret_key": (string | null);
};

export type Quote = {
  "schema_version": 1;
  "instrument_id": string;
  "price": number;
  "timestamp": number;
  "source": string;
  "feed": string;
  "freshness": "live" | "delayed" | "historical" | "imported" | "stale" | "unavailable";
};

export type ResearchJob = {
  "schema_version": 1;
  "id": string;
  "name": string;
  "revision": number;
  "status": "queued" | "running" | "completed" | "failed" | "cancelled" | "interrupted";
  "created_at": string;
  "started_at": (string | null);
  "finished_at": (string | null);
  "snapshot_hash": string;
  "result_hash": (string | null);
  "progress": number;
  "completed_events": number;
  "total_events": number;
  "elapsed_seconds": number;
  "peak_memory_bytes": number;
  "error": (string | null);
  "limits": WorkerLimits;
};

export type ResearchRequest = {
  "schema_version": 1;
  "name": string;
  "script": StrategyDefinition;
  "dataset_ids": Array<string>;
  "parameters": Record<string, (number | string | boolean)>;
  "settings": ExecutionSettings;
  "actions": Array<CorporateAction>;
  "limits": WorkerLimits;
};

export type ResearchResult = {
  "schema_version": 1;
  "engine_version": string;
  "settings": ExecutionSettings;
  "final_portfolio": Portfolio;
  "orders": Array<SimulationOrder>;
  "fills": Array<Fill>;
  "trades": Array<Trade>;
  "equity": Array<EquityPoint>;
  "metrics": Record<string, Metric>;
  "contributions": Array<Contribution>;
  "currency_translation": (string | null);
  "conversions": Array<FXConversion>;
  "corporate_actions": Array<Record<string, unknown>>;
  "logs": Array<Record<string, unknown>>;
  "plots": Array<Record<string, unknown>>;
  "limitations": Array<string>;
};

export type ScriptAnalysis = {
  "schema_version": 1;
  "valid": boolean;
  "script_hash": string;
  "diagnostics": Array<ScriptDiagnostic>;
  "parameters": Record<string, ScriptParameter>;
  "hooks": Array<string>;
};

export type ScriptDiagnostic = {
  "schema_version": 1;
  "line": number;
  "column": number;
  "severity": "error" | "warning";
  "message": string;
};

export type ScriptParameter = {
  "schema_version": 1;
  "type": "int" | "float" | "bool" | "str";
  "default": (number | string | boolean);
  "minimum": (number | null);
  "maximum": (number | null);
  "choices": Array<(number | string | boolean)>;
  "description": string;
};

export type SimulationOrder = {
  "schema_version": 1;
  "id": string;
  "sequence": number;
  "request": OrderRequest;
  "submitted_at": number;
  "eligible_from": number;
  "status": "pending" | "filled" | "cancelled" | "rejected";
  "reason": (string | null);
  "parent_id": (string | null);
  "sibling_id": (string | null);
  "activated_bar_start": (number | null);
  "activation_phase": ("open" | "touch" | null);
  "completed_at": (number | null);
};

export type StrategyDefinition = {
  "schema_version": 1;
  "id": string;
  "name": string;
  "source": string;
  "kind": "strategy" | "indicator";
  "revision": number;
  "parameters": Record<string, (number | string | boolean)>;
  "subscriptions": Array<string>;
};

export type Trade = {
  "schema_version": 1;
  "id": string;
  "instrument_id": string;
  "time": number;
  "direction": "long" | "short";
  "quantity": string;
  "entry_price": string;
  "exit_price": string;
  "gross_pnl": string;
  "allocated_fees": string;
  "net_pnl": string;
  "quote_currency": string;
  "reporting_pnl": string;
  "conversion": FXConversion;
};

export type Watchlist = {
  "schema_version": 1;
  "id": string;
  "name": string;
  "items": Array<WatchlistItem>;
  "sections": Array<string>;
  "sort": "manual" | "symbol" | "last" | "change" | "changePercent";
};

export type WatchlistItem = {
  "schema_version": 1;
  "instrument_id": string;
  "section": string;
};

export type WatchlistsDocument = {
  "schema_version": 1;
  "workspace_revision": number;
  "watchlists": Array<Watchlist>;
  "active_watchlist": string;
};

export type WorkerLimits = {
  "schema_version": 1;
  "deadline_seconds": number;
  "memory_mb": number;
};

export type Workspace = {
  "schema_version": 1;
  "id": string;
  "name": string;
  "revision": number;
  "theme": "dark" | "light";
  "layout": 1 | 2 | 4;
  "charts": Array<ChartState>;
  "active_chart": number;
  "watchlists": Array<Watchlist>;
  "active_watchlist": string;
  "sidebar_width": number;
  "bottom_height": number;
  "sidebar_open": boolean;
  "bottom_open": boolean;
  "link_symbol": boolean;
  "link_interval": boolean;
  "link_crosshair": boolean;
  "link_range": boolean;
  "indicator_templates": Record<string, Array<IndicatorInstance>>;
};
