"""Restart a real service over a credential-free snapshot; optionally keep its UI open."""
import hashlib
import json
import shutil
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = ROOT/'evidence/recovery'
EVIDENCE.mkdir(exist_ok=True)
snapshot = Path(tempfile.mkdtemp(prefix='saved-work-', dir=EVIDENCE))
# An explicit allowlist excludes provider configuration and keys from the copy.
with (sqlite3.connect(f'file:{ROOT / "data/workbench.sqlite3"}?mode=ro', uri=True) as source,
      sqlite3.connect(snapshot/'workbench.sqlite3') as destination):
    source.backup(destination)
for name in ('datasets', 'runs'):
    shutil.copytree(ROOT/'data'/name, snapshot/name)

PORT = 8001
client = httpx.Client(base_url=f'http://127.0.0.1:{PORT}/api', timeout=10,
                     headers={'X-Workbench-Request': '1'})
owned = None
log = (snapshot/'service.log').open('w')


def call(path, data=None, method='POST'):
    response = client.get(path) if data is None else client.request(method, path, json=data)
    response.raise_for_status()
    return response.json()


def start():
    global owned
    code = ('from pathlib import Path; import sys,uvicorn; import backend.app as module; '
            'module.ORIGINS.add("http://127.0.0.1:8001"); '
            'uvicorn.run(module.create_app(Path(sys.argv[1])),host="127.0.0.1",port=8001)')
    owned = subprocess.Popen([sys.executable, '-c', code, str(snapshot)], cwd=ROOT,
                             stdout=log, stderr=log)
    deadline = time.monotonic()+15
    while time.monotonic() < deadline:
        if owned.poll() is not None:
            raise RuntimeError('Owned recovery service exited during startup')
        try:
            if call('/health')['status'] == 'ok':
                return owned.pid
        except httpx.HTTPError:
            pass
        time.sleep(.05)
    raise TimeoutError('Recovery service startup timed out')


def stop():
    if owned is not None and owned.poll() is None:
        owned.terminate()
        try:
            owned.wait(timeout=10)
        except subprocess.TimeoutExpired:
            owned.kill()
            owned.wait(timeout=5)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def interrupted(*_):
    raise KeyboardInterrupt


signal.signal(signal.SIGTERM, interrupted)
signal.signal(signal.SIGINT, interrupted)
try:
    first_pid = start()
    workspace = call('/workspaces/default')
    dataset = call('/examples/dataset', {})
    bars = call('/datasets/'+dataset['id'])['bars']
    script_id = str(uuid4())
    script = {'id': script_id, 'name': 'Recovery verification', 'kind': 'strategy',
              'source': 'def on_bars(ctx, bars):\n    ctx.log(ctx.timestamp)',
              'parameters': {}, 'subscriptions': [], 'revision': 0}
    saved_script = call('/scripts/'+script_id, script, 'PUT')
    call('/scripts/'+script_id, {**saved_script, 'source': script['source']+'\n'}, 'PUT')
    drawing = {'id': str(uuid4()), 'instrument_id': dataset['instrument']['id'], 'kind': 'trend',
               'anchors': [{'time': b['start'], 'price': b['close']} for b in bars[2:4]],
               'color': '#70b8f0', 'width': 2, 'opacity': 1, 'label': 'Recovery trend',
               'quantity': '1', 'levels': [], 'locked': True, 'visible': True}
    workspace.update(layout=1, active_chart=0, bottom_open=True)
    workspace['charts'][0].update(dataset_id=dataset['id'], follow_live=False,
                                   drawings=[drawing], indicators=[])
    call('/workspaces/default', workspace, 'PUT')
    account_id = json.loads((ROOT/'evidence/browser/candles-paper-report.json').read_text())['accountId']
    job_id = next(job['id'] for job in call('/research') if job['status'] == 'completed')

    def capture():
        return {'workspace': call('/workspaces/default'), 'scriptVersions': call(f'/scripts/{script_id}/versions'),
                'paper': call('/accounts/'+account_id), 'result': call(f'/research/{job_id}/result'),
                'alertHistory': call('/alert-events')}

    before = capture()
    assert before['paper']['account']['paused']
    assert any(float(p['quantity']) != 0 for p in before['paper']['portfolio']['positions'])
    assert len(before['scriptVersions']) == 2 and before['alertHistory']
    began = time.monotonic()
    stop()
    try:
        call('/health')
    except httpx.ConnectError:
        pass
    else:
        raise AssertionError('Old service still responds after its owned process exited')
    second_pid = start()
    after = capture()
    assert {k: digest(v) for k, v in before.items()} == {k: digest(v) for k, v in after.items()}
    report = {'status': 'passed', 'date': datetime.now(UTC).isoformat(),
              'restart_seconds': time.monotonic()-began, 'process_ids': [first_pid, second_pid],
              'observed_offline_and_recovery': True, 'snapshot_directory': str(snapshot.relative_to(ROOT)),
              'hashes': {k: digest(v) for k, v in after.items()},
              'account_id': account_id, 'job_id': job_id, 'script_id': script_id,
              'checks': ['Credential-free SQLite backup plus immutable datasets and saved runs',
                         'Actual process exit and new process startup',
                         'Workspace and locked time/price drawing unchanged', 'Two exact source versions unchanged',
                         'Previously filled Coinbase-source paper position unchanged',
                         'Completed result and nonempty alert history unchanged'],
              'browser_restoration': 'pending separate UI inspection'}
    (EVIDENCE/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report), flush=True)
    if '--serve' in sys.argv:
        print('Recovery copy remains available at http://127.0.0.1:8001 for UI inspection.', flush=True)
        while True:
            time.sleep(1)
except KeyboardInterrupt:
    pass
finally:
    stop()
    client.close()
    log.close()
