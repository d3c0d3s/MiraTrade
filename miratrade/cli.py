"""Command line: ``miratrade analyze | snapshot | demo``."""
from __future__ import annotations

import argparse
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from miratrade.backtest import build_panel, run_trades
from miratrade.config import CAP_TIERS, Config, load_user_config
from miratrade.edge import attach_walk_forward, mine_rules, prune_redundant, scan, walk_forward
from miratrade.regimes import regime_baseline, regime_rules
from miratrade.report import render
from miratrade.signals.options_flow import unusual_prints
from miratrade.survivorship import coverage


def pipeline(prices: dict, insiders: pd.DataFrame, flow: pd.DataFrame, start: pd.Timestamp,
             out_dir: Path, cfg: Config = Config(), universe: set[str] | None = None,
             ownership: pd.DataFrame | None = None, short_volume: pd.DataFrame | None = None,
             shares: pd.DataFrame | None = None) -> dict:
    """``universe``: every ticker that should have been tested (default: those with prices), so
    tickers that got no price data can be reported. ``ownership`` (13D/13G) and
    ``short_volume`` (FINRA) add the smart-money conditions when given."""
    panel = build_panel(prices, insiders, flow, cfg, ownership=ownership, short_volume=short_volume, shares=shares)
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


def load_inputs(days: int, end: date | None = None, max_insider_tickers: int = 150, max_13d_tickers: int = 100,
                tickers: list[str] | None = None, flow_path: str | None = None, insiders_csv: str | None = None,
                prices_dir: str | None = None, smart_money: bool = True, cfg: Config = Config(),
                fundamentals: bool = True, cap_tier: str | None = None,
                universe_cutoff: date | None = None) -> dict:
    """Everything an analysis reads, downloaded or taken from the cache: the same inputs for
    ``analyze`` and ``experiment``."""
    from miratrade.data.options import FLOW_COLUMNS, load_flow_csv
    from miratrade.data.prices import load_prices, load_prices_csv
    from miratrade.data.sec import clean_insiders, fetch_insiders

    end = end or date.today()
    start = end - timedelta(days=days)

    if insiders_csv:
        insiders = pd.read_csv(insiders_csv, parse_dates=["filing_date", "trade_date"])
    else:
        print(f"Fetching SEC Form 4 filings {start} → {end} …")
        insiders = fetch_insiders(start, end)
    flow = load_flow_csv(flow_path) if flow_path else pd.DataFrame(columns=FLOW_COLUMNS)
    insiders, dropped = clean_insiders(insiders)
    print(f"  dropped insider rows: {dropped['placeholder_ticker']} placeholder tickers, "
          f"{dropped['fund_ticker']} mutual funds, {dropped['total_as_price']} with the total typed as price")

    buys = insiders[(insiders["code"] == "P") & (insiders["value"] >= cfg.insider.min_value_usd)]
    if universe_cutoff is not None:
        # Ranking companies over the whole window would let the confirmation period pick the
        # universe it is then judged on; only filings before the cut may choose it.
        buys = buys[pd.to_datetime(buys["filing_date"]).dt.date < universe_cutoff]
        print(f"  universe ranked on filings before {universe_cutoff} ({len(buys)} buys)")
    ranked = buys.assign(value=buys["value"].clip(upper=cfg.insider.rank_cap_usd))
    universe = set(ranked.groupby("ticker")["value"].sum().nlargest(max_insider_tickers).index)
    universe |= set(unusual_prints(flow, cfg.flow)["ticker"].unique())
    universe |= set(tickers or []) | {"SPY"}

    ownership = short_volume = None
    if smart_money:
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
        universe |= set(new_13d["ticker"].value_counts().head(max_13d_tickers).index)
        print(f"Fetching FINRA short volume for {len(universe)} tickers …")
        # 60 extra calendar days so the short-ratio z-score has history at the window start.
        short_volume = fetch_short_volume(start - timedelta(days=60), end, tickers=universe)

    shares = None
    if fundamentals:
        import json

        from miratrade.data.fundamentals import (cap_from_filings, fetch_shares, filter_by_tier, ticker_ciks,
                                                 tier_report)
        from miratrade.data.sec import SecClient

        client = SecClient()
        ciks = ticker_ciks(insiders, json.loads(client.get("https://www.sec.gov/files/company_tickers.json",
                                                           max_age_days=7)), ownership)
        print(f"Fetching shares outstanding (SEC XBRL) for {len(universe)} tickers …")
        shares = fetch_shares(universe, ciks, client)
        print(f"  {shares['ticker'].nunique()} with shares outstanding (funds and some foreign filers have none)")
        # Size filter before the prices: that is what saves the download and the simulation.
        tier = cap_tier or cfg.data.cap_tier
        if tier != "all":
            universe, stats = filter_by_tier(universe - {"SPY"}, cap_from_filings(insiders, shares), tier)
            universe |= {"SPY"}
            print("  " + tier_report(stats, tier))

    if prices_dir:
        prices = load_prices_csv(Path(prices_dir))
    else:
        print(f"Loading prices for {len(universe)} tickers …")
        # 300 extra calendar days so 200-day averages exist at the window start.
        prices = load_prices(sorted(universe), start - timedelta(days=300), end + timedelta(days=1))
    return {"prices": prices, "insiders": insiders, "flow": flow, "ownership": ownership,
            "short_volume": short_volume, "shares": shares, "universe": universe, "start": start, "end": end}


