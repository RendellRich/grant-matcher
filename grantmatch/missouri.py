"""Missouri grants from three agencies' pages. This is partial coverage, not a statewide list.

Read: the Department of Natural Resources' public notices filtered to grants (dnr.mo.gov), with each linked program
page on the same host; the Missouri Arts Council's grants, apply for funding and Express Grants pages
(missouriartscouncil.org); and ServMO's grant opportunities page (serv.mo.gov). Only calls a nonprofit could apply to
are kept: one that names nonprofits, or, for ServMO, one whose page doesn't say who may apply.

Not read: PDFs, and a notice whose program page is on another site (it is dropped and named in the skipped list).

mo.gov's data policy (https://mo.gov/data-policy, read 2026-11-27) requires its disclaimer on sites that use the
data: web/src/disclaimers.json holds the words, and the site, its downloads and its emails add them to anything that
lists a Missouri call. The policy also lets the State require that the display stop (docs/state-coverage.md). A run
stops, keeping the previous data file, when a page loses the part its dates come from.

Records use the same fields as Ohio's (grantmatch/ohio.py), so the same scorer reads them.

Run:  python -m grantmatch.missouri --out data/missouri.json.gz [--skipped build/skipped-missouri.json.gz]
      add --dir <folder> to read saved copies (notices.html, one <last part of its address>.html per program page,
      grants.html, apply.html, express.html and serve.html)
"""
from __future__ import annotations

import argparse
import re
from datetime import date
from html import unescape
from pathlib import Path
from urllib.parse import urljoin, urlparse

from . import webpages
from .minnesota import NONPROFIT, _lines

DNR = "https://dnr.mo.gov/"
LIST = DNR + "public-notices-comments?field_pub_notice_topic_name_value=grant"
COUNCIL = "https://missouriartscouncil.org/"
GRANTS = COUNCIL + "grants/"
APPLY = COUNCIL + "apply-for-funding/"
EXPRESS = COUNCIL + "express-grants/"
SERVE = "https://serv.mo.gov/grant-opportunities/"
NATURAL = "Missouri Department of Natural Resources"
ARTS = "Missouri Arts Council"
SERVMO = "Missouri Community Service Commission (ServMO)"
SOURCE = "Missouri Natural Resources grant notices, Arts Council and ServMO pages only"
CHANGED = "keeping the previous data file"
UNSTATED = "Not stated on the agency's page; read the notice"
DATE_WORDS = r"([A-Z][a-z]+ \d{1,2}, \d{4})"


def _sentences(texts: list[str]) -> list[str]:
    return [s for t in texts for s in re.split(r"(?<=[.!?])\s+", t) if s]


def _first(texts: list[str], pattern: str) -> str:
    return next((s for s in _sentences(texts) if re.search(pattern, s, re.I)), "")


def _section(lines: list[dict], pattern: str) -> list[str]:
    """The lines under the heading that matches, up to the next heading."""
    at = next((i for i, x in enumerate(lines) if x["head"] and re.search(pattern, x["text"], re.I)), None)
    out = []
    for x in lines[at + 1:] if at is not None else []:
        if x["head"]:
            break
        out.append(x["text"])
    return out


def notices(page: str) -> list[dict]:
    """One entry per row of the DNR notice table: the program's title and page, and the application period."""
    body = re.search(r"<tbody>(.*?)</tbody>", page, re.S)
    if not body or re.search(r"(?:\?|&|&amp;)page=\d", page):   # a second page of notices would be missed
        raise RuntimeError(f"Missouri's grant notice table has changed; {CHANGED}")
    out = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", body.group(1), re.S):
        cell = dict(re.findall(r'<td headers="view-field-([\w-]+?)-table-column"[^>]*>(.*?)</td>', row, re.S))
        link = re.search(r'<a href="([^"]+)"[^>]*>(.*?)</a>', cell.get("pub-notice-topic-name", ""), re.S)
        opens, closes = (webpages.day(" ".join(x["text"] for x in _lines(cell.get(k, ""))))
                         for k in ("meeting-date-time", "event-date-end"))
        if not link or not closes:
            raise RuntimeError(f"A Missouri grant notice no longer has its program link and end date; {CHANGED}")
        out.append({"title": webpages.clean(unescape(link.group(2))), "url": urljoin(LIST, unescape(link.group(1))),
                    "opens": opens, "closes": closes})
    if not out:
        raise RuntimeError(f"Missouri's grant notice table has no rows; {CHANGED}")
    return out


