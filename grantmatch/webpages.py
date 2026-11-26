"""What the adapters for states read from web pages share (arkansas.py, maryland.py, northdakota.py, tennessee.py,
wyoming.py).

Every page is asked for with cycles.fetch_page: the project's own user agent, and the terms blocklist and the host's
robots.txt checked before each address, redirects included. A page that can't be read stops the run, so the last
data file is kept.

Records use the same fields as Ohio's (grantmatch/ohio.py), so the same scorer reads them. Nothing a page doesn't
say is filled in: a silent match stays blank ("Match not stated" on the card), and a call is kept without a date only
when its own page says it takes applications any time.
"""
from __future__ import annotations

import gzip
import json
import re
import time
from datetime import date, datetime, timezone
from pathlib import Path

from .cycles import DATE, fetch_page
from .display import without_email
from .minnesota import NONPROFIT

PAUSE = 2  # seconds between requests to one site; none of these hosts' robots.txt asks for more

# A page's own words that it isn't taking applications. STOPPED holds whatever the dates say. CLOSED does too, except
# when it is only the wait before a window the page also gives, or is about an earlier fiscal year (not_taking below).
STOPPED = re.compile(
    r"\btemporarily (?:paused|closed|suspended)\b|\bpaused applications\b|\bon hold\b"
    r"|\b(?:is|are|has been|have been) (?:currently |temporarily )?paused\b"
    r"|\bno longer (?:accepting|accepts?) (?:new |grant )?(?:applications|proposals)\b"
    r"|\b(?:grants?|program|applications?|round|cycle|funding)(?: \w+){0,4}? (?:is|are|has been|have been) "
    r"(?:currently )?suspended\b", re.I)
CLOSED = re.compile(
    r"\b(?:applications?|application (?:period|window|portal)(?: for [\w ]{0,40}?)?"
    r"|grants?(?: (?:cycle|round|portal|program|application|opportunity))?|program|round|cycle|portal|submissions?)"
    r" (?:is|are) (?:now |currently )?closed\b(?! out\b)"
    r"|\bclosed (?:for|to) (?:new )?(?:applications|applicants|this cycle|requests|proposals)\b"
    r"|\bnot (?:currently )?accepting (?:new )?applications\b"
    r"|\bapplications are not (?:currently )?(?:being )?accepted\b", re.I)
FISCAL_YEAR = re.compile(r"\b(?:Fiscal Year |FY ?)(\d{4}|\d{2})\b", re.I)
WILL_OPEN = re.compile(r"\bwill (?:re)?open (?:in |on )?(January|February|March|April|May|June|July|August|September|"
                       r"October|November|December)(?: \d{1,2},?)? (\d{4})", re.I)
# Words that say organizations, or nonprofits, may not apply: taken out before looking for who may.
ORGANIZATION = r"(?:(?:non-?\s?profit|not[- ]for[- ]profit)(?: arts?)?(?: organi[sz]ations?)?s?|organi[sz]ations?)"
NOT_ORGANIZATIONS = re.compile(
    rf"\b{ORGANIZATION}\s+(?:(?:are|is) (?:not eligible|ineligible)|(?:are|is) not (?:able|permitted|allowed) to apply"
    rf"|(?:cannot|can not|may not) apply)"
    rf"|\bnot (?:open|available) to [^.;,]*?\b{ORGANIZATION}\b"
    rf"|\b(?:not|no)\s+(?:to |for |by )?(?:an? )?{ORGANIZATION}\b"
    r"|(?<!not-)(?<!not )\bfor[- ]profit(?: organi[sz]ations?| businesses)?", re.I)
ORGANIZATIONS = re.compile(r"\borgani[sz]ations?\b", re.I)
INVITATION = re.compile(r"\bby invitation only\b|\binvitation[- ]only\b", re.I)
LOAN = re.compile(r"\bloans?\b(?!\s+(?:repayment|forgiveness))|\brevolving (?:loan )?funds?\b", re.I)


def clean(s: str | None) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("\xa0", " ").replace("​", "").replace("﻿", "")).strip()


def open_to_nonprofits(who: str) -> bool:
    """Whether the page's words on who may apply leave a nonprofit in: nonprofits or organizations named, other than
    to say they can't apply. Blank words are kept (the card says to read the notice)."""
    if not who:
        return True
    rest = NOT_ORGANIZATIONS.sub(" ", who)
    return bool(NONPROFIT.search(rest) or ORGANIZATIONS.search(rest))


def _only_waiting(sentence: str, text: str, today: str, opens: str | None) -> bool:
    """A "closed" sentence that doesn't close the call shown: about an earlier fiscal year, or the wait before the
    window the page gives."""
    current = int(today[:4]) + (1 if int(today[5:7]) >= 7 else 0)   # a state fiscal year starts in July
    years = [int(y) if len(y) == 4 else 2000 + int(y) for y in FISCAL_YEAR.findall(sentence)]
    if years and all(y < current for y in years):
        return True
    if opens and opens > today:
        return True
    said = WILL_OPEN.search(text)
    return bool(opens and said and day(f"{said.group(1)} 1, {said.group(2)}")[:7] == opens[:7])


def not_taking(texts: list[str], today: str | None = None, opens: str | None = None) -> str:
    """The sentence that says the call isn't being taken, or "". `opens` is the date the page says the window opens."""
    today = today or date.today().isoformat()
    for text in texts:
        text = clean(text)
        for sentence in re.split(r"(?<=[.!?])\s+", text):
            if STOPPED.search(sentence) or (CLOSED.search(sentence) and not _only_waiting(sentence, text, today, opens)):
                return sentence
    return ""


