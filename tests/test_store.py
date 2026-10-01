"""The shared market database: a round trip has to be lossless and a re-parse must not duplicate."""
from datetime import date

import pandas as pd
import pytest

from miratrade.store import (SCHEMA_VERSION, SchemaTooNew, connect, counts, covered, gaps,
                             mark_covered, migrate, note, notes, prices, read, version, write)


@pytest.fixture
def db(tmp_path):
    conn = connect(tmp_path / "market.db")
    yield conn
    conn.close()


def _insiders(accession="0001-26-000001", price=26.34, shares=38000.0):
    return pd.DataFrame([{
        "accession": accession, "filing_date": pd.Timestamp("2026-08-14"),
        "trade_date": pd.Timestamp("2026-08-12"), "ticker": "PFE", "issuer": "PFIZER INC",
        "issuer_cik": "78003", "owner": "BOURLA ALBERT", "owner_cik": "0001560011",
        "is_officer": True, "is_director": False, "is_ten_pct": False, "title": "CEO",
        "code": "P", "shares": shares, "price": price, "value": shares * price,
        "owned_after": 500000.0, "delta_own_pct": 0.082, "plan_10b5_1": False}])


def test_a_new_file_gets_the_schema_and_says_so(tmp_path):
    path = tmp_path / "sub" / "market.db"
    conn = connect(path)                                 # the folder is created on the way
    assert path.exists() and version(conn) == SCHEMA_VERSION
    assert notes(conn)["written_by"] == "MiraTrade" and "created_at" in notes(conn)
    assert counts(conn)["insiders"] == 0 and "congress_trades" in counts(conn)
    conn.close()

    again = connect(path)                                # opening it twice changes nothing
    assert version(again) == SCHEMA_VERSION
    again.close()


def test_a_file_from_a_newer_miratrade_is_refused_instead_of_misread(db):
    note(db, "schema_version", str(SCHEMA_VERSION + 5))
    with pytest.raises(SchemaTooNew, match="update MiraTrade"):
        migrate(db)


def test_insider_rows_survive_the_round_trip_with_their_types(db):
    assert write(db, "insiders", _insiders()) == 1
    back = read(db, "insiders")
    assert len(back) == 1
    row = back.iloc[0]
    assert row["ticker"] == "PFE" and row["code"] == "P"
    assert row["price"] == 26.34 and row["value"] == pytest.approx(38000 * 26.34)
    assert row["filing_date"] == pd.Timestamp("2026-08-14")     # a date again, not text
    assert row["trade_date"] == pd.Timestamp("2026-08-12")
    assert bool(row["is_officer"]) is True and bool(row["plan_10b5_1"]) is False


def test_parsing_a_filing_again_replaces_it_instead_of_duplicating_it(db):
    """A parser fix changes a price by a cent; the filing must still appear once."""
    write(db, "insiders", _insiders(price=26.34))
    write(db, "insiders", _insiders(price=26.35))
    back = read(db, "insiders")
    assert len(back) == 1 and back.iloc[0]["price"] == 26.35

    write(db, "insiders", _insiders(accession="0001-26-000002"))   # a different filing is its own row
    assert len(read(db, "insiders")) == 2


def test_writing_nothing_is_not_an_error_and_writes_nothing(db):
    assert write(db, "insiders", None) == 0
    assert write(db, "insiders", pd.DataFrame()) == 0
    assert len(read(db, "insiders")) == 0


def test_an_unknown_table_or_unrelated_columns_fail_loudly(db):
    with pytest.raises(KeyError, match="market database"):
        write(db, "not_a_table", _insiders())
    with pytest.raises(ValueError, match="match the columns"):
        write(db, "insiders", pd.DataFrame([{"nothing": 1}]))


def test_prices_go_in_from_the_index_and_come_back_the_same_shape(db):
    idx = pd.date_range("2026-09-01", periods=3, freq="B")
    bars = pd.DataFrame({"open": [10.0, 11, 12], "high": [11.0, 12, 13], "low": [9.0, 10, 11],
                         "close": [10.5, 11.5, 12.5], "volume": [1e6, 2e6, 3e6]}, index=idx)
    bars.index.name = "date"
    assert write(db, "prices", bars.assign(ticker="ACME", source="schwab")) == 3

    out = prices(db)
    assert list(out) == ["ACME"]
    got = out["ACME"]
    assert list(got.index) == list(idx) and got.index.name == "date"
    assert list(got.columns) == ["open", "high", "low", "close", "volume"]
    assert got["close"].iloc[-1] == 12.5

    assert prices(db, ["NOPE"]) == {} and prices(db, []) == {}
    assert len(prices(db, ["ACME"], start=idx[1])["ACME"]) == 2
    assert len(prices(db, ["acme"], end=idx[0])["ACME"]) == 1      # the ticker is upper-cased


