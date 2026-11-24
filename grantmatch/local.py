"""County, city and state grant programs, entered by hand from each program's own page (data/local-<ST>.json).

No public catalog lists local government grants, so these are kept by hand: each entry names the
counties it serves, whether it needs 501(c)(3) status, and its application window when it has one,
with the date someone last checked the official page. They join the state's programs as records of
the same shape, so the page, the background count and ETO treat them like any other state program:
Florida's are keyed "local-<slug>" (the keys ETO already stores), other states' "local-<st>-<slug>".
The weekly website check and the page watch read each entry's page too. One file per state:
data/local-FL.json, data/local-WA.json, and so on.

Run:  python -m grantmatch.local            # check every state's file and print what it would add
"""
from __future__ import annotations

import gzip
import json
import re
import sys
from datetime import date
from pathlib import Path

LOCAL = Path(__file__).resolve().parent.parent / "data"
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{2,50}$")
DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
LEVELS = ("State", "County", "City", "Children's services council", "Community foundation", "United Way")
STATEWIDE = "Statewide"  # counties: ["Statewide"] for a program open across the state
REQUIRED = ("slug", "title", "agency", "level", "counties", "objectives", "who", "application", "award", "url", "checked")
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December"]


def long_day(s: str) -> str:
    d = date.fromisoformat(s)
    return f"{MONTHS[d.month - 1]} {d.day}, {d.year}"


def states() -> list[str]:
    """The states with a hand-kept list, from the file names (data/local-FL.json gives FL)."""
    return sorted(p.stem.split("-", 1)[1].upper() for p in LOCAL.glob("local-??.json"))


def file_for(state: str) -> Path:
    return LOCAL / f"local-{state.upper()}.json"


def record_id(slug: str, state: str = "FL") -> str:
    """Florida keeps "local-<slug>" (ETO stores those keys); other states add theirs so keys never clash."""
    return f"local-{slug}" if state.upper() == "FL" else f"local-{state.lower()}-{slug}"


def county_places(state: str = "FL") -> dict[str, list[str]]:
    path = LOCAL / "counties.json.gz"
    return json.loads(gzip.decompress(path.read_bytes())).get(state, {}) if path.exists() else {}


def check(entry: dict, counties: dict[str, list[str]]) -> list[str]:
    """What is wrong with one entry, in plain words; empty when it is fine."""
    problems = [f"missing {k}" for k in REQUIRED if not entry.get(k)]
    slug = str(entry.get("slug", ""))
    if slug and not SLUG.match(slug):
        problems.append(f"slug {slug!r} must be lowercase letters, digits and hyphens")
    if entry.get("level") and entry["level"] not in LEVELS:
        problems.append(f"level must be one of {', '.join(LEVELS)}")
    names = entry.get("counties") or []
    if STATEWIDE in names and len(names) > 1:
        problems.append(f"counties is either [{STATEWIDE!r}] or a list of counties, not both")
    for c in names:
        if counties and c != STATEWIDE and c not in counties:
            problems.append(f"unknown county {c!r}")
    for k in ("opens", "closes", "checked"):
        v = entry.get(k)
        if v is not None and not (isinstance(v, str) and DAY.match(v)):
            problems.append(f"{k} must be a yyyy-mm-dd date or null")
    if entry.get("opens") and entry.get("closes") and entry["opens"] > entry["closes"]:
        problems.append("opens is after closes")
    if not isinstance(entry.get("requires_501c3"), bool):
        problems.append("requires_501c3 must be true or false")
    for k in ("url", "web"):
        v = entry.get(k)
        if v and not str(v).startswith("https://"):
            problems.append(f"{k} must start with https://")
    return problems


def deadline_text(entry: dict) -> str:
    if entry.get("deadlines"):
        return entry["deadlines"]
    o, c = entry.get("opens"), entry.get("closes")
    if o and c:
        return f"Applications open {long_day(o)} and close {long_day(c)}."
    if c:
        return f"Applications close {long_day(c)}."
    return "No set window is published; see how to apply."


def to_record(entry: dict, counties: dict[str, list[str]], fiscal_year: str = "", state: str = "FL") -> dict:
    """A state program record (the shape grantmatch.florida writes) with the local fields added."""
    from .display import STATE_NAMES
    names = list(entry["counties"])
    if names == [STATEWIDE]:
        names, area = [], f"all of {STATE_NAMES.get(state.upper(), state)}"  # no places: open statewide
    else:
        area = (names[0] + " County") if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1] + " counties"
    places = set()
    for c in names:
        places |= {c.lower(), f"{c.lower()} county"}
        places |= {p.lower() for p in counties.get(c, [])}
    return {
        "id": record_id(entry["slug"], state),
        "csfa": "",
        "title": entry["title"],
        "agency": entry["agency"],
        "objectives": entry["objectives"],
        "assistance": "Grant",
        "applicant_types": entry["who"],
        "nonprofit_eligible": True,
        "earmark": False,
        "restrictions": "",
        "application": entry["application"],
        "award": entry["award"],
        "deadlines": deadline_text(entry),
        "contact": entry.get("contact", ""),
        "web": entry.get("web") or entry["url"],
        "subjects": entry.get("subjects", ""),
        "fiscal_year": fiscal_year,
        "url": entry["url"],
        "level": entry["level"],
        "area": area,
        "places": sorted(places),
        "requires_501c3": entry["requires_501c3"],
        "opens": entry.get("opens"),
        "closes": entry.get("closes"),
        "checked": entry["checked"],
    }


def load(path: Path | None = None, counties: dict[str, list[str]] | None = None, fiscal_year: str = "",
         state: str = "FL") -> list[dict]:
    """Every entry in a state's file as a program record. A bad entry stops the run with what is wrong, so a
    typo never reaches the site."""
    path = path or file_for(state)
    if not path.exists():
        return []
    counties = county_places(state) if counties is None else counties
    entries = json.loads(path.read_text(encoding="utf-8")).get("programs", [])
    problems, seen = [], set()
    for e in entries:
        for p in check(e, counties):
            problems.append(f"{e.get('slug', '?')}: {p}")
        if e.get("slug") in seen:
            problems.append(f"{e['slug']}: slug used twice")
        seen.add(e.get("slug"))
    if problems:
        raise ValueError(f"{path.name} has problems:\n  " + "\n  ".join(problems))
    return [to_record(e, counties, fiscal_year, state) for e in entries]


def site_targets(path: Path | None = None, state: str | None = None) -> dict[str, str]:
    """For the weekly website check: each program's id and the page to read, for one file or every state's."""
    if path is None and state is None:
        out: dict[str, str] = {}
        for st in states():
            out |= site_targets(state=st)
        return out
    try:
        records = load(path, counties={}, state=state or "FL")
    except ValueError:
        return {}
    return {r["id"]: r["url"] for r in records if not r["url"].lower().endswith(".pdf")} | \
           {r["id"]: r["web"] for r in records if r["url"].lower().endswith(".pdf") and not r["web"].lower().endswith(".pdf")}


def main() -> None:
    total = 0
    for st in states():
        try:
            records = load(state=st)
        except ValueError as exc:
            print(exc, file=sys.stderr)
            sys.exit(1)
        for r in records:
            print(f"{r['id']}: {r['title']} ({r['area']}); {r['deadlines']}")
        print(f"{st}: {len(records)} hand-kept programs")
        total += len(records)
    print(f"{total} in all")


if __name__ == "__main__":
    main()
