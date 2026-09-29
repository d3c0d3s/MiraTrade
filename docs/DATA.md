# The shared market database

Everything MiraTrade downloads and everything it works out from it lives in **one SQLite file**, so
another Mirandas Group app can read it without downloading anything again.

```
%APPDATA%\MirandasGroup\market.db          Windows
~/.config/MirandasGroup/market.db          elsewhere (whatever APPDATA/home resolves to)
```

Override with `MIRANDAS_DATA` (the folder) or `MIRATRADE_DB` (the file). To see what is there:

```bash
miratrade store info
```

The desktop app's **Scanner** screen is the view of this database: every source, filtered in SQL,
with a button that opens the original filing and another that exports the rows shown. Signals,
Reports and Practice read the same data but apply strategy to it; the Scanner applies none.

## Reading it from another app

It is plain SQLite with no extensions, so any language opens it. Open it **read-only** so your app
can never corrupt MiraTrade's copy, and so a wrong path fails instead of silently creating an empty
database.

```python
import sqlite3

db = sqlite3.connect("file:%APPDATA%/MirandasGroup/market.db?mode=ro", uri=True)
db.row_factory = sqlite3.Row
for row in db.execute("SELECT ticker, filing_date, owner, value FROM insiders "
                      "WHERE code='P' AND value >= 250000 AND filing_date >= '2026-09-01' "
                      "ORDER BY value DESC LIMIT 10"):
    print(dict(row))
```

With MiraTrade installed you get the DataFrame helpers instead:

```python
from miratrade import store

with store.connect(read_only=True) as db:
    buys = store.read(db, "insiders", "code = 'P' AND filing_date >= ?", ("2026-09-01",))
    bars = store.prices(db, ["PFE", "AAPL"], start="2026-01-01")   # {ticker: DataFrame}
```

## Conventions that hold everywhere

| | |
|---|---|
| Dates | ISO text, `YYYY-MM-DD`. They sort correctly as text and read the same in any locale. |
| Booleans | `0` / `1` integers. |
| Money | US dollars, as filed. Congressional amounts are **ranges**, never exact. |
| Missing | SQL `NULL`, never `0`, `""` or `NaN`. |
| Nothing pickled | Every column is text, integer or real. No Python needed to read a row. |
| `filing_date` | When the fact became **public**. The only date a backtest may condition on. |
| `trade_date` | When the transaction happened. Usually earlier — sometimes much earlier. |

## Tables

### `insiders` — SEC Form 4 transactions

One row per non-derivative transaction line. `code` is the Form 4 transaction code: **`P` is an
open-market purchase** and `S` a sale; `A`, `M`, `F` and `G` are awards, option exercises, tax
withholding and gifts, and say nothing about conviction. `plan_10b5_1` is the Form 4 checkbox,
filled in since 2023 — a purchase under a pre-set plan is not a decision made that week.
`delta_own_pct` is the purchase as a share of what the insider already held (`1.0` = a new position).

Form 4 is filed within two business days, so `filing_date` is close to `trade_date`. Rows are keyed
by nothing: writing a filing again replaces every row of that `accession`, so re-parsing is safe.

**This table is raw, as filed.** It still contains what filers typed wrong and what is not a share:
placeholder tickers (`NONE`), mutual funds (`PBLSX`), rows carrying two tickers (`LEN, LEN.B`), and
the classic error of typing the *total* amount into the price field. MiraTrade filters those when it
reads (`miratrade.data.sec.clean_insiders`), and keeps the raw rows here so another app can decide for
itself. Filter before you total anything.

### `ownership` — Schedule 13D / 13G

Someone crossed 5 % of a company. `kind` is `13D` (active intent — activists) or `13G` (passive).
`passive` marks a 13G from an index fund, which is a mechanical consequence of fund flows and not a
view on the company. `amendment` marks an `/A`.

### `prices` — daily bars

`source` records where a bar came from, because **the licence follows the data**: `schwab` is the
user's own broker account, `research` is Yahoo/Stooq and is personal, non-commercial research only.
Do not redistribute `research` bars or use them in anything sold. One row per ticker per day; a later
download of the same day replaces the earlier one, which is what you want after a split.

### `short_volume` — FINRA off-exchange volume

What traded away from the exchanges (dark pools, ATSs, wholesalers). **It is not short interest**,
and it is normally a third to a half of consolidated volume, so a "high" reading means high *for that
ticker*, not high in absolute terms.

### `shares_outstanding`

As reported to SEC XBRL, with the date it was reported, so market capitalisation on a past day can be
computed from the shares that were *known* that day rather than today's.

