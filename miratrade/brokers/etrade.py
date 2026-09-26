"""E*TRADE API (the user's own consumer key) behind ``BrokerClient``: accounts, quotes and
option chains. Read-only: MiraTrade sends orders only through Schwab and ``OrderGuard``.

Terms: an individual consumer key is for the key holder's own E*TRADE accounts (E*TRADE's
"Non-Commercial Use"); real-time quotes need the market data agreement signed in the account,
otherwise E*TRADE answers with delayed quotes (each quote says which). The API has **no price
history**: daily bars come from Schwab.

Login is OAuth 1.0a: MiraTrade asks for a request token, the user signs in at E*TRADE and copies
the verification code it shows, and MiraTrade exchanges it for an access token. The token dies
at midnight US Eastern and after two hours without use (then it is renewed automatically).
Secrets live in the Windows Credential Manager.
"""
from __future__ import annotations

import time
from datetime import date, datetime, timezone
from urllib.parse import parse_qs

import pandas as pd

from miratrade.brokers.base import Account, BrokerClient, OrderPreview, OrderRequest, OrderStatus, Position, Quote
from miratrade.brokers.credentials import CredentialStore

KEY, SECRET, ENV, TOKEN = "etrade.consumer_key", "etrade.consumer_secret", "etrade.env", "etrade.token"
OAUTH = "https://api.etrade.com/oauth"
AUTHORIZE_URL = "https://us.etrade.com/e/t/etws/authorize?key={key}&token={token}"
API_BASE = {"prod": "https://api.etrade.com", "sandbox": "https://apisb.etrade.com"}
IDLE_RENEW_S = 90 * 60                  # E*TRADE deactivates a token after 2 h idle: renew before that
PACE_S = 0.3


class BrokerError(RuntimeError):
    pass


def mask(account_id: str) -> str:
    return "…" + str(account_id)[-4:]


def _session(key: str, secret: str, token: str | None = None, token_secret: str | None = None,
             verifier: str | None = None, callback: str | None = None):
    from requests_oauthlib import OAuth1Session

    return OAuth1Session(key, client_secret=secret, resource_owner_key=token, resource_owner_secret=token_secret,
                         verifier=verifier, callback_uri=callback, signature_type="AUTH_HEADER")


def _token_from(resp) -> dict:
    if resp.status_code >= 400:
        raise BrokerError(f"E*TRADE answered {resp.status_code}: {resp.text[:200]}")
    q = parse_qs(resp.text)
    if "oauth_token" not in q:
        raise BrokerError("E*TRADE did not return a token.")
    return {"token": q["oauth_token"][0], "secret": q["oauth_token_secret"][0]}


def next_midnight_et(ts: float) -> datetime:
    """When a token created at ``ts`` (epoch seconds) expires: the next midnight US Eastern."""
    et = pd.Timestamp(ts, unit="s", tz="UTC").tz_convert("America/New_York")
    return (et.normalize() + pd.Timedelta(days=1)).tz_convert("UTC").to_pydatetime()


# --------------------------------------------------------------------------- authentication

class EtradeAuth:
    def __init__(self, store: CredentialStore | None = None, session_factory=_session):
        self.store = store or CredentialStore()
        self._session_factory = session_factory
        self._request: dict | None = None

    def configured(self) -> bool:
        return bool(self.store.get(KEY) and self.store.get(SECRET))

    @property
    def env(self) -> str:
        return self.store.get(ENV) or "prod"

    def setup(self, consumer_key: str, consumer_secret: str, sandbox: bool = False) -> None:
        if not consumer_key.strip() or not consumer_secret.strip():
            raise ValueError("Consumer key and secret are both needed (E*TRADE → developer → your keys).")
        self.store.set(KEY, consumer_key.strip())
        self.store.set(SECRET, consumer_secret.strip())
        self.store.set(ENV, "sandbox" if sandbox else "prod")
        self.store.delete(TOKEN)

    def login_url(self) -> str:
        """Step 1: the E*TRADE page where the user signs in and gets a verification code."""
        s = self._session_factory(self.store.get(KEY), self.store.get(SECRET), callback="oob")
        self._request = _token_from(s.get(f"{OAUTH}/request_token"))
        return AUTHORIZE_URL.format(key=self.store.get(KEY), token=self._request["token"])

    def complete_login(self, verifier: str) -> None:
        """Step 2: the code E*TRADE showed after signing in."""
        if self._request is None:
            raise RuntimeError("Call login_url() first, in the same session.")
        code = verifier.strip()
        if not code:
            raise ValueError("Paste the verification code E*TRADE showed.")
        s = self._session_factory(self.store.get(KEY), self.store.get(SECRET), self._request["token"],
                                  self._request["secret"], verifier=code)
        tok = _token_from(s.get(f"{OAUTH}/access_token"))
        now = time.time()
        self.store.set_json(TOKEN, {**tok, "created": now, "used": now})
        self._request = None

    def expires(self) -> datetime | None:
        tok = self.store.get_json(TOKEN)
        return None if not tok else next_midnight_et(tok["created"])

    def hours_left(self) -> float | None:
        exp = self.expires()
        return None if exp is None else (exp - datetime.now(timezone.utc)).total_seconds() / 3600

    def session(self):
        """An API session; renews the token first if it has been idle too long."""
        tok = self.store.get_json(TOKEN)
        if not tok:
            raise BrokerError("Not logged in to E*TRADE: run `miratrade etrade login`.")
        if (self.hours_left() or 0) <= 0:
            raise BrokerError("The E*TRADE login expired at midnight (US Eastern): log in again.")
        s = self._session_factory(self.store.get(KEY), self.store.get(SECRET), tok["token"], tok["secret"])
        if time.time() - tok.get("used", 0) > IDLE_RENEW_S:
            r = s.get(f"{OAUTH}/renew_access_token")
            if r.status_code >= 400:
                raise BrokerError("E*TRADE could not renew the login (idle more than two hours?): log in again.")
        tok["used"] = time.time()
        self.store.set_json(TOKEN, tok)
        return s

    def logout(self) -> None:
        tok = self.store.get_json(TOKEN)
        if tok:
            try:
                self._session_factory(self.store.get(KEY), self.store.get(SECRET), tok["token"],
                                      tok["secret"]).get(f"{OAUTH}/revoke_access_token")
            except Exception:                    # revoking is a courtesy; the token dies at midnight anyway
                pass
        self.store.delete(TOKEN)

    def forget(self) -> None:
        self.logout()
        for name in (KEY, SECRET, ENV):
            self.store.delete(name)