def program(page: str, notice: dict, today: str) -> dict:
    """One DNR program from its own page, with the notice's application period."""
    main = page[page.find("<main"):page.find("</main>")]
    lines = _lines(re.sub(r"(</t[dh]>)", r" \1", main))
    who = _section(lines, r"^Who Can Apply$")
    if not who:
        raise RuntimeError(f"No 'Who Can Apply' on {notice['url']}; {CHANGED}")
    award = _section(lines, r"^Award Amounts? and Match$")
    start = next((i for i, x in enumerate(lines) if x["head"] == "h1"), 0)
    about = next((x["text"] for x in lines[start:] if not x["head"] and len(x["text"]) > 80), "")
    record = webpages.record(
        "MO", webpages.slug(notice["title"]), notice["title"], NATURAL, notice["url"], LIST, " ".join(who),
        bool(NONPROFIT.search(" ".join(who))), closes=notice["closes"], opens=notice["opens"], objectives=about,
        award=" ".join(award), match=_first(award, r"\brequire[sd]? (?:to provide match|a cost[- ]share of|a match of)\b"),
        application=" ".join(_section(lines, r"^Application Process$")), today=today)
    if "Grant Amounts" in award:   # "Revolving Fund" in a title reads as a loan, but this part of the fund gives grants
        record.update(assistance="Grant", loan=False)
    return {"record": record, "closed": webpages.not_taking([x["text"] for x in lines], today, notice["opens"])}


def _council(page: str, url: str) -> list[dict]:
    """An Arts Council page's own lines: from its first heading to the footer."""
    lines = _lines(page)
    start = next((i for i, x in enumerate(lines) if x["head"] == "h1"), None)
    end = next((i for i, x in enumerate(lines) if x["text"] == "VISIT US"), None)
    if start is None or end is None or end <= start:
        raise RuntimeError(f"A Missouri Arts Council page has changed ({url}); {CHANGED}")
    return lines[start:end]


def who_may_apply(page: str) -> str:
    lines = _council(page, APPLY)
    # the section titles on this page are plain lines, not headings
    at = next((i for i, x in enumerate(lines) if x["text"] == "Who may apply"), None)
    end = next((i for i, x in enumerate(lines) if x["text"] == "What makes a strong application"), None)
    if at is None or end is None or end <= at + 1:
        raise RuntimeError(f"The Missouri Arts Council no longer says who may apply; {CHANGED}")
    return " ".join(x["text"] for x in lines[at + 1:end])


def express(page: str, who: str, today: str) -> dict:
    """Express Grants: rolling, so listed only on the page's own yes and nothing against it."""
    texts = [x["text"] for x in _council(page, EXPRESS)]
    taking = [s for s in _sentences(texts)
              if re.search(r"\bapplications are accepted\b|\bcurrently accepting applications\b", s, re.I)]
    deadline = " ".join(t for t in texts if t.startswith("The deadline for applications is"))
    closed = webpages.not_taking(texts, today)
    if not closed and not deadline:
        raise RuntimeError(f"The Missouri Express Grants page no longer gives its deadline rule; {CHANGED}")
    record = webpages.record(
        "MO", "express-grants", "Express Grants", ARTS, EXPRESS, GRANTS, who, bool(NONPROFIT.search(who)),
        rolling=True, deadline_words=deadline, objectives=_first(texts, r"\bExpress Grants are designed\b"),
        award=_first(texts, r"\bmaximum request amount\b"),
        match_none=bool(_first(texts, r"\bno matching funds are required\b")),
        application=f"{deadline} Apply in the Council's SmartSimple grant portal.", today=today)
    return {"record": record, "closed": closed, "rolling": taking, "about": texts}


def annual(page: str, who: str, today: str) -> dict:
    """Annual Grants for a first-time applicant: the Intent to Apply is the one date the page gives them."""
    texts = [x["text"] for x in _council(page, GRANTS)]
    said = next((m for s in _sentences(texts)
                 if (m := re.search(rf"deadline for the FY(\d{{4}}) Intent to Apply is (?:\w+day, )?{DATE_WORDS}", s))),
                None)
    if not said:
        raise RuntimeError(f"The Missouri grants page no longer gives the Intent to Apply deadline; {CHANGED}")
    year, due = said.groups()
    programs = _first(texts, r"\bWe are accepting applications for these programs\b")
    record = webpages.record(
        "MO", f"annual-grants-fy{year}", f"Annual Grants FY{year}, new applicants (Intent to Apply)", ARTS, GRANTS,
        GRANTS, who, bool(NONPROFIT.search(who)), closes=webpages.day(due), objectives=programs,
        match=_first(texts, r"\baward cannot exceed 50% of total project expenses\b"),
        application=f"Intent to Apply deadline for new applicants: {due}. The application itself comes after it; "
                    "read the grants page for its date. Apply in the Council's SmartSimple grant portal.",
        today=today)
    return {"record": record, "closed": webpages.not_taking([said.string, programs], today)}


