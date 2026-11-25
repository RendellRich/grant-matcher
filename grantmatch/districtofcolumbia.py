"""District of Columbia grants from the District Grants Clearinghouse (communityaffairs.dc.gov/node/26).

The page is the District government's clearinghouse for its agencies' grant notices: one table of notices with
the title and agency, the notice, the application packet and the submission deadline, and above it a short table
of the Mayor's own community grants. DC.gov content is licensed Creative Commons Attribution 3.0
(dc.gov/page/terms-and-conditions-use), so the site names the source and the license where it names the source.
robots.txt asks for 10 seconds between requests; a run makes one request.

The tables have no field for who may apply, so every call is kept with a note to read the notice, except one
whose title says it is a grant for local education agencies (school systems and charter schools). A call whose
deadline has passed is dropped, and so is one whose deadline can't be read (no year), unless it says it takes
applications on a rolling basis.

Records use the same fields as Ohio's (grantmatch/ohio.py), so the same scorer reads them.

Run:  python -m grantmatch.districtofcolumbia --out data/districtofcolumbia.json.gz [--skipped build/skipped-districtofcolumbia.json.gz]
      add --file <saved.html> to read a saved copy of the page instead of fetching it
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import sys
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin

import requests

from .display import without_email

LIST = "https://communityaffairs.dc.gov/node/26"
MIN_ROWS = 5  # the clearinghouse table holds about twenty notices; fewer than this means the page changed shape
WHO = "Not stated on the District's table; read the notice"
SCHOOLS_SAYS = "The title says it is a grant for local education agencies (school systems and charter schools); read the notice"
MAYORS_OFFICE = "Mayor's Office of Community Affairs"  # the heading above the page's community grant table

session = requests.Session()
session.headers.update({"User-Agent": "grant-matcher (github.com/RendellRich/grant-matcher)"})

INVITATION = re.compile(r"\bby invitation only\b|\binvitation[- ]only\b", re.I)
LOAN = re.compile(r"\bloans?\b(?!\s+(?:repayment|forgiveness))|\brevolving (?:loan )?funds?\b", re.I)
ROLLING = re.compile(r"\b(?:ongoing|rolling|open until filled|year[- ]round)\b", re.I)
SCHOOLS = re.compile(r"\bLEA\b\)?\s*\)?\s*Grant|\bgrants? (?:for|to) (?:LEAs|local education(?:al)? agencies)\b", re.I)
MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
DATE = re.compile(rf"\b({MONTHS})\s+(\d{{1,2}}),?\s+(\d{{4}})")


def _clean(s: str | None) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("\xa0", " ").replace("​", "")).strip()


class _Tables(HTMLParser):
    """Each table's rows; each cell as its paragraphs of text and its links."""

    BLOCKS = ("p", "br", "div", "li", "ul", "ol")

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[dict]]] = []
        self._cell: dict | None = None
        self._link: list | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.tables.append([])
        elif tag == "tr" and self.tables:
            self.tables[-1].append([])
        elif tag in ("td", "th") and self.tables and self.tables[-1]:
            self._cell = {"text": [""], "links": []}
            self.tables[-1][-1].append(self._cell)
        elif self._cell is not None:
            if tag in self.BLOCKS:
                self._cell["text"].append("")
            elif tag == "a":
                self._link = [dict(attrs).get("href") or "", ""]
                self._cell["links"].append(self._link)

    def handle_endtag(self, tag):
        if tag in ("td", "th", "table"):
            self._cell = self._link = None
        elif tag == "a":
            self._link = None
        elif tag in self.BLOCKS and self._cell is not None:
            self._cell["text"].append("")

    def handle_data(self, data):
        if self._cell is not None:
            self._cell["text"][-1] += data
            if self._link is not None:
                self._link[1] += data


def _paragraphs(cell: dict) -> list[str]:
    return [t for t in (_clean(p) for p in cell["text"]) if t]


def _links(cell: dict) -> list[tuple[str, str]]:
    """(label, full address) for each web link in a cell."""
    found = ((_clean(text), urljoin(LIST, href.strip())) for href, text in cell["links"] if href.strip())
    return [(text, url) for text, url in found if url.startswith("http")]


def parse(page: str) -> tuple[list[dict], int]:
    """The listings from both tables, and how many rows the clearinghouse table has."""
    tables = _Tables()
    tables.feed(page)
    out, clearinghouse = [], 0
    for table in tables.tables:
        if not table:
            continue
        head = [" ".join(_paragraphs(c)).lower() for c in table[0]]
        if len(head) >= 4 and "public notice" in head[0] and "deadline" in head[3]:
            for cells in table[1:]:
                if len(cells) < 4:
                    continue
                name = _paragraphs(cells[0])
                if not name and not _paragraphs(cells[3]):
                    continue  # an empty spacer row
                clearinghouse += 1
                out.append({"title": name[0] if name else "", "agency": ", ".join(name[1:]),
                            "notice": _links(cells[1]), "packet": _links(cells[2]),
                            "deadline": " ".join(_paragraphs(cells[3]))})
        elif len(head) >= 3 and "focus area" in head[0] and "application" in head[2]:
            for cells in table[1:]:
                if len(cells) < 3:
                    continue
                name = _paragraphs(cells[0])
                if not name:
                    continue
                said = " ".join(_paragraphs(cells[2]))
                when = re.search(r"Deadline:?\s*(.*)$", said, re.I)
                out.append({"title": name[0], "agency": MAYORS_OFFICE, "notice": _links(cells[1]),
                            "packet": _links(cells[2]), "deadline": when.group(1) if when else ""})
    return out, clearinghouse


