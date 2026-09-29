"""The Scanner's query layer: filters have to run in SQL, and only where they mean something."""
from datetime import date

import pandas as pd
import pytest

from miratrade import scanner, store

END = date(2026, 9, 27)


@pytest.fixture
def db(tmp_path):
    conn = store.connect(tmp_path / "market.db")
    store.write(conn, "insiders", pd.DataFrame([
        # a CEO's own open-market purchase: the row the screen exists to find
        {"accession": "0001-26-1", "filing_date": "2026-09-20", "trade_date": "2026-09-19",
         "ticker": "PFE", "owner": "BOURLA ALBERT", "title": "CEO", "code": "P", "shares": 38000.0,
         "price": 26.34, "value": 1_000_920.0, "is_officer": 1, "is_director": 0, "is_ten_pct": 0,
         "plan_10b5_1": 0, "issuer_cik": "0000078003"},
        # the same size, but set up months earlier by a plan, and by a director rather than an officer
        {"accession": "0001-26-2", "filing_date": "2026-09-21", "trade_date": "2026-09-20",
         "ticker": "KLTR", "owner": "DOE JANE", "title": "Director", "code": "P", "shares": 1000.0,
         "price": 900.0, "value": 900_000.0, "is_officer": 0, "is_director": 1, "is_ten_pct": 0,
         "plan_10b5_1": 1, "issuer_cik": "0000099"},
        {"accession": "0001-26-3", "filing_date": "2026-09-22", "trade_date": "2026-09-22",
         "ticker": "ACME", "owner": "ROE RICHARD", "title": "CFO", "code": "S", "shares": 500.0,
         "price": 10.0, "value": 5_000.0, "is_officer": 1, "is_director": 0, "is_ten_pct": 0,
         "plan_10b5_1": 0, "issuer_cik": "0000001"},
        {"accession": "0001-26-4", "filing_date": "2026-01-05", "trade_date": "2026-01-04",
         "ticker": "OLD", "owner": "PAST PERSON", "title": "CEO", "code": "P", "shares": 100.0,
         "price": 50.0, "value": 5_000.0, "is_officer": 1, "is_director": 0, "is_ten_pct": 0,
         "plan_10b5_1": 0, "issuer_cik": "0000002"}]))
    store.write(conn, "congress_members", pd.DataFrame([
        {"bioguide_id": "W1", "name": "Tim Walberg", "chamber": "house", "sectors": '["Defense"]'}]))
    store.write(conn, "congress_trades", pd.DataFrame([
        {"doc_id": "D1", "row_in_doc": 0, "filing_date": "2026-09-22", "trade_date": "2026-08-12",
         "member": "Tim Walberg", "bioguide_id": "W1", "chamber": "house", "ticker": "AVGO",
         "asset": "Broadcom Inc. (AVGO) [ST]", "type": "purchase", "owner": "joint",
         "amount_low": 1001.0, "amount_high": 15000.0,
         "filing_url": "https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/2026/D1.pdf"},
        {"doc_id": "D2", "row_in_doc": 0, "filing_date": "2026-09-23", "trade_date": "2026-09-01",
         "member": "Jane Senator", "bioguide_id": None, "chamber": "senate", "ticker": "NVDA",
         "asset": "NVIDIA (NVDA) [ST]", "type": "sale", "owner": "self",
         "amount_low": 50001.0, "amount_high": 100000.0, "filing_url": ""}]))
    store.write(conn, "ownership", pd.DataFrame([
        {"accession": "0002-26-1", "filing_date": "2026-09-15", "ticker": "PFE", "filer": "ACTIVIST LP",
         "kind": "13D", "amendment": 0, "passive": 0, "subject_cik": "0000078003"},
        {"accession": "0002-26-2", "filing_date": "2026-09-16", "ticker": "ACME", "filer": "BIG INDEX FUND",
         "kind": "13G", "amendment": 0, "passive": 1, "subject_cik": "0000001"}]))
    store.write(conn, "short_volume", pd.DataFrame([
        {"date": "2026-09-22", "ticker": "PFE", "short_volume": 400.0, "total_volume": 1000.0}]))
    yield conn
    conn.close()


# --------------------------------------------------------------------------- the filters

