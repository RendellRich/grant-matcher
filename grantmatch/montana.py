"""Montana grants from the Montana Arts Council's own pages. This is partial coverage, not a statewide list.

Three pages are read: Arts Education Grants (art.mt.gov/artsed), which links an HTML guidelines page for each of the
Experiences and Residencies grants; Arts in Health (art.mt.gov/artsinhealth); and Strategic Investment Grants
(art.mt.gov/sig). An education grant's deadline, award, match and who may apply come from its guidelines page, and
Arts in Health's dates from its "Next opportunity" lines. Strategic Investment Grants take applications every month,
so they have no date to end them: they are listed only while the page says applications are due each month and
nothing on it says closed, paused or out of money.

Not read: the Traditional Arts Apprenticeship page (for individual artists; it says it is accepting applications, but
the only guidelines it links give a 2025 deadline), and programs whose pages gave no open date on 2026-11-26. The
site's /obsolete pages are closed to crawlers and never asked for. A run stops, keeping the previous data file, when a
page loses the part its dates come from. robots.txt was checked and no terms or privacy page for the site is linked
from it (2026-11-26, docs/state-coverage.md).

Records use the same fields as Ohio's (grantmatch/ohio.py), so the same scorer reads them.

Run:  python -m grantmatch.montana --out data/montana.json.gz [--skipped build/skipped-montana.json.gz]
      add --dir <folder> to read saved copies (artsed.html, artsinhealth.html, sig.html, and experiences.html and
      residencies.html for the two guidelines pages)
"""
from __future__ import annotations

import argparse
import re
from datetime import date
from pathlib import Path
from urllib.parse import urljoin, urlparse

from . import webpages
from .minnesota import NONPROFIT, _lines

SITE = "https://art.mt.gov/"
LIST = SITE + "artsed"
HEALTH = SITE + "artsinhealth"
INVESTMENT = SITE + "sig"
AGENCY = "Montana Arts Council"
SOURCE = "Montana Arts Council grant pages (art.mt.gov), one agency only"
CHANGED = "keeping the previous data file"
APPLY_HOW = "Apply in the Council's online grants system; read the guidelines first."
EDUCATION = ("Experiences", "Residencies")
DEADLINE = re.compile(r"^([A-Z][a-z]+ \d{1,2}, \d{4}) at \d{1,2}(?::\d{2})? ?[AP]\.?M\.?", re.I)
UNSTATED = "Not stated on the agency's page; read the notice"


def content(page: str, url: str) -> list[dict]:
    """A page's own lines: after the site menu, which ends with the grants login, and before the address footer. The
    pages have no main element, and some no h1."""
    lines = _lines(page)
    start = next((i + 1 for i, x in enumerate(lines) if x["text"] == "GRANTS LOGIN"), None)
    end = next((i for i, x in enumerate(lines) if x["text"].startswith("Montana Arts Council |")), None)
    if start is None or end is None or end <= start:
        raise RuntimeError(f"A Montana page's menu or footer has changed ({url}); {CHANGED}")
    return lines[start:end]


def guideline_links(page: str) -> dict[str, str]:
    """The address of each education grant's HTML guidelines, from the Arts Education page."""
    found = {}
    for x in content(page, LIST):
        for name in EDUCATION:
            if re.match(rf"Arts Education {name}\b.*\bGuidelines \(HTML\)", x["text"]) and x["links"]:
                url = urljoin(LIST, x["links"][0][0].split("#")[0])
                if urlparse(url).netloc != urlparse(SITE).netloc or "/obsolete" in url:
                    raise RuntimeError(f"Montana's {name} guidelines link leads somewhere new ({url}); {CHANGED}")
                found[name] = url
    if len(found) != len(EDUCATION):
        raise RuntimeError(f"The Montana Arts Education page no longer links both HTML guidelines; {CHANGED}")
    return found


def _sentences(texts: list[str]) -> list[str]:
    return [s for t in texts for s in re.split(r"(?<=[.!?])\s+", t) if s]


