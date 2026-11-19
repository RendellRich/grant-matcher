"""How much of the country the foundation data covers, state by state.

The IRS Exempt Organizations Business Master File lists every registered private foundation (those required
to file Form 990-PF) and every organization coded as a community foundation, public foundation or United Way.
This compares that list with the state files the foundation refresh writes, so the site can say what share of
each state's foundations it holds, and why the rest are missing:

  registered      in the master file, based in the state
  e-filed         of those, a return in the IRS e-file index for the two newest filing years, which is
                  what the refresh can read
  read            what the refresh did with each return (from parsed.json, when that run wrote one)
  listed          foundations in the state's file: they pay grants to organizations and take requests

A foundation that is read but not listed pays no grants to organizations, or says it only funds charities it
picks itself. Those are left out on purpose (foundations._keep), so "listed" is never meant to reach 100%.

Run:  python -m grantmatch.coverage --foundations build/foundations --community build/community --out coverage.json
      add --irs <folder holding eo1.csv to eo4.csv and index_<year>.csv> to read the IRS files from disk
"""
from __future__ import annotations

import argparse
import csv
import gzip
import io
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

BMF = "https://www.irs.gov/pub/irs-soi/eo{n}.csv"
INDEX = "https://apps.irs.gov/pub/epostcard/990/xml/{year}/index_{year}.csv"
COMMUNITY_CODES = ("T31", "T30", "T70")
FILING_YEARS = 2  # the refresh lists a foundation only when it filed in the two newest filing years
RETURN_TYPE = {"private": "990PF", "community": "990"}
STATE = re.compile(r"[A-Z]{2}")


def _csv(url: str, path: Path | None):
    """Rows of one IRS file, from disk when a folder is given. None when the IRS doesn't have it yet."""
    if path is not None:
        if not path.exists():
            return None
        text = path.read_text(encoding="latin-1")
    else:
        from .foundations import session
        r = session.get(url, timeout=300)
        if r.status_code != 200:
            return None
        text = r.content.decode("latin-1")
    return csv.DictReader(io.StringIO(text))


def bmf_rows(folder: Path | None = None):
    """Every row of the master file's four regional files."""
    for n in range(1, 5):
        rows = _csv(BMF.format(n=n), folder / f"eo{n}.csv" if folder else None)
        if rows is None:
            raise RuntimeError(f"IRS master file eo{n}.csv is missing")
        yield from rows


def index_rows(year: int, folder: Path | None = None):
    """Every return in the e-file index for the two newest filing years."""
    for y in range(year - FILING_YEARS + 1, year + 1):
        yield from _csv(INDEX.format(year=y), folder / f"index_{y}.csv" if folder else None) or []


def master(rows) -> dict[str, tuple[str, str]]:
    """EIN -> (state, kind) for private foundations (required to file Form 990-PF) and community-type
    organizations. A few carry both marks; the 990-PF requirement decides which pipeline reads them."""
    orgs = {}
    for row in rows:
        st = (row.get("STATE") or "").strip()
        if not STATE.fullmatch(st):
            continue
        if (row.get("PF_FILING_REQ_CD") or "").strip() == "1":
            orgs[row["EIN"]] = (st, "private")
        elif (row.get("NTEE_CD") or "")[:3] in COMMUNITY_CODES:
            orgs[row["EIN"]] = (st, "community")
    return orgs


def registered(orgs: dict[str, tuple[str, str]], index) -> dict[str, dict]:
    """Per state: how many of each kind are registered, and how many of those e-filed lately."""
    out: dict[str, Counter] = defaultdict(Counter)
    for st, kind in orgs.values():
        out[st][kind] += 1
    efiled = set()
    for row in index:
        org = orgs.get(row.get("EIN") or "")
        if org and row.get("RETURN_TYPE") == RETURN_TYPE[org[1]]:
            efiled.add(row["EIN"])
    for ein in efiled:
        st, kind = orgs[ein]
        out[st][f"{kind}_efiled"] += 1
    return {st: dict(c) for st, c in out.items()}


def _load(path: Path) -> list[dict]:
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return json.load(fh).get("foundations", [])


