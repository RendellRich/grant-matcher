"""Minnesota state grants from two agencies' own pages. This is partial coverage, not a statewide list.

- Department of Health: "Grants and Loans: Open Grant Opportunities" (health.state.mn.us/about/grants/), one
  entry per call with its title, a link to the program page, the intent and application deadlines and the
  eligible applicants.
- Department of Public Safety, Office of Justice Programs: "Funding opportunities" (dps.mn.gov), one section per
  call with its request for proposals, deadline, available money and eligible applicants. The host's robots.txt
  disallows PDF files, so the request for proposals is linked on the card and never fetched.

The statewide Find a Grant page (mn.gov) answers scripts with a bot check, so it isn't read. Both hosts'
robots.txt and policy pages were checked on 2026-11-25 (docs/state-coverage.md).

Who may apply is each agency's own list or sentence: one that names nonprofits, faith-based, community-based or
"... serving" organizations keeps the call open to nonprofits; one that names only others (individuals, schools,
public water suppliers) leaves nonprofits out, and so does one that limits the call to a kind of hospital, even
a nonprofit one; a blank one is kept with a note to read the notice. A call whose
deadline has passed is dropped, and so is one with no date unless it takes applications on a rolling basis.
Contacts on these pages are email addresses, so no contact is kept.

Records use the same fields as Ohio's (grantmatch/ohio.py), so the same scorer reads them.

Run:  python -m grantmatch.minnesota --out data/minnesota.json.gz [--skipped build/skipped-minnesota.json.gz]
      add --health <saved.html> --justice <saved.html> to read saved copies of both pages instead of fetching them
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

HEALTH = "https://www.health.state.mn.us/about/grants/index.html"
JUSTICE = "https://dps.mn.gov/divisions/ojp/ojp-grants/funding-opportunities"
HEALTH_AGENCY = "Minnesota Department of Health"
JUSTICE_AGENCY = "Minnesota Department of Public Safety, Office of Justice Programs"
MIN_ROWS = 5  # the Health page lists about a dozen calls; fewer than this means the page changed shape
WHO = "Not stated on the agency's page; read the notice"

session = requests.Session()
session.headers.update({"User-Agent": "grant-matcher (github.com/RendellRich/grant-matcher)"})

NONPROFIT = re.compile(r"non-?\s?profit|not[- ]for[- ]profit|\bis not for profit|501\s*\(?\s*c\s*\)?\s*\(?\s*3|"
                       r"faith-based|community[- ]based organi[sz]ation|-serving organi[sz]ation|"
                       r"serving organi[sz]ation|social service (?:organi[sz]ation|agenc)", re.I)
# "An eligible applicant for this grant program is a ... hospital ... that is not for profit": open to a kind of
# hospital, not to nonprofits generally.
HOSPITALS_ONLY = re.compile(r"\beligible applicants?\b[^.:;]{0,60}\bis an? [^.:;]{0,60}\bhospital\b", re.I)
INVITATION = re.compile(r"\bby invitation only\b|\binvitation[- ]only\b", re.I)
LOAN = re.compile(r"\bloans?\b(?!\s+(?:repayment|forgiveness))|\brevolving (?:loan )?funds?\b", re.I)
ROLLING = re.compile(r"\b(?:ongoing|rolling|year[- ]round|accepted any ?time)\b", re.I)
MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
DATE = re.compile(rf"\b({MONTHS})\s+(\d{{1,2}}),?\s+(\d{{4}})")
INTENT = re.compile(r"^(?:letter of )?intent to (?:apply )?(?:apply )?deadline\s*:?", re.I)
APPLY = re.compile(r"^application deadline\s*:?", re.I)
ELIGIBLE = re.compile(r"^eligible applicants?\s*:?", re.I)


def _clean(s: str | None) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("\xa0", " ").replace("​", "")).strip()


def _day(s: str) -> str | None:
    found = DATE.search(s or "")
    if not found:
        return None
    try:
        return datetime.strptime(" ".join(found.groups()), "%B %d %Y").date().isoformat()
    except ValueError:
        return None


class _Lines(HTMLParser):
    """A page fragment as lines of text, each with its links and the heading level it is, if any."""

    BLOCKS = ("p", "br", "div", "li", "ul", "ol", "h1", "h2", "h3", "h4", "tr", "table", "section")
    HIDDEN = ("script", "style", "noscript")

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lines: list[dict] = [{"text": "", "links": [], "head": "", "item": False}]
        self._head, self._item, self._hidden, self._link = "", 0, 0, None

    def _break(self):
        if self.lines[-1]["text"].strip() or self.lines[-1]["links"]:
            self.lines.append({"text": "", "links": [], "head": "", "item": False})
        self.lines[-1]["head"], self.lines[-1]["item"] = self._head, self._item > 0

    def handle_starttag(self, tag, attrs):
        if tag in self.HIDDEN:
            self._hidden += 1
        if tag in ("h1", "h2", "h3", "h4"):
            self._head = tag
        if tag == "li":
            self._item += 1
        if tag in self.BLOCKS:
            self._break()
        elif tag == "a":
            self._link = [dict(attrs).get("href") or "", ""]

    def handle_endtag(self, tag):
        if tag in self.HIDDEN and self._hidden:
            self._hidden -= 1
        if tag in ("h1", "h2", "h3", "h4"):
            self._head = ""
        if tag == "li" and self._item:
            self._item -= 1
        if tag in self.BLOCKS:
            self._break()
        elif tag == "a" and self._link is not None:
            if self._link[0]:
                self.lines[-1]["links"].append((self._link[0], _clean(self._link[1])))
            self._link = None

    def handle_data(self, data):
        if self._hidden:
            return
        self.lines[-1]["text"] += data
        if self._link is not None:
            self._link[1] += data


def _lines(fragment: str) -> list[dict]:
    p = _Lines()
    p.feed(fragment)
    p.close()
    return [{**x, "text": _clean(x["text"])} for x in p.lines if _clean(x["text"])]


def parse_health(page: str) -> list[dict]:
    """One row per call on the Health page. An entry starts at the line above its intent deadline."""
    start = page.find("Open Opportunities")
    if start < 0:
        return []
    end = page.find("field--name-field-tags", start)
    end = end if end > 0 else page.find("</main>", start)
    fragment = page[start:end if end > 0 else len(page)]
    lines = _lines(fragment[:fragment.rfind("<")] if end > 0 else fragment)
    starts = [i - 1 for i, x in enumerate(lines) if i and INTENT.match(x["text"])]
    blocks = [lines[at:end] for at, end in zip(starts, [*starts[1:], len(lines)])]
    # An entry is found by its intent deadline line. One without it would be read as part of the entry above (taking
    # over its deadline and eligibility) or, at the top, not read at all, so either one stops the run.
    above = lines[:starts[0]] if starts else lines
    for allowed, block in [(0, above), *((1, b) for b in blocks)]:
        for label in (APPLY, ELIGIBLE):
            if sum(bool(label.match(x["text"])) for x in block) > allowed:
                raise RuntimeError("An entry on the Minnesota Health page has no intent deadline line, so it can't be "
                                   "told apart from its neighbor; keeping the previous data file")
    out = []
    for block in blocks:
        links = block[0]["links"]
        row = {"agency": "health", "title": block[0]["text"], "url": urljoin(HEALTH, links[0][0].split("#")[0]) if links else HEALTH,
               "intent": "", "intent_letter": False, "deadline": "", "window": "", "eligible": ""}
        part, window, who = "", [], []
        for x in block[1:]:
            text = x["text"]
            if INTENT.match(text):
                row["intent"] = _clean(INTENT.sub("", text))
                row["intent_letter"] = text.lower().startswith("letter")
                part = "intent"
            elif APPLY.match(text):
                row["deadline"] = _clean(APPLY.sub("", text))
                part = "apply"
            elif ELIGIBLE.match(text):
                who.append(_clean(ELIGIBLE.sub("", text)))
                part = "who"
            elif part == "apply":
                window.append(text)
            elif part == "who":
                # list items are joined with semicolons, unless the item already ends its own way ("beds, and")
                who.append(f"{text};" if x["item"] and not re.search(r"(?:[;.:,]|\band|\bor)$", text) else text)
        row["window"] = " ".join(window)
        row["eligible"] = " ".join(t for t in who if t).rstrip("; ")
        out.append(row)
    return out


def parse_justice(page: str) -> list[dict]:
    """One row per call on the Office of Justice Programs page: a second-level heading with its own panels."""
    start = page.find("<main")
    end = page.find("</main>", start)
    if start < 0:
        return []
    sections: list[dict] = []
    for x in _lines(page[start:end if end > 0 else len(page)]):
        if x["head"] == "h2":
            sections.append({"title": x["text"], "panel": "", "panels": {}, "links": []})
        elif sections and x["head"] == "h3":
            sections[-1]["panel"] = x["text"].lower()
            sections[-1]["panels"].setdefault(x["text"].lower(), [])
        elif sections and sections[-1]["panel"]:
            sections[-1]["panels"][sections[-1]["panel"]].append(x["text"])
            sections[-1]["links"] += x["links"]
    out = []
    for s in sections:
        def panel(word: str) -> list[str]:
            return [t for name, texts in s["panels"].items() if word in name for t in texts]
        proposals, who = panel("request for proposal"), panel("eligible applicant")
        if not proposals and not who:
            continue  # "Related laws" and other headings that aren't calls
        due = ""
        for t in [t for texts in s["panels"].values() for t in texts]:
            if re.search(r"\b(?:applications?|proposals?)\b[^\n]{0,40}\bdue\b", t, re.I) and DATE.search(t):
                due = t
                break
        rfp = next((urljoin(JUSTICE, href) for href, text in s["links"] if re.search(r"\bRFP\b|request for proposal", text, re.I)
                    and href.split("?")[0].lower().endswith((".pdf", ".docx"))), "")
        out.append({"agency": "justice", "title": s["title"], "url": JUSTICE, "intent": "", "intent_letter": False,
                    "deadline": due, "window": "", "eligible": " ".join(who),
                    "purpose": " ".join(t for t in proposals if t != due and not t.lower().startswith("read the rfp")),
                    "award": " ".join(panel("available funding")), "conditions": " ".join(panel("project date")), "rfp": rfp})
    if not out and not re.search(r"no (?:current|open) (?:funding )?opportunit", page, re.I):
        raise RuntimeError("No funding call could be read from the Office of Justice Programs page; keeping the previous data file")
    return out


def _slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def _key(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:6]


def normalize(row: dict, today: str | None = None) -> dict:
    today = today or date.today().isoformat()
    health = row["agency"] == "health"
    title = without_email(_clean(row["title"]))  # before the key is made from it
    closes = _day(row["deadline"])
    rolling = not closes and bool(ROLLING.search(f"{row['deadline']} {row['window']}"))
    who = _clean(row["eligible"])
    nonprofit = bool(NONPROFIT.search(who)) and not HOSPITALS_ONLY.search(who) if who else True
    intent = _day(row["intent"])
    notes = []
    if intent:
        label = "Letter of intent" if row["intent_letter"] else "Intent to apply"
        passed = " That date has passed; check the notice before you start." if intent < today else ""
        notes.append(f"{label} deadline: {_clean(row['intent'])}.{passed}")
    if rolling and row["window"]:
        notes.append(_clean(row["window"]))
    if health:
        notes.append("Read the request for proposals on the program's page and apply as it says.")
    else:
        notes += [_clean(row["deadline"]), f"Request for proposals: {row['rfp']}" if row.get("rfp") else
                  "Read the request for proposals on the agency's page."]
    loan = bool(LOAN.search(title))
    rec = {
        # The link's hash is always part of the key, so two calls with one title stay apart and neither's key
        # changes when the other expires, moves or leaves the page.
        "id": f"mn-{'health' if health else 'justice'}-{_slug(title)}-{_key(row['url'])}",
        "csfa": "",
        "number": "",
        "state": "MN",
        "title": title,
        "agency": HEALTH_AGENCY if health else JUSTICE_AGENCY,
        "objectives": _clean(row.get("purpose"))[:3000],
        "assistance": "Loan" if loan else "Grant",
        "applicant_types": who[:1200] or WHO,
        "nonprofit_eligible": nonprofit,
        "earmark": False,
        "restrictions": _clean(row.get("conditions"))[:1200],
        "application": " ".join(t for t in notes if t)[:1200],
        "award": _clean(row.get("award"))[:800],
        "deadlines": closes or ("Ongoing" if rolling else _clean(row["deadline"])),
        "contact": "",
        "web": HEALTH if health else JUSTICE,
        "subjects": "",
        "fiscal_year": "",
        "url": row["url"],
        "status": "active",
        "opens": None,
        "closes": closes,
        "match": "",
        "loan": loan,
        "funding_method": "",
        "loi": bool(intent),
        "updated": None,
    }
    return {k: without_email(v) if isinstance(v, str) else v for k, v in rec.items()}


def build_records(items: list[dict], today: str | None = None, skips: list[dict] | None = None) -> list[dict]:
    """Open calls, one per entry. Rows dropped are added to skips, when given."""
    today = today or date.today().isoformat()
    out: dict[str, dict] = {}
    for row in items:
        try:
            rec = normalize(row, today)
        except Exception as exc:  # one odd row shouldn't sink the refresh
            print(f"skip a row: {exc}", file=sys.stderr)
            continue
        base = {"source": "minnesota", "id": rec["id"], "name": rec["title"] or "(no title)", "state": "MN",
                "funder": rec["agency"], "url": rec["url"]}
        reason = detail = ""
        if not rec["title"]:
            reason, detail = "no_title", "The agency's entry has no title"
        elif rec["closes"] and rec["closes"] < today:
            reason, detail = "deadline_passed", f"Listed, but its deadline was {rec['closes']}"
        elif not rec["closes"] and rec["deadlines"] != "Ongoing":
            reason, detail = "no_deadline", f"No date and not rolling (it says: {rec['deadlines'][:80] or 'nothing'})"
        elif INVITATION.search(f"{rec['title']} {rec['applicant_types']}"):
            reason, detail = "invitation_only", "The listing says: by invitation only"
        elif rec["id"] in out:
            reason, detail = "duplicate", "The same title and link are listed twice"
        if reason:
            if skips is not None:
                skips.append({**base, "reason": reason, "detail": detail})
            continue
        out[rec["id"]] = rec
    return sorted(out.values(), key=lambda r: r["id"])


def read_rows(health: str, justice: str) -> list[dict]:
    """Both pages' entries, or an error when either page no longer reads."""
    found = parse_health(health)
    if len(found) < MIN_ROWS:
        raise RuntimeError(f"Only {len(found)} calls on the Minnesota Health page; keeping the previous data file")
    return found + parse_justice(justice)