def test_every_insider_filter_narrows_and_they_combine(db):
    wide = scanner.Filters(days=30, end=END)
    assert len(scanner.run(db, "insiders", wide)) == 3          # the January row is outside 30 days

    assert len(scanner.run(db, "insiders", scanner.Filters(days=365, end=END))) == 4
    assert len(scanner.run(db, "insiders", scanner.Filters(days=30, code="P", end=END))) == 2
    assert len(scanner.run(db, "insiders", scanner.Filters(days=30, role="director", end=END))) == 1
    assert len(scanner.run(db, "insiders", scanner.Filters(days=30, min_amount=1e6, end=END))) == 1
    assert len(scanner.run(db, "insiders", scanner.Filters(days=30, exclude_plan=True, end=END))) == 2

    # the combination every insider screen is really for: a big open-market buy by an officer,
    # not a pre-arranged plan
    narrow = scanner.Filters(days=30, code="P", role="officer", min_amount=500_000,
                             exclude_plan=True, end=END)
    rows = scanner.run(db, "insiders", narrow)
    assert len(rows) == 1 and rows.iloc[0]["Ticker"] == "PFE"
    assert rows.iloc[0]["Insider"] == "BOURLA ALBERT" and rows.iloc[0]["Value"] == 1_000_920.0


def test_several_tickers_can_be_typed_the_way_a_watchlist_is_written(db):
    for text in ("PFE, ACME", "pfe,acme", "PFE; ACME", " PFE ,  ACME "):
        rows = scanner.run(db, "insiders", scanner.Filters(days=30, ticker=text, end=END))
        assert sorted(rows["Ticker"]) == ["ACME", "PFE"], text
    assert len(scanner.run(db, "insiders", scanner.Filters(days=30, ticker="NOPE", end=END))) == 0
    # an empty box is not a filter
    assert len(scanner.run(db, "insiders", scanner.Filters(days=30, ticker="  ,  ", end=END))) == 3


def test_days_of_zero_means_everything_ever_collected(db):
    assert len(scanner.run(db, "insiders", scanner.Filters(days=0, end=END))) == 4


def test_a_filter_a_source_does_not_understand_is_ignored_rather_than_breaking_the_query(db):
    """The screen hides those controls, but nothing may depend on the screen for correctness."""
    f = scanner.Filters(days=30, code="P", role="officer", chamber="senate", option_type="call",
                        stake_kind="13D", end=END)
    rows = scanner.run(db, "prices", f)          # prices understand only dates and ticker
    assert list(rows.columns)[:2] == ["Day", "Ticker"] and len(rows) == 0
    assert len(scanner.run(db, "short_volume" if False else "dark", f)) == 1


def test_the_congress_source_joins_the_roster_and_shows_how_late_the_filing_was(db):
    rows = scanner.run(db, "congress", scanner.Filters(days=30, end=END))
    assert len(rows) == 2
    walberg = rows[rows["Ticker"] == "AVGO"].iloc[0]
    assert walberg["Days late"] == 41                      # 12 August traded, 22 September filed
    assert walberg["Committee sectors"] == '["Defense"]'
    assert walberg["Held by"] == "joint"

    senator = rows[rows["Ticker"] == "NVDA"].iloc[0]
    assert pd.isna(senator["Committee sectors"])           # not matched to a member: left empty
    assert len(scanner.run(db, "congress", scanner.Filters(days=30, chamber="senate", end=END))) == 1
    assert len(scanner.run(db, "congress", scanner.Filters(days=30, trade_type="purchase", end=END))) == 1
    assert len(scanner.run(db, "congress", scanner.Filters(days=30, member="walberg", end=END))) == 1
    assert len(scanner.run(db, "congress", scanner.Filters(days=30, min_amount=50_000, end=END))) == 1


def test_active_stakes_can_be_told_from_an_index_funds_mechanical_filing(db):
    assert len(scanner.run(db, "ownership", scanner.Filters(days=30, end=END))) == 2
    active = scanner.run(db, "ownership", scanner.Filters(days=30, exclude_passive=True, end=END))
    assert len(active) == 1 and active.iloc[0]["Filer"] == "ACTIVIST LP"
    only_13d = scanner.run(db, "ownership", scanner.Filters(days=30, stake_kind="13D", end=END))
    assert len(only_13d) == 1 and only_13d.iloc[0]["Kind"] == "13D"


