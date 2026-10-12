"""Serve an isolated, credential-free synthetic workspace for native browser checks."""
import json
import sys
import tempfile
from pathlib import Path

import uvicorn

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from backend.app import ORIGINS, create_app
from backend.fixtures import example_dataset
from backend.models import StrategyDefinition, Watchlist, WatchlistItem, Workspace
from backend.store import Store

directory = ROOT / 'evidence' / 'keyboard'
directory.mkdir(parents=True, exist_ok=True)
data = Path(tempfile.mkdtemp(prefix='workspace-', dir=directory))
store = Store(data)
first = example_dataset(store)
second = store.save_dataset(first.instrument.model_copy(update={'id': 'EXAMPLE:LAST', 'symbol': 'LAST',
    'name': 'Last keyboard navigation fixture'}), '1d', store.bars(first.id), first.limitations)
small = Watchlist(id='small', name='Small verification list', items=[WatchlistItem(instrument_id=first.instrument.id)])
large = Watchlist(id='large', name='Large verification list', sections=['Synthetic identities'], items=[
    WatchlistItem(instrument_id=first.instrument.id),
    *[WatchlistItem(instrument_id=f'KEYBOARD:{i:04}', section='Synthetic identities') for i in range(1199)],
    WatchlistItem(instrument_id=second.instrument.id, section='Synthetic identities')])
workspace = Workspace(watchlists=[small, large], active_watchlist=small.id)
workspace.charts[0].dataset_id = first.id
store.save_document('workspace', workspace.id, workspace.model_dump(mode='json'), 0)
script = StrategyDefinition(id='keyboard-strategy', name='Keyboard verification strategy', kind='strategy', source='''PARAMETERS = {"quantity": {"type": "int", "default": 1, "minimum": 1}}

def on_bars(ctx, bars):
    if not ctx.state.get("submitted"):
        for identity in bars:
            ctx.order(identity, "buy", ctx.parameters["quantity"])
        ctx.state["submitted"] = True
    ctx.log(ctx.clock)
''')
store.save_document('script', script.id, script.model_dump(mode='json'), 0)
metadata = {'url': 'http://127.0.0.1:8001/', 'data_directory': str(data.relative_to(ROOT)),
            'watchlist_sizes': [1, 1201], 'source': 'Deterministic synthetic data; no provider configuration copied',
            'dataset_ids': [first.id, second.id], 'bars_per_dataset': 365}
(directory / 'workspace.json').write_text(json.dumps(metadata, indent=2)+'\n')
print(json.dumps(metadata), flush=True)
ORIGINS.add(metadata['url'].rstrip('/'))
uvicorn.run(create_app(data), host='127.0.0.1', port=8001, access_log=False, log_level='warning')
