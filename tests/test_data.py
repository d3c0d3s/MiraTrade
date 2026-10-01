import io
import zipfile
from datetime import date

import pandas as pd

from miratrade.data.options import normalise_flow, parse_cboe_chain, parse_occ
from miratrade.data.sec import parse_bulk_zip, parse_daily_index, parse_form4_xml

FORM4 = """<ownershipDocument>
  <issuer><issuerCik>1</issuerCik><issuerName>Acme Corp</issuerName>
    <issuerTradingSymbol>acme</issuerTradingSymbol></issuer>
  <reportingOwner>
    <reportingOwnerId><rptOwnerCik>99</rptOwnerCik><rptOwnerName>Doe Jane</rptOwnerName></reportingOwnerId>
    <reportingOwnerRelationship><isDirector>0</isDirector><isOfficer>1</isOfficer>
      <officerTitle>Chief Executive Officer</officerTitle></reportingOwnerRelationship>
  </reportingOwner>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <transactionDate><value>2026-08-03</value></transactionDate>
      <transactionCoding><transactionCode>P</transactionCode></transactionCoding>
      <transactionAmounts><transactionShares><value>1000</value></transactionShares>
        <transactionPricePerShare><value>50.5</value></transactionPricePerShare></transactionAmounts>
      <postTransactionAmounts><sharesOwnedFollowingTransaction><value>5000</value>
        </sharesOwnedFollowingTransaction></postTransactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>"""


def test_parse_form4_xml():
    df = parse_form4_xml(FORM4, accession="a1", filing_date="20260805")
    r = df.iloc[0]
    assert r.ticker == "ACME" and r.code == "P" and r.is_officer and not r.is_director
    assert r.issuer_cik == "1"
    assert r.value == 50_500 and r.delta_own_pct == 0.25
    assert r.filing_date == pd.Timestamp("2026-08-05") and r.trade_date == pd.Timestamp("2026-08-03")
    assert not r.plan_10b5_1                                     # no checkbox: not under a plan
    planned = parse_form4_xml(FORM4.replace("<issuer>", "<aff10b5One>1</aff10b5One><issuer>"))
    assert planned["plan_10b5_1"].all()


def test_parse_daily_index_dedupes_and_filters():
    idx = ("Form Type   Company Name   CIK   Date Filed  File Name\n" + "-" * 40 + "\n"
           "4           ACME CORP      1     20260805    edgar/data/1/0001-26-1.txt\n"
           "4           DOE JANE       99    20260805    edgar/data/99/0001-26-1.txt\n"
           "4/A         ACME CORP      1     20260805    edgar/data/1/0001-26-2.txt\n"
           "10-K        ACME CORP      1     20260805    edgar/data/1/0001-26-3.txt\n")
    # the company and the insider each get an index line for the SAME filing, under their own CIK:
    # two paths, one accession, one document to download
    assert parse_daily_index(idx) == [("edgar/data/1/0001-26-1.txt", "20260805")]


