"""Maryland grants from the "State Grants" table on the Department of Commerce's nonprofit page. This is partial
coverage: a short table the department keeps, not every state grant.

business.maryland.gov/nonprofit-opportunities/ has tables of federal, state, local and private grants. Only the one
under the "State Grants" heading is read (Agency/Department, Grant Name, Due Date); the federal ones are on
Grants.gov already. The table doesn't say who may apply, what a grant pays or whether it asks for a match, so every
call says to read the notice. A call whose date has passed is dropped, and so is one with no date unless the table
says it is rolling. A row whose due date or title says closed, paused or the like is dropped, and a rolling one also
by such words in a line above the table. robots.txt allows the page, and no terms or privacy page for the site is
linked from it (checked 2026-11-26, docs/state-coverage.md).

Records use the same fields as Ohio's (grantmatch/ohio.py), so the same scorer reads them.

Run:  python -m grantmatch.maryland --out data/maryland.json.gz [--skipped build/skipped-maryland.json.gz]
      add --file <saved.html> to read a saved copy of the page instead of fetching it
"""
from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path
from urllib.parse import urljoin

from . import webpages
from .cycles import page_text
from .districtofcolumbia import _paragraphs, _Tables

LIST = "https://business.maryland.gov/nonprofit-opportunities/"
SOURCE = ("Maryland Department of Commerce nonprofit opportunities page, its State Grants table (business.maryland.gov), "
          "a short list and not every state grant")
WHO = "Not stated on the Commerce Department's table; read the notice"
HEADER = ["agency/department", "grant name", "due date"]
MIN_ROWS = 3  # the table holds about six rows; fewer than this means the page changed shape
ROLLING = re.compile(r"\b(?:rolling|ongoing|year[- ]round)\b", re.I)
CHANGED = "keeping the previous data file"


def parse(page: str) -> list[dict]:
    """The rows of the table under the "State Grants" heading: agency, title, link, date."""
    heading = re.search(r"<h2[^>]*>\s*State Grants\s*</h2>", page, re.I)
    if not heading:
        raise RuntimeError(f"No 'State Grants' heading on the Maryland page; {CHANGED}")
    rest = page[heading.end():]
    table = re.search(r"(?is)<table\b.*?</table>", rest)
    if not table or re.search(r"(?i)<h2\b", rest[:table.start()]):
        raise RuntimeError(f"No table under 'State Grants' on the Maryland page; {CHANGED}")
    reader = _Tables()
    reader.feed(table.group(0))
    rows = reader.tables[0] if reader.tables else []
    if not rows or [" ".join(_paragraphs(c)).lower() for c in rows[0]] != HEADER:
        raise RuntimeError(f"The Maryland State Grants table's columns changed; {CHANGED}")
    # a notice between the heading and the table is about every row of it
    notice = webpages.clean(page_text(rest[:table.start()]))
    out = []
    for cells in rows[1:]:
        if len(cells) != 3:
            raise RuntimeError(f"A row of the Maryland State Grants table doesn't have three cells; {CHANGED}")
        agency, title, due = (" ".join(_paragraphs(c)) for c in cells)
        if not (agency or title or due):
            continue  # an empty spacer row
        href = next((h.strip() for h, _ in cells[1]["links"] if h.strip()), "")
        out.append({"agency": agency, "title": title, "url": urljoin(LIST, href) if href else LIST, "due": due,
                    "notice": notice})
    if len(out) < MIN_ROWS:
        raise RuntimeError(f"Only {len(out)} rows in the Maryland State Grants table; {CHANGED}")
    if not any(webpages.day(r["due"]) or ROLLING.search(r["due"]) for r in out):
        raise RuntimeError(f"No date could be read in the Maryland State Grants table; {CHANGED}")
    return out


def normalize(row: dict, today: str | None = None) -> dict:
    title = webpages.clean(row["title"])
    closes = webpages.day(row["due"])
    # The link's hash is part of the key, so two calls with one title stay apart.
    key = f"{webpages.slug(title)}-{hashlib.sha1(row['url'].encode('utf-8')).hexdigest()[:6]}"
    application = [f"Due date as the table gives it: {webpages.clean(row['due'])}." if webpages.clean(row["due"]) else "",
                   "Open the agency's page for this grant and apply as it says."]
    return webpages.record("MD", key, title, webpages.clean(row["agency"]), row["url"], LIST, WHO, True, closes=closes,
                           rolling=not closes and bool(ROLLING.search(row["due"])), deadline_words=row["due"],
                           application=" ".join(t for t in application if t), today=today)


def build_records(items: list[dict], today: str | None = None, skips: list[dict] | None = None) -> list[dict]:
    """Open calls, one per row. Rows dropped are added to skips, when given."""
    rows = []
    for item in items:
        record = normalize(item, today)
        notes = " ".join(re.findall(r"\(([^)]*)\)", item["title"]))
        row = {"record": record, "closed": webpages.doubt([item["due"], notes]) or webpages.not_taking([item["notice"]])}
        if record["deadlines"] == "Ongoing":   # no date ends it: the cell's yes, and nothing against it
            row.update(rolling=[item["due"]], about=[item["due"], notes, item.get("notice", "")])
        rows.append(row)
    return webpages.keep_open("maryland", rows, today, skips)


def build(out: Path, skipped_out: Path | None = None, saved: Path | None = None) -> int:
    page = saved.read_text(encoding="utf-8", errors="replace") if saved else webpages.get(LIST)
    skips: list[dict] = []
    records = build_records(parse(page), skips=skips)
    return webpages.write("MD", SOURCE, records, skips, out, skipped_out, "Maryland")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="data/maryland.json.gz", type=Path)
    ap.add_argument("--skipped", type=Path)
    ap.add_argument("--file", type=Path, help="a saved copy of the page, instead of fetching it")
    args = ap.parse_args()
    build(args.out, args.skipped, args.file)


if __name__ == "__main__":
    main()
