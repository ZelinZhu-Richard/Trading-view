"""Documented market-data endpoints only. This module never submits orders."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import UTC, datetime
from typing import Literal

import httpx
import pandas as pd
from pydantic import SecretStr, model_validator

from .models import Bar, Contract, Instrument, Interval, ProviderCapabilities, Quote
from .normalization import SECONDS, aggregate, bar_window
from .store import Store, atomic_write

ProviderID = Literal['alpaca', 'coinbase', 'alpha-vantage']
ALL_INTERVALS = ['1m', '5m', '15m', '30m', '1h', '4h', '1d', '1w', '1mo']
logging.getLogger('httpx').setLevel(logging.WARNING)  # URLs can contain AV credentials.


class ProviderError(ValueError):
    def __init__(self, provider: str, code: str, message: str):
        super().__init__(message)
        self.provider, self.code = provider, code


class ProviderConfig(Contract):
    api_key: SecretStr
    secret_key: SecretStr | None = None


class HistoryRequest(Contract):
    provider: ProviderID
    instrument: Instrument
    interval: Interval
    start: int
    end: int

    @model_validator(mode='after')
    def ordered_dates(self):
        if self.end <= self.start:
            raise ValueError('History end must follow start')
        if self.provider not in self.instrument.provider_symbols:
            raise ValueError('Instrument has no mapping for this provider')
        return self


class ProviderManager:
    def __init__(self, store: Store, transport=None, sleep=asyncio.sleep):
        self.store = store
        self.key_path = store.root / 'provider-keys.json'
        self.keys = json.loads(self.key_path.read_text()) if self.key_path.exists() else {}
        self.client = httpx.AsyncClient(timeout=20, transport=transport,
                                       headers={'User-Agent': 'MarketWorkbench/0.1'})
        self.sleep = sleep
        self.locks = {p: asyncio.Lock() for p in ('alpaca', 'coinbase', 'alpha-vantage')}
        self.next_request = {p: 0.0 for p in self.locks}
        self.states = {p: 'available' for p in self.locks}

    async def close(self):
        await self.client.aclose()

    def configure(self, provider: ProviderID, value: ProviderConfig):
        if provider == 'coinbase':
            raise ValueError('Coinbase public market data does not need a key')
        if provider == 'alpaca' and not value.secret_key:
            raise ValueError('Alpaca requires both an API key and a secret key')
        self.keys[provider] = {'api_key': value.api_key.get_secret_value(),
                               'secret_key': value.secret_key.get_secret_value() if value.secret_key else ''}
        atomic_write(self.key_path, json.dumps(self.keys))
        self.key_path.chmod(0o600)
        self.states[provider] = 'available'

    def remove_keys(self, provider: ProviderID):
        self.keys.pop(provider, None)
        atomic_write(self.key_path, json.dumps(self.keys))
        self.key_path.chmod(0o600)

    def capabilities(self) -> list[ProviderCapabilities]:
        details = [
            ('alpaca', 'Alpaca Basic', ['US stocks', 'US ETFs'], ALL_INTERVALS, True, True,
             'History returned by the IEX feed, subject to account entitlement.',
             ['IEX coverage only; not consolidated US market volume.',
              'Daily provider bars use New York day buckets. Intraday imports retain regular-session minutes only.',
              'Free account keys required. Corporate actions are not automatically supplied.']),
            ('coinbase', 'Coinbase Exchange', ['Crypto'], ALL_INTERVALS, True, False,
             'Public candle history; requests are paged in blocks of at most 300 buckets.',
             ['Coinbase venue only. No candle is returned for an interval without ticks.',
              '30-minute and 4-hour bars are locally derived. Some history may be incomplete.']),
            ('alpha-vantage', 'Alpha Vantage', ['Forex'], ['1d', '1w', '1mo'], False, True,
             'FX_DAILY full history, with locally derived weekly and monthly bars.',
             ['Free daily quota applies. No free intraday forex connection.',
              'Forex volume is unavailable. Daily bars use the provider-reported timezone.']),
        ]
        return [ProviderCapabilities(id=p, name=n, markets=m, intervals=i, streaming=s, requires_keys=k,
                                     history=h, limitations=l,
                                     status='not-configured' if k and not self.keys.get(p) else self.states[p])
                for p, n, m, i, s, k, h, l in details]

    def require_keys(self, provider):
        keys = self.keys.get(provider)
        if not keys or not keys.get('api_key'):
            raise ProviderError(provider, 'not-configured', f'Configure {provider} keys locally before connecting.')
        return keys

    async def get_json(self, provider, url, *, params=None, headers=None):
        # One bounded request stream per provider; cancellation interrupts waits and HTTP I/O.
        async with self.locks[provider]:
            remaining = self.next_request[provider] - time.monotonic()
            if remaining > 0:
                await self.sleep(remaining)
            spacing = {'coinbase': .15, 'alpaca': .35, 'alpha-vantage': 12.1}[provider]
            for attempt in range(3):
                try:
                    response = await self.client.get(url, params=params, headers=headers)
                except httpx.RequestError:
                    self.states[provider] = 'disconnected'
                    if attempt == 2:
                        raise ProviderError(provider, 'connection', f'{provider} could not be reached. Cached datasets remain available.') from None
                    await self.sleep(2 ** attempt)
                    continue
                finally:
                    self.next_request[provider] = time.monotonic() + spacing
                if response.status_code in (401, 403):
                    self.states[provider] = 'disconnected'
                    raise ProviderError(provider, 'authentication', 'Provider rejected the credentials or feed entitlement.')
                if response.status_code == 404:
                    raise ProviderError(provider, 'not-found', 'This instrument is unavailable at the selected provider.')
                if response.status_code == 429 or response.status_code >= 500:
                    self.states[provider] = 'throttled' if response.status_code == 429 else 'disconnected'
                    if attempt == 2:
                        raise ProviderError(provider, 'throttled' if response.status_code == 429 else 'unavailable',
                                            'Provider limit or service outage. Try later; cached data is preserved.')
                    try:
                        retry_after = float(response.headers.get('Retry-After', 2 ** attempt))
                    except ValueError:
                        retry_after = 2 ** attempt
                    await self.sleep(min(15, max(.25, retry_after)))
                    continue
                if response.is_error:
                    raise ProviderError(provider, 'request', f'Provider rejected the market-data request (HTTP {response.status_code}).')
                try:
                    body = response.json()
                except ValueError:
                    raise ProviderError(provider, 'response', 'Provider returned an invalid JSON response.') from None
                if provider == 'alpha-vantage':
                    if not isinstance(body, dict):
                        raise ProviderError(provider, 'response', 'Provider returned an unexpected response.')
                    if 'Information' in body or 'Note' in body:
                        self.states[provider] = 'throttled'
                        raise ProviderError(provider, 'quota', 'Alpha Vantage quota or endpoint entitlement prevented this request. No automatic quota retries were made.')
                    if 'Error Message' in body:
                        raise ProviderError(provider, 'request', 'Alpha Vantage could not return this currency pair.')
                self.states[provider] = 'connected'
                return body

    def alpaca_headers(self):
        keys = self.require_keys('alpaca')
        return {'APCA-API-KEY-ID': keys['api_key'], 'APCA-API-SECRET-KEY': keys.get('secret_key', '')}

    async def instruments(self, provider: ProviderID, query: str = '') -> list[Instrument]:
        cached = self.store.get_document('provider-instruments', provider)
        if cached and time.time() - cached['fetched_at'] < 86400:
            values = [Instrument.model_validate(v) for v in cached['instruments']]
        else:
            try:
                values = await self._instruments(provider)
            except ProviderError:
                if not cached:
                    raise
                values = [Instrument.model_validate(v) for v in cached['instruments']]
            else:
                self.store.save_document('provider-instruments', provider,
                                         {'fetched_at': time.time(), 'instruments': [v.model_dump(mode='json') for v in values]},
                                         cached['revision'] if cached else 0)
        q = query.upper().strip()
        return [v for v in values if q in f'{v.symbol} {v.name} {v.exchange}'.upper()][:100]

    async def _instruments(self, provider):
        if provider == 'coinbase':
            body = await self.get_json(provider, 'https://api.exchange.coinbase.com/products')
            if not isinstance(body, list):
                raise ProviderError(provider, 'response', 'Coinbase product response has an unexpected shape.')
            return [Instrument(id=f'COINBASE:{p["id"]}', symbol=p['id'], name=p.get('display_name', p['id']),
                               exchange='COINBASE', asset_class='crypto', base_currency=p['base_currency'],
                               quote_currency=p['quote_currency'], timezone='UTC', calendar='24/7', session='continuous',
                               price_tick=p['quote_increment'], quantity_step=p['base_increment'],
                               provider_symbols={provider: p['id']}) for p in body if p.get('status') == 'online']
        if provider == 'alpaca':
            body = await self.get_json(provider, 'https://paper-api.alpaca.markets/v2/assets',
                                       params={'status': 'active', 'asset_class': 'us_equity'}, headers=self.alpaca_headers())
            if not isinstance(body, list):
                raise ProviderError(provider, 'response', 'Alpaca asset response has an unexpected shape.')
            return [Instrument(id=f'ALPACA:{p["id"]}', symbol=p['symbol'], name=p['name'],
                               exchange=p['exchange'], asset_class='equity', quote_currency='USD',
                               timezone='America/New_York', calendar='XNYS', session='provider-day',
                               price_tick='.01', quantity_step='.000000001' if p.get('fractionable') else '1',
                               provider_symbols={provider: p['symbol']}) for p in body if p.get('status') == 'active']
        # Common pairs are an explicitly labeled local directory, not a provider discovery claim.
        currencies = ['USD', 'EUR', 'GBP', 'JPY', 'CHF', 'CAD', 'AUD', 'NZD', 'CNY', 'HKD', 'SGD']
        return [Instrument(id=f'FX:{a}{b}', symbol=f'{a}/{b}', name=f'{a} / {b}', exchange='FOREX',
                           asset_class='forex', base_currency=a, quote_currency=b, timezone='UTC',
                           calendar='24/5', session='provider-day', price_tick='.00001', quantity_step='1',
                           provider_symbols={provider: f'{a}/{b}'}) for a in currencies for b in currencies if a != b]

    async def history(self, request: HistoryRequest):
        try:
            return await self._history(request)
        except ProviderError:
            raise
        except (ValueError, KeyError, TypeError, IndexError):
            raise ProviderError(request.provider, 'response', 'Provider data failed validation; no resulting dataset was committed.') from None

    async def fetch_history(self, request: HistoryRequest):
        try:
            return await self._history(request, commit=False)
        except ProviderError:
            raise
        except (ValueError, KeyError, TypeError, IndexError):
            raise ProviderError(request.provider, 'response', 'Provider candle data failed validation; cached history was retained.') from None

    async def _history(self, request: HistoryRequest, *, commit=True):
        provider, instrument = request.provider, request.instrument
        cap = next(c for c in self.capabilities() if c.id == provider)
        if request.interval not in cap.intervals:
            raise ProviderError(provider, 'interval', 'This provider does not support the requested interval on the free baseline.')
        limitations = list(cap.limitations)
        if provider == 'coinbase':
            base_interval = {'30m': '15m', '4h': '1h', '1w': '1d', '1mo': '1d'}.get(request.interval, request.interval)
            seconds = SECONDS[base_interval]
            records = {}
            cursor = request.start
            while cursor < request.end:
                end = min(cursor + seconds * 299, request.end)
                body = await self.get_json(provider,
                    f'https://api.exchange.coinbase.com/products/{instrument.provider_symbols[provider]}/candles',
                    params={'start': iso(cursor), 'end': iso(end), 'granularity': seconds})
                if not isinstance(body, list):
                    raise ProviderError(provider, 'response', 'Coinbase candles have an unexpected shape.')
                for row in body:
                    if not isinstance(row, list) or len(row) != 6:
                        raise ProviderError(provider, 'response', 'Coinbase candle row has an unexpected shape.')
                    t, low, high, op, cl, volume = row
                    if request.start <= t < request.end:
                        add_unique(records, Bar(start=t, end=t + seconds, open=op, high=high, low=low,
                                                close=cl, volume=volume, complete=t + seconds <= time.time(),
                                                source=provider, feed='exchange', adjustment='raw'))
                cursor = end
            bars = sorted(records.values(), key=lambda b: b.start)
        elif provider == 'alpaca':
            base_interval = '1d' if request.interval in ('1d', '1w', '1mo') else '1m'
            params = {'symbols': instrument.provider_symbols[provider], 'timeframe': '1Day' if base_interval == '1d' else '1Min',
                      'start': iso(request.start), 'end': iso(request.end), 'limit': 10000, 'feed': 'iex', 'adjustment': 'raw', 'sort': 'asc'}
            records, pages, excluded = {}, set(), 0
            while True:
                body = await self.get_json(provider, 'https://data.alpaca.markets/v2/stocks/bars', params=params, headers=self.alpaca_headers())
                if not isinstance(body, dict) or not isinstance(body.get('bars'), dict):
                    raise ProviderError(provider, 'response', 'Alpaca bars have an unexpected shape.')
                for row in body['bars'].get(instrument.provider_symbols[provider], []):
                    t = pd.Timestamp(row['t'])
                    try:
                        start, end = bar_window(t, base_interval, instrument)
                    except ValueError:
                        excluded += 1
                        continue
                    if not request.start <= start < request.end:
                        continue
                    add_unique(records, Bar(start=start, end=end, open=row['o'], high=row['h'], low=row['l'],
                                            close=row['c'], volume=row.get('v'), complete=end <= time.time(),
                                            source=provider, feed='iex', adjustment='raw'))
                token = body.get('next_page_token')
                if not token:
                    break
                if token in pages:
                    raise ProviderError(provider, 'pagination', 'Provider repeated its page token; partial history was not committed.')
                pages.add(token)
                params['page_token'] = token
            if excluded:
                limitations.append(f'{excluded} out-of-session minute records excluded; no substitute candles were created.')
            bars = sorted(records.values(), key=lambda b: b.start)
        else:
            base_interval = '1d'
            pair = instrument.provider_symbols[provider].split('/')
            if len(pair) != 2:
                raise ValueError('Forex instrument must map to BASE/QUOTE')
            body = await self.get_json(provider, 'https://www.alphavantage.co/query',
                                       params={'function': 'FX_DAILY', 'from_symbol': pair[0], 'to_symbol': pair[1],
                                               'outputsize': 'full', 'apikey': self.require_keys(provider)['api_key']})
            series = body.get('Time Series FX (Daily)')
            if not isinstance(series, dict):
                raise ProviderError(provider, 'response', 'Alpha Vantage did not return daily FX bars.')
            metadata = body.get('Meta Data', {})
            zone = next((str(v) for k, v in metadata.items() if 'Time Zone' in k), None)
            if not zone:
                raise ProviderError(provider, 'timezone', 'Provider response omitted its daily timezone; timestamps were not guessed.')
            zone = {'GMT': 'UTC', 'US/Eastern': 'America/New_York'}.get(zone, zone)
            instrument = Instrument.model_validate({**instrument.model_dump(), 'timezone': zone})
            bars = []
            for day, row in sorted(series.items()):
                t = pd.Timestamp(day, tz=zone)
                start, end = int(t.timestamp()), int((t + pd.DateOffset(days=1)).timestamp())
                if request.start <= start < request.end:
                    bars.append(Bar(start=start, end=end, open=row['1. open'], high=row['2. high'], low=row['3. low'],
                                    close=row['4. close'], volume=None, complete=end <= time.time(),
                                    source=provider, feed='FX_DAILY', adjustment='raw'))
        if not bars:
            raise ProviderError(provider, 'empty', 'No history was returned for this instrument and date range.')
        if base_interval != request.interval:
            parent = self.store.save_dataset(instrument, base_interval, bars, limitations) if commit else None
            bars = aggregate(bars, base_interval, request.interval, instrument)
            limitations.append(f'Locally aggregated from immutable {base_interval} dataset {parent.id}.' if parent else f'Locally aggregated from documented {base_interval} provider candles.')
        else:
            parent = None
        if any(not b.complete for b in bars):
            limitations.append('Incomplete bars are excluded from completed-bar research. Missing buckets are not filled.')
        if not commit:
            return instrument, bars, limitations
        return self.store.save_dataset(instrument, request.interval, bars, limitations, parent.id if parent else None)

    async def quote(self, provider: ProviderID, instrument: Instrument) -> Quote:
        symbol = instrument.provider_symbols[provider]
        if provider == 'coinbase':
            body = await self.get_json(provider, f'https://api.exchange.coinbase.com/products/{symbol}/ticker')
            timestamp = int(pd.Timestamp(body['time']).timestamp())
            return Quote(instrument_id=instrument.id, price=body['price'], timestamp=timestamp,
                         source=provider, feed='exchange', freshness='live' if time.time() - timestamp <= 90 else 'stale')
        if provider == 'alpaca':
            body = await self.get_json(provider, 'https://data.alpaca.markets/v2/stocks/trades/latest',
                                       params={'symbols': symbol, 'feed': 'iex'}, headers=self.alpaca_headers())
            trade = body.get('trades', {}).get(symbol)
            if not trade:
                raise ProviderError(provider, 'empty', 'No latest IEX trade is available.')
            timestamp = int(pd.Timestamp(trade['t']).timestamp())
            return Quote(instrument_id=instrument.id, price=trade['p'], timestamp=timestamp,
                         source=provider, feed='iex', freshness='live' if time.time() - timestamp <= 90 else 'stale')
        raise ProviderError(provider, 'capability', 'Daily forex history does not provide a live quote subscription.')


def iso(seconds: int) -> str:
    return datetime.fromtimestamp(seconds, UTC).isoformat()


def add_unique(records, bar: Bar):
    previous = records.get(bar.start)
    if previous and previous != bar:
        raise ProviderError(bar.source, 'conflicting-data', 'Provider returned conflicting bars at the same timestamp; partial data was not committed.')
    records[bar.start] = bar
