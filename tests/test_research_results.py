"""Hand-computed report metrics and undefined-value boundaries."""
import math
import statistics
from decimal import Decimal

import pytest

from backend.research_results import build_result
from tests.test_simulation import engine, order, series


def test_daily_risk_drawdown_turnover_and_exposure_are_hand_computed():
    sim = engine([series(prices=[(p, p, p, p) for p in (10, 11, 9, 12)], interval=86400)], initial_capital=100)
    order(sim, 10)
    sim.advance()
    metrics = build_result(sim).metrics
    returns = [0, .1, 9/11-1, 12/9-1, 0]
    deviation = statistics.stdev(returns)
    assert metrics['total_return'].value == pytest.approx(.2)
    assert metrics['volatility'].value == pytest.approx(deviation*math.sqrt(365.25))
    assert metrics['sharpe'].value == pytest.approx(statistics.mean(returns)/deviation*math.sqrt(365.25))
    assert metrics['max_drawdown'].value == pytest.approx(1-9/11)
    assert metrics['turnover'].value == 1 and metrics['exposure'].value == 1
    assert metrics['win_rate'].value is None and metrics['profit_factor'].value is None
    assert metrics['annualized_return'].undefined_reason


def test_annualization_threshold_and_closed_day_carry():
    sim = engine([series(prices=[(100, 110, 100, 110)], interval=30*86400)], initial_capital=100)
    order(sim, 1); sim.advance()
    result = build_result(sim)
    expected = (1.1**(365.25/30))-1
    assert result.metrics['annualized_return'].value == pytest.approx(expected)
    assert result.metrics['volatility'].value == pytest.approx(statistics.stdev([0]*30+[.1])*math.sqrt(365.25))
    assert result.metrics['max_drawdown'].value == 0


def test_closing_trade_statistics_and_instrument_contributions_reconcile():
    sim = engine([series(prices=[(p, p, p, p) for p in (10, 12, 9)])], initial_capital=100)
    order(sim, 1)
    def step(bars):
        if sim.clock == 10:
            order(sim, 1, 'sell'); order(sim, 1)
        if sim.clock == 20:
            order(sim, 1, 'sell')
    sim.advance(on_bars=step)
    result = build_result(sim)
    assert [trade.net_pnl for trade in result.trades] == [Decimal(2), Decimal(-3)]
    assert result.metrics['win_rate'].value == .5
    assert result.metrics['profit_factor'].value == pytest.approx(2/3)
    assert result.metrics['turnover'].value == .43
    assert result.contributions[0].reporting_pnl == -1
    assert result.currency_translation == 0 and result.final_portfolio.equity == 99


def test_stale_fx_makes_risk_and_final_valuation_explicitly_undefined():
    fx = series('EURUSD', [(1.2, 1.2, 1.2, 1.2)], base='EUR')
    sim = engine([series(currency='EUR', start=10), fx], initial_capital=100, start=10, fx_max_age_seconds=5)
    order(sim, 1); sim.advance()
    result = build_result(sim)
    assert len(result.fills) == 1 and result.final_portfolio.equity is None
    for key in ('total_return', 'annualized_return', 'volatility', 'sharpe', 'max_drawdown', 'exposure'):
        assert result.metrics[key].value is None and result.metrics[key].undefined_reason
    assert result.currency_translation is None and result.contributions[0].reporting_pnl is None