# --------------------------------------------------------------------------- parsers

def _list(x) -> list:
    return x if isinstance(x, list) else ([] if x is None else [x])


def parse_account_list(data: dict) -> list[dict]:
    accts = ((data or {}).get("AccountListResponse", {}).get("Accounts", {}) or {}).get("Account")
    return [a for a in _list(accts) if str(a.get("accountStatus", "ACTIVE")).upper() != "CLOSED"]


def parse_balance(data: dict) -> dict:
    b = (data or {}).get("BalanceResponse", {}) or {}
    comp = b.get("Computed", {}) or {}
    rt = comp.get("RealTimeValues", {}) or {}
    return {"equity": rt.get("totalAccountValue"), "cash": comp.get("cashBalance", comp.get("netCash")),
            "buying_power": comp.get("cashBuyingPower", comp.get("marginBuyingPower"))}


def parse_portfolio(data: dict) -> list[Position]:
    out = []
    for acct in _list(((data or {}).get("PortfolioResponse", {}) or {}).get("AccountPortfolio")):
        for p in _list(acct.get("Position")):
            prod = p.get("Product", {}) or {}
            out.append(Position(symbol=prod.get("symbol", p.get("symbolDescription", "")),
                                asset_type="OPTION" if prod.get("securityType") == "OPTN" else "EQUITY",
                                quantity=float(p.get("quantity", 0)) * (-1 if p.get("positionType") == "SHORT" else 1),
                                avg_price=p.get("pricePaid"), market_value=p.get("marketValue"),
                                day_pl=p.get("daysGain")))
    return out


def parse_quotes(data: dict) -> dict[str, Quote]:
    out = {}
    for q in _list(((data or {}).get("QuoteResponse", {}) or {}).get("QuoteData")):
        sym = (q.get("Product", q.get("product", {})) or {}).get("symbol")
        a = q.get("All", {}) or {}
        ts = q.get("dateTimeUTC")
        out[sym] = Quote(symbol=sym, bid=a.get("bid"), ask=a.get("ask"), last=a.get("lastTrade"),
                         change_pct=a.get("changeClosePercentage"), volume=a.get("totalVolume"),
                         time=datetime.fromtimestamp(ts, timezone.utc) if ts else None)
    return out


def quote_status(data: dict) -> set[str]:
    """``REALTIME`` / ``DELAYED`` per quote: delayed means the market data agreement is not signed."""
    return {q.get("quoteStatus", "") for q in _list(((data or {}).get("QuoteResponse", {}) or {}).get("QuoteData"))}


def parse_expiries(data: dict) -> list[date]:
    rows = _list(((data or {}).get("OptionExpireDateResponse", {}) or {}).get("ExpirationDate"))
    return sorted(date(int(r["year"]), int(r["month"]), int(r["day"])) for r in rows if r.get("year"))


CHAIN_COLUMNS = ["symbol", "underlying", "type", "expiry", "dte", "strike", "bid", "ask", "mark", "delta", "iv",
                 "open_interest", "volume"]


