"""Florida state programs from the Catalog of State Financial Assistance (CSFA).

The CSFA, kept by the Florida Department of Financial Services under the Florida Single Audit Act,
lists every state program that gives money to local governments, nonprofits, and businesses.
It is a catalog of programs, not a list of open calls: each entry says who can apply and how,
and the agency announces its own application windows.

Run:  python -m grantmatch.florida --out data/florida.json.gz
"""
from __future__ import annotations

import argparse
import gzip
import html
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE = "https://apps.fldfs.com/fsaa/"
LABELS = [
    "CSFA Number", "State Project Title", "Agency", "Program", "Budget Entity", "Specific Appropriation",
    "Appropriation Category", "Related CFDA Code", "Authorization", "Objectives", "Types Of Assistance",
    "Applicant Type", "Restrictions", "Procedures", "Pre-Application Notice", "Application Procedures",
    "Award Procedures", "Deadlines", "Information Contact", "Web Address", "Associated Subjects",
]
EARMARK = re.compile(r"\b(earmark|direct allocation|direct appropriation award|proviso|specific appropriation to|line item)\b", re.I)
NAMED_RECIPIENT = re.compile(r"\bcontracts? (?:directly )?with (?:the )?[A-Z][a-z]+")
REVENUE_FOR = re.compile(r"\bto generate revenue for\b|\bvoluntary contributions?\b|\bannual use fees?\b", re.I)
NAMED_AWARD = re.compile(r"named sub-?recipient|budget proposal|non-?competitive|appropriated to", re.I)
NAMED_TITLE = re.compile(r"\b(inc|incorporated|foundation|association|university|college|society|corporation|ministries|league|"
                         r"club|fund|alliance|bar association|lodge)\b|^the ", re.I)
PLATE = re.compile(r"\b(license|specialty) plates?\b|\bplate (fees|revenues?|proceeds)\b", re.I)


def _title(s: str) -> str:
    small = {"and", "of", "for", "the", "in", "to", "a", "an", "on", "at", "by", "or"}
    words = s.lower().split()
    return " ".join(w if (i and w in small) else w[:1].upper() + w[1:] for i, w in enumerate(words))
PAUSE_SECONDS = 0.4

session = requests.Session()
session.headers.update({"User-Agent": "grant-matcher (github.com/RendellRich/grant-matcher)"})


def is_earmark(title: str, objectives: str, assistance: str, award: str, restrictions: str) -> bool:
    """True when the money is set aside for a specific, named recipient rather than open to applicants."""
    return (
        bool(EARMARK.search(award) or EARMARK.search(restrictions) or NAMED_RECIPIENT.search(award) or NAMED_AWARD.search(award))
        or assistance.lower().startswith("direct appropriation")
        or bool(PLATE.search(title) or PLATE.search(objectives) or REVENUE_FOR.search(objectives))
        or bool(NAMED_TITLE.search(title))
    )


def fiscal_year_code(today: datetime | None = None) -> tuple[str, str]:
    """Florida's fiscal year starts July 1. Returns the form code ('27') and label ('2026-2027')."""
    today = today or datetime.now()
    end = today.year + 1 if today.month >= 7 else today.year
    return str(end % 100), f"{end - 1}-{end}"


def list_ids(year_code: str) -> list[str]:
    form = {k: "" for k in ("agency_str", "subject_str", "apptype_str", "project_name_like_str",
                            "cfa_code_str", "project_name_str")}
    form["year_str"] = year_code
    r = session.post(BASE + "searchCatalogResults.aspx?SearchCat=1", data=form, timeout=120)
    r.raise_for_status()
    return sorted(set(re.findall(r"searchCatalogResultsDetail\.aspx\?id=(\d+)", r.text)))


def _text(fragment: str) -> str:
    t = re.sub(r"<br\s*/?>", "\n", fragment, flags=re.I)
    t = re.sub(r"<[^>]+>", "\n", t)
    t = html.unescape(t).replace("\xa0", " ")
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in t.splitlines()]
    return "\n".join(ln for ln in lines if ln)


def parse_detail(page: str) -> dict:
    text = _text(page)
    fields, current = {}, None
    for line in text.splitlines():
        label = line.rstrip(":").strip()
        if label in LABELS:
            current = label
            fields[current] = []
        elif line.startswith("Return To Top"):
            current = None
        elif current:
            fields[current].append(line)
    return {k: " ".join(v).strip() for k, v in fields.items()}


def normalize(pid: str, f: dict, year_label: str) -> dict:
    applicants = f.get("Applicant Type", "")
    award = f.get("Award Procedures", "")
    assistance = f.get("Types Of Assistance", "")
    title = f.get("State Project Title", "")
    earmark = is_earmark(title, f.get("Objectives", ""), assistance, award, f.get("Restrictions", ""))
    web = f.get("Web Address", "")
    return {
        "id": f"fl-{pid}",
        "csfa": f.get("CSFA Number", ""),
        "title": _title(title),
        "agency": f.get("Agency", ""),
        "objectives": f.get("Objectives", "")[:3000],
        "assistance": assistance,
        "applicant_types": applicants,
        "nonprofit_eligible": bool(re.search(r"non-?\s?profit", applicants, re.I)),
        "earmark": earmark,
        "restrictions": f.get("Restrictions", "")[:1500],
        "application": f.get("Application Procedures", "")[:1500],
        "award": award[:800],
        "deadlines": f.get("Deadlines", "")[:600],
        "contact": f.get("Information Contact", "")[:600],
        "web": web if web.startswith("http") else (f"https://{web}" if web and "." in web and " " not in web else ""),
        "subjects": f.get("Associated Subjects", ""),
        "fiscal_year": year_label,
        "url": f"{BASE}searchCatalogResultsDetail.aspx?id={pid}",
    }


def build(out: Path, limit: int | None = None) -> int:
    code, label = fiscal_year_code()
    ids = list_ids(code)
    if limit:
        ids = ids[:limit]
    print(f"{len(ids)} Florida state projects for FY {label}", flush=True)
    records, failures = [], 0
    for i, pid in enumerate(ids, 1):
        try:
            r = session.get(f"{BASE}searchCatalogResultsDetail.aspx?id={pid}", timeout=60)
            r.raise_for_status()
            records.append(normalize(pid, parse_detail(r.text), label))
        except Exception as exc:
            failures += 1
            print(f"skip {pid}: {exc}", file=sys.stderr)
        if i % 100 == 0:
            print(f"  {i}/{len(ids)}", flush=True)
        time.sleep(PAUSE_SECONDS)
    if not records or failures > max(10, len(ids) * 0.05):
        raise RuntimeError(f"Too many failures ({failures}); keeping the previous data file")
    payload = {
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "source": "Florida Catalog of State Financial Assistance (apps.fldfs.com/fsaa)",
        "fiscal_year": label,
        "count": len(records),
        "programs": records,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(out, "wt", encoding="utf-8") as fh:
        json.dump(payload, fh, separators=(",", ":"))
    open_ones = sum(1 for r in records if r["nonprofit_eligible"] and not r["earmark"])
    print(f"wrote {len(records)} programs to {out}; {open_ones} open to nonprofits and not earmarked")
    return len(records)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/florida.json.gz", type=Path)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    build(args.out, args.limit)


if __name__ == "__main__":
    main()
