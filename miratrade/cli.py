"""Command line: ``miratrade analyze | snapshot | demo``."""
from __future__ import annotations

import argparse
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from miratrade.backtest import build_panel, run_trades
from miratrade.config import Config
from miratrade.edge import attach_walk_forward, mine_rules, prune_redundant, scan, walk_forward
from miratrade.regimes import regime_baseline, regime_rules
from miratrade.report import render
from miratrade.signals.options_flow import unusual_prints
from miratrade.survivorship import coverage


def pipeline(prices: dict, insiders: pd.DataFrame, flow: pd.DataFrame, start: pd.Timestamp,
             out_dir: Path, cfg: Config = Config(), universe: set[str] | None = None,
             ownership: pd.DataFrame | None = None, short_volume: pd.DataFrame | None = None) -> dict:
    """``universe``: every ticker that should have been tested (default: those with prices), so
    tickers that got no price data can be reported. ``ownership`` (13D/13G) and
    ``short_volume`` (FINRA) add the smart-money conditions when given."""
    panel = build_panel(prices, insiders, flow, cfg, ownership=ownership, short_volume=short_volume)
    trades = run_trades(panel, start=start, cfg=cfg)
    wf = None
    if trades.empty:
        rules, baseline = pd.DataFrame(), None
    else:
        rules, baseline = mine_rules(trades, cfg.edge)
        wf = walk_forward(trades, cfg.edge)
        rules = attach_walk_forward(rules, wf, cfg.edge)
    candidates = scan(panel, rules, cfg.trade, cfg.options) if not rules.empty else pd.DataFrame()
    opt = None
    if cfg.options.enabled and "opt_r" in trades:
        opt_trades = trades.dropna(subset=["opt_r"]).assign(r=lambda d: d["opt_r"])
        opt_rules, opt_base = mine_rules(opt_trades, cfg.edge)
        opt_shown = (prune_redundant(opt_rules[opt_rules["validated"]], top=10)
                     if not opt_rules.empty and opt_rules["validated"].any() else pd.DataFrame())
        opt = {"trades": opt_trades, "rules": opt_rules, "shown": opt_shown, "baseline": opt_base}

    out_dir.mkdir(parents=True, exist_ok=True)
    trades.to_csv(out_dir / "trades.csv", index=False)
    rules.to_csv(out_dir / "rules.csv", index=False)
    if opt is not None:
        opt["rules"].to_csv(out_dir / "rules_options.csv", index=False)
    candidates.to_csv(out_dir / "candidates.csv", index=False)
    if wf is not None:
        wf["folds"].to_csv(out_dir / "walk_forward.csv", index=False)
    surv = coverage(universe if universe is not None else set(prices), prices, panel, insiders, flow,
                    trades, start, cfg)
    profiles = None
    if cfg.outcomes.enabled:
        from miratrade.outcomes import build_outcomes, mine_profiles, summarize

        events = build_outcomes(panel, cfg, start)
        if len(events):
            profiles = {"summary": summarize(events, cfg), "mined": mine_profiles(events, cfg), "events": events}
            events.to_csv(out_dir / "events.csv", index=False)
            profiles["summary"].to_csv(out_dir / "profiles.csv", index=False)
            mined = [m["rules"].assign(variant=v) for v, m in profiles["mined"].items() if not m["rules"].empty]
            (pd.concat(mined, ignore_index=True) if mined else pd.DataFrame()).to_csv(
                out_dir / "profile_rules.csv", index=False)
    if baseline is None:
        (out_dir / "edge_report.md").write_text("# MiraTrade edge report\n\nNo trades generated.\n", encoding="utf-8")
        return {"trades": trades, "rules": rules, "candidates": candidates}
    end = max(df.index[-1] for df in panel.values())
    meta = {"start": start.date(), "end": end.date(), "n_tickers": len(panel),
            "n_insider": len(insiders), "n_unusual": len(unusual_prints(flow, cfg.flow)),
            "n_ownership": 0 if ownership is None else len(ownership),
            "stop_atr": cfg.trade.stop_atr, "target_atr": cfg.trade.target_atr,
            "max_hold": cfg.trade.max_hold_days, "min_lift_r": cfg.edge.min_lift_r,
            "min_trades": cfg.edge.min_trades}
    validated = rules[rules["validated"]] if not rules.empty else rules
    shown = prune_redundant(validated, top=10) if len(validated) else validated
    regimes = {"baseline": regime_baseline(trades),
               "rules": regime_rules(trades, shown) if len(shown) else pd.DataFrame()}
    report = render(trades, rules, shown, baseline, candidates, meta, opt, wf, regimes, surv, profiles)
    (out_dir / "edge_report.md").write_text(report, encoding="utf-8")
    return {"trades": trades, "rules": rules, "candidates": candidates, "report": report,
            "options": opt, "walk_forward": wf, "regimes": regimes, "survivorship": surv, "profiles": profiles}


