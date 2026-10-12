import sqlite3

import pytest

from backend.store import Store


def test_failed_migration_rolls_back_schema_and_preserves_documents(tmp_path, monkeypatch):
    original = Store(tmp_path)
    saved = original.save_document('fixture', 'retained', {'value': 'user work'}, 0)
    with original.connect() as db:
        db.execute('DROP TABLE alert_states')
        db.execute('DROP TABLE alert_events')
        db.execute('PRAGMA user_version=1')

    connect = Store.connect

    def failing_connection(store):
        db = connect(store)
        # Deny the second new table after the first has actually been created.
        db.set_authorizer(lambda action, name, *_: sqlite3.SQLITE_DENY
                          if action == sqlite3.SQLITE_CREATE_TABLE and name == 'alert_events'
                          else sqlite3.SQLITE_OK)
        return db

    with monkeypatch.context() as patch:
        patch.setattr(Store, 'connect', failing_connection)
        with pytest.raises(sqlite3.DatabaseError, match='not authorized'):
            Store(tmp_path)

    with connect(original) as db:
        assert db.execute('PRAGMA user_version').fetchone()[0] == 1
        assert not db.execute("SELECT name FROM sqlite_master WHERE name IN ('alert_states','alert_events')").fetchall()
    assert original.get_document('fixture', 'retained') == saved
    assert original.document_versions('fixture', 'retained') == [saved]
    backups = list((tmp_path / 'backups').glob('*.sqlite3'))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as db:
        assert db.execute('PRAGMA user_version').fetchone()[0] == 1
        assert 'user work' in db.execute('SELECT body FROM documents').fetchone()[0]
    recovered = Store(tmp_path)
    assert recovered.get_document('fixture', 'retained') == saved
    with recovered.connect() as db:
        assert db.execute('PRAGMA user_version').fetchone()[0] == 2


def test_future_database_version_is_rejected_without_rewriting_saved_work(tmp_path):
    original = Store(tmp_path)
    original.save_document('fixture', 'future', {'value': 'newer application data'}, 0)
    with original.connect() as db:
        db.execute('PRAGMA user_version=100')
        before = '\n'.join(db.iterdump())
    with pytest.raises(RuntimeError, match='newer Market Workbench'):
        Store(tmp_path)
    with original.connect() as db:
        assert '\n'.join(db.iterdump()) == before
