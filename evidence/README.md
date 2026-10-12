# Verification evidence

The repository includes bounded JSON reports, test results and the REA evidence
index. These record the checks actually performed, their dates and their limits.
They do not establish that the entire goal has passed; see
[acceptance status](../docs/acceptance.md).

Raw REA bundles (`tradingview-reference.json`, `reference-baseline.json`), browser
action logs, screenshots, browser profiles and temporary SQLite/Parquet fixture
workspaces are retained locally but excluded from Git. The full reference bundle
contains embedded screenshot bytes. The index preserves evidence IDs, provenance
and screenshot hashes without publishing those binary captures.

Paths to screenshots or temporary workspaces inside reports describe historical
local artifacts. They will not exist in a fresh clone. Source checks and committed
report references in `docs/requirements.json` can be checked with
`uv run python scripts/check-acceptance.py`; that command checks coverage and file
existence, not the truth of recorded results or full product acceptance.

The project was moved from `workspace/market-workbench` to `workspace/trading-view`
on 2026-10-12. Historical reports retain their original observations and paths.
Current startup instructions and the requirement map use the new location.
