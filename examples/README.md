# Data examples

`china-daily-synthetic.csv` is fabricated for import testing. It is not market data.
Import it using symbol `CN-DEMO`, venue `EXAMPLE`, currency `CNY`, timezone
`Asia/Shanghai`, interval `1d`, calendar `XSHG`, and raw adjustment. All five dates
are regular Shanghai sessions according to the installed calendar package.

The application's **Open synthetic example** action creates a reproducible 365-bar
dataset using a fixed random seed. Its provenance is `fixture / deterministic-example`.
Never label either example as a provider connection or use it as a quote.

## Python examples

Import these through the Python editor, inspect Run settings, then explicitly Run:

- `custom_indicator.py`: rolling average via immutable history; choose Indicator type.
- `moving_average_crossover.py`: EMA crossover with shared built-in calculations.
- `multi_asset_rebalance.py`: monthly equal weighting in the reporting currency.
- `multi_currency_portfolio.py`: fixed-quantity holdings across currencies with supplied FX inputs.

Use sufficiently long datasets and suitable initial capital. Examples log simulated
activity only. See `../docs/python-research.md` for the SDK and cost assumptions.