def cmd_analyze(a) -> None:
    from miratrade.data.options import FLOW_COLUMNS, load_flow_csv
    from miratrade.data.prices import load_prices, load_prices_csv
    from miratrade.data.sec import clean_insiders, fetch_insiders

    end = date.fromisoformat(a.end) if a.end else date.today()
    start = end - timedelta(days=a.days)
    cfg = Config()

    if a.insiders_csv:
        insiders = pd.read_csv(a.insiders_csv, parse_dates=["filing_date", "trade_date"])
    else:
        print(f"Fetching SEC Form 4 filings {start} → {end} …")
        insiders = fetch_insiders(start, end)
    flow = load_flow_csv(a.flow) if a.flow else pd.DataFrame(columns=FLOW_COLUMNS)
    insiders, dropped = clean_insiders(insiders)
    print(f"  dropped insider rows: {dropped['placeholder_ticker']} placeholder tickers, "
          f"{dropped['fund_ticker']} mutual funds, {dropped['total_as_price']} with the total typed as price")

    buys = insiders[(insiders["code"] == "P") & (insiders["value"] >= cfg.insider.min_value_usd)]
    ranked = buys.assign(value=buys["value"].clip(upper=cfg.insider.rank_cap_usd))
    universe = set(ranked.groupby("ticker")["value"].sum().nlargest(a.max_insider_tickers).index)
    universe |= set(unusual_prints(flow, cfg.flow)["ticker"].unique())
    universe |= set(a.tickers or []) | {"SPY"}

    ownership = short_volume = None
    if not a.no_smart_money:
        from miratrade.data.finra import fetch_short_volume
        from miratrade.data.ownership import cik_ticker_map, fetch_ownership
        from miratrade.data.sec import SecClient

        client = SecClient()
        print(f"Fetching 13D/13G filings {start} → {end} …")
        ownership, stats = fetch_ownership(start - timedelta(days=cfg.smart.lookback_days), end,
                                           cik_ticker_map(client, insiders), client,
                                           passive_filers=cfg.smart.passive_filers)
        print(f"  {stats['resolved']} of {stats['filings']} filings matched to a ticker "
              f"({stats['unresolved']} private or unknown issuers, {stats['ambiguous']} needed a header)")
        new_13d = ownership[(ownership["kind"] == "13D") & ~ownership["amendment"]]
        universe |= set(new_13d["ticker"].value_counts().head(a.max_13d_tickers).index)
        print(f"Fetching FINRA short volume for {len(universe)} tickers …")
        # 60 extra calendar days so the short-ratio z-score has history at the window start.
        short_volume = fetch_short_volume(start - timedelta(days=60), end, tickers=universe)

    if a.prices_dir:
        prices = load_prices_csv(Path(a.prices_dir))
    else:
        print(f"Loading prices for {len(universe)} tickers …")
        # 300 extra calendar days so 200-day averages exist at the window start.
        prices = load_prices(sorted(universe), start - timedelta(days=300), end + timedelta(days=1))
    res = pipeline(prices, insiders, flow, pd.Timestamp(start), Path(a.out), cfg, universe=universe,
                   ownership=ownership, short_volume=short_volume)
    print(res.get("report", "No trades generated."))
    print(f"\nWrote {a.out}/edge_report.md, trades.csv, rules.csv, candidates.csv, walk_forward.csv")


def cmd_snapshot(a) -> None:
    from miratrade.data.options import snapshot_cboe

    df = snapshot_cboe(a.tickers)
    print(f"Saved {len(df)} option rows for {df['ticker'].nunique() if len(df) else 0} tickers.")


def cmd_demo(a) -> None:
    from miratrade.synthetic import make_market

    prices, insiders, flow = make_market()
    start = prices["SPY"].index[-90]
    res = pipeline(prices, insiders, flow, start, Path(a.out))
    print(res["report"])


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="miratrade", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    an = sub.add_parser("analyze", help="backtest the last N days and mine an edge")
    an.add_argument("--days", type=int, default=90)
    an.add_argument("--end", help="YYYY-MM-DD (default today)")
    an.add_argument("--tickers", nargs="*", help="extra tickers to include (swing universe)")
    an.add_argument("--flow", help="options-flow CSV file or directory")
    an.add_argument("--insiders-csv", help="pre-downloaded insider CSV (skip SEC fetch)")
    an.add_argument("--prices-dir", help="directory of <TICKER>.csv OHLCV files (skip download)")
    an.add_argument("--max-insider-tickers", type=int, default=150)
    an.add_argument("--max-13d-tickers", type=int, default=100,
                    help="add up to this many companies with new 13D filings to the universe")
    an.add_argument("--no-smart-money", action="store_true",
                    help="skip 13D/13G and FINRA short-volume data")
    an.add_argument("--out", default="reports")
    an.set_defaults(func=cmd_analyze)

    sn = sub.add_parser("snapshot", help="save today's CBOE option chains to .cache/flow")
    sn.add_argument("tickers", nargs="+")
    sn.set_defaults(func=cmd_snapshot)

    de = sub.add_parser("demo", help="run the full pipeline on synthetic data with a planted edge")
    de.add_argument("--out", default="reports/demo")
    de.set_defaults(func=cmd_demo)

    from miratrade.massive_cli import add_parser as add_massive
    add_massive(sub)

    try:                                    # needs the [schwab] extra
        from miratrade.broker_cli import add_parser as add_schwab
        add_schwab(sub)
    except ImportError:
        pass

    a = ap.parse_args(argv)
    a.func(a)


if __name__ == "__main__":
    main()
