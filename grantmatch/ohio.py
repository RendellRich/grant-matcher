"""Ohio state grants from the Ohio Grants Partnership's list of current funding opportunities.

Ohio's grants policy (Office of Budget and Management, ORC 126.22) requires every state agency that offers a
state or federal funding opportunity to post it on the Ohio Grants Partnership site, grants.ohio.gov. Its
"Find current opportunities" table is filled from a public JSON list, api.obm.ohio.gov, with each
opportunity's title, number, agency, application window, award floor and ceiling, match, a description and
the state's own list of eligible applicant types ("Non-Profit", "County", "Township" and so on). Each one
also has a public detail page on grantsportal.ohio.gov.

Records use the same fields as California's and Illinois' (grantmatch/california.py), so the same scorer
reads them.

Run:  python -m grantmatch.ohio --out data/ohio.json.gz [--skipped build/skipped-ohio.json.gz]
"""
from __future__ import annotations

import argparse
import gzip
import html
import json
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import requests

LIST = "https://api.obm.ohio.gov/grants/getfundingopportunities/0/0/1"
DETAIL = "https://grantsportal.ohio.gov/Public/FundingOpportunityDetails?detailid={}"
SITE = "https://grants.ohio.gov/funding-opportunities/find-current-opportunities"
MIN_ROWS = 3  # Ohio posts a few dozen at a time at most; fewer than this means the list changed shape

session = requests.Session()
session.headers.update({"User-Agent": "grant-matcher (github.com/RendellRich/grant-matcher)"})

# The state's own applicant types that a nonprofit can be. Faith-based organizations are almost always
# nonprofits; "Houses of Worship" is kept apart because it often means the building, not the organization.
NONPROFIT_TYPES = re.compile(r"^(?:non-?\s?profit|faith-based associations/organizations)$", re.I)
INVITATION = re.compile(r"\bby invitation only\b|\binvitation[- ]only\b", re.I)


def _clean(s: str | None) -> str:
    s = re.sub(r"<[^>]+>", " ", html.unescape(s or ""))
    return re.sub(r"\s+", " ", s.replace("\xa0", " ")).strip()


def _day(s: str | None) -> str | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s[:19]).date().isoformat()
    except ValueError:
        try:
            return datetime.strptime(s.strip()[:10], "%m/%d/%Y").date().isoformat()
        except ValueError:
            return None


def _money(n) -> str:
    try:
        n = float(n or 0)
    except (TypeError, ValueError):
        return ""
    return f"${n:,.0f}" if n > 0 else ""


def _codes(items) -> list[str]:
    out = []
    for it in items or []:
        code = it.get("Code") if isinstance(it, dict) else it
        if isinstance(code, str) and code.strip() and (not isinstance(it, dict) or it.get("IsValid", True)):
            out.append(code.strip())
    return out


