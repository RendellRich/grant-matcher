"""A foundation's giving over several years, from the same IRS returns the parsers read.

The latest return says what a foundation gave last year. Several years say more: whether it gives every
year, how often it funds groups it hasn't funded before, and whether it only recently started giving in a
place. The parsers (foundations.py and community.py) add every return's grants here as they read them;
each record then gets a short "hist" summary, and each state's file gets the places in that state the
foundation has funded, with the first year it did.

  hist = {"y": [2021, 2022, 2023, 2024],   tax years with grants, oldest first (at most YEARS)
          "n": [12, 15, 14, 18],          grants in each of those years
          "steady": true,                 grants in each of the last STEADY years up to the latest
          "new": 0.39,                    share of the latest year's grantees it hadn't funded before
                                          (null without NEW_MIN_EARLIER earlier years or NEW_MIN_GRANTEES grantees)
          "pl": {"bradenton": 2022}}      places in this file's state, with the first year funded there

Display only: scores never read it.
"""
from __future__ import annotations

import hashlib
import re
from collections import defaultdict

YEARS = 5
STEADY = 4
NEW_MIN_EARLIER = 2
NEW_MIN_GRANTEES = 3
MAX_PLACES = 300  # per state per foundation, so a national funder can't swell a state's file


def _year(tax_year) -> int | None:
    s = str(tax_year or "")[:4]
    return int(s) if s.isdigit() else None


# Words a grantee's name gains or loses from one return to the next ("Reading Club, Inc." and "The Reading Club").
NAME_NOISE = {"inc", "incorporated", "corp", "corporation", "co", "company", "llc", "ltd", "the", "of", "and"}


def recipient_key(name: str, state: str) -> int:
    """A short fingerprint of a grantee, so years can be compared without keeping every name."""
    words = [w for w in re.split(r"[^a-z0-9]+", (name or "").lower().replace("&", " and ")) if w and w not in NAME_NOISE]
    norm = "".join(words) + "|" + (state or "").upper()
    return int.from_bytes(hashlib.blake2b(norm.encode(), digest_size=8).digest(), "big")


class History:
    def __init__(self) -> None:
        # ein -> tax year -> (grant count, grantee fingerprints, {state: {city}})
        self.by_ein: dict[str, dict[int, tuple[int, set[int], dict[str, set[str]]]]] = defaultdict(dict)

    def add(self, ein: str, tax_year, grants: list[dict]) -> None:
        """One return's grants. A later return for the same tax year (an amendment) replaces the earlier one."""
        year = _year(tax_year)
        if not ein or year is None or not grants:
            return
        keys, places = set(), defaultdict(set)
        for g in grants:
            if g.get("to"):
                keys.add(recipient_key(g["to"], g.get("state", "")))
            st, city = (g.get("state") or "").upper(), (g.get("city") or "").strip().lower()
            if re.fullmatch(r"[A-Z]{2}", st) and city:
                places[st].add(city)
        self.by_ein[str(ein)][year] = (len(grants), keys, dict(places))

    def summary(self, ein: str, latest_tax_year) -> dict | None:
        """The hist summary for a record whose latest return is for latest_tax_year (places left out; see places)."""
        latest = _year(latest_tax_year)
        years = {y: v for y, v in self.by_ein.get(str(ein), {}).items() if latest is None or y <= latest}
        if not years:
            return None
        ys = sorted(years)[-YEARS:]
        top = ys[-1]
        steady = all(y in years for y in range(top - STEADY + 1, top + 1))
        earlier = [y for y in sorted(years) if y < top]
        new = None
        if len(earlier) >= NEW_MIN_EARLIER and len(years[top][1]) >= NEW_MIN_GRANTEES:
            seen = set().union(*(years[y][1] for y in earlier))
            new = round(len(years[top][1] - seen) / len(years[top][1]), 2)
        return {"y": ys, "n": [years[y][0] for y in ys], "steady": steady, "new": new}

    def places(self, ein: str, state: str, latest_tax_year) -> dict[str, int]:
        """Cities in one state this foundation has funded, with the first year it did."""
        latest = _year(latest_tax_year)
        first: dict[str, int] = {}
        for y, (_, _, by_state) in sorted(self.by_ein.get(str(ein), {}).items()):
            if latest is not None and y > latest:
                continue
            for city in by_state.get(state, ()):
                first.setdefault(city, y)
        if len(first) > MAX_PLACES:  # keep the newest places first: they are the ones "new to your area" needs
            first = dict(sorted(first.items(), key=lambda kv: (-kv[1], kv[0]))[:MAX_PLACES])
        return dict(sorted(first.items()))

    def for_state(self, rec: dict, state: str) -> dict:
        """A copy of rec for one state's file, with its hist and that state's places."""
        h = self.summary(rec["ein"], rec.get("tax_year"))
        if not h:
            return rec
        pl = self.places(rec["ein"], state, rec.get("tax_year"))
        return {**rec, "hist": {**h, "pl": pl} if pl else h}


def default_years(this_year: int) -> list[int]:
    """IRS filing years to read: enough for YEARS tax years of history, plus this year's filings."""
    return list(range(this_year - YEARS, this_year + 1))
