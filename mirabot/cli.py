"""Command line: ``mirabot analyze | snapshot | demo``."""
from __future__ import annotations

import argparse
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from mirabot.backtest import build_panel, run_trades
from mirabot.config import Config
from mirabot.edge import mine_rules, prune_redundant, scan
from mirabot.report import render
from mirabot.signals.options_flow import unusual_prints


def pipeline(prices: dict, insiders: pd.DataFrame, flow: pd.DataFrame, start: pd.Timestamp,
             out_dir: Path, cfg: Config = Config()) -> dict:
    panel = build_panel(prices, insiders, flow, cfg)
    trades = run_trades(panel, start=start, cfg=cfg)
    if trades.empty:
        rules, baseline = pd.DataFrame(), None
    else:
        rules, baseline = mine_rules(trades, cfg.edge)
    candidates = scan(panel, rules, cfg.trade) if not rules.empty else pd.DataFrame()

    out_dir.mkdir(parents=True, exist_ok=True)
    trades.to_csv(out_dir / "trades.csv", index=False)
    rules.to_csv(out_dir / "rules.csv", index=False)
    candidates.to_csv(out_dir / "candidates.csv", index=False)
    if baseline is None:
        (out_dir / "edge_report.md").write_text("# MiraBot edge report\n\nNo trades generated.\n")
        return {"trades": trades, "rules": rules, "candidates": candidates}
    end = max(df.index[-1] for df in panel.values())
    meta = {"start": start.date(), "end": end.date(), "n_tickers": len(panel),
            "n_insider": len(insiders), "n_unusual": len(unusual_prints(flow, cfg.flow)),
            "stop_atr": cfg.trade.stop_atr, "target_atr": cfg.trade.target_atr,
            "max_hold": cfg.trade.max_hold_days, "min_lift_r": cfg.edge.min_lift_r}
    validated = rules[rules["validated"]] if not rules.empty else rules
    shown = prune_redundant(validated, top=10) if len(validated) else validated
    report = render(trades, rules, shown, baseline, candidates, meta)
    (out_dir / "edge_report.md").write_text(report)
    return {"trades": trades, "rules": rules, "candidates": candidates, "report": report}


def cmd_analyze(a) -> None:
    from mirabot.data.options import FLOW_COLUMNS, load_flow_csv
    from mirabot.data.prices import load_prices, load_prices_csv
    from mirabot.data.sec import fetch_insiders

    end = date.fromisoformat(a.end) if a.end else date.today()
    start = end - timedelta(days=a.days)
    cfg = Config()

    if a.insiders_csv:
        insiders = pd.read_csv(a.insiders_csv, parse_dates=["filing_date", "trade_date"])
    else:
        print(f"Fetching SEC Form 4 filings {start} → {end} …")
        insiders = fetch_insiders(start, end)
    flow = load_flow_csv(a.flow) if a.flow else pd.DataFrame(columns=FLOW_COLUMNS)

    buys = insiders[(insiders["code"] == "P") & (insiders["value"] >= cfg.insider.min_value_usd)]
    universe = set(buys.groupby("ticker")["value"].sum().nlargest(a.max_insider_tickers).index)
    universe |= set(unusual_prints(flow, cfg.flow)["ticker"].unique())
    universe |= set(a.tickers or []) | {"SPY"}

    if a.prices_dir:
        prices = load_prices_csv(Path(a.prices_dir))
    else:
        print(f"Loading prices for {len(universe)} tickers …")
        # 300 extra calendar days so 200-day averages exist at the window start.
        prices = load_prices(sorted(universe), start - timedelta(days=300), end + timedelta(days=1))
    res = pipeline(prices, insiders, flow, pd.Timestamp(start), Path(a.out), cfg)
    print(res.get("report", "No trades generated."))
    print(f"\nWrote {a.out}/edge_report.md, trades.csv, rules.csv, candidates.csv")


def cmd_snapshot(a) -> None:
    from mirabot.data.options import snapshot_cboe

    df = snapshot_cboe(a.tickers)
    print(f"Saved {len(df)} option rows for {df['ticker'].nunique() if len(df) else 0} tickers.")


def cmd_demo(a) -> None:
    from mirabot.synthetic import make_market

    prices, insiders, flow = make_market()
    start = prices["SPY"].index[-90]
    res = pipeline(prices, insiders, flow, start, Path(a.out))
    print(res["report"])


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="mirabot", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    an = sub.add_parser("analyze", help="backtest the last N days and mine an edge")
    an.add_argument("--days", type=int, default=90)
    an.add_argument("--end", help="YYYY-MM-DD (default today)")
    an.add_argument("--tickers", nargs="*", help="extra tickers to include (swing universe)")
    an.add_argument("--flow", help="options-flow CSV file or directory")
    an.add_argument("--insiders-csv", help="pre-downloaded insider CSV (skip SEC fetch)")
    an.add_argument("--prices-dir", help="directory of <TICKER>.csv OHLCV files (skip download)")
    an.add_argument("--max-insider-tickers", type=int, default=150)
    an.add_argument("--out", default="reports")
    an.set_defaults(func=cmd_analyze)

    sn = sub.add_parser("snapshot", help="save today's CBOE option chains to .cache/flow")
    sn.add_argument("tickers", nargs="+")
    sn.set_defaults(func=cmd_snapshot)

    de = sub.add_parser("demo", help="run the full pipeline on synthetic data with a planted edge")
    de.add_argument("--out", default="reports/demo")
    de.set_defaults(func=cmd_demo)

    a = ap.parse_args(argv)
    a.func(a)


if __name__ == "__main__":
    main()
