"""New York state grants from the Statewide Financial System's public "Search for Grant Opportunities" page.

The page (esupplier.sfs.ny.gov) needs no login: one GET returns every current opportunity in a PeopleSoft grid
with an Event ID, a funding agency code, a title, a status, who is eligible and the due date. The host has no
robots.txt (404, checked 2026-11-25). The page links no terms; the SFS Online Services Terms of Service bind
people who enroll for an account, which this doesn't do (docs/state-coverage.md).

What the grid doesn't give, the cards say: there is no link to a single opportunity (its titles are postbacks),
so every record links the public search page; titles are cut at 50 characters; and there is no description or
award amount. Agencies appear as codes; only a code the state's own list spells out has a name here.

Who may apply is the state's eligibility column: a call that doesn't list Not-For-Profit is marked as not open
to nonprofits, and a blank one is kept with a note to read the notice. A call whose due date has passed is
dropped. The run stops, keeping the previous file, if the page's "1-N of M" counter shows more rows than were
read.

Records use the same fields as Ohio's (grantmatch/ohio.py), so the same scorer reads them.

Run:  python -m grantmatch.newyork --out data/newyork.json.gz [--skipped build/skipped-newyork.json.gz]
      add --file <saved.html> to read a saved copy of the page instead of fetching it
"""
from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

import requests

from .display import without_email

LIST = "https://esupplier.sfs.ny.gov/psc/fscm/SUPPLIER/ERP/c/NY_SUPPUB_FL.AUC_RESP_INQ_AUC.GBL"
# The link grantsmanagement.ny.gov/search-funding-sfs gives people ("Find Grant Opportunities").
SITE = "https://esupplier.sfs.ny.gov/psp/fscm/SUPPLIER/ERP/c/NY_SUPPUB_FL.AUC_RESP_INQ_AUC.GBL"
MIN_ROWS = 5  # the list holds a few dozen calls; fewer than this means the page changed shape
TITLE_CUT = 50  # the grid cuts titles at this many characters
WHO = "Not stated on the state's list; read the notice"
# Agency codes verified from the state's own list ("NYSDOL OJET ..." is posted under DOL01). Any other code is
# shown as it is: add one only after reading an official source that pairs the code with the name.
AGENCIES = {"DOL01": "New York State Department of Labor"}
# The grid's element ids, each followed by "$<row number>".
CELLS = {
    "event": "AUC_ID_COL$span",
    "agency": "NY_AUC_INQ1_WRK_BUSINESS_UNIT",
    "title": "AUC_NAME_LNK",
    "status": "NY_AUC_INQ1_WRK_NY_GG_PORT_STATUS",
    "eligible": "NY_AUC_INQ1_WRK_FIELDLIST",
    "released": "RESP_INQA1_WK_AUC_DTTM_START",
    "due": "RESP_INQA1_WK_AUC_DTTM_FINISH",
}

session = requests.Session()  # a session keeps the anonymous cookies the page's redirect sets
session.headers.update({"User-Agent": "grant-matcher (github.com/RendellRich/grant-matcher)"})

INVITATION = re.compile(r"\bby invitation only\b|\binvitation[- ]only\b", re.I)
LOAN = re.compile(r"\bloans?\b(?!\s+(?:repayment|forgiveness))|\brevolving (?:loan )?funds?\b", re.I)
NONPROFIT = re.compile(r"not[- ]for[- ]profit|non-?\s?profit", re.I)


def _clean(s: str | None) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("\xa0", " ")).strip()