def parse_chain(data: dict, underlying: str, expiry: date, today: date | None = None) -> pd.DataFrame:
    today = today or date.today()
    rows = []
    for pair in _list(((data or {}).get("OptionChainResponse", {}) or {}).get("OptionPair")):
        for side in ("Call", "Put"):
            c = pair.get(side)
            if not c:
                continue
            g = c.get("OptionGreeks", {}) or {}
            bid, ask = c.get("bid"), c.get("ask")
            rows.append({"symbol": c.get("osiKey", c.get("displaySymbol")), "underlying": underlying,
                         "type": "C" if side == "Call" else "P", "expiry": pd.Timestamp(expiry),
                         "dte": (expiry - today).days, "strike": c.get("strikePrice"), "bid": bid, "ask": ask,
                         "mark": (bid + ask) / 2 if bid is not None and ask is not None else c.get("lastPrice"),
                         "delta": g.get("delta"), "iv": g.get("iv"), "open_interest": c.get("openInterest"),
                         "volume": c.get("volume")})
    return pd.DataFrame(rows, columns=CHAIN_COLUMNS)


# --------------------------------------------------------------------------- the broker

class EtradeBroker(BrokerClient):
    name = "etrade"
    is_live = True

    def __init__(self, auth: EtradeAuth | None = None, session=None):
        self.auth = auth or EtradeAuth()
        self._session = session
        self._last = 0.0

    def _get(self, path: str, params: dict | None = None) -> dict:
        if self._session is None:
            self._session = self.auth.session()
        wait = PACE_S - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()
        r = self._session.get(API_BASE[self.auth.env] + path, params=params or {}, headers={"Accept": "application/json"})
        if r.status_code == 401:
            raise BrokerError("E*TRADE rejected the login (expired or revoked): log in again.")
        if r.status_code == 204:
            return {}
        if r.status_code >= 400:
            raise BrokerError(f"E*TRADE {path} answered {r.status_code}: {r.text[:200]}")
        return r.json()

    def accounts(self) -> list[Account]:
        out = []
        for a in parse_account_list(self._get("/v1/accounts/list.json")):
            key = a["accountIdKey"]
            bal = parse_balance(self._get(f"/v1/accounts/{key}/balance.json",
                                          {"instType": a.get("institutionType", "BROKERAGE"), "realTimeNAV": "true"}))
            pos = parse_portfolio(self._get(f"/v1/accounts/{key}/portfolio.json"))
            out.append(Account(number_masked=mask(a.get("accountId", "")), account_hash=key, equity=bal["equity"],
                               cash=bal["cash"], buying_power=bal["buying_power"], positions=pos))
        return out

    def quotes(self, symbols: list[str]) -> dict[str, Quote]:
        out = {}
        for i in range(0, len(symbols), 25):                     # E*TRADE: up to 25 symbols per call
            chunk = ",".join(s.upper() for s in symbols[i:i + 25])
            out.update(parse_quotes(self._get(f"/v1/market/quote/{chunk}.json", {"detailFlag": "ALL"})))
        return out

    def price_history(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        raise BrokerError("E*TRADE's API has no price history; daily bars come from Schwab.")

    def option_chain(self, symbol: str, from_date: date, to_date: date, contract_type: str = "ALL") -> pd.DataFrame:
        chain_type = {"ALL": "CALLPUT", "CALL": "CALL", "PUT": "PUT"}[contract_type]
        expiries = [d for d in parse_expiries(self._get("/v1/market/optionexpiredate.json",
                                                        {"symbol": symbol, "expiryType": "ALL"}))
                    if from_date <= d <= to_date]
        frames = [parse_chain(self._get("/v1/market/optionchains.json",
                                        {"symbol": symbol, "expiryYear": d.year, "expiryMonth": d.month,
                                         "expiryDay": d.day, "chainType": chain_type, "includeWeekly": "true",
                                         "priceType": "ALL"}), symbol, d) for d in expiries]
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=CHAIN_COLUMNS)

    # orders go through Schwab only (OrderGuard); E*TRADE stays read-only for now
    def _no_orders(self, *_a, **_k):
        raise BrokerError("MiraTrade sends orders only through Schwab; E*TRADE is connected read-only.")

    def orders(self, account_hash: str, since: datetime, until: datetime | None = None) -> list[OrderStatus]:
        return self._no_orders()

    def transactions(self, account_hash: str, start: date, end: date) -> pd.DataFrame:
        return self._no_orders()

    def preview(self, account_hash: str, request: OrderRequest) -> OrderPreview:
        return self._no_orders()

    def place(self, account_hash: str, request: OrderRequest) -> str:
        return self._no_orders()

    def cancel(self, account_hash: str, order_id: str) -> None:
        return self._no_orders()

    def diagnose(self) -> dict:
        """Raw read-only responses to check the parsers; account ids masked."""
        quotes = self._get("/v1/market/quote/SPY.json", {"detailFlag": "ALL"})
        accounts = self._get("/v1/accounts/list.json")
        for a in parse_account_list(accounts):
            a["accountId"] = mask(a.get("accountId", ""))
            a["accountIdKey"] = "…"
        return {"quotes": quotes, "quote_status": sorted(quote_status(quotes)),
                "expiries": self._get("/v1/market/optionexpiredate.json", {"symbol": "SPY", "expiryType": "ALL"}),
                "accounts": accounts}
