import asyncio
import json
from datetime import UTC, datetime

import httpx
import pytest

from backend.models import Instrument
from backend.providers import HistoryRequest, ProviderConfig, ProviderError, ProviderManager
from backend.store import Store


async def no_wait(seconds):
    pass


def crypto():
    return Instrument(id='COINBASE:BTC-USD', symbol='BTC-USD', name='Bitcoin', exchange='COINBASE',
                      asset_class='crypto', base_currency='BTC', quote_currency='USD',
                      timezone='UTC', calendar='24/7', session='continuous', provider_symbols={'coinbase': 'BTC-USD'})


def provider(tmp_path, handler):
    return ProviderManager(Store(tmp_path), httpx.MockTransport(handler), sleep=no_wait)


@pytest.mark.asyncio
async def test_coinbase_pagination_sort_dedup_and_source(tmp_path):
    calls = []
    start = 1735689600
    rows = [[start + i * 60, 9, 12, 10, 11, 3] for i in range(600)]

    def response(request):
        calls.append(request)
        a = int(datetime.fromisoformat(request.url.params['start']).timestamp())
        b = int(datetime.fromisoformat(request.url.params['end']).timestamp())
        # Coinbase may include an overlap before the requested boundary.
        return httpx.Response(200, json=[r for r in reversed(rows) if a - 60 <= r[0] <= b])

    p = provider(tmp_path, response)
    try:
        meta = await p.history(HistoryRequest(provider='coinbase', instrument=crypto(), interval='1m', start=start, end=start + 600 * 60))
        bars = p.store.bars(meta.id)
        assert len(calls) == 3 and len(bars) == 600
        assert bars[0].start == start and bars[-1].start == start + 599 * 60
        assert meta.source == 'coinbase' and meta.feed == 'exchange' and meta.adjustment == 'raw'
    finally:
        await p.close()


@pytest.mark.asyncio
async def test_throttle_has_bounded_retries_and_no_provider_body_disclosure(tmp_path):
    calls = []

    def response(request):
        calls.append(request)
        return httpx.Response(429, json={'secret': 'do-not-echo'}, headers={'Retry-After': '0'})

    p = provider(tmp_path, response)
    try:
        with pytest.raises(ProviderError) as error:
            await p.get_json('coinbase', 'https://api.exchange.coinbase.com/products')
        assert len(calls) == 3 and error.value.code == 'throttled'
        assert 'do-not-echo' not in str(error.value)
    finally:
        await p.close()


@pytest.mark.asyncio
async def test_missing_and_invalid_credentials_preserve_local_cache(tmp_path):
    p = provider(tmp_path, lambda request: httpx.Response(401, json={'message': 'no'}))
    try:
        with pytest.raises(ProviderError, match='Configure'):
            p.alpaca_headers()
        p.configure('alpaca', ProviderConfig(api_key='fake-key', secret_key='fake-secret'))
        assert 'fake-secret' not in json.dumps([c.model_dump() for c in p.capabilities()])
        with pytest.raises(ProviderError) as error:
            await p.instruments('alpaca')
        assert error.value.code == 'authentication'
        assert p.store.datasets() == []
        assert p.key_path.stat().st_mode & 0o777 == 0o600
    finally:
        await p.close()


@pytest.mark.asyncio
async def test_alpaca_page_tokens_and_new_york_daily_availability(tmp_path):
    requests = []

    def response(request):
        requests.append(request)
        assert request.headers['APCA-API-KEY-ID'] == 'fake-key'
        assert request.url.params['feed'] == 'iex'
        page2 = request.url.params.get('page_token') == 'next'
        return httpx.Response(200, json={'bars': {'AAPL': [{'t': '2025-03-10T04:00:00Z' if page2 else '2025-03-07T05:00:00Z',
                                                         'o': 10, 'h': 12, 'l': 9, 'c': 11, 'v': 100}]},
                                       'next_page_token': None if page2 else 'next'})

    p = provider(tmp_path, response)
    p.configure('alpaca', ProviderConfig(api_key='fake-key', secret_key='fake-secret'))
    inst = Instrument(id='ALPACA:TEST', symbol='AAPL', name='Fixture', exchange='NASDAQ', asset_class='equity',
                      quote_currency='USD', timezone='America/New_York', calendar='XNYS', session='provider-day',
                      provider_symbols={'alpaca': 'AAPL'})
    try:
        meta = await p.history(HistoryRequest(provider='alpaca', instrument=inst, interval='1d', start=1741219200, end=1741737600))
        bars = p.store.bars(meta.id)
        assert len(requests) == 2 and len(bars) == 2
        assert datetime.fromtimestamp(bars[0].start, UTC).hour == 5
        assert datetime.fromtimestamp(bars[1].start, UTC).hour == 4
        assert bars[1].end - bars[1].start == 86400
    finally:
        await p.close()


@pytest.mark.asyncio
async def test_av_quota_does_not_retry_daily_budget(tmp_path):
    count = 0

    def response(request):
        nonlocal count
        count += 1
        return httpx.Response(200, json={'Information': 'quota message with a fake-key'})

    p = provider(tmp_path, response)
    try:
        with pytest.raises(ProviderError) as error:
            await p.get_json('alpha-vantage', 'https://www.alphavantage.co/query')
        assert count == 1 and error.value.code == 'quota' and 'fake-key' not in str(error.value)
    finally:
        await p.close()


@pytest.mark.asyncio
async def test_cancel_interrupts_inflight_provider_request(tmp_path):
    entered, cancelled = asyncio.Event(), asyncio.Event()

    async def response(request):
        entered.set()
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    p = provider(tmp_path, response)
    try:
        task = asyncio.create_task(p.get_json('coinbase', 'https://api.exchange.coinbase.com/products'))
        await asyncio.wait_for(entered.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert cancelled.is_set()
    finally:
        await p.close()


@pytest.mark.asyncio
async def test_bad_provider_rows_not_persisted(tmp_path):
    p = provider(tmp_path, lambda request: httpx.Response(200, json=[[1735689600, 15, 12, 10, 11, 3]]))
    try:
        with pytest.raises(ProviderError, match='validation'):
            await p.history(HistoryRequest(provider='coinbase', instrument=crypto(), interval='1d', start=1735689600, end=1735776000))
        assert p.store.datasets() == []
    finally:
        await p.close()


@pytest.mark.asyncio
async def test_long_security_name_does_not_block_instrument_directory(tmp_path):
    long_name = ('Example Holding Ltd. Depositary Shares Each Representing a 1/1,000th Interest '
                 'in a 6.35% Fixed-to-Floating Rate Perpetual Non-Cumulative Preference Share, Series A')
    assert len(long_name) > 160
    rows = [{'id': 'preferred', 'symbol': 'EXAMPLE-A', 'name': long_name, 'exchange': 'NYSE',
             'status': 'active'}, {'id': 'aapl', 'symbol': 'AAPL', 'name': 'Apple Inc.',
                                  'exchange': 'NASDAQ', 'status': 'active'}]
    p = provider(tmp_path, lambda request: httpx.Response(200, json=rows))
    p.configure('alpaca', ProviderConfig(api_key='fake-key', secret_key='fake-secret'))
    try:
        assert (await p.instruments('alpaca', 'AAPL'))[0].symbol == 'AAPL'
        assert (await p.instruments('alpaca', 'EXAMPLE-A'))[0].name == long_name
        assert p.store.get_document('provider-instruments', 'alpaca')['instruments'][0]['name'] == long_name
    finally:
        await p.close()
