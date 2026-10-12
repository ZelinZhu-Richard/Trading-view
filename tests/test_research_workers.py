import asyncio
import hashlib
import time

import psutil
import pytest

from backend.models import StrategyDefinition
from backend.research import ResearchService
from backend.research_models import ExecutionSettings, ResearchRequest, WorkerLimits
from backend.store import Store
from tests.test_simulation import series


async def wait_for(service, identifier, predicate, timeout=12):
    deadline = time.monotonic()+timeout
    while time.monotonic() < deadline:
        job = service.job(identifier)
        if predicate(job):
            return job
        await asyncio.sleep(.05)
    pytest.fail(f'Job did not reach expected state: {service.job(identifier)}')


def request(store, source, **limits):
    view = series()
    dataset = store.save_dataset(view.dataset.instrument, '1m', view.bars, ['Explicit synthetic process fixture'])
    return ResearchRequest(script=StrategyDefinition(id='worker-test', name='Worker test', source=source, kind='strategy'),
        dataset_ids=[dataset.id], settings=ExecutionSettings(allow_fixture_data=True),
        limits=WorkerLimits(**limits))


async def test_real_worker_snapshot_results_environment_and_runtime_traceback(tmp_path, monkeypatch):
    store = Store(tmp_path)
    service = ResearchService(store)
    monkeypatch.setenv('ALPACA_API_KEY', 'sentinel-must-not-be-in-worker')
    source = '''
import os
assert "ALPACA_API_KEY" not in os.environ
print("Worker started")
def initialize(ctx):
    ctx.order("A", "buy", 1)
def on_bars(ctx, bars):
    ctx.log(ctx.timestamp, len(ctx.history("A")))
'''
    try:
        first = await service.submit(request(store, source))
        done = await wait_for(service, first.id, lambda job: job.status in ('completed', 'failed'))
        assert done.status == 'completed', done.error
        result = service.result(done.id)
        assert len(result.fills) == 1 and len(result.logs) == 4
        assert service.output(done.id)['stdout'] == 'Worker started\n'
        manifest = service.verify_snapshot(done.id)
        assert manifest['script_hash'] == hashlib.sha256(source.encode()).hexdigest()
        original = store.root/'datasets'/f'{manifest["datasets"][0]["logical_hash"]}.parquet'
        copied = service.directory(done.id)/manifest['datasets'][0]['file']
        assert original.stat().st_ino != copied.stat().st_ino
        second = await service.submit(request(store, source))
        again = await wait_for(service, second.id, lambda job: job.status in ('completed', 'failed'))
        assert again.status == 'completed', again.error
        assert again.snapshot_hash == done.snapshot_hash
        assert again.result_hash == done.result_hash
        assert not service.processes
        failure = await service.submit(request(store, 'def on_bars(ctx, bars):\n    raise RuntimeError("specific failure")'))
        failed = await wait_for(service, failure.id, lambda job: job.status == 'failed')
        assert 'strategy.py' in failed.error and 'specific failure' in failed.error
        assert 'specific failure' in service.output(failure.id)['stderr']
    finally:
        await service.close()
    restored = ResearchService(Store(tmp_path))
    assert restored.job(first.id).status == 'completed'
    assert restored.result(first.id).fills == result.fills
    await restored.close()


async def test_cancellation_kills_owned_child_and_queue_never_executes(tmp_path):
    store = Store(tmp_path)
    service = ResearchService(store, concurrency=1)
    source = '''
import subprocess,sys,time
child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
print("child", child.pid)
def on_bars(ctx, bars):
    while True:
        time.sleep(.1)
'''
    try:
        running = await service.submit(request(store, source))
        await wait_for(service, running.id, lambda j: j.status == 'running')
        deadline = time.monotonic()+10
        while 'child ' not in service.output(running.id)['stdout'] and time.monotonic() < deadline:
            await asyncio.sleep(.05)
        child_pid = int(service.output(running.id)['stdout'].split('child ')[1].split()[0])
        child = psutil.Process(child_pid)
        queued = await service.submit(request(store, 'raise RuntimeError("must not run")\ndef on_bars(ctx,bars): pass'))
        assert service.job(queued.id).status == 'queued'
        await service.cancel(queued.id)
        await wait_for(service, queued.id, lambda j: j.status == 'cancelled', timeout=2)
        assert service.job(running.id).status == 'running'
        start = time.monotonic()
        await service.cancel(running.id)
        await wait_for(service, running.id, lambda j: j.status == 'cancelled')
        assert time.monotonic()-start < 4
        await wait_for(service, queued.id, lambda j: j.status == 'cancelled')
        assert not (service.directory(queued.id)/'outcome.json').exists()
        assert not child.is_running() or child.status() == psutil.STATUS_ZOMBIE
        assert not service.processes
    finally:
        await service.close()


