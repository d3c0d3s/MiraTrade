"""What happened after each event, under every "high profit" profile.

For each event (a new insider buy, a day of bullish unusual flow, a new 13D / active 13G;
later events on the same ticker within ``event_cooldown`` sessions are the same move and are
skipped) the entry is the next session's open, and each profile asks: which came first, the
target or the stop?

* ``stock12m_30`` … ``stock12m_50``: the shares, over ``long_months``; target and stop on the
  stock price (a bar touching both counts as the stop; a gap through a level fills at the open).
* ``call30_30`` … ``call60_50``: a ~0.65-delta call on the monthly expiry nearest 30/45/60 days
  out, target and stop on the premium, valued each close with Black-Scholes (realised vol ×
  ``iv_mult``, half-spread paid both ways), held at most ``call_max_hold`` sessions and never
  into the last ``call_exit_days_before_expiry`` days. **Modelled prices**, not quotes.

Each variant column is ``res_<v>`` (1 target, -1 stop, 0 neither by the horizon, NaN when the
horizon runs past the data) and ``ret_<v>`` (the return).
"""
from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd

from miratrade.config import Config, OptionParams
from miratrade.options_trades import bs_price, option_contract

EVENT_TYPES = ("event:insider_buy", "event:flow", "event:13dg")


def variants(cfg: Config) -> list[str]:
    o = cfg.outcomes
    pct = [int(round(t * 100)) for t, _ in o.targets]
    return ([f"stock{o.long_months}m_{p}" for p in pct]
            + [f"call{d}_{p}" for d in o.call_dtes for p in pct])


def stock_outcome(o: np.ndarray, h: np.ndarray, l: np.ndarray, c: np.ndarray, i: int,
                  last: int, target: float, stop: float) -> tuple[float, float]:
    """Enter at ``o[i]``; scan bars ``i..last``. Returns (result, return)."""
    entry = o[i]
    up, dn = entry * (1 + target), entry * (1 - stop)
    for j in range(i, last + 1):
        if j > i and o[j] <= dn:                        # gapped through the stop
            return -1.0, o[j] / entry - 1
        if j > i and o[j] >= up:                        # gapped through the target
            return 1.0, o[j] / entry - 1
        if l[j] <= dn:                                  # both touched: assume the worse
            return -1.0, -stop
        if h[j] >= up:
            return 1.0, target
    return 0.0, c[last] / entry - 1


def call_outcome(ind: pd.DataFrame, i: int, vol: float, dte: int, target: float, stop: float,
                 p: OptionParams, max_hold: int, exit_before: int) -> tuple[float, float]:
    """Buy the call at bar ``i``'s open; check the modelled bid at each close."""
    day0 = ind.index[i].date()
    pp = replace(p, target_dte=dte, min_dte=max(21, dte - 15))
    c = option_contract(ind["open"].iat[i], day0, vol, pp)
    ask = c["ask"]
    if not np.isfinite(ask) or ask <= 0:
        return np.nan, np.nan
    closes = ind["close"].to_numpy()
    last_day = c["expiry"] - pd.Timedelta(days=exit_before).to_pytimedelta()
    bid = ask
    for j in range(i, min(i + max_hold, len(ind) - 1) + 1):
        day = ind.index[j].date()
        if day > last_day:
            break
        t = max((c["expiry"] - day).days, 0) / 365
        bid = bs_price(closes[j], c["strike"], t, pp.rate, c["sigma"]) * (1 - pp.half_spread)
        ret = bid / ask - 1
        if ret >= target:
            return 1.0, ret
        if ret <= -stop:
            return -1.0, ret
    return 0.0, bid / ask - 1


