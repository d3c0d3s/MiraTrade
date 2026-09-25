"""Insider-buying features, point-in-time: a filing is only visible from its filing date."""
from __future__ import annotations

import numpy as np
import pandas as pd

from miratrade.config import InsiderParams

EXEC_RE = r"\b(?:CEO|CFO|COO|President|Chief Executive|Chief Financial|Chairman)\b"

INSIDER_FEATURES = ["ins_buy_value", "ins_buyers", "ins_cluster", "ins_exec_buy",
                    "ins_max_delta_own", "ins_sell_value", "ins_fresh"]


def _by_filing(ev: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray]:
    """Rows sorted (stably) by filing date, plus their filing dates as datetime64[ns]."""
    ev = ev[ev["filing_date"].notna()].sort_values("filing_date", kind="stable")
    return ev, ev["filing_date"].to_numpy("datetime64[ns]")


def _window_bounds(fd: np.ndarray, d: np.ndarray, window: np.timedelta64) -> tuple[np.ndarray, np.ndarray]:
    """[lo, hi) slices of the sorted filing dates ``fd`` with ``d - window < fd <= d``."""
    return np.searchsorted(fd, d - window, side="right"), np.searchsorted(fd, d, side="right")


def _max_cluster(owner: np.ndarray, td: np.ndarray, cluster: np.timedelta64) -> int:
    """Largest number of distinct insiders whose first purchase falls inside one cluster window."""
    ok = (owner >= 0) & ~np.isnat(td)
    owner, td = owner[ok], td[ok]
    if owner.size == 0:
        return 0
    order = np.lexsort((td, owner))
    owner, td = owner[order], td[order]
    first = np.ones(owner.size, dtype=bool)
    first[1:] = owner[1:] != owner[:-1]
    t = np.sort(td[first])
    return int((np.searchsorted(t, t + cluster, side="right") - np.searchsorted(t, t, side="left")).max())


def insider_features(insiders: pd.DataFrame, dates: pd.DatetimeIndex, ticker: str,
                     p: InsiderParams = InsiderParams()) -> pd.DataFrame:
    """Rolling insider features for one ticker on each date in ``dates``.

    Filings are sorted by filing date once, so each bar's lookback window
    ``(d - lookback_days, d]`` is a contiguous slice found with ``searchsorted``."""
    out = np.zeros((len(dates), len(INSIDER_FEATURES)))
    ev = insiders[insiders["ticker"] == ticker]
    if ev.empty:
        return pd.DataFrame(out, index=dates, columns=INSIDER_FEATURES)
    ev = ev.assign(filing_date=pd.to_datetime(ev["filing_date"]).dt.normalize(), _row=np.arange(len(ev)))
    buys, b_fd = _by_filing(ev[(ev["code"] == "P") & (ev["value"] >= p.min_value_usd)])
    sells, s_fd = _by_filing(ev[ev["code"] == "S"])
    window = np.timedelta64(pd.Timedelta(days=p.lookback_days).value, "ns")
    cluster = np.timedelta64(pd.Timedelta(days=p.cluster_window_days).value, "ns")

    # Per-row arrays; ``*_pos`` keeps each row's original position so window sums add up in the
    # original row order (bit-identical to summing a boolean-filtered frame).
    b_pos = buys["_row"].to_numpy()
    b_val = buys["value"].to_numpy()
    b_owner = pd.factorize(buys["owner_cik"])[0]
    b_td = pd.to_datetime(buys["trade_date"]).to_numpy("datetime64[ns]")
    b_exec = buys["title"].fillna("").str.contains(EXEC_RE, case=False).to_numpy(dtype=bool)
    b_delta = buys["delta_own_pct"].to_numpy(dtype=float)
    s_pos = sells["_row"].to_numpy()
    s_val = sells["value"].to_numpy()

    d = dates.to_numpy("datetime64[ns]")
    b_lo, b_hi = _window_bounds(b_fd, d, window)
    s_lo, s_hi = _window_bounds(s_fd, d, window)
    # Previous bar (covers non-trading filing days); the first bar looks back a full window.
    since = np.empty_like(d)
    if len(d):
        since[0] = d[0] - window
        since[1:] = d[:-1]

    def in_order(pos: np.ndarray, lo: int, hi: int) -> np.ndarray:
        return lo + np.argsort(pos[lo:hi])

    cache: dict[tuple[int, int], tuple[float, ...]] = {}
    for i in np.flatnonzero((b_hi > b_lo) | (s_hi > s_lo)):
        slo, shi = s_lo[i], s_hi[i]
        out[i, 5] = np.nansum(s_val[in_order(s_pos, slo, shi)]) if shi > slo else 0.0
        lo, hi = b_lo[i], b_hi[i]
        if hi == lo:
            continue
        if (lo, hi) not in cache:
            owners = b_owner[lo:hi]
            delta = b_delta[lo:hi]
            delta = delta[~np.isnan(delta)]
            cache[lo, hi] = (
                np.sum(b_val[in_order(b_pos, lo, hi)]),
                np.unique(owners[owners >= 0]).size,
                _max_cluster(owners, b_td[lo:hi], cluster),
                float(b_exec[lo:hi].any()),
                delta.max() if delta.size else np.nan,
            )
        out[i, :5] = cache[lo, hi]
        out[i, 6] = float(b_fd[hi - 1] > since[i])
    return pd.DataFrame(out, index=dates, columns=INSIDER_FEATURES)
