"""Snapshot persistence and owned, bounded research workers."""
from __future__ import annotations

import asyncio
import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID, uuid4

import psutil

from .models import utc_now
from .normalization import dataset_digest
from .research_models import ResearchJob, ResearchRequest, ResearchResult
from .scripts import analyze_script, validate_parameters
from .simulation import ENGINE_VERSION
from .store import Store, atomic_write
from .worker_process import ProcessTree

APP_ROOT = Path(__file__).resolve().parent.parent
TERMINAL = {'completed', 'failed', 'cancelled', 'interrupted'}


def digest_file(path):
    with path.open('rb') as file:
        return hashlib.file_digest(file, 'sha256').hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


class ResearchService:
    def __init__(self, store: Store, concurrency=2):
        self.store = store
        self.root = store.root/'runs'
        self.root.mkdir(exist_ok=True)
        self.semaphore = asyncio.Semaphore(concurrency)
        self.tasks = {}
        self.submissions = set()
        self.stops = {}
        self.processes = {}
        self.closed = False
        for body in self.store.list_documents('research'):
            job = ResearchJob.model_validate(body)
            if job.status not in TERMINAL:
                job.status, job.error, job.finished_at = 'interrupted', 'Local service stopped before the run finished; inputs are retained.', utc_now()
                self._save(job)

    def _save(self, job: ResearchJob):
        saved = self.store.save_document('research', job.id, job.model_dump(mode='json'), job.revision)
        job.revision = saved['revision']

    def jobs(self):
        return [ResearchJob.model_validate(value) for value in self.store.list_documents('research')]

    def job(self, identifier):
        value = self.store.get_document('research', identifier)
        if value is None:
            raise KeyError('Research run does not exist')
        return ResearchJob.model_validate(value)

    def directory(self, identifier):
        job = self.job(identifier)  # Persisted identity, never an arbitrary path segment.
        if str(UUID(job.id)) != job.id:
            raise ValueError('Invalid persisted run identity')
        return self.root/job.id

    def _snapshot(self, request: ResearchRequest):
        analysis = analyze_script(request.script)
        if not analysis.valid:
            raise ValueError('Fix script diagnostics before running')
        request = request.model_copy(deep=True)
        request.parameters = validate_parameters(analysis.parameters, request.parameters)
        identifier = str(uuid4())
        temporary = self.root/f'.staging-{identifier}'
        temporary.mkdir()
        try:
            files, datasets, identities = {}, [], set()
            for dataset_id in request.dataset_ids:
                dataset = self.store.dataset(dataset_id)
                bars = self.store.bars(dataset_id)
                if dataset.instrument.id in identities:
                    raise ValueError('Select one interval/source dataset for each instrument')
                identities.add(dataset.instrument.id)
                if dataset_digest(dataset.instrument, dataset.interval, bars) != dataset.hash:
                    raise ValueError('Stored dataset content does not match its immutable identity')
                if not request.settings.allow_fixture_data and dataset.source == 'fixture':
                    raise ValueError('Enable the labeled demonstration setting to run synthetic fixtures')
                filename = f'dataset-{len(datasets)}.parquet'
                shutil.copyfile(self.store.root/'datasets'/f'{dataset.hash}.parquet', temporary/filename)
                files[filename] = digest_file(temporary/filename)
                datasets.append({'metadata': dataset.model_dump(mode='json'), 'file': filename,
                    'file_hash': files[filename], 'logical_hash': dataset.hash})
            if set(request.script.subscriptions)-identities:
                raise ValueError('Script subscriptions are outside the selected dataset universe')
            atomic_write(temporary/'strategy.py', request.script.source)
            atomic_write(temporary/'request.json', request.model_dump_json())
            files['strategy.py'] = digest_file(temporary/'strategy.py')
            files['request.json'] = digest_file(temporary/'request.json')
            manifest = {'schema_version': 1, 'engine_version': ENGINE_VERSION,
                'python_version': platform.python_version(), 'dependencies': {name: importlib.metadata.version(name)
                    for name in ('numpy', 'pandas', 'pydantic', 'pyarrow', 'exchange-calendars', 'psutil')},
                'script_hash': analysis.script_hash, 'datasets': datasets, 'files': files,
                'settings': request.settings.model_dump(mode='json'), 'parameters': request.parameters,
                'actions': [action.model_dump(mode='json') for action in request.actions]}
            snapshot_hash = hashlib.sha256(canonical(manifest).encode()).hexdigest()
            atomic_write(temporary/'manifest.json', canonical(manifest))
            (temporary/'tmp').mkdir()
            destination = self.root/identifier
            temporary.rename(destination)
            return ResearchJob(id=identifier, name=request.name, status='queued', created_at=utc_now(),
                snapshot_hash=snapshot_hash, limits=request.limits)
        except BaseException:
            shutil.rmtree(temporary, ignore_errors=True)  # Only this unexecuted, owned staging directory.
            raise

    async def submit(self, request: ResearchRequest):
        if self.closed:
            raise ValueError('The research service is shutting down')
        if len(self.tasks)+len(self.submissions) >= 20:
            raise ValueError('The local research queue is full; cancel or wait for an existing run')
        async def create():
            job = await asyncio.to_thread(self._snapshot, request)
            self._save(job)
            self.stops[job.id] = asyncio.Event()
            self.tasks[job.id] = asyncio.create_task(self._run(job), name=f'research-{job.id}')
            return job
        task = asyncio.create_task(create())
        self.submissions.add(task)
        task.add_done_callback(self.submissions.discard)
        return await asyncio.shield(task)

    def verify_snapshot(self, identifier):
        directory = self.directory(identifier)
        manifest = json.loads((directory/'manifest.json').read_text())
        if hashlib.sha256(canonical(manifest).encode()).hexdigest() != self.job(identifier).snapshot_hash:
            raise ValueError('Research manifest changed after snapshot creation')
        for filename, expected in manifest['files'].items():
            if Path(filename).name != filename or digest_file(directory/filename) != expected:
                raise ValueError(f'Research snapshot changed: {filename}')
        return manifest

    def result(self, identifier):
        job = self.job(identifier)
        if job.status != 'completed':
            raise ValueError('This run has no completed result')
        path = self.directory(identifier)/'result.json'
        if digest_file(path) != job.result_hash:
            raise ValueError('Saved result content does not match its recorded hash')
        return ResearchResult.model_validate_json(path.read_text())

    def output(self, identifier):
        directory = self.directory(identifier)
        result = {}
        for filename in ('stdout', 'stderr'):
            path = directory/f'{filename}.txt'
            if path.exists():
                with path.open('rb') as file:
                    file.seek(max(0, path.stat().st_size-64000))
                    result[filename] = file.read(64000).decode('utf-8', errors='replace')
            else:
                result[filename] = ''
        progress = directory/'progress.json'
        value = json.loads(progress.read_text()) if progress.exists() else {}
        result['logs'] = value.get('logs', [])
        result['plots'] = value.get('plots', [])
        return result

    @asynccontextmanager
    async def _slot(self, stop):
        acquire = asyncio.create_task(self.semaphore.acquire())
        cancelled = asyncio.create_task(stop.wait())
        acquired = False
        try:
            await asyncio.wait((acquire, cancelled), return_when=asyncio.FIRST_COMPLETED)
            if acquire.done() and not acquire.cancelled():
                acquired = acquire.result()
            else:
                acquire.cancel()
                await asyncio.gather(acquire, return_exceptions=True)
            yield acquired and not stop.is_set()
        finally:
            cancelled.cancel()
            await asyncio.gather(cancelled, return_exceptions=True)
            if acquired:
                self.semaphore.release()

    async def cancel(self, identifier):
        job = self.job(identifier)
        if job.status in TERMINAL:
            return job
        event = self.stops.get(identifier)
        if event is None:
            raise ValueError('This run is no longer owned by the running service')
        event.set()
        return job

    async def _run(self, job: ResearchJob):
        started = time.monotonic()
        tree, process = None, None
        try:
            async with self._slot(self.stops[job.id]) as acquired:
                stop = self.stops[job.id]
                if not acquired or stop.is_set() or self.closed:
                    job.status = 'interrupted' if self.closed else 'cancelled'
                    return
                directory = self.directory(job.id)
                await asyncio.to_thread(self.verify_snapshot, job.id)
                parent = psutil.Process()
                parent.children(recursive=False)  # Refuse execution if ownership monitoring is unavailable.
                environment = {'PATH': str(Path(sys.executable).parent), 'PYTHONUNBUFFERED': '1',
                    'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONHASHSEED': '0', 'PYTHONNOUSERSITE': '1',
                    'LANG': 'en_US.UTF-8', 'TZ': 'UTC', 'TMPDIR': str(directory/'tmp'),
                    'TEMP': str(directory/'tmp'), 'TMP': str(directory/'tmp'),
                    'OPENBLAS_NUM_THREADS': '1', 'OMP_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1'}
                if os.name == 'nt':
                    for key in ('SYSTEMROOT', 'WINDIR'):
                        if key in os.environ:
                            environment[key] = os.environ[key]
                process = await asyncio.to_thread(subprocess.Popen, [sys.executable, '-m', 'backend.research_worker', str(directory),
                    str(parent.pid), str(parent.create_time())], cwd=APP_ROOT, env=environment,
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    start_new_session=os.name == 'posix',
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0)
                tree = ProcessTree(psutil.Process(process.pid))
                atomic_write(directory/'worker-identity.json', json.dumps({
                    'pid': process.pid, 'created_at': tree.created,
                    'parent_pid': parent.pid, 'parent_created_at': parent.create_time()}))
                self.processes[job.id] = tree
                started = time.monotonic()
                job.status, job.started_at = 'running', utc_now()
                self._save(job)
                while process.poll() is None:
                    elapsed = time.monotonic()-started
                    rss = tree.rss()
                    job.peak_memory_bytes = max(job.peak_memory_bytes, rss)
                    reason = None
                    if stop.is_set() or self.closed:
                        job.status = 'interrupted' if self.closed else 'cancelled'
                        reason = 'Local service shutdown' if self.closed else 'Cancelled by user'
                    elif elapsed > job.limits.deadline_seconds:
                        job.status, reason = 'failed', 'Worker deadline exceeded'
                    elif rss > job.limits.memory_mb*1024*1024:
                        job.status, reason = 'failed', 'Worker memory limit exceeded'
                    if reason:
                        job.error = reason
                        remaining = await asyncio.to_thread(tree.terminate)
                        if remaining:
                            raise RuntimeError('Owned research processes could not be stopped; ownership retained')
                        await asyncio.to_thread(process.wait, timeout=3)
                        return
                    progress = directory/'progress.json'
                    if progress.exists():
                        value = json.loads(progress.read_text())
                        job.completed_events, job.total_events = value['completed_events'], value['total_events']
                        job.progress = job.completed_events/max(1, job.total_events)
                    job.elapsed_seconds = elapsed
                    self._save(job)
                    await asyncio.sleep(.25)
                await asyncio.to_thread(process.wait)
                remaining = await asyncio.to_thread(tree.terminate, False)
                if remaining:
                    raise RuntimeError('A script child process remains active; ownership retained')
                outcome_path = directory/'outcome.json'
                if not outcome_path.exists():
                    job.status, job.error = 'failed', f'Worker exited without an outcome (code {process.returncode})'
                    return
                outcome = json.loads(outcome_path.read_text())
                if outcome['status'] != 'completed':
                    job.status, job.error = 'failed', outcome.get('error', 'Script execution failed')
                    return
                await asyncio.to_thread(self.verify_snapshot, job.id)
                result_path = directory/'result.json'
                # Validate before advertising a finished run or serving its contents.
                await asyncio.to_thread(ResearchResult.model_validate_json, result_path.read_text())
                job.result_hash = digest_file(result_path)
                job.status, job.progress = 'completed', 1
        except Exception as exc:  # noqa: BLE001 -- task supervisor retains failure evidence
            job.status, job.error = 'failed', f'{type(exc).__name__}: {exc}'
            if tree is not None:
                await asyncio.to_thread(tree.terminate)
        finally:
            job.finished_at = utc_now()
            job.elapsed_seconds = time.monotonic()-started if job.started_at else 0
            self._save(job)
            try:
                if tree is None or not tree.refresh():
                    self.processes.pop(job.id, None)
            except (PermissionError, psutil.AccessDenied):
                pass  # Cleanup must retain identities if their exit cannot be confirmed.
            self.tasks.pop(job.id, None)
            self.stops.pop(job.id, None)

    async def close(self):
        self.closed = True
        if self.submissions:
            await asyncio.gather(*self.submissions, return_exceptions=True)
        for event in self.stops.values():
            event.set()
        if self.tasks:
            await asyncio.gather(*self.tasks.values(), return_exceptions=True)
        for identity, tree in list(self.processes.items()):
            remaining = await asyncio.to_thread(tree.terminate)
            if not remaining:
                self.processes.pop(identity, None)
        if self.processes:
            raise RuntimeError('Research process cleanup incomplete; owned identities retained')
