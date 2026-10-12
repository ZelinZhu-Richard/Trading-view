# Market Workbench — Complete Product and Build Goal

## 1. Product goal, scope, and working boundaries

### Product goal

Build **Market Workbench**, a personal browser application that runs locally and combines:

- Financial charting using TradingView Lightweight Charts.
- Persistent watchlists, chart layouts, indicators, and drawings.
- Separate market-data connections for US stocks, ETFs, crypto, and forex.
- CSV imports for China-market data and unsupported markets or intervals.
- Historical replay and local paper trading.
- Python authoring for custom indicators and strategies.
- Portfolio backtesting across multiple instruments, currencies, and trading calendars.

Deliver a working application with verified behavior. A visual prototype, populated menu, mocked integration, or initial milestone does not satisfy the whole goal.

TradingView is a reference for selected workflows and interactions. The scope is the explicit capability catalog below, rather than an unrestricted promise to reproduce every TradingView feature.

### Intended user and operation

The first release serves one person using a browser on their own computer.

- Support local operation on macOS and Windows.
- Target current Chrome. Further Edge verification is waived by the user (2026-10-12 UTC).
- Use a familiar professional layout, original branding, and dark/light themes.
- Require no hosted account, external application server, or cloud storage.
- Allow free provider accounts and locally configured API keys.
- Continue supporting imported and cached datasets when providers are unavailable.
- Make data coverage, delays, limitations, and calculation assumptions visible.

Desktop packaging, mobile applications, hosted collaboration, and multiple-user authentication are outside this goal.

### Explicit exclusions

Do not include:

- Real-money trading or brokerage order submission.
- Automatic paid subscriptions or purchases.
- Pine Script execution or compatibility claims.
- Social publishing, public script marketplaces, or community features.
- Options, futures, exchange order-book simulation, or tick-accurate execution.
- Automatic deployment or publication; commits and pushes require an explicit user request.

Mainland China support through validated CSV imports is required. An automatic China-market provider is optional and must not delay completion of the agreed scope.

### Workspace boundaries

The working repository is `workspace/trading-view/` inside `/Users/richardzhu/dev/REA`.

- Save this specification in `workspace/trading-view/goal.md`.
- Build the application inside `workspace/trading-view/`.
- Keep datasets, evidence, reports, browser profiles, local environments, and generated application artifacts inside the working area.
- Preserve unrelated REA source and existing user changes.
- Follow applicable `AGENTS.md` instructions.
- Never read `holdout/` casually or use it for development.
- Any deliberate custodian evaluation of holdout must be announced before reading.
- Worker agents must never list, inspect, copy, or reference holdout.

The application's replay cutoff and the project's protected holdout are separate boundaries. Both must be respected.

## 2. Architecture, interfaces, data, and reference investigation

### Application architecture

Use these components:

| Component | Choice | Responsibility |
|---|---|---|
| Browser application | React, TypeScript, Vite | Workspace, controls, state presentation |
| Chart renderer | Lightweight Charts | Price series, panes, scales, chart primitives |
| Local backend | Python and FastAPI | Providers, persistence, calculations, research jobs |
| Numerical libraries | NumPy and pandas | Numerical operations and tabular processing |
| Script editor | Monaco Editor | Python authoring, diagnostics, parameters, logs |
| Metadata storage | SQLite | Workspaces, watchlists, drawings, scripts, simulation state |
| Market-data storage | Parquet | Normalized caches and immutable research snapshots |
| Communication | HTTP and WebSockets | Requests, quotes, progress, calculation results |

Use project-local dependency environments and lockfiles. Follow the parent repository's pinned Node/npm toolchain where applicable. Pin a supported Python runtime for the application without replacing the user's system Python.

During development, provide one documented command that starts the frontend and backend. For normal local use, build the frontend and serve it from the Python service.

Bind services to loopback. Validate browser origins and WebSocket connections, and avoid enabling unrestricted cross-origin access.

### Ownership and separation

Keep these responsibilities separate:

