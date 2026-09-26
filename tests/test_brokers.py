"""Broker layer tests. Nothing here talks to Schwab: a fake client returns responses shaped like
the Trader API's, and no test can send a real order."""
import json
from datetime import date, datetime, timedelta, timezone

import pytest

from miratrade.brokers.base import Account, OrderRequest, OrderStatus, Position, Quote
from miratrade.brokers.credentials import CredentialStore
from miratrade.brokers.guard import OrderGuard, OrderRefused, OrderUncertain
from miratrade.brokers.schwab import (BrokerError, SchwabAuth, SchwabBroker, order_spec, parse_accounts,
                                      parse_candles, parse_chain, parse_preview, parse_quotes, tick_round)
from miratrade.brokers.simulated import SimulatedBroker
from miratrade.config import Config

NOW = datetime(2026, 9, 28, 14, 0, tzinfo=timezone.utc)


class MemoryKeyring:
    """keyring stand-in with the Windows size limit."""
    def __init__(self):
        self.data = {}

    def set_password(self, service, key, value):
        if len(value) > 1200:
            raise OSError("CredWrite: The stub received bad data")
        self.data[(service, key)] = value

    def get_password(self, service, key):
        return self.data.get((service, key))

    def delete_password(self, service, key):
        self.data.pop((service, key))


# ------------------------------------------------------------------ credentials / auth

def test_credential_store_splits_long_secrets():
    kr = MemoryKeyring()
    store = CredentialStore(backend=kr)
    token = {"creation_timestamp": 1, "token": {"access_token": "a" * 1500, "id_token": "b" * 1800}}
    store.set_json("schwab.token", token)
    assert store.get_json("schwab.token") == token
    assert all(len(v) <= 1000 for v in kr.data.values())
    store.delete("schwab.token")
    assert kr.data == {}


def test_half_written_secret_reads_as_missing():
    kr = MemoryKeyring()
    store = CredentialStore(backend=kr)
    store.set("x", "y" * 2500)
    del kr.data[("MiraTrade", "x#1")]
    assert store.get("x") is None


def test_auth_setup_and_expiry():
    store = CredentialStore(backend=MemoryKeyring())
    auth = SchwabAuth(store)
    with pytest.raises(ValueError):
        auth.setup("key", "secret", "https://example.com/callback")
    auth.setup("key", "secret", "https://127.0.0.1:8182")
    assert auth.configured() and auth.token_expires() is None
    store.set_json("schwab.token", {"creation_timestamp": 1_790_000_000, "token": {}})
    assert auth.token_expires() == datetime.fromtimestamp(1_790_000_000, timezone.utc) + timedelta(days=7)
    with pytest.raises(RuntimeError):
        auth.complete_login("https://127.0.0.1:8182/?code=abc")   # login_url() not called yet
    auth.logout()
    with pytest.raises(RuntimeError):
        auth.client()


# ------------------------------------------------------------------ order JSON

def test_equity_bracket_spec():
    req = OrderRequest("ACME", 10, 48.2, stop_price=45.084, target_price=51.157)
    spec = order_spec(req)
    assert spec["orderStrategyType"] == "TRIGGER" and spec["orderType"] == "LIMIT" and spec["price"] == "48.20"
    assert spec["orderLegCollection"][0]["instruction"] == "BUY"
    oco = spec["childOrderStrategies"][0]
    assert oco["orderStrategyType"] == "OCO"
    target, stop = oco["childOrderStrategies"]
    assert target["price"] == "51.16" and target["duration"] == "GOOD_TILL_CANCEL"   # rounded, not truncated
    assert stop["orderType"] == "STOP" and stop["stopPrice"] == "45.08"
    assert {c["orderLegCollection"][0]["instruction"] for c in (target, stop)} == {"SELL"}


def test_option_bracket_and_closing_specs():
    sym = "ACME  261120C00045000"
    spec = order_spec(OrderRequest(sym, 2, 4.9, asset_type="OPTION", stop_price=2.45, target_price=9.8))
    assert spec["orderLegCollection"][0] == {"instruction": "BUY_TO_OPEN", "quantity": 2,
                                              "instrument": {"assetType": "OPTION", "symbol": sym}}
    legs = [c["orderLegCollection"][0]["instruction"] for c in spec["childOrderStrategies"][0]["childOrderStrategies"]]
    assert legs == ["SELL_TO_CLOSE", "SELL_TO_CLOSE"]
    close = order_spec(OrderRequest("ACME", 10, 50.0, side="SELL"))
    assert close["orderStrategyType"] == "SINGLE" and close["orderLegCollection"][0]["instruction"] == "SELL"


