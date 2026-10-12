from fastapi.testclient import TestClient

from backend.app import create_app

HEADERS = {'X-Workbench-Request': '1'}


def test_focused_collections_share_revision_and_preserve_other_saved_work(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        initial = client.get('/api/workspaces/default').json()
        initial['theme'] = 'light'
        initial['charts'][1]['timezone'] = 'Asia/Shanghai'
        saved = client.put('/api/workspaces/default', json=initial, headers=HEADERS).json()
        lists = client.get('/api/watchlists/default').json()
        lists['watchlists'][0]['name'] = 'Renamed via collection'
        changed = client.put('/api/watchlists/default', json=lists, headers=HEADERS)
        assert changed.status_code == 200
        assert changed.json()['workspace_revision'] == saved['revision']+1
        # A stale full-workspace save must not erase a collection edit.
        assert client.put('/api/workspaces/default', json=saved, headers=HEADERS).status_code == 409
        drawing = {'id': 'line', 'kind': 'trend', 'instrument_id': 'CSV:TEST',
                   'anchors': [{'time': 100, 'price': 10}, {'time': 200, 'price': 11}]}
        objects = client.get('/api/drawings/default/chart-0').json()
        objects['drawings'] = [drawing]
        result = client.put('/api/drawings/default/chart-0', json=objects, headers=HEADERS)
        assert result.status_code == 200
        assert client.put('/api/watchlists/default', json=changed.json(), headers=HEADERS).status_code == 409
        bad = result.json() | {'drawings': [drawing, drawing]}
        assert client.put('/api/drawings/default/chart-0', json=bad, headers=HEADERS).status_code == 422
        assert client.get('/api/drawings/default/missing').status_code == 404
        lists = client.get('/api/watchlists/default').json()
        assert client.put('/api/watchlists/default', json=lists | {'active_watchlist': 'missing'}, headers=HEADERS).status_code == 422
    with TestClient(create_app(tmp_path)) as client:
        restored = client.get('/api/workspaces/default').json()
        assert restored['theme'] == 'light'
        assert restored['charts'][1]['timezone'] == 'Asia/Shanghai'
        assert restored['charts'][0]['drawings'][0]['id'] == 'line'
        assert restored['watchlists'][0]['name'] == 'Renamed via collection'
        assert len(client.get('/api/drawings/default/chart-0').json()['drawings']) == 1
