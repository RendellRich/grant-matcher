"""Washington state grants from FundHubWA, the Department of Commerce's funding portal.

FundHubWA (fundhub.wa.gov) lists state and federal grants, loans, rebates and incentives for Washington,
most of them for climate, clean energy, resilience and land and water work. Each listing is a WordPress
post with structured fields, published through the site's public JSON API (/wp-json/wp/v2/funding): its
status, application window, the state agency behind it, whether the money is state or federal, the total
and award range, cost share, eligibility text, and the portal's own audience tags ("Nonprofits",
"Local Government", "Individuals" and so on).

Only state money is read here. The federal listings are federal notices that Grants.gov already carries,
so the federal refresh has them. Records use the same fields as California's (grantmatch/california.py).

Run:  python -m grantmatch.washington --out data/washington.json.gz [--skipped build/skipped-washington.json.gz]
"""
from __future__ import annotations

import argparse
import gzip
import html
import json
import re
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

import requests

API = "https://fundhub.wa.gov/wp-json/wp/v2/"
FIELDS = "id,link,title,modified,funding-type,funding-audience,funding-sector,funding-disbursement-method,acf"
PAUSE = 0.5
MIN_ROWS = 100  # the portal holds several hundred listings, open and closed

session = requests.Session()
session.headers.update({"User-Agent": "grant-matcher (github.com/RendellRich/grant-matcher)"})

NONPROFIT = re.compile(r"non-?\s?profit|not-for-profit|community[- ]based organi[sz]ation|501\s*\(c\)", re.I)
NO_NONPROFIT = re.compile(r"\b(?:no|not|nor|ineligible|cannot)\b[^.]{0,50}(?:non-?\s?profit|not-for-profit)", re.I)
INVITATION = re.compile(r"\bby invitation only\b|\binvitation[- ]only\b", re.I)
OPEN = {"active", "open", "upcoming", "forecasted"}


def _clean(s: str | None) -> str:
    s = re.sub(r"<\s*(?:li|br|p|h\d)\b[^>]*>", "; ", s or "", flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"\s+", " ", html.unescape(s).replace("\xa0", " ")).strip()
    s = re.sub(r"(?:\s*;\s*)+", "; ", s).strip("; ")
    return re.sub(r"\s+([.,:])", r"\1", s)


def _day(s) -> str | None:
    s = str(s or "").strip()
    if re.fullmatch(r"\d{8}", s):
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    return None


def _money(s) -> str:
    s = str(s or "").replace(",", "").replace("$", "").strip()
    try:
        n = float(s)
    except ValueError:
        return ""
    return f"${n:,.0f}" if n > 1 else ""


def terms(name: str) -> dict[int, str]:
    """A taxonomy's term ids and names, e.g. funding-audience: {8: "Nonprofits", ...}."""
    r = session.get(API + name, params={"per_page": 100, "_fields": "id,name"}, timeout=60)
    r.raise_for_status()
    return {t["id"]: html.unescape(t["name"]) for t in r.json()}


def fetch_all() -> list[dict]:
    rows, page = [], 1
    while True:
        r = session.get(API + "funding", params={"per_page": 100, "page": page, "_fields": FIELDS}, timeout=90)
        if r.status_code == 400 and page > 1:  # past the last page
            break
        r.raise_for_status()
        batch = r.json()
        rows += batch
        if page >= int(r.headers.get("X-WP-TotalPages", page)) or not batch:
            break
        page += 1
        time.sleep(PAUSE)
    return rows


def _link(v) -> str:
    if isinstance(v, dict):
        return (v.get("url") or "").strip()
    return v.strip() if isinstance(v, str) and v.startswith("http") else ""


