"""20 instruments, ten years of explicit synthetic daily data; no market claim."""
import asyncio
import json
import math
import platform
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import exchange_calendars as xcals
import psutil

from backend.models import Bar, Instrument, StrategyDefinition
from backend.research import ResearchService
from backend.research_models import ExecutionSettings, ResearchRequest, WorkerLimits
from backend.store import Store

ROOT = Path(__file__).resolve().parent.parent


async def main():
    store = Store(ROOT/'data'/'benchmark-research')
    calendar = xcals.get_calendar('XNYS', start='2015-01-01', end='2024-12-31')
    schedule = calendar.schedule.loc['2015-01-01':'2024-12-31']
    dataset_ids = []
    for index in range(20):
        identity = f'BENCH:ASSET{index:02d}'
        instrument = Instrument(id=identity, symbol=f'ASSET{index:02d}', name='Synthetic portfolio benchmark',
            exchange='BENCH', asset_class='stock', quote_currency='USD', timezone='America/New_York', calendar='XNYS')
        bars = []
        for day, (_, row) in enumerate(schedule.iterrows()):
            price = round(50+index*3+day*.008+3*math.sin(day/30+index), 2)
            bars.append(Bar(start=int(row['open'].timestamp()), end=int(row['close'].timestamp()), open=price,
                high=price+2, low=price-2, close=round(price+.5*math.sin(day), 2), volume=100000,
                source='fixture', feed='ten-year-benchmark'))
        dataset_ids.append(store.save_dataset(instrument, '1d', bars, ['Synthetic benchmark prices; actual XNYS session times.']).id)
    source = (ROOT/'examples'/'multi_asset_rebalance.py').read_text()
    request = ResearchRequest(name='20-instrument ten-year synthetic benchmark',
        script=StrategyDefinition(id='benchmark', name='Monthly rebalance', kind='strategy', source=source),
        dataset_ids=dataset_ids, settings=ExecutionSettings(allow_fixture_data=True),
        limits=WorkerLimits(deadline_seconds=300, memory_mb=2048))
    service = ResearchService(store)
    try:
        submitted = time.perf_counter()
        job = await service.submit(request)
        snapshot_seconds = time.perf_counter()-submitted
        while service.job(job.id).status not in ('completed', 'failed', 'interrupted', 'cancelled'):
            await asyncio.sleep(.25)
        job = service.job(job.id)
        if job.status != 'completed':
            raise RuntimeError(job.error)
        result = service.result(job.id)
        report = {'status': 'passed', 'hardware': {'platform': platform.platform(), 'machine': platform.machine(),
            'logical_cpus': psutil.cpu_count(), 'memory_bytes': psutil.virtual_memory().total},
            'workload': {'instruments': 20, 'bars_each': len(schedule), 'bars_total': len(schedule)*20,
                'start': str(schedule.index[0]), 'end': str(schedule.index[-1]), 'strategy': 'Monthly equal-weight rebalance',
                'synthetic': True}, 'run_id': job.id, 'dataset_hashes': dataset_ids,
            'snapshot_seconds': snapshot_seconds, 'worker_seconds': job.elapsed_seconds,
            'sampled_peak_worker_tree_rss_bytes': job.peak_memory_bytes, 'sampling_seconds': .25,
            'orders': len(result.orders), 'fills': len(result.fills), 'equity_points': len(result.equity),
            'result_hash': job.result_hash, 'snapshot_hash': job.snapshot_hash,
            'limitations': ['Synthetic prices measure computation, not market returns.',
                'Memory is sampled resident memory of the worker and observed descendants, not all application processes.']}
        path = ROOT/'evidence'/'performance'/'research.json'
        path.parent.mkdir(exist_ok=True, parents=True)
        path.write_text(json.dumps(report, indent=2)+'\n')
        print(json.dumps({key: value for key, value in report.items() if key != 'dataset_hashes'}))
    finally:
        await service.close()


asyncio.run(main())
