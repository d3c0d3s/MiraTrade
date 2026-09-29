"""Recent events and their historical evidence: the Signals screen and ``miratrade scan``.

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
from miratrade.messages import note, sayer
from miratrade.outcomes import EVENT_TYPES

# Shown by the screens, which translate them.
EVENT_LABELS = {"event:insider_buy": "Insiders", "event:flow": "Options", "event:13dg": "13D / 13G"}
# The finer conditions used to narrow "similar events", per event type, most specific last.
KEY_FLAGS = {"event:insider_buy": ("ins:exec_buy", "ins:big_250k+", "ins:cluster2+"),
             "event:flow": ("flow:bull_1m+",),
             "event:13dg": ("own:13g_active", "own:13d")}
CONDITION_LABELS = {"ins:exec_buy": "an executive officer buys", "ins:big_250k+": "$250,000 or more",
                    "ins:cluster2+": "2 insiders or more", "flow:bull_1m+": "$1M or more in bullish premium",
                    "own:13g_active": "13G from a non-index fund", "own:13d": "13D (active intent)"}
MIN_SIMILAR = 30
DEFAULT_VARIANT = "call45_40"


# --------------------------------------------------------------------------- profiles

def variant_label(v: str, cfg: Config = Config(), translate=None) -> str:
    """``call45_40`` → "Call 45 days · +40 % / −25 %". ``translate`` is the interface's ``t()``
    when the label is shown on screen; without it the label comes out in English."""
    say = sayer(translate)
    kind, pct = v.split("_")
    stops = {int(round(t * 100)): int(round(s * 100)) for t, s in cfg.outcomes.targets}
    what = (say("Stock {months} months", months=kind[5:-1]) if kind.startswith("stock")
            else say("Call {days} days", days=kind[4:]))
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
                     "events_in_window": len(fired), "mkt_cap": float(row.get("mkt_cap", float("nan"))),
                     **conditions(row)})
    if not rows:
        return pd.DataFrame(columns=["ticker", "signal_date", "close", "events_in_window", "mkt_cap",
                                     *EVENT_TYPES])
    return pd.DataFrame(rows).sort_values(["signal_date", "ticker"], ascending=[False, True]).reset_index(drop=True)


def filter_events(events: pd.DataFrame, days: int | None = None, cap_tier: str = "all",
                  kinds: tuple[str, ...] | None = None, end: date | None = None) -> pd.DataFrame:
    """Narrow a saved scan without fetching anything: the window, the company size and the kind of
    event are views over what was already downloaded, not reasons to search again."""
    from miratrade.data.fundamentals import in_tier

    if events is None or events.empty:
        return events if events is not None else pd.DataFrame()
    out = events
    if days is not None:
        last = pd.Timestamp(end) if end is not None else pd.to_datetime(out["signal_date"]).max()
        out = out[pd.to_datetime(out["signal_date"]) > last - pd.Timedelta(days=days)]
    if cap_tier != "all":
        caps = pd.to_numeric(out.get("mkt_cap"), errors="coerce") if "mkt_cap" in out else None
        out = out[[in_tier(c, cap_tier) for c in caps]] if caps is not None else out.iloc[0:0]
    if kinds:
        present = [k for k in kinds if k in out]
        out = out[out[present].astype(bool).any(axis=1)] if present else out.iloc[0:0]
    return out


def within_window(now, start: str = "07:00", end: str = "22:30", weekdays_only: bool = True) -> bool:
    """Whether ``now`` falls inside a window given in **New York** time. Form 4s are filed to
    EDGAR on business days until about 22:00 there, so outside that there is nothing new to find
    and a repeated download would only spend the SEC's allowance."""
    from datetime import time as _time

    ts = pd.Timestamp(now)
    ts = ts.tz_localize("UTC") if ts.tzinfo is None else ts
    east = ts.tz_convert("America/New_York")
    if weekdays_only and east.weekday() >= 5:
        return False
    try:
        first, last = _time.fromisoformat(start), _time.fromisoformat(end)
    except ValueError:
        return True                              # an unreadable window must not silence the timer
    moment = east.time()
    return first <= moment <= last if first <= last else (moment >= first or moment <= last)


