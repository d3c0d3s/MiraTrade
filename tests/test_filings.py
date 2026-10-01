"""8-K items: parsing them, storing them, and asking what was filed near a day.

The reason this is the first piece of news work, and the reason it is worth testing carefully, is
that an EDGAR filing cannot be back-dated. Everything here rests on that, so the tests are mostly
about not losing the properties that make it true: the date is the public one, a correction is a
new filing rather than an edit, and nothing from after a day can leak into a question about it.
"""
import json
from datetime import date

import pandas as pd
import pytest

from miratrade import store
from miratrade.news import filings


def _payload(ticker="ACME", cik="0000012345", rows=(), files=()):
    """An EDGAR submissions response, shaped the way the real one is."""
    keys = ("accessionNumber", "filingDate", "reportDate", "acceptanceDateTime", "form", "items",
            "primaryDocument")
    recent = {k: [r.get(k, "") for r in rows] for k in keys}
    return {"cik": cik, "tickers": [ticker, f"{ticker}-PA"], "name": f"{ticker} CORP",
            "filings": {"recent": recent, "files": list(files)}}


ONE = _payload(rows=[
    {"accessionNumber": "0000012345-26-000001", "filingDate": "2026-09-10",
     "reportDate": "2026-09-09", "acceptanceDateTime": "2026-09-10T20:13:03.000Z",
     "form": "8-K", "items": "5.02,9.01", "primaryDocument": "acme-20260910.htm"},
    {"accessionNumber": "0000012345-26-000002", "filingDate": "2026-09-20",
     "reportDate": "2026-09-18", "acceptanceDateTime": "2026-09-20T13:02:00.000Z",
     "form": "8-K", "items": "3.02,1.01,9.01", "primaryDocument": "acme-20260920.htm"},
    {"accessionNumber": "0000012345-26-000003", "filingDate": "2026-09-22",
     "reportDate": "2026-09-22", "acceptanceDateTime": "2026-09-22T12:00:00.000Z",
     "form": "10-Q", "items": ""},
])


@pytest.fixture
def db(tmp_path):
    conn = store.connect(tmp_path / "market.db")
    yield conn
    conn.close()


# --------------------------------------------------------------------------- parsing

def test_one_row_per_item_not_per_filing(db):
    """The question asked of this data is always "was there a 5.02 near this day", and a filing
    carries several items. One row each makes counting a GROUP BY instead of string matching."""
    rows = filings.parse_submissions(ONE)
    assert len(rows) == 5                                  # 2 + 3 items, the 10-Q ignored
    assert set(rows["item"]) == {"5.02", "3.02", "1.01", "9.01"}
    assert set(rows["form"]) == {"8-K"}


def test_the_common_stock_is_the_ticker_not_the_preferred(db):
    """`tickers` lists the common first and then the preferred issues (WRB, WRB-PE, WRB-PF…). Only
    the first is the company as a price series knows it."""
    assert set(filings.parse_submissions(ONE)["ticker"]) == {"ACME"}


def test_the_public_timestamp_is_kept_to_the_second(db):
    """So "filed at 20:13 New York, therefore tradeable at the next open and not today's close" is
    a question with an answer rather than an assumption."""
    rows = filings.parse_submissions(ONE)
    late = rows[rows["item"] == "5.02"].iloc[0]
    assert late["accepted_at"] == "2026-09-10T20:13:03.000Z"
    assert late["filing_date"] == "2026-09-10"             # the date a backtest may condition on
    assert late["report_date"] == "2026-09-09"             # when it happened: usually earlier


def test_an_item_repeated_in_one_filing_is_counted_once(db):
    payload = _payload(rows=[{"accessionNumber": "a", "filingDate": "2026-09-10", "form": "8-K",
                              "items": "5.02, 5.02 ,9.01"}])
    assert sorted(filings.parse_submissions(payload)["item"]) == ["5.02", "9.01"]


def test_a_filing_with_no_accession_or_date_is_skipped_rather_than_stored_broken(db):
    payload = _payload(rows=[{"accessionNumber": "", "filingDate": "2026-09-10", "form": "8-K",
                              "items": "5.02"},
                             {"accessionNumber": "b", "filingDate": "", "form": "8-K",
                              "items": "5.02"}])
    assert len(filings.parse_submissions(payload)) == 0


def test_corrections_arrive_as_their_own_filing(db):
    """An 8-K/A does not edit the 8-K: it is a new document with its own date. That is exactly the
    property that makes this data safe to condition on, so both are kept."""
    payload = _payload(rows=[
        {"accessionNumber": "a", "filingDate": "2026-09-10", "form": "8-K", "items": "4.02"},
        {"accessionNumber": "b", "filingDate": "2026-09-30", "form": "8-K/A", "items": "4.02"}])
    rows = filings.parse_submissions(payload)
    assert len(rows) == 2 and set(rows["form"]) == {"8-K", "8-K/A"}
    assert sorted(rows["filing_date"]) == ["2026-09-10", "2026-09-30"]


def test_a_company_with_a_paginated_history_is_reported_not_hidden(db):
    """`recent` holds the newest 1,000 filings and the rest live in files we do not fetch. For a
    company that files constantly that cuts into the window a backtest needs, so it is counted."""
    assert filings.truncated(_payload(files=[{"name": "CIK-submissions-001.json"}])) is True
    assert filings.truncated(ONE) is False


# --------------------------------------------------------------------------- storing and asking

