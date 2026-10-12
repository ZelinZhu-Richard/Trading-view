from dataclasses import FrozenInstanceError

import pytest

from backend.indicators import DEFINITIONS, evaluate
from backend.models import IndicatorInstance, IndicatorRequest, StrategyDefinition
from backend.research_results import build_result
from backend.sdk import Context, ScriptRuntime
from tests.test_simulation import engine, order, series


def script(source, kind='strategy'):
    return StrategyDefinition(id='test', name='Test strategy', source=source, kind=kind)


def test_context_snapshots_history_clock_seed_and_same_indicator_calculation():
    view = series(prices=[(10+i, 11+i, 9+i, 10+i) for i in range(6)])
    sim = engine([view])
    ctx = Context(sim, {})
    assert not ctx.history('A') and ctx.indicator('A', 'sma', {'length': 2})['value'] == ()
    sim.advance(until=20)
    bars = ctx.history('A')
    assert len(bars) == 2 and ctx.clock.timestamp() == 20
    with pytest.raises(FrozenInstanceError):
        bars[0].close = 300
    local = ctx.instruments['A']
    local.name = 'Changed copy'
    assert ctx.instruments['A'].name == 'A'
    ctx.portfolio.cash['USD'] = 0
    assert sim.cash['USD'] == 100000
    expected = evaluate(IndicatorRequest(dataset_id='A', cutoff=20, instances=[IndicatorInstance(
        id='test', definition_id='sma', parameters={'length': 2})]), view.dataset, view.bars)
    assert ctx.indicator('A', 'sma', {'length': 2})['value'] == tuple(expected.results[0].lines[0].values)
    assert ctx.random.random() == Context(engine(), {}).random.random()
    order(sim)
    ctx.orders[0].request.quantity = 500
    assert sim.orders[0].request.quantity == 1


def test_future_perturbation_cannot_change_sdk_signals_or_early_fills():
    source = '''
PARAMETERS = {"length": {"type": "int", "default": 2}}
def on_bars(ctx, bars):
    value = ctx.indicator("A", "sma", {"length": ctx.parameters["length"]}, count=1)["value"]
    ctx.plot("mean", value[-1])
    ctx.log(ctx.clock, ctx.random.random())
    if value[-1] is not None and not ctx.state.get("entered"):
        ctx.order("A", "buy", 1)
        ctx.state["entered"] = True
'''
    results = []
    for future in (100, 200):
        sim = engine([series(prices=[(10, 11, 9, 10)]*4+[(future, future, future, future)])])
        runtime = ScriptRuntime(sim, script(source))
        sim.advance(on_bars=runtime.on_bars)
        runtime.finish()
        results.append(build_result(sim, runtime.ctx.logs, runtime.ctx.plots))
    assert results[0].fills == results[1].fills
    assert results[0].plots[:4] == results[1].plots[:4]
    assert results[0].logs == results[1].logs


def test_custom_indicator_executes_on_causal_completed_inputs():
    source = '''
PARAMETERS = {"scale": {"type": "float", "default": 2}}
def calculate(ctx):
    return {"double": ctx.history("A", count=1)[-1].close * ctx.parameters["scale"]}
'''
    sim = engine()
    runtime = ScriptRuntime(sim, script(source, 'indicator'))
    sim.advance(on_bars=runtime.on_bars)
    assert [value['value'] for value in runtime.ctx.plots] == [20]*4
    assert [value['time'] for value in runtime.ctx.plots] == [10, 20, 30, 40]
    assert not sim.fills


