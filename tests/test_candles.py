import asyncio
from datetime import datetime

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.accounts import AccountService
from backend.alerts import AlertService
from backend.app import create_app
from backend.candles import CandleService, series_key
from backend.models import AlertDefinition, Bar
from backend.providers import ProviderError, ProviderManager
from backend.research_models import AccountRequest, ExecutionSettings, OrderRequest
from backend.store import Store
from tests.test_providers import crypto, no_wait

T = 1735689600


def candle(index, close=10, complete=True):
    return Bar(start=T+index*60, end=T+(index+1)*60, open=close, high=close+1, low=close-1,
               close=close, volume=2, complete=complete, source='coinbase', feed='exchange')


def setup(tmp_path, prices=(10, 10), partial=False):
    store = Store(tmp_path)
    data = store.save_dataset(crypto(), '1m', [candle(i, p, not (partial and i == len(prices)-1))
        for i, p in enumerate(prices)], [])
    calls = []
    rows = [candle(i, p) for i, p in enumerate(prices)]

    def handler(request):
        calls.append(request)
        start = int(datetime.fromisoformat(request.url.params['start']).timestamp())
        end = int(datetime.fromisoformat(request.url.params['end']).timestamp())
        return httpx.Response(200, json=[[b.start, b.low, b.high, b.open, b.close, b.volume]
            for b in rows if start <= b.start < end])
    manager = ProviderManager(store, httpx.MockTransport(handler), sleep=no_wait)
    clock = [T+len(prices)*60]
    service = CandleService(store, manager, clock=lambda: clock[0])
    return store, data, manager, service, rows, calls, clock


@pytest.mark.asyncio
async def test_completed_refresh_drives_alert_and_paper_without_rewriting_inputs(tmp_path, monkeypatch):
    store, data, provider, service, rows, calls, clock = setup(tmp_path)
    from backend import accounts
    monkeypatch.setattr(accounts.time, 'time', lambda: clock[0])
    alerts, paper = AlertService(store), AccountService(store)
    alert = alerts.save(AlertDefinition(id='cross', name='Cross 10', dataset_id=data.id,
        threshold=10, condition='crosses_above', recurring=True))
    state = paper.create(AccountRequest(name='Feed account', mode='paper', dataset_ids=[data.id],
        settings=ExecutionSettings(initial_capital=1000)))
    state = paper.order(state.account.id, OrderRequest(instrument_id=crypto().id, side='buy', quantity=2), state.account.revision)
    rows.append(candle(2, 12)); clock[0] += 60
    refreshed = await service.refresh(data)
    assert refreshed.status == 'current' and refreshed.dataset.row_count == 3
    assert store.bars(data.id) == [candle(0), candle(1)]
    alerts.evaluate_all()
    assert len(alerts.events()) == 1 and alerts.events()[0].alert_id == alert.id
    state = paper.refresh_paper(state.account.id, state.account.revision)
    assert state.fills[0].price == 12 and state.fills[0].time == T+120
    assert state.portfolio.positions[0].quantity == 2
    await service.refresh(data); alerts.evaluate_all()
    assert len(alerts.events()) == 1 and len(store.datasets()) == 2
    assert len(calls) == 2
    restored = CandleService(store, provider).status([data.id])[data.id]
    assert restored.dataset == refreshed.dataset and restored.last_success
    await provider.close()


@pytest.mark.asyncio
async def test_partial_completion_same_last_end_and_revised_prefix_stop_consumers(tmp_path, monkeypatch):
    store, data, provider, service, rows, _, clock = setup(tmp_path, partial=True)
    clock[0] = T+90
    from backend import accounts
    monkeypatch.setattr(accounts.time, 'time', lambda: clock[0])
    paper = AccountService(store)
    state = paper.create(AccountRequest(name='Partial end', mode='paper', dataset_ids=[data.id]))
    assert state.account.cursor == T+60
    await service.refresh(data)
    assert service.status([data.id])[data.id].dataset.id == data.id
    clock[0] = T+120
    updated = await service.refresh(data)
    assert updated.dataset.last_end == data.last_end and updated.dataset.id != data.id
    state = paper.refresh_paper(state.account.id, state.account.revision)
    assert state.account.cursor == T+120
    rows[1] = candle(1, 11); rows.append(candle(2, 12)); clock[0] += 60
    revised = await service.refresh(data)
    assert revised.revised_history and store.bars(data.id)[1].close == 10
    with pytest.raises(ValueError, match='history changed'):
        paper.refresh_paper(state.account.id, state.account.revision)
    await provider.close()


@pytest.mark.asyncio
async def test_shared_interests_cancel_and_quota_backoff_survive_restart(tmp_path):
    store, data, provider, service, _, _, clock = setup(tmp_path)
    began, stopped = asyncio.Event(), asyncio.Event()

    async def blocked(request):
        began.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()
    provider.fetch_history = blocked
    one, two = service.subscribe([data.id]), service.subscribe([data.id])
    await service.cycle(); await began.wait()
    assert len(service.tasks) == 1
    service.unsubscribe(one); await service.cycle()
    assert not stopped.is_set()
    service.unsubscribe(two); await service.cycle()
    assert stopped.is_set() and not service.tasks

    async def quota(request):
        raise ProviderError('coinbase', 'quota', 'Fixture quota error')
    provider.fetch_history = quota
    status = await service.refresh(data)
    assert status.status == 'stale' and status.dataset == data and status.next_check > clock[0]
    restarted = CandleService(store, provider, clock=lambda: clock[0])
    restarted.subscribe([data.id]); await restarted.cycle()
    assert not restarted.tasks
    await service.close(); await restarted.close(); await provider.close()


@pytest.mark.asyncio
async def test_changed_feed_is_rejected_and_background_interests_are_deduplicated(tmp_path):
    store, data, provider, service, rows, _, _ = setup(tmp_path)
    alert = AlertService(store).save(AlertDefinition(id='a', name='A', dataset_id=data.id, threshold=12))
    async def wrong_feed(request):
        return crypto(), [bar.model_copy(update={'feed': 'other'}) for bar in rows], []
    provider.fetch_history = wrong_feed
    status = await service.refresh(data)
    assert status.status == 'stale' and 'metadata changed' in status.message and len(store.datasets()) == 1
    service.subscribe([data.id])
    service.states[series_key(data)].next_check = 0
    await service.cycle()
    assert service.background == [data.id] and len(service.tasks) == 1
    await asyncio.gather(*service.tasks.values())
    AlertService(store).save(alert.model_copy(update={'enabled': False}))
    await service.close(); await provider.close()


def test_candle_socket_owns_subscriptions_and_validates_origin(tmp_path):
    store, data, provider, _, _, _, _ = setup(tmp_path)
    app = create_app(store.root)
    # No lifespan: this boundary check intentionally makes no provider requests.
    with TestClient(app).websocket_connect('/api/candles/events', headers={'origin': 'http://127.0.0.1:5173'}) as socket:
        socket.send_json({'action': 'subscribe', 'dataset_ids': [data.id]})
        message = socket.receive_json()
        assert message['subscription'] == 'candles' and message['states'][data.id]['dataset']['id'] == data.id
        assert len(app.state.candles.consumers) == 1
        socket.send_json({'action': 'unsubscribe'})
        assert socket.receive_json()['type'] == 'unsubscribed'
    assert not app.state.candles.consumers
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect), TestClient(app).websocket_connect('/api/candles/events', headers={'origin': 'https://elsewhere.test'}):
        pass
    asyncio.run(provider.close())
    asyncio.run(app.state.providers.close())
