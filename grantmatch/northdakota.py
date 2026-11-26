"""North Dakota grants from the Council on the Arts' own pages. This is partial coverage, not a statewide list.

www.arts.nd.gov/grants ("Grants at a Glance") has a card per program: what it pays, who it is for and its deadline,
with "deadline has passed" under the past ones. A card whose deadline is relative ("6 weeks prior to project start
date") is read on the program's own page, which gives the date applications close for the year, the award, the match
and, for some, who is eligible. A card with no "Who" line is read by its "What" line ("grants to individual artists"
leaves nonprofits out). A run stops, keeping the previous data file, when the cards are gone or such a page no
longer gives its closing date. robots.txt and North Dakota's disclaimer, privacy and security pages were checked on
2026-11-26 (docs/state-coverage.md).

Records use the same fields as Ohio's (grantmatch/ohio.py), so the same scorer reads them.

Run:  python -m grantmatch.northdakota --out data/northdakota.json.gz [--skipped build/skipped-northdakota.json.gz]
      add --dir <folder> to read saved copies (grants.html and one <last part of the program's address>.html each)
"""
from __future__ import annotations

import argparse
import re
from datetime import date
from pathlib import Path
from urllib.parse import urljoin, urlparse

from . import webpages
from .cycles import page_text
from .minnesota import NONPROFIT, _lines

LIST = "https://www.arts.nd.gov/grants"
AGENCY = "North Dakota Council on the Arts"
SOURCE = "North Dakota Council on the Arts grant pages (arts.nd.gov), one agency only"
MIN_CARDS = 5  # the page has about nine cards; fewer than this means it changed shape
RELATIVE = re.compile(r"\bweeks? prior to (?:the )?(?:project|start)", re.I)
CLOSES = re.compile(r"Applications for FY\d+ will close on ([A-Z][a-z]+\.? \d{1,2}, \d{4})")
PASSED = re.compile(r"\bdeadline has passed\b", re.I)
CHANGED = "keeping the previous data file"
# A "What" line that gives the money to people, for a card with no "Who" line.
PEOPLE = re.compile(r"\bindividual artists\b|\b(?:to|for) (?:individuals|(?:master(?: traditional)?|traditional) artists)\b",
                    re.I)
HOW = "Apply in the Council's online grants system; read the program's guidelines first."


def parse(page: str) -> list[dict]:
    """The cards: title, the program's page, what it pays, who it is for and its deadline as the card says it."""
    out = []
    for part in re.split(r'(?=<a\s[^>]*class="card-link")', page)[1:]:
        link = re.match(r'<a\s[^>]*?href="([^"]+)"', part)
        title = re.search(r'(?s)field--name-field-featured-area-card-title[^>]*>(.*?)</div>', part)
        body = re.search(r'(?s)field--name-field-featured-area-card-descrip[^>]*>(.*?)</div>', part)
        if not (link and title and body):
            continue
        lines = [x["text"] for x in _lines(body.group(1))]

        def value(label: str) -> str:
            return next((webpages.clean(t[len(label):]) for t in lines if t.lower().startswith(label.lower())), "")

        at = next((i for i, t in enumerate(lines) if t.lower().startswith("deadline")), None)
        deadline = "" if at is None else " ".join(t for t in lines[at:] if not PASSED.search(t))
        out.append({"title": webpages.clean(page_text(title.group(1))).rstrip("."),
                    "url": urljoin(LIST, link.group(1)), "what": value("What:"), "who": value("Who:"),
                    "deadline": re.sub(r"(?i)^deadlines?\s*:\s*", "", deadline),
                    "passed": next((t.lstrip("*") for t in lines if PASSED.search(t)), "")})
    if len(out) < MIN_CARDS:
        raise RuntimeError(f"Only {len(out)} grant cards on the North Dakota arts page; {CHANGED}")
    if not all(c["deadline"] for c in out):
        raise RuntimeError(f"A North Dakota grant card has no deadline line; {CHANGED}")
    return out


def parse_program(page: str) -> dict:
    """A program page's closing date, award, match, eligibility and opening sentence."""
    start = page.find("<h1")
    if start < 0:
        raise RuntimeError(f"A North Dakota program page has no heading; {CHANGED}")
    end = page.find("Grant Guidelines - FY", start)
    lines = _lines(page[start:end if end > 0 else len(page)])
    text = " ".join(x["text"] for x in lines)
    closes = CLOSES.search(text)

    def under(word: str) -> list[str]:
        """The lines under the heading that holds `word`, up to the next heading."""
        at = next((i for i, x in enumerate(lines) if x["head"] and word in x["text"].lower()), None)
        found = []
        for x in lines[at + 1:] if at is not None else []:
            if x["head"]:
                break
            found.append(x["text"])
        return found

    # A match belongs to the label above it ("Title 1 and/or 21st Century Schools:"), when the page has one.
    shares, label = [], ""
    for x in lines:
        if x["head"]:
            label = ""
        elif x["text"].endswith(":"):
            label = x["text"].rstrip(":").strip()
        shares += [(m.group(1), label) for m in re.finditer(r"(\d{1,2})% (?:cash )?match (?:is )?required", x["text"], re.I)]
    return {
        "closes": webpages.day(closes.group(1)) if closes else None,
        "closed": webpages.not_taking([x["text"] for x in lines]),
        # the opening paragraph is its own line, so photo captions above it never come along
        "about": next((x["text"] for x in lines if re.search(r"\bprovides? up to \$", x["text"], re.I)), ""),
        "eligible": " ".join(under("eligibility")),
        # amounts, and the labels that say whose they are
        "award": " ".join(t for t in under("award") if "$" in t or t.endswith(":")),
        "match": shares,
    }


