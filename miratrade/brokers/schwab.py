"""Charles Schwab Trader API (personal developer app) behind ``BrokerClient``.

HTTP, OAuth refresh and order JSON come from ``schwab-py``; this module adds:

* **Login** without a local web server: the app opens Schwab's login page, you sign in and
  paste back the address Schwab redirects to (``https://127.0.0.1:8182/?code=…``).
* **Secrets** (app key, app secret, OAuth token) in the Windows Credential Manager.
* **Normalised data**: accounts, positions, quotes, option chains, price history, orders and
  transactions as the plain types in ``base.py``.

Schwab's refresh token lasts 7 days; after that ``login`` must run again. Account numbers are
shown masked; the API is addressed with each account's hash.

Response parsing is defensive (``.get`` everywhere) because field names were taken from the
public documentation; ``miratrade schwab diagnose`` saves redacted raw responses to check them.
"""
from __future__ import annotations

import warnings
from datetime import date, datetime, timedelta, timezone

import pandas as pd

from miratrade.brokers.base import (Account, BrokerClient, OrderPreview, OrderRequest, OrderStatus,
                                    Position, Quote)
from miratrade.brokers.credentials import CredentialStore

REFRESH_TOKEN_DAYS = 7
KEY, SECRET, CALLBACK, TOKEN = "schwab.app_key", "schwab.app_secret", "schwab.callback_url", "schwab.token"


def _schwab():
    with warnings.catch_warnings():         # authlib's httpx deprecation notice is not ours
        warnings.simplefilter("ignore")
        import schwab
        import schwab.auth
        import schwab.orders.common
        import schwab.orders.equities
        import schwab.orders.options
    return schwab


# --------------------------------------------------------------------------- authentication

class SchwabAuth:
    def __init__(self, store: CredentialStore | None = None):
        self.store = store or CredentialStore()
        self._context = None

    def configured(self) -> bool:
        return bool(self.store.get(KEY) and self.store.get(SECRET))

    def setup(self, app_key: str, app_secret: str, callback_url: str) -> None:
        if not callback_url.startswith("https://127.0.0.1"):
            raise ValueError("The callback URL must be https://127.0.0.1[:port], exactly as registered "
                             "in your Schwab developer app (e.g. https://127.0.0.1:8182).")
        self.store.set(KEY, app_key.strip())
        self.store.set(SECRET, app_secret.strip())
        self.store.set(CALLBACK, callback_url.strip())

    def login_url(self) -> str:
        """Step 1: the Schwab page to open in the browser."""
        self._context = _schwab().auth.get_auth_context(self.store.get(KEY), self.store.get(CALLBACK))
        return self._context.authorization_url

    def complete_login(self, received_url: str):
        """Step 2: the full address the browser landed on after signing in."""
        if self._context is None:
            raise RuntimeError("Call login_url() first, in the same session.")
        if "code=" not in received_url:
            raise ValueError("That address has no ?code=…: copy the whole URL from the browser bar.")
        return _schwab().auth.client_from_received_url(
            self.store.get(KEY), self.store.get(SECRET), self._context, received_url.strip(),
            token_write_func=self._write_token)

    def _write_token(self, token, *args, **kwargs):
        self.store.set_json(TOKEN, token)

    def client(self):
        """A client that refreshes its access token by itself (and saves each refresh)."""
        if self.store.get_json(TOKEN) is None:
            raise RuntimeError("Not logged in to Schwab: run `miratrade schwab login`.")
        return _schwab().auth.client_from_access_functions(
            self.store.get(KEY), self.store.get(SECRET),
            token_read_func=lambda: self.store.get_json(TOKEN), token_write_func=self._write_token)

    def token_expires(self) -> datetime | None:
        """When the refresh token stops working and a new login is needed."""
        token = self.store.get_json(TOKEN)
        if not token or "creation_timestamp" not in token:
            return None
        return datetime.fromtimestamp(token["creation_timestamp"], timezone.utc) + timedelta(days=REFRESH_TOKEN_DAYS)

    def logout(self) -> None:
        self.store.delete(TOKEN)

    def forget(self) -> None:
        for name in (TOKEN, KEY, SECRET, CALLBACK):
            self.store.delete(name)


# --------------------------------------------------------------------------- helpers

def mask(account_number: str) -> str:
    return "…" + str(account_number)[-4:]


