# Implementation progress

Updated 2026-10-12 UTC. The user waived further Edge checks in `../goal.md`; the
tracked goal is blocked on Windows access and actual Alpaca trade delivery. `requirements.json` maps all specification content,
including prose obligations, to implementation, evidence and remaining limitations.

## Current state

- Foundation: local React/TypeScript/Lightweight Charts frontend, Python service,
  locked environments, generated contracts, SQLite/Parquet storage, six bounded
  REA investigations, validated import and saved-work recovery implemented.
- Data and workspaces: all three provider adapters, CSV mapping/preview, calendar
  normalization, immutable versions, watchlists, chart variants/layouts/linking,
  source/freshness display, shared quote streams and completed-candle refresh.
- Analysis: all 42 indicators and 24 drawing families, templates, object editing,
  undo/redo, completed-bar alerts and persistent notification history.
- Python and simulation: local Monaco, exact-source versions, causal SDK, managed
  workers, shared Decimal multi-instrument/currency engine, replay, paper accounts,
  reproducible snapshots, reports, comparisons and exports.
- Acceptance: numerical, simulation and primary Chrome/Edge workflows passed on
  macOS. Remaining requirements are listed below; the whole goal is not complete.

## Latest verification

- Repository relocation on 2026-10-12: all 243 backend tests and 34 frontend tests
  passed in `workspace/trading-view`; TypeScript/build and all 420 specification
  mappings passed. The main app and existing Chrome verification workspace restarted
  successfully, with both providers still configured. See `../evidence/relocation-check.json`.
  The first restricted run passed 238 tests but blocked five worker checks because
  macOS process inspection was unavailable; the permitted rerun passed all 243.
- 236 backend tests passed in 7.53 seconds (`../evidence/backend-tests.xml`),
  including all-indicator reference/causality checks, hand-computed metrics,
  worker cancellation/parent death, and examples. Thirty-four frontend tests,
  TypeScript checks, Ruff checks and the production build passed. Seven subsequent
  export-boundary tests passed (`../evidence/export-tests.xml`): empty tables preserve
  headers and populated rows retain decimal/nested conversion values.
- Chrome 155.0.8059.39: ten workflows passed under `../evidence/browser/chrome-final/`.
  Edge 155.0.4283.45: nine workflows under `../evidence/browser/edge/` plus the
  drawing-edge workflow under `../evidence/browser/edge-drawing-edges/` passed.
  Required 1280×800 and 1920×1080 layouts and both themes were exercised.
- Actual configured Alpaca AAPL/SPY history and Alpha Vantage EUR/USD history
  passed, including weekly/monthly derivation. Alpaca's actual directory exposed
  a long legal security name; removing the arbitrary display-name cap fixed the
  failure, with a regression test. No credentials were retrieved into evidence.
- Alpaca stream authentication and unsubscribe passed. No trade arrived in the
  20-second check, so actual trade delivery remains unverified.
- Actual Coinbase discovery/history/ticker/stream/unsubscribe/reconnect passed.
  A provider-backed chart grew from seven to twelve completed minute candles and
  a local paper order filled at its next eligible actual source opening.
- An isolated credential-free service copy was stopped, observed offline, and
  restarted. Workspace/drawing, script versions, paper positions, finished result
  and alert history hashes matched. The built frontend reopened those records.
  See `../evidence/recovery/report.json` and its screenshots.
- Failed migration and unsupported future database version tests preserve saved
  documents and versions. Focused watchlist/drawing endpoints share workspace
  revisions and reject stale edits without losing unrelated chart settings.
- Dialog focus restoration was fixed across seven dialogs. Keyboard users can
  create drawings from the object form, edit coordinates, add/remove path anchors,
  and page through long paths. Focusable charts support arrow pan, +/- zoom and Home
  fit. Native keyboard checks in the in-app browser passed; screenshots and exact
  limits are in `../evidence/browser/keyboard-report.json`.
- Native Chrome checks passed for all seven modal focus returns/reopening,
  1,201-item watchlist Home/End/arrows/Page keys and Enter, Python Tab/Shift-Tab,
  optional indentation and Escape, version-2 save and completed synthetic research,
  and keyboard trend creation with saved price 112.25. The first Chrome check found
  that Monaco still indented with Tab navigation enabled; capture-phase handling
  fixed it and the rebuilt app passed the same check. Some workflow entry points
  used pointer focus setup; this is not a claim of an entirely keyboard-only run.
  See `../evidence/browser/chrome-keyboard-report.json`.
- Watchlist selection took 933 ms including native automation/accessibility.
  Chrome reported rounded tab memory of 102 MB with one item and 96.8 MB after
  1,201-item navigation. These are snapshots, not peak/heap or isolated allocations.
  See `../evidence/performance/watchlists.json`.
- The follow-up Alpaca check at 2026-10-12 03:37:57 UTC authenticated and
  unsubscribed cleanly, with no quote during its 20-second window. The verifier's
  overall status now remains partial until an actual live Alpaca/IEX trade for
  the selected instrument arrives during the check; stale cached quotes cannot
  pass. Seven explicit verifier qualification fixtures passed. `--stream-only`
  preserves prior history evidence and avoids repeating Alpha Vantage requests.
- `windows-verification.md` provides a clean Windows setup, actual worker-process
  tests, Chrome workflow, development shutdown and built-app recovery checklist.
  It is preparation only; no Windows execution is claimed.
- The REA ledger retains 37 records and 16 screenshots across six investigations;
  access gates and official-documentation fallback decisions remain explicit.

## Remaining acceptance work

1. Observe an actual Alpaca IEX trade through the app when the source produces one.
   History and authentication are already verified; never substitute generated ticks.
2. Windows verification remains mandatory and externally unavailable: the user
   reports no Windows machine. No macOS result or scope waiver replaces it.

Further Edge checks were explicitly waived by the user on 2026-10-12 UTC.

## Performance evidence

All measurements are from an Apple M4 Pro, 14 cores, 48 GiB RAM, macOS arm64.
Four charts × 10,000 bars × five studies became ready in 1.2432 seconds; renderer
heap was 189.2→204.9 MB after interactions. The 20-instrument ten-year synthetic
portfolio used actual XNYS session dates (50,320 bars), 0.4333 seconds snapshot time,
4.9837 seconds worker time, and 299,745,280 bytes sampled peak worker-tree RSS.
Switch-loop and reconnect reports include their own timings and memory scopes.
Research cancellation took 1.810 seconds Chrome/1.894 seconds Edge including browser
automation; charts remained interactive during the separate busy-script workflow.
Renderer heap, sampled worker RSS and endpoint process RSS are different measures;
none is mislabeled as peak whole-application memory.

## Local operation and boundaries

Application: `workspace/trading-view/`. Development frontend 127.0.0.1:5173;
backend 127.0.0.1:8000. Reuse the owned development supervisor when running.
The production build is served by the Python service. Verification fixtures and
real-provider records retain distinct provenance. Temporary verification services
are stopped after use. Holdout has not been accessed; unrelated REA source remains
outside the application work. No real orders, purchases or deployment occurred.
The user separately authorized consolidation into this independent Git repository
and an initial commit and push on 2026-10-12. The specification is now `../goal.md`.
