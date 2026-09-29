"""Who sits in Congress, and which industries their committees oversee.

LEGAL — PERSONAL USE ONLY. Congressional financial disclosures are governed by the Ethics in
Government Act, 5 U.S.C. app. § 105(c): it is unlawful to obtain or use a report *for any commercial
purpose*, other than by news and communications media for dissemination to the general public, for
determining a credit rating, or in the solicitation of money. The Attorney General may bring a civil
action for up to $10,000 per violation. MiraTrade is personal software for its own user, which is
what makes this module allowed — and it is the one part of MiraTrade that must be removed, or
separately cleared, before the app is sold to anyone. Nothing else here carries that restriction:
SEC Form 4 is Section 16 securities law and has no such limit.

This module reads only the roster, which has no such restriction at all: the
`unitedstates/congress-legislators` project publishes the members and their committee assignments in
the public domain. The disclosures themselves are fetched by ``congress_house`` and
``congress_senate``.

Why the committees matter: a member of the Armed Services Committee buying a defence contractor is a
different piece of evidence from the same member buying a supermarket chain. The sector a committee
oversees is the closest thing to "did they know something" that public data offers.
"""
from __future__ import annotations

import json
import urllib.request
from typing import Callable, NamedTuple

import pandas as pd

from miratrade.config import SEC_USER_AGENT

FEED = "https://unitedstates.github.io/congress-legislators/{name}.json"
MEMBER_COLUMNS = ["bioguide_id", "name", "chamber", "party", "state", "committees", "sectors", "updated"]

# Which industries a committee's work touches. Keywords are matched against the committee's name,
# most specific first, and a member gets the union over every committee they sit on. This is a
# judgement, not a fact: it says where a member is plausibly ahead of the public, nothing more.
SECTOR_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Defense", ("armed services", "intelligence", "homeland security", "veterans")),
    ("Finance", ("financial services", "banking", "ways and means", "finance", "budget",
                 "appropriations")),
    ("Healthcare", ("health", "aging")),
    ("Energy", ("energy", "natural resources", "environment")),
    ("Technology", ("science", "space", "technology", "commerce")),
    ("Industrials", ("transportation", "infrastructure", "agriculture", "small business")),
)


def _get(name: str, opener: Callable | None = None):
    url = FEED.format(name=name)
    request = urllib.request.Request(url, headers={"User-Agent": SEC_USER_AGENT})
    with (opener or urllib.request.urlopen)(request, timeout=60) as response:
        return json.load(response)


def sectors_for(committees: list[str]) -> list[str]:
    """The industries a set of committees oversees. ``Other`` only when nothing else applies."""
    found = []
    for sector, keywords in SECTOR_KEYWORDS:
        lowered = [c.lower() for c in committees]
        if any(k in c for c in lowered for k in keywords) and sector not in found:
            found.append(sector)
    return found or (["Other"] if committees else [])


def build_members(legislators: list, committees: list, membership: dict) -> pd.DataFrame:
    """The roster as one row per member, with their committees and the sectors those cover."""
    names = {c.get("thomas_id"): c.get("name", "") for c in committees}
    for c in committees:                                   # subcommittees carry their parent's id
        for sub in c.get("subcommittees", ()):
            names[f"{c.get('thomas_id')}{sub.get('thomas_id')}"] = f"{c.get('name', '')} — {sub.get('name', '')}"
    sits_on: dict[str, list[str]] = {}
    for code, members in membership.items():
        label = names.get(code, code)
        for m in members:
            sits_on.setdefault(m.get("bioguide", ""), []).append(label)

    updated = pd.Timestamp.now('UTC').strftime("%Y-%m-%d")
    rows = []
    for person in legislators:
        bioguide = person.get("id", {}).get("bioguide")
        term = (person.get("terms") or [{}])[-1]
        if not bioguide:
            continue
        mine = sorted(set(sits_on.get(bioguide, [])))
        rows.append({"bioguide_id": bioguide,
                     "name": person.get("name", {}).get("official_full")
                             or f"{person.get('name', {}).get('first', '')} "
                                f"{person.get('name', {}).get('last', '')}".strip(),
                     "chamber": {"sen": "senate", "rep": "house"}.get(term.get("type"), term.get("type")),
                     "party": term.get("party"), "state": term.get("state"),
                     "committees": json.dumps(mine),
                     "sectors": json.dumps(sectors_for(mine)),
                     "updated": updated})
    return pd.DataFrame(rows, columns=MEMBER_COLUMNS)


