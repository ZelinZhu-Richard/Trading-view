import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.models import StrategyDefinition
from backend.scripts import analyze_script, validate_parameters


def script(source):
    return StrategyDefinition(id='test', name='Script test', kind='strategy', source=source)


def test_static_analysis_does_not_execute_top_level_statements(tmp_path):
    output = tmp_path/'must-not-exist'
    source = f"from pathlib import Path\nPath({str(output)!r}).write_text('executed')\nPARAMETERS = {{'length': {{'type': 'int', 'default': 3, 'minimum': 1}}}}\ndef on_bars(ctx, bars):\n    pass\n"
    result = analyze_script(script(source))
    assert result.valid and result.parameters['length'].default == 3
    assert not output.exists()
    assert validate_parameters(result.parameters, {'length': 4}) == {'length': 4}
    for value in (0, 2.5, True, float('nan')):
        with pytest.raises(ValueError):
            validate_parameters(result.parameters, {'length': value})


def test_syntax_and_nonliteral_parameter_diagnostics():
    result = analyze_script(script('def on_bars(ctx, bars)\n    pass'))
    assert not result.valid and result.diagnostics[0].line == 1
    result = analyze_script(script('PARAMETERS = dict(length=10)\ndef on_bars(ctx, bars):\n    pass'))
    assert not result.valid and 'malformed' in result.diagnostics[0].message
    assert not analyze_script(script('def another_function():\n    pass')).valid


def test_script_api_versions_preserve_source_and_never_run_imports(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        headers = {'X-Workbench-Request': '1'}
        value = script('raise RuntimeError("must not execute while saving")\ndef on_bars(ctx, bars):\n    pass')
        first = client.put('/api/scripts/test', headers=headers, json=value.model_dump(mode='json'))
        assert first.status_code == 200 and first.json()['revision'] == 1
        changed = first.json() | {'source': 'def on_bars(ctx, bars):\n    ctx.log("version two")'}
        second = client.put('/api/scripts/test', headers=headers, json=changed)
        assert second.status_code == 200 and second.json()['revision'] == 2
        versions = client.get('/api/scripts/test/versions').json()
        assert [v['revision'] for v in versions] == [2, 1]
        assert versions[1]['source'] == value.source
        assert client.put('/api/scripts/test', headers=headers, json=changed).status_code == 409
        assert client.delete('/api/scripts/test', headers=headers).status_code == 200
        assert client.get('/api/scripts').json() == []
        assert len(client.get('/api/scripts/test/versions').json()) == 2
