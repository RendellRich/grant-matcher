"""Arkansas grants from the Arkansas Arts Council's own page. This is partial coverage, not a statewide list.

arkansasheritage.com/funding/art-grants is one hand-written page: a "When To Apply" list of dates, then a section for
each program. The three programs read are General Operating Support (year one), the Arts in Education major grants and
Arts on Tour, which the page says takes applications on an ongoing basis. The Community Arts Project grant is listed as
left out while the page says it is closed. Mini grants (closed on the "When To Apply" list), the artist grants and
Major Arts Partners (no date of its own) aren't read.

Because the page is prose, the run stops, keeping the previous data file, when the "When To Apply" list holds a line
this doesn't understand, or when a program's section or date is gone: a person then reads the page and updates this.
robots.txt (none, 404) and the privacy policy were checked on 2026-11-26 (docs/state-coverage.md).

Records use the same fields as Ohio's (grantmatch/ohio.py), so the same scorer reads them.

Run:  python -m grantmatch.arkansas --out data/arkansas.json.gz [--skipped build/skipped-arkansas.json.gz]
      add --file <saved.html> to read a saved copy of the page instead of fetching it
"""
from __future__ import annotations

import argparse
import re
from datetime import date
from pathlib import Path

from . import webpages
from .minnesota import NONPROFIT, _lines

LIST = "https://www.arkansasheritage.com/funding/art-grants"
AGENCY = "Arkansas Arts Council"
SOURCE = "Arkansas Arts Council art grants page (arkansasheritage.com), one agency only"
APPLY_HOW = "Apply in the Arts Council's grants portal from the page; it says to talk with the program manager first."

# Every line the "When To Apply" list may hold, by what it is.
WHEN = {
    "gos_opens": re.compile(r"^All General Operating Support grants open\b", re.I),
    "gos_intent": re.compile(r"^General Operating Support FY\d+ Letter of Intent Applications are due\b", re.I),
    "gos_one": re.compile(r"^General Operating Support FY\d+ Year One application is due\b", re.I),
    "gos_later": re.compile(r"^General Operating Support FY\d+ Years Two and Three application is due\b", re.I),
    "aie": re.compile(r"^All Arts in Education Major grants open\b.*\bApplications are due\b", re.I),
    "mini": re.compile(r"^Mini grants are closed\b", re.I),
}
HEADINGS = ("ARTS ON TOUR GRANT", "GENERAL OPERATING SUPPORT", "AIE ARTS CURRICULUM PROJECT")
PROJECT = "COMMUNITY ARTS PROJECT"
CHANGED = "keeping the previous data file"


def _when(lines: list[dict]) -> dict[str, str]:
    start = next((i for i, x in enumerate(lines) if x["head"] and x["text"].lower() == "when to apply"), None)
    if start is None:
        raise RuntimeError(f"No 'When To Apply' list on the Arkansas Arts Council page; {CHANGED}")
    found: dict[str, str] = {}
    for x in lines[start + 1:]:
        if x["head"]:
            break
        kind = next((k for k, pattern in WHEN.items() if pattern.search(x["text"])), None)
        if kind is None or kind in found:
            raise RuntimeError(f"The Arkansas 'When To Apply' list has a line this can't read ({x['text'][:80]}); {CHANGED}")
        found[kind] = x["text"]
    for kind in ("gos_one", "aie"):
        if not webpages.day(found.get(kind)):
            raise RuntimeError(f"A date is missing from the Arkansas 'When To Apply' list; {CHANGED}")
    return found


def _is_program(text: str) -> bool:
    """A program's name as the page writes it: two words or more, all capitals, notes in brackets aside."""
    bare = re.sub(r"\([^)]*\)", "", text).strip()
    return (len(bare.split()) >= 2 and bare == bare.upper() and any(c.isalpha() for c in bare)
            and bare not in ("APPLY NOW", "APPLY HERE"))


def _section(lines: list[dict], heading: str) -> list[str]:
    """The lines under a program's name, up to its apply button."""
    start = next((i for i, x in enumerate(lines) if x["text"] == heading), None)
    if start is None:
        raise RuntimeError(f"No '{heading}' section on the Arkansas Arts Council page; {CHANGED}")
    out = []
    for x in lines[start + 1:]:
        if x["text"].upper() in ("APPLY NOW", "APPLY HERE"):
            return out
        if _is_program(x["text"]):
            break   # the next program started first: this one's apply button is gone, so where it ends isn't known
        out.append(x["text"])
    raise RuntimeError(f"The '{heading}' section on the Arkansas page has no end; {CHANGED}")


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", webpages.clean(text)) if s]


def _first(sentences: list[str], pattern: str) -> str:
    return next((s for s in sentences if re.search(pattern, s, re.I)), "")


