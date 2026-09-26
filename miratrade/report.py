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
    tab = pd.DataFrame({
        "rule": v["rule"], "train n": v["train_n"], "train win": v["train_win_rate"].map(lambda x: _fmt(x, True)),
        "train avg R": v["train_avg_r"].round(2), "test n": v["test_n"],
        "test win": v["test_win_rate"].map(lambda x: _fmt(x, True)),
        "test avg R": v["test_avg_r"].round(2), "p (lift, train)": v["train_p"].map(lambda x: f"{x:.3f}"),
    })
    if "wf_oos_n" in v:
        tab["WF folds"] = [f"{b}/{a}" for a, b in zip(v["wf_folds_picked"], v["wf_folds_beat"])]
        tab["WF n"] = v["wf_oos_n"]
        tab["WF avg R"] = v["wf_oos_avg_r"].map(_fmt)
    return _table(tab)


def _walk_forward_section(wf: dict, min_lift_r: float) -> list[str]:
    out = ["\n## Walk-forward validation\n",
           "The whole discovery step is re-run on an expanding window: each fold mines rules only on "
           "trades that had closed before it starts, then measures the rules it picked on the next "
           "slice. This is the honest estimate of what the rule-mining process delivers on unseen data.\n"]
    folds = wf["folds"]
    if folds.empty:
        return out + ["Not enough closed trades for walk-forward folds.\n"]
    tab = folds.copy()
    for c in ("baseline_avg_r", "picked_avg_r"):
        tab[c] = tab[c].map(_fmt)
    out.append(_table(tab.rename(columns={
        "fold": "fold", "train_n": "train trades", "test_start": "test from", "test_end": "test to",
        "test_n": "test trades", "baseline_avg_r": "baseline avg R", "rules_tested": "rules tested",
        "rules_picked": "rules picked", "picked_n": "picked trades", "picked_avg_r": "picked avg R"})))
    s = wf["summary"]
    if s["trades"] == 0:
        out.append("\nNo fold picked a rule, so there is nothing to trade out of sample. Either there is "
                   "no stable edge in these signals, or each fold has too few trades to show one; a "
                   "longer window (`--days`) tells the two apart.\n")
    else:
        verdict = ("held up" if s["lift_r"] >= min_lift_r and s["p"] < 0.05
                   else "did **not** clearly beat the baseline")
        out.append(f"\nPooled out of sample, the picked rules took **{s['trades']} trades**: win rate "
                   f"{_fmt(s['win_rate'], True)}, avg {_fmt(s['avg_r'])}R, lift over each slice's baseline "
                   f"{_fmt(s['lift_r'])}R (t = {_fmt(s['t'])}, p = {s['p']:.3f}). The process {verdict}.\n")
    out.append("\n`WF folds` in the rule tables reads *folds where the rule beat the baseline / "
               "folds where it was picked*; `WF n` and `WF avg R` are its trades in those folds.\n")
    return out


def _regime_section(base: pd.DataFrame, by_rule: pd.DataFrame, min_trades: int) -> list[str]:
    from miratrade.regimes import TRENDS, VOLS

    out = ["\n## Results by market regime\n",
           "Regime on the signal date, using SPY: **bull** = SPY and its 50-day average above the "
           "200-day, **bear** = both below, **sideways** = mixed. **high_vol / low_vol** = SPY's "
           "20-day realised volatility above / below its one-year median.\n"]
    if base.empty:
        return out + ["No SPY data, so regimes are unknown.\n"]
    tab = base.assign(**{"win rate": base["win_rate"].map(lambda x: _fmt(x, True)),
                         "avg R": base["avg_r"].map(_fmt), "profit factor": base["profit_factor"].map(_fmt)})
    out.append(_table(tab[["dimension", "regime", "n", "win rate", "avg R", "profit factor"]]
                      .rename(columns={"n": "trades"})))
    trends = base[(base["dimension"] == "mkt_trend") & (base["n"] >= min_trades)]
    if len(trends) < 2:
        out.append("\n**Only one trend regime has enough trades.** Nothing here shows whether the "
                   "results carry over to a different market; widen the window.\n")
    if not by_rule.empty:
        out.append("\n### Validated rules by regime (avg R, trades)\n")
        rows = {"rule": by_rule["rule"]}
        for label in (*TRENDS, *VOLS):
            rows[label] = [f"{_fmt(r)} ({n})" if n else "–"
                           for r, n in zip(by_rule[f"{label}_avg_r"], by_rule[f"{label}_n"])]
        out.append(_table(pd.DataFrame(rows)))
        out.append(f"\nRegimes with fewer than {min_trades} trades for a rule are anecdotes, not evidence.\n")
    return out


def _survivorship_section(s: dict) -> list[str]:
    out = ["\n## Survivorship and data coverage\n",
           f"{s['traded']} of {s['universe']} tickers in the universe were backtested."]
    if s["missing"]:
        out.append(f" **{len(s['missing'])} had no price data** (often delisted, acquired or renamed): "
                   f"{', '.join(s['missing'][:20])}{' …' if len(s['missing']) > 20 else ''}.")
    if s["short"]:
        out.append(f" {len(s['short'])} had too short a history: {', '.join(s['short'][:20])}.")
    out.append("\n")
    if not (s["missing"] or s["short"]):
        out.append("No ticker was lost for lack of price data.\n")
    elif s["insider_buys"] or s["unusual_prints"]:
        out.append(f"\nSignals lost with them: {s['lost_insider_buys']} of {s['insider_buys']} insider buys "
                   f"(${s['lost_insider_value']:,.0f}) and {s['lost_unusual_prints']} of "
                   f"{s['unusual_prints']} unusual option prints. Stocks that stop trading are more often "
                   "losers than winners, so the more signals are lost, the more flattering the results.\n")
    if s["delisted"]:
        avg = f", avg {_fmt(s['delisted_avg_r'])}R" if s["delisted_trades"] else ""
        out.append(f"\n{len(s['delisted'])} tickers stopped trading inside the window "
                   f"({', '.join(s['delisted'][:20])}). Trades still open on their last bar are closed "
                   f"there with a {s['haircut']:.0%} haircut and **kept** in the statistics "
                   f"({s['delisted_trades']} trades{avg}).\n")
    return out


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


