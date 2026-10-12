"""Bounded real-provider checks through the local service; never fetch credentials."""
import asyncio
import json
import sys
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from pathlib import Path

import httpx
from websockets.asyncio.client import connect

ROOT = Path(__file__).resolve().parent.parent
BASE = 'http://127.0.0.1:8000/api'


def is_live_trade(event, instrument_id, started_at, received_at):
    quote = event.get('quote', {})
    return (event.get('type') == 'quote' and quote.get('source') == 'alpaca'
            and quote.get('feed') == 'iex' and quote.get('instrument_id') == instrument_id
            and quote.get('freshness') == 'live'
            and started_at <= quote.get('timestamp', 0) <= received_at)


async def main():
    report = {'date': datetime.now(UTC).isoformat(), 'kind': 'actual configured provider requests',
              'history': [], 'stream': {}, 'errors': []}
    alpaca_only = '--alpaca-only' in sys.argv
    stream_only = '--stream-only' in sys.argv
    if alpaca_only or stream_only:
        previous = json.loads((ROOT/'evidence/configured-providers.json').read_text())
        report['history'] = [item for item in previous['history']
                             if stream_only or item['provider'] != 'alpaca']
        report['retained_alpha_vantage_check_date'] = previous.get(
            'retained_alpha_vantage_check_date', previous['date'])
        if stream_only:
            report['retained_history_check_date'] = previous.get(
                'retained_history_check_date', previous['date'])
    end = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    instruments = {}
    async with httpx.AsyncClient(base_url=BASE, timeout=90,
                                 headers={'X-Workbench-Request': '1'}) as client:
        if stream_only:
            saved = next(item for item in report['history']
                         if item['provider'] == 'alpaca' and item['symbol'] == 'AAPL')
            response = await client.get('/datasets/'+saved['id'])
            response.raise_for_status()
            instruments['AAPL'] = response.json()['dataset']['instrument']
        for provider, symbol in [('alpaca', 'AAPL'), ('alpaca', 'SPY'), ('alpha-vantage', 'EUR/USD')]:
            if stream_only or (alpaca_only and provider != 'alpaca'):
                continue
            try:
                response = await client.get(f'/providers/{provider}/instruments', params={'query': symbol})
                if response.status_code != 200:
                    report['errors'].append({'provider': provider, 'symbol': symbol,
                                             'http_status': response.status_code, 'detail': response.json()})
                    continue
                instrument = next(item for item in response.json() if item['symbol'] == symbol)
                instruments[symbol] = instrument
                response = await client.post('/history', json={'provider': provider, 'instrument': instrument,
                    'interval': '1d', 'start': int((end-timedelta(days=90)).timestamp()), 'end': int(end.timestamp())})
                if response.status_code != 200:
                    report['errors'].append({'provider': provider, 'symbol': symbol,
                                             'http_status': response.status_code, 'detail': response.json()})
                    continue
                dataset = response.json()
                view = (await client.get('/datasets/'+dataset['id'])).json()
                bars = view['bars']
                assert bars and all(bar['source'] == provider and bar['adjustment'] == 'raw' for bar in bars)
                assert all(a['start'] < b['start'] for a, b in pairwise(bars))
                assert all(bar['volume'] is None for bar in bars) if provider == 'alpha-vantage' else True
                aggregates = {}
                for interval in ('1w', '1mo'):
                    aggregated = await client.post(f'/datasets/{dataset["id"]}/aggregate', params={'interval': interval})
                    aggregated.raise_for_status()
                    aggregates[interval] = aggregated.json()['row_count']
                report['history'].append({'provider': provider, 'symbol': symbol, 'id': dataset['id'],
                    'bars': len(bars), 'feed': dataset['feed'], 'timezone': dataset['instrument']['timezone'],
                    'hash': dataset['hash'], 'aggregated_bars': aggregates})
            except Exception as exc:  # noqa: BLE001 - retain failed verification without credentials
                # Only local API addresses are used by this script. Never retain provider response bodies.
                report['errors'].append({'provider': provider, 'symbol': symbol, 'error_type': type(exc).__name__})
        if 'AAPL' in instruments:
            subscription = 'quote:configured-verification'
            packets = []
            live_trade = None
            try:
                started_at = int(datetime.now(UTC).timestamp())
                async with connect('ws://127.0.0.1:8000/api/events', origin='http://127.0.0.1:5173') as socket:
                    await socket.send(json.dumps({'action': 'subscribe', 'subscription': subscription,
                        'provider': 'alpaca', 'instrument': instruments['AAPL']}))
                    deadline = asyncio.get_running_loop().time()+20
                    while asyncio.get_running_loop().time() < deadline:
                        try:
                            event = json.loads(await asyncio.wait_for(socket.recv(), deadline-asyncio.get_running_loop().time()))
                        except TimeoutError:
                            break
                        packets.append(event)
                        if is_live_trade(event, instruments['AAPL']['id'], started_at,
                                         int(datetime.now(UTC).timestamp())):
                            live_trade = event['quote']
                            break
                    await socket.send(json.dumps({'action': 'unsubscribe', 'subscription': subscription}))
                    while True:
                        event = json.loads(await asyncio.wait_for(socket.recv(), 5))
                        if event['type'] == 'unsubscribed':
                            break
                    report['stream'] = {'provider': 'alpaca', 'authenticated_connection': any(
                        event.get('status') == 'connected' for event in packets),
                        'quote_received': any(event['type'] == 'quote' for event in packets),
                        'live_trade_received': live_trade is not None,
                        'started_at': started_at,
                        'unsubscribe_acknowledged': True, 'events': packets,
                        'observation_seconds': 20, 'limitation': 'Connection status proves authentication. Live trade delivery requires Alpaca/IEX data for this instrument timestamped during this check; cached or stale quotes cannot satisfy it. No generated substitute quotes.'}
            except Exception as exc:  # noqa: BLE001 - persist bounded stream failure evidence
                report['stream'] = {'error_type': type(exc).__name__}
    report['history_status'] = 'passed' if len(report['history']) == 3 and not report['errors'] else 'partial'
    report['status'] = 'passed' if (report['history_status'] == 'passed'
        and report['stream'].get('authenticated_connection')
        and report['stream'].get('live_trade_received')
        and report['stream'].get('unsubscribe_acknowledged')) else 'partial'
    (ROOT/'evidence/configured-providers.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report))


if __name__ == '__main__':
    asyncio.run(main())