def test_tick_round():
    assert tick_round(51.157) == 51.16 and tick_round(0.123456) == 0.1235


# ------------------------------------------------------------------ parsing (Trader API shapes)

ACCOUNTS = [{"securitiesAccount": {
    "accountNumber": "12345678", "type": "MARGIN",
    "positions": [{"longQuantity": 10, "shortQuantity": 0, "averagePrice": 47.1, "marketValue": 482.0,
                   "currentDayProfitLoss": -12.5, "instrument": {"symbol": "ACME", "assetType": "EQUITY"}}],
    "currentBalances": {"liquidationValue": 25000.0, "cashBalance": 24518.0, "buyingPower": 49000.0}}}]
NUMBERS = [{"accountNumber": "12345678", "hashValue": "HASH1"}]


def test_parse_accounts_masks_number():
    acc = parse_accounts(NUMBERS, ACCOUNTS)[0]
    assert acc.number_masked == "…5678" and acc.account_hash == "HASH1" and acc.equity == 25000.0
    assert acc.positions[0].quantity == 10 and acc.day_pl == -12.5


def test_parse_quotes_chain_candles_preview():
    q = parse_quotes({"SPY": {"symbol": "SPY", "quote": {"bidPrice": 1.0, "askPrice": 1.1, "lastPrice": 1.05,
                                                         "netPercentChange": 0.4, "totalVolume": 9,
                                                         "quoteTime": 1790000000000}}})
    assert q["SPY"].ask == 1.1 and q["SPY"].time.year == 2026
    chain = parse_chain({"symbol": "ACME", "callExpDateMap": {"2026-11-20:55": {"45.0": [
        {"putCall": "CALL", "symbol": "ACME  261120C00045000", "bid": 4.8, "ask": 5.0, "mark": 4.9,
         "delta": 0.66, "volatility": 42.5, "openInterest": 120, "totalVolume": 30,
         "daysToExpiration": 55, "strikePrice": 45.0}]}}, "putExpDateMap": {}})
    r = chain.iloc[0]
    assert r["type"] == "C" and r["dte"] == 55 and r["iv"] == pytest.approx(0.425)
    candles = parse_candles({"candles": [{"datetime": 1790395200000, "open": 1, "high": 2, "low": 0.5,
                                          "close": 1.5, "volume": 100}]})
    assert str(candles.index[0].date()) == "2026-09-26" and candles["close"].iat[0] == 1.5
    req = OrderRequest("ACME", 10, 48.2, stop_price=45.0)
    p = parse_preview(req, {"orderValidationResult": {"rejects": [{"message": "Insufficient funds"}],
                                                       "warns": [{"message": "Low volume"}]},
                            "orderStrategy": {"orderBalance": {"orderValue": 482.0}}})
    assert not p.accepted and p.messages == ["REJECT: Insufficient funds", "WARN: Low volume"]
    assert parse_preview(req, {}).accepted


# ------------------------------------------------------------------ SchwabBroker with a fake client

class Resp:
    def __init__(self, status=200, body=None, headers=None):
        self.status_code, self._body, self.headers, self.text = status, body, headers or {}, ""

    def json(self):
        return self._body


class FakeClient:
    from schwab.client import Client as _C
    Account, Options = _C.Account, _C.Options

    def __init__(self, place_status=201):
        self.placed, self.place_status = [], place_status

    def get_account_numbers(self):
        return Resp(body=NUMBERS)

    def get_accounts(self, fields=None):
        return Resp(body=ACCOUNTS)

    def place_order(self, account_hash, spec):
        self.placed.append((account_hash, spec))
        if self.place_status >= 400:
            return Resp(self.place_status, {"message": "Order rejected: insufficient buying power"})
        return Resp(201, headers={"Location": f"https://api.schwabapi.com/trader/v1/accounts/{account_hash}/orders/987654"})


