"""Edge discovery: which combinations of conditions separated winning swing trades from losers?

Rules (conjunctions of up to ``max_rule_size`` conditions) are *discovered* on the first
``train_frac`` of the window and *validated* on the remainder. Because many rules are tried,
train p-values are corrected with Benjamini-Hochberg; only rules that hold up out-of-sample
are reported as an edge.

``walk_forward`` repeats the whole discovery step on an expanding window: each fold mines rules
on every trade that closed before it and measures them on the next slice only. It answers
"how did the rules this process picks do on data it had not seen yet?", over several slices
instead of one.
"""
from __future__ import annotations

import itertools
import math

import numpy as np
import pandas as pd

from miratrade.config import EdgeParams


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


def _hurdle(s: dict) -> float:
    # Significance is lift over the baseline, not merely "profitable": in a rising market
    # nearly every long rule is profitable.
    return max(s["avg_r"], 0)


def _score_rules(train: pd.DataFrame, test: pd.DataFrame, p: EdgeParams,
                 mu_train: float, mu_test: float) -> pd.DataFrame:
    """Train and test stats of every rule with at least ``min_trades`` train trades."""
    conds = [c for c in condition_columns(train) if train[c].sum() >= p.min_trades]
    col = {c: k for k, c in enumerate(conds)}
    x_tr, x_te = train[conds].to_numpy(bool), test[conds].to_numpy(bool)
    r_tr, r_te = train["r"].to_numpy(), test["r"].to_numpy()
    rows = []
    for k in range(1, p.max_rule_size + 1):
        for combo in itertools.combinations(conds, k):
            # Skip rules that pair two different setups (mutually exclusive by design).
            if sum(c.startswith("setup:") for c in combo) > 1:
                continue
            idx = [col[c] for c in combo]
            m_tr = x_tr[:, idx].all(axis=1)
            if m_tr.sum() < p.min_trades:
                continue
            m_te = x_te[:, idx].all(axis=1)
            tr = stats(pd.Series(r_tr[m_tr]), mu0=mu_train)
            te = stats(pd.Series(r_te[m_te]), mu0=mu_test)
            rows.append({"rule": " & ".join(combo), "size": k,
                         **{f"train_{a}": b for a, b in tr.items()},
                         **{f"test_{a}": b for a, b in te.items()}})
    rules = pd.DataFrame(rows)
    if not rules.empty:
        rules["train_bh_sig"] = benjamini_hochberg(rules["train_p"], p.fdr)
    return rules


def _selected(rules: pd.DataFrame, mu_train: float, p: EdgeParams) -> pd.Series:
    """Rules the discovery step picks, judged on train data only."""
    return rules["train_bh_sig"] & (rules["train_avg_r"] >= mu_train + p.min_lift_r)


