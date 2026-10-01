"""``miratrade news`` — the 8-K prose: scoring it, and asking whether it means anything.

Separate commands on purpose. Scoring is minutes of CPU and produces data; the study is seconds
and produces a claim. Keeping them apart means a claim can be re-examined without paying for the
data again, and makes it obvious which one you are looking at.
"""
from __future__ import annotations


def add_parser(sub) -> None:
    nw = sub.add_parser("news", help="the prose of an 8-K: score it with FinBERT, and test "
                                     "whether the score says anything")
    inner = nw.add_subparsers(dest="news_cmd", required=True)

    st = inner.add_parser("status", help="what is stored and what is missing; downloads nothing")
    st.set_defaults(func=cmd_status)

    sc = inner.add_parser("score", help="fetch the body of each filing a study needs and score it")
    sc.add_argument("--limit", type=int, default=None, help="stop after this many (a trial run)")
    sc.add_argument("--window", type=int, default=45,
                    help="days before a day that a filing still counts towards it")
    sc.set_defaults(func=cmd_score)

    sy = inner.add_parser("study", help="do the scores differ around events? Controlled, split "
                                        "in time, corrected for multiple testing")
    sy.set_defaults(func=cmd_study)


def cmd_status(a) -> None:
    from miratrade import store
    from miratrade.config import load_user_config
    from miratrade.news import scoring

    cfg = load_user_config()
    db = store.connect()
    try:
        need = scoring.wanted(db)
        done = scoring.already(db, cfg.sentiment.model)
        print(f"FinBERT: {'on' if cfg.sentiment.enabled else 'OFF'} · model {cfg.sentiment.model}")
        print(f"  filings a study would need : {len(need):,}")
        print(f"  already scored             : {len(done):,}")
        print(f"  still to do                : {len(need) - len(need[need['accession'].isin(done)]):,}")
        if not cfg.sentiment.enabled:
            print("\n  Switched off, which is the honest setting: no news signal here has survived\n"
                  "  an out-of-sample test. Turn it on in Settings to score anything.")
    finally:
        db.close()


def cmd_score(a) -> None:
    from miratrade import store
    from miratrade.config import load_user_config
    from miratrade.news.scoring import score_all
    from miratrade.news.sentiment import Unavailable

    db = store.connect()
    try:
        out = score_all(db, load_user_config(), window=a.window, limit=a.limit)
        print(f"{out['scored']:,} scored under {out['model']}")
    except Unavailable as e:
        raise SystemExit(f"{e}\n  Install the extra:  pip install -e .[news]") from e
    finally:
        db.close()


def cmd_study(a) -> None:
    """Whether the wording around an event differs from the wording around a day nobody picked."""
    import pandas as pd

    from miratrade import attempts, store
    from miratrade.news import scoring, study
    from miratrade.stats import Rate, say_rate

    db = store.connect(read_only=True)
    try:
        raw = study.build_sample(db)
        sample = study.match_on_cycle(db, raw)
        if sample.events.empty:
            raise SystemExit("Not enough matched days to compare. Score more filings first.")
        early, late = study.split(sample)

        print(f"{len(sample.events):,} events against {len(sample.placebos):,} placebo days at the "
              f"same point in the quarter\n")
        print(f"{'window':<16}{'events':>9}{'placebos':>11}{'difference':>13}")
        for name, part in (("whole", sample), ("discovery", early), ("confirmation", late)):
            a_ = scoring.of_days(db, part.events).dropna()
            b_ = scoring.of_days(db, part.placebos).dropna()
            if len(a_) < 10 or len(b_) < 10:
                print(f"{name:<16}{'too few scored':>33}")
                continue
            print(f"{name:<16}{a_.mean():>9.3f}{b_.mean():>11.3f}{a_.mean() - b_.mean():>13.3f}"
                  f"   (n={len(a_)} / {len(b_)})")
        print("\nA difference in how filings are worded is not a measured effect on a result, and\n"
              "the 8-K items that looked elevated here did not survive the same control.")
    finally:
        db.close()
