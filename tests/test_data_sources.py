"""Market data from each user's own broker: price sources, E*TRADE, broker option snapshots."""
import time
from datetime import date, datetime, timezone

import pandas as pd
import pytest

from miratrade.brokers.credentials import CredentialStore
from miratrade.brokers.etrade import (EtradeAuth, EtradeBroker, BrokerError, next_midnight_et, parse_account_list,
                                      parse_balance, parse_chain, parse_expiries, parse_portfolio, parse_quotes,
                                      quote_status)
from miratrade.config import Config
from miratrade.data.options import FLOW_COLUMNS, chain_to_flow, snapshot_broker
from miratrade.data.prices import PriceSourceError, load_prices


class MemoryKeyring:
    def __init__(self):
        self.data = {}

    def set_password(self, s, k, v):
        self.data[(s, k)] = v

    def get_password(self, s, k):
        return self.data.get((s, k))

    def delete_password(self, s, k):
        self.data.pop((s, k))


def _bars(start=None, end=None, n=5):
    """Bars for a window, so a test can see which days a loader actually asked for."""
    idx = (pd.bdate_range(start, end, name="date") if start is not None
           else pd.bdate_range("2026-01-05", periods=n, name="date"))
    return pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0}, index=idx)


# --------------------------------------------------------------------------- price sources

def test_prices_are_downloaded_once_and_then_read_from_the_store(tmp_path):
    """The old cache kept a CSV per ticker **per requested range**, so a window one day wider
    re-downloaded years of history: 908 tickers had produced 1,486 files of overlapping data."""
    from miratrade import store

    db = store.connect(tmp_path / "market.db")
    calls = []

    def fetch(t, s, e):
        calls.append((t, s, e))
        return None if t == "NOPE" else _bars()

    got = load_prices(["AAA", "NOPE"], date(2026, 1, 1), date(2026, 2, 1), tmp_path,
                      source="schwab", fetch=fetch, db=db)
    assert set(got) == {"AAA"}                          # a ticker with no data is simply left out
    assert [c[0] for c in calls] == ["AAA", "NOPE"]

    load_prices(["AAA"], date(2026, 1, 1), date(2026, 2, 1), tmp_path, source="schwab",
                fetch=fetch, db=db)
    assert len(calls) == 2                              # the same window asks the source for nothing

    # the licence follows the data, so where a bar came from is recorded with it
    assert set(store.read(db, "prices", "ticker = 'AAA'")["source"]) == {"schwab"}
    with pytest.raises(ValueError):
        load_prices(["AAA"], date(2026, 1, 1), date(2026, 2, 1), tmp_path, source="yahoo", db=db)
    db.close()


def test_a_wider_window_asks_only_for_the_days_that_are_missing(tmp_path):
    from miratrade import store

    db = store.connect(tmp_path / "market.db")
    asked = []

    def fetch(t, s, e):
        asked.append((s, e))
        return _bars(s, e)

    load_prices(["AAA"], date(2026, 1, 5), date(2026, 1, 9), tmp_path, source="research",
                fetch=fetch, db=db)
    assert asked == [(date(2026, 1, 5), date(2026, 1, 9))]

    # a window that reaches further back and further forward: one call covering both edges,
    # not the whole history again for every extra day
    load_prices(["AAA"], date(2026, 1, 1), date(2026, 1, 14), tmp_path, source="research",
                fetch=fetch, db=db)
    assert len(asked) == 2 and asked[1] == (date(2026, 1, 1), date(2026, 1, 14))

    # and now that it is covered, nothing more is asked for
    load_prices(["AAA"], date(2026, 1, 3), date(2026, 1, 12), tmp_path, source="research",
                fetch=fetch, db=db)
    assert len(asked) == 2
    db.close()


def test_not_connected_to_schwab_says_what_to_do(tmp_path, monkeypatch):
    from miratrade.brokers import schwab

    monkeypatch.setattr(schwab.SchwabAuth, "configured", lambda self: False)
    with pytest.raises(PriceSourceError, match="Settings"):
        load_prices(["AAA"], date(2026, 1, 1), date(2026, 2, 1), tmp_path, source="schwab")

    def boom(t, s, e):
        raise RuntimeError("unknown symbol")
    assert load_prices(["AAA"], date(2026, 1, 1), date(2026, 2, 1), tmp_path, source="schwab", fetch=boom) == {}


