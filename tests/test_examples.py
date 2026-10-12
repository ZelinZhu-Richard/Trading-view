import math
from pathlib import Path

import pytest

from backend.models import StrategyDefinition
from backend.research_results import build_result
from backend.sdk import ScriptRuntime
from tests.test_simulation import engine, series

EXAMPLES = Path(__file__).resolve().parent.parent/'examples'


@pytest.mark.parametrize('name', ['custom_indicator', 'moving_average_crossover', 'multi_asset_rebalance', 'multi_currency_portfolio'])
def test_shipped_python_examples_run_on_causal_multi_asset_inputs(name):
    prices = [(100+math.sin(i*.35)*20, 122, 78, 100+math.sin(i*.35)*20) for i in range(150)]
    views = [series('USD-ASSET', prices, interval=86400), series('EUR-ASSET', prices, currency='EUR', interval=86400),
             series('EURUSD', [(1.2,1.2,1.2,1.2)]*150, base='EUR', interval=86400)]
    sim = engine(views, initial_capital=100000)
    script = StrategyDefinition(id=name, name=name, source=(EXAMPLES/f'{name}.py').read_text(),
        kind='indicator' if name == 'custom_indicator' else 'strategy')
    runtime = ScriptRuntime(sim, script)
    sim.advance(on_bars=runtime.on_bars); runtime.finish()
    result = build_result(sim, runtime.ctx.logs, runtime.ctx.plots)
    if name == 'custom_indicator':
        assert result.plots and any(item['value'] is not None for item in result.plots)
        assert not result.fills
    else:
        assert result.fills and result.final_portfolio.equity is not None
        if name == 'multi_currency_portfolio':
            assert {f.quote_currency for f in result.fills} == {'USD','EUR'}
    assert all(leg.available_at <= conversion.at for conversion in result.conversions for leg in conversion.legs)
