"""Practice journal: sizing, marking, closing and what the screen reads from it."""
from datetime import date

import pytest

from miratrade.config import Config
from miratrade.practice import (CLOSED, OPEN, PaperTrade, close_trade, equity_curve, load, mark,
                                open_trade, option_value, save, size_for, summary)


def _call(**kw):
    base = dict(ticker="ACME", kind="call", entry=4.0, stop=3.0, target=5.6, equity=25_000.0,
                strike=50.0, expiry="2026-11-20", iv=0.4, today=date(2026, 9, 27))
    return base | kw


def test_size_respects_risk_and_the_cap_on_one_position():
    cfg = Config()                                          # 1 % risk, 25 % of equity per order
    # shares: risking 1 % of 25 000 = 250 $, losing 2 $ a share -> 125 shares
    assert size_for(25_000, 20.0, 18.0, 1, cfg) == 125
    # but one order may not cost more than 25 % of equity: 6 250 / 20 = 312, so risk still binds
    assert size_for(25_000, 20.0, 19.9, 1, cfg) == 312      # tiny stop: the value cap takes over
    assert size_for(25_000, 4.0, 3.0, 100, cfg) == 2        # contracts carry 100 shares each
    assert size_for(25_000, 4.0, 4.0, 100, cfg) == 0        # no room between entry and stop
    assert size_for(0, 20.0, 18.0, 1, cfg) == 0


def test_open_trade_refuses_what_should_not_be_opened():
    trades = []
    t = open_trade(trades, **_call(), note="3 directivos")
    assert t.status == OPEN and t.quantity == 2 and t.cost == 800.0 and t.risk == 200.0
    assert t.label() == "ACME 50 C · vence 2026-11-20" and t.note == "3 directivos"

    with pytest.raises(ValueError, match="ya tienes una posición abierta|Ya tienes una posición"):
        open_trade(trades, **_call())                        # same ticker twice
    with pytest.raises(ValueError, match="stop"):
        open_trade(trades, **_call(ticker="B", stop=5.0))    # stop above the entry
    with pytest.raises(ValueError, match="entrada no es válido"):
        open_trade(trades, **_call(ticker="C", entry=0.0))
    with pytest.raises(ValueError, match="ni una unidad"):
        open_trade(trades, **_call(ticker="D", equity=10.0))

    cfg = Config()
    cfg.risk.max_positions = 1
    with pytest.raises(ValueError, match="máximo"):
        open_trade(trades, **_call(ticker="E"), cfg=cfg)


def test_marking_closes_at_the_stop_the_target_and_expiry():
    trades = []
    open_trade(trades, **_call(ticker="UP"))
    open_trade(trades, **_call(ticker="DOWN"))
    t_up, t_down = trades
    # a call is worth what Black-Scholes says about the underlying, so move the stock
    closed = mark(trades, {"UP": 80.0, "DOWN": 30.0}, on=date(2026, 9, 28))
    assert {t.ticker for t in closed} == {"UP", "DOWN"}
    assert t_up.status == CLOSED and t_up.exit_reason == "target" and t_up.profit > 0
    assert t_down.status == CLOSED and t_down.exit_reason == "stop" and t_down.profit < 0
    assert mark(trades, {"UP": 80.0}) == []                  # closed positions are left alone

    still = []
    open_trade(still, **_call(ticker="WAIT"))
    assert mark(still, {"WAIT": 50.0}, on=date(2026, 9, 28)) == []
    assert still[0].status == OPEN and still[0].last is not None
    expired = mark(still, {"WAIT": 50.0}, on=date(2026, 11, 20))
    assert expired and still[0].exit_reason == "expiry"      # expiry ends it, whatever it is worth
    assert still[0].exit_price == 0.0

    unknown = []
    open_trade(unknown, **_call(ticker="QUIET"))
    assert mark(unknown, {}) == [] and unknown[0].last == 4.0   # no price, no change


def test_option_value_decays_and_a_share_is_just_its_price():
    t = PaperTrade(id="1", opened="2026-09-27", ticker="A", kind="call", quantity=1, entry=4.0,
                   stop=3.0, target=5.6, strike=50.0, expiry="2026-11-20", iv=0.4)
    near = option_value(t, 50.0, date(2026, 9, 27))
    later = option_value(t, 50.0, date(2026, 11, 1))
    assert near > later > 0                                   # same stock, less time left
    assert option_value(t, 50.0, date(2026, 11, 20)) == 0.0    # expiry, at the money
    share = PaperTrade(id="2", opened="x", ticker="B", kind="accion", quantity=1, entry=10.0,
                       stop=9.0, target=12.0)
    assert option_value(share, 11.0, date(2026, 9, 27)) is None


def test_summary_and_equity_curve_read_the_journal():
    trades = []
    a = open_trade(trades, **_call(ticker="WIN"))
    b = open_trade(trades, **_call(ticker="LOSE"))
    c = open_trade(trades, **_call(ticker="LIVE"))
    close_trade(a, 6.0, "target", date(2026, 10, 1))
    close_trade(b, 3.0, "stop", date(2026, 10, 2))
    c.last = 4.5

    s = summary(trades, 25_000.0)
    assert s["abiertas"] == 1 and s["cerradas"] == 2 and s["acierto"] == 0.5
    assert s["ganancia_realizada"] == pytest.approx((6.0 - 4.0) * 200 + (3.0 - 4.0) * 200)
    assert s["ganancia_abierta"] == pytest.approx((4.5 - 4.0) * 200)
    assert s["equity"] == pytest.approx(25_000 + s["ganancia_realizada"] + s["ganancia_abierta"])
    assert s["riesgo_abierto"] == 200.0

    dates, values = equity_curve(trades, 25_000.0)
    assert dates == ["2026-10-01", "2026-10-02"]
    assert values == pytest.approx([25_400.0, 25_200.0])


def test_the_journal_survives_closing_the_app(tmp_path):
    path = tmp_path / "practice.json"
    assert load(path) == []
    trades = []
    open_trade(trades, **_call(), note="evento")
    close_trade(trades[0], 5.0, "manual", date(2026, 10, 3))
    open_trade(trades, **_call(ticker="B"))
    save(trades, path)

    back = load(path)
    assert [t.id for t in back] == [t.id for t in trades]
    assert back[0].status == CLOSED and back[0].exit_price == 5.0 and back[0].note == "evento"
    assert back[1].status == OPEN and back[1].quantity == trades[1].quantity
    assert back[0].profit == trades[0].profit

    path.write_text("{ no es json", encoding="utf-8")
    assert load(path) == []                                   # a broken file loses practice, not the app
