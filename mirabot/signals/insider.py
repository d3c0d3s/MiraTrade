"""Insider-buying features, point-in-time: a filing is only visible from its filing date."""
from __future__ import annotations

import pandas as pd

from mirabot.config import InsiderParams

EXEC_RE = r"\b(?:CEO|CFO|COO|President|Chief Executive|Chief Financial|Chairman)\b"

INSIDER_FEATURES = ["ins_buy_value", "ins_buyers", "ins_cluster", "ins_exec_buy",
                    "ins_max_delta_own", "ins_sell_value", "ins_fresh"]


def insider_features(insiders: pd.DataFrame, dates: pd.DatetimeIndex, ticker: str,
                     p: InsiderParams = InsiderParams()) -> pd.DataFrame:
    """Rolling insider features for one ticker on each date in ``dates``."""
    out = pd.DataFrame(0.0, index=dates, columns=INSIDER_FEATURES)
    ev = insiders[insiders["ticker"] == ticker]
    if ev.empty:
        return out
    ev = ev.assign(filing_date=pd.to_datetime(ev["filing_date"]).dt.normalize())
    buys = ev[(ev["code"] == "P") & (ev["value"] >= p.min_value_usd)]
    sells = ev[ev["code"] == "S"]
    window = pd.Timedelta(days=p.lookback_days)
    cluster = pd.Timedelta(days=p.cluster_window_days)
    prev = None

    for d in dates:
        b = buys[(buys["filing_date"] <= d) & (buys["filing_date"] > d - window)]
        s = sells[(sells["filing_date"] <= d) & (sells["filing_date"] > d - window)]
        since_prev, prev = prev, d
        if b.empty and s.empty:
            continue
        row = out.loc[d]
        row["ins_sell_value"] = s["value"].sum()
        if not b.empty:
            row["ins_buy_value"] = b["value"].sum()
            row["ins_buyers"] = b["owner_cik"].nunique()
            # Largest number of distinct insiders whose purchases fall inside one cluster window.
            dates_by_owner = b.groupby("owner_cik")["trade_date"].min().sort_values()
            td = pd.to_datetime(dates_by_owner.values)
            row["ins_cluster"] = max(((td >= t) & (td <= t + cluster)).sum() for t in td)
            row["ins_exec_buy"] = float(b["title"].fillna("").str.contains(EXEC_RE, case=False).any())
            row["ins_max_delta_own"] = b["delta_own_pct"].max()
            # A new buy filing arrived since the previous bar (covers non-trading filing days).
            since = d - window if since_prev is None else since_prev
            row["ins_fresh"] = float((b["filing_date"] > since).any())
        out.loc[d] = row
    return out