def record_attempt(cfg: Config, kind: str, days: int | None = None) -> str:
    """Remember this configuration and say what the count means, under the report.

    Directly under the numbers on purpose. A backtest that finds a rule is only as good as the
    number of different rule sets it was chosen from, and that number belongs beside the result
    rather than in a place somebody has to think to look.
    """
    try:
        from miratrade import attempts, store

        db = store.connect()
        try:
            total, _fresh = attempts.record(db, cfg, kind, days=days)
        finally:
            db.close()
        return attempts.say(total)
    except Exception as e:              # counting must never be the reason an analysis fails
        return f"(could not record the attempt: {e})"


def cmd_analyze(a) -> None:
    cfg = load_user_config()
    end = date.fromisoformat(a.end) if a.end else None
    if getattr(a, "offline", False):
        # The same analysis over data already downloaded. Retuning a rule should cost the
        # simulation, not the download; see miratrade/reprocess.py.
        from miratrade import store
        from miratrade.reprocess import stored_inputs

        db = store.connect()
        try:
            print(f"Reading {a.days} days out of the store. Nothing is downloaded.")
            inp = stored_inputs(db, a.days, end, cfg, a.max_insider_tickers, a.max_13d_tickers,
                                cap_tier=a.cap)
        finally:
            db.close()
    else:
        inp = load_inputs(a.days, end, a.max_insider_tickers, a.max_13d_tickers, a.tickers, a.flow,
                          a.insiders_csv, a.prices_dir, not a.no_smart_money, cfg, cap_tier=a.cap)
    res = pipeline(inp["prices"], inp["insiders"], inp["flow"], pd.Timestamp(inp["start"]), Path(a.out), cfg,
                   universe=inp["universe"], ownership=inp["ownership"], short_volume=inp["short_volume"],
                   shares=inp["shares"])
    print(res.get("report", "No trades generated."))
    print(f"\nWrote {a.out}/edge_report.md, trades.csv, rules.csv, candidates.csv, walk_forward.csv")
    print("\n" + record_attempt(cfg, "analysis", a.days))


def cmd_experiment(a) -> None:
    from miratrade.data.issuers import classify_by_index, fetch_fund_ciks, issuer_table
    from miratrade.data.sec import SecClient
    from miratrade.experiments import extract_events, report, run_grid

    cfg = Config()
    end_date = date.fromisoformat(a.end) if a.end else date.today()
    span = timedelta(days=a.days)
    universe_cut = None if a.lookahead_universe else end_date - span + span * cfg.experiment.train_fraction
    inp = load_inputs(a.days, date.fromisoformat(a.end) if a.end else None, a.max_insider_tickers,
                      a.max_13d_tickers, flow_path=a.flow, smart_money=not a.no_smart_money, cfg=cfg,
                      cap_tier=a.cap, universe_cutoff=universe_cut)
    print("Building the panel …")
    panel = build_panel(inp["prices"], inp["insiders"], inp["flow"], cfg, ownership=inp["ownership"],
                        short_volume=inp["short_volume"], shares=inp["shares"])
    print("Classifying issuers (funds, ETF, BDC, SPAC) from the EDGAR index …")
    iss = issuer_table(inp["insiders"], panel)
    if inp["ownership"] is not None and len(inp["ownership"]):
        own = inp["ownership"].rename(columns={"subject_cik": "issuer_cik"}).assign(issuer="")
        own = own[~own["ticker"].isin(iss["ticker"]) & own["ticker"].isin(panel)][["ticker", "issuer_cik", "issuer"]]
        iss = pd.concat([iss, own.drop_duplicates("ticker")], ignore_index=True)
    kinds = classify_by_index(iss, fetch_fund_ciks(SecClient(), range(inp["start"].year, inp["end"].year + 1)))
    events = extract_events(panel, cfg, pd.Timestamp(inp["start"]), inp["insiders"],
                            dict(zip(kinds["ticker"], kinds["kind"])))
    print(f"{len(events)} events; simulating the grid …")
    trades = run_grid(panel, events, cfg)
    md, summary = report(trades, events, cfg, {"start": inp["start"], "end": inp["end"]})
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "experiments.md").write_text(md, encoding="utf-8")
    summary.to_csv(out / "experiments_summary.csv", index=False)
    events.to_csv(out / "experiment_events.csv", index=False)
    kinds.to_csv(out / "issuers.csv", index=False)
    print(md)
    print(f"\nWrote {out}/experiments.md, experiments_summary.csv, experiment_events.csv, issuers.csv")


