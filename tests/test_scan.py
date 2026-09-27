"""Recent-event scan and the evidence lookup behind the Señales screen."""
from datetime import timedelta

import numpy as np
import pandas as pd
import pytest

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


def test_scan_checks_the_price_source_before_downloading(monkeypatch):
    """Without prices the scan must stop at once, not after minutes of SEC downloads."""
    import miratrade.data.prices as prices
    from miratrade.data.prices import PriceSourceError
    from miratrade.scan import run_scan

    called = []
    monkeypatch.setattr(prices, "source_ready", lambda source=None: (False, "Schwab: falta iniciar sesión."))
    monkeypatch.setattr("miratrade.scan._default_fetchers", lambda log: called.append(1) or {})
    with pytest.raises(PriceSourceError, match="Configuración"):
        run_scan(days=7, log=lambda m: None)
    assert called == []                                    # nothing was downloaded


def test_contract_for_models_the_call_the_profile_would_buy():
    from miratrade.scan import contract_for

    idx = pd.bdate_range("2026-01-02", periods=120)
    close = pd.Series(50 * (1.002 ** np.arange(120)), index=idx)
    prices = pd.DataFrame({"open": close, "high": close * 1.01, "low": close * 0.99,
                           "close": close, "volume": 1e6}, index=idx)
    c = contract_for(prices, idx[-1], "call45_40")
    assert c is not None
    assert (c["expiry"].date() - idx[-1].date()).days >= 45 and c["dte"] >= 45
    assert 0.45 < c["delta"] < 0.85 and c["theta"] < 0 and c["vega"] > 0
    assert c["premium"] > 0 and c["cost"] == pytest.approx(c["premium"] * 100)
    assert c["target"] == pytest.approx(c["premium"] * 1.40)
    assert c["stop"] == pytest.approx(c["premium"] * 0.75)          # +40 % pairs with −25 %
    assert contract_for(prices, idx[-1], "stock12m_30") is None     # share profile: no contract
    assert contract_for(prices.head(5), idx[4], "call45_40") is None  # too little history
    assert contract_for(pd.DataFrame(), idx[-1], "call45_40") is None


def test_scan_explains_that_it_downloads_before_the_window(monkeypatch):
    """The download starts 30 days earlier so the cluster counts are right; the log must say so
    instead of looking like the scan is searching the wrong dates."""
    from miratrade.config import Config
    from miratrade.scan import run_scan

    lines, asked = [], {}
    prices, insiders, flow = make_market(n_tickers=4)
    end = prices["SPY"].index[-1].date()

    def grab(start, stop):
        asked["insiders"] = (start, stop)
        return insiders

    run_scan(days=7, end=end, log=lines.append,
             fetch={"insiders": grab,
                    "ownership": lambda s, e, i: pd.DataFrame(columns=OWNERSHIP_COLUMNS),
                    "prices": lambda t, s, e: {k: prices[k] for k in t if k in prices},
                    "flow": lambda: flow})
    look = max(Config().insider.lookback_days, Config().smart.lookback_days)
    since = end - timedelta(days=7)
    assert asked["insiders"][0] == since - timedelta(days=look)      # the extra history is fetched
    said = " ".join(lines)
    assert str(since) in said and str(since - timedelta(days=look)) in said and "sigue contando" in said


def _events(rows):
    return pd.DataFrame(rows)


def test_filters_are_views_over_what_was_already_downloaded():
    """Changing the window, the size or the kind of event must not mean searching again."""
    from miratrade.scan import covered_days, filter_events

    base = pd.Timestamp("2026-09-25")
    events = _events([
        {"ticker": "BIG", "signal_date": base, "mkt_cap": 50e9,
         "event:insider_buy": True, "event:13dg": False, "event:flow": False},
        {"ticker": "MID", "signal_date": base - pd.Timedelta(days=3), "mkt_cap": 5e9,
         "event:insider_buy": False, "event:13dg": True, "event:flow": False},
        {"ticker": "OLD", "signal_date": base - pd.Timedelta(days=20), "mkt_cap": 5e9,
         "event:insider_buy": True, "event:13dg": False, "event:flow": False},
        {"ticker": "NOCAP", "signal_date": base, "mkt_cap": float("nan"),
         "event:insider_buy": True, "event:13dg": False, "event:flow": False}])

    assert len(filter_events(events)) == 4
    assert set(filter_events(events, days=7)["ticker"]) == {"BIG", "MID", "NOCAP"}
    assert set(filter_events(events, cap_tier="large")["ticker"]) == {"BIG"}
    assert set(filter_events(events, cap_tier="mid")["ticker"]) == {"MID", "OLD"}
    assert set(filter_events(events, days=7, cap_tier="mid")["ticker"]) == {"MID"}
    assert set(filter_events(events, kinds=("event:13dg",))["ticker"]) == {"MID"}
    assert filter_events(events, cap_tier="micro").empty          # unknown size is not micro
    assert filter_events(pd.DataFrame()).empty

    from datetime import date
    assert covered_days({"since": date(2026, 9, 1), "end": date(2026, 9, 26)}) == 25
    assert covered_days(None) == 0 and covered_days({"since": None, "end": None}) == 0


def test_the_refresh_window_is_new_york_time():
    """Filings arrive on New York business days: the window is stated there, not in local time."""
    from miratrade.scan import new_york_time, within_window

    # 14:00 UTC on a Tuesday is 10:00 in New York, inside a 07:00-22:30 window
    assert within_window(pd.Timestamp("2026-09-29 14:00", tz="UTC"))
    # 03:00 UTC is 23:00 the previous evening in New York: past 22:30
    assert not within_window(pd.Timestamp("2026-09-30 03:00", tz="UTC"))
    # 10:00 UTC is 06:00 in New York: before it opens
    assert not within_window(pd.Timestamp("2026-09-29 10:00", tz="UTC"))
    # Saturday in New York
    assert not within_window(pd.Timestamp("2026-10-03 14:00", tz="UTC"))
    assert within_window(pd.Timestamp("2026-10-03 14:00", tz="UTC"), weekdays_only=False)

    assert within_window(pd.Timestamp("2026-09-29 14:00"))              # naive is read as UTC
    # a window that crosses midnight still works: 23:00 in New York is inside 22:00 -> 02:00
    assert within_window(pd.Timestamp("2026-09-30 03:00", tz="UTC"), start="22:00", end="02:00")
    assert not within_window(pd.Timestamp("2026-09-29 14:00", tz="UTC"), start="22:00", end="02:00")
    assert within_window(pd.Timestamp("2026-09-30 03:00", tz="UTC"), start="20:00", end="23:30")
    assert within_window(pd.Timestamp("2026-09-29 14:00", tz="UTC"), start="mal", end="peor")

    assert new_york_time(pd.Timestamp("2026-09-29 14:00", tz="UTC")).hour == 10
