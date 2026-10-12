# Completed provider candle updates

Enable **Follow candles** below a provider-backed chart. The chart follows new
immutable snapshots of the same instrument metadata, source, feed, interval,
adjustment basis, and original history start. Turning it off freezes the latest
shown snapshot and saves that selection. Replay always uses its fixed inputs and
closes chart candle subscriptions while the replay cutoff is active.

A chart's subscription belongs to its browser connection. Only visible chart slots
subscribe. Two consumers of the same series share one history check; disconnecting
or hiding the last chart cancels its pending provider request unless an enabled
alert or unpaused paper account still needs that series. Enabled once-only alerts
stop requesting updates after they fire. Research jobs and saved snapshots never
subscribe or change their dataset hashes.

Coinbase and Alpaca checks are spaced at least 30 seconds apart per series. Alpha
Vantage daily forex checks are spaced one day apart to limit free-quota usage.
Provider-wide request spacing and bounded HTTP retries still apply. Catch-up runs
use bounded date windows; a recent overlap reconciles the last two target buckets.
Derived intervals fetch and aggregate their underlying documented provider bars.
No quote-to-OHLC approximation or missing-candle fabrication is used.

Only source-returned completed bars advance these snapshots. An incomplete candle
already present in an imported provider snapshot retains its last imported value
until the source returns it complete. Streaming quotes update the instrument
summary separately; the chart label says **Completed candles · checked**, not that
its last trade is necessarily fresh. Closed or empty sessions do not acquire
invented bars. The available-history range and source remain inspectable.

History snapshots are content-addressed Parquet files. Unchanged checks create no
new snapshot. Changed completed history creates a new snapshot; old inputs remain
available to research and replay. This deliberately retains storage rather than
pruning datasets still referenced by saved work. Automatic retention/compaction is
not implemented; long-running minute feeds accumulate historical revisions.

The footer shows waiting/updating/catching-up/stale states. Its detail tooltip
includes the last successful check and provider error. **Provider candle updates**
in the alert and paper panels exposes all known series, their active/paused state,
last success, history corrections, and a retry control. Failed requests retain
cached data. Browser reconnect uses bounded retries; the visible Retry control can
restart it. Backoff survives service restart, including daily forex quota failures.

Provider metadata changes reject the update. Recent corrections to completed bars
are recorded on the new snapshot; alerts and paper accounts compare their already
used prefix and stop adoption when it differs. They do not silently rewrite past
triggers, fills, or positions. Review the new history and create a new account or
explicitly reset the alert baseline when that is the intended decision.

Paper commands retain their actual wall-clock submission time, rounded upward to
whole seconds. Delayed source updates cannot fill a new order at an opening that
already passed before it was submitted. Manual command identities stay stable
when bracket children appear during catch-up. A cancellation submitted after an
eligible opening cannot erase that opening fill when the completed source bar
arrives. Without tick evidence, touch timing uses the shared documented bar rules.

**Pause paper updates** stops that account's refresh interest and disallows new
orders. Existing pending commands remain recorded. Resume catches up the elapsed
source history, so orders can fill during that elapsed period according to their
original eligibility; pausing updates is not a cancellation of pending orders.

Verification:

- `tests/test_candles.py`: provider-shaped HTTP fixtures, completed-bar chart/alert/
  paper integration, immutable original data, same-end partial completion, revised
  prefix rejection, source mismatch, sharing, cancellation, persisted backoff,
  socket origin validation and unsubscribe ownership.
- `tests/test_accounts.py`: nine replay/paper cases, including actual submission
  time, delayed cancellation, stable manual identities, pause and restart behavior.
- `evidence/browser/candles-paper-report.json`: actual Coinbase public minute data
  increased a chart from seven to twelve bars; a local simulated buy waited until
  the next eligible opening, then appeared in the fills table. Follow-off, saved
  pause, and account reopening passed in Chrome at 1280×800 with no page errors.
  No brokerage orders were submitted. Test accounts were paused on cleanup.
- `evidence/configured-providers.json`: configured Alpaca AAPL/SPY and Alpha Vantage
  EUR/USD history and weekly/monthly aggregation passed. Alpaca stream authentication
  and unsubscribe passed; actual trade delivery remains unverified. Incremental
  candle/paper delivery was observed against Coinbase; Alpaca/Alpha Vantage refresh
  integration also has explicit provider-shaped fixture coverage.
