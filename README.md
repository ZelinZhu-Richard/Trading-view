# Market Workbench

A local charting and research application. **Final acceptance is blocked on external verification.** See
`docs/progress.md` for verified capabilities and remaining stages. The full scope
is in [goal.md](goal.md); remaining acceptance gaps are listed in [docs/acceptance.md](docs/acceptance.md).

Repository: [ZelinZhu-Richard/Trading-view](https://github.com/ZelinZhu-Richard/Trading-view).
The local working folder is `~/dev/REA/workspace/trading-view`.

## Run locally

Use Python 3.12 and the Node/npm versions in `.nvmrc` and `package.json`.

```sh
uv sync --locked
npm ci
npm run dev
```

Open http://127.0.0.1:5173. The single development command starts the Python service
on port 8000 and the browser development server on port 5173. Both bind to loopback.
Press Ctrl+C to stop both. If the ports are already occupied, resolve that conflict
instead of starting duplicate servers.

The project-local Node executable installed during development is
`.toolchain/node/node_modules/node/bin/node`. Its npm entrypoint is
`.toolchain/node/node_modules/npm/bin/npm-cli.js`. These cached tools are optional;
a matching existing toolchain works too. Python runs from `.venv`.

For a built application:

```sh
npm run build
uv run uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000. No external application server or account is required.
This startup path is intended for macOS and Windows, but Windows verification has
not yet been performed. The [Windows verification checklist](docs/windows-verification.md)
records the required setup, process, browser and recovery checks without claiming
that they have passed.

## First workflow

1. Choose **Open synthetic example**, or **Import data** to load your own CSV.
2. For CSV, map OHLC columns and choose instrument, currency, interval, timezone,
   calendar and adjustment basis. Timestamps without offsets require a timezone.
3. Review row errors and duplicate counts. Imports with invalid rows cannot commit.
4. Select a dataset, chart style, scale and layout. Use the data table to inspect
   source values. Example candles remain prominently labeled synthetic.
5. Workspace changes save automatically. Wait for **Saved locally** before closing.

Use the data-source icon beside **Import data** to connect Coinbase public data,
or configure your free Alpaca / Alpha Vantage keys in the local dialog. Search for
an instrument, choose a UTC date range and supported interval, then load history.
Coinbase product/history/ticker/streaming checks have passed against the actual
public service. Configured Alpaca keys returned AAPL and SPY IEX history; Alpha
Vantage returned EUR/USD daily history and local weekly/monthly aggregations.
Alpaca stream authentication passed, but actual trade delivery remains unverified.
Live quotes appear in the watchlist and instrument summary. Enable **Follow candles**
to adopt new completed provider candles; saved research inputs stay immutable.
See `docs/data-conventions.md` and `docs/candle-updates.md`.

To enter or replace keys, open **Connect data source**, choose **Alpaca Basic**,
enter **API key** and **Secret key**, and select **Save keys locally**. Then choose
**Alpha Vantage**, enter its **API key**, and save. Empty fields after a successful
save are intentional; saved keys are never returned to the browser.

Data lives in `data/`: SQLite for documents/history, immutable content-addressed
Parquet for datasets. A dataset's hash includes its instrument, interval and bars.
Workspace exports contain metadata and references, not the underlying Parquet files.
Keep the whole `data/` directory when backing up the local application.

## Analysis tools

- **Indicators** opens the 42-study library. Configure inputs, appearance and pane;
  save a template to reuse the set. Calculations use completed underlying source
  bars. Warm-up and unavailable values remain blank. Formulas and numerical choices
  appear in the settings; see `docs/indicator-formulas.md`.
- The left **Drawing tools** menu contains 24 families. Click anchors, drag a brush,
  or finish a path with Enter. Select anchors to edit them; drag a stroke to move
  an object. **Drawing objects** manages labels, styles, coordinates, visibility,
  locks, duplication and deletion. Undo/redo covers complete actions in this session.
- **Local alerts** evaluates completed stored bars. Choose a price or configured
  indicator output, condition and threshold. In-app notifications and trigger
  history persist. The service must stay running; streaming quotes alone do not
  supply completed candles. See `docs/alert-conventions.md` for the current boundary.

The Python editor, portfolio engine, replay and paper accounts are implemented.
Automatic provider candle refresh is integrated with charts, alerts, and paper
accounts. The full goal remains incomplete; Windows and the remaining acceptance gaps
are documented separately.

## Checks

```sh
uv run pytest
npm test
npm run typecheck
npm run build
uv run python scripts/check-acceptance.py
```

Regenerate browser contracts after changing backend models:

```sh
uv run python scripts/generate-contracts.py
```

## Repository contents

Source, lockfiles, examples, tests, the goal, documentation and bounded verification
reports are versioned. Your `data/` directory (including saved API keys), dependency
environments, builds, browser profiles, raw captures, screenshots and temporary
verification databases remain local and are ignored by Git. Moving the repository
does not move keys to GitHub. See [evidence/README.md](evidence/README.md) for the
distinction between committed reports and local supporting artifacts.

## Attribution

Charts use [TradingView Lightweight Charts](https://www.tradingview.com/),
Copyright © TradingView, Inc., licensed under Apache 2.0. The chart attribution logo
and application footer link are retained. TradingView reference investigations are
documented separately in `docs/reference-ledger.md`. This is an independent application.

## Python research

Open **Python editor**, create/import a script, then choose **Run settings**.
Select datasets, parameters, capital, currencies and costs; press **Run** explicitly.
**Research results** retains runs, comparisons, input hashes, logs, equity, orders
and exports. Cancel stops the owned worker. See [Python and research guide](docs/python-research.md)
and [examples](examples/README.md). Open **Replay & paper** for cursor controls and simulated accounts; see [replay and paper guide](docs/replay-paper.md).

Provider candle refresh, paper timing and pause behavior: [candle updates](docs/candle-updates.md).
