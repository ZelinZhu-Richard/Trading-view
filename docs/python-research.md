# Python research: execution and reproducibility

Open **Python editor** in the bottom panel. New/import/edit/save/version/export do
not run code. **Run settings → Run** snapshots the current editor source (including
an unsaved draft), parameter values, selected datasets, dates, cost assumptions and
worker limits. Select one source/interval per instrument. Select FX datasets as
well as foreign-currency assets; missing conversion paths cause explicit rejection
or unavailable valuation, never an assumed rate of one.

Saved runs appear in **Research results**. Inspect equity/drawdown, metric
conventions, orders, fills, average-cost closing trades, positions, contributions,
plots, logs and input provenance. Up to four completed runs can be compared with
currencies, costs, dates and input hashes visible. Export the complete result JSON
or orders/fills/trades/equity/positions/contributions as CSV. Nested CSV fields use
JSON cells. CSV files use UTF-8 text, comma delimiters, standard quoted cells and
CRLF record endings. Column names and order follow the corresponding versioned
result model in `contracts.schema.json`; empty tables still contain the header.
Null scalars are empty CSV cells (JSON retains null). Orders keep order inputs in
their nested `request` JSON cell. Decimal money values remain decimal strings in JSON and CSV. Table
pagination limits rendered rows without discarding export records.

## Extension interfaces

A strategy defines `on_bars(ctx, bars)` and optionally `initialize(ctx)` and
`finalize(ctx)`. `bars` maps instrument IDs to newly completed immutable bars.
The callback runs once for each shared availability time and receives only its
subscriptions. Empty subscriptions mean the selected universe. A custom indicator
defines `calculate(ctx)` returning a dictionary of named finite scalars or `None`;
it runs at each subscribed completion time and records those outputs as plots.

Declare controls with a literal module-level dictionary, for example:

```python
PARAMETERS = {"length": {"type": "int", "default": 20, "minimum": 1, "maximum": 500}}
```

Types are int/float/bool/str, with optional minimum, maximum, choices and description.
Source diagnostics read the AST without executing imports. Syntax success does not
prove runtime correctness; runtime errors retain their Python traceback.

Context members:

- `ctx.clock`: UTC datetime; `ctx.timestamp`: UTC seconds. Use these instead of wall time.
- `ctx.parameters`, `ctx.subscriptions`, `ctx.instruments`: validated parameters,
  subscribed identities, and copied instrument metadata.
- `ctx.history(id, count=None)`: immutable completed bars available now.
- `ctx.indicator(id, definition_id, parameters=None, count=None)`: named tuples of
  shared built-in values at their source indices. Warm-up/undefined values are None.
  Ichimoku display offsets never advance availability. The prefix-causal built-ins
  cache full immutable input calculations internally, exposing only completed values.
- `ctx.portfolio`, `ctx.orders`, `ctx.fills`: copies; modifying them cannot change
  engine accounting. Positions use signed Decimal quantities and average cost.
- `ctx.order(id, side, quantity, kind='market', ...)`: simulated order. Limit/stop
  orders require limit_price/stop_price. Brackets use kind='bracket', optional
  entry_kind and its entry price, plus stop_loss and take_profit. Return value has id.
- `ctx.cancel(order_id)`: cancel a pending order.
- `ctx.random`: seeded generator; `ctx.state`: per-run user state.
- `ctx.log(*values)`, `ctx.plot(name, value, instrument_id=None)`: bounded outputs.

The examples directory contains a custom average, EMA crossover, monthly equal
weight rebalance, and a portfolio using different quote currencies. Import an
example explicitly; none executes on application startup. Examples are execution
illustrations and are not claims of profitable strategies.

## Execution assumptions

The shared engine processes ending-bar touches, publishes completions, calls the
strategy, applies supplied actions, processes opening prices, then records equity.
New orders from a completion can participate in the next bar opening at that same
time boundary. Orders submitted after an opening was already processed wait for a
later bar. Overnight closures keep known marks; no fictional bars/fills are added.

Markets fill at eligible opens. Buy limits receive favorable gap opens at or below
the limit, otherwise a low touching the limit fills there; sell limits are symmetric.
Stops fill at adverse gap opens or their threshold. Slippage is adverse, and limit
fills remain inside the limit. Price rounding uses the shared nearest-tick/half-up
routine; quantities round toward zero to the instrument step.

Whole orders fill or reject without a liquidity model. Competing orders retain
submission order. Bracket entries require a flat instrument position; linked stop
exits win ambiguous bars, and cancel their targets. After an intrabar touched entry,
favorable same-bar exits wait one bar; adverse protection may execute. Other manual
position changes cancel protective children to prevent stale quantities. Intrabar
fills use bar-opening FX and are reported at bar completion; this is not tick timing.