def fetch_page(url: str) -> str:
    r = session.get(url, timeout=60)
    r.raise_for_status()
    return r.content.decode("utf-8", errors="replace")


def build(out: Path, skipped_out: Path | None = None, saved: tuple[Path, Path] | None = None) -> int:
    pages = ([p.read_text(encoding="utf-8", errors="replace") for p in saved] if saved
             else [fetch_page(HEALTH), fetch_page(JUSTICE)])
    skips: list[dict] = []
    records = build_records(read_rows(*pages), skips=skips)
    payload = {
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "source": "Minnesota Department of Health and Office of Justice Programs grant pages (two agencies only)",
        "state": "MN", "count": len(records), "programs": records,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(out, "wt", encoding="utf-8") as fh:
        json.dump(payload, fh, separators=(",", ":"))
    print(f"wrote {len(records)} open Minnesota calls to {out}; {sum(r['nonprofit_eligible'] for r in records)} open to nonprofits")
    if skipped_out is not None:
        from .fetch import write_skips
        write_skips(skipped_out, skips)
    return len(records)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="data/minnesota.json.gz", type=Path)
    ap.add_argument("--skipped", type=Path)
    ap.add_argument("--health", type=Path, help="a saved copy of the Health page, instead of fetching it")
    ap.add_argument("--justice", type=Path, help="a saved copy of the Justice Programs page, instead of fetching it")
    args = ap.parse_args()
    if bool(args.health) != bool(args.justice):
        ap.error("--health and --justice go together")
    build(args.out, args.skipped, (args.health, args.justice) if args.health else None)


if __name__ == "__main__":
    main()
