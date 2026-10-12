"""Hand-accounted synthetic cases exercise event ordering and money, not market parity."""
from decimal import Decimal

import pytest

from backend.fx import FXBook, MissingConversion
from backend.models import Bar, Dataset, DatasetView, Instrument
from backend.research_models import CorporateAction, ExecutionSettings, OrderRequest
from backend.simulation import Simulation

D = Decimal


def series(identity='A', prices=None, currency='USD', base=None, start=0, interval=10, adjustment='raw'):
    prices = prices or [(10, 11, 9, 10)]*4
    instrument = Instrument(id=identity, symbol=identity, name=identity, exchange='TEST',
        asset_class='forex' if base else 'other', base_currency=base, quote_currency=currency,
        timezone='UTC', quantity_step='0.01', price_tick='0.01', calendar='24/7')
    bars = [Bar(start=start+i*interval, end=start+(i+1)*interval, open=p[0], high=p[1], low=p[2], close=p[3],
                source='fixture', feed='simulation-tests', adjustment=adjustment) for i, p in enumerate(prices)]
    dataset = Dataset(id=identity, hash=identity+'-hash', instrument=instrument, interval='1m',
        source='fixture', feed='simulation-tests', adjustment=adjustment, created_at='2025-01-01T00:00:00Z',
        first_start=bars[0].start, last_end=bars[-1].end, row_count=len(bars))
    return DatasetView(dataset=dataset, bars=bars)


def engine(views=None, actions=None, **settings):
    return Simulation(views or [series()], ExecutionSettings(allow_fixture_data=True, **settings), actions)


def order(sim, quantity=1, side='buy', identity='A', **values):
    return sim.submit(OrderRequest(instrument_id=identity, side=side, quantity=D(quantity), **values))


def test_next_bar_open_shared_capital_and_source_ohlc():
    sim = engine([series('A'), series('B')], initial_capital=15)
    seen = []
    def callback(bars):
        seen.append((sim.clock, list(bars)))
        if sim.clock == 10:
            order(sim, identity='B')
            order(sim, identity='A')
    sim.advance(on_bars=callback)
    assert len(sim.fills) == 1 and sim.fills[0].instrument_id == 'B'
    assert sim.fills[0].time == 10 and sim.fills[0].bar_start == 10
    assert sim.orders[1].status == 'rejected' and 'Insufficient' in sim.orders[1].reason
    assert sim.portfolio().equity == 15 and sim.cash['USD'] == 5
    assert seen == [(10, ['A', 'B']), (20, ['A', 'B']), (30, ['A', 'B']), (40, ['A', 'B'])]


def test_daily_open_reserves_cash_before_later_intraday_signal():
    sim = engine([series('A', interval=100), series('B', interval=10)], initial_capital=15)
    order(sim, identity='A')
    def callback(bars):
        if sim.clock == 10:
            order(sim, identity='B')
    sim.advance(on_bars=callback)
    assert sim.fills[0].instrument_id == 'A' and sim.fills[0].time == 0
    assert sim.orders[1].status == 'rejected'


def test_long_average_cost_close_fees_and_slippage():
    sim = engine([series(prices=[(10, 12, 9, 11), (12, 13, 10, 12), (14, 15, 13, 14)])],
        initial_capital=1000, fee_bps=10, fee_per_order=1, slippage_bps=100)
    order(sim, 10)
    sim.advance(until=10)
    assert sim.fills[0].price == D('10.10') and sim.fills[0].fee == D('1.101')
    order(sim, 4, 'sell')  # bar at 10 has already opened; market fill waits to 20
    sim.advance()
    assert sim.fills[1].price == D('13.86')
    assert sim.positions['A'].quantity == 6
    assert sim.positions['A'].realized_gross == D('15.04')
    assert sim.trades[0].allocated_fees == D('1.49584')
    assert sim.cash['USD'] == D('952.28356')
    assert sim.portfolio().equity == D('1036.28356')


