"""New Jersey state grants from the Treasury Grants Office's list of state grant opportunities.

New Jersey's Department of the Treasury keeps one page of state grant opportunities
(nj.gov/treasury/grants-management/opportunities/state), and the page's table is read from a plain CSV file
beside it, state-data.csv: one row per opportunity with its category, title, a link to the notice, the agency,
and the deadline (a date, or "Rolling"). The file has no header row, no description and no field for who may
apply, and the page says the list is not complete; agencies also post calls on their own pages.

With no eligibility field, every call is kept with a note on its card to read the notice, as Iowa's are when
the description says neither way (grantmatch/iowa.py), except one whose title plainly says it is for
municipalities or counties, which is read as not open to nonprofits. A call whose deadline has passed is dropped.

Records use the same fields as Ohio's (grantmatch/ohio.py), so the same scorer reads them.

Run:  python -m grantmatch.newjersey --out data/newjersey.json.gz [--skipped build/skipped-newjersey.json.gz]
      add --file <saved.csv> to read a saved copy of the list instead of fetching it
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import requests

LIST = "https://www.nj.gov/treasury/grants-management/opportunities/state/state-data.csv"
SITE = "https://www.nj.gov/treasury/grants-management/opportunities/state"
MIN_ROWS = 10  # the list holds a few dozen calls; fewer than this means the file changed shape
WHO = "Not stated on the state's list; read the notice"

session = requests.Session()
session.headers.update({"User-Agent": "grant-matcher (github.com/RendellRich/grant-matcher)"})

INVITATION = re.compile(r"\bby invitation only\b|\binvitation[- ]only\b", re.I)
LOAN = re.compile(r"\bloans?\b|\brevolving (?:loan )?funds?\b", re.I)
# A title that plainly says the money is for municipalities or counties ("... Municipal Grants", "County
# Environmental Health Act Grants") is read as not open to nonprofits; the skipped report lists them for review.
GOVERNMENT_ONLY = re.compile(r"\b(?:municipal|municipalities|county|counties)\b", re.I)
GOVERNMENT_SAYS = "The title says it is for municipalities or counties; read the notice"


def _clean(s: str | None) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("\xa0", " ")).strip()


def _day(s: str) -> str | None:
    try:
        return datetime.strptime(_clean(s), "%m/%d/%Y").date().isoformat()
    except ValueError:
        return None


def rows(text: str) -> list[dict]:
    """The CSV's rows by position: category, title, url, agency, deadline. Short rows are left out."""
    out = []
    for cells in csv.reader(io.StringIO(text.lstrip("\ufeff"))):
        if len(cells) < 5:
            continue
        category, title, url, agency, deadline = (_clean(c) for c in cells[:5])
        out.append({"category": category, "title": title, "url": url, "agency": agency, "deadline": deadline})
    return out


def slug(title: str) -> str:
    """The whole title as a key: titles that differ only at the end ("... Round 1", "... Round 2") stay apart."""
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def normalize(row: dict) -> dict:
    title = row["title"]
    closes = _day(row["deadline"])
    rolling = not closes and row["deadline"].lower().startswith("rolling")
    key = slug(title)
    url = row["url"] if row["url"].startswith("http") else SITE
    loan = bool(LOAN.search(title))
    government = bool(GOVERNMENT_ONLY.search(title))
    return {
        "id": f"nj-{key}",
        "csfa": "",
        "number": "",
        "state": "NJ",
        "title": title,
        "agency": row["agency"],
        "objectives": "",
        "assistance": "Loan" if loan else "Grant",
        "applicant_types": GOVERNMENT_SAYS if government else WHO,
        "nonprofit_eligible": not government,
        "earmark": False,
        "restrictions": "",
        "application": "Apply as the notice says. The state's list gives no description or eligibility, so read the notice first.",
        "award": "",
        "deadlines": closes or ("Ongoing" if rolling else row["deadline"]),
        "contact": "",
        "web": SITE,
        "subjects": "; ".join(t.strip() for t in row["category"].split(";") if t.strip()),
        "fiscal_year": "",
        "url": url,
        "status": "active",
        "opens": None,
        "closes": closes,
        "match": "",
        "loan": loan,
        "funding_method": "",
        "loi": False,
        "updated": None,
    }


def build_records(items: list[dict], today: str | None = None, skips: list[dict] | None = None) -> list[dict]:
    """Open calls, one per row. Rows dropped are added to skips, when given."""
    today = today or date.today().isoformat()
    out: dict[str, dict] = {}
    for row in items:
        try:
            rec = normalize(row)
        except Exception as exc:  # one odd row shouldn't sink the refresh
            print(f"skip a row: {exc}", file=sys.stderr)
            continue
        base = {"source": "newjersey", "id": rec["id"], "name": rec["title"] or "(no title)", "state": "NJ",
                "funder": rec["agency"], "url": rec["url"]}
        if not rec["title"]:
            if skips is not None:
                skips.append({**base, "reason": "no_title", "detail": "The state's row has no title"})
            continue
        if rec["closes"] and rec["closes"] < today:
            if skips is not None:
                skips.append({**base, "reason": "deadline_passed", "detail": f"Listed, but its deadline was {rec['closes']}"})
            continue
        if INVITATION.search(rec["title"]):
            if skips is not None:
                skips.append({**base, "reason": "invitation_only", "detail": "The listing says: by invitation only"})
            continue
        if rec["id"] in out:
            # The same title twice (a second round, or a second agency's call): keep both, the later one keyed
            # by a short hash of its link so the key doesn't change from one refresh to the next. The same title
            # with the same link is a repeated row.
            hashed = f"{rec['id']}-{hashlib.sha1(rec['url'].encode('utf-8')).hexdigest()[:6]}"
            if out[rec["id"]]["url"] == rec["url"] or hashed in out:
                if skips is not None:
                    skips.append({**base, "reason": "duplicate", "detail": "The same title and link are listed twice"})
                continue
            rec["id"] = hashed
        out[rec["id"]] = rec
    return sorted(out.values(), key=lambda r: r["id"])


def fetch_list() -> str:
    r = session.get(LIST, timeout=60)
    r.raise_for_status()
    return r.content.decode("utf-8-sig", errors="replace")


def build(out: Path, skipped_out: Path | None = None, saved: Path | None = None) -> int:
    items = rows(saved.read_bytes().decode("utf-8-sig", errors="replace") if saved else fetch_list())
    if len(items) < MIN_ROWS:
        raise RuntimeError(f"Only {len(items)} rows on the New Jersey list; keeping the previous data file")
    skips: list[dict] = []
    records = build_records(items, skips=skips)
    payload = {
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "source": "New Jersey Treasury, State Grant Opportunities (nj.gov/treasury/grants-management)",
        "state": "NJ", "count": len(records), "programs": records,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(out, "wt", encoding="utf-8") as fh:
        json.dump(payload, fh, separators=(",", ":"))
    print(f"wrote {len(records)} open New Jersey calls to {out}")
    if skipped_out is not None:
        from .fetch import write_skips
        write_skips(skipped_out, skips)
    return len(records)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="data/newjersey.json.gz", type=Path)
    ap.add_argument("--skipped", type=Path)
    ap.add_argument("--file", type=Path, help="a saved copy of the list's CSV, instead of fetching it")
    args = ap.parse_args()
    build(args.out, args.skipped, args.file)


if __name__ == "__main__":
    main()
