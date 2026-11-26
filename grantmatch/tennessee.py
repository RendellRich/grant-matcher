"""Tennessee grants from the Tennessee Arts Commission's own pages. This is partial coverage, not a statewide list.

tnartscommission.org/grants/ links one page per grant program. Most end with the same headings: "For Projects
Occurring", "Application Dates & Deadlines", "Eligible Applicants" and "Funding Requests". The deadline, who may
apply, the amount and the match come from those. A program the page says is closed is left out, and so is one whose
deadline is only "30 days before the project" or that gives none; a rolling one is kept with the last date its page
gives, and only while the page says it is taking applications and nothing on it says closed, paused or out of money.
Where a page says first-time applicants must do something by a date, "How to apply" and "Who can apply" say so. A run
stops, keeping the previous data file, when the list is gone, a dated page loses its eligibility or "Funding Requests"
list, a first-time requirement gives no readable date or too few pages give dates. robots.txt and the site's privacy policy were checked on 2026-11-26; the policy points to a
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
# Said anywhere on the page. The bracketed forms are read only under "Funding Requests", where they are about the grant.
NONE_NEEDED = re.compile(r"\bdoes not require a match\b|\bno match(?:ing)?(?: funds?)? (?:is |are )?required\b", re.I)
NONE_MARKED = re.compile(r"\(non-matching\)|\(no match\)", re.I)
FIRST_TIME = re.compile(r"^First[- ]time applicants\b.*\bmust:?$", re.I)
BY_DATE = re.compile(r"\bby ([A-Z][a-z]+\.? \d{1,2})(?:, (\d{4}))?")
# an eligibility line that is about getting into the category, which only a first-time applicant has to do
ENTRY = re.compile(r"\brequest\b[^.;]{0,40}?\b(?:for|of) entry\b|\bletter requesting entry\b", re.I)
UEI = re.compile(r"\b(?:all applicants (?:are required to|must)\b.*\b(?:Unique Entity|UEI)|UEI will be required)\b", re.I)
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


def _first_time(lines: list[dict], closes: str | None, title: str) -> tuple[str, str | None]:
    """What the page says first-time applicants must do, and its date: ("", None) when it asks nothing of them."""
    at = next((i for i, x in enumerate(lines) if FIRST_TIME.search(x["text"])), None)
    if at is None:
        return "", None
    steps = []
    for x in lines[at + 1:]:
        if not x["item"]:
            break
        steps.append(x["text"])
    step = next((t for t in steps if BY_DATE.search(t)), "")
    if not step:
        if any(re.search(r"\bby\b|\bdeadline\b|\bdue\b", t, re.I) for t in steps):
            raise RuntimeError(f"Tennessee's {title} page asks first-time applicants for something by a date this "
                               f"can't read; {CHANGED}")
        return "", None
    said = BY_DATE.search(step)
    # no year on the page: the one that puts the date before the application deadline
    day = None
    if said.group(2):
        day = webpages.day(f"{said.group(1)}, {said.group(2)}")
    elif closes:
        day = webpages.day(f"{said.group(1)}, {closes[:4]}")
        if day and day > closes:
            day = webpages.day(f"{said.group(1)}, {int(closes[:4]) - 1}")
    # its first sentence, which holds the date; the rest is how to write the letter
    words = re.sub(r"^and\s+", "", re.split(r"(?<=\.)\s+(?=[A-Z])", step)[0])
    before = [re.sub(r",?\s*(?:and then|and)$", "", t).rstrip(";,.") for t in steps[:steps.index(step)]]
    return f"{lines[at]['text'].rstrip(':')}: {'; '.join([*before, words.rstrip('.')])}.", day


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
    # the match and the award come from "Funding Requests": renamed, they would go blank without a word
    if (closes or rolling) and not funding:
        raise RuntimeError(f"Tennessee's {title} page has dates but no 'Funding Requests' lines; {CHANGED}")
    first, entry_day = _first_time(lines, closes, title)
    who = "; ".join(f"For first-time applicants: {t.rstrip('.;')}" if first and ENTRY.search(t) else t.rstrip(".;")
                    for t in eligible)
    if first and who and "first-time" not in who.lower():
        who = f"{first.rstrip('.')}; {who}"
    # said first, since it can rule a new applicant out of this round (as minnesota.py puts a passed intent date)
    if first and entry_day and entry_day < today:
        first += " That date has passed; check the notice before you start."
    every = [x["text"] for x in lines]
    nothing = next((s for t in every for s in re.split(r"(?<=[.!?])\s+", t) if NONE_NEEDED.search(s)), "")
    uei = next((s for t in every for s in re.split(r"(?<=[.!?])\s+", t) if UEI.search(s)), "")
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
        match_none=not match and bool(nothing or NONE_MARKED.search(money)),
        restrictions=" ".join(t for t in (f"For projects occurring: {occurring[0].rstrip('.')}." if occurring else "",
                                          uei, "" if match or NONE_MARKED.search(money) else nothing) if t),
        funding_method="Reimbursement" if re.search(r"\bget reimbursed\b|\breimbursed (?:to grantee )?after\b", money, re.I)
        else "",
        loi=bool(first) or any("letter of intent" in t.lower() for t in dates),
        application=" ".join(t for t in (first, *dates, HOW) if t), today=today)
    row = {"record": record, "closed": webpages.not_taking(every, today, opens), "dated": bool(dates)}
    # a rolling call, dated or not, can end before any date does: kept only on a yes and nothing against it
    if said_rolling := [t for t in dates if ROLLING.search(t)]:
        row.update(rolling=said_rolling, about=every)
    return row


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
