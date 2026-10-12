# Local completed-bar alerts

The local service evaluates price OHLC fields or a captured built-in indicator
output against above/below/crossing conditions. Strict crossings require a known
previous value: crossing above means previous <= threshold and current > threshold.
Equality alone does not trigger. Missing indicator warm-up/gap values do not cross.
Recurring threshold alerts can fire on every qualifying completed bar. Once-only
rules stop after their first event; pausing/resuming can rearm at the latest local
baseline. Condition edits also establish a fresh latest-bar baseline.

The service compares newly stored datasets only when instrument metadata, interval,
provider, feed, and adjustment basis match. It requires the previously evaluated
prefix to be unchanged. A historical correction stops that rule with a review
message; it is not silently treated as an append. Events and cursor updates commit
in one SQLite transaction, with a unique alert/bar-end key. A browser reload or
service restart does not duplicate prior triggers. Deleting a rule retains events.

Alerts currently evaluate **stored completed bars**. A streaming quote is not a
completed OHLC bar and does not trigger this service. Importing/refetching complete
history supplies new bars. Enabled provider-backed rules also request automatic
completed-candle reconciliation through the shared [candle service](candle-updates.md).
The service must remain
running. The UI reports running/stopped/disconnected/error state and the last
completed data timestamp, and polls for in-app notices plus a persistent history.
No external messaging is sent.

Schema migration 1 → 2 adds alert checkpoints/events transactionally. Before
migrating an existing version-1 database, `Store` makes a consistent SQLite backup
under the application data directory's `backups/` folder. Unknown future versions
are rejected without rewriting the database.

Verification: `tests/test_alerts.py` covers strict boundaries, null values, price
and SMA conditions, recurring/once-only behavior, pause/resume, optimistic edits,
corrected history, restart deduplication, owned-task shutdown and migration backup.
`evidence/browser/alerts-report.json` records a synthetic two-crossing workflow,
notification, trigger-history display, pause/resume and reload in Chrome on macOS.
The workflow also passed in Edge; the latest suites are under
`../evidence/browser/chrome-final/` and `../evidence/browser/edge/`. An actual
service restart preserved alert history (`../evidence/recovery/report.json`).
The owned test rule was deleted; its explicitly named synthetic events remain in
the local audit history, as designed. No live-market alert delivery claim is made.