def test_short_collateral_not_available_for_leverage_and_partial_cover():
    sim = engine([series(prices=[(10, 11, 9, 10), (8, 9, 7, 8), (8, 9, 7, 8)])], initial_capital=100)
    order(sim, 5, 'sell')
    sim.advance(until=0)
    assert sim.cash['USD'] == 50
    assert sim.portfolio().restricted_cash['USD'] == 100
    assert sim.portfolio().equity == 100
    order(sim, 2)
    sim.advance(until=10)
    assert sim.cash['USD'] == 74
    assert sim.positions['A'].quantity == -3
    assert sim.positions['A'].short_collateral == 30
    assert sim.positions['A'].realized_gross == 4
    assert sim.portfolio().equity == 110
    order(sim, 3)
    sim.advance()
    assert sim.cash['USD'] == 110 and sim.portfolio().restricted_cash['USD'] == 0


@pytest.mark.parametrize(('side', 'kind', 'threshold', 'bar', 'expected', 'phase'), [
    ('buy', 'limit', 10, (8, 12, 7, 11), 8, 'open'),
    ('buy', 'limit', 10, (12, 13, 9, 11), 10, 'touch'),
    ('sell', 'limit', 10, (12, 13, 7, 11), 12, 'open'),
    ('sell', 'limit', 10, (8, 11, 7, 10), 10, 'touch'),
    ('buy', 'stop', 10, (12, 13, 7, 11), 12, 'open'),
    ('buy', 'stop', 10, (8, 11, 7, 10), 10, 'touch'),
    ('sell', 'stop', 10, (8, 12, 7, 11), 8, 'open'),
    ('sell', 'stop', 10, (12, 13, 9, 11), 10, 'touch'),
])
def test_gap_and_touch_rules(side, kind, threshold, bar, expected, phase):
    sim = engine([series(prices=[bar])])
    order(sim, side=side, kind=kind, **{kind+'_price': threshold})
    sim.advance()
    assert sim.fills[0].price == expected and sim.fills[0].phase == phase


def test_bracket_conflict_stop_first_and_linked_exit_cancellation():
    sim = engine([series(prices=[(10, 13, 7, 10), (10, 11, 9, 10)])])
    order(sim, 2, kind='bracket', stop_loss=8, take_profit=12)
    sim.advance()
    assert [f.price for f in sim.fills] == [10, 8]
    assert sim.orders[2].status == 'cancelled'
    assert sim.positions['A'].quantity == 0 and sim.trades[0].net_pnl == -4


def test_touched_bracket_entry_defers_favorable_exit_but_allows_stop():
    sim = engine([series(prices=[(11, 13, 9, 11), (11, 13, 10, 12)])])
    order(sim, kind='bracket', entry_kind='limit', limit_price=10, stop_loss=8, take_profit=12)
    sim.advance(until=10)
    assert len(sim.fills) == 1
    sim.advance()
    assert sim.fills[1].price == 12 and sim.fills[1].bar_start == 10
    sim = engine([series(prices=[(11, 13, 7, 11)])])
    order(sim, kind='bracket', entry_kind='limit', limit_price=10, stop_loss=8, take_profit=12)
    sim.advance()
    assert [f.price for f in sim.fills] == [10, 8]


def test_gap_beyond_short_collateral_records_insolvency_and_allows_cover():
    sim = engine([series(prices=[(10, 10, 10, 10), (100, 100, 100, 100), (100, 100, 100, 100)])], initial_capital=100)
    order(sim, 10, 'sell')
    sim.advance(until=0)
    order(sim, 10)
    sim.advance(until=10)
    assert sim.portfolio().equity == -800 and sim.portfolio().insolvent
    order(sim)
    sim.advance()
    assert sim.orders[-1].status == 'rejected' and 'insolvent' in sim.orders[-1].reason


def test_currency_conversion_is_causal_multihop_and_has_provenance():
    eur = series('EURUSD', [(1.2, 1.2, 1.2, 1.2), (1.5, 1.5, 1.5, 1.5)], base='EUR')
    jpy = series('EURJPY', [(150, 150, 150, 150)]*2, currency='JPY', base='EUR')
    book = FXBook([eur, jpy])
    with pytest.raises(MissingConversion):
        book.conversion('JPY', 'USD', 9, 'test')
    fx = book.conversion('JPY', 'USD', 10, 'test')
    assert fx.rate == D('0.008')
    assert [(l.from_currency, l.to_currency) for l in fx.legs] == [('JPY', 'EUR'), ('EUR', 'USD')]
    assert all(leg.available_at <= 10 for leg in fx.legs)
    assert fx.legs[1].dataset_hash == 'EURUSD-hash'
    assert book.conversion('EUR', 'USD', 19, 'test').rate == D('1.2')
    assert book.conversion('EUR', 'USD', 20, 'test').rate == D('1.5')
    with pytest.raises(MissingConversion):
        FXBook([eur], max_age=2).conversion('EUR', 'USD', 13, 'stale')


