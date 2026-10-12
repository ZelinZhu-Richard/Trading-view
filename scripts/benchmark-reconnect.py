"""Actual public Coinbase reconnect, induced only on this script's owned socket."""
import asyncio
import json
import os
import platform
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

import psutil
from websockets.asyncio.client import connect

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.providers import ProviderManager
from backend.store import Store, atomic_write
from backend.streams import QuoteHub


async def main():
    root = Path(__file__).resolve().parent.parent
    provider = ProviderManager(Store(root/'data'))
    sockets = []
    statuses = []
    @asynccontextmanager
    async def connector(*args, **kwargs):
        async with connect(*args, **kwargs) as socket:
            sockets.append(socket)
            yield socket
    hub = QuoteHub(provider, connector=connector)
    process = psutil.Process()
    before = process.memory_info().rss
    try:
        instrument = next(i for i in await provider.instruments('coinbase', 'BTC-USD') if i.symbol == 'BTC-USD')
        token, queue = await hub.subscribe('coinbase', instrument)
        async def quote():
            while True:
                event = await queue.get()
                if event['type'] == 'status':
                    statuses.append(event)
                if event['type'] == 'quote' and event['quote']['freshness'] == 'live':
                    return event['quote']
        first = await asyncio.wait_for(quote(), 30)
        start = time.perf_counter()
        await sockets[0].close()
        second = await asyncio.wait_for(quote(), 30)
        duration = time.perf_counter()-start
        if len(sockets) != 2 or not any(s['status']=='reconnecting' for s in statuses):
            raise AssertionError('No genuine reconnect observed')
        await hub.unsubscribe(token)
        report = {'passed': True, 'provider': 'Coinbase public WebSocket', 'induced_failure': 'Closed only the owned client socket; no external network change',
            'reconnect_to_live_quote_seconds': duration, 'connections': len(sockets), 'subscriptions_after_cleanup': len(hub.listeners),
            'tasks_after_cleanup': len(hub.tasks), 'statuses': statuses, 'first_quote_time': first['timestamp'], 'reconnected_quote_time': second['timestamp'],
            'rss_before': before, 'rss_after': process.memory_info().rss, 'memory_scope': 'Python benchmark process endpoints, not peak or full application memory',
            'hardware': {'arch': platform.machine(), 'platform': platform.platform(), 'logical_cores': os.cpu_count(), 'memory': psutil.virtual_memory().total}}
        atomic_write(root/'evidence/performance/reconnect.json', json.dumps(report, indent=2))
        print(json.dumps(report))
    finally:
        await hub.close()
        await provider.close()


asyncio.run(main())