def test_cboe_page_needs_the_research_source(monkeypatch, tmp_path):
    import miratrade.config as config
    from miratrade.data.options import snapshot_cboe

    monkeypatch.setattr(config, "load_user_config", lambda path=None: Config())
    with pytest.raises(PriceSourceError, match="personal research only"):
        snapshot_cboe(["SPY"])


# --------------------------------------------------------------------------- broker snapshots

CHAIN = pd.DataFrame({"symbol": ["A  261016C00010000", "A  261016C00012000"], "underlying": ["A", "A"],
                      "type": ["C", "C"], "expiry": [pd.Timestamp("2026-10-16")] * 2, "dte": [20, 20],
                      "strike": [10.0, 12.0], "bid": [1.0, 0.2], "ask": [1.2, 0.3], "mark": [1.1, None],
                      "delta": [0.6, 0.2], "iv": [0.4, 0.45], "open_interest": [100, 50], "volume": [300, 0]})


def test_chain_to_flow_keeps_traded_contracts():
    f = chain_to_flow(CHAIN, date(2026, 9, 25), underlying=11.0)
    assert list(f.columns) == FLOW_COLUMNS and len(f) == 1
    r = f.iloc[0]
    assert r.premium == pytest.approx(300 * 1.1 * 100) and r.underlying == 11.0 and r.side == ""
    assert chain_to_flow(pd.DataFrame(), date(2026, 9, 25)).empty


class FakeBroker:
    name = "schwab"

    def quotes(self, symbols):
        return {"A": type("Q", (), {"last": 11.0})()}

    def option_chain(self, symbol, a, b):
        if symbol == "BAD":
            raise RuntimeError("no chain")
        return CHAIN


def test_snapshot_broker_stores_one_day_with_volume_and_open_interest(tmp_path):
    """The broker chain is the only free source with volume AND open interest together, which is
    what a Vol > OI reading needs. It is stored under the broker's name, because the sources are not
    interchangeable."""
    from miratrade import store

    db = store.connect(tmp_path / "market.db")
    df = snapshot_broker(["a", "bad"], FakeBroker(), asof=date(2026, 9, 25), db=db,
                         log=lambda _m: None)
    assert len(df) == 1

    rows = store.read(db, "option_flow")
    assert len(rows) == 1
    row = rows.iloc[0]
    assert row["ticker"] == "A" and row["source"] == "schwab"
    assert row["volume"] == 300 and row["open_interest"] == 100       # both, which is the point
    assert row["date"] == pd.Timestamp("2026-09-25")

    # the ticker that answered is remembered; the one that failed is not, so it is asked again
    assert store.covered(db, "flow_schwab", scope="A") == {"2026-09-25"}
    assert store.covered(db, "flow_schwab", scope="BAD") == set()
    db.close()


def test_snapshotting_the_same_day_twice_updates_rather_than_duplicates(tmp_path):
    from miratrade import store

    db = store.connect(tmp_path / "market.db")
    for _ in range(2):
        snapshot_broker(["a"], FakeBroker(), asof=date(2026, 9, 25), db=db, log=lambda _m: None)
    assert len(store.read(db, "option_flow")) == 1
    db.close()


def test_two_sources_for_the_same_contract_day_are_kept_apart(tmp_path):
    """A broker snapshot and a historical feed disagree — the free history has no open interest at
    all. Letting one overwrite the other would hide that; they are separate rows."""
    from miratrade import store

    db = store.connect(tmp_path / "market.db")
    snapshot_broker(["a"], FakeBroker(), asof=date(2026, 9, 25), db=db, log=lambda _m: None)
    same_day = store.read(db, "option_flow").assign(source="massive", open_interest=None)
    store.write(db, "option_flow", same_day)

    rows = store.read(db, "option_flow")
    assert len(rows) == 2
    assert sorted(rows["source"]) == ["massive", "schwab"]
    assert rows.set_index("source").loc["schwab", "open_interest"] == 100
    assert pd.isna(rows.set_index("source").loc["massive", "open_interest"])
    db.close()


# --------------------------------------------------------------------------- E*TRADE

class _R:
    def __init__(self, status=200, text="", payload=None):
        self.status_code, self.text, self._payload = status, text, payload

    def json(self):
        return self._payload


class FakeSession:
    """Answers the OAuth endpoints and records every call."""
    calls = []
    routes = {}

    def __init__(self, *a, **k):
        self.args = a
        self.kwargs = k

    def get(self, url, params=None, headers=None):
        FakeSession.calls.append((url, params, self.kwargs.get("verifier")))
        for key, resp in FakeSession.routes.items():
            if key in url:
                return resp
        return _R(404, "no route")


