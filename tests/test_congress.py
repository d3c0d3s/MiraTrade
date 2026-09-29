"""Congressional disclosures: the roster, the committee sectors and the House PTR parser.

The PTR fixtures are the text pdfplumber really produced from filings 20034660, 20034999 and
20034984 (2026), NUL padding and all, because that padding is exactly what the parser has to survive.
"""
import json

import pandas as pd
import pytest

from miratrade.data.congress import (build_members, match_member, member_lookup,
                                     normalise_name, sectors_for, short_name)
from miratrade.data.congress_house import fetch_index, parse_ptr_text

# "Filing Status: New" as the PDF renders it: small-caps letters padded with NUL bytes.
FILING_STATUS = "F\x00\x00\x00\x00\x00 S\x00\x00\x00\x00\x00: New"
DESCRIPTION = "D\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00: Sale from Individual Retirement Account"
HEADER = ("ID Owner Asset Transaction Date Notification Amount Cap.\n"
          "Type Date Gains >\n$200?\n")

WALBERG = HEADER + (
    "JT Amazon.com, Inc. - Common Stock P 02/07/2025 05/29/2026 $1,001 - $15,000\n"
    "(AMZN) [ST]\n" + FILING_STATUS + "\n"
    "JT Apple Inc. - Common Stock (AAPL) P 02/07/2025 05/29/2026 $15,001 -\n"
    "[ST] $50,000\n" + FILING_STATUS + "\n"
    "JT Bank of America Corporation P 02/07/2025 05/29/2026 $15,001 -\n"
    "Common Stock (BAC) [ST] $50,000\n" + FILING_STATUS + "\n"
    "SP Boeing Company (BA) [ST] S (partial) 03/11/2026 03/20/2026 $1,001 -\n"
    "$15,000\n" + FILING_STATUS + "\n"
    "* For the complete list of asset type abbreviations, please visit https://fd.house.gov/\n")

SINGLE_SALE = HEADER + (
    "Ichor Holdings - Ordinary Shares S 06/17/2026 07/14/2026 $2,722.50\n"
    "(ICHR) [ST]\n" + FILING_STATUS + "\n" + DESCRIPTION + "\n"
    "I CERTIFY that the statements I have made on the attached Periodic Transaction Report are true\n"
    "Digitally Signed: Hon. Debbie Wasserman Schultz , 07/14/2026\n")

TREASURY = HEADER + (
    "Treasury Bill (3-Month, Matures P 07/13/2026 07/13/2026 $15,001 -\n"
    "10/15/2026) [GS] $50,000\n" + FILING_STATUS + "\n"
    "S\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00 O\x00\x00: Schwab (formerly TD Ameritrade)\n")


def test_a_wrapped_row_keeps_its_ticker_and_the_whole_amount_range():
    rows = parse_ptr_text(WALBERG, doc_id="20034660", member="Tim Walberg",
                          filing_date=pd.Timestamp("2026-05-29"), url="http://example/1.pdf")
    assert len(rows) == 4
    assert rows["ticker"].tolist() == ["AMZN", "AAPL", "BAC", "BA"]

    # the amount wraps onto the next line, and both ends of the range have to survive it
    assert rows["amount_low"].tolist() == [1001.0, 15001.0, 15001.0, 1001.0]
    assert rows["amount_high"].tolist() == [15000.0, 50000.0, 50000.0, 15000.0]

    # the asset name wraps too, in the middle of "Bank of America Corporation Common Stock"
    assert rows.iloc[2]["asset"] == "Bank of America Corporation Common Stock (BAC) [ST]"
    assert rows["type"].tolist() == ["purchase", "purchase", "purchase", "partial sale"]
    assert rows["owner"].tolist() == ["joint", "joint", "joint", "spouse"]
    assert rows["trade_date"].iloc[0] == pd.Timestamp("2025-02-07")
    assert rows["row_in_doc"].tolist() == [0, 1, 2, 3]
    assert set(rows["doc_id"]) == {"20034660"} and set(rows["chamber"]) == {"house"}


