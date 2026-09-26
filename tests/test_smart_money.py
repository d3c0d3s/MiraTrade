import gzip

import numpy as np
import pandas as pd

from miratrade.backtest import build_panel, conditions, entry_trigger
from miratrade.cli import pipeline
from miratrade.config import Config
from miratrade.data.finra import fetch_short_volume, parse_short_volume
from miratrade.data.options import FLOW_COLUMNS
from miratrade.data.ownership import cik_ticker_map, parse_13dg_index, resolve_subjects
from miratrade.data.sec import INSIDER_COLUMNS
from miratrade.signals.smart_money import ownership_features, short_features
from miratrade.synthetic import make_13d_market

# Same shape as EDGAR's full-index form.idx: each filing is listed once per party, under that
# party's own folder, with the same accession file name.
INDEX = """Description:           Master Index of EDGAR Dissemination Feed by Form Type
Form Type   Company Name                                                  CIK         Date Filed  File Name
---------------------------------------------------------------------------------------------------------------------------------------------
SCHEDULE 13D     2717 Partners LP                                              2053119     2025-08-19  edgar/data/2053119/0002053119-25-000002.txt
SCHEDULE 13D     ACCESS Newswire Inc.                                          843006      2025-08-19  edgar/data/843006/0002053119-25-000002.txt
SCHEDULE 13G     VANGUARD GROUP INC                                            102909      2025-08-20  edgar/data/102909/0000102909-25-000100.txt
SCHEDULE 13G     ACME CORP                                                     1000        2025-08-20  edgar/data/1000/0000102909-25-000100.txt
SCHEDULE 13D/A   Private Holdco LLC                                            5555        2025-08-21  edgar/data/5555/0000005555-25-000001.txt
SCHEDULE 13D/A   Private Target Inc                                            5556        2025-08-21  edgar/data/5556/0000005555-25-000001.txt
SC 13D           BIG PUBLIC CO                                                 7000        20250822    edgar/data/7000/0000007000-25-000009.txt
SC 13D           SMALL TARGET INC                                              7001        20250822    edgar/data/7001/0000007000-25-000009.txt
10-K             ACME CORP                                                     1000        2025-08-20  edgar/data/1000/0000001000-25-000001.txt
"""

NO_INS, NO_FLOW = pd.DataFrame(columns=INSIDER_COLUMNS), pd.DataFrame(columns=FLOW_COLUMNS)
CIK_MAP = {"843006": "ACCS", "1000": "ACME", "7000": "BIG", "7001": "SMOL"}


def test_parse_13dg_index_keeps_only_13d_13g():
    rows = parse_13dg_index(INDEX)
    assert len(rows) == 8 and set(rows["form"]) == {"SCHEDULE 13D", "SCHEDULE 13G", "SCHEDULE 13D/A", "SC 13D"}
    assert rows["filing_date"].iloc[-1] == pd.Timestamp("2025-08-22")   # compact date format too
    assert rows["cik"].iloc[0] == "2053119"


def test_resolve_subjects_picks_the_listed_party():
    header = b"SUBJECT COMPANY:\n\tCOMPANY DATA:\n\t\tCENTRAL INDEX KEY:\t\t\t0000007001\n"
    out, stats = resolve_subjects(parse_13dg_index(INDEX), CIK_MAP, fetch_header=lambda path: header,
                                  passive_filers=("VANGUARD",))
    by = out.set_index("ticker")
    assert set(by.index) == {"ACCS", "ACME", "SMOL"}
    assert by.loc["ACCS", "kind"] == "13D" and by.loc["ACCS", "filer"] == "2717 Partners LP"
    assert by.loc["ACME", "passive"] and not by.loc["ACCS", "passive"]
    assert stats == {"filings": 4, "resolved": 3, "unresolved": 1, "ambiguous": 1}


def test_ambiguous_filing_is_skipped_without_header():
    out, stats = resolve_subjects(parse_13dg_index(INDEX), CIK_MAP)
    assert "SMOL" not in set(out["ticker"]) and "BIG" not in set(out["ticker"])
    assert stats["ambiguous"] == 1


def test_cik_map_from_insiders_covers_delisted_issuers():
    ins = pd.DataFrame({"issuer_cik": ["42", "42", ""], "ticker": ["OLD", "NEW", "X"],
                        "filing_date": pd.to_datetime(["2024-01-01", "2025-01-01", "2025-01-01"])})
    assert cik_ticker_map(None, ins) == {"42": "NEW"}                 # latest filing wins


def _filings(*rows):
    cols = ["filing_date", "ticker", "kind", "amendment", "passive"]
    return pd.DataFrame([dict(zip(cols, r)) for r in rows]).assign(filing_date=lambda d: pd.to_datetime(d["filing_date"]))


