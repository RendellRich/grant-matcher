"""California state grants from the California Grants Portal (grants.ca.gov).

The Grant Information Act of 2018 has every state agency post its grant and loan opportunities to one
portal, kept by the California State Library, which publishes the whole list as public-domain open data,
updated daily. Unlike Florida's catalog these are open calls: each has an open date, a deadline (or
"Ongoing"), who can apply, whether matching funds are required, and how the money is paid.

Records use the same fields as Florida's programs (grantmatch/florida.py), so the same scorer reads them,
plus the open-call facts: status, opens, closes, match, loan, funding_method, loi.

Run:  python -m grantmatch.california --out data/california.json.gz
      add --csv <file> to read a downloaded copy
"""
from __future__ import annotations

import argparse
import csv
import gzip
import html
import io
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import requests

DATASET = "https://data.ca.gov/api/3/action/package_show?id=california-grants-portal"
PORTAL = "https://www.grants.ca.gov/"
OPEN_STATUSES = ("active", "forecasted")
VAGUE = re.compile(r"^dependa?nt on\b", re.I)  # the portal's stock answer when an agency gives no figure
DATE = re.compile(r"^(\d{4}-\d{2}-\d{2})\b")
MIN_ROWS = 20  # fewer open calls than this means the file is broken, not that California stopped granting

session = requests.Session()
session.headers.update({"User-Agent": "grant-matcher (github.com/RendellRich/grant-matcher)"})


def csv_url() -> str:
    """The daily CSV's address, read from the dataset's own listing so a moved file is still found."""
    r = session.get(DATASET, timeout=60)
    r.raise_for_status()
    for res in r.json()["result"]["resources"]:
        if (res.get("format") or "").upper() == "CSV":
            return res["url"]
    raise RuntimeError("The California Grants Portal dataset lists no CSV file")


def fetch_rows(path: Path | None = None) -> list[dict]:
    if path is not None:
        text = path.read_text(encoding="utf-8-sig")
    else:
        r = session.get(csv_url(), timeout=300)
        r.raise_for_status()
        text = r.content.decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(text)))


def _clean(s: str | None) -> str:
    return re.sub(r"\s+", " ", html.unescape(s or "").replace("\xa0", " ")).strip()


def _day(s: str | None) -> str | None:
    """yyyy-mm-dd from the portal's timestamps; None for "Ongoing", blanks and anything else."""
    m = DATE.match((s or "").strip())
    return m.group(1) if m else None


def _link(s: str | None) -> str:
    s = (s or "").strip()
    return s if re.match(r"https?://\S+$", s) else ""


def _pairs(s: str | None) -> dict[str, str]:
    """The portal's "name: A; email: B; tel: C;" fields as a dict."""
    out = {}
    for part in (s or "").split(";"):
        key, sep, value = part.partition(":")
        if sep and value.strip():
            out[key.strip().lower()] = value.strip()
    return out


def _given(s: str | None) -> str:
    """A figure the agency actually gave, or "" for the portal's stock non-answer."""
    s = _clean(s)
    return "" if VAGUE.match(s) else s


