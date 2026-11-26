"""Tennessee grants from the Tennessee Arts Commission's own pages. This is partial coverage, not a statewide list.

tnartscommission.org/grants/ links one page per grant program. Most end with the same headings: "For Projects
Occurring", "Application Dates & Deadlines", "Eligible Applicants" and "Funding Requests". The deadline, who may
apply, the amount and the match come from those. A program the page says is closed is left out, and so is one whose
deadline is only "30 days before the project" or that gives none; a rolling one is kept with the last date its page
gives. A run stops, keeping the previous data file, when the list is gone, a dated page loses its eligibility list or
too few pages give dates. robots.txt and the site's privacy policy were checked on 2026-11-26; the policy points to a
statewide tn.gov statement that isn't requested, since tn.gov turns scripts away (docs/state-coverage.md).

Records use the same fields as Ohio's (grantmatch/ohio.py), so the same scorer reads them.

Run:  python -m grantmatch.tennessee --out data/tennessee.json.gz [--skipped build/skipped-tennessee.json.gz]
      add --dir <folder> to read saved copies (grants.html and one <last part of the program's address>.html each)
"""
from __future__ import annotations

import argparse
import re
from datetime import date
from pathlib import Path
from urllib.parse import urljoin, urlparse

from . import webpages
from .minnesota import _lines

LIST = "https://tnartscommission.org/grants/"
AGENCY = "Tennessee Arts Commission"
SOURCE = "Tennessee Arts Commission grant pages (tnartscommission.org), one agency only"
MIN_ROWS = 10   # the Commission lists about twenty programs; fewer than this means the page changed shape
MIN_DATED = 8   # most programs have the dates heading; fewer than this means their pages changed shape
DATES = re.compile(r"^(?:Application Dates\b|Dates (?:&|and) Deadlines)", re.I)
ELIGIBLE = re.compile(r"^Eligible Applicants\b", re.I)
FUNDING = re.compile(r"^Funding Requests\b", re.I)
OCCURRING = re.compile(r"^For (?:Projects|Operations) Occurring\b", re.I)
DEADLINE = re.compile(r"\bapplication (?:submission )?deadline\b", re.I)
ROLLING = re.compile(r"\brolling\b|\bcontinual basis\b", re.I)
UNTIL = re.compile(r"\buntil ([A-Z][a-z]+ \d{1,2}, \d{4})")
RATIO = re.compile(r"\b(?:requires a (\d+:\d+)( cash or in-kind| cash| in-kind)? match|with a (\d+:\d+) match required)", re.I)
DOLLAR = re.compile(r"\brequires a dollar-for-dollar match\b", re.I)
NONE_NEEDED = re.compile(r"\(non-matching\)|\(no match\)|\bdoes not require a match\b|\bno match (?:is )?required\b", re.I)
CHANGED = "keeping the previous data file"
HOW = "Apply in the Commission's online grants system; read the program's guidelines first."


def parse(page: str) -> list[str]:
    """The address of each program's page, from the headings on the grants page."""
    start = page.find("<h1")
    found = []
    for x in _lines(page[start if start > 0 else 0:]):
        if x["head"] != "h3":
            continue
        for href, _ in x["links"]:
            url = urljoin(LIST, href.split("#")[0])
            if url.startswith(LIST) and url != LIST and url not in found:
                found.append(url)
    if len(found) < MIN_ROWS:
        raise RuntimeError(f"Only {len(found)} programs on the Tennessee Arts Commission page; {CHANGED}")
    return found