def get(url: str) -> str:
    """The page's HTML. Raises when it is off limits (cycles.OffLimits) or doesn't answer 200."""
    r = fetch_page(url, timeout=(10, 60))
    r.raise_for_status()
    return r.content.decode("utf-8", errors="replace")


def get_next(url: str) -> str:
    """get(), after a pause: for the second and later pages of one site."""
    time.sleep(PAUSE)
    return get(url)


def day(text: str | None) -> str | None:
    """The date a deadline line means: "Dec. 3, 2026", "March 26, 2027" or "12/09/26". With more than one, the date
    after "due", "closes" or the like, else the end of a range ("11/01/26 - 12/15/26"), else the first."""
    text = clean(text)
    found = []
    for m in re.finditer(rf"{DATE.pattern}|\b(?P<sm>\d{{1,2}})/(?P<sd>\d{{1,2}})/(?P<sy>\d{{2}})\b", text, re.I):
        if m.group("mon"):
            parts, fmt = f"{m.group('mon')[:3]} {m.group('day')} {m.group('year')}", "%b %d %Y"
        elif m.group("m"):
            parts, fmt = f"{m.group('m')}/{m.group('d')}/{m.group('y')}", "%m/%d/%Y"
        else:
            parts, fmt = f"{m.group('sm')}/{m.group('sd')}/{m.group('sy')}", "%m/%d/%y"
        try:
            found.append((m.start(), m.end(), datetime.strptime(parts, fmt).date().isoformat()))
        except ValueError:
            pass
    if not found:
        return None
    if len(found) > 1:
        said = re.search(r"\b(?:due|deadline|closes?|until|through|by)\b", text, re.I)
        after = [d for start, _, d in found if said and start >= said.end()]
        if after:
            return after[0]
        if re.fullmatch(r"\s*(?:-|\u2013|\u2014|to|through)\s*", text[found[0][1]:found[1][0]]):
            return found[1][2]
    return found[0][2]


def slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def record(state: str, key: str, title: str, agency: str, url: str, web: str, applicant_types: str,
           nonprofit_eligible: bool, *, closes: str | None = None, opens: str | None = None, rolling: bool = False,
           deadline_words: str = "", objectives: str = "", award: str = "", match: str = "", restrictions: str = "",
           application: str = "", funding_method: str = "", loi: bool = False, match_none: bool = False,
           today: str | None = None) -> dict:
    today = today or date.today().isoformat()
    title = without_email(clean(title))
    loan = bool(LOAN.search(title))
    rec = {
        "id": f"{state.lower()}-{key}",
        "csfa": "",
        "number": "",
        "state": state,
        "title": title,
        "agency": agency,
        "objectives": clean(objectives)[:3000],
        "assistance": "Loan" if loan else "Grant",
        "applicant_types": clean(applicant_types)[:1200],
        "nonprofit_eligible": nonprofit_eligible,
        "earmark": False,
        "restrictions": clean(restrictions)[:1200],
        "application": clean(application)[:1200],
        "award": clean(award)[:800],
        "deadlines": closes or ("Ongoing" if rolling else clean(deadline_words)),
        "contact": "",
        "web": web,
        "subjects": "",
        "fiscal_year": "",
        "url": url,
        "status": "forecasted" if opens and opens > today else "active",
        "opens": opens,
        "closes": closes,
        "match": match,
        "loan": loan,
        "funding_method": funding_method,
        "loi": loi,
        "updated": None,
        # only when the page says none is needed, as the lists with a match field do
        **({"match_none": True} if match_none else {}),
    }
    return {k: without_email(v) if isinstance(v, str) else v for k, v in rec.items()}


def keep_open(source: str, rows: list[dict], today: str | None = None, skips: list[dict] | None = None) -> list[dict]:
    """The open calls among `rows`, each {"record": ..., "closed": the page's words, when it says it isn't taking
    applications}. Rows dropped are added to skips, when given."""
    today = today or date.today().isoformat()
    out: dict[str, dict] = {}
    for row in rows:
        rec = row["record"]
        base = {"source": source, "id": rec["id"], "name": rec["title"] or "(no title)", "state": rec["state"],
                "funder": rec["agency"], "url": rec["url"]}
        reason = detail = ""
        if not rec["title"]:
            reason, detail = "no_title", "The page's entry has no title"
        elif row.get("closed"):
            reason, detail = "not_taking", f"The page says: {clean(row['closed'])[:200]}"
        elif rec["closes"] and rec["closes"] < today:
            reason, detail = "deadline_passed", f"Listed, but its deadline was {rec['closes']}"
        elif not rec["closes"] and rec["deadlines"] != "Ongoing":
            reason, detail = "no_deadline", f"No date and not rolling (it says: {rec['deadlines'][:80] or 'nothing'})"
        elif INVITATION.search(f"{rec['title']} {rec['applicant_types']}"):
            reason, detail = "invitation_only", "The listing says: by invitation only"
        elif rec["id"] in out:
            reason, detail = "duplicate", "The same title is listed twice"
        if reason:
            if skips is not None:
                skips.append({**base, "reason": reason, "detail": detail})
            continue
        out[rec["id"]] = rec
    return sorted(out.values(), key=lambda r: r["id"])


def write(state: str, source: str, records: list[dict], skips: list[dict], out: Path,
          skipped_out: Path | None, label: str) -> int:
    payload = {"fetched_at": datetime.now(timezone.utc).isoformat(timespec="minutes"), "source": source,
               "state": state, "count": len(records), "programs": records}
    out.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(out, "wt", encoding="utf-8") as fh:
        json.dump(payload, fh, separators=(",", ":"))
    print(f"wrote {len(records)} open {label} calls to {out}; {sum(r['nonprofit_eligible'] for r in records)} open to nonprofits")
    if skipped_out is not None:
        from .fetch import write_skips
        write_skips(skipped_out, skips)
    return len(records)