def parse(page: str, today: str | None = None) -> list[dict]:
    """One row per program: {"record": ..., "closed": the page's words, or ""}."""
    today = today or date.today().isoformat()
    lines = _lines(page)
    when = _when(lines)
    tour, operating, curriculum = (_sentences(" ".join(_section(lines, h))) for h in HEADINGS)

    def row(key, title, sentences, who, **fields):
        if not who:
            raise RuntimeError(f"No eligibility sentence for {title} on the Arkansas page; {CHANGED}")
        record = webpages.record("AR", key, title, AGENCY, LIST, LIST, who, bool(NONPROFIT.search(who)), today=today,
                                 **fields)
        return {"record": record, "closed": webpages.not_taking(sentences, today)}

    deadline = next((s for s in tour if s.lower().startswith("application deadline")), "")
    rolling = bool(re.search(r"\bongoing\b", deadline, re.I))
    if not rolling and not webpages.not_taking(tour, today):
        raise RuntimeError(f"Arts on Tour no longer says its deadline is ongoing; {CHANGED}")
    out = [row("arts-on-tour", "Arts on Tour grant", tour, _first(tour, r"\bcan apply\b"),
               rolling=rolling, deadline_words=deadline, objectives=" ".join(tour[:2]),
               award=_first(tour, r"\bpercent\b|\$\d"),
               funding_method="Reimbursement" if _first(tour, r"\breimburses\b") else "",
               application=f"{deadline} {APPLY_HOW}")]

    match = _first(operating, r"\bmatching funds\b")
    dates = [when[k] for k in ("gos_opens", "gos_intent", "gos_one", "gos_later") if k in when]
    # Said first, since both can rule an applicant out: the earlier intent date (as minnesota.py puts it) and the
    # income floor.
    said = re.search(r"\bare due (.+)$", when.get("gos_intent", ""))
    intent = f"Letter of intent deadline: {said.group(1).rstrip('.')}." if said else ""
    if intent and (webpages.day(said.group(1)) or today) < today:
        intent += " That date has passed; check the notice before you start."
    who = sorted((s for s in operating if re.search(r"\bestablished nonprofit\b|\bprogram is for\b", s, re.I)),
                 key=lambda s: "$" not in s)
    out.append(row("general-operating-support", "General Operating Support (year one)", operating, " ".join(who),
                   closes=webpages.day(when["gos_one"]), objectives=" ".join(operating[:1]),
                   match="Required" if re.search(r"\brequires\b", match, re.I) else "",
                   restrictions=" ".join(t for t in (_first(operating, r"\bmay only be spent\b"), match) if t),
                   award=_first(operating, r"\brequested amount\b"), loi="gos_intent" in when,
                   application=" ".join(t for t in [intent, *dates, APPLY_HOW] if t)))

    matched = _first(curriculum, r"\b1:1 match\b")
    out.append(row("arts-in-education-major", "Arts in Education major grants", curriculum,
                   _first(curriculum, r"\bare awarded to\b"), closes=webpages.day(when["aie"]),
                   objectives=" ".join(curriculum[:2]),
                   match=("1:1, half may be in-kind" if "50% in-kind" in matched else "1:1") if matched else "",
                   award=matched or _first(curriculum, r"\bup to \$"),
                   application=f"{when['aie']} {APPLY_HOW}"))

    if any(x["text"] == PROJECT for x in lines):
        project = _sentences(" ".join(_section(lines, PROJECT)))
        closed = webpages.not_taking(project, today)
        if not closed:
            raise RuntimeError(f"The Community Arts Project grant no longer says it is closed; {CHANGED}")
        record = webpages.record("AR", "community-arts-project", "Community Arts Project grant", AGENCY, LIST, LIST,
                                 "Not stated on the agency's page; read the notice", True, today=today)
        out.append({"record": record, "closed": closed})
    return out


def build_records(rows: list[dict], today: str | None = None, skips: list[dict] | None = None) -> list[dict]:
    return webpages.keep_open("arkansas", rows, today, skips)


def build(out: Path, skipped_out: Path | None = None, saved: Path | None = None) -> int:
    page = saved.read_text(encoding="utf-8", errors="replace") if saved else webpages.get(LIST)
    skips: list[dict] = []
    records = build_records(parse(page), skips=skips)
    return webpages.write("AR", SOURCE, records, skips, out, skipped_out, "Arkansas Arts Council")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="data/arkansas.json.gz", type=Path)
    ap.add_argument("--skipped", type=Path)
    ap.add_argument("--file", type=Path, help="a saved copy of the page, instead of fetching it")
    args = ap.parse_args()
    build(args.out, args.skipped, args.file)


if __name__ == "__main__":
    main()
