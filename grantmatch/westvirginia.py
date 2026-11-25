"""West Virginia state grants from grants.wv.gov, the state's list of available grants.

grants.wv.gov is a SharePoint site whose "AvailableGrants" list holds each agency's grant listings, and the
site's own public REST API returns the whole list as JSON, with no login: title, agency (Division), type of
grant, who may apply (EntityEligible, free text), posted and due dates, a forecast note ("Ongoing", "Annual
deadline of April 1st"), the details, guidelines and how to apply, links, and the program contact.

The list is never pruned: most rows are past their due date or were last updated years ago. A row whose due
date has passed is dropped, and so is one with no due date unless its forecast says it takes applications on a
rolling or ongoing basis. Who may apply comes from the state's own EntityEligible text: one that names
nonprofits, 501(c)(3) groups, community action agencies or "any legal entity" keeps the grant open to
nonprofits; one that names only others (state or local governments, districts, businesses) leaves nonprofits
out; and a blank one is kept with a note to read the notice.

Records use the same fields as Ohio's (grantmatch/ohio.py), so the same scorer reads them.

Run:  python -m grantmatch.westvirginia --out data/westvirginia.json.gz [--skipped build/skipped-westvirginia.json.gz]
      add --file <saved.json> to read a saved copy of the list instead of fetching it
"""
from __future__ import annotations

import argparse
import gzip
import html
import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

LIST = "https://grants.wv.gov/_api/web/lists/getbytitle('AvailableGrants')/items?$top=500"
SITE = "https://grants.wv.gov/"
MIN_ROWS = 20  # the list holds about 125 rows, most of them old; fewer than this means it changed shape

session = requests.Session()
session.headers.update({"User-Agent": "grant-matcher (github.com/RendellRich/grant-matcher)",
                        "Accept": "application/json;odata=nometadata"})

NONPROFIT = re.compile(r"non-?\s?profit|not-for-profit|501\s*\(?\s*c\s*\)?\s*\(?\s*3|community[- ]based organi[sz]ation|"
                       r"community action agenc|faith-based|any (?:legal )?entit|any (?:eligible )?organi[sz]ation", re.I)
# Only a real exclusion leaves nonprofits out: "nonprofits are not eligible", "non-profits may not apply", "not
# open to nonprofit organizations". A bare "not" or "no" nearby isn't one ("No match is required for non-profit
# organizations"), and the "not" in "not-for-profit" never counts.
_NP = r"(?:non-?\s?profits?|not-for-profits?)"
NO_NONPROFIT = re.compile(
    rf"\b{_NP}(?:\s+(?:organi[sz]ations?|agencies|entities|groups))?\s+(?:are|is)\s+(?:not\s+eligible|ineligible|excluded)"
    rf"|\b{_NP}[^.;]{{0,30}}\b(?:may|can|shall)\s*not\b(?!-)"
    rf"|\b{_NP}[^.;]{{0,30}}\bcannot\b"
    rf"|\b(?:not open to|excluding|excludes|except(?: for)?)\s+(?:[\w-]+\s+){{0,3}}?{_NP}", re.I)
# A sentence that names nonprofits only as reviewers ("reviewed by ... state and federal agencies as well as non
# profits") doesn't make them applicants.
REVIEWERS = re.compile(r"\breview(?:ed|ers?)?\b|\bmade up of\b|\bcommittee\b|\bpanel\b", re.I)
INVITATION = re.compile(r"\bby invitation only\b|\binvitation[- ]only\b", re.I)
ROLLING = re.compile(r"\b(?:ongoing|rolling|open until|year[- ]round|continuous)", re.I)
LOAN = re.compile(r"\bloans?\b|\brevolving (?:loan )?funds?\b", re.I)


def _clean(s: str | None) -> str:
    s = re.sub(r"<\s*(?:br|p|li|h\d|div)\b[^>]*>", " ", s or "", flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s).replace("\xa0", " ").replace("\u200b", "")
    return re.sub(r"\s+", " ", s).strip()


def _day(s: str | None) -> str | None:
    """The date in West Virginia. SharePoint stores midnight Eastern as 04:00 or 05:00 UTC, so four hours back
    gives the right day for both."""
    if not s:
        return None
    try:
        t = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None
    if t.tzinfo is not None:
        t = t.astimezone(timezone.utc).replace(tzinfo=None) - timedelta(hours=4)
    return t.date().isoformat()


def who_can_apply(text: str) -> tuple[bool, str]:
    """(nonprofits can apply, what the card says about who can) from the state's EntityEligible text."""
    text = _clean(text)
    if not text:
        return True, "Not stated on the state's listing; read the notice"
    if NO_NONPROFIT.search(text):
        return False, text
    sentences = re.split(r"(?<=[.;])\s+", text)
    return any(NONPROFIT.search(x) and not REVIEWERS.search(x) for x in sentences), text