def education(page: str, url: str, name: str, today: str) -> dict:
    """One education grant from its guidelines page: {"record": ..., "closed": the page's words, or ""}."""
    lines = _lines(page)
    # the application form follows the guidelines on the same page
    lines = lines[:next((i for i, x in enumerate(lines) if x["head"] == "h1" and x["text"].startswith("Project Name")),
                        len(lines))]
    texts = [x["text"] for x in lines]
    title = f"Arts Education {name}"
    # the next deadline listed that hasn't passed, with the project dates on the line before it
    found = [(webpages.day(m.group(1)), i) for i, t in enumerate(texts) if (m := DEADLINE.match(t))]
    found = [(d, i) for d, i in found if d]
    if not found:
        raise RuntimeError(f"Montana's {title} guidelines give no deadline; {CHANGED}")
    closes, at = min((f for f in found if f[0] >= today), default=max(found))
    span = texts[at - 1] if at and re.search(r"\b\d{4}\b", texts[at - 1]) and not DEADLINE.match(texts[at - 1]) else ""

    start = next((i for i, t in enumerate(texts) if re.match(r"All applicants must be one of the following", t, re.I)),
                 None)
    who = []
    for x in lines[start + 1:] if start is not None else []:
        if x["head"] or x["text"].rstrip(":") in ("Important", "Restrictions"):
            break
        who.append(x["text"])
    if not who:
        raise RuntimeError(f"Montana's {title} guidelines no longer list who may apply; {CHANGED}")
    kinds = []   # a sentence that runs on to the next line is one kind
    for t in who:
        if kinds and t[:1].islower():
            kinds[-1] = f"{kinds[-1]} {t}"
        else:
            kinds.append(t)
    sentences = _sentences(texts)
    years = [s for s in sentences if re.search(r"continuously operating in Montana|may not be awarded to individuals", s)]
    about = next((s for s in sentences if re.search(r"\bgrants are designed to\b", s, re.I)), "")
    award = next((s for s in sentences if re.search(r"\bGrant awards are between\b", s, re.I)), "")
    none = next((s for s in sentences if re.search(r"\bno match is required\b", s, re.I)), "")
    ratio = re.search(r"\brequire a (\d+:\d+) match\b", award)
    uei = next((s for s in sentences if re.search(r"\bUEI\b.*\bprior to\b", s)), "")
    other = next((s for s in sentences if re.search(r"\ba \d+:\d+ match\b.*\bis offered\b", s)), "")
    record = webpages.record(
        "MT", webpages.slug(title), title, AGENCY, url, LIST,
        "; ".join(k.rstrip(".;") for k in kinds) + ". " + " ".join(years),
        bool(NONPROFIT.search(" ".join(kinds))), closes=closes, objectives=about, award=award,
        match=ratio.group(1) if ratio else "", match_none=bool(none) and not ratio,
        restrictions=" ".join(t for t in (none, other, uei) if t),
        funding_method="Reimbursement" if re.search(r"\breimbursement-based\b", " ".join(texts)) else "",
        application=" ".join(t for t in (f"Grant deadline as the guidelines give it: {texts[at].rstrip('.')}.",
                                         f"Project timeframe: {span.rstrip('.')}." if span else "", APPLY_HOW) if t),
        today=today)
    return {"record": record, "closed": webpages.not_taking(texts, today)}