def test_a_second_app_can_read_the_file_but_not_change_it(tmp_path):
    path = tmp_path / "market.db"
    writer = connect(path)
    write(writer, "insiders", _insiders())
    writer.close()

    reader = connect(path, read_only=True)
    assert len(read(reader, "insiders")) == 1
    with pytest.raises(Exception):                       # sqlite3.OperationalError: readonly database
        write(reader, "insiders", _insiders(accession="0001-26-000003"))
    reader.close()


def test_reading_a_database_that_is_not_there_fails_instead_of_creating_one(tmp_path):
    with pytest.raises(Exception):
        connect(tmp_path / "missing.db", read_only=True)
    assert not (tmp_path / "missing.db").exists()


def test_coverage_remembers_a_day_that_produced_nothing(db):
    days = [date(2026, 9, 21), date(2026, 9, 22), date(2026, 9, 23)]
    assert gaps(db, "sec_form4", days) == days

    mark_covered(db, "sec_form4", days[:2], rows=0)       # a weekend: asked, nothing filed
    assert covered(db, "sec_form4") == {"2026-09-21", "2026-09-22"}
    assert gaps(db, "sec_form4", days) == [days[2]]       # and it is not asked again

    mark_covered(db, "prices", days[:1], rows=1, scope="ACME")
    assert gaps(db, "sec_form4", days) == [days[2]]       # a scope has its own coverage
    assert covered(db, "prices", scope="ACME") == {"2026-09-21"}
    assert covered(db, "prices") == set()


def test_marking_the_same_day_twice_updates_it_rather_than_failing(db):
    mark_covered(db, "sec_form4", [date(2026, 9, 21)], rows=0)
    mark_covered(db, "sec_form4", [date(2026, 9, 21)], rows=412)
    rows = read(db, "coverage")
    assert len(rows) == 1 and rows.iloc[0]["rows"] == 412
    mark_covered(db, "sec_form4", [])                    # nothing to mark is not an error
    assert len(read(db, "coverage")) == 1


def test_a_filter_runs_in_the_database_instead_of_loading_everything(db):
    write(db, "insiders", _insiders())
    write(db, "insiders", _insiders(accession="0001-26-000009").assign(ticker="KLTR", code="S"))
    buys = read(db, "insiders", "code = ? AND ticker = ?", ("P", "PFE"))
    assert len(buys) == 1 and buys.iloc[0]["ticker"] == "PFE"
    assert len(read(db, "insiders", "code = ?", ("S",))) == 1


def test_the_same_transaction_filed_twice_is_stored_once(db):
    """EDGAR's daily index lists a Form 4 under both the company's CIK and the insider's, so the
    same rows can arrive twice in one frame. They are one transaction, not two."""
    twice = pd.concat([_insiders(), _insiders()], ignore_index=True)
    assert write(db, "insiders", twice) == 1
    assert len(read(db, "insiders")) == 1

    # two genuinely different lots of the same filing are both kept
    lots = pd.concat([_insiders(shares=1000.0), _insiders(shares=2000.0)], ignore_index=True)
    write(db, "insiders", lots)
    assert sorted(read(db, "insiders")["shares"]) == [1000.0, 2000.0]