def test_off_exchange_share_is_worked_out_rather_than_left_to_the_reader(db):
    rows = scanner.run(db, "dark", scanner.Filters(days=30, end=END))
    assert rows.iloc[0]["Share %"] == 40.0


# --------------------------------------------------------------------------- counting and ordering

def test_the_count_uses_the_same_filters_as_the_rows(db):
    f = scanner.Filters(days=30, code="P", end=END)
    assert scanner.total(db, "insiders", f) == len(scanner.run(db, "insiders", f)) == 2


def test_a_limit_cuts_the_rows_but_not_the_count_so_the_screen_can_say_what_is_missing(db):
    f = scanner.Filters(days=365, end=END)
    assert len(scanner.run(db, "insiders", f, limit=2)) == 2
    assert scanner.total(db, "insiders", f) == 4


def test_the_newest_filing_comes_first(db):
    rows = scanner.run(db, "insiders", scanner.Filters(days=30, end=END))
    assert rows["Filed"].tolist() == sorted(rows["Filed"], reverse=True)
    assert rows["Filed"].iloc[0] == pd.Timestamp("2026-09-22")


def test_columns_come_back_named_by_their_heading_with_dates_as_dates(db):
    rows = scanner.run(db, "insiders", scanner.Filters(days=30, end=END))
    assert list(rows.columns) == [c.label for c in scanner.INSIDERS.columns]
    assert isinstance(rows["Filed"].iloc[0], pd.Timestamp)
    assert isinstance(rows["Traded"].iloc[0], pd.Timestamp)


# --------------------------------------------------------------------------- links and summary

def test_an_sec_row_links_to_its_filing_on_edgar(db):
    rows = scanner.run(db, "insiders", scanner.Filters(days=30, ticker="PFE", end=END))
    url = scanner.filing_link("insiders", rows.iloc[0]["Filing"])
    assert url == ("https://www.sec.gov/Archives/edgar/data/78003/000126100001/"
                   "0001-26-1-index.htm").replace("000126100001", "0001261")
    assert url.startswith("https://www.sec.gov/Archives/edgar/data/78003/")   # zeros stripped
    assert url.endswith("0001-26-1-index.htm")


def test_a_congressional_row_links_to_the_document_it_already_carries(db):
    rows = scanner.run(db, "congress", scanner.Filters(days=30, end=END))
    with_url = rows[rows["Ticker"] == "AVGO"].iloc[0]
    assert scanner.filing_link("congress", with_url["Filing"]).endswith("/D1.pdf")
    without = rows[rows["Ticker"] == "NVDA"].iloc[0]
    assert scanner.filing_link("congress", without["Filing"]) == ""


def test_a_row_with_nothing_to_link_to_gives_no_url(db):
    assert scanner.filing_link("insiders", "") == ""
    assert scanner.filing_link("insiders", "78003|") == ""
    assert scanner.filing_link("insiders", "|0001-26-1") == ""
    assert scanner.filing_link("insiders", None) == ""


def test_the_summary_says_what_has_been_collected_at_all(db):
    found = {label: (n, first, last) for label, n, first, last in scanner.summary(db)}
    assert found["Insiders (Form 4)"][0] == 4
    assert found["Insiders (Form 4)"][1] == "2026-01-05"
    assert found["Insiders (Form 4)"][2] == "2026-09-22"
    assert found["Congress"][0] == 2
    assert found["Daily prices"][0] == 0                 # nothing collected yet, and that is fine
    assert [s.label for s in scanner.SOURCES] == list(found)


def test_every_source_declares_only_filters_the_query_layer_knows(db):
    """A typo in a source's filter list would silently stop that filter narrowing anything."""
    known = {"dates", "ticker", "amount", "code", "role", "plan", "trade_type", "chamber", "member",
             "stake_kind", "passive", "option_type", "text", "new_position", "amendments",
             "contract_volume"}
    for source in scanner.SOURCES:
        assert set(source.filters) <= known, source.key
        assert "amount" not in source.filters or source.amount_column, source.key
        assert "ticker" not in source.filters or source.ticker_column, source.key
        # a free-text box that looks nowhere would silently return everything
        assert "text" not in source.filters or source.searchable, source.key
        # and each one actually runs against the real schema
        assert isinstance(scanner.total(db, source, scanner.Filters(days=30, end=END)), int)
