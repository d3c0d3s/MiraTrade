"""Recent-event scan and the evidence lookup behind the Señales screen."""
import pandas as pd

from miratrade.data.ownership import OWNERSHIP_COLUMNS
from miratrade.scan import (Evidence, evidence, load_scan, matching_rules, run_scan, save_scan,
                            variant_label)
from miratrade.synthetic import make_market


def _history(n_exec=40, n_other=60):
    """Insider events: executives reached the target 3 times in 4, the rest 1 in 4."""
    rows = []
    for i in range(n_exec + n_other):
        exec_ = i < n_exec
        hit = (i % 4 != 0) if exec_ else (i % 4 == 0)
        rows.append({"event:insider_buy": True, "event:flow": False, "event:13dg": False,
                     "ins:exec_buy": exec_, "ins:big_250k+": exec_ and i % 2 == 0, "ins:cluster2+": False,
                     "res_call45_40": 1.0 if hit else -1.0, "ret_call45_40": 0.4 if hit else -0.25})
    rows.append({"event:insider_buy": False, "event:flow": True, "event:13dg": False, "ins:exec_buy": False,
                 "ins:big_250k+": False, "ins:cluster2+": False, "res_call45_40": 1.0, "ret_call45_40": 0.4})
    rows.append({"event:insider_buy": True, "event:flow": False, "event:13dg": False, "ins:exec_buy": True,
                 "ins:big_250k+": False, "ins:cluster2+": False, "res_call45_40": float("nan"),
                 "ret_call45_40": float("nan")})                       # horizon past the data: ignored
    return pd.DataFrame(rows)


def test_evidence_narrows_while_enough_events_remain():
    ev = {"event:insider_buy": True, "ins:exec_buy": True, "ins:big_250k+": True}
    e = evidence(ev, _history(), "call45_40", min_n=30)
    # exec_buy leaves 40 (kept); big_250k+ would leave 20 < 30, so it is not applied
    assert e.similar_to == ["ins:exec_buy"] and e.n == 40
    assert e.target == 0.75 and e.stop == 0.25 and e.neither == 0
    assert round(e.mean_return, 4) == round(0.75 * 0.4 - 0.25 * 0.25, 4)
    assert e.sentence == ("40 eventos parecidos: 75 % llegó antes al objetivo, 25 % al stop y 0 % a ninguno. "
                          "Resultado medio +24 %.")
    big = Evidence("call45_40", n=1493, target=0.32, stop=0.66, neither=0.02, mean_return=-0.03)
    assert big.sentence.startswith("1.493 eventos parecidos: 32 % llegó antes al objetivo, 66 % al stop")
    assert big.sentence.endswith("Resultado medio −3 %.")


def test_evidence_without_a_matching_type_or_history():
    assert evidence({"event:13dg": True}, _history()).n == 0
    assert evidence({"event:insider_buy": True}, pd.DataFrame()).n == 0
    assert Evidence("call45_40").sentence.startswith("Sin eventos")
    broad = evidence({"event:insider_buy": True}, _history(), min_n=30)
    assert broad.n == 100 and broad.similar_to == []


def test_matching_rules_needs_validated_confirmed_and_every_condition():
    rules = pd.DataFrame({"rule": ["ins:exec_buy & trend:up", "ins:exec_buy", "ins:exec_buy", "flow:bullish"],
                          "validated": [True, True, False, True], "wf_confirmed": [True, True, True, True],
                          "variant": ["call45_40", "call45_40", "call45_40", "stock12m_30"]})
    ev = {"ins:exec_buy": True, "trend:up": False, "flow:bullish": True}
    assert matching_rules(ev, rules, "call45_40") == ["ins:exec_buy"]
    assert matching_rules({**ev, "trend:up": True}, rules, "call45_40") == ["ins:exec_buy & trend:up", "ins:exec_buy"]
    assert matching_rules(ev, None, "call45_40") == []


def test_variant_label():
    assert variant_label("call45_40") == "Call 45 días · +40 % / −25 %"
    assert variant_label("stock12m_30") == "Acción 12 meses · +30 % / −20 %"


def _synthetic_scan(tmp_path, days=60):
    prices, insiders, flow = make_market()
    end = prices["SPY"].index[-1].date()
    fetch = {"insiders": lambda s, e: insiders,
             "ownership": lambda s, e, ins: pd.DataFrame(columns=OWNERSHIP_COLUMNS),
             "prices": lambda tickers, s, e: {t: prices[t] for t in tickers if t in prices},
             "flow": lambda: flow}
    return run_scan(days=days, end=end, fetch=fetch, log=lambda m: None), prices, end


def test_run_scan_finds_recent_events_only(tmp_path):
    res, prices, end = _synthetic_scan(tmp_path)
    ev = res["events"]
    assert len(ev) > 0 and ev["ticker"].is_unique and "SPY" not in set(ev["ticker"])
    assert (ev["signal_date"].dt.date >= res["since"]).all()
    assert ev[["event:insider_buy", "event:flow"]].any(axis=1).all()
    assert ev["what"].str.len().gt(0).all()
    assert set(res["prices"]) == set(ev["ticker"])
    assert list(ev["signal_date"]) == sorted(ev["signal_date"], reverse=True)


def test_saved_scan_round_trip(tmp_path):
    res, _, _ = _synthetic_scan(tmp_path)
    save_scan(res, tmp_path / "scan")
    back = load_scan(tmp_path / "scan")
    assert list(back["events"]["ticker"]) == list(res["events"]["ticker"])
    assert back["since"] == res["since"] and back["end"] == res["end"]
    t = res["events"]["ticker"].iat[0]
    assert len(back["prices"][t]) == len(res["prices"][t])
    assert load_scan(tmp_path / "missing") is None
