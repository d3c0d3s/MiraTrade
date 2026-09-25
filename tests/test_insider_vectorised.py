"""Regression: the vectorised ``insider_features`` must match the original per-date loop exactly."""
import numpy as np
import pandas as pd
import pytest

from miratrade.config import InsiderParams
from miratrade.signals.insider import EXEC_RE, INSIDER_FEATURES, insider_features
from miratrade.synthetic import make_market


def _reference_insider_features(insiders, dates, ticker, p=InsiderParams()):
    """The original (slow) implementation, kept verbatim as a test oracle."""
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
            dates_by_owner = b.groupby("owner_cik")["trade_date"].min().sort_values()
            td = pd.to_datetime(dates_by_owner.values)
            row["ins_cluster"] = max(((td >= t) & (td <= t + cluster)).sum() for t in td)
            row["ins_exec_buy"] = float(b["title"].fillna("").str.contains(EXEC_RE, case=False).any())
            row["ins_max_delta_own"] = b["delta_own_pct"].max()
            since = d - window if since_prev is None else since_prev
            row["ins_fresh"] = float((b["filing_date"] > since).any())
        out.loc[d] = row
    return out


def _messy(insiders: pd.DataFrame, tickers: list[str], seed: int = 0) -> pd.DataFrame:
    """Synthetic filings plus random buys/sells: odd values, weekend and intraday filing times,
    missing titles/deltas, repeat owners, unsorted rows."""
    rng = np.random.default_rng(seed)
    start = insiders["filing_date"].min() - pd.Timedelta(days=60)
    n = 1500
    filing = start + pd.to_timedelta(rng.integers(0, 400 * 24, n), unit="h")
    extra = pd.DataFrame({
        "ticker": rng.choice(tickers, n),
        "filing_date": filing,
        "trade_date": filing - pd.to_timedelta(rng.integers(0, 12, n), unit="D"),
        "owner_cik": rng.choice([f"o{i}" for i in range(12)], n),
        "code": rng.choice(["P", "P", "S", "A"], n),
        "value": np.round(rng.lognormal(10.5, 1.2, n), 2),
        "title": rng.choice(["CEO", "Chief Financial Officer", "Director", "", None, "10% owner"], n),
        "delta_own_pct": np.where(rng.random(n) < 0.2, np.nan, rng.random(n)),
    })
    cols = list(extra.columns)
    return pd.concat([insiders[cols], extra], ignore_index=True).sample(frac=1, random_state=seed)


@pytest.fixture(scope="module")
def market():
    prices, insiders, _ = make_market(n_tickers=12, n_days=300, event_days=200, events_per_ticker=8)
    return prices, insiders


@pytest.mark.parametrize("messy", [False, True])
@pytest.mark.parametrize("params", [InsiderParams(),
                                    InsiderParams(cluster_window_days=3, min_value_usd=0, lookback_days=7)])
def test_matches_reference_loop(market, messy, params):
    prices, insiders = market
    if messy:
        insiders = _messy(insiders, list(prices))
    for t, df in prices.items():
        new = insider_features(insiders, df.index, t, params)
        old = _reference_insider_features(insiders, df.index, t, params)
        pd.testing.assert_frame_equal(new, old, check_exact=True)
    assert (new.index == df.index).all()


def test_matches_reference_on_irregular_dates(market):
    """Non-contiguous bars (gaps longer than the lookback) exercise ``ins_fresh``."""
    prices, insiders = market
    insiders = _messy(insiders, list(prices), seed=1)
    dates = prices["T00"].index[::9]
    pd.testing.assert_frame_equal(insider_features(insiders, dates, "T00"),
                                  _reference_insider_features(insiders, dates, "T00"), check_exact=True)