def normalize(row: dict, tax: dict[str, dict[int, str]]) -> dict:
    a = row.get("acf") or {}
    names = lambda key: [tax.get(key, {}).get(i, "") for i in row.get(key) or [] if tax.get(key, {}).get(i)]
    audience = names("funding-audience")
    kinds = names("funding-type")
    methods = names("funding-disbursement-method")
    eligibility = _clean(a.get("eligibility"))
    if audience:  # the portal's own tags decide, like a state's applicant categories
        nonprofit = any(re.fullmatch(r"non-?profits?", t.strip(), re.I) for t in audience)
        who = ", ".join(audience)
    else:
        nonprofit = bool(NONPROFIT.search(eligibility)) and not NO_NONPROFIT.search(eligibility)
        who = "" if nonprofit or eligibility else "Not stated on the portal; read the program page"
        nonprofit = nonprofit or not eligibility
    low, high = _money(a.get("award_start")), _money(a.get("ending_amount"))
    size = f"{low} to {high}" if low and high and low != high else high or low
    award = [f"{label}: {value}." for label, value in (
        ("Total available", _money(a.get("total_amount"))),
        ("Award size", size),
        ("Number of awards", str(a.get("number_of_awards") or "").strip()),
        ("Payment", _clean(a.get("disbursement_notes"))[:200]),
    ) if value]
    closes = _day(a.get("application_close_date"))
    cost_share = str(a.get("cost_share") or "").strip().lower()
    loan = any(k.lower() == "loan" for k in kinds)
    title = _clean((row.get("title") or {}).get("rendered"))
    agency = _clean(a.get("source"))
    sectors = {n.lower() for n in tax.get("funding-sector", {}).values()} | {"rural", "residential", "renewable energy",
                                                                          "energy infrastructure", "workforce development"}
    if agency and any(part.strip().lower() in sectors for part in agency.split(",")):
        agency = ""  # some listings carry their topic tags where the agency belongs
    apply = _link(a.get("application_link"))
    how = _clean(a.get("resources"))[:900]
    return {
        "id": f"wa-{row['id']}",
        "csfa": "",
        "number": (a.get("internal_reference_id") or "").strip(),
        "state": "WA",
        "title": title,
        "agency": agency or "Washington state agency (named on the program page)",
        "objectives": " ".join(t for t in (_clean(a.get("description")), _clean(a.get("requirements"))) if t)[:3000],
        "assistance": "; ".join(kinds) or "Grant",
        "applicant_types": _clean(". ".join(t for t in (who, eligibility) if t))[:1200],
        "nonprofit_eligible": nonprofit,
        "earmark": False,
        "restrictions": "",
        "application": (f"{how} Apply: {apply}" if apply else how) or "Apply as the program page says.",
        "award": " ".join(award)[:800],
        "deadlines": closes or "Ongoing",
        "contact": _clean(a.get("contact"))[:600],
        "web": apply,
        "subjects": "; ".join(names("funding-sector")),
        "fiscal_year": "",
        "url": row.get("link") or "",
        "status": "active",
        "opens": _day(a.get("application_open_date")) or _day(a.get("open_date")),
        "closes": closes,
        "match": "Required" if cost_share == "yes" else "",
        "loan": loan,
        "funding_method": "; ".join(m for m in methods if m.lower() != "unspecified"),
        "loi": str(a.get("pre_application") or "").strip().lower() == "yes",
        "updated": (row.get("modified") or "")[:10] or None,
        **({"match_none": True} if cost_share == "no" else {}),  # a blank says nothing
    }


def build_records(rows: list[dict], tax: dict[str, dict[int, str]], today: str | None = None,
                  skips: list[dict] | None = None) -> list[dict]:
    """Open state-funded calls. Federal listings are left to the federal refresh; closed ones are dropped."""
    today = today or date.today().isoformat()
    out: dict[str, dict] = {}
    for row in rows:
        a = row.get("acf") or {}
        if str(a.get("federal_or_state") or "").strip().lower() == "federal":
            continue
        status = str(a.get("funding_status") or "").strip().lower()
        if status and status not in OPEN:
            continue  # the portal keeps closed and expired listings; they aren't skips, just history
        try:
            rec = normalize(row, tax)
        except Exception as exc:
            print(f"skip {row.get('id')}: {exc}", file=sys.stderr)
            continue
        base = {"source": "washington", "id": rec["id"], "name": rec["title"] or "(no title)", "state": "WA",
                "funder": rec["agency"], "url": rec["url"]}
        if not rec["title"]:
            if skips is not None:
                skips.append({**base, "reason": "no_title", "detail": "The portal's listing has no title"})
            continue
        if rec["closes"] and rec["closes"] < today:
            if skips is not None:
                skips.append({**base, "reason": "deadline_passed",
                              "detail": f"Marked {status or 'open'}, but its window closed {rec['closes']}"})
            continue
        if INVITATION.search(f"{rec['applicant_types']} {rec['objectives']}"):
            if skips is not None:
                skips.append({**base, "reason": "invitation_only", "detail": "The listing says: by invitation only"})
            continue
        out[rec["id"]] = rec
    return sorted(out.values(), key=lambda r: r["id"])


def build(out: Path, skipped_out: Path | None = None) -> int:
    tax = {name: terms(name) for name in ("funding-audience", "funding-type", "funding-sector", "funding-disbursement-method")}
    rows = fetch_all()
    if len(rows) < MIN_ROWS:
        raise RuntimeError(f"Only {len(rows)} listings on FundHubWA; keeping the previous data file")
    skips: list[dict] = []
    records = build_records(rows, tax, skips=skips)
    payload = {
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "source": "FundHubWA, Washington Department of Commerce (fundhub.wa.gov)",
        "state": "WA", "count": len(records), "programs": records,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(out, "wt", encoding="utf-8") as fh:
        json.dump(payload, fh, separators=(",", ":"))
    print(f"wrote {len(records)} open Washington state listings to {out}; {sum(r['nonprofit_eligible'] for r in records)} open to nonprofits")
    if skipped_out is not None:
        from .fetch import write_skips
        write_skips(skipped_out, skips)
    return len(records)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="data/washington.json.gz", type=Path)
    ap.add_argument("--skipped", type=Path)
    args = ap.parse_args()
    build(args.out, args.skipped)


if __name__ == "__main__":
    main()