def fetch_members(opener: Callable | None = None, log: Callable[[str], None] = print) -> pd.DataFrame:
    """Download the current roster. Public domain, no key, no rate limit worth worrying about."""
    log("Congress roster (unitedstates/congress-legislators, public domain) …")
    members = build_members(_get("legislators-current", opener),
                            _get("committees-current", opener),
                            _get("committee-membership-current", opener))
    log(f"  {len(members)} members, {sum(bool(json.loads(c)) for c in members['committees'])} "
        "with a committee seat")
    return members


def update_members(db=None, opener: Callable | None = None, log: Callable[[str], None] = print) -> int:
    """Refresh ``congress_members`` in the market database. Returns how many members were written."""
    from miratrade import store

    owned, db = db is None, db if db is not None else store.connect()
    try:
        members = fetch_members(opener, log)
        written = store.write(db, "congress_members", members)
        store.note(db, "congress_members_updated", store.now())
        return written
    finally:
        if owned:
            db.close()


TITLES = ("hon", "mr", "mrs", "ms", "dr", "rep", "sen", "the", "honorable")
SUFFIXES = ("jr", "sr", "ii", "iii", "iv", "v")


def name_parts(name: str) -> list[str]:
    """A name reduced to its words, with the punctuation, titles and suffixes taken out.

    ``Pelosi, Nancy`` comes back as ``[nancy, pelosi]``, and a word repeated by the filer —
    the House index really does carry ``First: "Scott Scott"`` for one member — is collapsed.
    """
    text = str(name or "").lower().replace(".", " ")
    if "," in text:                                        # "pelosi, nancy" → "nancy pelosi"
        last, _, first = text.partition(",")
        text = f"{first} {last}"
    words = [w for w in text.split() if w not in TITLES and w not in SUFFIXES and len(w) > 1]
    return [w for i, w in enumerate(words) if i == 0 or w != words[i - 1]]


def normalise_name(name: str) -> str:
    """The whole name in a form two sources can agree on."""
    return " ".join(name_parts(name))


def short_name(name: str) -> str:
    """First and last word only. The House files a member's full legal name — "August Lee Pfluger
    II" — while the roster carries "August Pfluger", so the middle names have to go before the two
    can be matched at all."""
    parts = name_parts(name)
    return f"{parts[0]} {parts[-1]}" if len(parts) > 1 else " ".join(parts)


class Roster(NamedTuple):
    """The roster indexed for matching, by whole name and by first-and-last.

    The two indexes stay apart on purpose. One member's whole name can be another's first-and-last —
    "John Adams" is also what "John Quincy Adams" shortens to — so a name that only matches on the
    short form has to be checked against every member's short form, where that clash is visible,
    and not against the whole names, where it is not.
    """
    exact: dict[str, str]
    short: dict[str, str]

    def find(self, name: str) -> str | None:
        """The bioguide id for a name as a disclosure spells it, or ``None`` when it is not certain.
        An unattributed trade is a gap; a misattributed one is a false statement about a person."""
        return self.exact.get(normalise_name(name)) or self.short.get(short_name(name))


def member_lookup(db) -> Roster:
    from miratrade import store

    rows = store.read(db, "congress_members")
    names = list(rows.get("name", []))
    ids = list(rows.get("bioguide_id", []))
    seen: dict[str, set] = {}
    for name, bioguide in zip(names, ids):
        seen.setdefault(short_name(name), set()).add(bioguide)
    return Roster(exact={normalise_name(n): b for n, b in zip(names, ids)},
                  short={key: next(iter(found)) for key, found in seen.items() if len(found) == 1})


def match_member(name: str, roster: Roster) -> str | None:
    return roster.find(name)