def test_missing_fx_blocks_order_no_parity_and_currency_cash_revalues():
    euro_asset = series(currency='EUR', start=10)
    sim = engine([euro_asset])
    order(sim)
    sim.advance()
    assert sim.orders[0].status == 'rejected' and 'conversion path' in sim.orders[0].reason
    eur = series('EURUSD', [(1.2, 1.2, 1.2, 1.2), (1.5, 1.5, 1.5, 1.5)], base='EUR')
    sim = engine([euro_asset, eur], initial_capital=100, start=10)
    order(sim, 2)
    sim.advance(until=10)
    assert sim.cash['USD'] == 76 and sim.positions['A'].quantity == 2
    sim.advance()
    assert sim.portfolio().equity == 106
    assert sim.fills[0].conversion.rate == D('1.2')


def test_split_dividend_pending_order_and_adjustment_double_counting():
    actions = [CorporateAction(instrument_id='A', kind='split', time=10, value=2, source='fixture'),
        CorporateAction(instrument_id='A', kind='dividend', time=20, value=1, source='fixture')]
    prices = [(10, 10, 10, 10), (5, 5, 5, 5), (4, 4, 4, 4)]
    sim = engine([series(prices=prices)], actions=actions, initial_capital=100)
    order(sim, 5)
    order(sim, 1, kind='limit', limit_price=2)
    sim.advance()
    assert sim.positions['A'].quantity == 10 and sim.positions['A'].average_price == 5
    assert sim.cash['USD'] == 60 and sim.positions['A'].dividends == 10
    assert sim.orders[1].request.quantity == 2 and sim.orders[1].request.limit_price == 1
    assert sim.portfolio().equity == 100
    sim = engine([series(prices=prices, adjustment='total-return')], actions=actions)
    sim.advance()
    assert all(not record['applied'] for record in sim.action_log)


def test_incomplete_bars_unavailable_future_changes_do_not_change_prefix_and_replay_resets():
    def exercise(last):
        view = series(prices=[(10, 11, 9, 10), (11, 12, 10, 11), (last, last, last, last)])
        sim = engine([view])
        order(sim)
        def callback(bars):
            assert all(bar.end <= sim.clock for h in sim.history.values() for bar in h)
            if sim.clock == 10:
                order(sim, side='sell')
        sim.advance(until=20, on_bars=callback)
        return sim
    first, second = exercise(100), exercise(200)
    # End-at-20 also opens the next bar at 20; compare earlier events only.
    assert [f for f in first.fills if f.time < 20] == [f for f in second.fills if f.time < 20]
    assert [p for p in first.equity if p.time < 20] == [p for p in second.equity if p.time < 20]
    with pytest.raises(ValueError, match='rebuilding'):
        first.advance(until=10)
    reset = engine()
    reset.advance(until=10)
    assert not reset.fills and reset.positions['A'].quantity == 0
    view = series()
    view.bars[-1].complete = False
    sim = engine([view])
    sim.advance()
    assert len(sim.history['A']) == 3
    with pytest.raises(ValueError, match='Synthetic'):
        Simulation([series()], ExecutionSettings())


def test_new_bracket_children_do_not_jump_ahead_of_earlier_competing_orders():
    sim = engine([series('A', prices=[(11, 13, 7, 11)]),
                  series('B', prices=[(11, 13, 9, 11)])], initial_capital=100)
    order(sim, 5, kind='bracket', entry_kind='limit', limit_price=10, stop_loss=8, take_profit=12)
    order(sim, 6, identity='B', kind='limit', limit_price=10)
    sim.advance()
    assert sim.orders[1].status == 'rejected'
    assert [f.price for f in sim.fills] == [10, 8]
