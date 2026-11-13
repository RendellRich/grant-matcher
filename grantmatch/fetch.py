"""Pull open and forecasted federal opportunities that nonprofits can apply for.

Uses the public Grants.gov REST API (search2 and fetchOpportunity), which needs no key.
Run:  python -m grantmatch.fetch --out data/opportunities.json.gz
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

API = "https://api.grants.gov/v1/api"
# 12 = 501(c)(3) nonprofits, 13 = nonprofits without 501(c)(3), 25 = others (see text), 99 = unrestricted
NONPROFIT_ELIGIBILITIES = "12|13|25|99"
PAGE_SIZE = 100
PAUSE_SECONDS = 0.25  # stay polite; the terms allow Grants.gov to limit heavy use

session = requests.Session()
session.headers.update({"Content-Type": "application/json", "User-Agent": "grant-matcher (github.com/RendellRich/grant-matcher)"})


def _post(endpoint: str, body: dict, attempts: int = 4) -> dict:
    for attempt in range(attempts):
        try:
            r = session.post(f"{API}/{endpoint}", json=body, timeout=60)
            if r.status_code == 200:
                payload = r.json()
                if payload.get("errorcode", 0) == 0:
                    return payload["data"]
            err = f"HTTP {r.status_code}"
        except requests.RequestException as exc:
            err = str(exc)
        time.sleep(2 ** attempt)
    raise RuntimeError(f"{endpoint} failed after {attempts} attempts: {err}")


def search_ids() -> list[dict]:
    hits, start = [], 0
    while True:
        data = _post("search2", {
            "oppStatuses": "forecasted|posted",
            "eligibilities": NONPROFIT_ELIGIBILITIES,
            "rows": PAGE_SIZE,
            "startRecordNum": start,
        })
        page = data.get("oppHits", [])
        hits.extend(page)
        start += len(page)
        if not page or start >= data.get("hitCount", 0):
            return hits
        time.sleep(PAUSE_SECONDS)


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    text = re.sub(r"<[^>]+>", " ", value)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _num(value) -> float | None:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def _date(value: str | None) -> str | None:
    """'Dec 16, 2026 12:00:00 AM EST' or '12/16/2026' -> '2026-12-16'."""
    if not value:
        return None
    for fmt in ("%b %d, %Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(value[:12].strip().rstrip(","), fmt).date().isoformat()
        except ValueError:
            continue
    m = re.match(r"([A-Z][a-z]{2} \d{1,2}, \d{4})", value)
    if m:
        return datetime.strptime(m.group(1), "%b %d, %Y").date().isoformat()
    return None


def normalize(hit: dict, detail: dict) -> dict:
    status = hit.get("oppStatus", "")
    block = detail.get("forecast") if status == "forecasted" else detail.get("synopsis")
    block = block or detail.get("synopsis") or detail.get("forecast") or {}
    if status == "forecasted":
        close = _date(block.get("estApplicationResponseDate")) or _date(hit.get("closeDate"))
        description = block.get("forecastDesc")
    else:
        close = _date(block.get("responseDate")) or _date(hit.get("closeDate"))
        description = block.get("synopsisDesc")
    return {
        "id": str(hit["id"]),
        "number": hit.get("number", ""),
        "title": clean_text(hit.get("title") or detail.get("opportunityTitle")),
        "agency_code": hit.get("agencyCode", ""),
        "agency": clean_text(hit.get("agency") or block.get("agencyName") or ""),
        "status": status,
        "open_date": _date(hit.get("openDate")),
        "close_date": close,
        "award_ceiling": _num(block.get("awardCeiling")),
        "award_floor": _num(block.get("awardFloor")),
        "estimated_funding": _num(block.get("estimatedFunding")),
        "number_of_awards": _num(block.get("numberOfAwards")),
        "cost_sharing": bool(block.get("costSharing")),
        "applicant_types": [a["id"] for a in block.get("applicantTypes") or []],
        "categories": [c["id"] for c in block.get("fundingActivityCategories") or []],
        "category_labels": [c["description"] for c in block.get("fundingActivityCategories") or []],
        "instruments": [i["id"] for i in block.get("fundingInstruments") or []],
        "aln": [c.get("cfdaNumber") for c in detail.get("cfdas") or [] if c.get("cfdaNumber")],
        "description": clean_text(description)[:6000],
        "eligibility_text": clean_text(block.get("applicantEligibilityDesc"))[:2000],
        "url": f"https://www.grants.gov/search-results-detail/{hit['id']}",
    }


def build(out: Path, limit: int | None = None) -> int:
    hits = search_ids()
    if limit:
        hits = hits[:limit]
    print(f"{len(hits)} opportunities to fetch", flush=True)
    records, failures = [], 0
    for i, hit in enumerate(hits, 1):
        try:
            detail = _post("fetchOpportunity", {"opportunityId": int(hit["id"])})
            records.append(normalize(hit, detail))
        except Exception as exc:  # one bad record should not sink the nightly refresh
            failures += 1
            print(f"skip {hit.get('id')}: {exc}", file=sys.stderr)
        if i % 100 == 0:
            print(f"  {i}/{len(hits)}", flush=True)
        time.sleep(PAUSE_SECONDS)
    if failures > max(10, len(hits) * 0.05):
        raise RuntimeError(f"Too many failures ({failures}); keeping the previous data file")
    payload = {
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "source": "Grants.gov API (search2, fetchOpportunity)",
        "count": len(records),
        "opportunities": records,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(out, "wt", encoding="utf-8") as f:
        json.dump(payload, f, separators=(",", ":"))
    print(f"wrote {len(records)} records to {out} ({failures} skipped)")
    return len(records)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="data/opportunities.json.gz", type=Path)
    parser.add_argument("--limit", type=int, default=None, help="fetch only the first N (for testing)")
    args = parser.parse_args()
    build(args.out, args.limit)


if __name__ == "__main__":
    main()