async def test_deadline_shutdown_restart_and_snapshot_tamper(tmp_path):
    store = Store(tmp_path)
    service = ResearchService(store)
    try:
        timed = await service.submit(request(store, 'def on_bars(ctx,bars):\n    while True: pass', deadline_seconds=1))
        failed = await wait_for(service, timed.id, lambda j: j.status == 'failed')
        assert 'deadline' in failed.error
        interrupted = await service.submit(request(store, 'def on_bars(ctx,bars):\n    while True: pass'))
        await wait_for(service, interrupted.id, lambda j: j.status == 'running')
    finally:
        await service.close()
    assert service.job(interrupted.id).status == 'interrupted'
    assert not service.processes
    restored = ResearchService(store)
    assert restored.job(interrupted.id).status == 'interrupted'
    path = restored.directory(timed.id)/'strategy.py'
    path.write_text('changed')
    with pytest.raises(ValueError, match='snapshot changed'):
        restored.verify_snapshot(timed.id)
    await restored.close()


async def test_memory_monitor_bounds_worker(tmp_path):
    store = Store(tmp_path)
    service = ResearchService(store)
    try:
        job = await service.submit(request(store, 'def on_bars(ctx,bars):\n    value = bytearray(300*1024*1024)\n    while True: pass', memory_mb=256))
        failed = await wait_for(service, job.id, lambda j: j.status == 'failed')
        assert 'memory' in failed.error
        assert failed.peak_memory_bytes > 256*1024*1024
    finally:
        await service.close()


async def test_process_monitor_failure_refuses_to_launch(tmp_path, monkeypatch):
    import backend.research as module
    store = Store(tmp_path)
    service = ResearchService(store)
    monkeypatch.setattr(psutil.Process, 'children', lambda *a, **k: (_ for _ in ()).throw(PermissionError('monitor blocked')))
    monkeypatch.setattr(module.subprocess, 'Popen', lambda *a, **k: pytest.fail('Must refuse before starting a worker'))
    try:
        job = await service.submit(request(store, 'def on_bars(ctx,bars): pass'))
        failed = await wait_for(service, job.id, lambda j: j.status == 'failed')
        assert 'monitor blocked' in failed.error
        assert not service.processes
    finally:
        await service.close()


async def test_abrupt_parent_exit_stops_worker_and_its_child(tmp_path):
    import subprocess
    import sys

    from backend.research import APP_ROOT
    from backend.worker_process import ProcessTree
    parent_source = '''
import asyncio,json,sys
from pathlib import Path
from backend.research import ResearchService
from backend.store import Store
from tests.test_research_workers import request
async def main():
    store = Store(Path(sys.argv[1]))
    service = ResearchService(store)
    source = 'import subprocess,sys\\nchild=subprocess.Popen([sys.executable,"-c","import time;time.sleep(60)"])\\nprint(child.pid)\\ndef on_bars(ctx,bars):\\n    while True: pass'
    job = await service.submit(request(store, source))
    while service.job(job.id).status != 'running':
        await asyncio.sleep(.05)
    (store.root/'parent-ready.json').write_text(json.dumps({'run':job.id}))
    await asyncio.sleep(60)
asyncio.run(main())
'''
    parent = await asyncio.to_thread(subprocess.Popen, [sys.executable, '-c', parent_source, str(tmp_path)],
        cwd=APP_ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    tree = ProcessTree(psutil.Process(parent.pid))
    worker_tree = None
    try:
        ready = tmp_path/'parent-ready.json'
        deadline = time.monotonic()+12
        while not ready.exists() and time.monotonic() < deadline:
            await asyncio.sleep(.05)
        assert ready.exists()
        import json
        job_id = json.loads(ready.read_text())['run']
        directory = tmp_path/'runs'/job_id
        identity = json.loads((directory/'worker-identity.json').read_text())
        worker = psutil.Process(identity['pid'])
        assert worker.create_time() == identity['created_at']
        worker_tree = ProcessTree(worker)
        output = directory/'stdout.txt'
        while (not output.exists() or not output.read_text().strip()) and time.monotonic() < deadline:
            await asyncio.sleep(.05)
        child = psutil.Process(int(output.read_text().strip()))
        parent.kill()
        await asyncio.to_thread(parent.wait, timeout=3)
        end = time.monotonic()+5
        while (worker.is_running() and worker.status() != psutil.STATUS_ZOMBIE) and time.monotonic() < end:
            await asyncio.sleep(.05)
        assert not worker.is_running() or worker.status() == psutil.STATUS_ZOMBIE
        assert not child.is_running() or child.status() == psutil.STATUS_ZOMBIE
        restored = ResearchService(Store(tmp_path))
        assert restored.job(job_id).status == 'interrupted'
        await restored.close()
    finally:
        if worker_tree:
            await asyncio.to_thread(worker_tree.terminate)
        await asyncio.to_thread(tree.terminate)
        await asyncio.to_thread(parent.wait, timeout=3)
