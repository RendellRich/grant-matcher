"""What the adapters for states read from web pages share (arkansas.py, maryland.py, northdakota.py, wyoming.py).

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

PAUSE = 2  # seconds between requests to one site; none of these hosts' robots.txt asks for more

# A page's own words that it isn't taking applications, whatever its dates say.
NOT_TAKING = re.compile(
    r"\btemporarily paused\b|\bpaused applications\b|\bapplications (?:are|have been) (?:temporarily )?(?:paused|suspended)\b"
    r"|\b(?:currently|is) closed for (?:applications|this cycle)\b|\bnot (?:currently )?accepting applications\b", re.I)
INVITATION = re.compile(r"\bby invitation only\b|\binvitation[- ]only\b", re.I)
LOAN = re.compile(r"\bloans?\b(?!\s+(?:repayment|forgiveness))|\brevolving (?:loan )?funds?\b", re.I)


def clean(s: str | None) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("\xa0", " ").replace("​", "").replace("﻿", "")).strip()


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
    """The first full date in the text: "Dec. 3, 2026", "March 26, 2027" or "12/09/26"."""
    text = clean(text)
    found = DATE.search(text)
    short = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{2})\b", text)
    if found and not (short and short.start() < found.start()):
        if found.group("mon"):
            parts, fmt = f"{found.group('mon')[:3]} {found.group('day')} {found.group('year')}", "%b %d %Y"
        else:
            parts, fmt = f"{found.group('m')}/{found.group('d')}/{found.group('y')}", "%m/%d/%Y"
    elif short:
        parts, fmt = "/".join(short.groups()), "%m/%d/%y"
    else:
        return None
    try:
        return datetime.strptime(parts, fmt).date().isoformat()
    except ValueError:
        return None


def slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def record(state: str, key: str, title: str, agency: str, url: str, web: str, applicant_types: str,
           nonprofit_eligible: bool, *, closes: str | None = None, opens: str | None = None, rolling: bool = False,
           deadline_words: str = "", objectives: str = "", award: str = "", match: str = "", restrictions: str = "",
           application: str = "", funding_method: str = "", loi: bool = False, today: str | None = None) -> dict:
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
