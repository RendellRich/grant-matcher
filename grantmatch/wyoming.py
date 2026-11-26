"""Wyoming grants from the Wyoming Arts Council's own pages. This is partial coverage, not a statewide list.

wyoarts.state.wy.us/grants/ links one page per grant. Each gives either "Grant Opens" and "Grant Closes" dates or the
year's rounds ("Round Three: Jan 1 - Feb 1, 2027"); the next round that hasn't closed is shown. Who may apply and the
match are the page's own sentences. A run stops, keeping the previous data file, when the list is gone or a grant's
page gives neither form of date. robots.txt and the privacy policy the site links were checked on 2026-11-26
(docs/state-coverage.md).

Records use the same fields as Ohio's (grantmatch/ohio.py), so the same scorer reads them.

Run:  python -m grantmatch.wyoming --out data/wyoming.json.gz [--skipped build/skipped-wyoming.json.gz]
      add --dir <folder> to read saved copies (grants.html and one <last part of the grant's address>.html each)
"""
from __future__ import annotations

import argparse
import re
from datetime import date
from pathlib import Path
from urllib.parse import urljoin, urlparse

from . import webpages
from .minnesota import NONPROFIT, _lines

LIST = "https://wyoarts.state.wy.us/grants/"
AGENCY = "Wyoming Arts Council"
SOURCE = "Wyoming Arts Council grant pages (wyoarts.state.wy.us), one agency only"
MIN_ROWS = 3  # the Council lists five grants; fewer than this means the page changed shape
ORGANIZATIONS = re.compile(r"\borganizations?\b", re.I)
# Who may apply, the plainer wording first: "eligible to receive up to ..." is often about the amount.
WHO = (re.compile(r"\bopen to\b|\bis available to\b", re.I), re.compile(r"\b(?:is|are) eligible\b", re.I))
ROUND = re.compile(r"^Round \w+:\s*([A-Z][a-z]+)\.? (\d{1,2})(?:, (\d{4}))?\s*[\u2013\u2014-]\s*([A-Z][a-z]+)\.? (\d{1,2}), (\d{4})")
MONTHS = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
CHANGED = "keeping the previous data file"
HOW = "Apply in the Council's online grant system from the grant's page."


def parse(page: str) -> list[str]:
    """The address of each grant's page, from the headings on the grants page."""
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
        raise RuntimeError(f"Only {len(found)} grants on the Wyoming Arts Council page; {CHANGED}")
    return found


def _round(m: re.Match) -> tuple[str, str] | None:
    """(opens, closes) of a "Round Two: Aug 1 - Sept 1, 2026" line; the start takes the end's year unless it says."""
    try:
        end = date(int(m.group(6)), MONTHS[m.group(4)[:3].lower()], int(m.group(5)))
        first = MONTHS[m.group(1)[:3].lower()]
        year = int(m.group(3)) if m.group(3) else end.year - (1 if first > end.month else 0)
        return date(year, first, int(m.group(2))).isoformat(), end.isoformat()
    except (KeyError, ValueError):
        return None


def _said(iso: str) -> str:
    """"2027-02-01" as "February 1, 2027"."""
    d = date.fromisoformat(iso)
    return f"{d:%B} {d.day}, {d.year}"


def parse_grant(page: str, url: str, today: str | None = None) -> dict:
    """One grant's page: {"record": ..., "closed": the page's words, when it says it isn't taking applications}."""
    today = today or date.today().isoformat()
    start = page.find("<h1")
    lines = _lines(page[start:]) if start > 0 else []
    if not lines:
        raise RuntimeError(f"A Wyoming grant page has no heading ({url}); {CHANGED}")
    title = lines[0]["text"]
    texts = [x["text"] for x in lines[1:]]

    def labelled(label: str) -> str | None:
        return next((webpages.day(t) for t in texts if t.lower().startswith(label)), None)

    opens, closes = labelled("grant opens:"), labelled("grant closes:")
    rounds = [(t, _round(m)) for t in texts if (m := ROUND.match(t))]
    if not closes and rounds and all(dates for _, dates in rounds):
        ahead = [dates for _, dates in rounds if dates[1] >= today]
        opens, closes = ahead[0] if ahead else rounds[-1][1]
    if not closes:
        raise RuntimeError(f"Wyoming's {title} page gives no closing date or rounds; {CHANGED}")

    def sentences(pattern: re.Pattern) -> list[str]:
        return [t for t in texts if pattern.search(t)]

    eligible = next((found[:1] for found in map(sentences, WHO) if found), [])
    eligible += sentences(re.compile(r"\bartists cannot apply\b", re.I))[:1]
    applicants = " ".join(dict.fromkeys(eligible))
    named = eligible[0] if eligible else ""
    matches = sentences(re.compile(r"\bmatch\b", re.I))[:2]
    cash = re.search(r"\brequires? a (\d+:\d+) cash match\b", " ".join(matches), re.I)
    notes = list(dict.fromkeys(t for t, _ in rounds)) + sentences(re.compile(r"\bmust be submitted\b", re.I))[:1]
    window = f"Applications open {_said(opens)} and close {_said(closes)}." if opens else ""
    record = webpages.record(
        "WY", webpages.slug(title), title, AGENCY, url, LIST,
        applicants or "Not stated on the agency's page; read the notice",
        bool(NONPROFIT.search(named) or ORGANIZATIONS.search(named)) if named else True,
        closes=closes, opens=opens, objectives=texts[0] if texts else "",
        award=next((t for t in texts if "$" in t and re.search(r"\bup to\b|\beligible to receive\b|\beach\b", t, re.I)), ""),
        match=f"{cash.group(1)} cash" if cash else "", restrictions=" ".join(matches),
        application=" ".join(t for t in [window, *notes, HOW] if t), today=today)
    return {"record": record, "closed": next((t for t in texts if webpages.NOT_TAKING.search(t)), "")}


def read_rows(page: str, grant_page, today: str | None = None) -> list[dict]:
    """One row per grant. `grant_page(url)` gives a grant's page."""
    return [parse_grant(grant_page(url), url, today) for url in parse(page)]


def build_records(rows: list[dict], today: str | None = None, skips: list[dict] | None = None) -> list[dict]:
    return webpages.keep_open("wyoming", rows, today, skips)


def build(out: Path, skipped_out: Path | None = None, saved: Path | None = None) -> int:
    def read_saved(name: str) -> str:
        return (saved / f"{name}.html").read_text(encoding="utf-8", errors="replace")

    if saved:
        rows = read_rows(read_saved("grants"), lambda url: read_saved(urlparse(url).path.rstrip("/").rsplit("/", 1)[-1]))
    else:
        rows = read_rows(webpages.get(LIST), webpages.get_next)
    skips: list[dict] = []
    records = build_records(rows, skips=skips)
    return webpages.write("WY", SOURCE, records, skips, out, skipped_out, "Wyoming Arts Council")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="data/wyoming.json.gz", type=Path)
    ap.add_argument("--skipped", type=Path)
    ap.add_argument("--dir", type=Path, help="a folder of saved copies of the pages, instead of fetching them")
    args = ap.parse_args()
    build(args.out, args.skipped, args.dir)


if __name__ == "__main__":
    main()