def normalize(item: dict, today: str | None = None) -> dict:
    title = _clean(item.get("Title"))
    nonprofit, who = who_can_apply(item.get("EntityEligible") or "")
    details = " ".join(t for t in (_clean(item.get("Details")), _clean(item.get("FullDetails"))) if t)
    closes = _day(item.get("DueDate1"))
    opens = _day(item.get("PostedDate"))
    forecast = _clean(item.get("Forecasted"))
    rolling = not closes and bool(ROLLING.search(forecast))
    links = [u for u in (_clean(item.get(k)) for k in ("ReadMoreLinkURL", "LinkToApply", "LinkURL1")) if u.startswith("http")]
    apply_link = _clean(item.get("LinkToApply"))
    dates = [f"{_clean(item.get(f'ImportantDateTitle{n}'))}: {_day(item.get(f'ImportantDate{n}'))}." for n in (1, 2, 3)
             if _clean(item.get(f"ImportantDateTitle{n}")) and _day(item.get(f"ImportantDate{n}"))]
    contact = ", ".join(t for t in (_clean(item.get("ContactName1")), _clean(item.get("ContactEmail1")),
                                    _clean(item.get("ContactPhone1"))) if t)
    kind = _clean(item.get("TypeOfGrant"))
    today = today or date.today().isoformat()
    return {
        "id": f"wv-{item.get('Id') or item.get('ID')}",
        "csfa": "",
        "number": "",
        "state": "WV",
        "title": title,
        "agency": _clean(item.get("Division")),
        "objectives": details[:3000],
        "assistance": "Loan" if LOAN.search(title) else "Grant",
        "applicant_types": who[:1200],
        "nonprofit_eligible": nonprofit,
        "earmark": False,
        "restrictions": _clean(item.get("Guidelines"))[:1200],
        "application": " ".join(t for t in (_clean(item.get("HowToApply")),
                                            f"Apply at {apply_link}." if apply_link.startswith("http") else "",
                                            *dates) if t)[:1200],
        "award": f"Type: {kind}." if kind else "",
        "deadlines": closes or ("Ongoing" if rolling else forecast) or "",
        "contact": contact[:600],
        "web": links[0] if links else SITE,
        "subjects": "",
        "fiscal_year": "",
        "url": links[0] if links else SITE,
        "status": "forecasted" if opens and opens > today else "active",
        "opens": opens,
        "closes": closes,
        "match": "",
        "loan": bool(LOAN.search(title)),
        "funding_method": "",
        "loi": False,
        "updated": _day(item.get("Modified")),
        "_rolling": rolling,
    }


def build_records(items: list[dict], today: str | None = None, skips: list[dict] | None = None) -> list[dict]:
    """Open calls, one per listing. Rows dropped are added to skips, when given."""
    today = today or date.today().isoformat()
    out: dict[str, dict] = {}
    for item in items:
        try:
            rec = normalize(item, today)
        except Exception as exc:  # one odd row shouldn't sink the refresh
            print(f"skip a row: {exc}", file=sys.stderr)
            continue
        rolling = rec.pop("_rolling")
        base = {"source": "westvirginia", "id": rec["id"], "name": rec["title"] or "(no title)", "state": "WV",
                "funder": rec["agency"], "url": rec["url"]}
        if not rec["title"]:
            if skips is not None:
                skips.append({**base, "reason": "no_title", "detail": "The state's row has no title"})
            continue
        if rec["closes"] and rec["closes"] < today:
            if skips is not None:
                skips.append({**base, "reason": "deadline_passed", "detail": f"Listed, but its due date was {rec['closes']}"})
            continue
        if not rec["closes"] and not rolling:
            if skips is not None:
                said = f" (it says: {rec['deadlines'][:80]})" if rec["deadlines"] else ""
                skips.append({**base, "reason": "no_deadline",
                              "detail": f"No due date and not rolling{said}; last updated {rec['updated'] or 'unknown'}"})
            continue
        if INVITATION.search(rec["objectives"] + " " + rec["application"]):
            if skips is not None:
                skips.append({**base, "reason": "invitation_only", "detail": "The listing says: by invitation only"})
            continue
        out[rec["id"]] = rec
    return sorted(out.values(), key=lambda r: r["id"])


def fetch_list() -> list[dict]:
    r = session.get(LIST, timeout=60)
    r.raise_for_status()
    return r.json().get("value") or []


def build(out: Path, skipped_out: Path | None = None, saved: Path | None = None) -> int:
    items = json.loads(saved.read_text(encoding="utf-8")).get("value", []) if saved else fetch_list()
    if len(items) < MIN_ROWS:
        raise RuntimeError(f"Only {len(items)} rows on the West Virginia list; keeping the previous data file")
    skips: list[dict] = []
    records = build_records(items, skips=skips)
    payload = {
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "source": "West Virginia grants.wv.gov, AvailableGrants list",
        "state": "WV", "count": len(records), "programs": records,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(out, "wt", encoding="utf-8") as fh:
        json.dump(payload, fh, separators=(",", ":"))
    print(f"wrote {len(records)} open West Virginia grants to {out}; {sum(r['nonprofit_eligible'] for r in records)} open to nonprofits")
    if skipped_out is not None:
        from .fetch import write_skips
        write_skips(skipped_out, skips)
    return len(records)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="data/westvirginia.json.gz", type=Path)
    ap.add_argument("--skipped", type=Path)
    ap.add_argument("--file", type=Path, help="a saved copy of the list's JSON, instead of fetching it")
    args = ap.parse_args()
    build(args.out, args.skipped, args.file)


if __name__ == "__main__":
    main()
