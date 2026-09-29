"""The shape of the shared market database.

One SQLite file holds everything MiraTrade downloads and everything it works out from it, so a
second app can open the same file and read it without downloading anything again. That is why the
schema is a contract, not an implementation detail:

* every column name matches the name the rest of the code already uses (``INSIDER_COLUMNS`` and
  friends), so a DataFrame goes in and comes back the same;
* dates are ISO text (``YYYY-MM-DD``), which sorts correctly and reads the same from any language;
* booleans are 0/1 integers, money is in dollars, and nothing is pickled — a foreign reader needs
  no Python to make sense of a row;
* ``filing_date`` is when a fact became public and is the only date a backtest may condition on;
  ``trade_date`` is when the transaction happened and is usually earlier.

Any change to a table raises :data:`SCHEMA_VERSION` and adds a migration in ``db.py`` — including
adding a column, because the DDL below only creates tables that do not exist yet, so a database
already on disk gains a new column from its migration and from nowhere else. What is cheap about
adding a table or a nullable column is that a *reader* written against the older version keeps
working; renaming or dropping one breaks it. ``docs/DATA.md`` documents the tables for whoever
writes that second app.
"""
from __future__ import annotations

SCHEMA_VERSION = 5

# Ordinary tables, created in this order.
TABLES: dict[str, str] = {
    # ------------------------------------------------------------------ housekeeping
    "meta": """
        CREATE TABLE IF NOT EXISTS meta (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )""",
    # Every setting a person can change, one row per setting rather than one blob, so two clients
    # can each change a different thing without one silently undoing the other — which is what a
    # whole-file save does the moment the app and the web front-end are both open.
    #
    # `value` is JSON so a list, a boolean and a number all come back as what they were: `false`
    # read from plain text is the string "false", which is true, and that is how a limit gets
    # quietly disabled.
    "settings": """
        CREATE TABLE IF NOT EXISTS settings (
            section    TEXT NOT NULL,      -- a section of Config: risk, data, insider, flow…
            key        TEXT NOT NULL,      -- a field of that section
            value      TEXT NOT NULL,      -- JSON-encoded value
            updated_at TEXT NOT NULL,
            PRIMARY KEY (section, key)
        )""",
    # Which days (or tickers) have already been downloaded per source, so a run fetches only the
    # gaps. A row means "asked and answered", including an answer of nothing at all — without that
    # a quiet day would be re-downloaded for ever.
    "coverage": """
        CREATE TABLE IF NOT EXISTS coverage (
            source     TEXT NOT NULL,      -- sec_form4, sec_13dg, prices, finra_short, congress_house…
            scope      TEXT NOT NULL,      -- a ticker or a member for per-name sources, '' for the rest
            day        TEXT NOT NULL,      -- ISO date the coverage is about
            rows       INTEGER NOT NULL,   -- how many rows that day produced (0 is a real answer)
            fetched_at TEXT NOT NULL,      -- ISO timestamp of the download
            PRIMARY KEY (source, scope, day)
        )""",
    # ------------------------------------------------------------------ SEC filings
    # Form 4 non-derivative transactions. Code P is an open-market purchase, S a sale; A, M, F and G
    # are awards, exercises, tax withholding and gifts, which say nothing about conviction.
    "insiders": """
        CREATE TABLE IF NOT EXISTS insiders (
            accession     TEXT NOT NULL,   -- SEC accession number: identifies the filing
            filing_date   TEXT NOT NULL,   -- when it became public
            trade_date    TEXT,            -- when the transaction happened
            ticker        TEXT NOT NULL,
            issuer        TEXT,
            issuer_cik    TEXT,
            owner         TEXT,            -- the insider's name as filed
            owner_cik     TEXT,
            is_officer    INTEGER,
            is_director   INTEGER,
            is_ten_pct    INTEGER,
            title         TEXT,            -- officer title as filed, e.g. "CEO"
            code          TEXT,            -- Form 4 transaction code
            shares        REAL,
            price         REAL,            -- dollars per share
            value         REAL,            -- shares × price
            owned_after   REAL,
            delta_own_pct REAL,            -- purchase as a share of what they held before (1.0 = new)
            plan_10b5_1   INTEGER          -- the Form 4 checkbox, filled in since 2023
        )""",
    # Schedule 13D (active intent) and 13G (passive) filings: someone crossed 5 % of a company.
    "ownership": """
        CREATE TABLE IF NOT EXISTS ownership (
            accession   TEXT NOT NULL,
            filing_date TEXT NOT NULL,
            ticker      TEXT NOT NULL,
            subject_cik TEXT,              -- the company the stake is in
            filer       TEXT,              -- who filed it
            kind        TEXT,              -- 13D or 13G
            amendment   INTEGER,           -- an /A amends an earlier filing
            passive     INTEGER            -- 13G from an index fund: no intent to act
        )""",
    # Shares outstanding as reported to SEC XBRL, used with the close to get market capitalisation
    # on a given day without a lookahead.
    "shares_outstanding": """
        CREATE TABLE IF NOT EXISTS shares_outstanding (
            ticker TEXT NOT NULL,
            filed  TEXT NOT NULL,          -- when the figure was reported
            shares REAL NOT NULL,
            PRIMARY KEY (ticker, filed)
        )""",
    # ------------------------------------------------------------------ market data
    # Daily bars. Which source they came from is in `source`, because a licence follows the data:
    # 'schwab' is the user's own broker account, 'research' is Yahoo/Stooq and is personal use only.
    "prices": """
        CREATE TABLE IF NOT EXISTS prices (
            ticker TEXT NOT NULL,
            date   TEXT NOT NULL,
            open   REAL, high REAL, low REAL, close REAL, volume REAL,
            source TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (ticker, date)
        )""",
    # FINRA daily off-exchange volume: what traded away from the exchanges (dark pools, ATSs,
    # wholesalers). It is NOT short interest, and it is a third to a half of consolidated volume.
    "short_volume": """
        CREATE TABLE IF NOT EXISTS short_volume (
            date         TEXT NOT NULL,
            ticker       TEXT NOT NULL,
            short_volume REAL,
            total_volume REAL,
            PRIMARY KEY (date, ticker)
        )""",
    # Option activity, one row per contract per day.
    #
    # `source` matters more here than anywhere else, because the sources are not interchangeable. A
    # broker chain snapshot has volume AND open interest but no aggressor side; the free Massive
    # history has volume but NO open interest; a paid flow feed has the side and each individual
    # print. Mixing them in one series without knowing which is which would show a change in the
    # data as though it were a change in the market — which is how a false edge gets manufactured.
    "option_flow": """
        CREATE TABLE IF NOT EXISTS option_flow (
            date          TEXT NOT NULL,
            ticker        TEXT NOT NULL,
            expiry        TEXT NOT NULL,
            type          TEXT NOT NULL,  -- call or put
            strike        REAL NOT NULL,
            volume        REAL,
            open_interest REAL,           -- NULL where the source has no OI history
            premium       REAL,           -- dollars: volume × mid × 100
            underlying    REAL,
            bid           REAL,           -- what you would be paid to sell it right now
            ask           REAL,           -- what you would pay to buy it right now
            side          TEXT,           -- ask, bid or mid, where the source distinguishes them
            source        TEXT NOT NULL DEFAULT '',   -- schwab, etrade, massive, or a paid feed
            PRIMARY KEY (date, ticker, expiry, type, strike, source)
        )""",
    # When companies report. Implied volatility rises into a known earnings date and collapses after
    # it, so a call can be right about the direction and still lose — and the gap can jump straight
    # through a stop. A trade that has to cross one of these dates is a different trade.
    "earnings": """
        CREATE TABLE IF NOT EXISTS earnings (
            ticker       TEXT NOT NULL,
            report_date  TEXT NOT NULL,   -- when the company reports, or reported
            fiscal_end   TEXT,            -- the quarter it covers
            when_of_day  TEXT,            -- pre-market, post-market, or unknown
            estimate     REAL,            -- consensus EPS, where there is one
            reported     REAL,            -- actual EPS, once the quarter is out
            surprise_pct REAL,
            source       TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (ticker, report_date)
        )""",
    # ------------------------------------------------------------------ congressional disclosures
    # LEGAL (personal use only): the Ethics in Government Act, 5 U.S.C. app. § 105(c), makes it
    # unlawful to obtain or use these reports for any commercial purpose other than by news media.
    # These two tables and everything that reads them must come out, or be separately cleared,
    # before MiraTrade is sold. Nothing else in this database carries that restriction.
    "congress_members": """
        CREATE TABLE IF NOT EXISTS congress_members (
            bioguide_id TEXT PRIMARY KEY,  -- the member's id in the House/Senate biographical directory
            name        TEXT NOT NULL,
            chamber     TEXT,              -- house or senate
            party       TEXT,
            state       TEXT,
            committees  TEXT,              -- JSON array of committee names
            sectors     TEXT,              -- JSON array: the sectors those committees oversee
            updated     TEXT               -- when this row was last refreshed
        )""",
    "congress_trades": """
        CREATE TABLE IF NOT EXISTS congress_trades (
            doc_id      TEXT NOT NULL,     -- the disclosure document's id at the House or Senate
            row_in_doc  INTEGER NOT NULL,  -- transactions are only unique within their document
            filing_date TEXT NOT NULL,     -- when the disclosure was filed: up to 45 days late
            trade_date  TEXT,              -- when the transaction happened
            member      TEXT NOT NULL,
            bioguide_id TEXT,              -- joins congress_members when the name could be matched
            chamber     TEXT,
            ticker      TEXT,
            asset       TEXT,              -- the asset as described, when there is no ticker
            type        TEXT,              -- purchase, sale, exchange
            owner       TEXT,              -- self, spouse, joint, dependent child
            amount_low  REAL,              -- disclosed as a range, never an exact figure
            amount_high REAL,
            filing_url  TEXT,              -- the original document, so a reader can check it
            PRIMARY KEY (doc_id, row_in_doc)
        )""",
    # ------------------------------------------------------------------ what MiraTrade works out
    # One row per ticker per day on which something happened, with the flags the screens filter on.
    # `flags` is a JSON object so a new condition does not need a migration; the columns beside it
    # are the ones worth indexing.
    "events": """
        CREATE TABLE IF NOT EXISTS events (
            ticker      TEXT NOT NULL,
            signal_date TEXT NOT NULL,
            insider_buy INTEGER NOT NULL DEFAULT 0,
            flow        INTEGER NOT NULL DEFAULT 0,
            ownership   INTEGER NOT NULL DEFAULT 0,
            congress    INTEGER NOT NULL DEFAULT 0,
            mkt_cap     REAL,              -- market capitalisation that day, for the size filter
            close       REAL,
            what        TEXT,              -- the English sentence, for a console or another app
            what_parts  TEXT,              -- JSON [[template, fields], …] so a screen can translate it
            flags       TEXT,              -- JSON object of every condition that was true
            PRIMARY KEY (ticker, signal_date)
        )""",
}

INDEXES = (
    "CREATE INDEX IF NOT EXISTS insiders_ticker_filed ON insiders (ticker, filing_date)",
    "CREATE INDEX IF NOT EXISTS insiders_accession ON insiders (accession)",
    "CREATE INDEX IF NOT EXISTS insiders_filed ON insiders (filing_date)",
    "CREATE INDEX IF NOT EXISTS ownership_ticker_filed ON ownership (ticker, filing_date)",
    "CREATE INDEX IF NOT EXISTS ownership_accession ON ownership (accession)",
    "CREATE INDEX IF NOT EXISTS prices_date ON prices (date)",
    "CREATE INDEX IF NOT EXISTS congress_trades_ticker ON congress_trades (ticker, filing_date)",
    "CREATE INDEX IF NOT EXISTS congress_trades_member ON congress_trades (member, filing_date)",
    "CREATE INDEX IF NOT EXISTS events_date ON events (signal_date)",
)

# Tables whose rows belong to a document: writing that document again replaces its rows instead of
# adding near-duplicates, which is what makes a re-parse safe.
BY_DOCUMENT = {"insiders": ("accession",), "ownership": ("accession",), "congress_trades": ("doc_id",)}
