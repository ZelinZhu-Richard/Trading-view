from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.models import ImportRequest, Instrument, Workspace
from backend.normalization import aggregate, bar_window, parse_import, timestamp
from backend.store import ConflictError, Store

HEADERS = {'X-Workbench-Request': '1'}


def instrument(**changes):
    return Instrument(id='CSV:TEST', symbol='TEST', name='Test fixture', exchange='TEST',
                      asset_class='other', quote_currency='USD', timezone='UTC', **changes)


def request(text, **changes):
    return ImportRequest(instrument=instrument(), csv_text=text, timezone='UTC', **changes)


CSV = 'timestamp,open,high,low,close,volume\n2025-01-01,10,12,9,11,0\n2025-01-02,11,13,10,12,\n'


def test_preview_commit_persist_and_restart(tmp_path):
    app = create_app(tmp_path)
    with TestClient(app) as client:
        preview = client.post('/api/imports/preview', headers=HEADERS, json=request(CSV).model_dump(mode='json'))
        assert preview.status_code == 200, preview.text
        body = preview.json()
        assert body['can_commit'] and body['valid_rows'] == 2
        assert [b['volume'] for b in body['preview']] == [0, None]
        committed = client.post('/api/imports/commit', headers=HEADERS, json={'token': body['token']})
        assert committed.status_code == 200, committed.text
        data = committed.json()
        workspace = client.get('/api/workspaces/default').json()
        workspace['charts'][0]['dataset_id'] = data['id']
        saved = client.put('/api/workspaces/default', headers=HEADERS, json=workspace)
        assert saved.status_code == 200 and saved.json()['revision'] == 1
    with TestClient(create_app(tmp_path)) as restarted:
        assert restarted.get('/api/workspaces/default').json()['charts'][0]['dataset_id'] == data['id']
        bars = restarted.get(f'/api/datasets/{data["id"]}').json()['bars']
        assert [b['close'] for b in bars] == [11, 12]
        assert [b['volume'] for b in bars] == [0, None]
        # Repeat imports preserve identity rather than duplicating immutable datasets.
        p = restarted.post('/api/imports/preview', headers=HEADERS, json=request(CSV).model_dump(mode='json')).json()
        d = restarted.post('/api/imports/commit', headers=HEADERS, json={'token': p['token']}).json()
        assert d['id'] == data['id']
        assert len(restarted.get('/api/datasets').json()) == 1


def test_duplicate_and_row_error_policy():
    text = CSV + '2025-01-01,10,12,9,11,0\n2025-01-02,11,13,10,12.5,\n2025-01-03,10,8,9,12,-3\n'
    preview, _ = parse_import(request(text))
    assert not preview.can_commit
    assert preview.exact_duplicates == 1 and preview.conflicting_duplicates == 1
    assert [e.row for e in preview.errors] == [5, 6]
    fixed = '\n'.join(text.splitlines()[:-1])
    p, bars = parse_import(request(fixed, conflict_policy='last'))
    assert p.can_commit and bars[-1].close == 12.5
    p, bars = parse_import(request(fixed, conflict_policy='first'))
    assert p.can_commit and bars[-1].close == 12


@pytest.mark.parametrize('value', ['2025-11-02 01:30', '2025-03-09 02:30'])
def test_ambiguous_or_missing_local_time_rejected(value):
    with pytest.raises(ValueError, match='ambiguous'):
        timestamp(value, 'America/New_York', None)


def test_timezone_required_and_explicit_offset_preserved():
    with pytest.raises(ValueError, match='Timezone is required'):
        timestamp('2025-01-01 10:00', None, None)
    assert timestamp('2025-01-01T10:00:00-05:00', None, None).hour == 15


def test_exchange_dst_holiday_and_china_lunch_break():
    us = instrument(calendar='XNYS').model_copy(update={'timezone': 'America/New_York'})
    before = bar_window(timestamp('2025-03-07', us.timezone, None), '1d', us)
    after = bar_window(timestamp('2025-03-10', us.timezone, None), '1d', us)
    assert datetime.fromtimestamp(before[0], UTC).hour == 14
    assert datetime.fromtimestamp(after[0], UTC).hour == 13
    with pytest.raises(ValueError, match='closed'):
        bar_window(timestamp('2025-07-04', us.timezone, None), '1d', us)
    china = instrument(calendar='XSHG').model_copy(update={'timezone': 'Asia/Shanghai'})
    with pytest.raises(ValueError, match='lunch'):
        bar_window(timestamp('2025-01-06 12:00', china.timezone, None), '5m', china)
    start, end = bar_window(timestamp('2025-01-06 11:00', china.timezone, None), '1h', china)
    assert end - start == 30 * 60


def test_invalid_nan_price_and_volume_are_row_errors():
    text = 'timestamp,open,high,low,close,volume\n2025-01-01,10,12,9,nan,0\n2025-01-02,11,13,10,12,-1\n'
    p, bars = parse_import(request(text))
    assert p.invalid_rows == 2 and not p.can_commit and bars == []


def test_workspace_optimistic_concurrency_and_schema(tmp_path):
    store = Store(tmp_path)
    original = Workspace().model_dump(mode='json')
    first = store.save_document('workspace', 'default', original, 0)
    with pytest.raises(ConflictError):
        store.save_document('workspace', 'default', {**original, 'theme': 'light'}, 0)
    assert store.workspace().theme == 'dark'
    assert first['revision'] == 1


def test_origins_hosts_and_import_token_enforced(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        assert client.post('/api/examples/dataset').status_code == 403
        assert client.post('/api/examples/dataset', headers={**HEADERS, 'Origin': 'https://example.net'}).status_code == 403
        assert client.get('/api/health', headers={'host': 'evil.example'}).status_code == 400
        assert client.post('/api/imports/commit', headers=HEADERS, json={'token': 'unknown'}).status_code == 410
        with client.websocket_connect('/api/events', headers={'origin': 'http://localhost:5173'}) as socket:
            socket.send_json({'action': 'subscribe', 'subscription': 'health'})
            assert socket.receive_json()['subscription'] == 'health'
            socket.send_json({'action': 'unsubscribe', 'subscription': 'health'})
            assert socket.receive_json()['type'] == 'unsubscribed'


def test_source_identity_and_unavailable_finer_interval():
    _, bars = parse_import(request(CSV))
    with pytest.raises(ValueError, match='finer'):
        aggregate(bars, '1d', '1h', instrument())
    bars[1] = bars[1].model_copy(update={'feed': 'other-feed'})
    with pytest.raises(ValueError, match='feeds'):
        aggregate(bars, '1d', '1w', instrument())


def test_cutoff_uses_completion_end_not_chart_start(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        p = client.post('/api/imports/preview', headers=HEADERS, json=request(CSV).model_dump(mode='json')).json()
        d = client.post('/api/imports/commit', headers=HEADERS, json={'token': p['token']}).json()
        all_bars = client.get('/api/datasets/' + d['id']).json()['bars']
        cutoff = all_bars[0]['end']
        visible = client.get(f'/api/datasets/{d["id"]}?cutoff={cutoff}').json()['bars']
        assert len(visible) == 1 and visible[0]['close'] == 11
