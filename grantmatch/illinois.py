"""Illinois state grants from the Catalog of State Financial Assistance's list of open funding notices.

Under the Grant Accountability and Transparency Act (GATA), every Illinois state agency posts its Notices of
Funding Opportunity (NOFOs) to one public list kept by the Governor's Office of Management and Budget:
omb.illinois.gov/PUBLIC/GATA/CSFA/OpportunityList.aspx. Each row has the title, agency, application window
and award range. Agencies that use the state's grants system (AmpliFund, marked GMS) link to a public page
with the description, who may apply, award size and match; the others link to the catalog's own notice and
program pages, which carry the same facts. Like California's portal these are open calls with real windows.

Records use the same fields as California's (grantmatch/california.py), so the same scorer reads them.

Run:  python -m grantmatch.illinois --out data/illinois.json.gz [--skipped build/skipped-illinois.json.gz]
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
from urllib.parse import parse_qs, urljoin, urlparse

import requests

BASE = "https://omb.illinois.gov/PUBLIC/GATA/CSFA/"
LIST = BASE + "OpportunityList.aspx"
MIN_ROWS = 20  # fewer than this means the list page changed, not that Illinois stopped granting
PAUSE = 0.3  # seconds between pages, to stay polite

session = requests.Session()
session.headers.update({"User-Agent": "grant-matcher (github.com/RendellRich/grant-matcher)"})

NONPROFIT = re.compile(r"non-?\s?profit|not-for-profit|community[- ]based organi[sz]ation|community action agenc|501\s*\(c\)", re.I)
# Filler the state puts in an eligibility box when it says nothing there
PLACEHOLDER = re.compile(r"^\W*(?:n/?a|none|see (?:the )?(?:nofo|notice|application manual)\b[^.]*)?\W*$", re.I)
NO_NONPROFIT = re.compile(r"\b(?:no|not|nor|ineligible|cannot)\b[^.]{0,50}(?:non-?\s?profit|not-for-profit)"
    r"|(?:non-?\s?profit|not-for-profit)s?\b[^.;]{0,25}\b(?:not|ineligible|cannot)\b", re.I)
AMPLIFUND_LABELS = {
    "Description", "Awarding Agency Name", "Agency Contact Name", "Agency Contact Email", "Program",
    "Fund Activity Categories", "Departments", "Opportunity Manager", "Posted Date", "Announcement Type",
    "Funding Opportunity Number", "Public Link", "Is Published", "Funding Information", "Opportunity Funding",
    "Funding Sources", "Funding Source Description", "Funding Restrictions", "Award Information", "Award Ceiling",
    "Award Floor", "Award Type", "Indirect Costs Allowed", "Matching Requirement", "Submission Information",
    "Submission Timeline Type", "Submission Open Date", "Submission Close Date", "Other Submission Requirements",
    "Eligibility Information", "Eligibility Type", "Eligible Applicants", "Applicant Eligibility Information",
    "Question Submission Information", "Attachments", "CSFA Number", "CSFA Popular Name", "Title",
    "Evaluation & Scoring", "Opportunity Information", "Application Review Start Date / Pre-Qualification Deadline",
    "Question Submission Open Date", "Question Submission Close Date", "Question Submission Email Address",
    "Question Submission Additional Information", "Additional Information", "Contact Information",
    "Agency Contact Phone", "Category Explanation", "Subjects", "Additional Users", "Award Start Date",
    "Award End Date", "Award Announcement Date", "Expected Number of Awards", "Indirect Cost Description",
    "Restrictions on Indirect Costs", "Technical Assistance Session", "Beneficiary Eligibility Information",
    "Credentials Documentation Eligibility Information", "Award Administration Information", "State Award Notices",
    "Administrative and National Policy Requirements", "Reporting", "State Awarding Agency Contacts",
    "Print", "Help", "Download", "Save", "Apply", "Log In", "Opportunity Details",
}
NONPROFIT_TYPES = re.compile(r"non\s?profit|not-for-profit", re.I)  # the "Eligible Applicants" categories
CSFA_LABELS = {
    "Awarding Agency Name", "Agency Contact", "Announcement Type", "Type of Assistance Instrument",
    "Agency Opportunity Number", "Agency Funding Program", "CSFA_Number", "CSFA Popular Name",
    "Anticipated Number of Awards", "Estimated Total Program Funding", "Single Award Range", "Source of Funding",
    "Cost Sharing or Matching Requirements", "Indirect Costs Allowed", "Restrictions on Indirect Costs",
    "Posted Date", "Application Date Range", "Grant Application Link", "Technical Assistance Session", "Attachments",
    # program page
    "STATE AGENCY INFORMATION", "Agency Name", "PROGRAM INFORMATION", "Short Description", "Federal Authorization",
    "Illinois Statue Authorization", "Illinois Administrative Rules Authorization", "Objective", "Prime Recipient",
    "UGA Program Terms", "Eligible Applicants", "Applicant Eligibility", "Beneficiary Eligibility",
    "Types of Assistance", "Subject / Service Area", "Credentials / Documentation", "Preapplication Coordination",
    "Application Procedures", "Award Procedures", "Deadlines", "Range of Approval or Disapproval Time", "Appeals",
    "Renewals", "Program Accomplishments", "Regulations, Guidelines and Literature", "Website Address",
}


def _clean(s: str | None) -> str:
    return re.sub(r"\s+", " ", html.unescape(s or "").replace("\xa0", " ")).strip()


def _lines(page: str) -> list[str]:
    page = re.sub(r"<(script|style)\b.*?</\1>", " ", page, flags=re.S | re.I)
    text = html.unescape(re.sub(r"<[^>]+>", "\n", page)).replace("\xa0", " ")
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


def fields(page: str, labels: set[str]) -> dict[str, str]:
    """Label: value pairs from a detail page laid out as a label line followed by its value lines."""
    out: dict[str, list[str]] = {}
    current = None
    for ln in _lines(page):
        if ln in labels:
            current = ln
            out.setdefault(current, [])
        elif current:
            out[current].append(ln)
    return {k: _clean(" ".join(v)) for k, v in out.items() if v}


def _day(s: str) -> str | None:
    try:
        return datetime.strptime(s.strip()[:10], "%m/%d/%Y").date().isoformat()
    except ValueError:
        return None


def list_rows(page: str) -> list[dict]:
    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", page, re.S | re.I):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S | re.I)
        if len(cells) < 4:
            continue
        link = re.search(r"href=['\"]([^'\"]+)['\"]", cells[0])
        if not link:
            continue
        href = html.unescape(link.group(1))
        if href.startswith("GMS.aspx"):
            detail = parse_qs(urlparse(href).query).get("url", [""])[0]
            kind = "gms"
        else:
            detail, kind = urljoin(BASE, href), "csfa"
        dates = _clean(re.sub(r"<[^>]+>", " ", cells[2]))
        start, _, end = dates.partition(" - ")
        rows.append({
            "title": _clean(re.sub(r"<[^>]+>", " ", cells[0])).removeprefix("GMS").strip(),
            "agency": _clean(re.sub(r"<[^>]+>", " ", cells[1])),
            "opens": _day(start), "closes": _day(end), "no_end": "no end date" in end.lower(),
            "award_range": _clean(re.sub(r"<[^>]+>", " ", cells[3])),
            "detail": detail, "kind": kind,
        })
    return rows


def _get(url: str) -> str:
    r = session.get(url, timeout=60)
    r.raise_for_status()
    return r.text


def details(row: dict) -> dict:
    """The facts on the row's detail page(s), as one flat dict of labels."""
    if row["kind"] == "gms":
        return fields(_get(row["detail"]), AMPLIFUND_LABELS)
    page = _get(row["detail"])
    out = fields(page, CSFA_LABELS)
    prog = re.search(r"href=['\"](Program\.aspx\?csfa=\d+)['\"]", page)
    if prog:
        time.sleep(PAUSE)
        out = {**fields(_get(urljoin(BASE, prog.group(1))), CSFA_LABELS), **out}
        out["_program_url"] = urljoin(BASE, prog.group(1))
    return out