def cmd_snapshot(a) -> None:
    from miratrade.config import load_user_config
    from miratrade.data.options import snapshot_broker, snapshot_cboe

    source = a.source or load_user_config().data.quote_broker
    from miratrade.flow import flow_universe

    tickers = flow_universe(a.tickers, a.from_events, a.limit)
    if not tickers:
        raise SystemExit("No tickers to snapshot: name them, or run `miratrade scan` first so "
                         "--from-events has something to work from.")
    print(f"Option chains for {len(tickers)} tickers from {source}: {', '.join(tickers[:12])}"
          + (" …" if len(tickers) > 12 else ""))
    if source == "cboe":
        df = snapshot_cboe(tickers)                     # research only: refuses unless enabled
    elif source == "etrade":
        from miratrade.brokers.etrade import EtradeBroker
        df = snapshot_broker(tickers, EtradeBroker())
    else:
        from miratrade.brokers.schwab import SchwabBroker
        df = snapshot_broker(tickers, SchwabBroker())
    print(f"Stored {len(df)} option rows for {df['ticker'].nunique() if len(df) else 0} tickers "
          f"({source}). This only accumulates forward — run it once a day after the close.")


def cmd_scan(a) -> None:
    from miratrade.config import APP_DIR, CACHE_DIR
    from miratrade.scan import (EVENT_LABELS, evidence, latest_history_report, load_history, run_scan,
                                save_scan, store_scan, variant_label)

    report = Path(a.report) if a.report else latest_history_report(Path("reports"))
    history, rules = load_history(report) if report else (pd.DataFrame(), pd.DataFrame())
    res = run_scan(days=a.days, flow_dir=Path(a.flow) if a.flow else CACHE_DIR / "flow",
                   smart_money=not a.no_smart_money, cap_tier=a.cap)
    save_scan(res, Path(a.save) if a.save else APP_DIR / "scan")
    written = store_scan(res)      # the shared database is what the screens filter on, and what
    print(f"  stored: {written['events']} events, {written['prices']} price bars")   # another app reads
    try:                           # a scan is what produces new events, so this is where they are
        from miratrade.notify import notify_new          # announced; never twice for the same one

        notify_new(cfg=load_user_config(), reports_dir=Path("reports"), log=print)
    except Exception as e:         # a notification must never be the reason a scan looks failed
        print(f"  notify failed: {e}")
    print(f"\nEvidencia: {report or 'sin reporte con events.csv'} · perfil {variant_label(a.variant)}\n")
    for ev in res["events"].to_dict("records"):
        kinds = ", ".join(v for k, v in EVENT_LABELS.items() if ev.get(k))
        e = evidence(ev, history, a.variant, rules)
        print(f"{ev['ticker']:6s} {ev['signal_date']:%Y-%m-%d}  {kinds}: {ev['what']}")
        print(f"       {e.sentence}" + (f" Reglas validadas: {', '.join(e.rules)}." if e.rules else ""))
    print("\nAnálisis, no asesoramiento.")