def test_parse_bulk_zip():
    tables = {
        "SUBMISSION.tsv": "ACCESSION_NUMBER\tFILING_DATE\tISSUERNAME\tISSUERTRADINGSYMBOL\tISSUERCIK\n"
                          "a1\t05-AUG-2026\tAcme\tACME\t0000000042\n",
        "REPORTINGOWNER.tsv": "ACCESSION_NUMBER\tRPTOWNERCIK\tRPTOWNERNAME\tRPTOWNER_RELATIONSHIP\tRPTOWNER_TITLE\n"
                              "a1\t99\tDoe\tDirector,Officer\tCFO\n",
        "NONDERIV_TRANS.tsv": "ACCESSION_NUMBER\tTRANS_DATE\tTRANS_CODE\tTRANS_SHARES\tTRANS_PRICEPERSHARE\tSHRS_OWND_FOLWNG_TRANS\n"
                              "a1\t01-AUG-2026\tP\t100\t10\t100\n",
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, body in tables.items():
            zf.writestr(name, body)
    r = parse_bulk_zip(buf.getvalue()).iloc[0]
    assert r.ticker == "ACME" and r.is_officer and r.is_director and r.value == 1000
    assert r.issuer_cik == "42"
    assert r.delta_own_pct == 1.0  # brand-new position
    assert not r.plan_10b5_1       # data sets before 2023 have no AFF10B5ONE column

    tables["SUBMISSION.tsv"] = ("ACCESSION_NUMBER\tFILING_DATE\tISSUERNAME\tISSUERTRADINGSYMBOL\tISSUERCIK\tAFF10B5ONE\n"
                                "a1\t05-AUG-2026\tAcme\tACME\t0000000042\ttrue\n")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, body in tables.items():
            zf.writestr(name, body)
    assert parse_bulk_zip(buf.getvalue())["plan_10b5_1"].all()


def test_parse_occ():
    assert parse_occ("AAPL260918C00200000") == ("AAPL", date(2026, 9, 18), "C", 200.0)
    assert parse_occ("garbage") is None


def test_normalise_flow_aliases():
    raw = pd.DataFrame({"Symbol": ["nvda"], "Executed At": ["2026-09-01 10:31"], "Expiration": ["2026-09-19"],
                        "Put/Call": ["call"], "Strike": [120], "Size": [3000], "OI": [400],
                        "Premium": ["$1,250,000"], "Stock Price": [118], "Side": ["Ask"]})
    raw = raw.rename(columns={"Put/Call": "put_call"})
    r = normalise_flow(raw).iloc[0]
    assert r.ticker == "NVDA" and r.type == "C" and r.premium == 1_250_000 and r.side == "ask"
    assert r.date == pd.Timestamp("2026-09-01")


def test_parse_cboe_chain():
    payload = {"data": {"symbol": "XYZ", "current_price": 100, "options": [
        {"option": "XYZ261016C00105000", "volume": 2000, "open_interest": 100, "last_trade_price": 2.5},
        {"option": "XYZ261016P00095000", "volume": 0, "open_interest": 100, "last_trade_price": 1.0}]}}
    df = parse_cboe_chain(payload, date(2026, 9, 24))
    assert len(df) == 1 and df.iloc[0].premium == 500_000 and df.iloc[0].strike == 105


class _Resp:
    def __init__(self, status, content=b"ok", headers=None):
        self.status_code, self.content, self.headers = status, content, headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


def _client(tmp_path, statuses):
    from miratrade.data.sec import SecClient

    c = SecClient(user_agent="test test@example.com", cache_dir=tmp_path, retries=3, backoff=0,
                  block_wait=0)
    replies = iter(_Resp(s) for s in statuses)
    c.session.get = lambda url, timeout: next(replies)
    return c


def test_sec_client_retries_transient_errors(tmp_path):
    c = _client(tmp_path, [503, 429, 200])
    assert c.get("https://www.sec.gov/x.txt") == b"ok"
    assert (tmp_path / "www.sec.gov_x.txt").exists()


def test_sec_client_gives_up_after_retries(tmp_path):
    import pytest

    c = _client(tmp_path, [503] * 4)
    with pytest.raises(RuntimeError):
        c.get("https://www.sec.gov/y.txt")
    assert _client(tmp_path, [404]).get("https://www.sec.gov/z.txt") is None


def test_sec_client_missing_statuses(tmp_path):
    import pytest

    # EDGAR answers a holiday's missing daily index with 403, not 404.
    assert _client(tmp_path, [403]).get("https://www.sec.gov/idx", missing=(403, 404)) is None
    with pytest.raises(RuntimeError):
        _client(tmp_path, [403]).get("https://www.sec.gov/other")


def test_sec_rate_limit_is_shared_and_a_429_pauses_everyone(tmp_path):
    import time

    import pytest

    from miratrade.data.sec import SecClient, SharedRate

    # two clients (think: the app and an analysis) share one budget through the cache folder
    a, b = (SecClient(user_agent="t t@example.com", cache_dir=tmp_path, per_second=20) for _ in range(2))
    for c in (a, b):
        c.session.get = lambda url, timeout: _Resp(200)
    t0 = time.perf_counter()
    for k in range(6):
        (a if k % 2 else b).get(f"https://www.sec.gov/r{k}", cache=False)
    assert time.perf_counter() - t0 >= 5 / 20 * 0.9

    # a 429 with Retry-After blocks the shared file and the retry waits for it
    replies = iter([_Resp(429, headers={"Retry-After": "0.3"}), _Resp(200, b"later")])
    a.session.get = lambda url, timeout: next(replies)
    t0 = time.perf_counter()
    assert a.get("https://www.sec.gov/blocked", cache=False) == b"later"
    assert time.perf_counter() - t0 >= 0.25
    assert SharedRate(tmp_path / ".sec_rate")._read()[1] > 0

    # a second 429 on the same request is an error, not an endless wait
    replies = iter([_Resp(429, headers={"Retry-After": "0"}), _Resp(429, headers={"Retry-After": "0"})])
    a.session.get = lambda url, timeout: next(replies)
    with pytest.raises(RuntimeError):
        a.get("https://www.sec.gov/again", cache=False)


def test_sec_cache_max_age(tmp_path):
    import os

    c = _client(tmp_path, [200])
    assert c.get("https://data.sec.gov/x.json") == b"ok"
    key = tmp_path / "data.sec.gov_x.json"
    old = key.stat().st_mtime - 10 * 86400
    os.utime(key, (old, old))
    c.session.get = lambda url, timeout: _Resp(200, b"fresh")
    assert c.get("https://data.sec.gov/x.json") == b"ok"                      # plain cache never expires
    assert c.get("https://data.sec.gov/x.json", max_age_days=7) == b"fresh"   # a stale copy is refetched


def test_clean_insiders_drops_filing_errors():
    from miratrade.data.sec import clean_insiders

    rows = pd.DataFrame({
        "ticker": ["ACME", "NONE", "PBLSX", "REEMF", "BRK.A", "SPGX"],
        "price": [50.0, 10.0, 12.0, 24_035_774.4, 700_000.0, 30.0],
        "shares": [1_000, 1_000, 1_000, 100_149_100, 10, 1_000],
    }).assign(value=lambda d: d["price"] * d["shares"])
    kept, stats = clean_insiders(rows)
    # REEMF typed the total into the price field; BRK.A is a genuinely high price on few shares;
    # SPGX is a four-letter stock, not a five-letter fund ticker.
    assert list(kept["ticker"]) == ["ACME", "BRK.A", "SPGX"]
    assert stats == {"placeholder_ticker": 1, "fund_ticker": 1, "total_as_price": 1}


def test_sec_downloads_run_in_parallel_without_exceeding_the_budget(tmp_path):
    """Several filings download at once, but the shared budget still sets the pace, and each
    thread gets its own session because requests.Session is not thread-safe."""
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor

    from miratrade.data.sec import SecClient

    c = SecClient(user_agent="t t@example.com", cache_dir=tmp_path, per_second=20)
    gate, seen = threading.Barrier(3), []                  # one session per thread, never shared

    def grab(_):
        session = c.session
        # Generous on purpose. The barrier is here to force three threads to exist at once, not to
        # measure how fast they get there — and with the whole suite running, five seconds is a
        # coin flip. A test that fails because the machine was busy teaches people to ignore
        # failures, which costs more than the thing it was checking.
        gate.wait(timeout=60)
        return session

    with ThreadPoolExecutor(max_workers=3) as pool:
        seen = list(pool.map(grab, range(3)))
    assert len({id(s) for s in seen}) == 3

    latency, requests_made = 0.05, 12
    in_flight, peak, lock = [0], [0], threading.Lock()

    def slow_get(url, timeout):
        with lock:
            in_flight[0] += 1
            peak[0] = max(peak[0], in_flight[0])
        time.sleep(latency)                                # stand in for the network
        with lock:
            in_flight[0] -= 1
        return _Resp(200, b"ok")

    original = type(c)._new_session
    type(c)._new_session = lambda self: type("S", (), {"get": staticmethod(slow_get), "headers": {}})()
    try:
        c._local = threading.local()                       # drop the real sessions
        with ThreadPoolExecutor(max_workers=6) as pool:
            t0 = time.perf_counter()
            list(pool.map(lambda i: c.get(f"https://www.sec.gov/f{i}", cache=False), range(requests_made)))
            elapsed = time.perf_counter() - t0
    finally:
        type(c)._new_session = original

    serial = requests_made * (latency + 1 / 20)            # what one-at-a-time would cost
    floor = (requests_made - 1) / 20                       # what the shared budget alone costs
    assert peak[0] > 1                                     # genuinely concurrent
    assert elapsed < serial * 0.8                          # faster than one at a time
    assert elapsed >= floor * 0.8                          # and never faster than the budget allows


def test_a_finished_day_is_parsed_once_and_reused(tmp_path, monkeypatch):
    """Raw filings were already cached, but every scan rebuilt a table from each XML. A day that
    is over cannot gain filings, so its parsed rows are kept and reused verbatim."""
    from datetime import date

    from miratrade.data import sec

    day = date(2026, 9, 11)
    index = ("Form Type   Company Name   CIK   Date Filed  File Name\n" + "-" * 40 + "\n"
             "4           ACME CORP      1     20260911    edgar/data/1/a.txt\n")
    parsed = 0
    real_parse = sec.parse_form4_xml

    def counting_parse(*args, **kwargs):
        nonlocal parsed
        parsed += 1
        return real_parse(*args, **kwargs)

    monkeypatch.setattr(sec, "parse_form4_xml", counting_parse)

    class Client:
        cache_dir = tmp_path
        calls = 0

        def get(self, url, cache=True, missing=(404,), max_age_days=None):
            Client.calls += 1
            if "daily-index" in url:
                return index.encode() if url.endswith("form.20260911.idx") else None
            if "Archives" in url:
                return FORM4.encode()
            return None

    from miratrade import store

    db = store.connect(tmp_path / "market.db")
    client = Client()
    first = sec.fetch_insiders(day, day, client, today=date(2026, 9, 20), db=db)
    assert len(first) == 1 and parsed == 1
    assert store.covered(db, sec.SOURCE) == {"2026-09-11"}   # the day is remembered as done

    calls_after_first = Client.calls
    second = sec.fetch_insiders(day, day, client, today=date(2026, 9, 20), db=db)
    assert parsed == 1                                      # nothing re-parsed
    assert Client.calls == calls_after_first                # and nothing re-downloaded
    assert second["ticker"].tolist() == first["ticker"].tolist()
    assert second["filing_date"].tolist() == first["filing_date"].tolist()
    assert second["is_officer"].tolist() == first["is_officer"].tolist()
    assert second["value"].tolist() == first["value"].tolist()

    # everything parsed is kept, not only the codes that were asked for
    assert len(store.read(db, "insiders")) >= len(first)
    db.close()


def test_today_is_never_cached_because_more_filings_may_arrive(tmp_path):
    from datetime import date

    from miratrade.data import sec

    day = date(2026, 9, 11)
    index = ("Form Type   Company   CIK   Date Filed  File Name\n" + "-" * 40 + "\n"
             "4           ACME      1     20260911    edgar/data/1/a.txt\n")

    class Client:
        cache_dir = tmp_path

        def get(self, url, cache=True, missing=(404,), max_age_days=None):
            if "daily-index" in url:
                return index.encode()
            return FORM4.encode() if "Archives" in url else None

    from miratrade import store

    db = store.connect(tmp_path / "market.db")
    sec.fetch_insiders(day, day, Client(), today=day, db=db)
    assert store.covered(db, sec.SOURCE) == set()            # today is never marked covered
    assert len(store.read(db, "insiders")) == 1              # but what it found is still stored
    db.close()


def test_a_filing_that_lists_two_share_classes_is_not_thrown_away():
    """Berkshire's first Form 4 for Lennar was filed with ticker "LEN, LEN.B". Rejecting that as
    malformed dropped $212M of open-market buying — 61% of what they bought — in silence."""
    import pandas as pd

    from miratrade.data.sec import primary_ticker

    got = primary_ticker(pd.Series(["LEN, LEN.B", "LEN", "len.b", "BRK.A", "GOOG/GOOGL",
                                    " PFE ", None, "", "LEN;LEN.B"]))
    assert list(got) == ["LEN", "LEN", "LEN.B", "BRK.A", "GOOG", "PFE", "", "", "LEN"]


def test_the_ticker_filter_still_rejects_what_is_not_a_stock():
    import pandas as pd

    from miratrade.data.sec import primary_ticker

    kept = primary_ticker(pd.Series(["LEN, LEN.B", "TOOLONGSYM", "123", "N/A"]))
    ok = kept.str.fullmatch(r"[A-Z.]{1,6}", na=False)
    assert list(kept[ok]) == ["LEN", "N"]          # the long symbol and the digits still go
    assert not ok.iloc[1] and not ok.iloc[2]


def test_both_form4_parsers_agree_on_a_missing_ticker():
    """A whole quarter of history died on this. The Form 4 XML gives "" for an absent
    issuerTradingSymbol and the quarterly TSV gives NaN, which is NULL, which the schema refuses —
    so the bulk path crashed on the 0.14% of rows that are non-traded REITs with no symbol."""
    import pandas as pd

    from miratrade.data.sec import INSIDER_COLUMNS, _finish, clean_insiders

    raw = pd.DataFrame({
        "accession": ["a", "b"], "filing_date": ["2026-09-01", "2026-09-01"],
        "trade_date": ["2026-08-30", "2026-08-30"],
        "ticker": [None, " pfe "], "issuer": ["A REIT", "PFIZER"], "issuer_cik": ["1", "2"],
        "owner": ["X", "Y"], "owner_cik": ["9", "8"],
        "is_officer": [False, True], "is_director": [False, False], "is_ten_pct": [False, False],
        "title": ["", ""], "code": ["P", "P"], "shares": [10.0, 10.0], "price": [1.0, 1.0],
        "owned_after": [10.0, 10.0], "plan_10b5_1": [False, False]})
    done = _finish(raw)
    assert list(done.columns) == INSIDER_COLUMNS
    assert done["ticker"].tolist() == ["", "PFE"]        # never NaN, and normalised
    assert done["ticker"].notna().all()                  # so NOT NULL cannot fail

    kept, _stats = clean_insiders(done)
    assert kept["ticker"].tolist() == ["PFE"]            # and the symbol-less row goes on read