def build_outcomes(panel: dict[str, pd.DataFrame], cfg: Config = Config(),
                   start: pd.Timestamp | None = None) -> pd.DataFrame:
    """One row per event: ticker, dates, its conditions and regime, and every variant."""
    from miratrade.backtest import conditions, entry_trigger

    o = cfg.outcomes
    rows = []
    for t, ind in panel.items():
        fired = np.flatnonzero(entry_trigger(ind).to_numpy())
        opens, highs, lows, closes = (ind[k].to_numpy() for k in ("open", "high", "low", "close"))
        cool_until = -1
        for s in fired:
            if s <= cool_until or (start is not None and ind.index[s] < start):
                continue
            i = s + 1                                   # enter at the next open
            if i >= len(ind) or closes[s] < cfg.trade.min_price:
                continue
            cool_until = s + o.event_cooldown
            row = ind.iloc[s]
            rec = {"ticker": t, "signal_date": ind.index[s], "entry_date": ind.index[i], "entry": opens[i],
                   "rv20": row.get("rv20", np.nan),
                   "mkt_trend": row.get("mkt_trend", "unknown"), "mkt_vol": row.get("mkt_vol", "unknown"),
                   **conditions(row)}
            end = ind.index[i] + pd.DateOffset(months=o.long_months)
            for tgt, stp in o.targets:
                v = f"stock{o.long_months}m_{int(round(tgt * 100))}"
                if end > ind.index[-1]:
                    rec[f"res_{v}"] = rec[f"ret_{v}"] = np.nan
                else:
                    last = int(ind.index.searchsorted(end, side="right")) - 1
                    rec[f"res_{v}"], rec[f"ret_{v}"] = stock_outcome(opens, highs, lows, closes, i, last, tgt, stp)
            vol = row.get("rv20", np.nan)
            for dte in o.call_dtes:
                for tgt, stp in o.targets:
                    v = f"call{dte}_{int(round(tgt * 100))}"
                    if not np.isfinite(vol) or i + o.call_max_hold >= len(ind):
                        rec[f"res_{v}"] = rec[f"ret_{v}"] = np.nan
                        continue
                    rec[f"res_{v}"], rec[f"ret_{v}"] = call_outcome(
                        ind, i, vol, dte, tgt, stp, cfg.options, o.call_max_hold, o.call_exit_days_before_expiry)
            rows.append(rec)
    return pd.DataFrame(rows)


def _horizon(v: str, cfg: Config) -> pd.DateOffset:
    """Latest possible exit after entry: used to purge training events that were still open."""
    if v.startswith("stock"):
        return pd.DateOffset(months=cfg.outcomes.long_months)
    return pd.DateOffset(days=int(cfg.outcomes.call_max_hold * 7 / 5) + 3)


def variant_frame(outcomes: pd.DataFrame, v: str, cfg: Config) -> pd.DataFrame:
    """The events measured under ``v``, shaped like a trades table for ``edge.mine_rules``:
    ``r`` is the return, ``exit_date`` the latest possible exit."""
    d = outcomes.dropna(subset=[f"res_{v}"]).copy()
    d["r"] = d[f"ret_{v}"]
    d["exit_reason"] = "closed"
    d["exit_date"] = d["entry_date"] + _horizon(v, cfg)
    return d


def mine_profiles(outcomes: pd.DataFrame, cfg: Config = Config()) -> dict[str, dict]:
    """Rule mining and walk-forward for every variant. Picking the best of several variants is
    itself a search, so the false discovery rate is split evenly across them."""
    from miratrade.edge import attach_walk_forward, mine_rules, walk_forward

    vs = [v for v in variants(cfg) if f"res_{v}" in outcomes]
    p = replace(cfg.edge, min_lift_r=cfg.outcomes.min_lift, fdr=cfg.edge.fdr / max(len(vs), 1))
    out = {}
    for v in vs:
        d = variant_frame(outcomes, v, cfg)
        if len(d) < 2 * p.min_trades:
            continue
        rules, baseline = mine_rules(d, p)
        wf = walk_forward(d, p)
        out[v] = {"rules": attach_walk_forward(rules, wf, p), "baseline": baseline, "wf": wf, "events": len(d)}
    return out


def summarize(outcomes: pd.DataFrame, cfg: Config = Config()) -> pd.DataFrame:
    """Per variant: events measured, share reaching the target first / the stop first, mean return."""
    from miratrade.edge import stats

    out = []
    for v in variants(cfg):
        if f"res_{v}" not in outcomes:
            continue
        d = outcomes.dropna(subset=[f"res_{v}"])
        s = stats(d[f"ret_{v}"])
        out.append({"variant": v, "events": len(d), "target_first": (d[f"res_{v}"] == 1).mean() if len(d) else np.nan,
                    "stop_first": (d[f"res_{v}"] == -1).mean() if len(d) else np.nan,
                    "mean_return": s["avg_r"], "t": s["t"]})
    return pd.DataFrame(out)
