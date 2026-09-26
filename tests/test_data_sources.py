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


def _bars(n=5):
    idx = pd.bdate_range("2026-01-05", periods=n, name="date")
    return pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0}, index=idx)


# --------------------------------------------------------------------------- price sources

def test_each_source_has_its_own_cache(tmp_path):
    calls = []

    def fetch(t, s, e):
        calls.append(t)
        return None if t == "NOPE" else _bars()

    got = load_prices(["AAA", "NOPE"], date(2026, 1, 1), date(2026, 2, 1), tmp_path, source="schwab", fetch=fetch)
    assert set(got) == {"AAA"} and (tmp_path / "schwab" / "AAA_20260101_20260201.csv").exists()
    load_prices(["AAA"], date(2026, 1, 1), date(2026, 2, 1), tmp_path, source="schwab", fetch=fetch)
    assert calls == ["AAA", "NOPE"]                                 # second call served from the cache
    load_prices(["AAA"], date(2026, 1, 1), date(2026, 2, 1), tmp_path, source="research", fetch=fetch)
    assert calls[-1] == "AAA" and (tmp_path / "AAA_20260101_20260201.csv").exists()   # research: its own copy
    with pytest.raises(ValueError):
        load_prices(["AAA"], date(2026, 1, 1), date(2026, 2, 1), tmp_path, source="yahoo")


def test_not_connected_to_schwab_says_what_to_do(tmp_path, monkeypatch):
    from miratrade.brokers import schwab

    monkeypatch.setattr(schwab.SchwabAuth, "configured", lambda self: False)
    with pytest.raises(PriceSourceError, match="Configuración"):
        load_prices(["AAA"], date(2026, 1, 1), date(2026, 2, 1), tmp_path, source="schwab")

    def boom(t, s, e):
        raise RuntimeError("unknown symbol")
    assert load_prices(["AAA"], date(2026, 1, 1), date(2026, 2, 1), tmp_path, source="schwab", fetch=boom) == {}


def test_cboe_page_needs_the_research_source(monkeypatch, tmp_path):
    import miratrade.config as config
    from miratrade.data.options import snapshot_cboe

    monkeypatch.setattr(config, "load_user_config", lambda path=None: Config())
    with pytest.raises(PriceSourceError, match="investigación personal"):
        snapshot_cboe(["SPY"], out_dir=tmp_path)


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


def test_snapshot_broker_saves_one_day(tmp_path):
    class FakeBroker:
        name = "schwab"

        def quotes(self, symbols):
            return {"A": type("Q", (), {"last": 11.0})()}

        def option_chain(self, symbol, a, b):
            if symbol == "BAD":
                raise RuntimeError("no chain")
            return CHAIN

    df = snapshot_broker(["a", "bad"], FakeBroker(), asof=date(2026, 9, 25), out_dir=tmp_path)
    assert len(df) == 1 and (tmp_path / "schwab_20260925.csv").exists()


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