def parse_program(page: str, url: str, today: str | None = None) -> dict:
    """One program's page: {"record": ..., "closed": the page's words, "dated": whether it has the dates heading}."""
    today = today or date.today().isoformat()
    start = page.find("<h1")
    lines = _lines(page[start:]) if start > 0 else []
    if not lines:
        raise RuntimeError(f"A Tennessee program page has no heading ({url}); {CHANGED}")
    lines = lines[:next((i for i, x in enumerate(lines) if x["text"].startswith("Address:")), len(lines))]
    title = lines[0]["text"]

    def under(heading: re.Pattern) -> list[str]:
        at = next((i for i, x in enumerate(lines) if x["head"] and heading.search(x["text"])), None)
        found = []
        for x in lines[at + 1:] if at is not None else []:
            if x["head"]:
                break
            found.append(x["text"])
        return found

    dates, eligible, funding = under(DATES), under(ELIGIBLE), under(FUNDING)
    deadline = next((t for t in dates if DEADLINE.search(t)), "")
    closes = webpages.day(deadline)
    rolling = False
    if not closes and (said := next((t for t in dates if ROLLING.search(t)), "")):
        until = UNTIL.search(said)
        closes = webpages.day(until.group(1)) if until else None
        rolling = not closes
    opens = next((webpages.day(t) for t in dates if re.match(r"application opens?\b", t, re.I)), None)
    if (closes or rolling) and not eligible:
        raise RuntimeError(f"Tennessee's {title} page has dates but no eligibility list; {CHANGED}")
    who = "; ".join(t.rstrip(".;") for t in eligible)
    money = " ".join(funding)
    ratio = RATIO.search(money)
    if ratio:
        match = f"{ratio.group(1) or ratio.group(3)}{ratio.group(2) or ''}"
    else:
        match = "1:1" if DOLLAR.search(money) else ""
    about_at = next((i for i, x in enumerate(lines) if x["text"].startswith("Important")), None)
    about = lines[about_at + 1]["text"] if about_at is not None and about_at + 1 < len(lines) else ""
    occurring = under(OCCURRING)
    record = webpages.record(
        "TN", webpages.slug(title), title, AGENCY, url, LIST,
        who or "Not stated on the agency's page; read the notice", webpages.open_to_nonprofits(who),
        closes=closes, opens=opens, rolling=rolling, deadline_words=deadline or " ".join(dates), objectives=about,
        award=" ".join(t for t in funding if "$" in t or t.endswith(":")), match=match,
        match_none=not match and bool(NONE_NEEDED.search(money)),
        restrictions=f"For projects occurring: {occurring[0]}" if occurring else "",
        funding_method="Reimbursement" if re.search(r"\bget reimbursed\b|\breimbursed (?:to grantee )?after\b", money, re.I)
        else "",
        loi=any("letter of intent" in t.lower() for t in dates), application=" ".join([*dates, HOW]), today=today)
    return {"record": record, "closed": webpages.not_taking([x["text"] for x in lines], today, opens),
            "dated": bool(dates)}


def read_rows(page: str, program_page, today: str | None = None) -> list[dict]:
    """One row per program. `program_page(url)` gives a program's page."""
    rows = [parse_program(program_page(url), url, today) for url in parse(page)]
    dated = sum(r["dated"] for r in rows)
    if dated < MIN_DATED:
        raise RuntimeError(f"Only {dated} Tennessee program pages have a dates heading; {CHANGED}")
    return rows


def build_records(rows: list[dict], today: str | None = None, skips: list[dict] | None = None) -> list[dict]:
    return webpages.keep_open("tennessee", rows, today, skips)


def build(out: Path, skipped_out: Path | None = None, saved: Path | None = None) -> int:
    def read_saved(name: str) -> str:
        return (saved / f"{name}.html").read_text(encoding="utf-8", errors="replace")

    if saved:
        rows = read_rows(read_saved("grants"), lambda url: read_saved(urlparse(url).path.rstrip("/").rsplit("/", 1)[-1]))
    else:
        rows = read_rows(webpages.get(LIST), webpages.get_next)
    skips: list[dict] = []
    records = build_records(rows, skips=skips)
    return webpages.write("TN", SOURCE, records, skips, out, skipped_out, "Tennessee Arts Commission")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="data/tennessee.json.gz", type=Path)
    ap.add_argument("--skipped", type=Path)
    ap.add_argument("--dir", type=Path, help="a folder of saved copies of the pages, instead of fetching them")
    args = ap.parse_args()
    build(args.out, args.skipped, args.dir)


if __name__ == "__main__":
    main()
