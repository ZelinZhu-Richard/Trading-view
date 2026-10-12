import asyncio
import sqlite3

import pytest

from backend.alerts import AlertService, matches
from backend.models import AlertDefinition, Bar, IndicatorInstance, Instrument
from backend.store import Store

INSTRUMENT = Instrument(id='TEST:ALERT', symbol='ALERT', name='Alert fixture', exchange='TEST',
    asset_class='other', quote_currency='USD', timezone='UTC', calendar='24/7')
START = 1735689600


def dataset(store, closes):
    bars = [Bar(start=START+i*60, end=START+(i+1)*60, open=c, high=c+1, low=c-1,
                close=c, volume=1, source='fixture', feed='alert-fixture', adjustment='raw') for i, c in enumerate(closes)]
    return store.save_dataset(INSTRUMENT, '1m', bars, [])


def alert(data, **changes):
    values = {'id': 'cross', 'name': 'Crossing check', 'dataset_id': data.id, 'condition': 'crosses_above', 'threshold': 10}
    return AlertDefinition(**(values | changes))


def test_crossing_boundary_and_missing_values():
    assert matches('crosses_above', 10, 11, 10)
    assert not matches('crosses_above', 9, 10, 10)
    assert matches('crosses_below', 10, 9, 10)
    assert not matches('crosses_above', None, 11, 10)
    assert not matches('below', 1, None, 10)
    assert matches('above', None, 11, 10)


def test_once_alert_persists_checkpoint_and_never_repeats_on_restart(tmp_path):
    store = Store(tmp_path)
    service = AlertService(store)
    initial = dataset(store, [8, 9, 10])
    service.save(alert(initial))
    dataset(store, [8, 9, 10, 11, 9, 12])
    service.evaluate_all()
    assert len(service.events()) == 1
    assert service.events()[0].bar_end == START+4*60
    restarted = AlertService(Store(tmp_path))
    restarted.evaluate_all()
    assert len(restarted.events()) == 1
    assert restarted.state('cross')['fired']
    restarted.delete('cross')
    assert not restarted.definitions()
    assert len(restarted.events()) == 1  # deleting a rule retains its event audit


def test_recurring_price_and_indicator_thresholds(tmp_path):
    store = Store(tmp_path)
    service = AlertService(store)
    initial = dataset(store, [8, 9, 10])
    service.save(alert(initial, recurring=True))
    service.save(alert(initial, id='mean', name='SMA threshold', recurring=True, condition='above',
        indicator=IndicatorInstance(id='sma', definition_id='sma', parameters={'length': 2}), threshold=10.5))
    dataset(store, [8, 9, 10, 11, 12, 8, 13])
    service.evaluate_all()
    crossings = [e for e in service.events() if e.alert_id == 'cross']
    assert [e.bar_end for e in crossings] == [START+7*60, START+4*60]
    mean = [e for e in service.events() if e.alert_id == 'mean']
    assert len(mean) == 1 and mean[0].value == 11.5
    service.evaluate_all()
    assert len(service.events()) == 3


def test_pause_edit_revision_and_corrected_history(tmp_path):
    from backend.store import ConflictError
    store = Store(tmp_path)
    service = AlertService(store)
    initial = dataset(store, [8, 9, 10])
    saved = service.save(alert(initial, recurring=True))
    paused = service.save(saved.model_copy(update={'enabled': False}))
    dataset(store, [8, 9, 10, 11])
    service.evaluate_all()
    assert not service.events()
    with pytest.raises(ConflictError):
        service.save(saved)
    resumed = service.save(paused.model_copy(update={'enabled': True}))
    service.evaluate_all()
    assert not service.events()  # pause/resume skips bars already completed while paused
    # A historical revision cannot silently change a previously observed prefix.
    dataset(store, [8, 8.5, 10, 11, 12])
    service.evaluate_all()
    assert 'changed' in service.state('cross')['message']
    assert not service.events()
    assert resumed.revision == 3


async def test_owned_alert_task_shutdown(tmp_path):
    service = AlertService(Store(tmp_path))
    service.start()
    await asyncio.sleep(.03)
    assert service.status()['running']
    await service.close()
    assert not service.status()['running'] and service.pending is None


def test_schema_migration_keeps_backup_and_documents(tmp_path):
    store = Store(tmp_path)
    store.save_document('fixture', 'retained', {'value': 123}, 0)
    with store.connect() as db:
        db.execute('DROP TABLE alert_states')
        db.execute('DROP TABLE alert_events')
        db.execute('PRAGMA user_version=1')
    migrated = Store(tmp_path)
    assert migrated.get_document('fixture', 'retained')['value'] == 123
    backups = list((tmp_path/'backups').glob('pre-schema-2-*.sqlite3'))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as db:
        assert db.execute('PRAGMA user_version').fetchone()[0] == 1
        assert '123' in db.execute("SELECT body FROM documents WHERE id='retained'").fetchone()[0]
    Store(tmp_path)
    assert len(list((tmp_path/'backups').glob('*.sqlite3'))) == 1
