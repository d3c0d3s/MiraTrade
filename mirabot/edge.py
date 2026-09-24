"""Edge discovery: which combinations of conditions separated winning swing trades from losers?

Rules (conjunctions of up to ``max_rule_size`` conditions) are *discovered* on the first
``train_frac`` of the window and *validated* on the remainder. Because many rules are tried,
train p-values are corrected with Benjamini-Hochberg; only rules that hold up out-of-sample
are reported as an edge.
"""
from __future__ import annotations

import itertools
import math

import numpy as np
import pandas as pd

from mirabot.config import EdgeParams


def stats(r: pd.Series, mu0: float = 0.0) -> dict:
    """Performance of a set of trades in R-multiples; ``t``/``p`` test mean R > ``mu0``."""
    n = len(r)
    if n == 0:
        return {"n": 0, "win_rate": np.nan, "avg_r": np.nan, "profit_factor": np.nan,
                "t": np.nan, "p": 1.0}
    wins, losses = r[r > 0].sum(), -r[r < 0].sum()
    sd = r.std(ddof=1) if n > 1 else np.nan
    t = (r.mean() - mu0) / (sd / math.sqrt(n)) if n > 1 and sd > 0 else np.nan
    # One-sided p-value, normal approximation.
    p = 0.5 * math.erfc(t / math.sqrt(2)) if np.isfinite(t) else 1.0
    return {"n": n, "win_rate": (r > 0).mean(), "avg_r": r.mean(),
            "profit_factor": wins / losses if losses > 0 else np.inf, "t": t, "p": p}


def condition_columns(trades: pd.DataFrame) -> list[str]:
    return [c for c in trades.columns if ":" in c and trades[c].dtype == bool]


def benjamini_hochberg(p: pd.Series, q: float = 0.10) -> pd.Series:
    order = p.sort_values()
    m = len(order)
    passed = order.values <= q * np.arange(1, m + 1) / m
    k = np.flatnonzero(passed).max() + 1 if passed.any() else 0
    out = pd.Series(False, index=p.index)
    out[order.index[:k]] = True
    return out


def split(trades: pd.DataFrame, train_frac: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Time split on signal date; train trades that exit after the cutoff are dropped."""
    dates = trades["signal_date"].sort_values()
    cutoff = dates.iloc[int(len(dates) * train_frac)] if len(dates) else pd.Timestamp.max
    train = trades[(trades["signal_date"] < cutoff) & (trades["exit_date"] < cutoff)]
    test = trades[trades["signal_date"] >= cutoff]
    return train, test


def mine_rules(trades: pd.DataFrame, p: EdgeParams = EdgeParams()) -> tuple[pd.DataFrame, dict]:
    trades = trades[trades["exit_reason"] != "open"]
    train, test = split(trades, p.train_frac)
    conds = [c for c in condition_columns(trades) if train[c].sum() >= p.min_trades]
    baseline = {"all": stats(trades["r"]), "train": stats(train["r"]), "test": stats(test["r"]),
                "cutoff": test["signal_date"].min() if len(test) else None}

    rows = []
    for k in range(1, p.max_rule_size + 1):
        for combo in itertools.combinations(conds, k):
            # Skip rules that pair two different setups (mutually exclusive by design).
            if sum(c.startswith("setup:") for c in combo) > 1:
                continue
            m_tr = train[list(combo)].all(axis=1)
            if m_tr.sum() < p.min_trades:
                continue
            m_te = test[list(combo)].all(axis=1)
            # Significance is lift over the baseline, not merely "profitable": in a rising
            # market nearly every long rule is profitable.
            tr = stats(train.loc[m_tr, "r"], mu0=max(baseline["train"]["avg_r"], 0))
            te = stats(test.loc[m_te, "r"], mu0=max(baseline["test"]["avg_r"], 0))
            rows.append({"rule": " & ".join(combo), "size": k,
                         **{f"train_{a}": b for a, b in tr.items()},
                         **{f"test_{a}": b for a, b in te.items()}})
    rules = pd.DataFrame(rows)
    if rules.empty:
        return rules, baseline
    rules["train_bh_sig"] = benjamini_hochberg(rules["train_p"], p.fdr)
    rules["validated"] = (
        rules["train_bh_sig"]
        & (rules["train_avg_r"] >= max(baseline["train"]["avg_r"], 0) + p.min_lift_r)
        & (rules["test_n"] >= max(3, p.min_trades // 3))
        & (rules["test_avg_r"] >= max(baseline["test"]["avg_r"], 0) + p.min_lift_r)
    )
    # Prefer rules that are robust (validated), then statistically strong, then simple.
    rules["score"] = (rules["train_t"].fillna(0) + rules["test_t"].fillna(0)) / np.sqrt(rules["size"])
    rules = rules.sort_values(["validated", "train_bh_sig", "score"], ascending=False)
    return rules.reset_index(drop=True), baseline


def prune_redundant(rules: pd.DataFrame, top: int = 10) -> pd.DataFrame:
    """Drop rules that select the same trades as, or only add a condition to, a listed rule
    without improving it."""
    kept: list[pd.Series] = []
    sig = ["train_n", "train_avg_r", "test_n", "test_avg_r"]
    for _, r in rules.sort_values(["size", "score"], ascending=[True, False]).iterrows():
        parts = set(r["rule"].split(" & "))
        dominated = any((set(k["rule"].split(" & ")) <= parts and k["test_avg_r"] >= r["test_avg_r"])
                        or all(np.isclose(k[c], r[c]) for c in sig) for k in kept)
        if not dominated:
            kept.append(r)
    out = pd.DataFrame(kept)
    return out.sort_values("score", ascending=False).head(top) if len(out) else out


def scan(panel: dict[str, pd.DataFrame], rules: pd.DataFrame, cfg_trade) -> pd.DataFrame:
    """Apply validated rules to each ticker's latest bar: today's trade candidates.

    Only bars that would have produced a trade in the backtest (an entry trigger) qualify, so
    live candidates are drawn from the same population the rules were measured on.
    """
    from mirabot.backtest import conditions, entry_trigger

    if rules.empty or "validated" not in rules:
        return pd.DataFrame()
    live = rules[rules["validated"]]
    out = []
    for t, ind in panel.items():
        row = ind.iloc[-1]
        if not np.isfinite(row["atr"]) or not entry_trigger(ind.iloc[[-1]]).iat[0]:
            continue
        c = conditions(row)
        hits = [r for r in live.itertuples() if all(c.get(x, False) for x in r.rule.split(" & "))]
        if not hits:
            continue
        best = max(hits, key=lambda r: r.test_avg_r)
        px = row["close"]
        out.append({"ticker": t, "date": ind.index[-1].date(), "close": round(px, 2),
                    "stop": round(px - cfg_trade.stop_atr * row["atr"], 2),
                    "target": round(px + cfg_trade.target_atr * row["atr"], 2),
                    "rules_matched": len(hits), "best_rule": best.rule,
                    "best_rule_test_avg_r": round(best.test_avg_r, 2)})
    return pd.DataFrame(out).sort_values(["rules_matched", "best_rule_test_avg_r"],
                                         ascending=False) if out else pd.DataFrame()