def _auth():
    FakeSession.calls = []
    FakeSession.routes = {
        "request_token": _R(text="oauth_token=req&oauth_token_secret=reqs&oauth_callback_confirmed=true"),
        "access_token": _R(text="oauth_token=acc&oauth_token_secret=accs"),
        "renew_access_token": _R(text="Access Token has been renewed"),
    }
    a = EtradeAuth(CredentialStore(backend=MemoryKeyring()), session_factory=FakeSession)
    a.setup("ck", "cs", sandbox=True)
    return a


def test_etrade_login_flow_and_token_storage():
    a = _auth()
    url = a.login_url()
    assert "key=ck" in url and "token=req" in url and a.env == "sandbox"
    with pytest.raises(ValueError):
        a.complete_login("  ")
    a.complete_login(" AB12C ")
    tok = a.store.get_json("etrade.token")
    assert tok["token"] == "acc" and tok["secret"] == "accs"
    assert FakeSession.calls[-1][2] == "AB12C"                      # the verifier went with the exchange
    assert 0 < a.hours_left() <= 24


def test_etrade_token_dies_at_midnight_new_york_and_renews_when_idle():
    # 2026-09-25 22:00 UTC = 18:00 in New York → expires at 04:00 UTC on the 26th
    ts = datetime(2026, 9, 25, 22, 0, tzinfo=timezone.utc).timestamp()
    assert next_midnight_et(ts) == datetime(2026, 9, 26, 4, 0, tzinfo=timezone.utc)
    a = _auth()
    a.login_url()
    a.complete_login("x")
    tok = a.store.get_json("etrade.token")
    tok["used"] = time.time() - 3 * 3600                           # idle three hours
    a.store.set_json("etrade.token", tok)
    a.session()
    assert any("renew_access_token" in c[0] for c in FakeSession.calls)
    tok["created"] = time.time() - 3 * 86400                       # yesterday's token
    a.store.set_json("etrade.token", tok)
    with pytest.raises(BrokerError, match="midnight"):
        a.session()


def test_etrade_parsers():
    accts = parse_account_list({"AccountListResponse": {"Accounts": {"Account": [
        {"accountId": "12345678", "accountIdKey": "k1", "accountStatus": "ACTIVE", "institutionType": "BROKERAGE"},
        {"accountId": "999", "accountIdKey": "k2", "accountStatus": "CLOSED"}]}}})
    assert [a["accountIdKey"] for a in accts] == ["k1"]
    bal = parse_balance({"BalanceResponse": {"Computed": {"cashBalance": 1000, "cashBuyingPower": 2000,
                                                          "RealTimeValues": {"totalAccountValue": 5000}}}})
    assert bal == {"equity": 5000, "cash": 1000, "buying_power": 2000}
    pos = parse_portfolio({"PortfolioResponse": {"AccountPortfolio": [{"Position": {
        "Product": {"symbol": "ACME", "securityType": "EQ"}, "quantity": 10, "pricePaid": 5.0, "marketValue": 60}}]}})
    assert pos[0].symbol == "ACME" and pos[0].quantity == 10 and pos[0].asset_type == "EQUITY"
    qd = {"QuoteResponse": {"QuoteData": [{"Product": {"symbol": "SPY"}, "quoteStatus": "DELAYED",
                                           "dateTimeUTC": 1790000000,
                                           "All": {"bid": 1.0, "ask": 1.1, "lastTrade": 1.05, "totalVolume": 7}}]}}
    q = parse_quotes(qd)["SPY"]
    assert q.bid == 1.0 and q.last == 1.05 and q.time.year == 2026 and quote_status(qd) == {"DELAYED"}
    exp = parse_expiries({"OptionExpireDateResponse": {"ExpirationDate": [
        {"year": 2026, "month": 11, "day": 20}, {"year": 2026, "month": 10, "day": 16}]}})
    assert exp == [date(2026, 10, 16), date(2026, 11, 20)]
    ch = parse_chain({"OptionChainResponse": {"OptionPair": [{
        "Call": {"osiKey": "SPY---261016C00600000", "strikePrice": 600, "bid": 10.0, "ask": 10.4, "volume": 5,
                 "openInterest": 90, "OptionGreeks": {"delta": 0.55, "iv": 0.18}},
        "Put": {"osiKey": "SPY---261016P00600000", "strikePrice": 600, "bid": 9.0, "ask": 9.2}}]}},
        "SPY", date(2026, 10, 16), today=date(2026, 9, 26))
    call = ch[ch["type"] == "C"].iloc[0]
    assert len(ch) == 2 and call.mark == pytest.approx(10.2) and call.dte == 20 and call.delta == 0.55


