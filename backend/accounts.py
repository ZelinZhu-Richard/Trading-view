"""Persistent replay and paper accounts, backed by the same simulation engine.

Only commands and immutable input identities persist. Rebuilding from those inputs
avoids stale future positions after a seek and avoids incompatible serialized engines.
"""
from __future__ import annotations

import asyncio
import math
import threading
import time
from bisect import bisect_right
from collections import defaultdict
from uuid import uuid4

from .models import DatasetView, utc_now
from .research_models import AccountCommand, AccountRequest, AccountView, PaperAccount
from .simulation import Simulation
from .store import ConflictError, Store


class AccountService:
    def __init__(self, store: Store):
        self.store = store
        self.lock = threading.RLock()
        self.cache = {}
        self.task = None
        self.pending = None
        self.stopping = threading.Event()
        self.error = None

    def start(self):
        self.stopping.clear()
        self.task = asyncio.create_task(self._loop(), name='paper-account-refresh')

    async def _loop(self):
        try:
            while True:
                try:
                    self.pending = asyncio.create_task(asyncio.to_thread(self._refresh_all))
                    await asyncio.shield(self.pending)
                    self.error = None
                except Exception as exc:  # noqa: BLE001 -- supervisor remains available and reports the failure
                    self.error = f'Paper refresh failed: {type(exc).__name__}: {exc}'
                finally:
                    if self.pending and self.pending.done():
                        self.pending = None
                await asyncio.sleep(2)
        except asyncio.CancelledError:
            return

    def _refresh_all(self):
        for account in self.accounts():
            if self.stopping.is_set():
                return
            if account.mode != 'paper' or account.paused:
                continue
            try:
                self.refresh_paper(account.id, account.revision)
            except ConflictError:
                continue  # An interactive command owns the newer revision.
            except Exception as exc:  # noqa: BLE001 -- record the affected account and continue others
                with self.lock:
                    current = self.account(account.id)
                    if current.error != str(exc):
                        current.error = str(exc)
                        self.store.save_document('paper-account', current.id, current.model_dump(mode='json'), current.revision)
                        self.cache.pop(current.id, None)

    async def close(self):
        self.stopping.set()
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
            self.task = None
        if self.pending:
            await asyncio.gather(self.pending, return_exceptions=True)
            self.pending = None

    def accounts(self):
        return [PaperAccount.model_validate(value) for value in self.store.list_documents('paper-account')]

    def account(self, identifier):
        value = self.store.get_document('paper-account', identifier)
        if value is None:
            raise KeyError('Paper or replay account does not exist')
        return PaperAccount.model_validate(value)

    def _datasets(self, identities, paper=False):
        cutoff = int(time.time()) if paper else None
        return [DatasetView(dataset=self.store.dataset(identity), bars=[bar for bar in self.store.bars(identity)
            if cutoff is None or bar.end <= cutoff]) for identity in identities]

    def _engine(self, account):
        cached = self.cache.get(account.id)
        if cached and cached[0] == account.revision:
            return cached[1]
        simulation = Simulation(self._datasets(account.dataset_ids, account.mode == 'paper'), account.settings, account.actions)
        commands = defaultdict(list)
        for command in account.commands:
            if account.mode == 'paper' or command.time <= account.cursor:
                commands[command.time].append(command)

        simulation.times = sorted(set(simulation.times) | {t for t in commands if simulation.start <= t <= simulation.end})

        def apply(time):
            for command in commands.get(time, []):
                if command.kind == 'order':
                    simulation.submit(command.order, at=command.time, order_id=command.order_id)
                else:
                    simulation.cancel(command.order_id, 'Cancelled in paper/replay account', at=command.time)

        simulation.advance(until=account.cursor, pause_before_open=True, on_event=apply)
        # Show submitted commands that await future source bars. A later paper refresh
        # rebuilds and applies them at their actual wall-clock time, never retroactively.
        for moment in sorted(t for t in commands if t > account.cursor):
            apply(moment)
        self.cache[account.id] = (account.revision, simulation)
        return simulation

    def _save(self, account, simulation):
        try:
            value = self.store.save_document('paper-account', account.id, account.model_dump(mode='json'), account.revision)
        except Exception:
            self.cache.pop(account.id, None)
            raise
        account.revision = value['revision']
        self.cache[account.id] = (account.revision, simulation)
        return self._view(account, simulation)

    def _view(self, account, simulation):
        times = sorted(time for time in simulation.ends if simulation.start <= time <= simulation.end)
        return AccountView(service_error=self.error, account=account, datasets=[view.dataset for view in simulation.views.values()], portfolio=simulation.portfolio(),
            orders=simulation.orders, fills=simulation.fills, trades=simulation.trades,
            next_time=next((time for time in times if time > account.cursor), None),
            first_time=simulation.start, last_time=simulation.end, completion_times=times)

    @staticmethod
    def _check_revision(account, revision):
        if account.revision != revision:
            raise ConflictError('This account changed in another view. Reload it before continuing.')

    @staticmethod
    def _cursor(simulation, target):
        if target < simulation.start or target > simulation.end:
            raise ValueError('Choose a replay time inside the selected research interval')
        times = sorted({simulation.start, *(time for time in simulation.ends if simulation.start <= time <= simulation.end)})
        return times[bisect_right(times, target)-1]

    def create(self, request: AccountRequest):
        with self.lock:
            datasets = self._datasets(request.dataset_ids, request.mode == 'paper')
            settings = request.settings.model_copy(deep=True)
            if request.mode == 'paper':
                completed = [bar.end for view in datasets for bar in view.bars if bar.complete]
                if not completed:
                    raise ValueError('Paper mode needs bars already completed at the current wall-clock time')
                settings.start = max(completed)
                settings.end = None
            simulation = Simulation(datasets, settings, request.actions)
            cursor = self._cursor(simulation, request.cursor if request.mode == 'replay' and request.cursor is not None else simulation.start)
            account = PaperAccount(id=str(uuid4()), name=request.name, mode=request.mode,
                dataset_ids=request.dataset_ids, settings=settings, actions=request.actions,
                cursor=cursor, created_at=utc_now())
            simulation.advance(until=cursor, pause_before_open=True)
            return self._save(account, simulation)

    def view(self, identifier):
        with self.lock:
            account = self.account(identifier)
            return self._view(account, self._engine(account))

    def seek(self, identifier, time, revision):
        with self.lock:
            account = self.account(identifier)
            self._check_revision(account, revision)
            if account.mode != 'replay':
                raise ValueError('Current-market paper accounts cannot seek in historical time')
            simulation = self._engine(account)
            target = self._cursor(simulation, time)
            if target < account.cursor:
                account.commands = [command for command in account.commands if command.time <= target]
                account.cursor = target
                self.cache.pop(identifier, None)
                simulation = self._engine(account)
            else:
                simulation.advance(until=target, pause_before_open=True)
                account.cursor = target
            return self._save(account, simulation)

    def order(self, identifier, request, revision):
        with self.lock:
            account = self.account(identifier)
            self._check_revision(account, revision)
            if account.mode == 'paper' and account.paused:
                raise ValueError('Resume paper updates before placing an order')
            simulation = self._engine(account)
            moment = max(account.cursor, math.ceil(time.time())) if account.mode == 'paper' else account.cursor
            order = simulation.submit(request, at=moment, order_id=f'manual-{uuid4()}')
            account.commands.append(AccountCommand(time=moment, kind='order', order=request, order_id=order.id))
            return self._save(account, simulation)

    def cancel(self, identifier, order_id, revision):
        with self.lock:
            account = self.account(identifier)
            self._check_revision(account, revision)
            simulation = self._engine(account)
            moment = max(account.cursor, math.ceil(time.time())) if account.mode == 'paper' else account.cursor
            if not simulation.cancel(order_id, 'Cancelled in paper/replay account', at=moment):
                raise ValueError('This order is not pending')
            account.commands.append(AccountCommand(time=moment, kind='cancel', order_id=order_id))
            return self._save(account, simulation)

    def pause(self, identifier, revision, paused):
        with self.lock:
            account = self.account(identifier)
            self._check_revision(account, revision)
            if account.mode != 'paper':
                raise ValueError('Use the playback controls to pause historical replay')
            account.paused = paused
            return self._save(account, self._engine(account))

    def refresh_paper(self, identifier, revision):
        """Adopt only an unchanged completed prefix from the exact same source/feed."""
        with self.lock:
            account = self.account(identifier)
            self._check_revision(account, revision)
            if account.mode != 'paper':
                raise ValueError('Replay uses its fixed input datasets; choose another account to change them')
            if account.paused:
                return self._view(account, self._engine(account))
            datasets = self.store.datasets()
            identities = []
            changed = False
            for identity in account.dataset_ids:
                old = self.store.dataset(identity)
                old_bars = [bar for bar in self.store.bars(identity) if bar.complete and bar.end <= account.cursor]
                candidates = [value for value in datasets if value.instrument == old.instrument
                    and (value.interval, value.source, value.feed, value.adjustment, value.first_start) ==
                    (old.interval, old.source, old.feed, old.adjustment, old.first_start)
                    and (value.last_end, value.created_at) > (old.last_end, old.created_at)]
                latest = max(candidates, key=lambda value: (value.last_end, value.created_at), default=old)
                if latest.id != old.id:
                    bars = [bar for bar in self.store.bars(latest.id) if bar.complete]
                    prefix = [bar for bar in bars if bar.end <= account.cursor]
                    if prefix != old_bars:
                        raise ValueError('Completed market history changed. This paper account keeps its original inputs; review the data revision.')
                    changed = True
                identities.append(latest.id)
            next_cursor = max(bar.end for view in self._datasets(identities, True) for bar in view.bars if bar.complete)
            if not changed and next_cursor == account.cursor:
                return self._view(account, self._engine(account))
            account.error = None
            account.dataset_ids = identities
            account.cursor = next_cursor
            self.cache.pop(identifier, None)
            simulation = self._engine(account)
            return self._save(account, simulation)