def _min_test_n(p: EdgeParams) -> int:
    return max(3, p.min_trades // 3)


def mine_rules(trades: pd.DataFrame, p: EdgeParams = EdgeParams()) -> tuple[pd.DataFrame, dict]:
    trades = trades[trades["exit_reason"] != "open"]
    train, test = split(trades, p.train_frac)
    baseline = {"all": stats(trades["r"]), "train": stats(train["r"]), "test": stats(test["r"]),
                "cutoff": test["signal_date"].min() if len(test) else None}
    mu_train, mu_test = _hurdle(baseline["train"]), _hurdle(baseline["test"])
    rules = _score_rules(train, test, p, mu_train, mu_test)
    if rules.empty:
        return rules, baseline
    rules["validated"] = (
        _selected(rules, mu_train, p)
        & (rules["test_n"] >= _min_test_n(p))
        & (rules["test_avg_r"] >= mu_test + p.min_lift_r)
    )
    # Prefer rules that are robust (validated), then statistically strong, then simple.
    rules["score"] = (rules["train_t"].fillna(0) + rules["test_t"].fillna(0)) / np.sqrt(rules["size"])
    rules = rules.sort_values(["validated", "train_bh_sig", "score"], ascending=False)
    return rules.reset_index(drop=True), baseline


def walk_forward(trades: pd.DataFrame, p: EdgeParams = EdgeParams()) -> dict:
    """Anchored walk-forward validation of the rule-mining process.

    Closed trades are ordered by signal date; the last ``1 - wf_min_train_frac`` of them is cut
    into ``wf_folds`` consecutive test slices. For each slice, rules are mined (BH-corrected,
    lift over the train baseline) on every earlier trade that had also *exited* before the
    slice starts, then measured on the slice. Returns

    * ``folds``: one row per slice (rules tested and picked, how the picked rules did),
    * ``rules``: per rule, how it did in the slices where it was picked,
    * ``summary``: every picked trade pooled, as lift over its slice's baseline.
    """
    closed = trades[trades["exit_reason"] != "open"].sort_values("signal_date", kind="stable")
    dates, n = closed["signal_date"], len(closed)
    bounds = [int(n * f) for f in np.linspace(p.wf_min_train_frac, 1.0, p.wf_folds + 1)]
    fold_rows, rule_parts, picked_parts = [], [], []
    for k in range(p.wf_folds):
        lo, hi = bounds[k], bounds[k + 1]
        if hi <= lo or lo >= n:
            continue
        t0 = dates.iloc[lo]
        t1 = dates.iloc[hi] if hi < n else pd.Timestamp.max
        train = closed[(dates < t0) & (closed["exit_date"] < t0)]
        test = closed[(dates >= t0) & (dates < t1)]
        if test.empty:
            continue
        base_test = stats(test["r"])
        mu_train, mu_test = _hurdle(stats(train["r"])), _hurdle(base_test)
        rules = _score_rules(train, test, p, mu_train, mu_test)
        sel = rules[_selected(rules, mu_train, p)] if not rules.empty else rules
        picked = np.zeros(len(test), dtype=bool)
        for rule in sel.get("rule", []):
            picked |= test[rule.split(" & ")].all(axis=1).to_numpy()
        picked_r = test.loc[picked, "r"]
        fold_rows.append({
            "fold": k + 1, "train_n": len(train), "test_start": t0.date(),
            "test_end": test["signal_date"].max().date(), "test_n": len(test),
            "baseline_avg_r": base_test["avg_r"], "rules_tested": len(rules), "rules_picked": len(sel),
            "picked_n": int(picked.sum()), "picked_avg_r": picked_r.mean() if len(picked_r) else np.nan,
        })
        picked_parts.append(pd.DataFrame({"fold": k + 1, "r": picked_r, "lift": picked_r - mu_test}))
        if len(sel):
            rule_parts.append(sel[["rule", "test_n", "test_avg_r", "test_win_rate"]]
                              .assign(fold=k + 1, mu=mu_test))

    pooled = pd.concat(picked_parts) if picked_parts else pd.DataFrame({"r": [], "lift": []})
    lift = stats(pooled["lift"].astype(float))
    summary = {"folds": len(fold_rows), "trades": len(pooled),
               "avg_r": pooled["r"].mean() if len(pooled) else np.nan,
               "win_rate": (pooled["r"] > 0).mean() if len(pooled) else np.nan,
               "lift_r": lift["avg_r"], "t": lift["t"], "p": lift["p"]}
    return {"folds": pd.DataFrame(fold_rows), "rules": _walk_forward_rules(rule_parts, p),
            "summary": summary}


def _walk_forward_rules(parts: list[pd.DataFrame], p: EdgeParams) -> pd.DataFrame:
    cols = ["rule", "wf_folds_picked", "wf_oos_n", "wf_oos_avg_r", "wf_oos_win_rate",
            "wf_oos_lift_r", "wf_folds_beat"]
    if not parts:
        return pd.DataFrame(columns=cols)
    d = pd.concat(parts, ignore_index=True)
    d["w_r"] = d["test_avg_r"].fillna(0) * d["test_n"]
    d["w_win"] = d["test_win_rate"].fillna(0) * d["test_n"]
    d["w_lift"] = (d["test_avg_r"] - d["mu"]).fillna(0) * d["test_n"]
    d["beat"] = (d["test_n"] > 0) & (d["test_avg_r"] >= d["mu"] + p.min_lift_r)
    g = d.groupby("rule", sort=False)
    out = pd.DataFrame({"wf_folds_picked": g.size(), "wf_oos_n": g["test_n"].sum(),
                        "wf_folds_beat": g["beat"].sum()})
    n = out["wf_oos_n"].where(out["wf_oos_n"] > 0)
    out["wf_oos_avg_r"] = g["w_r"].sum() / n
    out["wf_oos_win_rate"] = g["w_win"].sum() / n
    out["wf_oos_lift_r"] = g["w_lift"].sum() / n
    return out.reset_index()[cols]


def attach_walk_forward(rules: pd.DataFrame, wf: dict, p: EdgeParams = EdgeParams()) -> pd.DataFrame:
    """Add the per-rule walk-forward columns and ``wf_confirmed`` to a ``mine_rules`` table."""
    if rules.empty:
        return rules
    out = rules.merge(wf["rules"], on="rule", how="left")
    counts = ["wf_folds_picked", "wf_oos_n", "wf_folds_beat"]
    out[counts] = out[counts].fillna(0).astype(int)
    out["wf_confirmed"] = (out["wf_oos_n"] >= _min_test_n(p)) & (out["wf_oos_lift_r"] >= p.min_lift_r)
    return out


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


def scan(panel: dict[str, pd.DataFrame], rules: pd.DataFrame, cfg_trade, cfg_options=None) -> pd.DataFrame:
    """Apply validated rules to each ticker's latest bar: today's trade candidates.

    Only bars that would have produced a trade in the backtest (an entry trigger) qualify, so
    live candidates are drawn from the same population the rules were measured on.
    """
    from miratrade.backtest import conditions, entry_trigger

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
        cand = {"ticker": t, "date": ind.index[-1].date(), "close": round(px, 2),
                "stop": round(px - cfg_trade.stop_atr * row["atr"], 2),
                "target": round(px + cfg_trade.target_atr * row["atr"], 2),
                "rules_matched": len(hits), "best_rule": best.rule,
                "best_rule_test_avg_r": round(best.test_avg_r, 2),
                "best_rule_wf_confirmed": bool(getattr(best, "wf_confirmed", False))}
        if cfg_options is not None and cfg_options.enabled and np.isfinite(row.get("rv20", np.nan)):
            from miratrade.options_trades import option_contract

            c = option_contract(px, ind.index[-1].date(), row["rv20"], cfg_options)
            cand.update({"call": f"{t} {c['expiry']:%Y-%m-%d} {c['strike']:g}C",
                         "call_delta": round(c["delta"], 2), "call_est_ask": round(c["ask"], 2)})
        out.append(cand)
    return pd.DataFrame(out).sort_values(["rules_matched", "best_rule_test_avg_r"],
                                         ascending=False) if out else pd.DataFrame()