def test_ownership_features_point_in_time():
    f = _filings(("2026-08-05", "ACME", "13D", False, False),       # Wednesday
                 ("2026-08-08", "ACME", "13G", False, False),       # Saturday -> seen Monday
                 ("2026-08-05", "ACME", "13G", False, True),        # index fund: ignored
                 ("2026-08-06", "ACME", "13G", True, False))        # amendment: ignored
    dates = pd.bdate_range("2026-08-03", "2026-09-30")
    o = ownership_features(f, dates, "ACME")
    assert o.loc["2026-08-04"].sum() == 0                            # nothing filed yet
    assert o.loc["2026-08-05", "own_13d"] == 1 and o.loc["2026-08-05", "own_fresh"] == 1
    assert o.loc["2026-08-06", "own_fresh"] == 0 and o.loc["2026-08-06", "own_13g"] == 0
    assert o.loc["2026-08-10", "own_13g"] == 1 and o.loc["2026-08-10", "own_fresh"] == 1
    assert o.loc["2026-09-15"].sum() == 0                            # past the 30-day lookback


def _sv(ratios, ticker="ACME"):
    dates = pd.bdate_range("2026-01-01", periods=len(ratios))
    return pd.DataFrame({"date": dates, "ticker": ticker, "short_volume": np.array(ratios) * 1000,
                         "total_volume": 1000.0})


def test_short_features_z_score_and_flags():
    rng = np.random.default_rng(0)
    ratios = list(0.5 + rng.normal(0, 0.02, 40)) + [0.35]           # last day: shorting collapses
    sv = _sv(ratios)
    dates = pd.bdate_range("2026-01-01", periods=len(ratios))
    s = short_features(sv, dates, "ACME")
    assert s["short_z"].iloc[:9].isna().all()                        # not enough history yet
    assert s["short_z"].iloc[-1] < -1 and s["short_low"].iloc[-1] == 1 and s["short_high"].iloc[-1] == 0
    cut = short_features(sv.iloc[:30], dates[:30], "ACME")
    pd.testing.assert_frame_equal(s.iloc[:30], cut)                  # later days never change earlier ones
    assert short_features(sv, dates, "OTHER")["short_z"].isna().all()


def test_parse_short_volume_drops_trailer_and_filters():
    text = ("Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market\n"
            "20260924|AAPL|4408113.1|13863|8953313.2|B,Q,N\n"
            "20260924|SPY|5814477.3|23734|12478734.4|B,Q,N\n"
            "12360\n")
    df = parse_short_volume(text, {"AAPL"})
    assert list(df["ticker"]) == ["AAPL"] and df["date"].iat[0] == pd.Timestamp("2026-09-24")


class _Resp:
    def __init__(self, status, text=""):
        self.status_code, self.text = status, text


def test_fetch_short_volume_caches_and_skips_holidays(tmp_path):
    body = "Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market\n{d}|AAPL|10|0|20|Q\n1\n"
    calls = []

    class Session:
        def get(self, url, timeout):
            calls.append(url)
            d = url[-12:-4]
            return _Resp(404) if d == "20260703" else _Resp(200, body.format(d=d))

    df = fetch_short_volume(pd.Timestamp("2026-07-02").date(), pd.Timestamp("2026-07-06").date(),
                            cache_dir=tmp_path, session=Session(), min_interval=0)
    assert len(df) == 2 and len(calls) == 3                          # 2, 3 (holiday), 6 July
    assert gzip.decompress((tmp_path / "shvol_20260702.txt.gz").read_bytes()).startswith(b"Date|")
    fetch_short_volume(pd.Timestamp("2026-07-02").date(), pd.Timestamp("2026-07-06").date(),
                       cache_dir=tmp_path, session=Session(), min_interval=0)
    assert len(calls) == 4                                           # only the holiday is retried


def test_13d_filing_triggers_a_candidate_trade():
    prices, ownership = make_13d_market(n_tickers=3)
    panel = build_panel(prices, NO_INS, NO_FLOW, Config(), ownership=ownership)
    first = ownership[ownership["kind"] == "13D"].sort_values("filing_date").iloc[0]
    ind = panel[first["ticker"]]
    assert entry_trigger(ind).loc[first["filing_date"]]
    c = conditions(ind.loc[first["filing_date"]])
    assert c["event:13dg"] and c["own:13d"] and not c["own:13g_active"]


def test_recovers_planted_13d_edge(tmp_path):
    # Half the new filings are 13Ds with drift, half active 13Gs without: the rules must pick the 13Ds.
    prices, ownership = make_13d_market(n_tickers=100, drift_after_signal=0.006)
    res = pipeline(prices, NO_INS, NO_FLOW, prices["SPY"].index[-220], tmp_path,
                   ownership=ownership)
    validated = res["rules"][res["rules"]["validated"]]
    assert validated["rule"].str.contains("own:13d|event:13dg").any(), validated["rule"].tolist()
    assert not validated["rule"].str.contains("own:13g_active").any()     # the no-drift events


def test_no_13d_edge_in_pure_noise(tmp_path):
    prices, ownership = make_13d_market(n_tickers=100, drift_after_signal=0.0)
    res = pipeline(prices, NO_INS, NO_FLOW, prices["SPY"].index[-220], tmp_path, ownership=ownership)
    rules = res["rules"]
    assert not (rules["validated"] & rules["rule"].str.contains("own:|event:13dg")).any()