def test_etrade_broker_is_read_only_and_has_no_history():
    b = EtradeBroker(auth=_auth(), session=FakeSession())
    with pytest.raises(BrokerError, match="no price history"):
        b.price_history("SPY", date(2026, 1, 1), date(2026, 2, 1))
    with pytest.raises(BrokerError, match="only through Schwab"):
        b.place("k1", None)


def test_etrade_option_chain_filters_expiries():
    FakeSession.routes = {
        "optionexpiredate": _R(payload={"OptionExpireDateResponse": {"ExpirationDate": [
            {"year": 2026, "month": 10, "day": 16}, {"year": 2027, "month": 1, "day": 15}]}}),
        "optionchains": _R(payload={"OptionChainResponse": {"OptionPair": [{"Call": {
            "osiKey": "X", "strikePrice": 10, "bid": 1.0, "ask": 1.2}}]}}),
    }
    FakeSession.calls = []
    a = EtradeAuth(CredentialStore(backend=MemoryKeyring()), session_factory=FakeSession)
    b = EtradeBroker(auth=a, session=FakeSession())
    ch = b.option_chain("ACME", date(2026, 10, 1), date(2026, 12, 31), contract_type="CALL")
    assert len(ch) == 1 and ch["expiry"].iat[0] == pd.Timestamp("2026-10-16")
    chain_calls = [c for c in FakeSession.calls if "optionchains" in c[0]]
    assert len(chain_calls) == 1 and chain_calls[0][1]["chainType"] == "CALL"


def test_quote_status_covers_what_etrade_actually_returns():
    """A closed market answers CLOSING, not REALTIME or DELAYED: the message must not imply the
    market data agreement is missing when it simply cannot be told yet."""
    from miratrade.etrade_cli import QUOTE_STATUS

    assert {"REALTIME", "DELAYED", "CLOSING", "EH_REALTIME", "EH_BEFORE_OPEN", "EH_CLOSED"} <= set(QUOTE_STATUS)
    assert "acuerdo de datos de mercado" in QUOTE_STATUS["DELAYED"]
    assert "cerrado" in QUOTE_STATUS["CLOSING"]
    payload = {"QuoteResponse": {"QuoteData": [{"Product": {"symbol": "SPY"}, "quoteStatus": "CLOSING",
                                                "All": {"bid": 772.0, "ask": 772.04, "lastTrade": 771.35}}]}}
    assert quote_status(payload) == {"CLOSING"}
    assert parse_quotes(payload)["SPY"].bid == 772.0        # a closed market still parses


@pytest.mark.parametrize("taken, session", [
    ("2026-09-27 18:00Z", date(2026, 9, 25)),   # Sunday: the data is still Friday's
    ("2026-09-26 18:00Z", date(2026, 9, 25)),   # Saturday, the same
    ("2026-09-28 12:00Z", date(2026, 9, 25)),   # Monday 08:00 New York: nothing has traded yet
    ("2026-09-28 14:00Z", date(2026, 9, 28)),   # Monday 10:00: the session is under way
    ("2026-09-28 21:00Z", date(2026, 9, 28)),   # Monday 17:00: closed, and complete
])
def test_a_snapshot_is_labelled_with_the_session_it_belongs_to(taken, session):
    """A chain always shows the last session's figures. Labelling a snapshot with the calendar day it
    was taken filed Friday's trading under a Sunday date — a day the market never opened."""
    from miratrade.data.options import session_date

    assert session_date(taken) == session


def test_a_weekend_snapshot_does_not_invent_a_session(tmp_path):
    from miratrade import store
    from miratrade.data.options import session_date, snapshot_broker

    db = store.connect(tmp_path / "market.db")
    snapshot_broker(["a"], FakeBroker(), asof=session_date("2026-09-27 18:00Z"), db=db,
                    log=lambda _m: None)
    days = sorted(set(store.read(db, "option_flow")["date"].dt.date))
    assert days == [date(2026, 9, 25)]
    assert all(d.weekday() < 5 for d in days)
    db.close()