def _profiles_section(profiles: dict) -> list[str]:
    from miratrade.edge import prune_redundant

    out = ["## High profit: which events reached the target first\n",
           "Every event (new insider buy, bullish unusual flow, new 13D / active 13G; repeats on a ticker "
           "within 20 sessions count once) is entered at the next open and measured under each profile: "
           "the shares over 12 months, and ~0.65-delta calls at 30/45/60 days (modelled prices, held ≤ 20 "
           "sessions). Target / stop pairs: +30/−20, +40/−25, +50/−30 %.\n"]
    s = profiles["summary"]
    tab = pd.DataFrame({"profile": s["variant"], "events": s["events"],
                        "target first": s["target_first"].map(lambda x: _fmt(x, True)),
                        "stop first": s["stop_first"].map(lambda x: _fmt(x, True)),
                        "mean return": s["mean_return"].map(lambda x: _fmt(x, True)), "t": s["t"].map(_fmt)})
    out.append(_table(tab))
    out.append("\n### Rules that picked better-than-average events (both periods, split false-discovery rate)\n")
    any_rule = False
    for v, m in profiles["mined"].items():
        r = m["rules"]
        if r.empty or not r["validated"].any():
            continue
        any_rule = True
        shown = prune_redundant(r[r["validated"]], top=5)
        wf_note = f" · walk-forward pooled lift {_fmt(m['wf']['summary']['lift_r'], True)}" if m["wf"]["summary"]["trades"] else ""
        out.append(f"\n**{v}** (average event {_fmt(m['baseline']['all']['avg_r'], True)}{wf_note})\n")
        out.append(_table(pd.DataFrame({
            "rule": shown["rule"], "discovery n": shown["train_n"],
            "discovery return": shown["train_avg_r"].map(lambda x: _fmt(x, True)),
            "validation n": shown["test_n"], "validation return": shown["test_avg_r"].map(lambda x: _fmt(x, True)),
            "WF n": shown.get("wf_oos_n", 0), "WF confirmed": shown.get("wf_confirmed", False)})))
    if not any_rule:
        out.append("No rule picked out events that beat the average event in both periods, for any profile. "
                   "Nothing here is an edge yet.\n")
    return out


def render(trades: pd.DataFrame, rules: pd.DataFrame, shown: pd.DataFrame, baseline: dict,
           scan: pd.DataFrame, meta: dict, opt: dict | None = None, wf: dict | None = None,
           regimes: dict | None = None, survivorship: dict | None = None, profiles: dict | None = None) -> str:
    """``rules`` is every rule tested; ``shown`` the pruned validated rules to list; ``opt`` the
    same analysis with each trade expressed as a long call; ``wf`` the walk-forward result;
    ``regimes`` the ``baseline``/``rules`` regime tables; ``survivorship`` the coverage summary;
    ``profiles`` the high-profit profiles per event (all optional)."""
    out = [f"# MiraTrade edge report\n",
           f"Window: **{meta['start']} → {meta['end']}** · universe: {meta['n_tickers']} tickers · "
           f"insider rows: {meta['n_insider']} · unusual option prints: {meta['n_unusual']} · "
           f"13D/13G filings: {meta.get('n_ownership', 0)}\n",
           "Trades enter at the next open after a signal, with a "
           f"{meta['stop_atr']}×ATR stop, {meta['target_atr']}×ATR target and "
           f"{meta['max_hold']}-bar time stop. Results are in R (multiples of initial risk).\n"]

    if profiles is not None:
        out.extend(_profiles_section(profiles))
        out.append("\n---\n\n# Swing trades in R (ATR bracket, 15 sessions)\n")

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
        if "wf_confirmed" in shown:
            out.append(f"{int(shown['wf_confirmed'].sum())} of the {len(shown)} listed rules are also "
                       f"confirmed by walk-forward validation.\n")

    if wf is not None:
        out.extend(_walk_forward_section(wf, meta["min_lift_r"]))
    if regimes is not None:
        out.extend(_regime_section(regimes["baseline"], regimes["rules"], meta.get("min_trades", 12)))
    if survivorship is not None:
        out.extend(_survivorship_section(survivorship))

    if opt is not None and opt.get("baseline"):
        out.extend(_options_section(opt, baseline))

    out.append("\n## Current candidates (latest bar matches a validated rule)\n")
    out.append(_table(scan) if not scan.empty else "_none today_\n")

    out.append("\n## Caveats\n"
               "- A short window is a small sample and usually a single regime (see the regime "
               "table). Treat validated rules as hypotheses to paper-trade, not proven edges.\n"
               "- Price data comes from free sources that drop most delisted tickers; the coverage "
               "section shows how much was lost. Extra tickers passed with `--tickers` are today's "
               "names and carry survivorship bias.\n"
               "- Insider signals use the **filing** date, not the trade date, so the backtest only "
               "uses information that was public at the time.\n"
               "- Options flow without aggressor side is approximated (calls = bullish, puts = bearish).\n"
               "- No commissions or slippage are modelled; subtract about 0.05R per trade for liquid names.\n"
               "- Option results are **model prices**, not historical quotes. Real implied volatility "
               "often jumps before earnings and falls after; check the live chain (open interest, "
               "spread) before buying a suggested call.\n")
    return "\n".join(out)