def _money(s: str) -> str:
    """"$1,800,000.00" and "2120450.00" both as "$2,120,450"; ranges kept; zeros and "Not Applicable" dropped."""
    s = _clean(s)
    if not s or s in ("$0.00", "0.00", "Not Applicable", "$0 - $0"):
        return ""
    def one(m: re.Match) -> str:
        n = float(m.group(0).replace("$", "").replace(",", ""))
        return f"${n:,.0f}"
    return re.sub(r"\$?\d[\d,]*(?:\.\d+)?", one, s)


def normalize(row: dict, f: dict) -> dict:
    nofo = re.search(r"(?:nofo=|Details/)([\w-]+)", row["detail"])
    who = f.get("Eligible Applicants", "").rstrip(";, ")
    who_more = f.get("Applicant Eligibility Information") or f.get("Applicant Eligibility", "")
    if PLACEHOLDER.match(who_more):
        who_more = ""
    if who and not re.search(r"\bothers?\b", who, re.I):
        # The state's own categories decide; "public and non-profit universities" stays an education grant.
        nonprofit = bool(NONPROFIT_TYPES.search(who))
    else:  # "Others", or no categories: read the eligibility text and the description
        text = f"{who_more} {f.get('Description', '')}"
        nonprofit = bool(NONPROFIT.search(text)) and not NO_NONPROFIT.search(text)
        if not nonprofit and not who_more and not NO_NONPROFIT.search(text):
            # Nothing says who else may apply: keep it, and say so on the card
            nonprofit = True
            who = f"{who}. Whether nonprofits can apply isn't stated; read the notice" if who else \
                "Not stated on the state's listing; read the notice"
    objectives = " ".join(t for t in (f.get("Description") or f.get("Short Description", ""), f.get("Objective", "")) if t)
    match = _clean(f.get("Matching Requirement") or f.get("Cost Sharing or Matching Requirements", ""))
    match = "" if match.lower() in ("", "no", "none", "n/a") else ("Required" if match.lower() == "yes" else match)
    floor, ceiling = _money(f.get("Award Floor", "")), _money(f.get("Award Ceiling", ""))
    award = [f"{label}: {value}." for label, value in (
        ("Total available", _money(f.get("Opportunity Funding") or f.get("Estimated Total Program Funding", ""))),
        ("Award size", f"{floor} to {ceiling}" if floor and ceiling else _money(f.get("Single Award Range", "")) or _money(row["award_range"])),
        ("Number of awards", next((n for n in (f.get("Expected Number of Awards"), f.get("Anticipated Number of Awards")) if n and n != "0"), "")),
        ("Funding", f.get("Funding Source Description", "")),
    ) if value]
    contact = ", ".join(t for t in (f.get("Agency Contact Name") or f.get("Agency Contact", ""), f.get("Agency Contact Email", "")) if t)
    how = f.get("Application Procedures") or f.get("Other Submission Requirements") or ""
    closes = row["closes"]
    return {
        "id": f"il-{nofo.group(1) if nofo else re.sub(r'[^a-z0-9]+', '-', row['title'].lower())[:40]}",
        "csfa": "",
        "number": f.get("CSFA Number") or f.get("CSFA_Number", ""),
        "state": "IL",
        "title": row["title"],
        "agency": f.get("Awarding Agency Name") or row["agency"],
        "objectives": _clean(objectives)[:3000],
        "assistance": f.get("Type of Assistance Instrument") or f.get("Award Type") or "Grant",
        "applicant_types": _clean(". ".join(t for t in (who, who_more) if t))[:1200],
        "nonprofit_eligible": nonprofit,
        "earmark": False,
        "restrictions": _clean(f.get("Funding Restrictions", ""))[:1500],
        "application": _clean(how)[:1200] or "Apply through the notice's page; Illinois requires GATA pre-qualification first.",
        "award": " ".join(award)[:800],
        "deadlines": "Ongoing" if row["no_end"] else (closes or ""),
        "contact": contact[:600],
        "web": f.get("Website Address", ""),
        "subjects": f.get("Fund Activity Categories") or f.get("Subject / Service Area", ""),
        "fiscal_year": "",
        "url": row["detail"],
        "status": "active",
        "opens": row["opens"],
        "closes": closes,
        "match": match,
        "loan": "loan" in (f.get("Type of Assistance Instrument") or "").lower(),
        "funding_method": "",
        "loi": False,
        "updated": _day(f.get("Posted Date", "")) or row["opens"],
    }


