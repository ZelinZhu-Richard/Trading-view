import pytest

from backend.accounts import AccountService
from backend.research_models import AccountRequest, ExecutionSettings, OrderRequest
from backend.store import ConflictError, Store
from tests.test_simulation import series


def setup(tmp_path, mode='replay', count=4):
    store = Store(tmp_path)
    view = series(prices=[(10, 11, 9, 10)]*count)
    data = store.save_dataset(view.dataset.instrument, '1m', view.bars, [])
    service = AccountService(store)
    account = service.create(AccountRequest(name='Account test', mode=mode, dataset_ids=[data.id],
        settings=ExecutionSettings(allow_fixture_data=True, initial_capital=100)))
    return store, service, account, view


def test_replay_step_orders_same_engine_persistence_and_seek_drops_future(tmp_path):
    store, service, state, _ = setup(tmp_path)
    identity = state.account.id
    assert state.account.cursor == 0 and not state.orders
    state = service.seek(identity, 10, state.account.revision)
    state = service.order(identity, OrderRequest(instrument_id='A', side='buy', quantity=2), state.account.revision)
    assert state.orders[0].status == 'pending' and not state.fills
    state = service.seek(identity, 20, state.account.revision)
    assert state.fills[0].time == 10 and state.portfolio.positions[0].quantity == 2
    state = service.order(identity, OrderRequest(instrument_id='A', side='sell', quantity=2), state.account.revision)
    state = service.seek(identity, 30, state.account.revision)
    assert len(state.fills) == 2 and state.portfolio.positions == []
    restored = AccountService(Store(tmp_path)).view(identity)
    assert restored.model_dump() == state.model_dump()
    state = service.seek(identity, 10, state.account.revision)
    assert not state.fills and not state.portfolio.positions
    assert len(state.account.commands) == 1  # later sell is removed, not silently replayed in the future
    state = service.seek(identity, 30, state.account.revision)
    assert len(state.fills) == 1 and state.portfolio.positions[0].quantity == 2
    with pytest.raises(ConflictError):
        service.seek(identity, 20, 0)
    assert store.get_document('paper-account', identity)['revision'] == state.account.revision


def test_replay_keeps_closed_markets_and_paused_time_unchanged(tmp_path):
    store = Store(tmp_path)
    a, b = series('A', interval=10), series('B', start=50, interval=10)
    ids = [store.save_dataset(v.dataset.instrument, '1m', v.bars, []).id for v in (a, b)]
    service = AccountService(store)
    state = service.create(AccountRequest(name='Different sessions', mode='replay', dataset_ids=ids,
        settings=ExecutionSettings(allow_fixture_data=True)))
    state = service.seek(state.account.id, 20, state.account.revision)
    state = service.order(state.account.id, OrderRequest(instrument_id='B', side='buy', quantity=1), state.account.revision)
    state = service.seek(state.account.id, 40, state.account.revision)
    assert not state.fills
    state = service.seek(state.account.id, 60, state.account.revision)
    assert state.fills[0].time == 50
    for _ in range(3):
        assert service.view(state.account.id).account.cursor == 60


def test_paper_account_adopts_only_new_completed_matching_prefix_and_is_separate(tmp_path, monkeypatch):
    import backend.accounts as module
    monkeypatch.setattr(module.time, 'time', lambda: 20)
    store, service, state, view = setup(tmp_path, mode='paper', count=2)
    identity = state.account.id
    assert state.account.cursor == 20
    state = service.order(identity, OrderRequest(instrument_id='A', side='buy', quantity=3), state.account.revision)
    assert not state.fills
    with pytest.raises(ValueError, match='cannot seek'):
        service.seek(identity, 0, state.account.revision)
    newer = series(prices=[(10, 11, 9, 10)]*4)
    data = store.save_dataset(view.dataset.instrument, '1m', newer.bars, [])
    monkeypatch.setattr(module.time, 'time', lambda: 40)
    state = service.refresh_paper(identity, state.account.revision)
    assert state.account.dataset_ids == [data.id]
    assert state.account.cursor == 40 and state.fills[0].time == 20
    assert state.portfolio.positions[0].quantity == 3
    restored = AccountService(Store(tmp_path)).view(identity)
    assert restored.portfolio == state.portfolio
    replay = service.create(AccountRequest(name='Separate replay', mode='replay', dataset_ids=[data.id],
        settings=ExecutionSettings(allow_fixture_data=True)))
    assert replay.account.id != identity and not replay.portfolio.positions
    revised = series(prices=[(9, 10, 8, 9)]+[(10, 11, 9, 10)]*4)
    store.save_dataset(view.dataset.instrument, '1m', revised.bars, [])
    with pytest.raises(ValueError, match='history changed'):
        service.refresh_paper(identity, state.account.revision)
    assert service.view(identity).portfolio == state.portfolio


def test_cancel_pending_survives_rebuild(tmp_path):
    _, service, state, _ = setup(tmp_path)
    state = service.order(state.account.id, OrderRequest(instrument_id='A', side='buy', quantity=1, kind='limit', limit_price=5), state.account.revision)
    state = service.cancel(state.account.id, state.orders[0].id, state.account.revision)
    service.cache.clear()
    restored = service.view(state.account.id)
    assert restored.orders[0].status == 'cancelled'
    state = service.seek(state.account.id, 30, restored.account.revision)
    assert not state.fills


