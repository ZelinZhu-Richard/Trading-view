"""Local completed-bar alerts with transactional checkpoints and event deduplication."""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
from contextlib import suppress
from threading import Event

from .indicators import DEFINITIONS, evaluate, parameters
from .models import AlertDefinition, AlertEvent, IndicatorRequest, utc_now
from .store import ConflictError, Store


def matches(condition: str, previous: float | None, current: float | None, threshold: float) -> bool:
    if current is None:
        return False
    if condition == 'above':
        return current > threshold
    if condition == 'below':
        return current < threshold
    if previous is None:
        return False
    if condition == 'crosses_above':
        return previous <= threshold < current
    if condition == 'crosses_below':
        return previous >= threshold > current
    raise ValueError('Unknown alert condition')


class AlertService:
    def __init__(self, store: Store):
        self.store = store
        self.task: asyncio.Task | None = None
        self.error = ''
        self.last_cycle: str | None = None
        self.stopping = Event()
        self.pending: asyncio.Task | None = None

    def start(self):
        self.stopping.clear()
        self.task = asyncio.create_task(self.run())

    async def close(self):
        self.stopping.set()
        if self.task:
            self.task.cancel()
            with suppress(asyncio.CancelledError):
                await self.task
            self.task = None
        if self.pending:
            await asyncio.gather(self.pending, return_exceptions=True)
            self.pending = None

    async def run(self):
        while True:
            try:
                self.pending = asyncio.create_task(asyncio.to_thread(self.evaluate_all))
                await asyncio.shield(self.pending)
                self.pending = None
                self.last_cycle, self.error = utc_now(), ''
            except Exception as exc:  # noqa: BLE001 -- supervisor publishes failure state and remains available
                # Explicit service status; never swallow a failed evaluation as success.
                self.error = f'Alert evaluation failed: {type(exc).__name__}'
            await asyncio.sleep(2)

    def definitions(self):
        return [AlertDefinition.model_validate(d) for d in self.store.list_documents('alert')]

    def state(self, identifier: str):
        with self.store.connect() as db:
            row = db.execute('SELECT body FROM alert_states WHERE id=?', (identifier,)).fetchone()
        return json.loads(row[0]) if row else None

    def values(self, alert, dataset):
        bars = [b for b in self.store.bars(dataset.id) if b.complete and b.end <= time.time()]
        if alert.indicator:
            result = evaluate(IndicatorRequest(dataset_id=dataset.id, instances=[alert.indicator]), dataset, bars).results[0]
            if result.status != 'ready':
                raise ValueError(result.message)
            line = next((line for line in result.lines if line.output_id == alert.output_id), None)
            if line is None:
                raise ValueError('Indicator output does not exist')
            return bars, line.values
        return bars, [getattr(b, alert.field) for b in bars]

    def save(self, alert: AlertDefinition):
        dataset = self.store.dataset(alert.dataset_id)
        matching = [d for d in self.store.datasets() if d.instrument.model_dump() == dataset.instrument.model_dump()
            and (d.interval, d.source, d.feed, d.adjustment) == (dataset.interval, dataset.source, dataset.feed, dataset.adjustment)
            and d.first_start <= dataset.first_start]
        dataset = max(matching, key=lambda d: (d.last_end, d.created_at), default=dataset)
        if alert.indicator:
            parameters(alert.indicator.definition_id, alert.indicator.parameters)
            if alert.output_id not in {o.id for o in DEFINITIONS[alert.indicator.definition_id].outputs}:
                raise ValueError('Select a declared indicator output')
        bars, values = self.values(alert, dataset)
        if not bars:
            raise ValueError('Alerts need at least one completed historical bar as a baseline')
        previous = self.store.get_document('alert', alert.id)
        state = self.state(alert.id)
        # A pause/resume preserves the condition but starts at the latest local bar.
        # Editing a condition resets its baseline and once-only fired state explicitly.
        condition_changed = not previous or any(previous.get(k) != alert.model_dump(mode='json').get(k)
            for k in ('dataset_id', 'field', 'indicator', 'output_id', 'condition', 'threshold', 'recurring'))
        reset = condition_changed or not state or (alert.enabled and not previous.get('enabled'))
        if reset:
            state = {'last_end': bars[-1].end, 'previous': values[-1], 'fired': False,
                     'last_dataset_id': dataset.id, 'message': 'Waiting for a new completed bar.', 'updated_at': utc_now()}
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("SELECT revision FROM documents WHERE kind='alert' AND id=?", (alert.id,)).fetchone()
            revision = row[0] if row else 0
            if revision != alert.revision:
                raise ConflictError('A newer alert version exists; reload before saving')
            if not reset:
                current_state = db.execute('SELECT body FROM alert_states WHERE id=?', (alert.id,)).fetchone()
                state = json.loads(current_state[0]) if current_state else state
            value = alert.model_copy(update={'revision': revision+1})
            text, now = value.model_dump_json(), utc_now()
            db.execute('INSERT OR REPLACE INTO documents VALUES (?,?,?,?,?)', ('alert', alert.id, revision+1, text, now))
            db.execute('INSERT INTO versions VALUES (?,?,?,?,?)', ('alert', alert.id, revision+1, text, now))
            db.execute('INSERT OR REPLACE INTO alert_states VALUES (?,?)', (alert.id, json.dumps(state, allow_nan=False)))
        return value

    def delete(self, identifier):
        with self.store.connect() as db:
            db.execute("DELETE FROM documents WHERE kind='alert' AND id=?", (identifier,))
            db.execute('DELETE FROM alert_states WHERE id=?', (identifier,))
        # Trigger history remains an audit record after deleting an alert.

    def events(self, limit=200):
        with self.store.connect() as db:
            return [AlertEvent.model_validate_json(row[0]) for row in db.execute(
                'SELECT body FROM alert_events ORDER BY rowid DESC LIMIT ?', (limit,))]

    def evaluate_all(self):
        datasets = self.store.datasets()
        for alert in self.definitions():
            if self.stopping.is_set():
                return
            if not alert.enabled:
                continue
            state = self.state(alert.id)
            if not state or (state['fired'] and not alert.recurring):
                continue
            baseline = self.store.dataset(alert.dataset_id)
            candidates = [d for d in datasets if d.instrument.model_dump() == baseline.instrument.model_dump()
                and (d.interval, d.source, d.feed, d.adjustment) == (baseline.interval, baseline.source, baseline.feed, baseline.adjustment)
                and d.last_end > state['last_end'] and d.first_start <= baseline.first_start]
            if not candidates:
                continue
            latest = max(candidates, key=lambda d: (d.last_end, d.created_at))
            try:
                bars, values = self.values(alert, latest)
                previous_bars = [b for b in self.store.bars(state['last_dataset_id']) if b.complete and b.end <= state['last_end']]
                current_prefix = [b for b in bars if b.end <= state['last_end']]
                if previous_bars != current_prefix:
                    raise ValueError('Historical source bars changed; edit this alert to select a new baseline before resuming.')
            except ValueError as exc:
                with self.store.connect() as db:
                    state['message'] = str(exc)
                    db.execute('UPDATE alert_states SET body=? WHERE id=?', (json.dumps(state), alert.id))
                continue
            with self.store.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                row = db.execute("SELECT revision FROM documents WHERE kind='alert' AND id=?", (alert.id,)).fetchone()
                if not row or row[0] != alert.revision:
                    continue  # UI edit/delete won; do not emit from obsolete conditions.
                row = db.execute('SELECT body FROM alert_states WHERE id=?', (alert.id,)).fetchone()
                if not row:
                    continue
                state = json.loads(row[0])
                if state['fired'] and not alert.recurring:
                    continue
                for bar, value in zip(bars, values, strict=True):
                    if self.stopping.is_set():
                        break
                    if bar.end <= state['last_end']:
                        continue
                    if matches(alert.condition, state['previous'], value, alert.threshold):
                        event = AlertEvent(id=hashlib.sha256(f'{alert.id}:{bar.end}'.encode()).hexdigest(),
                            alert_id=alert.id, alert_name=alert.name, dataset_id=latest.id, bar_end=bar.end,
                            evaluated_at=utc_now(), value=value, threshold=alert.threshold,
                            condition=alert.condition, source=latest.source, feed=latest.feed)
                        db.execute('INSERT OR IGNORE INTO alert_events VALUES (?,?,?,?)',
                                   (event.id, alert.id, bar.end, event.model_dump_json()))
                        state['fired'] = True
                    state.update(last_end=bar.end, previous=value, last_dataset_id=latest.id,
                                 message='Waiting for a new completed bar.', updated_at=utc_now())
                    if state['fired'] and not alert.recurring:
                        state['message'] = 'Triggered once; evaluation stopped.'
                        break
                db.execute('UPDATE alert_states SET body=? WHERE id=?', (json.dumps(state, allow_nan=False), alert.id))

    def status(self):
        return {'running': self.task is not None and not self.task.done(), 'last_cycle': self.last_cycle,
                'error': self.error, 'states': {a.id: self.state(a.id) for a in self.definitions()},
                'scope': 'Local service only. Completed stored bars; streaming quotes do not trigger these alerts. Supported provider history refreshes automatically for enabled rules while this service runs. Imported history needs new imports; source errors appear in candle-update status.'}