def tick_round(price: float) -> float:
    """Schwab prices: cents from $1, four decimals below."""
    return round(price, 2 if price >= 1 else 4)


def _json(resp) -> object:
    if resp.status_code >= 400:
        raise BrokerError(f"Schwab {resp.status_code}: {_error_text(resp)}")
    return resp.json()


def _error_text(resp) -> str:
    try:
        body = resp.json()
        return str(body.get("message") or body.get("errors") or body)[:300]
    except Exception:
        return (resp.text or "")[:300]


def _ts(value) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000, timezone.utc)
    try:
        return pd.Timestamp(value).to_pydatetime()
    except Exception:
        return None


class BrokerError(RuntimeError):
    pass


# --------------------------------------------------------------------------- order JSON

def order_spec(req: OrderRequest) -> dict:
    """Schwab order JSON for a request. An entry with a stop and/or target becomes a bracket:
    the entry TRIGGERs a one-cancels-other pair of good-till-cancel exits."""
    s = _schwab()
    common, eq, opt = s.orders.common, s.orders.equities, s.orders.options
    gtc = common.Duration.GOOD_TILL_CANCEL
    qty, sym = req.quantity, req.symbol
    is_opt = req.asset_type == "OPTION"
    limit = None if req.limit_price is None else tick_round(req.limit_price)

    if req.is_entry:
        if limit is None:
            entry = opt.option_buy_to_open_market(sym, qty) if is_opt else eq.equity_buy_market(sym, qty)
        else:
            entry = opt.option_buy_to_open_limit(sym, qty, limit) if is_opt else eq.equity_buy_limit(sym, qty, limit)
    else:
        if limit is None:
            return (opt.option_sell_to_close_market(sym, qty) if is_opt else eq.equity_sell_market(sym, qty)).build()
        return (opt.option_sell_to_close_limit(sym, qty, limit) if is_opt else eq.equity_sell_limit(sym, qty, limit)).build()

    exits = []
    if req.target_price is not None:
        px = tick_round(req.target_price)
        exits.append((opt.option_sell_to_close_limit(sym, qty, px) if is_opt
                      else eq.equity_sell_limit(sym, qty, px)).set_duration(gtc))
    if req.stop_price is not None:
        base = opt.option_sell_to_close_market(sym, qty) if is_opt else eq.equity_sell_market(sym, qty)
        exits.append(base.set_order_type(common.OrderType.STOP)
                     .set_stop_price(tick_round(req.stop_price)).set_duration(gtc))
    if not exits:
        return entry.build()
    child = exits[0] if len(exits) == 1 else common.one_cancels_other(*exits)
    return common.first_triggers_second(entry, child).build()


def option_symbol(underlying: str, expiry: date, kind: str, strike: float) -> str:
    """Schwab option symbol, e.g. ``ACME  261120C00045000``."""
    return _schwab().orders.options.OptionSymbol(underlying, expiry, kind, f"{strike:g}").build()


# --------------------------------------------------------------------------- response parsing

def parse_accounts(numbers: list[dict], accounts: list[dict]) -> list[Account]:
    hashes = {str(n.get("accountNumber")): n.get("hashValue") for n in numbers}
    out = []
    for a in accounts:
        sa = a.get("securitiesAccount", a)
        num = str(sa.get("accountNumber", ""))
        bal = sa.get("currentBalances", {}) or {}
        positions = [Position(
            symbol=(p.get("instrument") or {}).get("symbol", ""),
            asset_type=(p.get("instrument") or {}).get("assetType", ""),
            quantity=(p.get("longQuantity") or 0) - (p.get("shortQuantity") or 0),
            avg_price=p.get("averagePrice"), market_value=p.get("marketValue"),
            day_pl=p.get("currentDayProfitLoss"),
        ) for p in sa.get("positions", []) or []]
        day_pl = sum(p.day_pl for p in positions if p.day_pl is not None) if positions else 0.0
        out.append(Account(
            number_masked=mask(num), account_hash=hashes.get(num, ""),
            equity=bal.get("liquidationValue", bal.get("equity")),
            cash=bal.get("cashBalance", bal.get("cashAvailableForTrading")),
            buying_power=bal.get("buyingPower", bal.get("cashAvailableForTrading")),
            day_pl=day_pl, positions=positions))
    return out


