import asyncio
import json

import pytest

from backend.models import Instrument
from backend.providers import ProviderManager
from backend.store import Store
from backend.streams import QuoteHub


class FakeSocket:
    def __init__(self):
        self.sent = []
        self.incoming = asyncio.Queue()
        self.closed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.closed = True

    async def send(self, message):
        self.sent.append(json.loads(message))

    async def recv(self):
        return await self.incoming.get()


@pytest.mark.asyncio
async def test_duplicate_quote_subscriptions_share_connection_and_cleanup(tmp_path):
    socket, connections = FakeSocket(), []

    def connect(*args, **kwargs):
        connections.append(args[0])
        return socket

    providers = ProviderManager(Store(tmp_path))
    hub = QuoteHub(providers, connector=connect)
    instrument = Instrument(id='COINBASE:BTC-USD', symbol='BTC-USD', name='Bitcoin', exchange='COINBASE',
                            asset_class='crypto', quote_currency='USD', timezone='UTC', provider_symbols={'coinbase': 'BTC-USD'})
    try:
        first, queue1 = await hub.subscribe('coinbase', instrument)
        second, queue2 = await hub.subscribe('coinbase', instrument)
        await socket.incoming.put(json.dumps({'type': 'ticker', 'product_id': 'BTC-USD',
                                             'price': '100', 'time': '2025-01-01T00:00:00Z'}))
        async def quote(queue):
            while True:
                message = await queue.get()
                if message['type'] == 'quote':
                    return message
        a, b = await asyncio.wait_for(asyncio.gather(quote(queue1), quote(queue2)), 2)
        assert a['quote']['price'] == b['quote']['price'] == 100
        assert a['quote']['freshness'] == 'stale'
        assert len(connections) == 1
        assert socket.sent == [{'type': 'subscribe', 'product_ids': ['BTC-USD'], 'channels': ['ticker', 'heartbeat']}]
        await hub.unsubscribe(first)
        assert not socket.closed
        await hub.unsubscribe(second)
        assert socket.closed and not hub.tasks and not hub.listeners
    finally:
        await hub.close()
        await providers.close()
