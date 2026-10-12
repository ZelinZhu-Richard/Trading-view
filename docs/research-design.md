# Research engine implementation contract (in progress)

This document records implementation choices within the complete goal; it does
not replace goal.md or establish completion. The editor, shared engine, SDK, process supervisor, replay and paper account APIs now exist.
Verification and remaining integration are tracked in progress.md and acceptance.md.

## Causal event order

Use one deterministic engine for strategy runs, replay and paper sessions. Source
bars are immutable raw market OHLC, never the Heikin-Ashi display transformation.
Incomplete bars do not participate. Explicit synthetic fixtures are allowed only
as labeled demonstration/test inputs; no market-accuracy claim follows from them.

Iterate the union of source bar start/end times and supplied action times. At a
shared timestamp: (1) finish eligible intrabar touches and existing brackets from
ending bars, using conservative stop-first ambiguity; (2) publish completed bars
and update known close valuations; (3) call on_bars once with the newly completed
batch; (4) apply effective corporate actions before the new session's opens;
(5) process opening bars and eligible market/gap orders in stable recorded order;
(6) record the portfolio state. Opening-time events are necessary: postponing a
daily market order until its bar closes would incorrectly let a later minute-bar
order spend its capital first. At equal time a signal from a completed prior bar
may enter the next bar opening at that same boundary.

Market fills use opening price and explicit slippage. Buy limits: favorable gap
open<=limit uses open; otherwise low<=limit uses limit. Sell limits are symmetric.
Stops use adverse gap opens or their touched threshold. Touch fills become known
at bar completion; use a documented conservative bar-opening FX rate, never a
future rate. Stable ordering uses event phase/time, order sequence and instrument.
Same-bar bracket stop wins if both exits are reachable. For an entry filled only
by intrabar touch, favorable same-bar exits require a stated conservative policy
because their ordering is unobserved. Do not claim tick execution accuracy.

## Accounting and FX

Use Decimal and shared backend/money.py tick/quantity routines. Keep per-currency
free cash and separately restricted short collateral/proceeds. No leverage by
default: long buys consume their full cash cost; shorts reserve 100% initial
notional in addition to restricted sale proceeds. Closing releases collateral and
pays the buyback. Short losses can exceed initial collateral after a gap; report
insolvency and reject new exposure rather than pretending gaps cannot occur.

Automatic currency funding converts available reporting-currency cash at causal
rates; preserve foreign-currency proceeds. Value every cash/position currency at
rates whose source bar completed no later than the valuation/fill timestamp.
Build deterministic explicit conversion paths from supplied base/quote datasets;
record path, provider/feed/hash, source timestamp and age. Never assume USD/USDT or
any other pair is at parity. Missing required conversion blocks that operation or
valuation. Include currency translation separately in contribution reconciliation.

Apply supplied raw-price splits before relevant opening fills: quantities and
pending order levels/quantities adjust, cost basis and last mark adjust inversely.
Skip split accounting when dataset adjustment already includes splits. Dividends
credit longs and debit shorts at the supplied cash-effective time; skip dividends
for total-return-adjusted data. Mark corporate-action coverage unknown unless the
input explicitly describes it; do not imply downloaded coverage.

## SDK and worker ownership

Public script hooks: initialize(ctx), on_bars(ctx,bars), finalize(ctx); custom
indicator hook calculate(ctx). PARAMETERS is a literal declaration dictionary,
validated without executing imports or source. Context supplies immutable causal
history, metadata, shared indicator calculations, portfolio/orders/fills, SDK clock,
seeded randomness, user state, logging and plotting. No public future-data accessor.
Trusted code can introspect Python/host files; process separation is not a hostile
code security boundary. Examples use SDK time/randomness rather than wall time.

Run only after explicit Run. Snapshot source/hash, parameters, dataset logical and
file hashes, actions, execution settings, engine/dependency versions and provenance
before starting. Worker directories live under data/runs. Copy snapshot data;
never hardlink it to mutable script-accessible original files. Run in separate
processes with a minimal environment that contains no provider credentials, bounded
concurrency, deadline/memory monitoring and owned-process cancellation/cleanup.
Persist queued/running/completed/failed/cancelled/interrupted states and structured
errors/logs. Saving/importing scripts never runs them or installs dependencies.

Replay seeks rebuild from the start or a valid earlier checkpoint. Rebuilds exclude
future manual actions and reset portfolio/indicator/user state. Paper and replay
accounts remain distinct. Runs retain immutable results, exact settings and data
provenance; metric undefinedness and zero-cost assumptions stay explicit.
