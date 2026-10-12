"""Shared quote connections with explicit ownership and bounded reconnects."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from uuid import uuid4

import pandas as pd
from websockets.asyncio.client import connect
from websockets.exceptions import WebSocketException

from .models import Instrument, Quote
from .providers import ProviderError, ProviderManager

logging.getLogger('websockets').setLevel(logging.WARNING)


class QuoteHub:
    def __init__(self, providers: ProviderManager, connector=connect, sleep=asyncio.sleep):
        self.providers = providers
        self.connector, self.sleep = connector, sleep
        self.listeners: dict[str, tuple[str, Instrument, asyncio.Queue]] = {}
        self.tasks: dict[str, asyncio.Task] = {}
        self.last: dict[str, Quote] = {}

    async def subscribe(self, provider: str, instrument: Instrument):
        if provider not in ('coinbase', 'alpaca') or provider not in instrument.provider_symbols:
            raise ProviderError(provider, 'capability', 'A quote stream is unavailable for this provider/instrument.')
        if provider == 'alpaca':
            self.providers.require_keys(provider)
        token, queue = uuid4().hex, asyncio.Queue(maxsize=8)
        self.listeners[token] = (provider, instrument, queue)
        queue.put_nowait({'type': 'status', 'status': 'connecting'})
        if instrument.id in self.last:
            value = self.last[instrument.id].model_copy(update={'freshness': 'stale'})
            queue.put_nowait({'type': 'quote', 'quote': value.model_dump(mode='json')})
        if provider not in self.tasks or self.tasks[provider].done():
            self.tasks[provider] = asyncio.create_task(self._run(provider))
        return token, queue

    async def unsubscribe(self, token: str):
        removed = self.listeners.pop(token, None)
        if removed and not self._instruments(removed[0]):
            task = self.tasks.pop(removed[0], None)
            if task:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    async def close(self):
        self.listeners.clear()
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.tasks.clear()

    def _instruments(self, provider):
        return {instrument.provider_symbols[provider]: instrument
                for p, instrument, _ in self.listeners.values() if p == provider}

    def _broadcast(self, provider, message, instrument_id=None):
        for p, instrument, queue in self.listeners.values():
            if p == provider and (instrument_id is None or instrument.id == instrument_id):
                # Quotes are state updates, not an execution tape. Keep the latest state for slow clients.
                if queue.full():
                    queue.get_nowait()
                queue.put_nowait(message)

    async def _run(self, provider):
        endpoint = {'coinbase': 'wss://ws-feed.exchange.coinbase.com',
                    'alpaca': 'wss://stream.data.alpaca.markets/v2/iex'}[provider]
        for attempt in range(5):
            if not self._instruments(provider):
                return
            try:
                async with self.connector(endpoint, open_timeout=10, close_timeout=2, ping_interval=20,
                                          ping_timeout=20, max_size=4_000_000) as socket:
                    if provider == 'alpaca':
                        await asyncio.wait_for(socket.recv(), 10)  # Initial connected message.
                        keys = self.providers.require_keys(provider)
                        await socket.send(json.dumps({'action': 'auth', 'key': keys['api_key'], 'secret': keys['secret_key']}))
                        reply = json.loads(await asyncio.wait_for(socket.recv(), 10))
                        if not isinstance(reply, list) or not any(r.get('T') == 'success' and r.get('msg') == 'authenticated' for r in reply):
                            raise ProviderError(provider, 'authentication', 'Alpaca streaming authentication was rejected.')
                    subscribed: set[str] = set()
                    self.providers.states[provider] = 'connected'
                    self._broadcast(provider, {'type': 'status', 'status': 'connected', 'reconnect_attempt': attempt})
                    last_received = time.monotonic()
                    while self._instruments(provider):
                        wanted = set(self._instruments(provider))
                        for action, symbols in [('subscribe', wanted - subscribed), ('unsubscribe', subscribed - wanted)]:
                            if symbols:
                                message = ({'type': action, 'product_ids': sorted(symbols), 'channels': ['ticker', 'heartbeat']}
                                           if provider == 'coinbase' else {'action': action, 'trades': sorted(symbols)})
                                await socket.send(json.dumps(message))
                        subscribed = wanted
                        try:
                            raw = await asyncio.wait_for(socket.recv(), timeout=1)
                        except TimeoutError:
                            if provider == 'coinbase' and time.monotonic() - last_received > 30:
                                raise ProviderError(provider, 'stale', 'Coinbase stream heartbeat timed out.')
                            continue
                        last_received = time.monotonic()
                        messages = json.loads(raw)
                        if provider == 'coinbase':
                            messages = [messages]
                        if not isinstance(messages, list):
                            raise ProviderError(provider, 'response', 'Unexpected stream message shape.')
                        for message in messages:
                            kind = message.get('type') if provider == 'coinbase' else message.get('T')
                            if kind == 'error':
                                raise ProviderError(provider, 'subscription', 'Provider rejected a quote subscription; check limits and availability.')
                            if kind not in ('ticker', 't'):
                                continue
                            symbol = message.get('product_id') if provider == 'coinbase' else message.get('S')
                            instrument = self._instruments(provider).get(symbol)
                            if instrument is None:
                                continue
                            timestamp = int(pd.Timestamp(message['time'] if provider == 'coinbase' else message['t']).timestamp())
                            quote = Quote(instrument_id=instrument.id,
                                          price=message['price'] if provider == 'coinbase' else message['p'],
                                          timestamp=timestamp, source=provider,
                                          feed='exchange' if provider == 'coinbase' else 'iex',
                                          freshness='live' if time.time() - timestamp <= 90 else 'stale')
                            previous = self.last.get(instrument.id)
                            if previous and quote.timestamp < previous.timestamp:
                                continue
                            self.last[instrument.id] = quote
                            self._broadcast(provider, {'type': 'quote', 'quote': quote.model_dump(mode='json')}, instrument.id)
            except asyncio.CancelledError:
                raise
            except (OSError, TimeoutError, WebSocketException, ValueError, KeyError, TypeError):
                self.providers.states[provider] = 'disconnected'
                status = 'disconnected' if attempt == 4 else 'reconnecting'
                self._broadcast(provider, {'type': 'status', 'status': status, 'reconnect_attempt': attempt + 1,
                                           'detail': 'Quote connection unavailable; retained prices are stale.'})
                for symbol, quote in list(self.last.items()):
                    if quote.source == provider:
                        self.last[symbol] = quote.model_copy(update={'freshness': 'stale'})
                        self._broadcast(provider, {'type': 'quote', 'quote': self.last[symbol].model_dump(mode='json')}, symbol)
                if attempt < 4:
                    await self.sleep(min(2 ** attempt, 15))
