"""Shares outstanding (SEC XBRL), point-in-time market cap and the cap conditions."""
import numpy as np
import pandas as pd

from miratrade.backtest import conditions
from miratrade.data.fundamentals import market_cap, parse_shares, ticker_ciks

PAYLOAD = {"units": {"shares": [
    # 10-K cover with two share classes: summed
    {"end": "2025-02-10", "val": 900, "accn": "a1", "filed": "2025-02-20", "form": "10-K"},
    {"end": "2025-02-10", "val": 100, "accn": "a1", "filed": "2025-02-20", "form": "10-K"},
    {"end": "2025-05-01", "val": 1200, "accn": "a2", "filed": "2025-05-08", "form": "10-Q"},
    {"end": "2025-05-01", "val": 0, "accn": "a3", "filed": "2025-05-09", "form": "10-Q"},  # bad row: dropped
]}}


def test_parse_shares_sums_classes_and_orders_by_filing():
    s = parse_shares(PAYLOAD)
    assert list(s["shares"]) == [1000, 1200]
    assert list(s["filed"]) == [pd.Timestamp("2025-02-20"), pd.Timestamp("2025-05-08")]
    assert parse_shares({}).empty


def test_market_cap_is_point_in_time():
    shares = parse_shares(PAYLOAD).assign(ticker="ACME")
    dates = pd.bdate_range("2025-02-18", "2025-05-12")
    close = pd.Series(10.0, index=dates)
    cap = market_cap(dates, close, shares, "ACME")
    assert np.isnan(cap[pd.Timestamp("2025-02-19")])               # nothing filed yet
    assert cap[pd.Timestamp("2025-02-20")] == 10_000               # known from the filing day
    assert cap[pd.Timestamp("2025-05-07")] == 10_000               # the 10-Q is not known yet
    assert cap[pd.Timestamp("2025-05-08")] == 12_000
    assert market_cap(dates, close, shares, "OTHER").isna().all()
    assert market_cap(dates, close, None, "ACME").isna().all()


def test_ticker_ciks_prefers_the_form4_issuer():
    tj = {"0": {"ticker": "ACME", "cik_str": 111}, "1": {"ticker": "BETA", "cik_str": 222}}
    ins = pd.DataFrame({"ticker": ["ACME"], "issuer_cik": ["0000333"], "filing_date": [pd.Timestamp("2025-01-01")]})
    own = pd.DataFrame({"ticker": ["GAMA"], "subject_cik": ["444"]})
    assert ticker_ciks(ins, tj, own) == {"ACME": "333", "BETA": "222", "GAMA": "444"}


def _row(cap, buy):
    base = {"ins_fresh": 1, "flow_fresh": 0, "ins_buy_value": buy, "ins_cluster": 1, "ins_exec_buy": 0,
            "ins_max_delta_own": 0.0, "ins_sell_value": 0.0, "flow_bull_prem": 0.0, "flow_bear_prem": 0.0,
            "flow_n_unusual": 0, "close": 10.0, "sma20": 9.0, "sma50": 8.0, "sma200": 7.0, "ret_20d": 0.1,
            "rsi": 50.0, "rel_volume": 1.0, "mkt_cap": cap}
    return pd.Series(base)


def test_cap_conditions():
    c = conditions(_row(500e6, 1e6))                               # 1 M$ in a 500 M$ company = 0.2 %
    assert c["cap:small"] and c["ins:buy_0.1%cap"]
    c = conditions(_row(50e9, 1e6))                                # the same buy in a 50 000 M$ company
    assert not c["cap:small"] and not c["ins:buy_0.1%cap"]
    c = conditions(_row(np.nan, 1e6))                              # unknown cap: neither fires
    assert not c["cap:small"] and not c["ins:buy_0.1%cap"]


def test_market_cap_accepts_mixed_datetime_units():
    """Cached bars and freshly downloaded ones arrive with different datetime units."""
    shares = parse_shares(PAYLOAD).assign(ticker="ACME")
    shares["filed"] = shares["filed"].astype("datetime64[us]")
    dates = pd.bdate_range("2025-02-18", "2025-05-12").astype("datetime64[s]")
    cap = market_cap(pd.DatetimeIndex(dates), pd.Series(10.0, index=dates), shares, "ACME")
    assert cap.notna().sum() > 0 and cap.iloc[-1] == 12_000
