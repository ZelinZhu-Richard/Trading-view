import csv
import io
import json
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.research_results import build_result
from backend.research_routes import routes
from tests.test_simulation import engine, order


@pytest.mark.parametrize(('table', 'required'), [
    ('orders', {'id', 'request', 'status'}),
    ('fills', {'id', 'price', 'conversion'}),
    ('trades', {'instrument_id', 'net_pnl'}),
    ('equity', {'time', 'equity', 'valuation_errors'}),
    ('positions', {'instrument_id', 'quantity'}),
    ('contributions', {'instrument_id', 'reporting_pnl'}),
])
def test_empty_csv_tables_keep_parseable_column_headers(table, required):
    result = build_result(engine())
    for key in ('orders', 'fills', 'trades', 'equity', 'contributions'):
        setattr(result, key, [])
    result.final_portfolio.positions = []
    app = FastAPI()
    app.include_router(routes(SimpleNamespace(result=lambda _: result), set()))
    with TestClient(app) as client:
        response = client.get(f'/api/research/test/export/{table}')
    assert response.status_code == 200
    assert response.headers['content-type'].startswith('text/csv')
    reader = csv.DictReader(io.StringIO(response.text))
    assert required <= set(reader.fieldnames)
    assert list(reader) == []


def test_fill_csv_preserves_decimal_values_and_nested_conversion_metadata():
    simulation = engine()
    order(simulation, '0.25')
    simulation.advance()
    result = build_result(simulation)
    app = FastAPI()
    app.include_router(routes(SimpleNamespace(result=lambda _: result), set()))
    with TestClient(app) as client:
        response = client.get('/api/research/test/export/fills')
    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert len(rows) == 1
    assert Decimal(rows[0]['quantity']) == Decimal('.25')
    assert Decimal(rows[0]['price']) == Decimal(10)
    conversion = json.loads(rows[0]['conversion'])
    assert Decimal(conversion['rate']) == 1
    assert conversion['from_currency'] == conversion['to_currency'] == 'USD'