- **Provider adapters:** translate external API responses and capabilities.
- **Normalization layer:** owns timestamps, identifiers, sessions, units, and data validation.
- **Dataset store:** owns caching, snapshots, provenance, and data revisions.
- **Calculation engine:** owns indicator values.
- **Simulation engine:** owns orders, fills, cash, positions, and portfolio valuation.
- **Browser UI:** presents state and submits commands.
- **Research workers:** run scripts and calculations without blocking the application.

The chart must never become the authoritative source for financial calculations. Previewed values, simulated fills, and exported results must originate from the same backend definitions.

### Public contracts

Define versioned models for:

- `Instrument`: stable identity, provider mappings, exchange, asset class, base/quote currency, timezone, session, price tick, and quantity precision.
- `Bar`: interval start/end, OHLC, nullable volume, completion status, provenance, and adjustment basis.
- `Quote`: price, timestamp, source, and freshness.
- `ProviderCapabilities`: searchable markets, intervals, history coverage, streaming support, and limits.
- `IndicatorDefinition`: identity, parameters, required inputs, outputs, warm-up behavior, and plotting metadata.
- `Drawing`: type, instrument scope, anchors, appearance, visibility, and lock state.
- `Workspace`: chart layouts, linked groups, indicators, drawings, and panel arrangement.
- `StrategyDefinition`: Python source, parameters, subscriptions, and version.
- `SimulationOrder`, `Fill`, `Position`, `Portfolio`, and `ResearchResult`.

Use backend models to generate or validate frontend API types. Avoid independently maintained, inconsistent schemas.

Provide endpoint groups for provider status, instruments, history, imports, workspaces, watchlists, drawings, indicators, scripts, research jobs, and paper accounts. WebSocket events must identify their subscription or job and support clean unsubscribe behavior.

### Persistence and recovery

Persist user work automatically with debounced saves and explicit save status.

- Version saved documents and database migrations.
- Preserve existing data during migration failures.
- Support workspace export/import without credentials.
- Save scripts independently from their execution results.
- Preserve completed research runs after restart.
- Mark interrupted jobs as interrupted; do not silently restart them.
- Preserve paper-account state and alert history.
- Use atomic writes for exported documents and research artifacts.

### Data-provider baseline

| Market | Required implementation |
|---|---|
| US stocks and ETFs | Alpaca Basic, including symbol metadata, history, and available streaming data |
| Crypto | Coinbase public market-data endpoints, supported products, history, and available streaming updates |
| Forex | Alpha Vantage daily bars, with locally derived weekly/monthly intervals |
| China and unsupported intervals | CSV import with explicit instrument and market metadata |

Alpaca Basic provides limited real-time equity coverage through IEX. Alpha Vantage's documented intraday forex endpoint is premium, so it is outside the required free baseline. [Alpaca coverage](https://docs.alpaca.markets/docs/about-market-data-api), [Alpha Vantage documentation](https://www.alphavantage.co/documentation/)

Use documented provider endpoints. Do not use TradingView's observed internal connections as the application's data backend.

Provider adapters must:

- Expose capabilities and limitations.
- Handle authentication errors, throttling, unavailable symbols, pagination, and connection loss.
- Cache useful results and avoid duplicate subscriptions.
- Cancel obsolete requests after symbol or interval changes.
- Apply bounded retries with backoff.
- Preserve data source and feed identity.
- Never silently substitute a different feed.

Store keys only in backend configuration excluded from version control. Do not expose them in browser responses, logs, screenshots, exports, or research-worker environments.

### Normalization and import rules

Use UTC internally while retaining exchange timezone and session metadata. Distinguish a bar's opening time from when its final values become available.

Support these intervals when source data permits: 1 minute, 5 minutes, 15 minutes, 30 minutes, 1 hour, 4 hours, daily, weekly, and monthly.

- Never derive intraday history from daily bars.
- Aggregate only from sufficiently detailed source data.
- Respect market calendars, daylight-saving changes, holidays, and lunch breaks.
- Do not invent candles for closed sessions.
- Distinguish missing volume from zero volume.
- Preserve raw versus adjusted price metadata.
- Never merge differently adjusted or differently sourced history without an explicit dataset transformation.

