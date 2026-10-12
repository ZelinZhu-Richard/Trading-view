"""Owned, shared completed-candle refresh using documented provider history.

Browser interests live only as long as their socket; enabled alerts and paper
accounts remain active while the local service runs. Research snapshots never move.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
from uuid import uuid4

from .models import CandleStatus, Dataset, utc_now
from .providers import HistoryRequest, ProviderError, ProviderManager
from .store import Store

PROVIDERS = {'coinbase', 'alpaca', 'alpha-vantage'}


def series_key(dataset: Dataset) -> str:
    fields = [dataset.instrument.model_dump(mode='json'), dataset.interval, dataset.source,
              dataset.feed, dataset.adjustment, dataset.first_start]
    return hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()


class CandleService:
    def __init__(self, store: Store, providers: ProviderManager, clock=time.time):
        self.store, self.providers, self.clock = store, providers, clock
        self.consumers: dict[str, list[str]] = {}
        self.states: dict[str, CandleStatus] = {}
        self.tasks: dict[str, asyncio.Task] = {}
        self.loop_task = None
        self.error = None
        self.stopping = False
        self.failures = {}
        self.scan_after = 0
        self.background = []
        self.io_tasks = set()

    def start(self):
        self.stopping = False
        self.loop_task = asyncio.create_task(self._loop(), name='completed-candle-refresh')

    async def close(self):
        self.stopping = True
        if self.loop_task:
            self.loop_task.cancel()
            await asyncio.gather(self.loop_task, return_exceptions=True)
            self.loop_task = None
        for task in self.tasks.values():
            task.cancel()
        await asyncio.gather(*self.tasks.values(), return_exceptions=True)
        self.tasks.clear()
        self.consumers.clear()
        await asyncio.gather(*self.io_tasks, return_exceptions=True)
        for state in self.states.values():
            state.active = False

    async def _io(self, fn, *args):
        task = asyncio.create_task(asyncio.to_thread(fn, *args))
        self.io_tasks.add(task)
        task.add_done_callback(self.io_tasks.discard)
        return await asyncio.shield(task)

    def subscribe(self, identities):
        if not isinstance(identities, list) or len(identities) > 4 or any(not isinstance(i, str) for i in identities):
            raise ValueError('Choose up to four visible candle datasets')
        for identity in identities:
            self._validate(self.store.dataset(identity))
        token = str(uuid4())
        self.consumers[token] = list(dict.fromkeys(identities))
        return token

    def unsubscribe(self, token):
        self.consumers.pop(token, None)

    @staticmethod
    def _validate(dataset):
        if dataset.source not in PROVIDERS or dataset.source not in dataset.instrument.provider_symbols:
            raise ValueError('This dataset has no supported provider connection; imported history stays fixed')
        if dataset.adjustment != 'raw':
            raise ValueError('Automatic refresh supports the raw provider feeds only')

    def _background_interests(self):
        identities = []
        for alert in self.store.list_documents('alert'):
            if alert['enabled']:
                with self.store.connect() as db:
                    row = db.execute('SELECT body FROM alert_states WHERE id=?', (alert['id'],)).fetchone()
                state = json.loads(row[0]) if row else None
                if state and state['fired'] and not alert['recurring']:
                    continue
                identities.append(alert['dataset_id'])
        for account in self.store.list_documents('paper-account'):
            if account['mode'] == 'paper' and not account.get('paused', False):
                identities.extend(account['dataset_ids'])
        return list(dict.fromkeys(identities))

    def _state(self, dataset):
        key = series_key(dataset)
        if key not in self.states:
            saved = self.store.get_document('candle-state', key)
            state = CandleStatus.model_validate(saved['state']) if saved else CandleStatus(
                series_id=key, dataset=dataset, status='waiting', message='Waiting for the next provider check.')
            # Persisted success does not assert this process is connected.
            state.status = 'waiting'
            state.active = False
            self.states[key] = state
        state = self.states[key]
        if (dataset.last_end, dataset.created_at) > (state.dataset.last_end, state.dataset.created_at):
            state.dataset = dataset
        return state

    def status(self, identities):
        return {identity: self._state(self.store.dataset(identity)).model_copy(deep=True) for identity in identities}

    def _persist(self, state):
        saved = self.store.get_document('candle-state', state.series_id)
        self.store.save_document('candle-state', state.series_id, {'state': state.model_dump(mode='json')},
                                 saved['revision'] if saved else 0)

    async def _loop(self):
        while True:
            try:
                await self.cycle()
                self.error = None
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 -- supervise and expose service failures
                self.error = f'Candle refresh failed: {type(exc).__name__}: {exc}'
            await asyncio.sleep(1)

    async def cycle(self):
        now = self.clock()
        if now >= self.scan_after:
            self.background = self._background_interests()
            self.scan_after = now + 2
        active = {}
        for identity in [*self.background, *(i for values in self.consumers.values() for i in values)]:
            dataset = self.store.dataset(identity)
            if dataset.source in PROVIDERS and dataset.adjustment == 'raw':
                self._validate(dataset)
                active[series_key(dataset)] = self._state(dataset)
        for key, state in self.states.items():
            state.active = key in active
        for key, task in list(self.tasks.items()):
            if key not in active:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                del self.tasks[key]
            elif task.done():
                del self.tasks[key]
                await task
        for key, state in active.items():
            if key not in self.tasks and now >= state.next_check:
                self.tasks[key] = asyncio.create_task(self.refresh(state.dataset), name=f'candles-{key[:12]}')

    async def refresh(self, dataset):
        self._validate(dataset)
        state = self._state(dataset)
        previous = state.dataset
        provider = previous.source
        normal_delay = 86400 if provider == 'alpha-vantage' else 30
        state.status = 'updating'
        state.message = 'Checking completed source candles…'
        try:
            # Revisit two whole target buckets to reconcile recent corrections.
            old = await self._io(self.store.bars, previous.id)
            start = old[max(0, len(old)-2)].start
            now = int(self.clock())
            # Bound each catch-up batch. Target monthly/weekly buckets need their full span.
            span = 370*86400 if previous.interval in ('1w', '1mo') else 90*86400 if previous.interval == '1d' else 7*86400
            end = min(now, max(start+span, old[-1].end+1))
            if end <= start:
                raise ProviderError(provider, 'future', 'This dataset starts in the future; waiting for its source interval.')
            instrument, fetched, limitations = await self.providers.fetch_history(HistoryRequest(
                provider=provider, instrument=previous.instrument, interval=previous.interval, start=start, end=end))
            if instrument != previous.instrument or any((b.source, b.feed, b.adjustment) !=
                (previous.source, previous.feed, previous.adjustment) for b in fetched):
                raise ValueError('Provider metadata changed; the original feed and history were retained')
            completed = [bar for bar in fetched if bar.complete and bar.end <= now]
            # An incomplete current bucket is never relabeled complete just because time passed.
            # Only source-returned complete bars replace the queried completed window.
            boundary = max((bar.end for bar in completed), default=start)
            merged = [bar for bar in old if bar.start < start or bar.start >= boundary]
            records = {bar.start: bar for bar in merged}
            records.update((bar.start, bar) for bar in completed)
            merged = sorted(records.values(), key=lambda bar: bar.start)
            if merged and merged[0].start != previous.first_start:
                raise ValueError('Provider removed the beginning of the saved history; review a fresh import before following it')
            revised = any(bar.complete and bar.end <= boundary and records.get(bar.start) != bar for bar in old)
            if completed and merged != old:
                state.dataset = await self._io(self.store.save_dataset, instrument, previous.interval, merged,
                    list(dict.fromkeys([*limitations, 'Automatic completed-candle refresh. Partial candles stay as last imported until their completed source bar arrives.',
                        *(['Provider revised previously completed history; existing alerts and paper accounts require review.'] if revised else [])])), previous.id)
            state.status = 'current' if end >= now else 'catching-up'
            state.message = ('Completed source candles checked; no bars are invented for closed or empty intervals.' if end >= now
                             else 'Catching up saved history in bounded batches.')
            state.revised_history = state.revised_history or revised
            state.last_success = utc_now()
            state.next_check = self.clock() + normal_delay
            self.failures[state.series_id] = 0
        except ProviderError as exc:
            # Empty windows can be legitimate closed/no-tick sessions, but do not claim a fresh price.
            state.status = 'waiting' if exc.code == 'empty' else 'stale'
            state.message = str(exc)
            self.failures[state.series_id] = self.failures.get(state.series_id, 0)+1
            delay = max(normal_delay, min(900, 30*2**min(self.failures[state.series_id], 5)))
            if exc.code in ('quota', 'not-configured', 'authentication'):
                delay = 86400 if provider == 'alpha-vantage' else 300
            state.next_check = self.clock()+delay
        except asyncio.CancelledError:
            state.status = 'waiting'
            state.message = 'Refresh stopped; cached candles remain available.'
            raise
        except Exception as exc:  # noqa: BLE001 -- preserve cached data and surface a failed reconciliation
            state.status, state.message = 'stale', f'Candle update rejected: {type(exc).__name__}: {exc}'
            state.next_check = self.clock()+300
        self._persist(state)
        return state.model_copy(deep=True)