def parse_quotes(data: dict) -> dict[str, Quote]:
    out = {}
    for sym, item in (data or {}).items():
        q = item.get("quote", {}) or {}
        out[sym] = Quote(symbol=sym, bid=q.get("bidPrice"), ask=q.get("askPrice"),
                         last=q.get("lastPrice", q.get("mark")), change_pct=q.get("netPercentChange"),
                         volume=q.get("totalVolume"), time=_ts(q.get("quoteTime")))
    return out


def parse_chain(data: dict) -> pd.DataFrame:
    rows = []
    for side in ("callExpDateMap", "putExpDateMap"):
        for exp_key, strikes in (data.get(side) or {}).items():
            for contracts in strikes.values():
                for c in contracts:
                    rows.append({
                        "symbol": c.get("symbol"), "underlying": data.get("symbol"),
                        "type": "C" if c.get("putCall") == "CALL" else "P",
                        "expiry": pd.Timestamp(exp_key.split(":")[0]),
                        "dte": c.get("daysToExpiration", int(exp_key.split(":")[1]) if ":" in exp_key else None),
                        "strike": c.get("strikePrice"), "bid": c.get("bid"), "ask": c.get("ask"),
                        "mark": c.get("mark"), "delta": c.get("delta"),
                        "iv": (c.get("volatility") or 0) / 100 or None,     # Schwab sends percent
                        "open_interest": c.get("openInterest"), "volume": c.get("totalVolume"),
                    })
    return pd.DataFrame(rows, columns=["symbol", "underlying", "type", "expiry", "dte", "strike", "bid",
                                       "ask", "mark", "delta", "iv", "open_interest", "volume"])


def parse_candles(data: dict) -> pd.DataFrame:
    c = pd.DataFrame(data.get("candles") or [], columns=["datetime", "open", "high", "low", "close", "volume"])
    idx = pd.to_datetime(c["datetime"], unit="ms", utc=True).dt.tz_convert("America/New_York")
    c.index = pd.DatetimeIndex(idx.dt.tz_localize(None).dt.normalize(), name="date")
    return c[["open", "high", "low", "close", "volume"]].astype(float)


def parse_orders(data: list[dict]) -> list[OrderStatus]:
    out = []
    for o in data or []:
        leg = (o.get("orderLegCollection") or [{}])[0]
        out.append(OrderStatus(
            order_id=str(o.get("orderId", "")), symbol=(leg.get("instrument") or {}).get("symbol", ""),
            status=o.get("status", ""), side=leg.get("instruction", ""),
            quantity=o.get("quantity", 0), filled=o.get("filledQuantity", 0),
            price=o.get("price", o.get("stopPrice")), entered=_ts(o.get("enteredTime"))))
    return out


def parse_transactions(data: list[dict]) -> pd.DataFrame:
    rows = []
    for t in data or []:
        items = [i for i in t.get("transferItems") or [] if (i.get("instrument") or {}).get("assetType") != "CURRENCY"]
        item = items[0] if items else {}
        rows.append({"time": _ts(t.get("time")), "type": t.get("type"), "description": t.get("description"),
                     "symbol": (item.get("instrument") or {}).get("symbol"), "quantity": item.get("amount"),
                     "price": item.get("price"), "net_amount": t.get("netAmount")})
    return pd.DataFrame(rows, columns=["time", "type", "description", "symbol", "quantity", "price", "net_amount"])


def parse_preview(req: OrderRequest, data: dict) -> OrderPreview:
    v = data.get("orderValidationResult") or {}
    rejects = [r.get("message") or r.get("validationRuleName", "") for r in v.get("rejects") or []]
    warns = [w.get("message") or w.get("validationRuleName", "")
             for key in ("warns", "reviews", "alerts") for w in v.get(key) or []]
    strategy = data.get("orderStrategy") or {}
    balance = strategy.get("orderBalance") or {}
    fees = (data.get("commissionAndFee") or {}).get("commission") or {}
    commission = None
    try:
        commission = sum(float(v.get("value", 0)) for leg in fees.get("commissionLegs", [])
                         for v in leg.get("commissionValues", []))
    except Exception:
        pass
    return OrderPreview(request=req, fingerprint=req.fingerprint(), accepted=not rejects,
                        messages=[f"REJECT: {m}" for m in rejects] + [f"WARN: {m}" for m in warns],
                        est_cost=balance.get("orderValue", req.cost()), est_commission=commission,
                        created_at=datetime.now(timezone.utc), raw=data)


