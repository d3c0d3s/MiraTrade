"""Options flow.

Free historical options *flow* does not exist, so there are two inputs:

* ``snapshot_cboe`` pulls CBOE's delayed end-of-day chain (volume, OI, prices). Run it daily
  (see ``miratrade snapshot``) to build your own history in ``.cache/flow/``.
* ``load_flow_csv`` imports an export from a flow vendor (Unusual Whales, Barchart,
  Cheddar Flow, etc.); column names are mapped through ``ALIASES``.

Both produce ``FLOW_COLUMNS``.
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Callable

import pandas as pd

from miratrade.config import CACHE_DIR

FLOW_COLUMNS = ["date", "ticker", "expiry", "type", "strike", "volume", "open_interest",
                "premium", "underlying", "bid", "ask", "side"]

ALIASES = {
    "date": ["date", "trade_date", "executed_at", "time", "datetime", "tradetime"],
    "ticker": ["ticker", "symbol", "underlying_symbol", "root", "sym"],
    "expiry": ["expiry", "expiration", "expiration_date", "exp", "expires", "expirationdate"],
    "type": ["type", "put_call", "option_type", "cp", "call_put", "right"],
    "strike": ["strike", "strike_price"],
    "volume": ["volume", "size", "qty", "contracts", "vol"],
    "open_interest": ["open_interest", "oi", "openinterest", "open_int"],
    "premium": ["premium", "total_premium", "prem", "value", "notional"],
    "underlying": ["underlying", "underlying_price", "stock_price", "spot", "underlyingprice"],
    "bid": ["bid", "bid_price", "bidprice"],
    "ask": ["ask", "ask_price", "askprice", "offer"],
    "side": ["side", "aggressor", "bid_ask", "sentiment_side", "trade_side"],
}

OCC_RE = re.compile(r"^(?P<root>[A-Z.]{1,6})(?P<ymd>\d{6})(?P<cp>[CP])(?P<strike>\d{8})$")


def parse_occ(symbol: str) -> tuple[str, date, str, float] | None:
    m = OCC_RE.match(symbol.replace(" ", ""))
    if not m:
        return None
    ymd = m["ymd"]
    expiry = date(2000 + int(ymd[:2]), int(ymd[2:4]), int(ymd[4:]))
    return m["root"], expiry, m["cp"], int(m["strike"]) / 1000


def _norm_side(s: pd.Series) -> pd.Series:
    s = s.astype(str).str.lower()
    out = pd.Series("unknown", index=s.index, dtype="object")
    out[s.str.contains("ask|buy|above")] = "ask"
    out[s.str.contains("bid|sell|below")] = "bid"
    return out


def normalise_flow(df: pd.DataFrame) -> pd.DataFrame:
    lower = {c.lower().strip().replace(" ", "_"): c for c in df.columns}
    out = pd.DataFrame(index=df.index)
    for col, names in ALIASES.items():
        src = next((lower[n] for n in names if n in lower), None)
        out[col] = df[src] if src is not None else pd.NA
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.tz_localize(None).dt.normalize()
    out["expiry"] = pd.to_datetime(out["expiry"], errors="coerce")
    out["ticker"] = out["ticker"].astype(str).str.upper().str.strip()
    out["type"] = out["type"].astype(str).str.upper().str[0].where(out["type"].notna())
    for col in ("strike", "volume", "open_interest", "premium", "underlying", "bid", "ask"):
        out[col] = pd.to_numeric(
            out[col].astype(str).str.replace(r"[$,]", "", regex=True), errors="coerce")
    out["side"] = _norm_side(out["side"])
    return out.dropna(subset=["date", "ticker", "type", "strike"])[FLOW_COLUMNS].reset_index(drop=True)


def load_flow_csv(path: Path | str) -> pd.DataFrame:
    path = Path(path)
    files = sorted(path.glob("*.csv")) if path.is_dir() else [path]
    if not files:
        return pd.DataFrame(columns=FLOW_COLUMNS)
    return pd.concat([normalise_flow(pd.read_csv(f)) for f in files], ignore_index=True)


def parse_cboe_chain(payload: dict, asof: date) -> pd.DataFrame:
    data = payload.get("data", payload)
    spot = data.get("current_price") or data.get("close")
    rows = []
    for opt in data.get("options", []):
        parsed = parse_occ(opt.get("option", ""))
        vol = opt.get("volume") or 0
        if not parsed or vol <= 0:
            continue
        root, expiry, cp, strike = parsed
        px = opt.get("last_trade_price") or ((opt.get("bid", 0) + opt.get("ask", 0)) / 2)
        rows.append({
            "date": pd.Timestamp(asof), "ticker": data.get("symbol", root).lstrip("_"),
            "expiry": pd.Timestamp(expiry), "type": cp, "strike": strike, "volume": vol,
            "open_interest": opt.get("open_interest", 0), "premium": vol * px * 100,
            "underlying": spot, "side": "unknown",
        })
    return pd.DataFrame(rows, columns=FLOW_COLUMNS)


def chain_to_flow(chain: pd.DataFrame, asof: date, underlying: float | None = None) -> pd.DataFrame:
    """A broker option chain (``BrokerClient.option_chain``) as one day of ``FLOW_COLUMNS``:
    volume, open interest and premium (volume × mid × 100) per contract. The aggressor side is not
    in a chain, so it stays unknown (the flow filter then treats the print as a buy)."""
    if chain is None or chain.empty:
        return pd.DataFrame(columns=FLOW_COLUMNS)
    c = chain[pd.to_numeric(chain["volume"], errors="coerce").fillna(0) > 0].copy()
    mid = c["mark"].where(c["mark"].notna(), (c["bid"] + c["ask"]) / 2)
    return pd.DataFrame({
        "date": pd.Timestamp(asof), "ticker": c["underlying"], "expiry": pd.to_datetime(c["expiry"]),
        "type": c["type"], "strike": c["strike"], "volume": c["volume"], "open_interest": c["open_interest"],
        "premium": c["volume"] * mid * 100, "underlying": underlying,
        # the quotes are kept, not only the mid they imply: the spread is what decides whether the
        # contract can be traded and how much of a target the round trip costs
        "bid": c["bid"], "ask": c["ask"], "side": "",
    }, columns=FLOW_COLUMNS).reset_index(drop=True)


def session_date(now=None) -> date:
    """The trading session a snapshot taken *now* belongs to, in New York time.

    A chain always shows the last session's figures, so labelling a snapshot with the calendar day it
    was taken puts Friday's trading under a Sunday date — a row for a day the market never opened,
    and Friday's volume counted twice if Friday evening was captured as well.

    Before the opening bell the session is still the previous one, because nothing has traded yet.
    """
    import pandas as pd

    from miratrade.scan import new_york_time

    here = new_york_time(pd.Timestamp(now) if now is not None else pd.Timestamp.now(tz="UTC"))
    started = here.weekday() < 5 and (here.hour, here.minute) >= (9, 30)
    return here.date() if started else pd.bdate_range(end=here.date() - pd.Timedelta(days=1),
                                                      periods=1)[0].date()


def snapshot_broker(tickers: list[str], broker, asof: date | None = None, days: int = 120,
                    db=None, log: Callable[[str], None] = print) -> pd.DataFrame:
    """Today's option chains from the user's own broker account, stored as one day of flow history.

    This is the only free source that has volume **and** open interest together, which is what the
    Vol > OI reading needs — the free historical feeds have volume alone. It only ever accumulates
    forward, so every day it does not run is a day that cannot be recovered later: run it once a day
    after the close.

    A ticker whose chain cannot be fetched is reported and skipped, never allowed to lose the rest.
    """
    from datetime import timedelta

    from miratrade import store

    asof = asof or session_date()
    owned, db = db is None, db if db is not None else store.connect()
    frames, failed = [], []
    try:
        spots = {}
        try:
            spots = {s: q.last for s, q in broker.quotes([t.upper() for t in tickers]).items()}
        except Exception as e:      # without spots the moneyness filter simply does not apply
            log(f"  no quotes ({e}); moneyness will be unknown")
        for t in tickers:
            t = t.upper()
            try:
                chain = broker.option_chain(t, asof + timedelta(days=1), asof + timedelta(days=days))
            except Exception as e:                  # one ticker failing must not lose the others
                failed.append(t)
                log(f"  {t}: no chain ({e})")
                continue
            rows = chain_to_flow(chain, asof, spots.get(t))
            if len(rows):
                frames.append(rows.assign(source=broker.name))
        df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=FLOW_COLUMNS)
        written = store.write(db, "option_flow", df)
        done = sorted({t.upper() for t in tickers} - set(failed))
        for t in done:                              # coverage per ticker: a resumable backfill
            store.mark_covered(db, f"flow_{broker.name}", [asof], rows=written, scope=t)
        log(f"  {broker.name} {asof}: {written} contracts over {len(done)} tickers"
            + (f", {len(failed)} without a chain" if failed else ""))
        return df
    finally:
        if owned:
            db.close()


def snapshot_cboe(tickers: list[str], asof: date | None = None, db=None) -> pd.DataFrame:
    """Fetch today's delayed chains from CBOE's public page. Personal research only: its terms do
    not allow commercial use, so it needs the "research" data source switched on in settings.

    Stored under its own ``source``, so these rows can be told apart from a broker's — they are
    delayed, and their licence is not the same.
    """
    import requests

    from miratrade.config import load_user_config
    from miratrade.data.prices import PriceSourceError

    if load_user_config().data.price_source != "research":
        raise PriceSourceError("The CBOE page is for personal research only. Use `miratrade snapshot` "
                               "with your broker, or choose the «Public websites» source under "
                               "Settings.")
    asof = asof or date.today()
    frames = []
    for t in tickers:
        sym = f"_{t}" if t in {"SPX", "VIX", "NDX", "RUT"} else t
        url = f"https://cdn.cboe.com/api/global/delayed_quotes/options/{sym}.json"
        try:
            resp = requests.get(url, timeout=30)
            if resp.ok:
                frames.append(parse_cboe_chain(json.loads(resp.text), asof))
        except Exception:
            continue
    from miratrade import store

    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=FLOW_COLUMNS)
    owned, db = db is None, db if db is not None else store.connect()
    try:
        store.write(db, "option_flow", df.assign(source="cboe") if len(df) else df)
    finally:
        if owned:
            db.close()
    return df
