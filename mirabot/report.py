"""Markdown edge report."""
from __future__ import annotations

import pandas as pd


def _fmt(v, pct=False):
    if pd.isna(v):
        return "–"
    if pct:
        return f"{v:.0%}"
    return f"{v:.2f}" if isinstance(v, float) else str(v)


def _table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_none_\n"
    head = "| " + " | ".join(df.columns) + " |\n|" + "---|" * len(df.columns) + "\n"
    return head + "".join("| " + " | ".join(map(str, r)) + " |\n" for r in df.itertuples(index=False))


def _stat_row(label: str, s: dict) -> list:
    return [label, s["n"], _fmt(s["win_rate"], True), _fmt(s["avg_r"]),
            _fmt(s["profit_factor"]), _fmt(s["t"])]


def _rules_table(v: pd.DataFrame) -> str:
    return _table(pd.DataFrame({
        "rule": v["rule"], "train n": v["train_n"], "train win": v["train_win_rate"].map(lambda x: _fmt(x, True)),
        "train avg R": v["train_avg_r"].round(2), "test n": v["test_n"],
        "test win": v["test_win_rate"].map(lambda x: _fmt(x, True)),
        "test avg R": v["test_avg_r"].round(2), "p (lift, train)": v["train_p"].map(lambda x: f"{x:.3f}"),
    }))


def _options_section(opt: dict, baseline: dict) -> list[str]:
    out = ["\n## Stocks vs. options (long calls)\n",
           "Each signal is also traded as a ~0.65-delta call on the monthly expiry nearest 45 days out, "
           "entered and exited on the stock trade's dates. Contracts are priced with Black-Scholes "
           "(realised vol × 1.15 as implied vol, 2.5% half-spread each side).\n"]
    ob = opt["baseline"]
    closed = opt["trades"][opt["trades"]["exit_reason"] != "open"]
    rows = [["stocks", *(_stat_row("", baseline["all"])[1:])], ["calls", *(_stat_row("", ob["all"])[1:])]]
    tab = pd.DataFrame(rows, columns=["instrument", "trades", "win rate", "avg R", "profit factor", "t"])
    tab["avg return"] = [_fmt(closed["ret"].mean(), True), _fmt(closed["opt_ret"].mean(), True)]
    out.append(_table(tab))
    out.append("\n### Rules that held up for calls\n")
    out.append(_rules_table(opt["shown"]) if not opt["shown"].empty else
               "No rule validated for calls. Stick to shares for these signals.\n")
    return out


def render(trades: pd.DataFrame, rules: pd.DataFrame, shown: pd.DataFrame, baseline: dict,
           scan: pd.DataFrame, meta: dict, opt: dict | None = None) -> str:
    """``rules`` is every rule tested; ``shown`` the pruned validated rules to list; ``opt`` the
    same analysis with each trade expressed as a long call (optional)."""
    out = [f"# MiraBot edge report\n",
           f"Window: **{meta['start']} → {meta['end']}** · universe: {meta['n_tickers']} tickers · "
           f"insider rows: {meta['n_insider']} · unusual option prints: {meta['n_unusual']}\n",
           "Trades enter at the next open after a signal, with a "
           f"{meta['stop_atr']}×ATR stop, {meta['target_atr']}×ATR target and "
           f"{meta['max_hold']}-bar time stop. Results are in R (multiples of initial risk).\n"]

    out.append("## Baseline (every candidate trade)\n")
    cols = ["set", "trades", "win rate", "avg R", "profit factor", "t"]
    base = pd.DataFrame([_stat_row(k, baseline[k]) for k in ("all", "train", "test")], columns=cols)
    out.append(_table(base))
    if baseline.get("cutoff") is not None:
        out.append(f"\nTrain/validate split at {pd.Timestamp(baseline['cutoff']).date()}.\n")

    closed = trades[trades["exit_reason"] != "open"] if not trades.empty else trades
    if not closed.empty:
        out.append("\n## What the winners had in common\n")
        conds = [c for c in closed.columns if ":" in c and closed[c].dtype == bool]
        win = closed["r"] > 0
        rows = []
        for c in conds:
            if closed[c].sum() == 0:
                continue
            rows.append([c, int(closed[c].sum()), _fmt(closed.loc[win, c].mean(), True),
                         _fmt(closed.loc[~win, c].mean(), True),
                         _fmt(closed.loc[closed[c], "r"].mean())])
        tab = pd.DataFrame(rows, columns=["condition", "trades", "% of winners", "% of losers", "avg R"])
        out.append(_table(tab.sort_values("avg R", ascending=False, key=lambda s: pd.to_numeric(s, errors="coerce"))))

        out.append("\n## Top 10 profitable trades\n")
        top = closed.nlargest(10, "r")[["ticker", "entry_date", "exit_date", "entry", "exit",
                                        "r", "exit_reason"]].copy()
        top["entry_date"] = top["entry_date"].dt.date
        top["exit_date"] = top["exit_date"].dt.date
        top["on"] = [" ".join(c for c in conds if closed.at[i, c]) for i in top.index]
        out.append(_table(top.round(2)))

    out.append("\n## The edge: rules that held up out of sample\n")
    if shown.empty:
        out.append("No rule beat the baseline in both the discovery and validation periods. "
                   "That result counts: don't trade a pattern that didn't hold up.\n")
    else:
        out.append(_rules_table(shown))
        out.append(f"\n{len(rules)} rules tested; {int(rules['train_bh_sig'].sum())} significant in "
                   f"the discovery period after the Benjamini-Hochberg correction; "
                   f"{int(rules['validated'].sum())} also beat the baseline by "
                   f"≥{meta['min_lift_r']}R in validation (redundant variants hidden).\n")

    if opt is not None and opt.get("baseline"):
        out.extend(_options_section(opt, baseline))

    out.append("\n## Current candidates (latest bar matches a validated rule)\n")
    out.append(_table(scan) if not scan.empty else "_none today_\n")

    out.append("\n## Caveats\n"
               "- 90 days is one market regime and a small sample. Treat validated rules as "
               "hypotheses to paper-trade, not proven edges.\n"
               "- Insider signals use the **filing** date, not the trade date, so the backtest only "
               "uses information that was public at the time.\n"
               "- Options flow without aggressor side is approximated (calls = bullish, puts = bearish).\n"
               "- No commissions or slippage are modelled; subtract about 0.05R per trade for liquid names.\n"
               "- Option results are **model prices**, not historical quotes. Real implied volatility "
               "often jumps before earnings and falls after; check the live chain (open interest, "
               "spread) before buying a suggested call.\n")
    return "\n".join(out)