def listed(folder: Path | None) -> dict[str, dict]:
    """Per state file: foundations based in the state, every funder that gives there, and how fresh and how
    reachable the home-state ones are."""
    out: dict[str, dict] = {}
    if folder is None or not folder.exists():
        return out
    for path in sorted(folder.glob("*.json.gz")):
        st = path.name.split(".")[0]
        if not STATE.fullmatch(st):
            continue
        recs = _load(path)
        home = [r for r in recs if r.get("state") == st]
        years = Counter(str(r.get("tax_year") or "") for r in home)
        years.pop("", None)
        out[st] = {
            "home": len(home),
            "giving_here": len(recs),
            "newest_tax_year": max(years) if years else "",
            "with_website": sum(1 for r in home if (r.get("website") or "").strip().upper() not in ("", "N/A", "NONE")),
            "with_how_to_apply": sum(1 for r in home if r.get("apply")),
        }
    return out


def parsed(folder: Path | None) -> dict[str, dict]:
    """The refresh's own count of returns read per state (parsed.json), when that run wrote one."""
    path = folder / "parsed.json" if folder is not None else None
    if path is None or not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8")).get("states", {})


def tally(seen: dict[str, dict], kept, newest: int, current_years: int) -> dict:
    """What the refresh read, per home state, for parsed.json. seen is every return's latest outcome by EIN
    ({"state", "filed", "why"}); kept is the EINs that ended up listed."""
    states: dict[str, Counter] = defaultdict(Counter)
    for ein, s in seen.items():
        if s["filed"] <= newest - current_years or not STATE.fullmatch(s.get("state") or ""):
            continue
        c = states[s["state"]]
        c["read"] += 1
        c["listed" if ein in kept else (s["why"] or "older_return_listed")] += 1
    return {"states": {st: dict(c) for st, c in sorted(states.items())}}


def share(part: int, whole: int) -> float | None:
    return round(part / whole, 3) if whole else None


def report(reg: dict, private: dict, community: dict, read_private: dict, read_community: dict, year: int) -> dict:
    """The coverage file the site shows: one row per state and the national totals."""
    rows = []
    for st in sorted(set(reg) | set(private) | set(community)):
        r, p, c = reg.get(st, {}), private.get(st, {}), community.get(st, {})
        row = {
            "state": st,
            "private": {
                "registered": r.get("private", 0),
                "efiled": r.get("private_efiled", 0),
                "listed": p.get("home", 0),
                "listed_share": share(p.get("home", 0), r.get("private_efiled", 0)),
                "giving_here": p.get("giving_here", 0),
                "newest_tax_year": p.get("newest_tax_year", ""),
                "with_website": p.get("with_website", 0),
                "with_how_to_apply": p.get("with_how_to_apply", 0),
            },
            "community": {
                "registered": r.get("community", 0),
                "efiled": r.get("community_efiled", 0),
                "listed": c.get("home", 0),
                "giving_here": c.get("giving_here", 0),
                "newest_tax_year": c.get("newest_tax_year", ""),
            },
        }
        if st in read_private:
            row["private"]["read"] = read_private[st]
        if st in read_community:
            row["community"]["read"] = read_community[st]
        rows.append(row)

    def total(kind: str, key: str) -> int:
        return sum(row[kind][key] for row in rows)

    national = {
        "private": {k: total("private", k) for k in ("registered", "efiled", "listed", "with_website", "with_how_to_apply")},
        "community": {k: total("community", k) for k in ("registered", "efiled", "listed")},
        "states_with_data": sum(1 for row in rows if row["private"]["listed"] or row["community"]["listed"]),
    }
    national["private"]["listed_share"] = share(national["private"]["listed"], national["private"]["efiled"])
    return {
        "made_at": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "filing_years": list(range(year - FILING_YEARS + 1, year + 1)),
        "has_read_counts": bool(read_private or read_community),
        "national": national,
        "states": rows,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--foundations", type=Path, default=Path("data/foundations"))
    ap.add_argument("--community", type=Path, default=Path("data/community"))
    ap.add_argument("--irs", type=Path, help="a folder holding eo1.csv to eo4.csv and index_<year>.csv (default: download from the IRS)")
    ap.add_argument("--out", type=Path, default=Path("data/coverage.json"))
    ap.add_argument("--year", type=int, default=datetime.now().year)
    args = ap.parse_args()
    reg = registered(master(bmf_rows(args.irs)), index_rows(args.year, args.irs))
    rep = report(reg, listed(args.foundations), listed(args.community),
                 parsed(args.foundations), parsed(args.community), args.year)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(rep, separators=(",", ":")), encoding="utf-8")
    n = rep["national"]
    print(f"{n['private']['listed']:,} of {n['private']['efiled']:,} private foundations that e-filed lately are listed "
          f"({(n['private']['listed_share'] or 0):.0%}); {n['community']['listed']:,} community-type funders; "
          f"{n['states_with_data']} states and territories with data -> {args.out}")


if __name__ == "__main__":
    main()