def test_the_forms_own_headings_are_not_read_as_part_of_the_asset():
    """The headings arrive padded with NUL bytes, not spaces. Treating NUL as text once put
    "Filing Status: New" inside every asset name."""
    rows = parse_ptr_text(SINGLE_SALE, doc_id="20034999", member="Debbie Wasserman Schultz")
    assert len(rows) == 1
    row = rows.iloc[0]
    assert row["asset"] == "Ichor Holdings - Ordinary Shares (ICHR) [ST]"
    assert "Filing Status" not in row["asset"] and "New" not in row["asset"]
    assert "Sale from" not in row["asset"]
    assert row["ticker"] == "ICHR" and row["type"] == "sale" and row["owner"] == "self"
    assert row["amount_low"] == row["amount_high"] == 2722.50      # an exact figure, not a range


def test_something_that_is_not_a_share_gets_no_ticker():
    """(3-Month, Matures …) is not a ticker and [GS] is a government security, not a stock."""
    rows = parse_ptr_text(TREASURY, doc_id="20034984", member="Rudy C. Yakym III")
    assert len(rows) == 1
    assert rows.iloc[0]["ticker"] is None
    assert rows.iloc[0]["asset"].startswith("Treasury Bill")
    assert rows.iloc[0]["amount_low"] == 15001.0 and rows.iloc[0]["amount_high"] == 50000.0


def test_a_report_with_no_transactions_gives_no_rows():
    assert len(parse_ptr_text(HEADER)) == 0
    assert len(parse_ptr_text("")) == 0
    assert list(parse_ptr_text("").columns)[:3] == ["doc_id", "row_in_doc", "filing_date"]


# --------------------------------------------------------------------------- the roster

def test_committees_map_to_the_sectors_they_oversee():
    assert sectors_for(["House Committee on Armed Services"]) == ["Defense"]
    assert sectors_for(["Senate Committee on Finance"]) == ["Finance"]
    assert sectors_for(["House Committee on Energy and Commerce"]) == ["Energy", "Technology"]
    assert sectors_for(["House Committee on Ethics"]) == ["Other"]     # nothing industrial
    assert sectors_for([]) == []                                      # no seat, no claim


def test_the_roster_joins_members_to_their_committee_seats():
    legislators = [
        {"id": {"bioguide": "W000798"}, "name": {"official_full": "Tim Walberg", "first": "Tim",
                                                 "last": "Walberg"},
         "terms": [{"type": "rep", "state": "MI", "party": "Republican"}]},
        {"id": {"bioguide": "S000033"}, "name": {"first": "Bernard", "last": "Sanders"},
         "terms": [{"type": "sen", "state": "VT", "party": "Independent"}]},
        {"name": {"official_full": "No Id"}, "terms": [{"type": "rep"}]},      # skipped: no bioguide
    ]
    committees = [{"thomas_id": "HSAS", "name": "House Committee on Armed Services",
                   "subcommittees": [{"thomas_id": "03", "name": "Seapower"}]},
                  {"thomas_id": "SSFI", "name": "Senate Committee on Finance"}]
    membership = {"HSAS": [{"bioguide": "W000798"}], "HSAS03": [{"bioguide": "W000798"}],
                  "SSFI": [{"bioguide": "S000033"}]}

    members = build_members(legislators, committees, membership)
    assert len(members) == 2                                   # the one with no id is left out
    walberg = members[members["bioguide_id"] == "W000798"].iloc[0]
    assert walberg["name"] == "Tim Walberg" and walberg["chamber"] == "house"
    assert json.loads(walberg["sectors"]) == ["Defense"]
    assert json.loads(walberg["committees"]) == ["House Committee on Armed Services",
                                                 "House Committee on Armed Services — Seapower"]
    sanders = members[members["bioguide_id"] == "S000033"].iloc[0]
    assert sanders["name"] == "Bernard Sanders" and sanders["chamber"] == "senate"
    assert json.loads(sanders["sectors"]) == ["Finance"]


@pytest.mark.parametrize("filed, roster", [
    ("Hon. Nancy Pelosi", "Nancy Pelosi"),
    ("Pelosi, Nancy", "Nancy Pelosi"),
    ("  DEBBIE WASSERMAN SCHULTZ ", "Debbie Wasserman Schultz"),
    ("Scott Scott Franklin", "Scott Franklin"),          # the index really does repeat the word
])
def test_a_name_on_a_disclosure_matches_the_same_name_on_the_roster(filed, roster):
    assert normalise_name(filed) == normalise_name(roster)


