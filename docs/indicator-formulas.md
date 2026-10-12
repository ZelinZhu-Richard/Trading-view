# Indicator formula reference

Research date: 2026-10-11. Scope: the 42 indicators required by `workspace/goal.md`.

This is a proposed calculation contract for the independent Python implementation. It is **not a TradingView numerical-parity report**, and it does not certify the current app. The earlier REA runtime investigation established interface behavior; screenshots did not establish formulas, hidden preload, initialization, or numerical values. This pass used public primary documentation, Alan Hull's own explanation, and a few official QuantConnect/MetaTrader definitions. It did not reopen the reference browser.

The machine-readable companion, [indicator-reference.json](indicator-reference.json), contains every formula, canonical ID, proposed default, output/pane, warm-up, exceptional case, source URL, and verification case. Its `source_ids` distinguish supporting evidence from `unsettled_or_app_choices`. Warm-up indices are derived from the stated contract; they are not observations of TradingView's first plotted bar.

## Common calculation contract

Index `t=0` is the first input bar. A length-`n` rolling price window includes the current completed bar and first becomes ready at `n-1`. A length-`n` price change needs `n+1` prices and first becomes ready at `n`. Do not create weekend bars or replace absent observations with zeros.

For this app, EMA uses `alpha=2/(n+1)`; Wilder/RMA uses `alpha=1/n`. Both publish the arithmetic mean of their first `n` valid inputs as their seed, then recur as `y = alpha*x + (1-alpha)*previous_y`. Each cascade seeds separately, so DEMA first becomes ready at `2(n-1)`, TEMA at `3(n-1)`. These seed positions are explicit app choices. The [general MA documentation](https://www.tradingview.com/support/solutions/43000502589-moving-averages/) describes an SMA seed for EMA; the [ADX documentation](https://www.tradingview.com/support/solutions/43000589099-average-directional-index-adx/) supplies Wilder-style recurrence and an arithmetic initial ADX. Neither proves exact agreement with every Pine built-in.

Use population standard deviation by default: divide squared deviations by `n`. A separately selected sample convention divides by `n-1`; do not change this invisibly. [QuantConnect's primary definition](https://raw.githubusercontent.com/QuantConnect/Lean/master/Indicators/StandardDeviation.cs) explicitly uses population normalization. This is a supported independent convention, not proof of TradingView's denominator.

Explicit missing inputs invalidate full rolling windows and reset recursive studies for reseeding. Unknown contributions invalidate cumulative OBV/ADL/anchored VWAP until the missing prefix is repaired or an explicit new baseline is selected. A session VWAP can recover at the next complete session. This differs deliberately from some Pine functions: the [official FAQ](https://www.tradingview.com/pine-script-docs/faq/functions/) says SMA can ignore `na` observations. Valid zero volume remains zero; absent or unsuitable volume disables dependent calculations.

Use one calculation path for closed-bar charts, replay, and backtests. Keep provisional live-bar values visibly provisional. Every shifted plot stores `computed_at`, `available_at`, and `plot_at` separately. Higher-timeframe values cannot become available before their source bar completes. Display precision, line styling, and pane placement cannot modify calculation values.

## Proposed catalogue

The table summarizes the defaults. It does not assert that every value is a TradingView standalone UI default: some come from worked examples or [Technical Ratings configurations](https://www.tradingview.com/support/solutions/43000614331-technical-ratings/), and the registry labels app choices individually. A pane named for the indicator means a separate numeric scale; volume MA shares the volume pane.

### Moving averages

| Canonical ID | Proposed defaults | Outputs / pane | Primary reference |
|---|---|---|---|
| `sma` | length=9, source=close | value / price | [Simple Moving Average](https://www.tradingview.com/support/solutions/43000696841-simple-moving-average/) |
| `ema` | length=9, source=close, seed=sma | value / price | [Moving Averages](https://www.tradingview.com/support/solutions/43000502589-moving-averages/) |
| `wma` | length=9, source=close | value / price | [Moving Averages](https://www.tradingview.com/support/solutions/43000502589-moving-averages/) |
| `vwma` | length=20, source=close | value / price | [Volume-Weighted Moving Average](https://www.tradingview.com/support/solutions/43000592293-volume-weighted-moving-average-vwma/) |
| `dema` | length=9, source=close, seed=sma | value / price | [Moving Averages](https://www.tradingview.com/support/solutions/43000502589-moving-averages/) |
| `tema` | length=9, source=close, seed=sma | value / price | [Moving Averages](https://www.tradingview.com/support/solutions/43000502589-moving-averages/) |
| `hma` | length=9, source=close, rounding=floor | value / price | [Hull Moving Average](https://www.tradingview.com/support/solutions/43000589149-hull-moving-average/) |
| `kama` | length=10, fast=2, slow=30, source=close, seed=previous_source | value / price | [Kaufman's Adaptive Moving Average](https://www.tradingview.com/support/solutions/43000773012-kaufman-s-adaptive-moving-average-kama/) |
| `alma` | length=9, offset=0.85, sigma=6, source=close, floor_center=false | value / price | [Arnaud Legoux Moving Average](https://www.tradingview.com/support/solutions/43000594683-arnaud-legoux-moving-average/) |

### Overlays

| Canonical ID | Proposed defaults | Outputs / pane | Primary reference |
|---|---|---|---|
| `bollinger_bands` | length=20, multiplier=2, source=close, basis=sma, ddof=0 | basis, upper, lower / price | [Bollinger Bands](https://www.tradingview.com/support/solutions/43000501840-bollinger-bands-bb/) |
| `keltner_channels` | length=20, atr_length=10, multiplier=2, source=close, basis=ema, range_smoothing=rma | basis, upper, lower / price | [Keltner Channels](https://www.tradingview.com/support/solutions/43000502266-keltner-channels-kc/) |
| `donchian_channels` | length=20, include_current=true | upper, middle, lower / price | [Donchian Channels](https://www.tradingview.com/support/solutions/43000502253-donchian-channels-dc/) |
| `ichimoku` | conversion=9, base=26, span_b=52, displacement=26 | conversion, base, leading_a, leading_b, lagging_close / price | [Ichimoku Cloud](https://www.tradingview.com/support/solutions/43000589152-ichimoku-cloud/) |
| `supertrend` | atr_length=10, factor=3, smoothing=rma | line, direction / price | [Supertrend](https://www.tradingview.com/support/solutions/43000634738-supertrend/) |
| `parabolic_sar` | start=0.02, increment=0.02, maximum=0.2 | sar, direction / price | [Parabolic SAR](https://www.tradingview.com/support/solutions/43000502597-parabolic-sar-sar/) |
| `pivot_points` | method=traditional, period=session, levels=3, session_mode=instrument_regular | p, r1, s1, r2, s2, r3, s3 / price | [Pivot Points Standard](https://www.tradingview.com/support/solutions/43000521824-pivot-points-standard/) |

### Momentum

| Canonical ID | Proposed defaults | Outputs / pane | Primary reference |
|---|---|---|---|
| `rsi` | length=14, source=close, smoothing=rma | value / rsi | [Relative Strength Index](https://www.tradingview.com/support/solutions/43000502338-relative-strength-index-rsi/) |
| `stochastic` | length=14, k_smoothing=3, d_smoothing=3 | k, d / stochastic | [Stochastic](https://www.tradingview.com/support/solutions/43000502332-stochastic-stoch/) |
| `stochastic_rsi` | rsi_length=14, stochastic_length=14, k_smoothing=3, d_smoothing=3, source=close, scale=100 | k, d / stochastic_rsi | [Stochastic RSI](https://www.tradingview.com/support/solutions/43000502333-stochastic-rsi-stoch-rsi/) |
| `macd` | fast=12, slow=26, signal=9, source=close, oscillator_ma=ema, signal_ma=ema, seed=sma | macd, signal, histogram / macd | [MACD](https://www.tradingview.com/support/solutions/43000502344-moving-average-convergence-divergence-macd-indicator/) |
| `cci` | length=20, source=hlc3, constant=0.015 | value / cci | [Commodity Channel Index](https://www.tradingview.com/support/solutions/43000502001-commodity-channel-index-cci/) |
| `roc` | length=9, source=close, scale=100 | value / roc | [Rate of Change](https://www.tradingview.com/support/solutions/43000502343-rate-of-change-roc/) |
| `momentum` | length=10, source=close | value / momentum | [QuantConnect LEAN: Momentum](https://raw.githubusercontent.com/QuantConnect/Lean/master/Indicators/Momentum.cs) |
| `williams_r` | length=14 | value / williams_r | [MetaTrader 5: Williams' Percent Range](https://www.metatrader5.com/en/terminal/help/indicators/oscillators/wpr) |
| `trix` | length=18, signal_length=9, source=close, seed=sma | value, signal / trix | [TRIX](https://www.tradingview.com/support/solutions/43000502331-trix/) |
| `ultimate_oscillator` | short=7, medium=14, long=28, weights=4/2/1 | value / ultimate_oscillator | [Ultimate Oscillator](https://www.tradingview.com/support/solutions/43000502328-ultimate-oscillator-uo/) |
| `awesome_oscillator` | fast=5, slow=34, source=hl2 | histogram / awesome_oscillator | [Awesome Oscillator](https://www.tradingview.com/support/solutions/43000501826-awesome-oscillator-ao/) |

### Volatility and strength

| Canonical ID | Proposed defaults | Outputs / pane | Primary reference |
|---|---|---|---|
| `atr` | length=14, smoothing=rma | value / atr | [Average True Range](https://www.tradingview.com/support/solutions/43000501823-average-true-range-atr/) |
| `adx_dmi` | di_length=14, adx_length=14, smoothing=rma | plus_di, minus_di, adx / adx_dmi | [Directional Movement](https://www.tradingview.com/support/solutions/43000502250-directional-movement-dmi/) |
| `aroon` | length=14, tie=most_recent, window_extra=1 | up, down / aroon | [Aroon Indicator](https://www.tradingview.com/support/solutions/43000501801-aroon-indicator/) |
| `standard_deviation` | length=20, source=close, ddof=0 | value / standard_deviation | [QuantConnect LEAN: StandardDeviation](https://raw.githubusercontent.com/QuantConnect/Lean/master/Indicators/StandardDeviation.cs) |
| `historical_volatility` | length=20, source=close, returns=log, ddof=0, bars_per_year=252, annualization_mode=explicit | value / historical_volatility | [Historical Volatility](https://www.tradingview.com/support/solutions/43000589145-historical-volatility/) |
| `choppiness_index` | length=14 | value / choppiness_index | [Choppiness Index](https://www.tradingview.com/support/solutions/43000501980-choppiness-index-chop/) |

### Volume

| Canonical ID | Proposed defaults | Outputs / pane | Primary reference |
|---|---|---|---|
| `volume` | color_by=close_vs_open | volume / volume | [Pine: Chart information](https://www.tradingview.com/pine-script-docs/concepts/chart-information/) |
| `volume_ma` | length=20, method=sma | value / volume | [Pine: Declaration statements](https://tradingview.com/pine-script-docs/language/declaration-statements/) |
| `obv` | source=close, baseline=0 | value / obv | [On Balance Volume](https://in.tradingview.com/support/solutions/43000502593-on-balance-volume-obv/) |
| `mfi` | length=14, source=hlc3 | value / mfi | [Money Flow Index](https://www.tradingview.com/support/solutions/43000502348-money-flow-mfi/) |
| `cmf` | length=20 | value / cmf | [Chaikin Money Flow](https://www.tradingview.com/support/solutions/43000501974-chaikin-money-flow-cmf/) |
| `accumulation_distribution` | baseline=0 | value / accumulation_distribution | [Accumulation Distribution](https://www.tradingview.com/support/solutions/43000501770-accumulation-distribution-adl/) |
| `chaikin_oscillator` | fast=3, slow=10, seed=sma | value / chaikin_oscillator | [Chaikin Oscillator](https://www.tradingview.com/support/solutions/43000501979-chaikin-oscillator/) |
| `session_vwap` | source=hlc3, session_mode=instrument_regular, reset=session | value / price | [Volume Weighted Average Price](https://www.tradingview.com/support/solutions/43000502018-volume-weighted-average-price-vwap/) |
| `anchored_vwap` | source=hlc3, anchor_time=required, anchor_snap=first_bar_open_at_or_after, reset=none | value / price | [Anchored VWAP drawing tool](https://www.tradingview.com/support/solutions/43000669764-anchored-vwap-drawing-tool/) |

## Conventions that need special attention

### HMA, KAMA, and ALMA

HMA uses the weighted average of `2*WMA(floor(n/2)) - WMA(n)`, with a final WMA of `floor(sqrt(n))`; derived periods are at least one. [Alan Hull](https://alanhull.com/the-hull-moving-average/) specifies integer periods. The app chooses floor for positive lengths; test odd lengths and non-square lengths, because rounding differently changes values.

KAMA uses an efficiency ratio over `n` price changes, then squares the interpolation between fast and slow EMA coefficients. The first app output is at index `n`, initialized from the immediately previous source value; a zero volatility sum gives ER zero. The [TradingView definition](https://www.tradingview.com/support/solutions/43000773012-kaufman-s-adaptive-moving-average-kama/) defines the coefficient but leaves seed and flat-data behavior open. [LEAN's source](https://raw.githubusercontent.com/QuantConnect/Lean/master/Indicators/KaufmanAdaptiveMovingAverage.cs) demonstrates a previous-price seed variant; its readiness semantics are not adopted.

ALMA is a causal weighted sum of a trailing window. The registry defines Gaussian center `offset*(n-1)`, width `n/sigma`, and a `floor_center` option. [TradingView's support article](https://www.tradingview.com/support/solutions/43000594683-arnaud-legoux-moving-average/) supports the Gaussian idea and defaults 9/.85/6, but not center rounding. [LEAN](https://raw.githubusercontent.com/QuantConnect/Lean/master/Indicators/ArnaudLegouxMovingAverage.cs) floors its center; the proposed app default leaves it fractional. Do not interpret informal two-direction smoothing prose as authorization to use future prices.

### ADX, SAR, Supertrend, and Keltner

The [DMI article](https://www.tradingview.com/support/solutions/43000502250-directional-movement-dmi/) calls its smoothing exponential without a precise coefficient/order. The [ADX article](https://www.tradingview.com/support/solutions/43000589099-average-directional-index-adx/) gives the more specific Wilder recurrence. The app smooths DM and TR separately with RMA before dividing. Its transition-aligned seeds exclude the first bar, so default DI starts at index 14 and ADX at 27. Zero smoothed TR yields DI zero; zero DI sum yields DX zero. Those exceptions are chosen explicitly.

[Parabolic SAR](https://www.tradingview.com/support/solutions/43000502597-parabolic-sar-sar/) is a state machine, not just one recurrence. The registry fixes initial trend, initial extreme, acceleration changes, strict reversal comparisons, and prior-two-bar clamping. Equal initial closes choose down; reversals use the previous extreme. Outside bars and reversal-before-clamp ordering need separate fixtures. Other platforms can make different choices.

[Supertrend](https://www.tradingview.com/support/solutions/43000634738-supertrend/) carries its upper/lower bands and switches using the prior trend state. The app starts down at the first ready ATR, flips only on strict close crossings, and encodes up as +1/down as -1. Do not assume another platform uses the same sign encoding. Default 10/3 and ready-bar initialization are proposed settings.

The proposed [Keltner](https://www.tradingview.com/support/solutions/43000502266-keltner-channels-kc/) variant uses an EMA basis plus/minus a Wilder ATR multiple. A function named `ta.kc` or a channel using EMA-smoothed high-low range is not automatically an oracle for this variant.

### Plot offsets and prior-session pivots

[Ichimoku support](https://www.tradingview.com/support/solutions/43000589152-ichimoku-cloud/) describes 26-period forward and backward plotting. The app specifies exactly +26 for leading spans and -26 for lagging close. It does not silently substitute displacement minus one. With defaults, span B first calculates at source index 51 and plots at 77. A close plotted at an older position still becomes available only at its actual source time. Strategy comparisons against the cloud visible at `t` use already-known span values calculated at `t-26`; they must never read future values from a visually shifted array.

[Pivot Points Standard](https://www.tradingview.com/support/solutions/43000521824-pivot-points-standard/) names several genuinely different formula families. This contract chooses **Traditional**, with P and R1–R3/S1–S3 from the previous completed period, held fixed in the next period. Classic is not an alias for Traditional beyond the shared lower levels. Additional formula families and R4/R5 remain potential extensions, not claimed implementations. Daily-feed close/settlement, regular/extended sessions, and incomplete periods can change pivots even when arithmetic agrees.

### Volume, VWAP, and undefined ratios

[MFI](https://www.tradingview.com/support/solutions/43000502348-money-flow-mfi/) assigns flow by changes in typical price; unchanged typical price contributes neither direction. The app returns null for no directional flow, 100 for positive-only flow, and zero for negative-only flow. [OBV](https://in.tradingview.com/support/solutions/43000502593-on-balance-volume-obv/) leaves equal-close bars unchanged; the app chooses an initial zero baseline. [CMF](https://www.tradingview.com/support/solutions/43000501974-chaikin-money-flow-cmf/) uses rolling flow volume divided by rolling total volume. The app uses zero close-location contribution on zero-range bars and null for a zero denominator. These boundary choices are not established by the help articles.

[Session VWAP](https://www.tradingview.com/support/solutions/43000502018-volume-weighted-average-price-vwap/) resets cumulative price-volume and volume at its configured boundary. Exchange sessions can cross midnight; the [session documentation](https://www.tradingview.com/pine-script-docs/concepts/sessions/) distinguishes exchange timezone from chart display timezone. This app requires an instrument calendar and regular/extended choice, or explicit UTC-midnight sessions for 24/7 markets. A truncated session prefix produces null, not a mislabeled full-session VWAP.

[Anchored VWAP](https://www.tradingview.com/support/solutions/43000669764-anchored-vwap-drawing-tool/) starts from a user-selected point and does not reset each day. The app stores the selected bar's open timestamp; arbitrary timestamps snap forward to the first bar opening at or after the anchor. Initial zero volume produces null; later zero-volume bars retain the current average. An anchor selected with hindsight cannot enter an earlier simulated decision.

Volume units and data quality remain provider properties. [Pine's chart-information documentation](https://www.tradingview.com/pine-script-docs/concepts/chart-information/) explicitly notes instrument-dependent units. Tick counts must not be presented as exchange trade volume.

### Remaining definition choices

- **Aroon:** use an `n+1` extreme window and most-recent tie. The [newer official Aroon Oscillator article](https://www.tradingview.com/support/solutions/43000773004-aroon-oscillator/) explicitly supplies the window length; the tie rule remains an app choice.
- **CCI:** use HLC3 by default, following the [worked formula](https://www.tradingview.com/support/solutions/43000502001-commodity-channel-index-cci/). That article's input prose instead says close. Keep source selection explicit.
- **Stochastic RSI:** expose a 0–100 scale, though [support explains the unscaled 0–1 ratio](https://www.tradingview.com/support/solutions/43000502333-stochastic-rsi-stoch-rsi/). Flat RSI range yields null.
- **Historical volatility:** propose log returns, population deviation, a 20-return window, and explicit annualization. [TradingView's retrieved help](https://www.tradingview.com/support/solutions/43000589145-historical-volatility/) is conceptual and does not settle these values. A factor of 252 belongs to a declared daily equity convention; use an explicit 365 for daily 24/7 data, or a justified calendar/frequency factor for other intervals.
- **Null results:** flat RSI, zero-range CCI/Stochastic/Williams %R, no-flow MFI, and zero-volume ratios stay undefined under this contract unless an explicit one-sided limit is specified. No arbitrary epsilon or silent neutral value is inserted.

## Verification and limits

The registry gives targeted cases for all 42 entries. Start with hand-computable vectors: SMA3 on [1,2,3,4] gives [null,null,2,3]; WMA3 on [1,2,3] gives 14/6; VWMA2 on prices [10,20] with volume [1,3] gives 17.5; CCI3 on [1,2,3] gives 100. Check null masks separately from values.

For every indicator, compare batch and incremental calculations, verify the first valid index, insert missing/zero inputs, and append a future suffix while asserting the already-available prefix stays fixed. Calendar fixtures must cover daylight saving changes, overnight sessions, holidays, missing session prefixes, and regular/extended choices. Replay and backtests must consume the same source-time arrays as charts.

Independent full-precision golden vectors are still needed. Cross-platform differences must be classified by seed, source price, window membership, variance divisor, corporate-action adjustment, history preload, session, volume type, or display offset before changing formulas. The same function called twice is not an independent numerical reference.

The public Pine reference pages exposed only a shell to the text reader, so exact `ta.ema`, `ta.rma`, `ta.alma`, and other internal details were not verified through that route. The JSON lists this limit and preserves URLs for all consulted supporting sources. No proprietary implementation source or user account data was used.