# --------------------------------------------------------------------------- the broker

class SchwabBroker(BrokerClient):
    name = "schwab"
    is_live = True

    def __init__(self, client=None, auth: SchwabAuth | None = None):
        self.auth = auth or SchwabAuth()
        self._client = client

    @property
    def client(self):
        if self._client is None:
            self._client = self.auth.client()
        return self._client

    def accounts(self) -> list[Account]:
        c = self.client
        numbers = _json(c.get_account_numbers())
        accounts = _json(c.get_accounts(fields=[c.Account.Fields.POSITIONS]))
        return parse_accounts(numbers, accounts)

    def quotes(self, symbols: list[str]) -> dict[str, Quote]:
        return parse_quotes(_json(self.client.get_quotes(symbols)))

    def price_history(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        data = _json(self.client.get_price_history_every_day(
            symbol, start_datetime=datetime.combine(start, datetime.min.time()),
            end_datetime=datetime.combine(end, datetime.min.time())))
        return parse_candles(data)

    def option_chain(self, symbol: str, from_date: date, to_date: date,
                     contract_type: str = "ALL") -> pd.DataFrame:
        c = self.client
        kind = getattr(c.Options.ContractType, contract_type)
        return parse_chain(_json(c.get_option_chain(symbol, contract_type=kind,
                                                    from_date=from_date, to_date=to_date)))

    def orders(self, account_hash: str, since: datetime, until: datetime | None = None) -> list[OrderStatus]:
        until = until or datetime.now(timezone.utc)
        return parse_orders(_json(self.client.get_orders_for_account(
            account_hash, from_entered_datetime=since, to_entered_datetime=until)))

    def transactions(self, account_hash: str, start: date, end: date) -> pd.DataFrame:
        return parse_transactions(_json(self.client.get_transactions(
            account_hash, start_date=datetime.combine(start, datetime.min.time()),
            end_date=datetime.combine(end, datetime.max.time()))))

    def preview(self, account_hash: str, request: OrderRequest) -> OrderPreview:
        return parse_preview(request, _json(self.client.preview_order(account_hash, order_spec(request))))

    def place(self, account_hash: str, request: OrderRequest) -> str:
        resp = self.client.place_order(account_hash, order_spec(request))
        if resp.status_code >= 400:
            raise BrokerError(f"Schwab rejected the order ({resp.status_code}): {_error_text(resp)}")
        location = resp.headers.get("Location", "")
        return location.rstrip("/").rsplit("/", 1)[-1] if location else ""

    def cancel(self, account_hash: str, order_id: str) -> None:
        resp = self.client.cancel_order(order_id, account_hash)
        if resp.status_code >= 400:
            raise BrokerError(f"Schwab could not cancel {order_id} ({resp.status_code}): {_error_text(resp)}")

    def diagnose(self) -> dict:
        """Raw read-only responses (for checking the parsers), with account numbers masked."""
        c = self.client
        numbers = _json(c.get_account_numbers())
        out = {"account_numbers": [{"accountNumber": mask(n.get("accountNumber", "")), "hashValue": "…"}
                                   for n in numbers],
               "quotes": _json(c.get_quotes(["SPY"])),
               "chain": _json(c.get_option_chain("SPY", strike_count=2,
                                                 from_date=date.today() + timedelta(days=25),
                                                 to_date=date.today() + timedelta(days=35)))}
        if numbers:
            h = numbers[0]["hashValue"]
            acct = _json(c.get_account(h, fields=[c.Account.Fields.POSITIONS]))
            acct.get("securitiesAccount", {})["accountNumber"] = "…masked"
            out["account"] = acct
            out["orders"] = _json(c.get_orders_for_account(
                h, from_entered_datetime=datetime.now(timezone.utc) - timedelta(days=30),
                to_entered_datetime=datetime.now(timezone.utc)))
        return out


def hours_until_relogin(auth: SchwabAuth) -> float | None:
    """Hours until a new login is needed (None: not logged in)."""
    exp = auth.token_expires()
    return None if exp is None else (exp - datetime.now(timezone.utc)).total_seconds() / 3600

