"""Dedicated Python entry point. Launched only by the explicit research Run action."""
import hashlib
import io
import json
import os
import signal
import sys
import threading
import time
import traceback
from pathlib import Path

import pandas as pd
import psutil

from .models import Bar, Dataset, DatasetView
from .research_models import ResearchRequest
from .research_results import build_result
from .sdk import ScriptRuntime
from .simulation import Simulation
from .store import atomic_write
from .worker_process import ProcessTree


class BoundedOutput(io.TextIOBase):
    def __init__(self, path, limit=1000000):
        self.file = path.open('w', encoding='utf-8')
        self.remaining = limit
        self.truncated = False
        self.lock = threading.Lock()

    def write(self, text):
        with self.lock:
            if self.remaining > 0:
                encoded = text.encode('utf-8', errors='replace')[:self.remaining]
                self.file.write(encoded.decode('utf-8', errors='replace'))
                self.remaining -= len(encoded)
            elif not self.truncated:
                self.file.write('\n[Output capped at 1 MB]\n')
                self.truncated = True
            self.file.flush()
        return len(text)

    def flush(self):
        if not self.file.closed:
            self.file.flush()


def run(directory: Path, parent_pid: int, parent_created: float):
    directory = directory.resolve()
    os.chdir(directory)
    stdout, stderr = BoundedOutput(directory/'stdout.txt'), BoundedOutput(directory/'stderr.txt')
    sys.stdout, sys.stderr = stdout, stderr
    owner = ProcessTree(psutil.Process())
    stop = threading.Event()

    def watchdog():
        while not stop.wait(.25):
            try:
                owner.refresh()
            except (PermissionError, psutil.AccessDenied):
                pass
            try:
                parent = psutil.Process(parent_pid)
                live = parent.is_running() and parent.create_time() == parent_created
            except psutil.NoSuchProcess:
                live = False
            if not live:
                owner.terminate(include_root=False)
                if os.name == 'posix' and os.getpgrp() == os.getpid():
                    os.killpg(os.getpgrp(), signal.SIGKILL)
                os._exit(3)

    thread = threading.Thread(target=watchdog, name='research-parent-watchdog', daemon=True)
    thread.start()
    runtime = None
    completed_events, total_events = 0, 0

    def save_progress():
        atomic_write(directory/'progress.json', json.dumps({'completed_events': completed_events,
            'total_events': total_events, 'logs': runtime.ctx.logs[-200:] if runtime else [],
            'plots': runtime.ctx.plots[-500:] if runtime else []}))
    try:
        manifest = json.loads((directory/'manifest.json').read_text())
        for filename, digest in manifest['files'].items():
            if hashlib.sha256((directory/filename).read_bytes()).hexdigest() != digest:
                raise ValueError(f'Snapshot content changed: {filename}')
        request = ResearchRequest.model_validate_json((directory/'request.json').read_text())
        views = []
        for entry in manifest['datasets']:
            meta = Dataset.model_validate(entry['metadata'])
            frame = pd.read_parquet(directory/entry['file'])
            records = frame.astype(object).where(pd.notna(frame), None).to_dict(orient='records')
            views.append(DatasetView(dataset=meta, bars=[Bar.model_validate(record) for record in records]))
        simulation = Simulation(views, request.settings, request.actions)
        runtime = ScriptRuntime(simulation, request.script, request.parameters)
        updated = 0

        def progress(done, total):
            nonlocal updated, completed_events, total_events
            completed_events, total_events = done, total
            now = time.monotonic()
            if now-updated >= .2 or done == total:
                save_progress()
                updated = now

        simulation.advance(on_bars=runtime.on_bars, on_progress=progress)
        runtime.finish()
        save_progress()
        result = build_result(simulation, runtime.ctx.logs, runtime.ctx.plots)
        atomic_write(directory/'result.json', result.model_dump_json())
        atomic_write(directory/'outcome.json', json.dumps({'status': 'completed'}))
    except BaseException as exc:  # noqa: BLE001 -- process boundary retains script exceptions/SystemExit
        detail = ''.join(traceback.format_exception(exc))[-16000:]
        stderr.write(detail)
        save_progress()
        atomic_write(directory/'outcome.json', json.dumps({'status': 'failed', 'error': detail}))
    finally:
        stop.set()
        thread.join(timeout=1)
        remaining = owner.terminate(include_root=False)
        if remaining:
            atomic_write(directory/'outcome.json', json.dumps({'status': 'failed', 'error': 'Owned script child processes could not be stopped'}))
        stdout.file.close()
        stderr.file.close()


if __name__ == '__main__':
    run(Path(sys.argv[1]), int(sys.argv[2]), float(sys.argv[3]))