def _day(s: str | None) -> str | None:
    """The date from "01/22/2027 3:00PM EST" or "09/15/26 9:00AM" (New York's own dates, no conversion)."""
    first = _clean(s).split(" ")[0]
    for fmt in ("%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(first, fmt).date().isoformat()
        except ValueError:
            pass
    return None


class _Grid(HTMLParser):
    """The text of every element whose id is one of the grid's cells."""

    ID = re.compile(rf"^({'|'.join(re.escape(v) for v in CELLS.values())})\$(\d+)$")

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.cells: dict[tuple[int, str], str] = {}
        self._key, self._tag, self._depth = None, "", 0

    def handle_starttag(self, tag, attrs):
        if self._key is None:
            m = self.ID.match(dict(attrs).get("id") or "")
            if m:
                self._key, self._tag, self._depth = (int(m.group(2)), m.group(1)), tag, 1
                self.cells[self._key] = ""
        elif tag == self._tag:
            self._depth += 1

    def handle_endtag(self, tag):
        if self._key is not None and tag == self._tag:
            self._depth -= 1
            if not self._depth:
                self._key = None

    def handle_data(self, data):
        if self._key is not None:
            self.cells[self._key] += data


def parse(page: str) -> tuple[list[dict], int | None]:
    """The grid's rows, and the total its "1-N of M" counter claims (None when the counter isn't there)."""
    grid = _Grid()
    grid.feed(page)
    names = {v: k for k, v in CELLS.items()}
    rows: dict[int, dict] = {}
    for (n, cell), text in grid.cells.items():
        rows.setdefault(n, {})[names[cell]] = _clean(text)
    counter = re.search(r">\s*\d+-\d+ of (\d+)\s*<", page)
    return [{k: rows[n].get(k, "") for k in CELLS} for n in sorted(rows)], int(counter.group(1)) if counter else None


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def normalize(row: dict, today: str | None = None) -> dict:
    today = today or date.today().isoformat()
    title, code, event = row["title"], row["agency"], row["event"]
    who = row["eligible"]
    nonprofit = bool(NONPROFIT.search(who)) if who else True
    closes = _day(row["due"])
    opens = _day(row["released"])
    advertised = "not in sfs" in row["status"].lower()
    notes = [
        f"Search for Event ID {event} on New York's grant opportunity search; the state's list has no link to a "
        "single opportunity, no description and no award amount.",
        "The state lists this one as advertised only, so you don't apply in its system: follow the agency's notice."
        if advertised else "",
        "The state's list cuts titles at 50 characters, so this one may be incomplete." if len(title) >= TITLE_CUT else "",
    ]
    loan = bool(LOAN.search(title))
    rec = {
        # Event IDs are numbered by each agency, so the agency code is part of the key.
        "id": f"ny-{_slug(code)}-{_slug(event)}",
        "csfa": "",
        "number": event,
        "state": "NY",
        "title": title,
        "agency": AGENCIES.get(code) or (f"State agency code {code}" if code else ""),
        "objectives": "",
        "assistance": "Loan" if loan else "Grant",
        "applicant_types": who[:1200] or WHO,
        "nonprofit_eligible": nonprofit,
        "earmark": False,
        "restrictions": "",
        "application": " ".join(t for t in notes if t),
        "award": "",
        "deadlines": closes or "",
        "contact": "",
        "web": SITE,
        "subjects": "",
        "fiscal_year": "",
        "url": SITE,
        "status": "forecasted" if "anticipated" in row["status"].lower() or (opens and opens > today) else "active",
        "opens": opens,
        "closes": closes,
        "match": "",
        "loan": loan,
        "funding_method": "",
        "loi": False,
        "updated": None,
    }
    return {k: without_email(v) if isinstance(v, str) else v for k, v in rec.items()}


def build_records(items: list[dict], today: str | None = None, skips: list[dict] | None = None) -> list[dict]:
    """Open calls, one per row. Rows dropped are added to skips, when given."""
    today = today or date.today().isoformat()
    out: dict[str, dict] = {}
    for row in items:
        try:
            rec = normalize(row, today)
        except Exception as exc:  # one odd row shouldn't sink the refresh
            print(f"skip a row: {exc}", file=sys.stderr)
            continue
        base = {"source": "newyork", "id": rec["id"], "name": rec["title"] or "(no title)", "state": "NY",
                "funder": rec["agency"], "url": rec["url"]}
        reason = detail = ""
        if not rec["title"] or not row["event"]:
            reason, detail = "no_title", "The state's row has no title or no Event ID"
        elif rec["closes"] and rec["closes"] < today:
            reason, detail = "deadline_passed", f"Listed, but its due date was {rec['closes']}"
        elif "closed" in row["status"].lower():
            reason, detail = "deadline_passed", "The state's list marks it closed"
        elif not rec["closes"]:
            reason, detail = "no_deadline", f"No due date on the list (it says: {row['due'][:80] or 'nothing'})"
        elif INVITATION.search(rec["title"]):
            reason, detail = "invitation_only", "The listing says: by invitation only"
        elif rec["id"] in out:
            reason, detail = "duplicate", "The same agency and Event ID are listed twice"
        if reason:
            if skips is not None:
                skips.append({**base, "reason": reason, "detail": detail})
            continue
        out[rec["id"]] = rec
    return sorted(out.values(), key=lambda r: r["id"])


def read_rows(page: str) -> list[dict]:
    """The page's rows, or an error when it doesn't show every row it says it has."""
    rows, total = parse(page)
    if len(rows) < MIN_ROWS:
        raise RuntimeError(f"Only {len(rows)} rows on the New York list; keeping the previous data file")
    if total is None or len(rows) < total:
        raise RuntimeError(f"Read {len(rows)} rows but the page's counter says {total}; keeping the previous data file")
    return rows


def fetch_list() -> str:
    r = session.get(LIST, timeout=90)
    r.raise_for_status()
    return r.content.decode("utf-8", errors="replace")


def build(out: Path, skipped_out: Path | None = None, saved: Path | None = None) -> int:
    items = read_rows(saved.read_text(encoding="utf-8", errors="replace") if saved else fetch_list())
    skips: list[dict] = []
    records = build_records(items, skips=skips)
    payload = {
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "source": "New York Statewide Financial System, Search for Grant Opportunities (esupplier.sfs.ny.gov)",
        "state": "NY", "count": len(records), "programs": records,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(out, "wt", encoding="utf-8") as fh:
        json.dump(payload, fh, separators=(",", ":"))
    print(f"wrote {len(records)} open New York calls to {out}; {sum(r['nonprofit_eligible'] for r in records)} open to nonprofits")
    if skipped_out is not None:
        from .fetch import write_skips
        write_skips(skipped_out, skips)
    return len(records)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="data/newyork.json.gz", type=Path)
    ap.add_argument("--skipped", type=Path)
    ap.add_argument("--file", type=Path, help="a saved copy of the search page, instead of fetching it")
    args = ap.parse_args()
    build(args.out, args.skipped, args.file)


if __name__ == "__main__":
    main()
