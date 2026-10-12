"""Read-only public-provider verification. Does not use account keys."""
import asyncio
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.providers import HistoryRequest, ProviderManager
from backend.store import Store, atomic_write
from backend.streams import QuoteHub


async def main():
    root = Path(__file__).resolve().parent.parent
    provider = ProviderManager(Store(root / 'data'))
    try:
        matches = await provider.instruments('coinbase', 'BTC-USD')
        instrument = next(i for i in matches if i.symbol == 'BTC-USD')
        end = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        dataset = await provider.history(HistoryRequest(provider='coinbase', instrument=instrument, interval='1d',
                                                        start=int((end - timedelta(days=90)).timestamp()), end=int(end.timestamp())))
        quote = await provider.quote('coinbase', instrument)
        hub = QuoteHub(provider)
        token, queue = await hub.subscribe('coinbase', instrument)
        try:
            async def next_quote():
                while True:
                    event = await queue.get()
                    if event['type'] == 'quote':
                        return event['quote']
            streamed = await asyncio.wait_for(next_quote(), 20)
        finally:
            await hub.unsubscribe(token)
            await hub.close()
        report = {'date': datetime.now(UTC).isoformat(), 'status': 'passed', 'provider': 'Coinbase Exchange public API',
                  'instrument': instrument.id, 'dataset_id': dataset.id, 'bars': dataset.row_count,
                  'quote_timestamp': quote.timestamp, 'stream_quote_timestamp': streamed['timestamp'], 'checks': ['Product discovery', 'Historical daily candles', 'Latest public ticker', 'Live public WebSocket quote and unsubscribe cleanup'],
                  'limitations': ['No Alpaca or Alpha Vantage credentials used']}
    except Exception as error:  # noqa: BLE001 - Persist failed verification before exiting nonzero.
        report = {'date': datetime.now(UTC).isoformat(), 'status': 'failed', 'error': str(error)}
    finally:
        await provider.close()
    atomic_write(root / 'evidence' / 'coinbase-live-check.json', json.dumps(report, indent=2))
    print(json.dumps(report))
    if report['status'] != 'passed':
        raise SystemExit(1)


asyncio.run(main())