def health(page: str, today: str) -> dict:
    """Arts in Health, from the "Next opportunity" lines of its page."""
    lines = content(page, HEALTH)
    texts = [x["text"] for x in lines]
    at = next((i for i, x in enumerate(lines) if x["head"] and x["text"].lower() == "next opportunity"), None)
    if at is None:
        raise RuntimeError(f"No 'Next opportunity' on Montana's Arts in Health page; {CHANGED}")
    said = []
    for x in lines[at + 1:]:
        if x["head"]:
            break
        said.append(x["text"])
    words = " ".join(said)
    opens = re.search(r"\bwill open ([A-Z][a-z]+ \d{1,2}, \d{4})", words)
    closes = re.search(r"\bDeadline for application submissions\b[^.]*?\b([A-Z][a-z]+ \d{1,2}, \d{4})", words)
    closed = webpages.not_taking(texts, today, webpages.day(opens.group(1)) if opens else None) or webpages.doubt(
        [s for s in _sentences(said) if not re.search(r"\bwill (?:re)?open\b", s, re.I)], today)
    if not closes and not closed:
        raise RuntimeError(f"Montana's Arts in Health page no longer gives its deadline; {CHANGED}")
    record = webpages.record(
        "MT", "arts-in-health", "Arts in Health", AGENCY, HEALTH, LIST, UNSTATED, True,
        closes=webpages.day(closes.group(1)) if closes else None, opens=webpages.day(opens.group(1)) if opens else None,
        objectives=next((t for t in texts if t.startswith("Arts in Health projects require")), ""),
        application=" ".join([*said, APPLY_HOW]), today=today)
    return {"record": record, "closed": closed}


def investment(page: str, today: str) -> dict:
    """Strategic Investment Grants: monthly, so listed only on the page's own yes and nothing against it."""
    lines = content(page, INVESTMENT)
    texts = [x["text"] for x in lines]
    sentences = _sentences(texts)
    at = next((i for i, x in enumerate(lines) if x["head"] and x["text"].lower() == "application deadline"), None)
    if at is None:
        raise RuntimeError(f"No 'Application Deadline' on Montana's Strategic Investment Grants page; {CHANGED}")
    said = []
    for x in lines[at + 1:]:
        if x["head"]:
            break
        said += [s for s in _sentences([x["text"]]) if "@" not in s]
    who = [s for s in sentences if re.search(r"\bsupports nonprofit organizations\b|\bapplicants and 501\(c\)3\b", s)]
    about = next((s for s in sentences if re.search(r"\bprovide up to \$", s, re.I)), "")
    closed = webpages.not_taking(texts, today)
    if not closed and not (who and about):
        raise RuntimeError(f"Montana's Strategic Investment Grants page no longer says who or how much; {CHANGED}")
    monthly = [s for s in said if re.search(r"\b(?:each|every) month\b", s, re.I)]
    record = webpages.record(
        "MT", "strategic-investment-grants", "Strategic Investment Grants", AGENCY, INVESTMENT, LIST,
        " ".join(who) or UNSTATED, True, rolling=bool(monthly), deadline_words=" ".join(said), objectives=about,
        award=about, application=" ".join([*said, APPLY_HOW]), today=today)
    return {"record": record, "closed": closed, "rolling": monthly, "about": texts}


def read_rows(page, today: str | None = None) -> list[dict]:
    """One row per grant. `page(url, name)` gives a page; name is what a saved copy of it is called."""
    today = today or date.today().isoformat()
    links = guideline_links(page(LIST, "artsed"))
    rows = [education(page(links[name], name.lower()), links[name], name, today) for name in EDUCATION]
    return [*rows, health(page(HEALTH, "artsinhealth"), today), investment(page(INVESTMENT, "sig"), today)]


def build_records(rows: list[dict], today: str | None = None, skips: list[dict] | None = None) -> list[dict]:
    return webpages.keep_open("montana", rows, today, skips)


def build(out: Path, skipped_out: Path | None = None, saved: Path | None = None) -> int:
    def read_saved(url: str, name: str) -> str:
        return (saved / f"{name}.html").read_text(encoding="utf-8", errors="replace")

    def read_live(url: str, name: str) -> str:
        return (webpages.get if url == LIST else webpages.get_next)(url)

    rows = read_rows(read_saved if saved else read_live)
    skips: list[dict] = []
    records = build_records(rows, skips=skips)
    return webpages.write("MT", SOURCE, records, skips, out, skipped_out, "Montana Arts Council")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="data/montana.json.gz", type=Path)
    ap.add_argument("--skipped", type=Path)
    ap.add_argument("--dir", type=Path, help="a folder of saved copies of the pages, instead of fetching them")
    args = ap.parse_args()
    build(args.out, args.skipped, args.dir)


if __name__ == "__main__":
    main()