### `option_flow`

One row per contract per day. `premium` is dollars (`volume × mid × 100`). `side` says whether the
volume leaned to the ask, the bid or neither, when the source distinguishes them.

### `events` — what MiraTrade worked out

One row per ticker per day on which something happened, with `insider_buy` / `flow` / `ownership` /
`congress` flags and the market capitalisation that day. `flags` is a JSON object holding every
condition that was true, so new conditions need no migration. `what` is an English sentence for a
console or another app; `what_parts` is the same sentence as `[[template, fields], …]` so a screen can
show it in the user's language.

### `congress_members`, `congress_trades` — ⚠ personal use only

**Legal restriction.** Congressional financial disclosures are governed by the Ethics in Government
Act, **5 U.S.C. app. § 105(c)**. It is unlawful to obtain or use a report:

- for any unlawful purpose;
- **for any commercial purpose**, other than by news and communications media for dissemination to
  the general public;
- for determining or establishing anyone's credit rating;
- in the solicitation of money for any political, charitable or other purpose.

The Attorney General may bring a civil action for up to **$10,000 per violation**. MiraTrade is
personal software for its own user, which is what makes these two tables allowed. **They are the only
part of this database under that restriction, and they must be removed — or separately cleared —
before MiraTrade is sold to anyone.** Nothing else here is affected: SEC Form 4 is Section 16
securities law and carries no such limit.

That is why the code is quarantined: `miratrade/data/congress*.py`, `miratrade/congress_cli.py`, the
two tables above, and the `congress` extra in `pyproject.toml`. Removing those and the `congress`
column from `events` removes the restriction.

What the data is worth before trusting it:

- **The lag is 30 to 45 days.** The STOCK Act gives members that long to file, and many use all of
  it. `trade_date` and `filing_date` both being stored means you can measure the lag per row instead
  of assuming it. For an options horizon of 30 to 60 days this is a *slow* signal — much slower than
  a Form 4, which arrives in two business days.
- **Amounts are ranges.** `amount_low` and `amount_high` bracket the disclosed band; there is no
  exact figure to be had.
- **`owner`** is `self`, `spouse`, `joint` or `dependent child`.
- **`bioguide_id`** joins `congress_members`, where `committees` and `sectors` are JSON arrays. The
  sector is the industry a member's committees oversee — a keyword judgement, not a fact. A member of
  the Armed Services Committee buying a defence contractor is different evidence from the same member
  buying a supermarket; that is the whole point of keeping it.
  **As it stands the mapping is too coarse to carry information**: a member on several committees
  comes out tagged with five of the seven sectors, so "their committee covers this sector" is almost
  always true and therefore says nothing. Narrow it before building a signal on it.
- **`ticker` is `NULL` for anything that is not a share or an option.** Treasury bills, funds and
  property are stored with their `asset` text and no ticker.
- **A few filings are scans** with no text layer. They are skipped, counted and reported, never
  silently dropped.
- `filing_url` is the original document, so any row can be checked against the source.

### `coverage` — what has already been downloaded

`(source, scope, day)` with the row count and when it was fetched. A row means *asked and answered*,
including an answer of nothing at all — without that, a quiet day would be re-downloaded for ever.
`source` is `sec_form4`, `congress_house`, `prices` and so on; `scope` is a ticker or a document id
for per-name sources and `''` for the rest. This is what makes a run fetch only the gaps.

### `meta`

`schema_version`, `created_at`, and notes such as `congress_members_updated`.

## Versioning

`schema_version` is currently **1**. Adding a table or a nullable column does not break a reader and
does not raise it. Renaming or dropping does, and raises it with a migration in
`miratrade/store/db.py`. A file written by a newer MiraTrade is **refused** rather than misread.

Check it before reading, so your app fails with a clear message rather than a wrong answer:

```python
row = db.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
assert int(row[0]) == 1, f"this app understands schema 1, the database is at {row[0]}"
```

## Concurrency

The database is in WAL mode with a 30-second busy timeout: readers never block the writer, and a
second writer waits its turn instead of failing. Several processes can hold it open at once — the
desktop app, an analysis it started, the command line, and your app reading it.

## Filling it

```bash
miratrade store import        # bring an old .cache of pickles and CSVs in; nothing re-downloaded
miratrade scan --days 30      # SEC Form 4, 13D/G, prices, events
miratrade congress members    # the roster and its committee sectors
miratrade congress trades     # House Periodic Transaction Reports (personal use only)
miratrade store info          # what is in there now
```
