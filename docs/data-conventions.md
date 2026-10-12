# Data contracts and conventions

All timestamps are UTC epoch seconds. Instrument metadata preserves the exchange
timezone and calendar. Bar `start` is the chart label; `end` is the earliest time
at which this application permits a complete bar to enter completed-bar research.
Provider delays and subsequent revisions are not historical point-in-time archives.
Research snapshots must therefore report this limitation.

CSV has an explicit preview/commit boundary. Missing volume remains null; zero
volume remains zero. NaN/infinite and nonpositive OHLC values are rejected. Low
must not exceed open/close and high must not fall below them. Duplicate timestamps
with identical values are removed; conflicting values require an explicit first/
last policy or correction. Invalid rows prevent commit. No partial import is
silently accepted. Files are parsed using Python's CSV parser, including quoted
fields and BOM handling.

Naive timestamps require an IANA timezone. DST folds and nonexistent local times
are rejected; explicit offsets disambiguate those times. Regular-session intraday
bars are clipped at session closes or lunch breaks. Closed-session timestamps are
rejected. Exchange schedules come from the pinned `exchange-calendars` package;
precomputed calendar coverage bounds are respected. A 24/5 calendar has weekday
rules only, without venue holidays; this limitation is shown in import summaries.

Aggregation never invents missing candles. Intraday buckets begin at the actual
session segment opening. Weekly buckets start Monday; monthly buckets use calendar
months in the instrument's timezone. No finer timeframe is derived from coarser
bars. Bars retain their source/feed/adjustment identity, and incompatible inputs
are rejected. An aggregate with missing source intervals or an incomplete edge is
marked incomplete, with the full target availability boundary retained. This is a
conservative policy: providers can omit intervals with no trades, which also causes
such derived aggregates to be incomplete until a more detailed missingness policy
is implemented. Do not treat an incomplete aggregate as a completed strategy input.

## Provider contracts

- **Coinbase:** public Exchange products, candle history, latest ticker, and ticker
  WebSocket. Candles are explicitly requested in batches below the 300-bucket cap,
  trimmed to the requested range, sorted, and deduplicated. Conflicting duplicates
  reject the request. 30m and 4h are derived from 15m and 1h respectively. See the
  [official candle contract](https://docs.cdp.coinbase.com/api-reference/exchange-api/rest-api/products/get-product-candles)
  and [WebSocket channels](https://docs.cdp.coinbase.com/exchange/websocket-feed/channels).
- **Alpaca:** the feed is always explicitly `iex`, with raw adjustment. Asset
  metadata identifies US equity instruments; the API's `us_equity` category does
  not establish stock-versus-ETF classification, so the model retains `equity`.
  Intraday requests use minute data and retain regular sessions. Daily bars retain
  the provider's New York day bucket and become complete at the next local midnight;
  they are not moved to the regular-session close. The provider uses different
  trade-condition rules for minute and daily bars, so daily OHLC/volume must not be
  claimed identical to an intraday reconstruction. See [historical bars](https://docs.alpaca.markets/us/reference/stockbars)
  and [aggregation rules](https://docs.alpaca.markets/us/docs/market-data-faq).
- **Alpha Vantage:** `FX_DAILY`, full output, no volume. The returned timezone is
  required; unknown/missing timezone is an error. Weekly/monthly bars are local
  aggregations. Search is a local common-pair directory; successful history retrieval
  establishes availability. A quota/information response stops without spending
  additional daily calls on automatic retries. See [FX_DAILY](https://www.alphavantage.co/documentation/#fx-daily).

Transport retries are bounded to three attempts for transient HTTP failures, with
bounded backoff; authentication errors are not retried. Streaming uses one owned
connection per provider, shared across subscribers, and at most five connection
attempts. Unsubscribing the last listener closes the owned connection. Slow clients
receive recent quote state, not a lossless execution tape. Quotes over 90 seconds
old are marked stale. Displayed live quotes do not silently overwrite immutable
historical chart candles.

Keys live in `data/provider-keys.json` with restrictive permissions and are excluded
from workspace exports. They are sent only to the selected documented provider.
Provider responses and error messages containing keys are not relayed. No brokerage
order endpoint exists in the application.

## Verification and limits

Actual configured requests on 2026-10-12 UTC returned 63 daily bars each for Alpaca
AAPL and SPY, and 64 for Alpha Vantage EUR/USD. Each produced 13 weekly and four
monthly aggregates. See `../evidence/configured-providers.json`. Alpaca stream
authentication and unsubscribe passed; no trade arrived during the 20-second
observation, so actual trade delivery remains unverified. Coinbase actual history,
ticker, stream, reconnect, and completed-candle/paper checks have separate evidence.

[Candle updates](candle-updates.md) documents automatic refresh, reconciliation,
quota spacing, and visible stale states. Dataset revisions are not point-in-time
archives. Alpaca equity price ticks use the documented application assumption of
0.01 and quantity step 0.000000001 for fractionable assets (otherwise 1); asset metadata does not prove venue-specific tick
schedules. These limitations remain visible rather than implying exact execution.
