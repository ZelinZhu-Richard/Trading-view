from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from itertools import pairwise
from pathlib import Path

import pandas as pd

from .models import Bar, Dataset, Instrument, Interval, Workspace, utc_now
from .normalization import dataset_digest


class ConflictError(ValueError):
    pass


def atomic_write(path: Path, content: str | bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix='.writing-')
    try:
        with os.fdopen(fd, 'wb') as file:
            file.write(content.encode() if isinstance(content, str) else content)
            file.flush()
            os.fsync(file.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


class Store:
    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        (root / 'datasets').mkdir(exist_ok=True)
        self.db_path = root / 'workbench.sqlite3'
        with self.connect() as db:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version > 2:
                raise RuntimeError('This database needs a newer Market Workbench; existing data was preserved')
            if version == 1:
                backup_dir = root / 'backups'
                backup_dir.mkdir(exist_ok=True)
                backup_path = backup_dir / f'pre-schema-2-{utc_now().replace(":", "-")}.sqlite3'
                with sqlite3.connect(backup_path) as backup:
                    db.backup(backup)
            db.executescript('''
                BEGIN;
                CREATE TABLE IF NOT EXISTS documents (
                    kind TEXT NOT NULL, id TEXT NOT NULL, revision INTEGER NOT NULL,
                    body TEXT NOT NULL, updated_at TEXT NOT NULL, PRIMARY KEY(kind,id));
                CREATE TABLE IF NOT EXISTS versions (
                    kind TEXT NOT NULL, id TEXT NOT NULL, revision INTEGER NOT NULL,
                    body TEXT NOT NULL, updated_at TEXT NOT NULL, PRIMARY KEY(kind,id,revision));
                CREATE TABLE IF NOT EXISTS datasets (id TEXT PRIMARY KEY, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS alert_states (id TEXT PRIMARY KEY, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS alert_events (
                    id TEXT PRIMARY KEY, alert_id TEXT NOT NULL, bar_end INTEGER NOT NULL,
                    body TEXT NOT NULL, UNIQUE(alert_id,bar_end));
                PRAGMA user_version=2;
                COMMIT;
            ''')

    def connect(self):
        db = sqlite3.connect(self.db_path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('PRAGMA foreign_keys=ON')
        return db

    def get_document(self, kind: str, identifier: str):
        with self.connect() as db:
            row = db.execute('SELECT body FROM documents WHERE kind=? AND id=?', (kind, identifier)).fetchone()
        return json.loads(row['body']) if row else None

    def list_documents(self, kind: str):
        with self.connect() as db:
            return [json.loads(r[0]) for r in db.execute('SELECT body FROM documents WHERE kind=? ORDER BY updated_at DESC', (kind,))]

    def document_versions(self, kind: str, identifier: str):
        with self.connect() as db:
            return [json.loads(r[0]) for r in db.execute(
                'SELECT body FROM versions WHERE kind=? AND id=? ORDER BY revision DESC', (kind, identifier))]

    def save_document(self, kind: str, identifier: str, body: dict, expected_revision: int) -> dict:
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT revision FROM documents WHERE kind=? AND id=?', (kind, identifier)).fetchone()
            revision = row['revision'] if row else 0
            if revision != expected_revision:
                raise ConflictError('A newer version exists. Reload it before saving to prevent lost changes.')
            value = {**body, 'revision': revision + 1}
            text = json.dumps(value, allow_nan=False)
            now = utc_now()
            db.execute('INSERT OR REPLACE INTO documents VALUES (?,?,?,?,?)', (kind, identifier, revision + 1, text, now))
            db.execute('INSERT INTO versions VALUES (?,?,?,?,?)', (kind, identifier, revision + 1, text, now))
        return value

    def workspace(self, identifier: str = 'default') -> Workspace:
        saved = self.get_document('workspace', identifier)
        return Workspace.model_validate(saved) if saved else Workspace(id=identifier)

    def datasets(self) -> list[Dataset]:
        with self.connect() as db:
            return [Dataset.model_validate_json(r[0]) for r in db.execute('SELECT body FROM datasets ORDER BY rowid DESC')]

    def dataset(self, identifier: str) -> Dataset:
        with self.connect() as db:
            row = db.execute('SELECT body FROM datasets WHERE id=?', (identifier,)).fetchone()
        if not row:
            raise KeyError('Dataset does not exist')
        return Dataset.model_validate_json(row[0])

    def save_dataset(self, instrument: Instrument, interval: Interval, bars: list[Bar], limitations: list[str], parent_id: str | None = None) -> Dataset:
        if not bars:
            raise ValueError('Cannot save an empty dataset')
        if any(a.start >= b.start or a.end > b.start for a, b in pairwise(bars)):
            raise ValueError('Bars must be uniquely ordered and non-overlapping')
        if len({(b.source, b.feed, b.adjustment) for b in bars}) != 1:
            raise ValueError('Dataset must have one source, feed and adjustment basis')
        digest = dataset_digest(instrument, interval, bars)
        identifier = digest
        try:
            return self.dataset(identifier)
        except KeyError:
            pass
        meta = Dataset(id=identifier, hash=digest, instrument=instrument, interval=interval,
                       source=bars[0].source, feed=bars[0].feed, adjustment=bars[0].adjustment,
                       created_at=utc_now(), first_start=bars[0].start, last_end=bars[-1].end,
                       row_count=len(bars), limitations=limitations, parent_id=parent_id)
        frame = pd.DataFrame([b.model_dump() for b in bars])
        # Immutable content-addressed files: crashes cannot mutate an older snapshot.
        atomic_write(self.root / 'datasets' / f'{identifier}.parquet', frame.to_parquet(index=False))
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO datasets VALUES (?,?)', (identifier, meta.model_dump_json()))
        return self.dataset(identifier)

    def bars(self, identifier: str) -> list[Bar]:
        meta = self.dataset(identifier)  # Identity lookup before using a path component.
        frame = pd.read_parquet(self.root / 'datasets' / f'{meta.hash}.parquet')
        records = frame.astype(object).where(pd.notna(frame), None).to_dict(orient='records')
        return [Bar.model_validate(r) for r in records]
