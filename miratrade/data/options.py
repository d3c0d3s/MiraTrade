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

import pandas as pd

from miratrade.config import CACHE_DIR

FLOW_COLUMNS = ["date", "ticker", "expiry", "type", "strike", "volume", "open_interest",
                "premium", "underlying", "side"]

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
    for col in ("strike", "volume", "open_interest", "premium", "underlying"):
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
        "premium": c["volume"] * mid * 100, "underlying": underlying, "side": "",
    }, columns=FLOW_COLUMNS).reset_index(drop=True)


def snapshot_broker(tickers: list[str], broker, asof: date | None = None, days: int = 120,
                    out_dir: Path = CACHE_DIR / "flow") -> pd.DataFrame:
    """Today's option chains from the user's own broker account (Schwab or E*TRADE), saved as one
    day of flow history. Run it once a day after the close to build your own history."""
    from datetime import timedelta

    asof = asof or date.today()
    frames = []
    spots = {}
    try:
        spots = {s: q.last for s, q in broker.quotes([t.upper() for t in tickers]).items()}
    except Exception:
        pass
    for t in tickers:
        t = t.upper()
        try:
            chain = broker.option_chain(t, asof + timedelta(days=1), asof + timedelta(days=days))
        except Exception as e:                      # one ticker failing must not lose the others
            print(f"  {t}: sin cadena ({e})")
            continue
        frames.append(chain_to_flow(chain, asof, spots.get(t)))
    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=FLOW_COLUMNS)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_dir / f"{broker.name}_{asof:%Y%m%d}.csv", index=False)
    return df


def snapshot_cboe(tickers: list[str], asof: date | None = None,
                  out_dir: Path = CACHE_DIR / "flow") -> pd.DataFrame:
    """Fetch today's delayed chains from CBOE's public page. Personal research only: its terms do
    not allow commercial use, so it needs the "research" data source switched on in settings."""
    import requests

    from miratrade.config import load_user_config
    from miratrade.data.prices import PriceSourceError

    if load_user_config().data.price_source != "research":
        raise PriceSourceError("La página de CBOE es solo para investigación personal. Usa "
                               "`miratrade snapshot` con tu bróker, o elige la fuente «Webs públicas» en Configuración.")
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
    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=FLOW_COLUMNS)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_dir / f"cboe_{asof:%Y%m%d}.csv", index=False)
    return df