def test_paper_hides_future_complete_prices_until_wall_clock_reaches_them(tmp_path, monkeypatch):
    import backend.accounts as module
    monkeypatch.setattr(module.time, 'time', lambda: 20)
    _, service, state, _ = setup(tmp_path, mode='paper', count=4)
    assert state.account.cursor == 20 and state.last_time == 20
    state = service.order(state.account.id, OrderRequest(instrument_id='A', side='buy', quantity=1), state.account.revision)
    monkeypatch.setattr(module.time, 'time', lambda: 30)
    state = service.refresh_paper(state.account.id, state.account.revision)
    assert state.account.cursor == 30 and state.fills[0].time == 20


async def test_background_paper_refresh_has_owned_shutdown(tmp_path, monkeypatch):
    import asyncio

    import backend.accounts as module
    monkeypatch.setattr(module.time, 'time', lambda: 20)
    store, service, state, view = setup(tmp_path, mode='paper', count=2)
    state = service.order(state.account.id, OrderRequest(instrument_id='A', side='buy', quantity=1), state.account.revision)
    newer = series(prices=[(10, 11, 9, 10)]*3)
    store.save_dataset(view.dataset.instrument, '1m', newer.bars, [])
    monkeypatch.setattr(module.time, 'time', lambda: 30)
    service.start()
    try:
        for _ in range(40):
            if service.view(state.account.id).fills:
                break
            await asyncio.sleep(.05)
        assert service.view(state.account.id).fills[0].time == 20
    finally:
        await service.close()
    assert service.task is None and service.pending is None


def test_paper_order_and_cancel_use_actual_submission_time_across_delayed_refresh(tmp_path, monkeypatch):
    import backend.accounts as module
    now = [20]
    monkeypatch.setattr(module.time, 'time', lambda: now[0])
    store, service, state, view = setup(tmp_path, mode='paper', count=2)
    now[0] = 25.1
    state = service.order(state.account.id, OrderRequest(instrument_id='A', side='buy', quantity=1), state.account.revision)
    order_id = state.orders[0].id
    assert state.orders[0].submitted_at == 26
    now[0] = 30
    extended = series(prices=[(10, 11, 9, 10)]*3)
    store.save_dataset(view.dataset.instrument, '1m', extended.bars, [])
    state = service.refresh_paper(state.account.id, state.account.revision)
    assert not state.fills  # The opening at 20 preceded the actual submission at 26.
    now[0] = 35
    state = service.cancel(state.account.id, order_id, state.account.revision)
    now[0] = 40
    extended = series(prices=[(10, 11, 9, 10)]*4)
    store.save_dataset(view.dataset.instrument, '1m', extended.bars, [])
    state = service.refresh_paper(state.account.id, state.account.revision)
    assert state.fills[0].time == 30  # Later cancellation cannot erase an already-eligible opening.
    assert state.orders[0].id == order_id and state.orders[0].status == 'filled'
    restored = AccountService(store).view(state.account.id)
    assert restored.fills == state.fills and restored.orders == state.orders


def test_pending_paper_commands_keep_stable_identity_when_bracket_children_appear(tmp_path, monkeypatch):
    import backend.accounts as module
    now = [20]
    monkeypatch.setattr(module.time, 'time', lambda: now[0])
    store, service, state, view = setup(tmp_path, mode='paper', count=2)
    state = service.order(state.account.id, OrderRequest(instrument_id='A', side='buy', quantity=1,
        kind='bracket', stop_loss=8, take_profit=12), state.account.revision)
    parent_id = state.orders[-1].id
    now[0] = 25
    state = service.order(state.account.id, OrderRequest(instrument_id='A', side='buy', quantity=1,
        kind='limit', limit_price=5), state.account.revision)
    cancelled_id = state.orders[-1].id
    state = service.cancel(state.account.id, cancelled_id, state.account.revision)
    now[0] = 40
    extended = series(prices=[(10, 11, 9, 10)]*4)
    store.save_dataset(view.dataset.instrument, '1m', extended.bars, [])
    state = service.refresh_paper(state.account.id, state.account.revision)
    assert state.fills[0].order_id == parent_id
    assert next(o for o in state.orders if o.id == cancelled_id).status == 'cancelled'
    assert len([o for o in state.orders if o.parent_id == parent_id and o.status == 'pending']) == 2
    assert service.view(state.account.id).orders == state.orders


def test_paper_pause_stops_refresh_and_resumes_elapsed_history(tmp_path, monkeypatch):
    import backend.accounts as module
    now = [20]
    monkeypatch.setattr(module.time, 'time', lambda: now[0])
    store, service, state, view = setup(tmp_path, mode='paper', count=2)
    state = service.pause(state.account.id, state.account.revision, True)
    assert AccountService(store).view(state.account.id).account.paused
    with pytest.raises(ValueError, match='Resume paper'):
        service.order(state.account.id, OrderRequest(instrument_id='A', side='buy', quantity=1), state.account.revision)
    extended = series(prices=[(10, 11, 9, 10)]*4)
    store.save_dataset(view.dataset.instrument, '1m', extended.bars, [])
    now[0] = 40
    assert service.refresh_paper(state.account.id, state.account.revision).account.cursor == 20
    state = service.pause(state.account.id, state.account.revision, False)
    assert service.refresh_paper(state.account.id, state.account.revision).account.cursor == 40