def test_schwab_broker_accounts_and_place():
    fake = FakeClient()
    b = SchwabBroker(client=fake, auth=SchwabAuth(CredentialStore(backend=MemoryKeyring())))
    assert b.accounts()[0].account_hash == "HASH1"
    assert b.place("HASH1", OrderRequest("ACME", 1, 48.2, stop_price=45.0)) == "987654"
    bad = SchwabBroker(client=FakeClient(place_status=400), auth=b.auth)
    with pytest.raises(BrokerError, match="insufficient buying power"):
        bad.place("HASH1", OrderRequest("ACME", 1, 48.2, stop_price=45.0))


# ------------------------------------------------------------------ the guard

class LiveFake(SimulatedBroker):
    """Simulated fills, but flagged as real money so the live-trading rules apply."""
    name, is_live = "livefake", True

    def __init__(self, fail_place=False, **kw):
        super().__init__(**kw)
        self.fail_place, self.place_calls = fail_place, 0

    def place(self, account_hash, request):
        self.place_calls += 1
        if self.fail_place:
            super().place(account_hash, request)      # it did reach the broker…
            raise TimeoutError("read timed out")      # …but the reply was lost
        return super().place(account_hash, request)


def _acct(equity=25_000.0, positions=(), day_pl=0.0):
    return Account("…5678", "SIM", equity, equity, equity, day_pl, list(positions))


def _guard(tmp_path, broker=None, live=False):
    cfg = Config()
    cfg.broker.live_trading = live
    return OrderGuard(broker or SimulatedBroker(clock=lambda: NOW), cfg, tmp_path, clock=lambda: NOW)


GOOD = OrderRequest("ACME", 100, 48.2, stop_price=45.7, target_price=53.2)   # risk $250 = 1%


@pytest.mark.parametrize("req, account, reason", [
    (OrderRequest("ACME", 100, 48.2), _acct(), "needs a stop"),
    (OrderRequest("ACME", 100, None, stop_price=45.0), _acct(), "limit orders"),
    (OrderRequest("ACME", 100, 48.2, stop_price=40.0), _acct(), "ceiling"),            # 3.3% risk
    (OrderRequest("PNNY", 100, 3.0, stop_price=2.5), _acct(), "minimum"),
    (OrderRequest("ACME", 100, 48.2, stop_price=49.0), _acct(), "below the entry"),
    (GOOD, _acct(positions=[Position(s, "EQUITY", 1, 1, 1) for s in "ABCDE"]), "open positions"),
    (GOOD, _acct(day_pl=-800), "daily limit"),
    (GOOD, _acct(equity=None), "equity unknown"),
])
def test_guard_refusals(tmp_path, req, account, reason):
    with pytest.raises(OrderRefused, match=reason):
        _guard(tmp_path).preview(account, req)


def test_guard_suggests_size_from_risk(tmp_path):
    assert _guard(tmp_path).suggest_quantity(_acct(), 48.2, 45.7) == 100
    assert _guard(tmp_path).suggest_quantity(_acct(), 4.9, 2.45, multiplier=100) == 1


def test_place_needs_a_fresh_matching_preview(tmp_path):
    g = _guard(tmp_path)
    acc = _acct()
    with pytest.raises(OrderRefused, match="Preview"):
        g.place(acc, GOOD)
    g.preview(acc, GOOD)
    other = OrderRequest("ACME", 99, 48.2, stop_price=45.7, target_price=53.2)
    with pytest.raises(OrderRefused, match="Preview"):
        g.place(acc, other)                                   # a different order than previewed
    assert g.place(acc, GOOD)
    with pytest.raises(OrderRefused, match="Preview"):
        g.place(acc, GOOD)                                    # one preview, one submission
    later = OrderGuard(g.broker, g.cfg, tmp_path, clock=lambda: NOW + timedelta(minutes=5))
    later._previews = {}
    g.preview(acc, GOOD)
    later._previews = g._previews
    with pytest.raises(OrderRefused, match="expired"):
        later.place(acc, GOOD)