Longs consume full notional. Shorts reserve 100% initial notional and restrict sale
proceeds separately. Partial covers release proportional collateral. No borrow or
availability model is implied. Adverse gaps can make cash/equity negative; closes
can realize the deficit, while new exposure is rejected. Fees and slippage are
explicit inputs. Zero defaults are labeled assumptions, not cost estimates.

Conversion paths use completed base/quote currency datasets at or before the event,
with deterministic shortest-path/lexical selection. Each conversion records source,
feed, dataset hash, direction, timestamp and age. An optional age limit excludes
stale rates. Foreign sale proceeds remain in their currency. Final contributions
translate local instrument P/L at final causal FX; the currency-translation residual
reconciles those contributions to total portfolio profit, including foreign cash
and historical conversion effects.

Raw splits adjust position/order quantities and inverse prices before effective
opens. Fractional entitlements remain exact; no cash-in-lieu is invented. Supplied
dividends credit longs/debit shorts at the supplied cash-effective timestamp.
Already-adjusted prices skip corresponding actions. Unknown adjustment blocks
supplied action application; corporate-action coverage remains explicit.

Metrics are defined in result metadata. Returns use initial/final equity; annualized
return requires 30 days and positive terminal equity. Risk statistics use UTC daily
returns, calendar-day carry-forward, sample deviation, 365.25 days/year, and zero
risk-free return. Undefined values carry a reason. Closing trade metrics use
average-cost matching and proportionally allocated entry/exit fees.

## Workers and retained files

Up to two workers run concurrently, with a queue bounded at 20 submissions/runs.
Each job has a 1–3600 second deadline and a 128–8192 MB memory setting. Memory limits
are monitored at 250 ms intervals, not a hard allocation sandbox. No provider keys
are inherited; the worker environment is an explicit small allowlist. Trusted
Python can access local files and create processes; this is not a hostile-code
security boundary and dependencies are never automatically installed.

`data/runs/<uuid>/` retains copied Parquet inputs, exact source, request and manifest,
progress/output, and finished result. Copies are not hardlinks to original caches.
The manifest binds source/data file hashes, logical dataset hashes, engine version,
Python/dependency versions, actions and parameters. Content is checked before
execution and before accepting results. Completed result hashes are checked on read.

Run/Cancel and shutdown own process handles plus creation identities, track child
processes, and stop owned processes. POSIX workers own a process group. A worker
watchdog checks its parent identity and exits on parent death. If process discovery
is unavailable, execution fails before launch. Previously unfinished records become
interrupted after restart; completed runs stay available. stdout/stderr are capped
at 1 MB each; UI tails are 64 KB. Context output previews retain recent records;
finished results retain up to 5,000 context logs and 100,000 plot points with an
explicit truncation notice.

## Actual verification boundary

- Chrome 155 and Edge 155 authoring and research browser workflows passed on macOS. The research
  check includes parameters, results, CSV export, input inspection, comparison,
  reload and chart interaction during a busy script. Recorded cancellation took
  1.810 seconds in Chrome and 1.894 seconds in Edge, including browser automation.
- Unit/integration cases cover shared capital, timing, gap/touch fills, brackets,
  long/short/collateral/fees, causal multi-hop FX, splits/dividends, incomplete bars,
  source-index indicators, future perturbation and repeatable results.
- Actual workers passed isolated-environment, copied/hash-bound snapshots, exact
  rerun results, traceback, child cleanup, cancellation, deadline, memory and
  interrupted-shutdown checks. Restricted macOS process monitoring initially failed;
  the failure path was corrected and tests rerun with monitoring available.
- The ten-year synthetic benchmark used 20 instruments × 2,516 actual XNYS session
  dates, 50,320 bars, and monthly rebalance: 4.984 seconds worker duration, 0.433
  seconds snapshot creation, 299,745,280 bytes sampled peak worker-tree RSS on this
  14-core/48-GiB arm64 Mac. See `../evidence/performance/research.json`.
- All 42 built-ins have chart/replay/SDK consistency checks; separate hand-computed
  cases cover metric definitions. All four example scripts execute in managed workers.
- Replay/paper integration, actual Coinbase completed-candle paper fills, and
  abrupt-parent-death verification pass; see `replay-paper.md`. Saved script versions
  and completed results survived an actual isolated service restart and were reopened
  in the browser (`../evidence/recovery/report.json`). Windows remains unverified;
  see `acceptance.md` for other open requirements. These checks do not mark the full goal done.

Primary runtime references: [Python subprocess](https://docs.python.org/3/library/subprocess.html),
[psutil](https://psutil.readthedocs.io/en/latest/), and
[Vite dependency optimization](https://vite.dev/config/dep-optimization-options.html).
