# Acceptance status — goal blocked

Updated 2026-10-12 UTC. Market Workbench is implemented across all five stages,
with the acceptance gaps below still required. The complete goal is **not achieved**.

[`requirements.json`](requirements.json) maps 420 specification rows: the original
319 bullet/table items plus 101 prose/context paragraphs. Every row retains its
source line, text, status, evidence paths and limitations. Context/table headers
are informational; explicit exclusions are not missing features. “Verified” means
the linked bounded checks passed, not all platforms or all possible inputs.

## Recorded outcomes

| Area | Evidence | Actual scope |
|---|---|---|
| Repository relocation | `../evidence/relocation-check.json`, `../evidence/relocation-backend-tests.xml` | All 243 backend tests, 34 frontend tests, TypeScript/build and 420 requirement mappings passed from `workspace/trading-view`. App restarted and both provider configurations remained present. The initial restricted run's five process-inspection failures are retained separately |
| Backend, numerical, simulation and worker checks | `../evidence/backend-tests.xml` | 236 passed in the full run plus seven later export-boundary cases (`../evidence/export-tests.xml`); includes 42-indicator reference/causality cases, hand-computed accounting/metrics, real managed processes, cancellation and parent-death cleanup |
| Frontend helpers and build | `src/*.test.ts`, production build | 34 tests; TypeScript, Ruff and build passed. Monaco's large lazy-loaded chunk produces a build warning |
| Primary Chrome workflow | `../evidence/browser/chrome-final/suite.json` | Ten workflows passed in Chrome 155.0.8059.39 on macOS |
| Primary Edge workflow | `../evidence/browser/edge/suite.json`, `../evidence/browser/edge-drawing-edges/suite.json` | Nine workflows plus drawing edges passed in Edge 155.0.4283.45 on macOS |
| Layout/themes | Browser report/screenshots in the above suites | 1280×800 and 1920×1080; dark/light, four charts, resizing and primary interaction |
| Indicators and drawings | `tests/test_indicators.py`, `tests/test_sdk.py`, `tests/test_money.py`, browser indicator/drawing/edge reports | All 42 indicators; all 24 drawing families, whole-object/anchor editing, snap, zoom/resize/interval invariance, lock, undo and persistence |
| Watchlists | Browser watchlist reports | 1,201 identities with five rendered rows; sections, sort, import/export, select and persistence. Chrome tab-memory snapshots recorded in `../evidence/performance/watchlists.json` |
| Alerts and provider candles | `tests/test_alerts.py`, `tests/test_candles.py`, browser alert and candle/paper reports | Completed-bar evaluation, shared refresh, correction rejection, history/deduplication, provider-shaped failure cases |
| Actual Coinbase | `../evidence/coinbase-live-check.json`, `../evidence/browser/provider-report.json`, `../evidence/browser/candles-paper-report.json`, reconnect report | Products/history/ticker/stream; actual growing chart and local simulated next-open fill; reconnect and final-listener cleanup |
| Actual Alpaca | `../evidence/configured-providers.json` | AAPL and SPY: 63 daily IEX bars each, 13 weekly/four monthly; authenticated stream and unsubscribe. No trade observed in the follow-up 20-second check at 2026-10-12 03:37:57 UTC; overall provider verification remains partial |
| Actual Alpha Vantage | Same configured-provider report | EUR/USD: 64 daily bars, 13 weekly/four monthly; missing volume retained. No claim of premium intraday support |
| Replay/Python/research | Browser Python/replay/research reports; SDK/account/worker/example tests | Author/save/version/run, causal cutoffs, replay reset, shared paper rules, comparisons, exports, busy-chart interaction and cancellation |
| Actual process restart | `../evidence/recovery/report.json` | Credential-free snapshot, actual stop/offline/start, matching hashes for workspace, drawing, script versions, paper position, result and alerts; restored built UI inspected |
| Migration failure | `tests/test_store_recovery.py` | Deliberately denied second migration table rolls back first; backups and documents retained. Future version rejection preserves logical database contents |
| Collection endpoints | `backend/workspace_routes.py`, `tests/test_workspace_routes.py` | Watchlists and per-chart drawings use the workspace's revision authority; stale writes conflict, unrelated state survives restart |
| Keyboard improvements | `../evidence/browser/keyboard-report.json`, `../evidence/browser/chrome-keyboard-report.json` | Native Chrome: seven dialogs restore focus/reopen, 1,201-item navigation, editor Tab/Shift-Tab/indent/Escape, save/run, drawing coordinates/persistence. Some entry points used pointer focus setup. Chart keys also checked in the in-app browser. Further Edge checks waived by the user |
| REA reference investigation | `reference-ledger.md` | Six bounded investigations, 37 retained records, 16 screenshots; access gates and documented fallbacks separately labeled |