def test_live_orders_need_switch_and_typed_confirmation(tmp_path):
    broker = LiveFake(clock=lambda: NOW)
    acc = _acct()
    off = _guard(tmp_path, broker, live=False)
    off.preview(acc, GOOD)
    with pytest.raises(OrderRefused, match="Live trading is off"):
        off.place(acc, GOOD, "BUY 100 ACME")
    on = _guard(tmp_path, broker, live=True)
    on.preview(acc, GOOD)
    with pytest.raises(OrderRefused, match="Type"):
        on.place(acc, GOOD, "yes")
    assert broker.place_calls == 0
    assert on.place(acc, GOOD, "buy 100 acme")               # case and spacing don't matter
    assert broker.place_calls == 1


def test_lost_reply_is_reported_not_retried(tmp_path):
    broker = LiveFake(fail_place=True, clock=lambda: NOW)
    g = _guard(tmp_path, broker, live=True)
    acc = _acct()
    g.preview(acc, GOOD)
    with pytest.raises(OrderUncertain, match="1 WORKING"):
        g.place(acc, GOOD, "BUY 100 ACME")
    assert broker.place_calls == 1
    events = [json.loads(line)["event"] for line in (tmp_path / "orders.jsonl").read_text().splitlines()]
    assert events == ["preview", "submit", "uncertain"]


def test_stop_all_cancels_entries_keeps_protective_exits(tmp_path):
    class Orders(SimulatedBroker):
        def __init__(self):
            super().__init__(clock=lambda: NOW)
            self.cancelled = []

        def orders(self, account_hash, since, until=None):
            return [OrderStatus("1", "ACME", "WORKING", "BUY", 10, 0, 48.2, NOW),
                    OrderStatus("2", "NOVA", "WORKING", "SELL", 5, 0, 120.0, NOW),       # a position's stop
                    OrderStatus("3", "KLTR", "FILLED", "BUY", 5, 5, 20.0, NOW)]

        def cancel(self, account_hash, order_id):
            self.cancelled.append(order_id)

    broker = Orders()
    g = _guard(tmp_path, broker)
    assert g.stop_all(_acct()) == ["1"] and broker.cancelled == ["1"]
    with pytest.raises(OrderRefused, match="stopped"):
        g.preview(_acct(), GOOD)
    g.resume()
    assert g.preview(_acct(), GOOD)[0].accepted


def test_journal_masks_account_and_holds_no_hash(tmp_path):
    g = _guard(tmp_path)
    g.preview(Account("…5678", "SECRET-HASH", 25_000.0, 25_000.0, 25_000.0), GOOD)
    text = (tmp_path / "orders.jsonl").read_text(encoding="utf-8")
    assert json.loads(text.splitlines()[0])["account"] == "…5678" and "SECRET-HASH" not in text


# ------------------------------------------------------------------ practice broker

def test_simulated_bracket_fills_and_exits():
    b = SimulatedBroker(cash=25_000, clock=lambda: NOW)
    oid = b.place("SIM", GOOD)
    assert b.mark({"ACME": Quote("ACME", 48.5, 48.6, 48.55)}) == []          # above the limit: no fill
    fill = b.mark({"ACME": Quote("ACME", 48.0, 48.1, 48.05)})
    assert fill[0]["price"] == 48.1 and b.positions["ACME"].quantity == 100
    exit_ = b.mark({"ACME": Quote("ACME", 53.5, 53.6, 53.5)})                  # through the target
    assert exit_[0]["description"] == "target" and "ACME" not in b.positions
    assert b.cash == pytest.approx(25_000 + (53.5 - 48.1) * 100)
    assert [o.status for o in b.orders("SIM", NOW - timedelta(days=1))] == ["FILLED"] and oid == "1"


def test_guard_with_simulated_broker_end_to_end(tmp_path):
    b = SimulatedBroker(cash=25_000, clock=lambda: NOW)
    g = _guard(tmp_path, b)
    acc = b.accounts()[0]
    preview, check = g.preview(acc, GOOD)
    assert preview.accepted and check.risk_pct == pytest.approx(1.0)
    assert g.place(acc, GOOD)                                  # practice: no confirmation needed
    b.mark({"ACME": Quote("ACME", 48.0, 48.1, 48.05)})
    b.mark({"ACME": Quote("ACME", 45.0, 45.1, 45.0)})         # gaps through the stop
    assert b.accounts()[0].day_pl == pytest.approx((45.0 - 48.1) * 100)
