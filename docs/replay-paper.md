# Historical replay and paper accounts

Open **Replay & paper → New account**. Choose replay or current-market paper,
select one dataset per instrument (plus any FX series), and configure capital and
costs. These modes have separate account identities and never submit brokerage
orders. Explicitly enable synthetic inputs only for demonstrations.

Replay offers a UTC cursor, a position slider, single-completion stepping, play,
pause and target speeds from 0.5 to 10 steps per second. A step advances the union
of selected instruments' completion times. Playback waits for visible charts and
indicator values to load before scheduling another step. Slow calculation can
therefore reduce the achieved playback rate.

The amber replay banner remains visible when another bottom panel is open. All
charts use the same cutoff, and data/indicator responses exclude incomplete bars
and bars ending after that time. Old chart canvases are hidden immediately when
the cutoff changes. Current quotes are suppressed in chart details/watchlists while
replay is active. Leaving replay restores the normal chart universe.

Manual orders are accepted while paused, before the next opening. On the next
step, the same engine used by backtests processes those openings/touches and fills.
Market, limit, stop and market-entry bracket orders are available in the order form;
the public order contract also supports limit/stop bracket entries. Pending orders
can be cancelled. The panel shows orders, fills, positions, equity, free cash,
valuation errors and insolvency. The latest 200 orders/fills are rendered; account
history itself is retained.

A backward seek rebuilds the engine from its fixed inputs and retained commands.
Commands after the new cursor are discarded, so playing forward cannot silently
restore later positions or user actions. Commands exactly at the selected cursor
remain pending before that opening. Earlier data can warm up indicators without
creating carried-in account holdings. Closing and reopening a saved account
restores its cursor and accounting from the same command log.

To exercise a Python strategy at a replay cursor, open **Python editor → Run settings**
while the replay banner is active. The dialog selects the replay universe and costs,
and locks the run end to the cursor. Explicit Run starts a fresh managed strategy
worker and reports its portfolio to that time. This is an independent strategy
simulation; it does not inject manual replay-account commands or mutate that account.

Current-market paper accounts start empty at the latest already-completed stored
bars. They cannot seek backward. A local service checks for new stored history every
two seconds. Only the same instrument metadata, feed, source, interval, adjustment
and unchanged completed prefix can advance the account. Corrections to previously
used history stop adoption and produce an error. Future-dated bars remain unavailable
until their completion time has passed. A manual refresh button is also available.
The paper panel polls its persisted state and can be reopened after restart.

Supported provider candles now refresh automatically while the service is running;
see [candle updates](candle-updates.md) for frequency, error states and retention.
Paper commands use their actual submission time, so a delayed update cannot fill
an order at an opening that preceded submission. Pause paper updates stops checks;
resuming catches up pending commands through elapsed history. Quote ticks alone
never fill completed-bar orders.

Verification: `tests/test_accounts.py` has nine replay/paper cases, including restart,
backward reset, different calendars, cancellation, unchanged-prefix refresh,
wall-clock availability and owned background cleanup. Chrome verification in
`../evidence/browser/replay-report.json` checks four charts and shared SMA cutoffs,
manual next-open fills, step/play/pause/speed, backward reset, cursor-bounded Python,
reopen and exit. Replay evidence uses explicit synthetic prices. The separate Coinbase candle/paper
browser report records actual public candles and simulated fills; it does not
establish Windows behavior. The full replay workflow also passed in Edge 155 on
macOS (`../evidence/browser/edge/replay-report.json`). A credential-free copy of
the actual saved paper position survived a process restart and was reopened in
the built frontend (`../evidence/recovery/report.json`).
