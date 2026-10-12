# Windows verification — not yet performed

The user has no Windows machine available. This checklist prepares the remaining
platform check; it is not Windows evidence and does not waive that requirement.
Use a real Windows installation. macOS, Linux, an emulated platform flag, or Wine
does not establish Windows behavior.

## Prepare a clean local checkout

Keep the application under the project's working subfolder. Transfer source,
lockfiles, examples and documentation. Create Windows dependencies locally;
do not copy the macOS `.venv`, `node_modules`, `.toolchain`, provider configuration,
browser profiles, or personal `data` directory. Begin with disposable test data.

Use the versions declared by the repository: Node 24.18.0 (`.nvmrc`), npm 11.16.0
(`package.json`), and Python 3.12 (`.python-version`). Run the following in
PowerShell from the `trading-view` repository root with a compatible `uv` available:

```powershell
uv sync --locked --python 3.12
npm ci
New-Item -ItemType Directory -Force evidence/windows | Out-Null
Get-CimInstance Win32_OperatingSystem | Select-Object Caption, Version, OSArchitecture
Get-CimInstance Win32_Processor | Select-Object Name, NumberOfCores
Get-CimInstance Win32_ComputerSystem | Select-Object TotalPhysicalMemory
node --version
npm --version
uv run python --version
```

Record the displayed platform/tool versions in the Windows report. Do not copy
environment dumps or credentials into evidence.

## Numerical, worker and build checks

```powershell
uv run pytest --basetemp=evidence/windows/pytest-temp --junitxml=evidence/windows/backend-tests.xml
if ($LASTEXITCODE -ne 0) { throw 'Backend checks failed' }
npm test
if ($LASTEXITCODE -ne 0) { throw 'Frontend checks failed' }
npm run build
if ($LASTEXITCODE -ne 0) { throw 'Build failed' }
```

The pytest temporary directory is disposable and is replaced on a subsequent run.
Retain actual output and skipped/failed test names. In particular, inspect
`tests/test_research_workers.py`: actual process launch, environment filtering,
queued cancellation, child cleanup, deadline/memory limits, service shutdown,
restart, and abrupt parent exit must pass on this host. A mocked process or a
successful UI cancellation alone is insufficient evidence of cleanup.

## Startup, browser workflow and recovery

1. Run `npm run dev`. Visit `http://127.0.0.1:5173/` in Chrome and verify the local
   service connects. Record Chrome's actual version and observed viewport size.
2. Import `examples/china-daily-synthetic.csv` with its metadata from
   `examples/README.md`, reviewing the mapping, preview and any row errors. Also
   open the synthetic example. Keep the synthetic labels and execution opt-in.
3. Exercise one/two/four charts, an overlay and a separate-pane indicator,
   watchlist selection, interval changes, drawing coordinates and persistence.
   Check 1280×800 and 1920×1080, both themes, resizing, visible focus, and keyboard
   navigation. Include editor Tab/Shift-Tab, optional indentation and Escape.
4. Import an included strategy explicitly, save a version, and run it with the
   documented synthetic opt-in. Inspect its inputs, results and logs. Export JSON
   and CSV, then open the files to confirm their contents. Cancel a separate busy
   test run and confirm the owned process exits.
5. Create a replay account, submit a simulated order, step to its eligible opening,
   and inspect the fill and position. Step/play/pause and seek backward; check
   that later candles and later simulation state are absent. Check paper-account
   persistence separately using the candle/recovery procedures in the linked guides.
6. Wait for **Saved locally**. Stop the development command with Ctrl+C. Verify
   both listeners close and that its owned reloader and child processes stop.
   Do not kill unrelated applications to obtain a passing result. Record any
   leftover owned process as a failure requiring a launcher fix.
7. Start the same command again. Confirm saved workspace, drawings, script
   versions, account position, completed result and alert history restore without
   unexplained changes. An interrupted research run must stay interrupted.
8. Stop development. Run the built application with
   `uv run uvicorn backend.app:app --host 127.0.0.1 --port 8000` and verify the
   same saved work at `http://127.0.0.1:8000/`. Stop it cleanly after checking.

Use [replay and paper](replay-paper.md), [candle updates](candle-updates.md),
[Python research](python-research.md), and [data conventions](data-conventions.md)
for the exact semantics. Fixture-based checks must remain labeled as fixtures;
provider credentials are entered locally only if live checks are also requested.

## Record the outcome

Save a dated report under `evidence/windows/` containing hardware/tool versions,
commands, exit codes, pass/fail/skip results, browser observations, recovery
comparisons, and app-only screenshots. Reference it from `docs/requirements.json`
and `docs/acceptance.md`. Mark Windows verified only after the actual checks pass;
keep specific failures open otherwise. Edge repetition is waived by the user.

## Remaining Alpaca streaming check

This is a separate gap and can be completed on the existing macOS host. After
the local app has recorded successful configured-provider history checks, run:

```sh
uv run python scripts/verify-configured-providers.py --stream-only
```

It preserves prior history evidence, reads the stored instrument through the app,
and observes an actual Alpaca subscription for 20 seconds without fetching keys
or repeating Alpha Vantage requests. Only live Alpaca/IEX data for that instrument
timestamped during the check qualifies. Authentication, cached quotes and a clean
unsubscribe do not prove actual trade delivery. A no-trade result remains partial;
rerun when the source produces trades rather than fabricating a substitute.
