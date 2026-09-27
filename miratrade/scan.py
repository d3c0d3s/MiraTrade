"""Recent events and their historical evidence: the Señales screen and ``miratrade scan``.

A scan fetches the last few days of new insider buys (Form 4), 13D / 13G filings and, when a
flow directory is given, unusual option prints; builds the same panel as the analysis; and keeps
the bars where an event fired. Each event then gets its *evidence*: what happened to similar
events in the latest report's ``events.csv`` under one outcome profile, plus any validated
profile rule it matches. Nothing here predicts; it only looks up the past.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Mapping

import numpy as np
import pandas as pd

from miratrade.backtest import build_panel, conditions, entry_trigger
from miratrade.config import Config
from miratrade.outcomes import EVENT_TYPES

EVENT_LABELS = {"event:insider_buy": "Directivos", "event:flow": "Opciones", "event:13dg": "13D / 13G"}
# The finer conditions used to narrow "similar events", per event type, most specific last.
KEY_FLAGS = {"event:insider_buy": ("ins:exec_buy", "ins:big_250k+", "ins:cluster2+"),
             "event:flow": ("flow:bull_1m+",),
             "event:13dg": ("own:13g_active", "own:13d")}
CONDITION_LABELS = {"ins:exec_buy": "compra un directivo ejecutivo", "ins:big_250k+": "250 000 $ o más",
                    "ins:cluster2+": "2 o más directivos", "flow:bull_1m+": "1 M$ o más en primas alcistas",
                    "own:13g_active": "13G de un fondo no indexado", "own:13d": "13D (intención activa)"}
MIN_SIMILAR = 30
DEFAULT_VARIANT = "call45_40"


# --------------------------------------------------------------------------- profiles

def variant_label(v: str, cfg: Config = Config()) -> str:
    """``call45_40`` → "Call 45 días · +40 % / −25 %"."""
    kind, pct = v.split("_")
    stops = {int(round(t * 100)): int(round(s * 100)) for t, s in cfg.outcomes.targets}
    what = f"Acción {kind[5:-1]} meses" if kind.startswith("stock") else f"Call {kind[4:]} días"
    return f"{what} · +{pct} % / −{stops.get(int(pct), '?')} %"


# --------------------------------------------------------------------------- events

def recent_events(panel: Mapping[str, pd.DataFrame], since: pd.Timestamp) -> pd.DataFrame:
    """The latest bar on or after ``since`` where an event fired, one row per ticker."""
    rows = []
    for t, ind in panel.items():
        fired = np.flatnonzero(entry_trigger(ind).to_numpy())
        fired = [s for s in fired if ind.index[s] >= since]
        if not fired:
            continue
        s = fired[-1]
        row = ind.iloc[s]
        rows.append({"ticker": t, "signal_date": ind.index[s], "close": float(row["close"]),
                     "events_in_window": len(fired), **conditions(row)})
    if not rows:
        return pd.DataFrame(columns=["ticker", "signal_date", "close", "events_in_window", *EVENT_TYPES])
    return pd.DataFrame(rows).sort_values(["signal_date", "ticker"], ascending=[False, True]).reset_index(drop=True)


def describe(ev: Mapping, insiders: pd.DataFrame | None, ownership: pd.DataFrame | None,
             since: pd.Timestamp, min_value: float = 25_000) -> str:
    """One plain sentence about what was filed (who bought, how much; who crossed 5 %)."""
    parts = []
    t = ev["ticker"]
    if ev.get("event:insider_buy") and insiders is not None and len(insiders):
        b = insiders[(insiders["ticker"] == t) & (insiders["code"] == "P") & (insiders["value"] >= min_value)
                     & (pd.to_datetime(insiders["filing_date"]) >= since)]
        if len(b):
            n = b["owner_cik"].nunique()
            who = "1 directivo compró" if n == 1 else f"{n} directivos compraron"
            parts.append(f"{who} {_money(b['value'].sum())}")
    if ev.get("event:13dg") and ownership is not None and len(ownership):
        o = ownership[(ownership["ticker"] == t) & (pd.to_datetime(ownership["filing_date"]) >= since)
                      & ~ownership["passive"].astype(bool)]
        if len(o):
            r = o.sort_values("filing_date").iloc[-1]
            parts.append(f"{str(r['filer']).title()} presentó un {r['kind']}{' (modificación)' if r['amendment'] else ''}")
    if ev.get("event:flow"):
        parts.append("opciones con volumen inusual")
    return "; ".join(parts) or "evento nuevo"


def _money(v: float) -> str:
    if v >= 1e6:
        return f"{v / 1e6:,.1f} M$".replace(".", ",")
    return f"{v / 1e3:,.0f} k$".replace(",", ".")


# --------------------------------------------------------------------------- evidence

@dataclass
class Evidence:
    variant: str
    n: int = 0
    target: float = float("nan")        # share of similar events that reached the target first
    stop: float = float("nan")          # … that hit the stop first
    neither: float = float("nan")       # … that reached neither by the horizon
    mean_return: float = float("nan")
    similar_to: list[str] = field(default_factory=list)   # the conditions used to narrow the match
    rules: list[str] = field(default_factory=list)        # validated profile rules the event meets

    @property
    def sentence(self) -> str:
        if self.n == 0:
            return "Sin eventos parecidos en el último reporte."
        pct = lambda x: f"{x * 100:.0f} %"  # noqa: E731
        mean = f"{self.mean_return * 100:+.0f}".replace("-", "−")
        n = f"{self.n:,}".replace(",", ".")
        return (f"{n} eventos parecidos: {pct(self.target)} llegó antes al objetivo, "
                f"{pct(self.stop)} al stop y {pct(self.neither)} a ninguno. Resultado medio {mean} %.")


def _true(ev: Mapping, key: str) -> bool:
    v = ev.get(key, False)
    return bool(v) and not (isinstance(v, float) and np.isnan(v))


def evidence(ev: Mapping, history: pd.DataFrame, variant: str = DEFAULT_VARIANT,
             rules: pd.DataFrame | None = None, min_n: int = MIN_SIMILAR) -> Evidence:
    """Past events of the same type(s), narrowed by the event's key conditions while at least
    ``min_n`` remain, measured under ``variant``."""
    out = Evidence(variant)
    res = f"res_{variant}"
    if history is None or history.empty or res not in history:
        return out
    kinds = [k for k in EVENT_TYPES if _true(ev, k) and k in history]
    if not kinds:
        return out
    h = history.dropna(subset=[res])
    sim = h[h[kinds].astype(bool).any(axis=1)]
    for k in kinds:
        for f in KEY_FLAGS.get(k, ()):
            if _true(ev, f) and f in sim:
                narrower = sim[sim[f].astype(bool)]
                if len(narrower) >= min_n:
                    sim = narrower
                    out.similar_to.append(f)
    out.n = len(sim)
    if out.n:
        r = sim[res]
        out.target, out.stop, out.neither = float((r == 1).mean()), float((r == -1).mean()), float((r == 0).mean())
        out.mean_return = float(sim[f"ret_{variant}"].mean())
    out.rules = matching_rules(ev, rules, variant)
    return out


def matching_rules(ev: Mapping, rules: pd.DataFrame | None, variant: str) -> list[str]:
    """Validated rules for ``variant`` (confirmed by walk-forward when that column exists) whose
    every condition holds for the event."""
    if rules is None or rules.empty or "rule" not in rules:
        return []
    r = rules
    if "variant" in r:
        r = r[r["variant"] == variant]
    ok = r["validated"].astype(bool) if "validated" in r else pd.Series(False, index=r.index)
    if "wf_confirmed" in r:
        ok &= r["wf_confirmed"].astype(bool)
    return [rule for rule in r.loc[ok, "rule"] if all(_true(ev, c.strip()) for c in str(rule).split("&"))]


def contract_for(prices: pd.DataFrame, signal_date, variant: str = DEFAULT_VARIANT,
                 cfg: Config = Config()) -> dict | None:
    """The call the chosen profile would buy for this event: strike, expiry, premium and greeks.

    **Modelled** with Black-Scholes on the stock's realised volatility, the same way the analysis
    priced it, not a quote. ``None`` for the share profiles or when there is too little history."""
    from dataclasses import replace

    from miratrade.options_trades import bs_greeks, option_contract, realized_vol

    if not variant.startswith("call") or prices is None or prices.empty:
        return None
    dte = int(variant[4:].split("_")[0])
    target = int(variant.split("_")[1]) / 100
    stop = dict(cfg.outcomes.targets).get(target, 0.25)
    history = prices.loc[:pd.Timestamp(signal_date)]
    if len(history) < 30:
        return None
    vol = float(realized_vol(history["close"]).iloc[-1])
    spot = float(history["close"].iloc[-1])
    if not np.isfinite(vol) or vol <= 0 or spot <= 0:
        return None
    params = replace(cfg.options, target_dte=dte, min_dte=dte)
    c = option_contract(spot, history.index[-1].date(), vol, params)
    if not np.isfinite(c["ask"]) or c["ask"] <= 0:
        return None
    greeks = bs_greeks(spot, c["strike"], c["t"], params.rate, c["sigma"])
    return {"ticker": None, "strike": c["strike"], "expiry": pd.Timestamp(c["expiry"]),
            "dte": (c["expiry"] - history.index[-1].date()).days, "spot": spot,
            "premium": c["ask"], "cost": c["ask"] * 100, "iv": c["sigma"],
            "in_the_money": spot / c["strike"] - 1, "target": c["ask"] * (1 + target),
            "stop": c["ask"] * (1 - stop), "target_pct": target, "stop_pct": stop, **greeks}


def latest_history_report(root: Path) -> Path | None:
    """Newest report folder under ``root`` (two levels deep) that has an ``events.csv``."""
    root = Path(root)
    found = [p.parent for pat in ("events.csv", "*/events.csv", "*/*/events.csv") for p in root.glob(pat)]
    return max(found, key=lambda p: (p / "events.csv").stat().st_mtime) if found else None


def load_history(report_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """``events.csv`` and ``profile_rules.csv`` of a report (empty frames when missing)."""
    def read(name: str) -> pd.DataFrame:
        p = Path(report_dir) / name
        try:
            return pd.read_csv(p) if p.exists() and p.stat().st_size > 1 else pd.DataFrame()
        except pd.errors.EmptyDataError:
            return pd.DataFrame()
    return read("events.csv"), read("profile_rules.csv")


# --------------------------------------------------------------------------- orchestration

def run_scan(days: int = 7, end: date | None = None, cfg: Config = Config(), flow_dir: Path | None = None,
             smart_money: bool = True, log: Callable[[str], None] = print, fetch=None,
             cap_tier: str | None = None) -> dict:
    """Fetch the last ``days`` of events and return ``{"events", "prices", "since", "end"}``.

    ``fetch`` overrides the downloads for tests: ``{"insiders": fn(start, end), "ownership":
    fn(start, end, insiders), "prices": fn(tickers, start, end)}`` and optionally ``"flow": fn()``."""
    end = end or date.today()
    since = end - timedelta(days=days)
    look = max(cfg.insider.lookback_days, cfg.smart.lookback_days)
    if fetch is None:
        # Check the price source FIRST: the SEC download below takes minutes, and finding out
        # afterwards that there are no prices wastes all of it.
        from miratrade.data.prices import FIX_HINT, PriceSourceError, source_ready

        ok, why = source_ready()
        if not ok:
            raise PriceSourceError(f"{why} {FIX_HINT}")
        log(why)
        fetch = _default_fetchers(log)

    log(f"Compras de directivos (Form 4) {since} → {end} …")
    insiders = fetch["insiders"](since - timedelta(days=look), end)
    new_buys = insiders[(insiders["code"] == "P") & (insiders["value"] >= cfg.insider.min_value_usd)
                        & (pd.to_datetime(insiders["filing_date"]).dt.date >= since)]
    tickers = set(new_buys["ticker"])
    ownership = None
    if smart_money:
        log(f"13D / 13G {since} → {end} …")
        ownership = fetch["ownership"](since - timedelta(days=look), end, insiders)
        fresh = ownership[(pd.to_datetime(ownership["filing_date"]).dt.date >= since) & ~ownership["amendment"].astype(bool)
                          & ~ownership["passive"].astype(bool)]
        tickers |= set(fresh["ticker"])
    flow = fetch["flow"]() if "flow" in fetch else _load_flow(flow_dir)
    if len(flow):
        from miratrade.signals.options_flow import unusual_prints
        u = unusual_prints(flow, cfg.flow)
        tickers |= set(u.loc[pd.to_datetime(u["date"]).dt.date >= since, "ticker"]) if "date" in u else set()
    # Shares outstanding come before prices: the size filter then cuts the list of companies
    # whose prices have to be downloaded, which is the slow part.
    shares = fetch["shares"](sorted(tickers), insiders, ownership) if "shares" in fetch else None
    tier = cap_tier or cfg.data.cap_tier
    if tier != "all":
        from miratrade.data.fundamentals import cap_from_filings, filter_by_tier, tier_report

        tickers, stats = filter_by_tier(tickers, cap_from_filings(insiders, shares), tier)
        log("  " + tier_report(stats, tier))
    log(f"Precios de {len(tickers)} empresas …")
    # 400 extra days: 200-day averages at the window start plus a year of chart.
    prices = fetch["prices"](sorted(tickers | {"SPY"}), since - timedelta(days=400), end + timedelta(days=1))
    panel = build_panel(prices, insiders, flow, cfg, ownership=ownership, shares=shares)
    events = recent_events({t: p for t, p in panel.items() if t != "SPY"}, pd.Timestamp(since))
    if len(events):
        events["what"] = [describe(e, insiders, ownership, pd.Timestamp(since), cfg.insider.min_value_usd)
                          for e in events.to_dict("records")]
    log(f"{len(events)} eventos nuevos.")
    return {"events": events, "prices": {t: prices[t] for t in events["ticker"] if t in prices},
            "since": since, "end": end}


def _load_flow(flow_dir: Path | None) -> pd.DataFrame:
    from miratrade.data.options import FLOW_COLUMNS, load_flow_csv

    if flow_dir and Path(flow_dir).exists() and any(Path(flow_dir).glob("*.csv")):
        return load_flow_csv(flow_dir)
    return pd.DataFrame(columns=FLOW_COLUMNS)


def _default_fetchers(log: Callable[[str], None]) -> dict:
    from miratrade.data.ownership import cik_ticker_map, fetch_ownership
    from miratrade.data.prices import load_prices
    from miratrade.data.sec import SecClient, clean_insiders, fetch_insiders

    client = SecClient()

    def insiders(start, end):
        df, _ = clean_insiders(fetch_insiders(start, end, client))
        return df

    def ownership(start, end, ins):
        df, stats = fetch_ownership(start, end, cik_ticker_map(client, ins), client,
                                    passive_filers=Config().smart.passive_filers)
        log(f"  {stats['resolved']} de {stats['filings']} filings con ticker")
        return df

    def shares(tickers, ins, own):
        from miratrade.data.fundamentals import fetch_shares, ticker_ciks

        tj = json.loads(client.get("https://www.sec.gov/files/company_tickers.json", max_age_days=7))
        log(f"Acciones en circulación (SEC XBRL) de {len(tickers)} empresas …")
        return fetch_shares(tickers, ticker_ciks(ins, tj, own), client, log)

    return {"insiders": insiders, "ownership": ownership, "prices": load_prices, "shares": shares}


# --------------------------------------------------------------------------- saved scans

def save_scan(result: dict, folder: Path) -> Path:
    """Keep the last scan so the app shows it on the next start (prices stay in the price cache)."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    result["events"].to_csv(folder / "events.csv", index=False)
    for t, df in result["prices"].items():
        df.to_csv(folder / f"prices_{t}.csv")
    (folder / "meta.txt").write_text(f"{result['since']}\n{result['end']}\n", encoding="utf-8")
    return folder


def load_scan(folder: Path) -> dict | None:
    folder = Path(folder)
    if not (folder / "events.csv").exists():
        return None
    try:
        events = pd.read_csv(folder / "events.csv", parse_dates=["signal_date"])
    except pd.errors.EmptyDataError:
        events = pd.DataFrame()
    prices = {p.stem[7:]: pd.read_csv(p, index_col=0, parse_dates=True) for p in folder.glob("prices_*.csv")}
    lines = (folder / "meta.txt").read_text(encoding="utf-8").split() if (folder / "meta.txt").exists() else []
    return {"events": events, "prices": prices,
            "since": date.fromisoformat(lines[0]) if lines else None,
            "end": date.fromisoformat(lines[1]) if len(lines) > 1 else None}