def new_york_time(now=None) -> pd.Timestamp:
    ts = pd.Timestamp(now if now is not None else pd.Timestamp.now(tz="UTC"))
    ts = ts.tz_localize("UTC") if ts.tzinfo is None else ts
    return ts.tz_convert("America/New_York")


def covered_days(scan: Mapping | None) -> int:
    """How many days the saved scan actually downloaded, so the screen can say when a filter is
    asking for more than there is."""
    if not scan or scan.get("since") is None or scan.get("end") is None:
        return 0
    return max(0, (scan["end"] - scan["since"]).days)


def describe(ev: Mapping, insiders: pd.DataFrame | None, ownership: pd.DataFrame | None,
             since: pd.Timestamp, min_value: float = 25_000) -> list[tuple[str, dict]]:
    """What was filed (who bought, how much; who crossed 5 %), as the pieces of one plain
    sentence. They stay as ``(template, fields)`` so the scan can save them and the screen can
    still show them in the user's language; ``note()`` joins them."""
    parts: list[tuple[str, dict]] = []
    t = ev["ticker"]
    if ev.get("event:insider_buy") and insiders is not None and len(insiders):
        b = insiders[(insiders["ticker"] == t) & (insiders["code"] == "P") & (insiders["value"] >= min_value)
                     & (pd.to_datetime(insiders["filing_date"]) >= since)]
        if len(b):
            n = int(b["owner_cik"].nunique())
            template = ("1 insider bought {amount}" if n == 1 else
                        "{count} insiders bought {amount}")
            parts.append((template, {"count": n, "amount": float(b["value"].sum())}))
    if ev.get("event:13dg") and ownership is not None and len(ownership):
        o = ownership[(ownership["ticker"] == t) & (pd.to_datetime(ownership["filing_date"]) >= since)
                      & ~ownership["passive"].astype(bool)]
        if len(o):
            r = o.sort_values("filing_date").iloc[-1]
            parts.append(("{filer} filed a {kind}" if not r["amendment"] else
                          "{filer} filed a {kind} (amended)",
                          {"filer": str(r["filer"]).title(), "kind": r["kind"]}))
    if ev.get("event:flow"):
        parts.append(("options with unusual volume", {}))
    return parts


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
        """The English sentence, which is what the console prints."""
        return self.say()

    def say(self, translate=None, number=None) -> str:
        """The same sentence through the interface's ``t()`` and its own number format."""
        say = sayer(translate)
        if self.n == 0:
            return say("No similar event in the latest report.")
        num = number or (lambda v, decimals=0: f"{v:,.{decimals}f}".replace("-", "−"))
        pct = lambda x: f"{num(x * 100, 0)} %"  # noqa: E731
        mean = f"{self.mean_return * 100:+.0f}".replace("-", "−")
        return say("{n} similar events: {target} reached the target first, {stop} the stop and "
                   "{neither} neither. Average result {mean} %.",
                   n=num(self.n, 0), target=pct(self.target), stop=pct(self.stop),
                   neither=pct(self.neither), mean=mean)


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

    # The events are the ones inside the window, but a purchase filed up to `look` days earlier
    # still counts towards the cluster and the amounts on those days, so the download starts there.
    first_filing = since - timedelta(days=look)
    log(f"Events from {since} to {end}. Downloading Form 4 filings from {first_filing}, because a "
        f"purchase keeps counting for {look} days …")
    insiders = fetch["insiders"](first_filing, end)
    new_buys = insiders[(insiders["code"] == "P") & (insiders["value"] >= cfg.insider.min_value_usd)
                        & (pd.to_datetime(insiders["filing_date"]).dt.date >= since)]
    tickers = set(new_buys["ticker"])
    ownership = None
    if smart_money:
        log(f"13D / 13G filings from {first_filing} (events from {since} to {end}) …")
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
    # FINRA's off-exchange volume: free, published each evening, and what the dark-pool conditions
    # read. It was never fetched by a scan, so those conditions could never fire.
    short_volume = None
    if smart_money and tickers:
        try:
            from miratrade.data.finra import fetch_short_volume

            log(f"Off-exchange volume (FINRA) for {len(tickers)} companies …")
            short_volume = fetch_short_volume(since - timedelta(days=look), end, tickers=tickers)
        except Exception as e:          # one optional source must not lose the whole scan
            log(f"  no off-exchange volume ({e})")
    log(f"Prices for {len(tickers)} companies …")
    # 400 extra days: 200-day averages at the window start plus a year of chart.
    prices = fetch["prices"](sorted(tickers | {"SPY"}), since - timedelta(days=400), end + timedelta(days=1))
    panel = build_panel(prices, insiders, flow, cfg, ownership=ownership,
                        short_volume=short_volume, shares=shares)
    events = recent_events({t: p for t, p in panel.items() if t != "SPY"}, pd.Timestamp(since))
    if len(events):
        parts = [describe(e, insiders, ownership, pd.Timestamp(since), cfg.insider.min_value_usd)
                 for e in events.to_dict("records")]
        # the rendered English for the console, and the pieces so the screen can translate them
        events["what"] = [note(p) for p in parts]
        events["what_parts"] = [json.dumps(p) for p in parts]
    log(f"{len(events)} new events.")
    # Everything downloaded is returned, not only what the screens draw. A filing fetched and then
    # dropped is a filing that has to be fetched again, and the 13D/G, the shares outstanding and
    # the option flow were all being thrown away here while the SEC was asked for them every run.
    return {"events": events, "prices": {t: prices[t] for t in events["ticker"] if t in prices},
            "insiders": insiders, "ownership": ownership, "shares": shares, "flow": flow,
            "short_volume": short_volume,
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
        log(f"Shares outstanding (SEC XBRL) for {len(tickers)} companies …")
        return fetch_shares(tickers, ticker_ciks(ins, tj, own), client, log)

    return {"insiders": insiders, "ownership": ownership, "prices": load_prices, "shares": shares}


# --------------------------------------------------------------------------- saved scans

# --------------------------------------------------------------------------- events in the store

# The store keeps these as columns of their own, because they are what gets filtered and indexed;
# every other flag a scan produces travels in `flags` as JSON, so adding a condition needs no
# migration. The keys are how the pipeline names them, the values how the table does.
EVENT_KINDS = {"event:insider_buy": "insider_buy", "event:flow": "flow", "event:13dg": "ownership",
               "event:congress_buy": "congress"}
EVENT_NAMED = ("ticker", "signal_date", "close", "mkt_cap", "what", "what_parts")


def events_to_rows(events: pd.DataFrame) -> pd.DataFrame:
    """A scan's events as rows of the store's ``events`` table."""
    if events is None or not len(events):
        return pd.DataFrame()
    out = pd.DataFrame(index=events.index)
    for name in EVENT_NAMED:
        out[name] = events[name] if name in events else None
    for source, column in EVENT_KINDS.items():
        out[column] = events[source].astype(bool).astype(int) if source in events else 0
    spare = [c for c in events.columns if c not in EVENT_NAMED and c not in EVENT_KINDS
             and c != "what_parts"]
    out["flags"] = [json.dumps({c: _plain(row[c]) for c in spare}) for _, row in events.iterrows()]
    return out


def empty_events() -> pd.DataFrame:
    """No events, but with the columns anyway.

    A caller that finds nothing still asks for ``["ticker"]`` or checks a flag, so an empty result
    has to be the same shape as a full one. Handing back a bare DataFrame made every such caller
    crash instead of showing an empty list.
    """
    return pd.DataFrame(columns=[*EVENT_NAMED, *EVENT_KINDS])


def rows_to_events(rows: pd.DataFrame) -> pd.DataFrame:
    """…and back: ``flags`` expanded into the columns the screens condition on, so a DataFrame read
    from the store is the same shape as one straight out of a scan."""
    if rows is None or not len(rows):
        return empty_events()
    out = rows.drop(columns=[c for c in ("flags",) if c in rows.columns]).copy()
    for source, column in EVENT_KINDS.items():
        if column in out.columns:
            out[source] = out.pop(column).fillna(0).astype(bool)
    spread = pd.DataFrame([json.loads(f or "{}") for f in rows.get("flags", [])], index=rows.index)
    for column in spread.columns:
        if column not in out.columns:
            out[column] = spread[column]
    return out


def _plain(value):
    """A flag as JSON can hold it: numpy bools and NaN are not JSON."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    return value if isinstance(value, (int, float, str)) else str(value)


def store_scan(result: dict, db=None) -> dict:
    """Put a finished scan in the shared market database: its events, its price bars and the days it
    covered. Returns how many rows of each went in.

    This is what makes the screens' filters queries instead of re-reads, and what lets another app
    see the same events. See docs/DATA.md.
    """
    from miratrade import store

    owned, db = db is None, db if db is not None else store.connect()
    try:
        written = {"events": store.write(db, "events", events_to_rows(result.get("events")))}
        bars = 0
        for ticker, df in (result.get("prices") or {}).items():
            if df is not None and len(df):
                bars += store.write(db, "prices", df.assign(ticker=ticker))
        written["prices"] = bars
        # The raw filings behind those events, so nothing is ever downloaded twice. `insiders` is
        # already stored as it is parsed; these three were not stored anywhere at all.
        written["ownership"] = store.write(db, "ownership", result.get("ownership"))
        written["shares"] = store.write(db, "shares_outstanding", result.get("shares"))
        written["short_volume"] = store.write(db, "short_volume", result.get("short_volume"))
        flow = result.get("flow")
        if flow is not None and len(flow):
            written["option_flow"] = store.write(db, "option_flow", flow.assign(source="scan"))
        since, end = result.get("since"), result.get("end")
        if since and end:
            store.mark_covered(db, "events", pd.bdate_range(since, end).date,
                               rows=written["events"])
        return written
    finally:
        if owned:
            db.close()


def load_events(db, days: int | None = None, cap_tier: str = "all",
                kinds: tuple[str, ...] | None = None, end: date | None = None,
                ticker: str = "", limit: int = 5000) -> pd.DataFrame:
    """Events from the store, narrowed in SQL rather than in memory.

    The window, the company size, the kind of event and the ticker are all views over what was
    downloaded — never a reason to download again — and doing that narrowing in the database is what
    keeps changing a dropdown instant with tens of thousands of events stored.
    """
    from miratrade import store
    from miratrade.config import CAP_TIERS

    where, params = [], []
    if days:
        last = pd.Timestamp(end) if end is not None else _last_event_day(db)
        if last is not None:
            where.append("signal_date > ?")
            params.append((last - pd.Timedelta(days=days)).strftime("%Y-%m-%d"))
    if cap_tier and cap_tier != "all":
        low, high, _label = CAP_TIERS[cap_tier]
        where.append("mkt_cap IS NOT NULL")          # an unknown size is only kept by "all"
        if low is not None:
            where.append("mkt_cap >= ?")
            params.append(float(low))
        if high is not None:
            where.append("mkt_cap < ?")
            params.append(float(high))
    if kinds:
        columns = [EVENT_KINDS[k] for k in kinds if k in EVENT_KINDS]
        if columns:
            where.append("(" + " OR ".join(f"{c} = 1" for c in columns) + ")")
        else:
            return empty_events()
    if ticker.strip():
        wanted = [x.strip().upper() for x in ticker.replace(";", ",").split(",") if x.strip()]
        if wanted:
            where.append(f"upper(ticker) IN ({','.join('?' * len(wanted))})")
            params += wanted
    rows = store.read(db, "events", " AND ".join(where), params,
                      order=f"signal_date DESC, ticker LIMIT {int(limit)}")
    return rows_to_events(rows)


def _last_event_day(db):
    """The newest event stored, so "the last 7 days" means the last 7 days that were downloaded
    rather than the last 7 calendar days, which may hold nothing at all."""
    row = db.execute("SELECT max(signal_date) AS d FROM events").fetchone()
    value = row["d"] if row is not None else None
    return pd.Timestamp(value) if value else None


def stored_days(db) -> int:
    """How many days of events the store holds, for the screen to say when it has fewer than asked."""
    row = db.execute("SELECT min(signal_date) AS a, max(signal_date) AS b FROM events").fetchone()
    if row is None or not row["a"]:
        return 0
    return int((pd.Timestamp(row["b"]) - pd.Timestamp(row["a"])).days) + 1


def save_scan(result: dict, folder: Path) -> Path:
    """Write the last scan as plain files, beside :func:`store_scan`.

    The shared market database is what the screens read; this is the readable copy — one CSV anyone
    can open, and the window the scan covered. The price bars are **not** written here any more:
    they live in the database, and a copy per ticker per scan was tens of thousands of duplicated
    rows on disk for something nothing read.
    """
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    result["events"].to_csv(folder / "events.csv", index=False)
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