def cmd_reprocess(a) -> None:
    """Run the rules again over what is stored. No downloads: see miratrade/reprocess.py."""
    from miratrade.config import load_user_config
    from miratrade.reprocess import reprocess
    from miratrade.scan import EVENT_LABELS

    cfg = load_user_config()
    if a.min_value is not None:
        cfg.insider.min_value_usd = a.min_value
    if a.lookback is not None:
        cfg.insider.lookback_days = a.lookback
    end = date.fromisoformat(a.end) if a.end else None
    out = reprocess(days=a.days, end=end, cfg=cfg, cap_tier=a.cap, write=not a.dry_run)
    if a.dry_run:
        print("  --dry-run: nothing was written.")
    for ev in out["events"].to_dict("records")[:a.show]:
        kinds = ", ".join(v for k, v in EVENT_LABELS.items() if ev.get(k))
        print(f"{ev['ticker']:6s} {pd.Timestamp(ev['signal_date']):%Y-%m-%d}  {kinds}: "
              f"{ev.get('what') or ''}")


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
    an.add_argument("--cap", choices=list(CAP_TIERS), default=None,
                    help="company size to keep (default: the app setting); saves download time")
    an.add_argument("--offline", action="store_true",
                    help="read the filings, bars and volumes from the store instead of downloading "
                         "them: the same analysis under different settings, in minutes not hours")
    an.add_argument("--out", default="reports")
    an.set_defaults(func=cmd_analyze)

    sn = sub.add_parser("snapshot", help="store today's option chains (volume and open interest per "
                                         "contract) from your own broker account")
    sn.add_argument("tickers", nargs="*", help="the tickers to snapshot; omit to use --from-events")
    sn.add_argument("--from-events", type=int, default=30, metavar="DAYS",
                    help="with no tickers named, use the ones with an event in the last DAYS "
                         "(default 30)")
    sn.add_argument("--limit", type=int, default=60,
                    help="most tickers to ask for in one run; a chain is one broker request each "
                         "(default 60)")
    sn.add_argument("--source", choices=["schwab", "etrade", "cboe"],
                    help="default: data.quote_broker in settings; cboe = personal research only")
    sn.set_defaults(func=cmd_snapshot)

    sc = sub.add_parser("scan", help="new events of the last N days and what similar past events did")
    sc.add_argument("--days", type=int, default=7)
    sc.add_argument("--variant", default="call45_40", help="outcome profile, e.g. call45_40 or stock12m_30")
    sc.add_argument("--report", help="report folder with events.csv (default: newest under reports/)")
    sc.add_argument("--flow", help="options-flow CSV file or directory (default .cache/flow)")
    sc.add_argument("--no-smart-money", action="store_true", help="skip 13D/13G filings")
    sc.add_argument("--cap", choices=list(CAP_TIERS), default=None, help="company size to keep")
    sc.add_argument("--save", help="folder for the result (default: the app's scan folder)")
    sc.set_defaults(func=cmd_scan)

    ex = sub.add_parser("experiment", help="stock-driven tests: event filters, call vs shares, stops and exits")
    ex.add_argument("--days", type=int, default=1825)
    ex.add_argument("--end", help="YYYY-MM-DD (default today)")
    ex.add_argument("--max-insider-tickers", type=int, default=400)
    ex.add_argument("--max-13d-tickers", type=int, default=200)
    ex.add_argument("--flow", help="options-flow CSV file or directory")
    ex.add_argument("--no-smart-money", action="store_true")
    ex.add_argument("--cap", choices=list(CAP_TIERS), default=None, help="company size to keep")
    ex.add_argument("--lookahead-universe", action="store_true",
                    help="rank the universe over the whole window (round 1 did this; it peeks)")
    ex.add_argument("--out", default="reports/5y")
    ex.set_defaults(func=cmd_experiment)

    rp = sub.add_parser("reprocess", help="run the event rules again over stored data, no downloads")
    rp.add_argument("--days", type=int, default=None,
                    help="window ending at the last day stored (default: everything stored)")
    rp.add_argument("--end", help="YYYY-MM-DD (default: the last filing in the store)")
    rp.add_argument("--cap", choices=list(CAP_TIERS), default=None, help="company size to keep")
    rp.add_argument("--min-value", type=float, default=None,
                    help="smallest insider purchase that counts, in dollars")
    rp.add_argument("--lookback", type=int, default=None,
                    help="days a purchase keeps counting towards a cluster")
    rp.add_argument("--dry-run", action="store_true",
                    help="show what these settings would find without touching the events table")
    rp.add_argument("--show", type=int, default=20, help="how many events to print")
    rp.set_defaults(func=cmd_reprocess)

    de = sub.add_parser("demo", help="run the full pipeline on synthetic data with a planted edge")
    de.add_argument("--out", default="reports/demo")
    de.set_defaults(func=cmd_demo)

    from miratrade.store_cli import add_parser as add_store
    add_store(sub)

    from miratrade.congress_cli import add_parser as add_congress
    add_congress(sub)

    from miratrade.flow_cli import add_parser as add_flow
    add_flow(sub)

    from miratrade.earnings_cli import add_parser as add_earnings
    add_earnings(sub)

    from miratrade.schedule_cli import add_parser as add_schedule
    add_schedule(sub)

    from miratrade.notify_cli import add_parser as add_notify
    add_notify(sub)

    from miratrade.massive_cli import add_parser as add_massive
    add_massive(sub)

    try:                                    # needs the [schwab] extra
        from miratrade.broker_cli import add_parser as add_schwab
        add_schwab(sub)
    except ImportError:
        pass
    from miratrade.etrade_cli import add_parser as add_etrade   # OAuth imported only when used
    add_etrade(sub)

    a = ap.parse_args(argv)
    from miratrade.data.prices import PriceSourceError
    try:
        a.func(a)
    except PriceSourceError as e:           # no connected source: say what to do, no traceback
        raise SystemExit(str(e))


if __name__ == "__main__":
    main()