def _dates(card: dict) -> list[str]:
    """The full dates in a card's deadline."""
    return [d for d in (webpages.day(t) for t in re.findall(r"[A-Z][a-z]+\.? \d{1,2}, \d{4}", card["deadline"])) if d]


def normalize(card: dict, program: dict | None = None, today: str | None = None) -> dict:
    program = program or {}
    today = today or date.today().isoformat()
    relative = bool(RELATIVE.search(card["deadline"]))
    # A card with dates lists each round's: the next one is shown, or the last when all have passed (so it is dropped).
    dates = _dates(card)
    ahead = [d for d in dates if d >= today]
    closes = program.get("closes") if relative else (min(ahead) if ahead else max(dates) if dates else None)
    who = program.get("eligible") or card["who"]
    about = program.get("about", "")
    # The opening sentence names who the money is for on some pages ("... for North Dakota nonprofit art organizations").
    applicants = " ".join(t for t in (who, about if NONPROFIT.search(about) and not program.get("eligible") else "") if t)
    nonprofit = webpages.open_to_nonprofits(applicants)
    if not applicants:
        # no "Who" line: the card's "What" still says when the money goes to people, or to organizations
        what = card["what"]
        for_organizations = bool(NONPROFIT.search(what) or webpages.ORGANIZATIONS.search(what))
        if PEOPLE.search(what) or for_organizations:
            applicants = f"As the Council's card puts it: {what.rstrip('.')}."
            nonprofit = for_organizations and webpages.open_to_nonprofits(what)
    shares = list(dict.fromkeys(program.get("match", [])))
    if len({share for share, _ in shares}) > 1:
        named = all(label for _, label in shares)
        match = ("; " if named else " or ").join(f"{share}% for {label}" if named else f"{share}%" for share, label in shares)
    else:
        match = f"{shares[0][0]}%" if shares else ""
    notes = [f"Deadline as the Council gives it: {card['deadline']}." if card["deadline"] else "",
             "Apply at least six weeks before your project starts." if relative else "", HOW]
    return webpages.record(
        "ND", webpages.slug(card["title"]), card["title"], AGENCY, card["url"], LIST,
        applicants or "Not stated on the agency's page; read the notice",
        nonprofit,
        closes=closes, deadline_words=card["deadline"], objectives=about or card["what"],
        award=program.get("award") or card["what"], match=match,
        funding_method="Reimbursement" if re.search(r"\breimbursement grant\b", about, re.I) else "",
        application=" ".join(t for t in notes if t), today=today)


def read_rows(page: str, program_page, today: str | None = None) -> list[dict]:
    """One row per card. `program_page(url)` gives a program's page. It is needed for a relative deadline, and for an
    open card whose own words leave nonprofits out ("Educational institutions"), since the page may name them."""
    today = today or date.today().isoformat()
    out = []
    for card in parse(page):
        program = None
        relative = bool(RELATIVE.search(card["deadline"]))
        # (a card with no "Who" line is read by its "What" line instead, in normalize)
        left_out = not webpages.open_to_nonprofits(card["who"]) and any(d >= today for d in _dates(card))
        if (relative and not card["passed"]) or left_out:
            program = parse_program(program_page(card["url"]))
            if relative and not program["closes"] and not program["closed"]:
                raise RuntimeError(f"North Dakota's {card['title']} page no longer says when applications close; {CHANGED}")
        record = normalize(card, program, today)
        closed = (program or {}).get("closed", "")
        if card["passed"] and not record["closes"]:
            closed = card["passed"]
        out.append({"record": record, "closed": closed})
    return out


def build_records(rows: list[dict], today: str | None = None, skips: list[dict] | None = None) -> list[dict]:
    return webpages.keep_open("northdakota", rows, today, skips)


def build(out: Path, skipped_out: Path | None = None, saved: Path | None = None) -> int:
    def read_saved(name: str) -> str:
        return (saved / f"{name}.html").read_text(encoding="utf-8", errors="replace")

    if saved:
        rows = read_rows(read_saved("grants"), lambda url: read_saved(urlparse(url).path.rstrip("/").rsplit("/", 1)[-1]))
    else:
        def program_page(url: str) -> str:
            if urlparse(url).netloc != urlparse(LIST).netloc:
                raise RuntimeError(f"A North Dakota card links another site ({url}); {CHANGED}")
            return webpages.get_next(url)

        rows = read_rows(webpages.get(LIST), program_page)
    skips: list[dict] = []
    records = build_records(rows, skips=skips)
    return webpages.write("ND", SOURCE, records, skips, out, skipped_out, "North Dakota Council on the Arts")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="data/northdakota.json.gz", type=Path)
    ap.add_argument("--skipped", type=Path)
    ap.add_argument("--dir", type=Path, help="a folder of saved copies of the pages, instead of fetching them")
    args = ap.parse_args()
    build(args.out, args.skipped, args.dir)


if __name__ == "__main__":
    main()