def test_price_bars_keep_their_day_whatever_the_index_is_called(db):
    """Bars carry the day in the index. One frame names it "date" and another does not; dropping the
    unnamed one turned a whole download into rows with no day at all."""
    idx = pd.date_range("2026-09-01", periods=3, freq="B")
    bars = pd.DataFrame({"open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 10.0},
                        index=idx)

    assert bars.index.name is None
    assert write(db, "prices", bars.assign(ticker="NONAME")) == 3

    named = bars.copy()
    named.index.name = "date"
    assert write(db, "prices", named.assign(ticker="NAMED")) == 3

    out = prices(db)
    assert list(out["NONAME"].index) == list(idx) == list(out["NAMED"].index)
    assert len(read(db, "prices", "date IS NULL")) == 0


def test_a_version_1_database_is_upgraded_without_losing_its_rows(tmp_path):
    """The real database already held 41,000 insider rows when option_flow gained `source`.
    A migration that loses them, or that leaves the file between two versions, is not acceptable."""
    import sqlite3

    from miratrade.store.schema import SCHEMA_VERSION

    path = tmp_path / "v1.db"
    old = sqlite3.connect(path)
    with old:                                   # the version 1 shape, by hand
        old.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        old.execute("INSERT INTO meta VALUES ('schema_version', '1')")
        old.execute("CREATE TABLE option_flow (date TEXT NOT NULL, ticker TEXT NOT NULL, "
                    "expiry TEXT NOT NULL, type TEXT NOT NULL, strike REAL NOT NULL, volume REAL, "
                    "open_interest REAL, premium REAL, underlying REAL, side TEXT, "
                    "PRIMARY KEY (date, ticker, expiry, type, strike))")
        old.execute("INSERT INTO option_flow VALUES ('2026-09-25','ACME','2026-11-20','call',10.0,"
                    "300,1200,33000,11.0,'')")
        old.execute("CREATE TABLE insiders (accession TEXT, ticker TEXT, filing_date TEXT)")
        old.execute("INSERT INTO insiders VALUES ('0001-26-1','PFE','2026-08-14')")
    old.close()

    conn = connect(path)
    assert version(conn) == SCHEMA_VERSION      # stepped all the way up, in one go
    # every column each later version added is there, whatever order they ended up in
    columns = {r["name"] for r in conn.execute("PRAGMA table_info(option_flow)")}
    assert {"source", "bid", "ask"} <= columns

    flow = read(conn, "option_flow")
    assert len(flow) == 1                                   # carried across, not dropped
    assert flow.iloc[0]["ticker"] == "ACME" and flow.iloc[0]["open_interest"] == 1200
    assert flow.iloc[0]["source"] == ""                      # unknown, because version 1 never said
    assert pd.isna(flow.iloc[0]["bid"]) and pd.isna(flow.iloc[0]["ask"])   # version 1 had no quotes
    assert len(read(conn, "insiders")) == 1                  # and nothing else was touched
    assert not conn.execute("SELECT name FROM sqlite_master WHERE name='option_flow_v1'").fetchall()
    conn.close()

    again = connect(path)                                    # opening it again is not a second migration
    assert version(again) == SCHEMA_VERSION and len(read(again, "option_flow")) == 1
    again.close()


def test_a_database_that_is_not_there_says_so_by_name(tmp_path):
    """"unable to open database file" tells a person neither what is missing nor where it looked."""
    from miratrade.store import NoDatabase

    with pytest.raises(NoDatabase, match="no market database at"):
        connect(tmp_path / "missing.db", read_only=True)
    assert not (tmp_path / "missing.db").exists()       # and it does not create an empty one


def test_a_reader_still_opens_a_wal_database_whose_shm_is_gone(tmp_path):
    """A read-only connection cannot build the -shm file a WAL database needs, so it fails with a
    bare "unable to open database file" after a crash or while a writer is busy. The app must still
    be able to read: what keeps it from writing is its own code, not the file mode."""
    path = tmp_path / "market.db"
    writer = connect(path)
    write(writer, "insiders", _insiders())
    writer.close()
    for leftover in ("market.db-shm", "market.db-wal"):
        if (tmp_path / leftover).exists():
            (tmp_path / leftover).unlink()

    reader = connect(path, read_only=True)
    assert len(read(reader, "insiders")) == 1
    reader.close()


def test_adding_a_column_twice_is_not_an_error(tmp_path):
    """The trap this project documented at version 2 and walked into anyway at version 8.

    `schema.py` describes the table as it is TODAY and `migrate` runs that DDL first, so a database
    that never had the table gets it already carrying the new columns — and a bare ALTER then dies
    with "duplicate column name" on a file that was perfectly fine. A step that can be skipped when
    it is unnecessary is the shape that does not have the problem.
    """
    import sqlite3

    from miratrade.store.db import _step

    conn = sqlite3.connect(tmp_path / "x.db")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE t (a TEXT)")

    _step(conn, ("+column", "t", "b", "TEXT"))
    _step(conn, ("+column", "t", "b", "TEXT"))        # again: must not raise
    assert {r["name"] for r in conn.execute("PRAGMA table_info(t)")} == {"a", "b"}

    _step(conn, "ALTER TABLE t ADD COLUMN c TEXT")    # plain SQL still works
    assert "c" in {r["name"] for r in conn.execute("PRAGMA table_info(t)")}

    with pytest.raises(ValueError, match="unknown migration step"):
        _step(conn, ("+index", "t", "b", "TEXT"))
    conn.close()


def test_a_database_from_every_old_version_reaches_the_newest(tmp_path):
    """Not just v1: each step has to survive being reached from wherever a file happens to be."""
    import sqlite3

    from miratrade.store import db as store_db

    for start in range(1, store_db.SCHEMA_VERSION):
        path = tmp_path / f"v{start}.db"
        raw = sqlite3.connect(path)
        raw.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        raw.execute("INSERT INTO meta VALUES ('schema_version', ?)", (str(start),))
        raw.commit()
        raw.close()

        conn = connect(path)
        assert version(conn) == store_db.SCHEMA_VERSION, f"desde v{start}"
        conn.close()