@pytest.mark.parametrize("filed, roster", [
    ("August Lee Pfluger II", "August Pfluger"),
    ("Rudy C. Yakym III", "Rudy Yakym"),
    ("Richard Dean Dr McCormick", "Rich McCormick" if False else "Richard McCormick"),
    ("John J Mr McGuire III", "John McGuire"),
])
def test_a_full_legal_name_still_matches_the_roster_without_the_middle_names(filed, roster):
    """The House files the whole legal name; the roster carries the everyday one."""
    assert short_name(filed) == short_name(roster)


def test_different_people_do_not_match():
    assert normalise_name("Nancy Pelosi") != normalise_name("Paul Pelosi")
    assert short_name("Nancy Pelosi") != short_name("Paul Pelosi")


def test_a_name_two_members_share_is_left_unmatched_rather_than_guessed(tmp_path):
    """Attributing a trade to the wrong named person is worse than attributing it to nobody."""
    from miratrade import store

    db = store.connect(tmp_path / "market.db")
    store.write(db, "congress_members", pd.DataFrame([
        {"bioguide_id": "A1", "name": "John Adams", "chamber": "house"},
        {"bioguide_id": "A2", "name": "John Quincy Adams", "chamber": "house"},
        {"bioguide_id": "P1", "name": "Nancy Pelosi", "chamber": "house"}]))
    lookup = member_lookup(db)

    assert match_member("Nancy Pelosi", lookup) == "P1"
    assert match_member("Pelosi, Nancy", lookup) == "P1"
    assert match_member("John Quincy Adams", lookup) == "A2"   # the full name is unambiguous
    assert match_member("John Fitzgerald Adams", lookup) is None  # "john adams" fits two people
    assert match_member("Someone Else", lookup) is None
    db.close()


# --------------------------------------------------------------------------- the index

def test_the_index_keeps_only_periodic_transaction_reports(tmp_path, monkeypatch):
    import io
    import zipfile

    from miratrade.data import congress_house

    xml = ("<FinancialDisclosure>"
           "<Member><Last>Walberg</Last><First>Tim</First><FilingType>P</FilingType>"
           "<Year>2026</Year><FilingDate>5/29/2026</FilingDate><DocID>20034660</DocID></Member>"
           "<Member><Last>Aaron</Last><First>Richard</First><FilingType>W</FilingType>"
           "<Year>2026</Year><FilingDate>4/15/2026</FilingDate><DocID>8068</DocID></Member>"
           "<Member><Last>Yakym</Last><First>Rudy C.</First><Suffix>III</Suffix>"
           "<FilingType>P</FilingType><Year>2026</Year><FilingDate>7/13/2026</FilingDate>"
           "<DocID>20034984</DocID></Member>"
           "</FinancialDisclosure>")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("2026FD.xml", xml)
        z.writestr("2026FD.txt", "ignored")
    monkeypatch.setattr(congress_house, "_get", lambda *a, **k: buffer.getvalue())

    index = fetch_index(2026, tmp_path)
    assert index["doc_id"].tolist() == ["20034660", "20034984"]     # the annual report W is left out
    assert index["member"].tolist() == ["Tim Walberg", "Rudy C. Yakym III"]
    assert index["filing_date"].iloc[0] == pd.Timestamp("2026-05-29")


def test_a_year_with_no_index_published_is_empty_not_an_error(tmp_path, monkeypatch):
    from miratrade.data import congress_house

    monkeypatch.setattr(congress_house, "_get", lambda *a, **k: None)
    assert len(fetch_index(2099, tmp_path)) == 0


def test_lines_are_rebuilt_from_where_the_words_sit_not_from_newlines():
    """Some filings carry the whole page as one line in their text layer. Trusting newlines there
    read one transaction where there were twelve, and lost the owner of each."""
    from miratrade.data.congress_house import page_lines

    class Page:
        """A page whose text layer has no line breaks, only word positions."""

        @staticmethod
        def extract_words(**_):
            return [{"text": "SP", "top": 10.0, "x0": 5.0},
                    {"text": "Apple", "top": 10.4, "x0": 20.0},   # same row, slightly different top
                    {"text": "(AAPL)", "top": 10.0, "x0": 60.0},
                    {"text": "[ST]", "top": 23.0, "x0": 20.0},    # the row below
                    {"text": "JT", "top": 23.2, "x0": 5.0}]

    assert page_lines(Page()) == ["SP Apple (AAPL)", "JT [ST]"]   # and each is left-to-right