def normalize(item: dict) -> dict:
    o = item.get("Opportunity") or {}
    agency = ((o.get("AgencyDivision") or {}).get("Agency") or {})
    division = (o.get("AgencyDivision") or {}).get("DivisionName") or ""
    who = _codes(item.get("EligibleApplicants"))
    nonprofit = any(NONPROFIT_TYPES.match(c) for c in who)
    overview = _clean(o.get("OverviewDetails"))
    described = _clean(o.get("ProvidedProjectDescription"))
    floor, ceiling = _money(o.get("AwardFloor")), _money(o.get("AwardCeiling"))
    size = f"{floor} to {ceiling}" if floor and ceiling else ceiling or floor
    award = [f"{label}: {value}." for label, value in (
        ("Total available", _money(o.get("EstimatedFunding"))),
        ("Award size", size),
        ("Average award", _money(o.get("AverageAwardSize"))),
        ("Funding", _clean(o.get("FinancialDetails"))[:300]),
    ) if value]
    contact = ", ".join(t for t in (
        " ".join(t for t in (_clean(o.get("ContactFirstName")), _clean(o.get("ContactLastName"))) if t),
        _clean(o.get("ContactEmail")), _clean(o.get("ContactPhone"))) if t)
    guid = (o.get("GUID") or o.get("AlternatePK") or "").strip()
    number = _clean(o.get("OpportunityNumber"))
    key = re.sub(r"[^a-z0-9]+", "-", (number or guid or o.get("OpportunityTitle", "")).lower()).strip("-")[:48]
    url = DETAIL.format(guid) if guid else SITE
    closes = _day(o.get("ApplicationDueDate")) or _day(o.get("DisplayAEndDate"))
    agency_name = agency.get("AgencyName") or agency.get("FullAgencyName") or ""
    unit = _clean(o.get("AgencyBusinessUnitDescription")) or ("" if division == "No Division" else division)
    return {
        "id": f"oh-{key}",
        "csfa": "",
        "number": number,
        "state": "OH",
        "title": _clean(o.get("OpportunityTitle")),
        "agency": ", ".join(t for t in (agency_name, unit) if t),
        "objectives": " ".join(t for t in (overview, described) if t)[:3000],
        "assistance": "Grant",
        "applicant_types": "; ".join(who)[:1200] or "Not stated on the state's listing; read the notice",
        "nonprofit_eligible": nonprofit if who else True,
        "earmark": False,
        "restrictions": "",
        "application": ("Apply as the notice's page says; many Ohio grants use an OH|ID account and the Ohio Grants Portal."
                        if not o.get("RegistrationRequired") else
                        "Register on the Ohio Grants Portal from the notice's page, then apply."),
        "award": " ".join(award)[:800],
        "deadlines": closes or "",
        "contact": contact[:600],
        "web": _clean(o.get("MoreInformationURL")),
        "subjects": "; ".join(_codes(item.get("OpportunityCategories"))),
        "fiscal_year": "",
        "url": url,
        "status": "active",
        "opens": _day(o.get("ApplicationStartDate")),
        "closes": closes,
        "match": "Required" if o.get("MatchingRequired") else "",
        "loan": False,
        "funding_method": "",
        "loi": False,
        "updated": _day(o.get("UpdatedDate")) or _day(o.get("InsertedDate")) or _day(o.get("ApplicationStartDate")),
    }


def build_records(items: list[dict], today: str | None = None, skips: list[dict] | None = None) -> list[dict]:
    """Open calls, one per opportunity. Rows dropped are added to skips, when given."""
    today = today or date.today().isoformat()
    out: dict[str, dict] = {}
    for item in items:
        try:
            rec = normalize(item)
        except Exception as exc:  # one odd row shouldn't sink the refresh
            print(f"skip a row: {exc}", file=sys.stderr)
            continue
        base = {"source": "ohio", "id": rec["id"], "name": rec["title"] or "(no title)", "state": "OH",
                "funder": rec["agency"], "url": rec["url"]}
        if not rec["title"]:
            if skips is not None:
                skips.append({**base, "reason": "no_title", "detail": "The state's row has no title"})
            continue
        if rec["closes"] and rec["closes"] < today:
            if skips is not None:
                skips.append({**base, "reason": "deadline_passed", "detail": f"Listed, but its window closed {rec['closes']}"})
            continue
        if INVITATION.search(rec["objectives"]):
            if skips is not None:
                skips.append({**base, "reason": "invitation_only", "detail": "The notice says: by invitation only"})
            continue
        out[rec["id"]] = rec
    return sorted(out.values(), key=lambda r: r["id"])


def fetch_list() -> list[dict]:
    r = session.get(LIST, timeout=60)
    r.raise_for_status()
    data = r.json()
    if data.get("IsFailure"):
        raise RuntimeError(f"Ohio's list said: {data.get('FailureMessage')}")
    return data.get("Result") or []


def build(out: Path, skipped_out: Path | None = None) -> int:
    items = fetch_list()
    if len(items) < MIN_ROWS:
        raise RuntimeError(f"Only {len(items)} rows on the Ohio list; keeping the previous data file")
    skips: list[dict] = []
    records = build_records(items, skips=skips)
    payload = {
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "source": "Ohio Grants Partnership, current funding opportunities (grants.ohio.gov)",
        "state": "OH", "count": len(records), "programs": records,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(out, "wt", encoding="utf-8") as fh:
        json.dump(payload, fh, separators=(",", ":"))
    print(f"wrote {len(records)} open Ohio opportunities to {out}; {sum(r['nonprofit_eligible'] for r in records)} open to nonprofits")
    if skipped_out is not None:
        from .fetch import write_skips
        write_skips(skipped_out, skips)
    return len(records)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="data/ohio.json.gz", type=Path)
    ap.add_argument("--skipped", type=Path)
    args = ap.parse_args()
    build(args.out, args.skipped)


if __name__ == "__main__":
    main()