CSV import must include:

- Column mapping and a preview.
- Timestamp format and timezone selection.
- Instrument, market, currency, and interval metadata.
- OHLC validation and nonnegative volume validation.
- Row-level error reporting.
- Exact-duplicate detection and explicit handling of conflicting duplicates.
- A summary before committing the imported dataset.

Ambiguous timestamps must require a timezone choice. Missing data must remain identifiable.

### Data presentation

Every chart and research run must expose:

- Provider and feed.
- Live, delayed, historical, imported, or stale status.
- Last successful update.
- Available history and interval.
- Currency and exchange timezone.
- Price-adjustment basis.
- Relevant data-quality limitations.

A disconnected provider must leave useful cached data visible with a clear stale state.

### REA investigation

Use REA to investigate bounded reference behaviors in an inspectable TradingView browser session.

Required investigation subjects:

1. Symbol selection, interval changes, zoom, and crosshair interaction.
2. Indicator addition, settings, visibility, and pane placement.
3. Drawing creation, anchor editing, selection, styling, and deletion.
4. Watchlist organization and chart selection.
5. Panel resizing and chart-layout behavior.
6. Replay and strategy-result workflows where accessible.

Use existing suitable browser access or a dedicated profile stored inside the working area. Native decompilation is not required.

For each investigation, record:

- The question being answered.
- Reference URL, access conditions, and observation date.
- REA Evidence IDs.
- Reproduction steps.
- Observed behavior.
- Inferences and unresolved limitations.
- The corresponding application behavior and verification case.

Use official documentation when reference behavior is inaccessible, but label documentation-derived decisions separately. An unavailable reference must not block unrelated development or become an unsupported parity claim.