def build_records(rows: list[dict], today: str | None = None, skips: list[dict] | None = None,
                  fetch=details) -> list[dict]:
    """Open calls (window not yet closed), one per notice. Rows dropped are added to skips, when given."""
    today = today or date.today().isoformat()
    out: dict[str, dict] = {}
    for row in rows:
        if row["closes"] and row["closes"] < today:
            if skips is not None:
                skips.append({"source": "illinois", "id": row["detail"], "name": row["title"], "state": "IL",
                              "funder": row["agency"], "reason": "deadline_passed", "url": row["detail"],
                              "detail": f"Listed, but its window closed {row['closes']}"})
            continue
        try:
            f = fetch(row)
        except Exception as exc:  # one unreadable notice shouldn't sink the refresh
            print(f"skip {row['title']}: {exc}", file=sys.stderr)
            if skips is not None:
                skips.append({"source": "illinois", "id": row["detail"], "name": row["title"], "state": "IL",
                              "funder": row["agency"], "reason": "read_failed", "url": row["detail"],
                              "detail": f"The notice's page couldn't be read ({exc})"[:300]})
            continue
        rec = normalize(row, f)
        out[rec["id"]] = rec
        time.sleep(PAUSE)
    return sorted(out.values(), key=lambda r: r["id"])


def build(out: Path, skipped_out: Path | None = None) -> int:
    rows = list_rows(_get(LIST))
    if len(rows) < MIN_ROWS:
        raise RuntimeError(f"Only {len(rows)} rows on the Illinois list; keeping the previous data file")
    skips: list[dict] = []
    records = build_records(rows, skips=skips)
    if len(records) < MIN_ROWS // 2:
        raise RuntimeError(f"Only {len(records)} notices read; keeping the previous data file")
    payload = {
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "source": "Illinois Catalog of State Financial Assistance, Notices of Funding Opportunity (omb.illinois.gov)",
        "state": "IL", "count": len(records), "programs": records,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(out, "wt", encoding="utf-8") as fh:
        json.dump(payload, fh, separators=(",", ":"))
    print(f"wrote {len(records)} open Illinois notices to {out}; {sum(r['nonprofit_eligible'] for r in records)} open to nonprofits")
    if skipped_out is not None:
        from .fetch import write_skips
        write_skips(skipped_out, skips)
    return len(records)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="data/illinois.json.gz", type=Path)
    ap.add_argument("--skipped", type=Path)
    args = ap.parse_args()
    build(args.out, args.skipped)


if __name__ == "__main__":
    main()