def normalize(row: dict) -> dict:
    kinds = [k.strip() for k in (row.get("Type") or "").split(";") if k.strip()]
    applicants = [a.strip() for a in (row.get("ApplicantType") or "").split(";") if a.strip()]
    notes = _clean(row.get("ApplicantTypeNotes"))
    deadline = (row.get("ApplicationDeadline") or "").strip()
    closes = _day(deadline)
    match = _clean(row.get("MatchingFunds"))
    match = "" if match.lower() in ("", "not required") else match
    submit = _pairs(row.get("ElecSubmission"))
    how = []
    if (row.get("LOI") or "").strip().lower() == "yes":
        how.append("A letter of intent is required.")
    if _link(submit.get("url")):
        how.append(f"Apply online at {submit['url']}")
    elif submit.get("email"):
        how.append(f"Apply by email to {submit['email']}")
    award = [f"{label}: {value}." for label, value in (
        ("Total available", _given(row.get("EstAvailFunds"))),
        ("Award size", _given(row.get("EstAmounts"))),
        ("Number of awards", _given(row.get("EstAwards"))),
        ("Paid by", _clean(row.get("FundingMethod"))),
        ("Award period", _clean(row.get("AwardPeriod"))),
        ("Expected award date", _clean(row.get("ExpAwardDate"))),
    ) if value]
    limits = [t for t in (_clean(row.get("Geography")), _clean(row.get("MatchingFundsNotes")),
                          _clean(row.get("FundingMethodNotes"))) if t]
    contact = _pairs(row.get("ContactInfo"))
    return {
        "id": f"ca-{row['PortalID'].strip()}",
        "csfa": "",
        "number": row["PortalID"].strip(),
        "state": "CA",
        "title": _clean(row.get("Title")),
        "agency": _clean(row.get("AgencyDept")),
        "objectives": f"{_clean(row.get('Purpose'))} {_clean(row.get('Description'))}".strip()[:3000],
        "assistance": "; ".join(kinds),
        "applicant_types": "; ".join(applicants) + (f". {notes}" if notes else ""),
        "nonprofit_eligible": "Nonprofit" in applicants,
        "earmark": False,
        "restrictions": " ".join(limits)[:1500],
        "application": " ".join(how),
        "award": " ".join(award)[:800],
        "deadlines": "Ongoing" if deadline.lower() == "ongoing" else (closes or ""),
        "contact": ", ".join(contact[k] for k in ("name", "email", "tel") if contact.get(k))[:600],
        "web": _link(row.get("AgencyURL")),
        "subjects": _clean(row.get("Categories")),
        "fiscal_year": "",
        "url": _link(row.get("GrantURL")) or _link(row.get("AgencyURL")) or PORTAL,
        # Open-call facts Florida's catalog doesn't have
        "status": (row.get("Status") or "").strip().lower(),
        "opens": _day(row.get("OpenDate")),
        "closes": closes,
        "match": match,
        "loan": bool(kinds) and all(k.lower() == "loan" for k in kinds),
        "funding_method": _clean(row.get("FundingMethod")),
        "loi": (row.get("LOI") or "").strip().lower() == "yes",
        "updated": _day(row.get("LastUpdated")),
    }


def build_records(rows: list[dict], today: str | None = None, skips: list[dict] | None = None) -> list[dict]:
    """Open and forecasted calls, one per portal id, without any whose deadline has already passed. Open or
    forecasted rows left out for another reason are added to skips, when given, for the skipped-grants review."""
    today = today or datetime.now(timezone.utc).date().isoformat()
    seen: dict[str, dict] = {}
    for row in rows:
        if (row.get("Status") or "").strip().lower() not in OPEN_STATUSES:
            continue
        if not (row.get("PortalID") or "").strip():
            if skips is not None:
                skips.append({"source": "california", "id": "", "name": _clean(row.get("Title")), "state": "CA",
                              "funder": _clean(row.get("AgencyDept")), "reason": "no_portal_id",
                              "detail": "The portal row has no ID, so it can't be linked", "url": PORTAL})
            continue
        rec = normalize(row)
        if not rec["title"] or (rec["closes"] and rec["closes"] < today):
            if skips is not None:
                skips.append({"source": "california", "id": rec["id"], "name": rec["title"] or "(no title)", "state": "CA",
                              "funder": rec["agency"], "url": rec["url"],
                              "reason": "deadline_passed" if rec["title"] else "no_title",
                              "detail": f"Marked {row.get('Status', '').strip()} but the deadline was {rec['closes']}"
                              if rec["title"] else "The portal row has no title"})
            continue
        seen[rec["id"]] = rec
    return sorted(seen.values(), key=lambda r: r["id"])


def build(out: Path, source: Path | None = None, skipped_out: Path | None = None) -> int:
    rows = fetch_rows(source)
    skips: list[dict] = []
    records = build_records(rows, skips=skips)
    if len(records) < MIN_ROWS:
        raise RuntimeError(f"Only {len(records)} open calls in {len(rows)} rows; keeping the previous data file")
    payload = {
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "source": "California Grants Portal (grants.ca.gov), California State Library, public domain",
        "state": "CA",
        "count": len(records),
        "programs": records,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(out, "wt", encoding="utf-8") as fh:
        json.dump(payload, fh, separators=(",", ":"))
    open_ones = sum(1 for r in records if r["nonprofit_eligible"])
    print(f"wrote {len(records)} open California calls to {out}; {open_ones} open to nonprofits")
    if skipped_out is not None:
        from .fetch import write_skips
        write_skips(skipped_out, skips)
        print(f"wrote {len(skips)} left-out California rows to {skipped_out}")
    return len(records)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="data/california.json.gz", type=Path)
    ap.add_argument("--csv", type=Path, help="read a downloaded copy of the portal's CSV")
    ap.add_argument("--skipped", type=Path, help="also write the open rows left out, and why")
    args = ap.parse_args()
    build(args.out, args.csv, args.skipped)


if __name__ == "__main__":
    main()