def serve(page: str, today: str) -> list[dict]:
    """ServMO's funding opportunities. The page doesn't say who may apply."""
    texts = [x["text"] for x in _lines(page)]
    end = next((i for i, t in enumerate(texts) if t.startswith("ServMO | AmeriCorps in Missouri")), len(texts))
    texts = texts[:end]
    starts = [i for i, t in enumerate(texts)
              if len(t) < 120 and re.search(r"\bFunding Opportunity(?:\s*\W\s*\w+ Funding)?$", t)]
    if not starts:
        raise RuntimeError(f"No funding opportunities on ServMO's page; {CHANGED}")
    rows = []
    for at, until in zip(starts, [*starts[1:], len(texts)]):
        title, body = texts[at], texts[at + 1:until]
        words = " ".join(body)
        due = re.search(rf"deadline to submit an application is {DATE_WORDS}", words)
        intent = re.search(rf"Notice of Intent by {DATE_WORDS}", words)
        closed = webpages.not_taking(body, today) or ("" if due else _first(body, r"\bhas passed\b"))
        if not due and not closed:
            raise RuntimeError(f"ServMO's '{title}' gives no application deadline; {CHANGED}")
        notes = []
        if intent:
            passed = " That date has passed; check the notice before you start." \
                if (webpages.day(intent.group(1)) or "9999") < today else ""
            notes.append(f"Notice of Intent deadline: {intent.group(1)}.{passed}")
        if due:
            notes.append(f"Application deadline: {due.group(1)}.")
        record = webpages.record(
            "MO", webpages.slug(title), title, SERVMO, SERVE, SERVE, UNSTATED, True,
            closes=webpages.day(due.group(1)) if due else None, application=" ".join(notes), loi=bool(intent),
            today=today)
        rows.append({"record": record, "closed": closed})
    return rows


def read_rows(page, today: str | None = None) -> list[dict]:
    """One row per call. `page(url, name)` gives a page; name is what a saved copy of it is called."""
    today = today or date.today().isoformat()
    rows = []
    for notice in notices(page(LIST, "notices")):
        if urlparse(notice["url"]).netloc != urlparse(DNR).netloc:
            record = webpages.record("MO", webpages.slug(notice["title"]), notice["title"], NATURAL, notice["url"],
                                     LIST, UNSTATED, True, closes=notice["closes"], today=today)
            rows.append({"record": record, "skip": ("page_not_read", f"Its program page: {notice['url']}")})
            continue
        rows.append(program(page(notice["url"], notice["url"].rstrip("/").rsplit("/", 1)[-1]), notice, today))
    who = who_may_apply(page(APPLY, "apply"))
    rows.append(express(page(EXPRESS, "express"), who, today))
    rows.append(annual(page(GRANTS, "grants"), who, today))
    return [*rows, *serve(page(SERVE, "serve"), today)]


def build_records(rows: list[dict], today: str | None = None, skips: list[dict] | None = None) -> list[dict]:
    return webpages.keep_open("missouri", rows, today, skips, nonprofits_only=True)


def build(out: Path, skipped_out: Path | None = None, saved: Path | None = None) -> int:
    def read_saved(url: str, name: str) -> str:
        return (saved / f"{name}.html").read_text(encoding="utf-8", errors="replace")

    def read_live(url: str, name: str) -> str:
        return (webpages.get if url == LIST else webpages.get_next)(url)

    rows = read_rows(read_saved if saved else read_live)
    skips: list[dict] = []
    records = build_records(rows, skips=skips)
    return webpages.write("MO", SOURCE, records, skips, out, skipped_out, "Missouri")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="data/missouri.json.gz", type=Path)
    ap.add_argument("--skipped", type=Path)
    ap.add_argument("--dir", type=Path, help="a folder of saved copies of the pages, instead of fetching them")
    args = ap.parse_args()
    build(args.out, args.skipped, args.dir)


if __name__ == "__main__":
    main()
