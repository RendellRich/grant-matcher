"""What the adapters for states read from web pages share (arkansas.py, maryland.py, montana.py, northdakota.py,
tennessee.py, wyoming.py).

Every page is asked for with cycles.fetch_page: the project's own user agent, and the terms blocklist and the host's
robots.txt checked before each address, redirects included. A page that can't be read stops the run, so the last
data file is kept.

Records use the same fields as Ohio's (grantmatch/ohio.py), so the same scorer reads them. Nothing a page doesn't
say is filled in: a silent match stays blank ("Match not stated" on the card). A call that is rolling, or has no date,
is kept only when its own page says it is taking applications and nothing it says counts against that (keep_open).
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

# What happens if the money runs out, or once a window has closed, is not said of today: taken out of a sentence
# before reading it. A past-tense clause ("when funds were exhausted") stays.
CONDITION = re.compile(
    r"\b(?:until|once|when|if|unless|should|as long as|while|before|after)\b(?:(?!\b(?:was|were)\b)[^.;,]){0,60}?"
    r"\b(?:depleted|exhausted|expended|spent|awarded|committed|runs? out|(?:is|are|has|have) closed)\b", re.I)
SUBJECT = (r"(?:applications?|application (?:period|window|portal|process)(?: for [\w ]{0,40}?)?"
           r"|grants?(?: (?:cycle|round|portal|program|application|opportunity))?|opportunity|program|round|cycle"
           r"|portal|submissions?|competition)")
USED = "awarded|committed|allocated|obligated|spent|expended|distributed|claimed|depleted|exhausted"
RULE = r"(?![^.;]{0,40}?\b(?:after|before|if|unless|without|that|which|from|via|late|by [a-z]+|in person)\b)"
REFUSED = (rf"\bno (?:new |more |further |additional )?(?:applications?|proposals|requests|submissions) "
           rf"(?:will be|can be|are being|are|is being) (?:accepted|taken|received)\b{RULE}"
           r"|\b(?:cannot|can ?not|can't|unable to|will not|won't) (?:currently |presently )?(?:accept|take|receive)"
           rf"(?: any)?(?: new| more| further| additional)? (?:applications|requests|proposals|submissions)\b{RULE}")
# A page's own words that it isn't taking applications. STOPPED holds whatever the dates say. CLOSED does too, except
# when it is only the wait before a window the page also gives, or is about an earlier fiscal year (not_taking below).
STOPPED = re.compile(
    r"\btemporarily (?:paused|closed|suspended)\b|\bpaused applications\b|\bon hold\b"
    r"|\b(?:is|are|has been|have been) (?:currently |temporarily )?paused\b"
    r"|\bno longer (?:accepting|accepts?|taking|takes?|receiving|receives?) (?:any )?(?:new |grant |further )?"
    r"(?:applications|proposals|requests)\b"
    r"|\bapplications?(?: [\w-]+){0,3}? (?:is|are) no longer (?:being )?(?:accepted|taken|received|available)\b"
    r"|\b(?:grants?|program|applications?|round|cycle|funding)(?: \w+){0,4}? (?:is|are|has been|have been) "
    r"(?:currently )?suspended\b|" + REFUSED, re.I)
CLOSED = re.compile(
    rf"\b{SUBJECT} (?:is|are) (?:now |currently )?closed\b(?! out\b)"
    rf"|\b{SUBJECT} (?:has|have) (?:now |since )?closed\b(?![- ](?:out|caption))"
    r"|\bclosed (?:for|to) (?:new )?(?:applications|applicants|this cycle|requests|proposals)\b"
    r"|\bnot (?:currently )?accepting (?:new )?applications\b"
    r"|\bapplications are not (?:currently )?(?:being )?accepted\b"
    r"|\b(?:funds?|funding)(?: for [\w ]{0,25}?)? (?:is|are|has been|have been|was|were) "
    r"(?:now |fully |completely |already |all )?(?:depleted|exhausted)\b"
    rf"|\b(?:funds?|funding) (?:is|are|has been|have been|was|were) (?:now )?(?:fully|completely) (?:{USED})\b"
    rf"|\ball(?: [\w-]+){{0,3}}? (?:funds?|funding|awards|grants) (?:has|have) (?:now |already )?been (?:{USED})\b",
    re.I)
# A call that no date will end (rolling, or taken until the money runs out) is held to more: its page has to say it is
# taking applications (TAKING), and any of DOUBT's words anywhere about it counts against it. Not finding a "closed"
# phrase is never enough, since a page can close a program in words nobody has written down here.
TAKING = re.compile(
    r"\b(?:ongoing|rolling|year[- ]round|any ?time|continual basis|continuous basis|continuously|each month"
    r"|every month|monthly)\b"
    r"|\b(?:accepting|taking|accepts|takes) (?:new )?(?:grant )?(?:applications|proposals|requests)\b"
    r"|\bapplications?(?: [\w-]+){0,3}? (?:is|are|will be) (?:now |currently )?(?:being )?(?:accepted|open)\b"
    r"|\b(?:is|are) (?:now|currently) open\b", re.I)
DOUBT = re.compile(
    r"\bclos(?:ed|es|ing|ure)\b(?![- ]?(?:out|caption))"
    r"|\bpaus(?:e|ed|es|ing)\b|\bon hold\b|\bfroz(?:e|en)\b|\bfreeze\b"
    # suspended or suspension, said of the money or the program: grant terms also speak of a suspended contractor
    r"|\b(?:grants?|program|applications?|funding|funds|awards?|round|cycle|opportunity)(?: [\w-]+){0,4}? "
    r"(?:is|are|has been|have been|was|were)(?: \w+)? suspended\b"
    r"|\bsuspend(?:ed|ing|s)? (?:new |all |accepting )?(?:applications|(?:the|this) (?:program|grant|fund)|grants|"
    r"funding|awards)\b"
    r"|\bsuspension of (?:the |this )?(?:grant|program|application|funding)s?\b"
    r"|\bexhaust(?:ed|ion)\b|\bdeplet(?:ed|ion)\b|\br[au]n out\b|\bused up\b|\boversubscribed\b|\bno longer\b"
    rf"|\bfully (?:been )?(?:subscribed|{USED})\b"
    r"|\ball(?: [\w-]+){0,3}? (?:funds?|funding|awards) (?:has|have|is|are|was|were)(?: now| already)?(?: been)? "
    rf"(?:gone|{USED})\b"
    # "not accepting", and an application not accepted or open; a rule about late or paper ones says nothing of today
    r"|\b(?:not|isn't|aren't) (?:currently |yet |presently )?(?:accepting|taking|receiving)\b"
    r"(?! (?:late|incomplete|paper|mailed|faxed|emailed|hard)\b)"
    r"|(?<!late )(?<!incomplete )(?<!paper )(?<!mailed )(?<!faxed )(?<!emailed )\bapplications?(?: [\w-]+){0,2}? "
    r"(?:is|are|will) not (?:currently |now )?(?:be |being )?(?:accepted|taken|received|open)\b"
    r"(?! (?:after|before|if|from|by|via|through|without|unless)\b)"
    r"|\b(?:grants?|program|funding|opportunity|applications?)(?: [\w-]+){0,2}? (?:is|are) "
    r"(?:currently |presently |now )?not (?:currently )?(?:open|available|offered|being offered)\b(?! (?:to|for)\b)"
    r"|\bunavailable\b|\bdiscontinu(?:ed|ing)\b|\bcancell?ed\b|(?<!-)\bended\b|\bstopped\b"
    r"|\bno (?:more |remaining |additional |further )?(?:funds?|funding)(?: is| are)? "
    r"(?:available|remain(?:s|ing)?|left)\b"
    r"|\bcheck back\b|\bwill (?:re)?open\b|\breopens?\b|\bwait(?:ing)?[- ]?list\b"
    r"|\breached (?:its |the )?(?:limit|capacity|maximum)\b|\bat (?:full )?capacity\b"
    r"|\bon (?:a )?(?:temporary )?hold\b|\bdeadline (?:has )?passed\b|\bwill resume\b|\baccepting [\w ]{0,20}?again\b"
    r"|\b(?:program|grant|fund|opportunity)(?: [\w-]+){0,3}? (?:has been|is|was) (?:eliminated|terminated|retired|"
    r"defunded|concluded)\b"
    r"|\b(?:funds?|funding|allocation|budget|money)(?: for [\w ]{0,25}?)? (?:has|have) (?:now |all )?been "
    r"(?:used|spent|committed|obligated|allocated|awarded)\b|" + REFUSED, re.I)
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
OPENED = re.compile(r"\bwill (?:re)?open (?:on |in )?([A-Z][a-z]+\.? \d{1,2}, \d{4})")
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
            said = CONDITION.sub(" ", sentence)
            if STOPPED.search(said) or (CLOSED.search(said) and not _only_waiting(sentence, text, today, opens)):
                return sentence
    return ""


def doubt(texts: list[str], today: str | None = None) -> str:
    """For a call no date will end: the first sentence with any closed, paused or used-up wording, or ""."""
    today = today or date.today().isoformat()

    def opened(m: re.Match) -> str:
        """"will open July 1, 2026" once that day is here: it opened, which says nothing against it."""
        return " " if (day(m.group(1)) or "9999") <= today else m.group(0)

    for text in texts:
        for sentence in re.split(r"(?<=[.!?])\s+", clean(text)):
            if DOUBT.search(OPENED.sub(opened, CONDITION.sub(" ", sentence))):
                return sentence
    return ""


def taking(statements: list[str]) -> bool:
    """Whether any of the page's statements about a program says it is taking applications."""
    return any(TAKING.search(clean(s)) for s in statements)


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
    applications}. A rolling or undated call, which no date will end, also gives "rolling" (the page's words on when it
    takes applications) and "about" (everything the page says of it): it is kept only when "rolling" says it is taking
    applications and nothing in "about" says otherwise. Rows dropped are added to skips, when given."""
    today = today or date.today().isoformat()
    out: dict[str, dict] = {}
    for row in rows:
        rec = row["record"]
        base = {"source": source, "id": rec["id"], "name": rec["title"] or "(no title)", "state": rec["state"],
                "funder": rec["agency"], "url": rec["url"]}
        reason = detail = ""
        rolling = "rolling" in row or rec["deadlines"] == "Ongoing"
        closed = row.get("closed") or (doubt(row.get("about", []), today) if rolling else "")
        if not rec["title"]:
            reason, detail = "no_title", "The page's entry has no title"
        elif closed:
            reason, detail = "not_taking", f"The page says: {clean(closed)[:200]}"
        elif rec["closes"] and rec["closes"] < today:
            reason, detail = "deadline_passed", f"Listed, but its deadline was {rec['closes']}"
        elif not rec["closes"] and rec["deadlines"] != "Ongoing":
            reason, detail = "no_deadline", f"No date and not rolling (it says: {rec['deadlines'][:80] or 'nothing'})"
        elif rolling and not taking(row.get("rolling", [])):
            reason, detail = "not_taking", "No date may end this call, and the page doesn't say it is taking applications"
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