Retain the attribution required by [Lightweight Charts](https://tradingview.github.io/lightweight-charts/docs).

## 3. Required product capabilities

### Chart workspace

Provide one-chart, two-chart, and four-chart layouts.

Each chart supports:

- Candlestick, OHLC bar, line, area, baseline, and Heikin-Ashi views.
- Linear, logarithmic, and percentage price scales.
- Volume and indicator panes.
- Crosshair details and OHLC readouts.
- Symbol search and interval selection.
- Zoom, pan, reset, and fit-to-data.
- Timezone selection and session information.
- Chart-image export.

Allow selective linking of symbol, interval, crosshair, and visible time range. Linking must not create recursive update loops.

Use the selected layout:

- Drawing toolbar on the left.
- Charts in the center.
- Watchlists and instrument details on the right.
- Python editor, replay controls, orders, and research results below.

Panels must resize and collapse without corrupting chart dimensions. Preserve layouts across restarts.

Provide dark/light themes, visible keyboard focus, labeled controls, readable numeric typography, and an accessible tabular view of chart values. Do not rely solely on red/green to communicate state.

### Watchlists

Support:

- Multiple named lists.
- Sections and manual ordering.
- Instrument search and addition.
- Removal, duplication, and reordering.
- Sorting by available quote fields.
- CSV import/export.
- Selection that updates the active chart.
- Instrument identity including venue and currency.
- Explicit stale or unavailable quotes.

Virtualize long lists and subscribe only to data needed for visible or active instruments, within provider limits.

### Indicator catalog

Every listed indicator is required.

| Category | Indicators |
|---|---|
| Moving averages | SMA, EMA, WMA, VWMA, DEMA, TEMA, HMA, KAMA, ALMA |
| Overlays | Bollinger Bands, Keltner Channels, Donchian Channels, Ichimoku, Supertrend, Parabolic SAR, standard pivot points |
| Momentum | RSI, Stochastic, Stochastic RSI, MACD, CCI, ROC, Momentum, Williams %R, TRIX, Ultimate Oscillator, Awesome Oscillator |
| Volatility and strength | ATR, ADX/DMI, Aroon, rolling standard deviation, historical volatility, Choppiness Index |
| Volume | Volume, volume moving average, OBV, MFI, Chaikin Money Flow, Accumulation/Distribution, Chaikin Oscillator, session VWAP, anchored VWAP |

Each indicator needs:

- Documented formula and numerical conventions.
- Validated parameter controls.
- Defaults recorded in a machine-readable registry.
- Defined warm-up, missing-value, and zero-denominator behavior.
- Appropriate overlay or separate-pane rendering.
- Styling, visibility, removal, and template persistence.
- Automated numerical reference tests.

Specify smoothing conventions explicitly, particularly Wilder versus EMA smoothing. Record standard-deviation conventions and session resets.

Use shared Python calculations across live charts, replay, and backtests. Disable volume-dependent indicators when meaningful volume is absent.

Projected plotting positions must not make future data available to a strategy. Document indicators whose historical appearance can change.

### Drawing catalog

Implement all of the following:

- Trend line, ray, extended line.
- Horizontal line, horizontal ray, vertical line, cross line.
- Parallel channel, regression channel, pitchfork.
- Fibonacci retracement and extension.
- Rectangle, ellipse, triangle.
- Brush, path, arrow, text.
- Price range, date range, combined date/price measurement.
- Long-position and short-position risk/reward drawings.

Shared behaviors:

- Select and edit anchors.
- Move the whole object.
- Snap to relevant chart values.
- Configure color, opacity, width, labels, and applicable levels.
- Lock, hide, duplicate, and delete.
- Manage objects through a list.
- Undo and redo complete editing actions.
- Persist and restore drawings.

Store anchors in time/price coordinates, not screen pixels. Preserve placement during zoom, resizing, and interval changes.

Use supported [Lightweight Charts primitives and plugins](https://tradingview.github.io/lightweight-charts/docs/plugins/intro). Financial calculations for risk/reward drawings must use the same currency and precision conventions as the simulation engine.

### Alerts

Support:

- Price above/below and crossing conditions.
- Indicator threshold and crossing conditions.
- Once-only and recurring alerts.
- User-selected evaluation on completed bars.
- In-app notifications and a persistent event history.
- Pausing, editing, and deletion.

Evaluate alerts while the local service is running. Display stopped, disconnected, and stale-data states. Prevent duplicate triggers after reconnection or restart.

External email, SMS, and messaging integrations are outside this goal.

### Python editor and SDK

Provide:

- Script creation, editing, saving, duplication, and version history.
- Parameter forms generated from script declarations.
- Syntax diagnostics, runtime tracebacks, logs, and output previews.
- Explicit Run and Cancel controls.
- Example indicators and portfolio strategies.
- Export/import of source files without automatic execution.

Define two documented extension interfaces:

- **Indicators:** calculate declared outputs from available historical inputs and parameters.
- **Strategies:** initialize state, receive batches of newly completed bars, inspect portfolio state, submit/cancel simulated orders, and finalize results.

The strategy context exposes:

- Simulation time.
- Instrument metadata.
- Historical values available at that time.
- Current cash, positions, pending orders, and fills.
- Deterministic random-number generation.
- Plot and log output.
- Order submission and cancellation.

Do not expose future bars through the SDK. Strategy examples must use the SDK clock and seeded randomness rather than wall-clock time.

Run trusted scripts in separate cancellable processes. Remove provider credentials from their environment. Bound worker concurrency and provide configurable job deadlines and memory monitoring.

Process separation is for responsiveness and fault containment; it must not be described as a secure sandbox for hostile Python code. Do not automatically execute downloaded scripts or install arbitrary script dependencies.

Include examples for:

- A custom indicator.
- Moving-average crossover.
- Multi-asset periodic rebalancing.
- A portfolio containing instruments with different quote currencies.

### Historical replay

Provide:

- Date/time selection for a replay starting point.
- Single-bar stepping.
- Play, pause, and speed controls.
- Synchronized progression across chart layouts.
- Replay-only paper accounts.
- A clear visual distinction between replay and current-market mode.

Hide future candles from charts and future-derived values from indicators and scripts.

Changing replay position resets dependent simulation state or restores a valid checkpoint. It must not retain positions or indicator state from a later point.

### Shared simulation engine

Use the same order, fill, accounting, and valuation rules for replay, paper trading, and backtesting.

Required order types:

- Market.
- Limit.
- Stop.
- Bracket orders with linked take-profit and stop-loss exits.

Required accounting:

- Multiple instruments sharing capital.
- Multiple quote currencies and a configurable reporting currency.
- USD as the default reporting currency.
- Long and short simulation.
- No leverage by default.
- Configurable fees and slippage.
- Explicit shorting and collateral assumptions.
- Cash, positions, realized/unrealized profit and loss, and equity.

Use decimal arithmetic or fixed precision for monetary bookkeeping. Indicator calculations may use floating-point arithmetic with documented tolerances.

### Execution rules

Make the default execution model explicit:

- Strategies act on completed bars.
- New orders become eligible on the next tradable bar.
- Market orders use that bar's opening price plus configured costs.
- Limit and stop orders use documented gap and touch rules.
- Orders cannot fill on unavailable or synthetic candles.
- Simultaneous orders use a stable, recorded ordering.
- Insufficient-capital orders are rejected with a reason.
- Where both bracket exits can be reached within one bar and finer evidence is absent, use conservative stop-first resolution.
- Do not claim tick-level execution accuracy.
- Use underlying market OHLC for fills even when the display uses Heikin-Ashi.

Fees, slippage, and other cost assumptions must be explicit parameters. Default zero-cost settings must be labeled as such, not presented as estimates of actual trading costs.

### Portfolio timing and currency conversion

Align events using exchange-aware bar availability.

- Closed markets retain their last known valuation without generating fictitious fills.
- Strategies receive only data available at each event time.
- Currency conversion uses rates available at or before that event.
- Never use a later conversion rate to value an earlier event.
- Record conversion paths, source, timestamp, and age.
- Missing required conversion data blocks the affected operation or result rather than silently assuming parity.

Support supplied split and dividend events. Avoid double counting when bars are already adjusted. Identify unknown corporate-action coverage in results.

### Backtesting and results

Allow selection of:

- Strategy and parameters.
- Instrument universe.
- Dataset and date range.
- Intervals.
- Initial capital and reporting currency.
- Fees, slippage, and execution settings.

Snapshot the exact inputs before execution. Record:

- Dataset hashes.
- Script hash.
- Engine and dependency versions.
- Parameters and execution assumptions.
- Data provenance and limitations.
- Run start/end, completion state, and errors.

Display:

- Portfolio equity and drawdown.
- Positions and exposure.
- Orders, fills, and trade history.
- Contributions by instrument.
- Comparable summaries across saved runs.

Calculate total return, annualized return where meaningful, volatility, Sharpe ratio with stated assumptions, maximum drawdown, turnover, exposure, win rate, and profit factor.

Show undefined metrics explicitly. Do not replace them with misleading zeros.

Export results and supporting tables in documented JSON/CSV formats.

## 4. Delivery stages, verification, and completion

### Stage 1 — Foundation and evidence

Deliver:

- Isolated application structure.
- Reproducible dependency setup.
- Local startup and health checks.
- Core contracts and persistence schema.
- REA investigation checklist and evidence ledger.
- Deterministic synthetic fixtures and an imported-data example.

Exit condition: the browser connects to the backend, loads a chart from a validated dataset, saves a workspace, and restores it after restart.

### Stage 2 — Data and workspaces

Deliver:

- All required provider adapters.
- CSV import and normalization.
- Data caching and provenance.
- Watchlists.
- Chart types, layouts, linking, and persistence.
- Visible provider and freshness states.

Exit condition: users can connect or import data, select instruments, switch supported intervals, organize watchlists, and recover their workspace after restart.

### Stage 3 — Analysis tools

Deliver:

- The complete indicator catalog.
- The complete drawing catalog.
- Templates and object management.
- Undo/redo.
- Alerts.
- Themes and keyboard-accessible workflows.

Exit condition: every listed tool has working UI behavior, persistence where applicable, and relevant verification. Menu entries without functioning implementations do not count.

### Stage 4 — Python and simulation

Deliver:

- Python editor and SDK.
- Research-worker management.
- Shared simulation engine.
- Historical replay.
- Paper accounts.
- Portfolio backtests.
- Reports and exports.

Exit condition: a supplied multi-instrument strategy completes a reproducible backtest, can be exercised in replay, and uses the same accounting rules in paper mode.

### Stage 5 — Integration and acceptance

Deliver:

- Recovery and failure handling.
- Performance measurements.
- Browser interaction verification.
- Setup and usage documentation.
- Provider coverage notes.
- Example scripts and datasets.
- A final requirement-by-requirement acceptance report.

This stage is part of the product work, not an optional cleanup phase.

### Verification matrix

**Indicators**

- Independently computed expected values.
- Warm-up boundaries.
- Constant and short datasets.
- Missing bars and volume.
- Zero denominators.
- Parameter changes.
- Consistency between chart, replay, and backtest calculations.

**Drawings**

- Anchor placement and editing.
- Hit testing and selection.
- Zoom, resizing, and interval changes.
- Lock/hide/duplicate/delete.
- Undo/redo.
- Save/reload.
- Correct risk/reward measurements.

**Providers and imports**

- Invalid or absent keys.
- Throttling and exhausted quotas.
- Disconnection and reconnection.
- Pagination and cancellations.
- Duplicate and out-of-order records.
- DST boundaries, closed sessions, and session breaks.
- Invalid CSV rows and ambiguous timestamps.
- No silent feed or adjustment-basis substitution.

**Simulation**

- Shared-capital competition.
- Long and short accounting.
- Fees, slippage, and insufficient funds.
- Gap-through stops and limits.
- Conflicting bracket exits.
- Multi-currency valuation.
- Missing conversion data.
- Splits and dividends.
- Weekends and mixed market calendars.
- Cancellation and interrupted jobs.

**No-lookahead and reproducibility**

- Modify future input data and prove that earlier signals and fills remain unchanged.
- Verify that incomplete bars are unavailable to completed-bar strategies.
- Verify that conversion rates are selected causally.
- Run identical snapshots, scripts, and settings twice and compare results.
- Confirm that replay cannot retain state from a future position.

**Browser and recovery**

- Complete the primary workflow in current Chrome. Further Edge checks are waived by the user (2026-10-12 UTC).
- Inspect 1280×800 and 1920×1080 layouts.
- Verify dark/light themes, keyboard access, and visible focus.
- Restart with saved workspaces, drawings, scripts, paper positions, and finished runs.
- Verify useful errors instead of blank panels or corrupted state.

### Performance verification

Measure and report:

- Four charts, each with 10,000 bars and five indicators.
- A 20-instrument daily portfolio backtest spanning approximately ten years.
- Repeated symbol/interval changes.
- Provider reconnects.
- Large watchlists.
- Job cancellation during calculation.

Record hardware, dataset size, timings, and memory use. Charts must remain interactive while research jobs run. Cancellation should acknowledge promptly and terminate owned worker processes without leaving orphan jobs.

Do not invent benchmark results or claim operating-system coverage that was not exercised.

### Completion criteria

The goal is complete only when:

1. All mandatory capabilities listed here work.
2. A user can connect or import data, analyze charts, save drawings, author Python, replay history, run a portfolio backtest, and export results.
3. Required numerical, integration, simulation, and browser checks have recorded outcomes.
4. Real-provider checks are distinguished from fixture-based tests.
5. Documentation explains setup, provider limits, simulation assumptions, and recovery behavior.
6. The acceptance report maps every requirement to implementation and verification evidence.

External blockers such as missing credentials must be reported precisely while independent work continues. They must not be hidden by mocked data or silently removed requirements.

Keep this specification stable during implementation. Track progress separately, and record any user-approved scope changes explicitly.