def test_identical_snapshots_produce_identical_serialized_results_and_undefined_metrics():
    source = '''
def initialize(ctx):
    ctx.order("A", "buy", 5)
def on_bars(ctx, bars):
    if ctx.timestamp == 10:
        ctx.order("A", "sell", 5)
'''
    results = []
    for _ in range(2):
        sim = engine(initial_capital=100)
        runtime = ScriptRuntime(sim, script(source))
        sim.advance(on_bars=runtime.on_bars)
        runtime.finish()
        results.append(build_result(sim, runtime.ctx.logs, runtime.ctx.plots))
    assert results[0].model_dump_json() == results[1].model_dump_json()
    metrics = results[0].metrics
    assert metrics['total_return'].value == 0
    assert metrics['annualized_return'].value is None
    assert metrics['sharpe'].value is None
    assert metrics['profit_factor'].value is None
    assert metrics['win_rate'].value == 0
    assert results[0].currency_translation == 0


def test_foreign_pnl_and_translation_reconcile():
    eur = series('EURUSD', [(1.2, 1.2, 1.2, 1.2), (1.5, 1.5, 1.5, 1.5)], base='EUR')
    sim = engine([series(currency='EUR', start=10), eur], initial_capital=100, start=10)
    order(sim, 2)
    sim.advance()
    result = build_result(sim)
    assert result.final_portfolio.equity == 106
    assert result.contributions[0].reporting_pnl == 0
    assert result.currency_translation == 6
    assert result.metrics['total_return'].value == .06


def test_orders_after_processed_open_cannot_use_already_started_bar_touch():
    sim = engine([series(prices=[(10, 11, 8, 10), (10, 11, 8, 10)])])
    sim.advance(until=0)
    order(sim, kind='limit', limit_price=9)
    sim.advance(until=10)
    assert not sim.fills
    sim.advance()
    assert sim.fills[0].bar_start == 10


@pytest.mark.parametrize('identifier', list(DEFINITIONS))
def test_every_builtin_has_same_causal_values_in_chart_replay_and_sdk(identifier):
    import math

    from backend.models import DatasetView
    from tests.test_indicators import INSTRUMENT, START, bars
    from tests.test_simulation import series
    settings = {'anchor_time': '2025-01-01T00:00:00Z'} if identifier == 'anchored_vwap' else {'bars_per_year': 365.25*1440} if identifier == 'historical_volatility' else {}
    source = bars([100+math.sin(i*.4)*8+i*.1 for i in range(100)], step=60)
    source = [bar for i, bar in enumerate(source) if i != 38]  # Missing source bucket must not become a phantom SDK bar.
    source[-1] = source[-1].model_copy(update={'complete': False})
    dataset = series().dataset.model_copy(update={'id': 'shared', 'instrument': INSTRUMENT, 'first_start': START,
        'last_end': source[-1].end, 'row_count': len(source), 'feed': 'hand-ramp'})
    view = DatasetView(dataset=dataset, bars=source)
    sim = engine([view]); ctx = Context(sim, {})
    for cutoff in (START+25*60, START+60*60, START+100*60):
        sim.advance(until=cutoff, pause_before_open=True)
        expected = evaluate(IndicatorRequest(dataset_id=dataset.id, cutoff=cutoff, instances=[IndicatorInstance(
            id='shared', definition_id=identifier, parameters=settings)]), dataset, source)
        assert expected.results[0].status == 'ready'
        actual = ctx.indicator(INSTRUMENT.id, identifier, settings)
        for line in expected.results[0].lines:
            assert list(actual[line.output_id]) == pytest.approx(line.values, abs=1e-10, rel=1e-9)
        assert all(bar.end <= cutoff for bar in ctx.history(INSTRUMENT.id))
        assert all(bar.end != source[-1].end for bar in ctx.history(INSTRUMENT.id))


def test_explicit_empty_parameter_set_uses_declared_defaults():
    definition = script('PARAMETERS = {"length": {"type": "int", "default": 3}}\ndef on_bars(ctx, bars):\n    pass')
    definition.parameters = {'length': 7}
    assert ScriptRuntime(engine(), definition, {}).ctx.parameters['length'] == 3
    assert ScriptRuntime(engine(), definition).ctx.parameters['length'] == 7
