"""Kentucky grants from the Kentucky Arts Council's grant pages. This is partial coverage, not a statewide list.

Only https://artscouncil.ky.gov/grants/ and the program pages it links under /grants/ may be read (Ren's decision,
2026-11-27): cycles.ONLY_UNDER keeps every job off the rest of the host, a redirect included. Each page is asked for
once a run, 10 seconds apart
(the site's robots.txt asks that). On 2026-11-27 the site's Terms of Service, Privacy Policy and Cookies Policy links
all answered 404; if they come back they are to be read before the next run's data is used (docs/state-coverage.md).

A program is kept when its page's "Application Deadline" is ahead, it doesn't say closed, and who may apply takes in
a nonprofit (schools alone don't count). A run stops, keeping the previous data file, when a page loses that part.

Records use the same fields as Ohio's (grantmatch/ohio.py), so the same scorer reads them.

Run:  python -m grantmatch.kentucky --out data/kentucky.json.gz [--skipped build/skipped-kentucky.json.gz]
      add --dir <folder> to read saved copies (grants.html and one <last part of its address>.html per program page)
"""
from __future__ import annotations

import argparse
import re
import time
from datetime import date
from pathlib import Path

from . import webpages
from .minnesota import _lines

LIST = "https://artscouncil.ky.gov/grants/"
PAUSE = 10  # artscouncil.ky.gov's robots.txt: Crawl-delay: 10
AGENCY = "Kentucky Arts Council"
SOURCE = "Kentucky Arts Council grant pages (artscouncil.ky.gov/grants), one agency only"
CHANGED = "keeping the previous data file"
APPLY_HOW = "Apply in the Council's GO Smart online system; read the guidelines first."
WHO = re.compile(r"^(?:Eligibility|Who May (?:Apply|Register))$", re.I)
# the line that starts the part after who may apply; the pages mark these as plain text, not headings
AFTER_WHO = re.compile(r"^(?:[A-Z]\. )?(?:Restrictions|Eligible Revenue|What We Fund|Proof of Eligibility|"
                       r"Program Description|Scoring Criteria|Program Coordination)\b", re.I)


def program_links(page: str) -> list[str]:
    links = list(dict.fromkeys(re.findall(r'href="(https://artscouncil\.ky\.gov/grants/[a-z0-9-]+/)"', page)))
    links = [u for u in links if not u.endswith("/grants/feed/")]
    if not links or "/grants/page/" in page:   # a second page of programs would be missed
        raise RuntimeError(f"The Kentucky Arts Council's grant list has changed; {CHANGED}")
    return links


def program(page: str, url: str, today: str) -> dict:
    """One program from its own page: {"record": ..., "closed": the page's words, or ""}."""
    lines = _lines(page[page.find("<main"):page.find("</main>")])
    texts = [x["text"] for x in lines]
    title = next((x["text"] for x in lines if x["head"] == "h1"), "")
    due = next((t for t in texts if t.startswith("Application Deadline:")), "")
    closes = webpages.day(due)
    if not title or not closes:
        raise RuntimeError(f"No title or 'Application Deadline' on {url}; {CHANGED}")
    closed = due if re.search(r"\bcurrently closed\b|\bApplication Closed\b", due, re.I) else \
        webpages.not_taking(texts, today)
    at = next((i for i, t in enumerate(texts) if WHO.match(t)), None)
    who = []
    for x in lines[at + 1:] if at is not None else []:
        if x["head"] or AFTER_WHO.match(x["text"]):
            break
        who.append(x["text"])
    if not who and not closed and closes >= today:
        raise RuntimeError(f"No eligibility on {url}; {CHANGED}")
    who = " ".join(who)
    about = next((texts[i + 1] for i, t in enumerate(texts[:-1]) if t == "About the Program"), "")
    tiers = [t for t in texts if re.match(r"Tier \d", t)]
    award = "; ".join(tiers) or next((s for s in re.split(r"(?<=[.!?])\s+", about) if "$" in s), "")
    words = re.sub(r"\s*(?:Apply Here|Apply Now!|Register Here)$", "", due).rstrip(".")
    record = webpages.record(
        "KY", webpages.slug(title), title, AGENCY, url, LIST, who, webpages.open_to_nonprofits(who), closes=closes,
        objectives=about, award=award, application=f"{words}. {APPLY_HOW}", today=today)
    return {"record": record, "closed": closed}


def read_rows(page, today: str | None = None) -> list[dict]:
    """One row per program. `page(url, name)` gives a page; name is what a saved copy of it is called."""
    today = today or date.today().isoformat()
    return [program(page(url, url.rstrip("/").rsplit("/", 1)[-1]), url, today)
            for url in program_links(page(LIST, "grants"))]


def build_records(rows: list[dict], today: str | None = None, skips: list[dict] | None = None) -> list[dict]:
    return webpages.keep_open("kentucky", rows, today, skips, nonprofits_only=True)


def build(out: Path, skipped_out: Path | None = None, saved: Path | None = None) -> int:
    def read_saved(url: str, name: str) -> str:
        return (saved / f"{name}.html").read_text(encoding="utf-8", errors="replace")

    def read_live(url: str, name: str) -> str:
        if url != LIST:
            time.sleep(PAUSE)
        return webpages.get(url)

    rows = read_rows(read_saved if saved else read_live)
    skips: list[dict] = []
    records = build_records(rows, skips=skips)
    return webpages.write("KY", SOURCE, records, skips, out, skipped_out, "Kentucky Arts Council")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="data/kentucky.json.gz", type=Path)
    ap.add_argument("--skipped", type=Path)
    ap.add_argument("--dir", type=Path, help="a folder of saved copies of the pages, instead of fetching them")
    args = ap.parse_args()
    build(args.out, args.skipped, args.dir)


if __name__ == "__main__":
    main()