Provider HTTP failures, quotas, pagination and some reconnect scenarios use explicit
fixtures. Those tests establish adapter handling, not real-provider availability.
The separately named real-provider reports contain observed network results.
Credentials were entered by the user locally and are not included in reports,
exports, screenshots or worker environments.

## Performance

Hardware: Apple M4 Pro, 14 cores, 48 GiB RAM, macOS arm64.

| Workload | Recorded result | Memory scope |
|---|---|---|
| Four charts × 10,000 bars × five indicators | 1.2432 s to ready; six drag roundtrips 132–152 ms including automation | Renderer JavaScript heap 189.2→204.9 MB |
| 20-instrument daily portfolio, 2015–2024 | 50,320 synthetic prices on actual XNYS session dates; snapshot 0.4333 s, worker 4.9837 s | Sampled peak worker-tree RSS 299,745,280 bytes |
| Repeated symbol/interval changes | Eight loops, Chrome roughly 1.08–1.23 s per roundtrip including automation/autosave | Chrome renderer heap 50,513,976 bytes; Edge report also records heap |
| Actual Coinbase reconnect | 1.49278 s after forced close; two connections, no remaining listeners/tasks after cleanup | Endpoint process RSS roughly 122.4→128.7 MB, not peak |
| Large watchlists | 1,201 identities; earlier full workflows 3.735 s Chrome / 4.015 s Edge; native Chrome selection 933 ms including automation/accessibility | Chrome rounded tab-memory snapshots 102 MB small list → 96.8 MB after navigation; not peak/heap or isolated allocation. See `watchlists.json` |
| Cancellation during research | 1.810 s Chrome / 1.894 s Edge including automation; active charts responded during the busy job | Worker cleanup independently verified by actual-process tests; not a whole-app peak claim |

Sources: `../evidence/performance/` and browser links/research/watchlist reports.
These separate workloads do not imply all stress cases ran simultaneously.

## Still required

- **Windows:** unavailable in this session; user confirmed no Windows machine.
  Startup/worker/platform behavior remains unverified. This requirement is retained.
  The [Windows checklist](windows-verification.md) prepares the checks but is not
  platform evidence.
- **Alpaca trade delivery:** a real IEX trade through the authenticated subscription
  has not been observed. History, authentication and unsubscribe already passed.
  The streaming-only verifier now rejects stale/cached, wrong-feed, wrong-symbol
  future-dated and pre-observation quotes; seven qualification fixtures passed, separately from
  the actual provider check.

Further Edge checks were explicitly waived by the user on 2026-10-12 UTC.
Chrome screenshot capture was blocked by automatic approval review because it
could include unrelated private browser tabs. Text observations were retained;
`../evidence/browser/chrome-result-iab-view.png` shows the saved drawing reopened
in the isolated in-app browser, not a Chrome capture.

These required acceptance tasks remain unresolved. Independent preparation is
complete; the tracked goal is blocked pending Windows access and actual Alpaca
trade delivery.
No real trading, purchases, deployment or holdout reads occurred. The user separately
authorized the initial Git commit and push on 2026-10-12; this does not close the
remaining product acceptance gaps.