def test_the_harvest_reads_what_is_already_on_disk(db, tmp_path):
    """These responses were fetched to find earnings dates; the 8-K items came in the same payload
    and were thrown away. Reading them back costs no request to anybody."""
    folder = tmp_path / "sec"
    folder.mkdir()
    (folder / "data.sec.gov_submissions_CIK0000012345.json").write_text(
        json.dumps(ONE), encoding="utf-8")
    out = filings.harvest_cache(db, folder, log=lambda _m: None)
    assert out == {"items": 5, "companies": 1, "truncated": 0, "files": 1}
    assert len(store.read(db, "filings")) == 5


def test_harvesting_twice_stores_one_copy(db, tmp_path):
    folder = tmp_path / "sec"
    folder.mkdir()
    (folder / "data.sec.gov_submissions_CIK0000012345.json").write_text(
        json.dumps(ONE), encoding="utf-8")
    for _ in range(3):
        filings.harvest_cache(db, folder, log=lambda _m: None)
    assert len(store.read(db, "filings")) == 5             # the primary key does the work


def test_unreadable_files_do_not_stop_the_harvest(db, tmp_path):
    folder = tmp_path / "sec"
    folder.mkdir()
    (folder / "data.sec.gov_submissions_CIK0000000001.json").write_text("{broken", encoding="utf-8")
    (folder / "data.sec.gov_submissions_CIK0000012345.json").write_text(
        json.dumps(ONE), encoding="utf-8")
    assert filings.harvest_cache(db, folder, log=lambda _m: None)["companies"] == 1


def test_nothing_from_after_a_day_can_answer_a_question_about_it(db, tmp_path):
    """The whole point. `after` defaults to 0 and anything a backtest reads must leave it there."""
    store.write(db, "filings", filings.parse_submissions(ONE))
    before = filings.near(db, "ACME", "2026-09-15", before=30)
    assert set(before["item"]) == {"5.02"}                 # the 20th has not happened yet
    later = filings.near(db, "ACME", "2026-09-25", before=30)
    assert set(later["item"]) == {"3.02", "1.01", "5.02"}


def test_routine_items_are_left_out_by_default(db):
    """9.01 marks that documents are attached and rides along with almost everything; counting it
    as news would drown the codes that mean something."""
    store.write(db, "filings", filings.parse_submissions(ONE))
    assert "9.01" not in set(filings.near(db, "ACME", "2026-09-25")["item"])
    assert "9.01" in set(filings.near(db, "ACME", "2026-09-25", exclude_routine=False)["item"])
    assert filings.ROUTINE == {"9.01", "5.07"}


def test_asking_for_one_item_gets_only_that(db):
    store.write(db, "filings", filings.parse_submissions(ONE))
    only = filings.near(db, "ACME", "2026-09-25", items=["3.02"])
    assert set(only["item"]) == {"3.02"}


def test_a_company_with_nothing_filed_is_an_empty_answer_not_an_error(db):
    assert len(filings.near(db, "NOBODY", "2026-09-25")) == 0


def test_what_is_stored_can_be_counted_with_its_meaning(db):
    store.write(db, "filings", filings.parse_submissions(ONE))
    counted = filings.counts(db)
    row = counted[counted["item"] == "5.02"].iloc[0]
    assert row["n"] == 1 and row["tickers"] == 1
    assert "officer" in row["means"]


def test_an_unlabelled_code_comes_back_as_itself(db):
    """An honest answer. The taxonomy grows; inventing a meaning for a code we do not know would
    put words in the SEC's mouth."""
    assert filings.label("5.02").startswith("a director")
    assert filings.label("6.04") == "6.04"


def test_a_company_already_asked_about_is_not_asked_again(db):
    """Coverage per ticker, so a run fetches only what is missing — including the companies whose
    items came from the disk harvest rather than from a request."""
    store.write(db, "filings", filings.parse_submissions(ONE))
    store.mark_covered(db, filings.SOURCE, [date(2026, 9, 25)], rows=0, scope="QUIET")
    asked, missing = filings.have(db, ["ACME", "QUIET", "NEW"])
    assert asked == {"ACME", "QUIET"} and missing == {"NEW"}


def test_fetch_asks_only_for_what_is_missing_and_says_what_it_could_not_resolve(db):
    calls = []

    class Client:
        def get(self, url, max_age_days=0):
            calls.append(url)
            return json.dumps(ONE)

    out = filings.fetch(["ACME", "NOCIK"], {"ACME": "12345"}, Client(), db, log=lambda _m: None)
    assert len(calls) == 1 and "0000012345" in calls[0]
    assert out["items"] == 5 and out["missing"] == ["NOCIK"]
    assert filings.have(db, ["ACME"])[0] == {"ACME"}


def test_the_body_of_a_filing_is_reachable_from_what_is_stored(db):
    """Without the CIK and the document name the table says a document exists and gives no way to
    open it, which is the worst of both: a reference with no referent."""
    rows = filings.parse_submissions(ONE)
    one = rows.iloc[0]
    assert one["cik"] == "12345" and one["document"]

    url = filings.body_url(one["cik"], one["accession"], one["document"])
    assert url.startswith("https://www.sec.gov/Archives/edgar/data/12345/")
    # the accession is dashed in the index and undashed in the path, which costs an afternoon the
    # first time you meet it
    assert "000001234526000001" in url and "-" not in url.rsplit("/", 2)[-2]


def test_both_columns_survive_the_round_trip(db):
    store.write(db, "filings", filings.parse_submissions(ONE))
    back = store.read(db, "filings", "item = ?", ("5.02",)).iloc[0]
    assert back["cik"] == "12345" and str(back["document"]).endswith(".htm")