def _day(s: str) -> str | None:
    """The last "Month D, YYYY" in the deadline cell, which holds a time and a date in either order."""
    found = DATE.findall(s or "")
    if not found:
        return None
    month, day, year = found[-1]
    try:
        return datetime.strptime(f"{month} {day} {year}", "%B %d %Y").date().isoformat()
    except ValueError:
        return None


def _slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def _key(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:6]


def normalize(row: dict) -> dict:
    title = without_email(_clean(row["title"]))  # before the key is made from it
    closes = _day(row["deadline"])
    rolling = not closes and bool(ROLLING.search(row["deadline"]))
    links = [*row["notice"], *row["packet"]]
    url = links[0][1] if links else LIST
    schools = bool(SCHOOLS.search(title))
    application = [f"Deadline as the District gives it: {_clean(row['deadline'])}." if _clean(row["deadline"]) else "",
                   *[f"{label or 'Application document'}: {link}" for label, link in row["packet"][:2]],
                   "Apply as the notice and application packet say."]
    loan = bool(LOAN.search(title))
    rec = {
        # The link's hash is always part of the key, so two calls with one title stay apart and neither's key
        # changes when the other expires, moves or leaves the page. A row with no link of its own is keyed by the
        # page and its agency.
        "id": f"dc-{_slug(title)}-{_key(url if links else url + row['agency'])}",
        "csfa": "",
        "number": "",
        "state": "DC",
        "title": title,
        "agency": row["agency"],
        "objectives": "",
        "assistance": "Loan" if loan else "Grant",
        "applicant_types": SCHOOLS_SAYS if schools else WHO,
        "nonprofit_eligible": not schools,
        "earmark": False,
        "restrictions": "",
        "application": " ".join(t for t in application if t)[:1200],
        "award": "",
        "deadlines": closes or ("Ongoing" if rolling else _clean(row["deadline"])),
        "contact": "",
        "web": LIST,
        "subjects": "",
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
    return {k: without_email(v) if isinstance(v, str) else v for k, v in rec.items()}


def build_records(items: list[dict], today: str | None = None, skips: list[dict] | None = None) -> list[dict]:
    """Open calls, one per notice. Rows dropped are added to skips, when given."""
    today = today or date.today().isoformat()
    out: dict[str, dict] = {}
    for row in items:
        try:
            rec = normalize(row)
        except Exception as exc:  # one odd row shouldn't sink the refresh
            print(f"skip a row: {exc}", file=sys.stderr)
            continue
        base = {"source": "districtofcolumbia", "id": rec["id"], "name": rec["title"] or "(no title)", "state": "DC",
                "funder": rec["agency"], "url": rec["url"]}
        reason = detail = ""
        if not rec["title"]:
            reason, detail = "no_title", "The District's row has no title"
        elif rec["closes"] and rec["closes"] < today:
            reason, detail = "deadline_passed", f"Listed, but its deadline was {rec['closes']}"
        elif not rec["closes"] and rec["deadlines"] != "Ongoing":
            reason, detail = "no_deadline", f"No full date to read (it says: {rec['deadlines'][:80] or 'nothing'})"
        elif INVITATION.search(rec["title"]):
            reason, detail = "invitation_only", "The listing says: by invitation only"
        elif rec["id"] in out:
            reason, detail = "duplicate", "The same title and link are listed twice"
        if reason:
            if skips is not None:
                skips.append({**base, "reason": reason, "detail": detail})
            continue
        out[rec["id"]] = rec
    return sorted(out.values(), key=lambda r: r["id"])


def read_rows(page: str) -> list[dict]:
    """The page's listings, or an error when the clearinghouse table isn't there or is nearly empty."""
    items, clearinghouse = parse(page)
    if clearinghouse < MIN_ROWS:
        raise RuntimeError(f"Only {clearinghouse} rows in the District's clearinghouse table; keeping the previous data file")
    return items


def fetch_list() -> str:
    r = session.get(LIST, timeout=60)
    r.raise_for_status()
    return r.content.decode("utf-8", errors="replace")


def build(out: Path, skipped_out: Path | None = None, saved: Path | None = None) -> int:
    items = read_rows(saved.read_text(encoding="utf-8", errors="replace") if saved else fetch_list())
    skips: list[dict] = []
    records = build_records(items, skips=skips)
    payload = {
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "source": "District Grants Clearinghouse (communityaffairs.dc.gov), DC.gov, CC BY 3.0, reformatted",
        "state": "DC", "count": len(records), "programs": records,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(out, "wt", encoding="utf-8") as fh:
        json.dump(payload, fh, separators=(",", ":"))
    print(f"wrote {len(records)} open District of Columbia grants to {out}; {sum(r['nonprofit_eligible'] for r in records)} open to nonprofits")
    if skipped_out is not None:
        from .fetch import write_skips
        write_skips(skipped_out, skips)
    return len(records)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="data/districtofcolumbia.json.gz", type=Path)
    ap.add_argument("--skipped", type=Path)
    ap.add_argument("--file", type=Path, help="a saved copy of the page, instead of fetching it")
    args = ap.parse_args()
    build(args.out, args.skipped, args.file)


if __name__ == "__main__":
    main()
