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


def build(out: Path, limit: int | None = None, skipped_out: Path | None = None) -> int:
    hits = search_ids()
    if limit:
        hits = hits[:limit]
    print(f"{len(hits)} opportunities to fetch", flush=True)
    records, failures = [], 0
    failed: list[dict] = []
    for i, hit in enumerate(hits, 1):
        try:
            detail = _post("fetchOpportunity", {"opportunityId": int(hit["id"])})
            records.append(normalize(hit, detail))
        except Exception as exc:  # one bad record should not sink the nightly refresh
            failures += 1
            failed.append(hit)
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
    if skipped_out is not None and not limit:
        try:  # the review list must never stop the data refresh
            rows = skipped({r["id"] for r in records}, failed)
            write_skips(skipped_out, rows)
            print(f"wrote {len(rows)} left-out opportunities to {skipped_out}")
        except Exception as exc:
            write_skips(skipped_out, [], error=str(exc))
            print(f"could not list the left-out opportunities: {exc}", file=sys.stderr)
    return len(records)


# Who Grants.gov says can apply, by code (search2's eligibilities).
ELIGIBILITY = {
    "00": "State governments", "01": "County governments", "02": "City or township governments",
    "04": "Special district governments", "05": "Independent school districts",
    "06": "Public and state colleges and universities", "07": "Federally recognized tribal governments",
    "08": "Public and Indian housing authorities", "11": "Tribal organizations", "12": "501(c)(3) nonprofits",
    "13": "Nonprofits without 501(c)(3) status", "20": "Private colleges and universities", "21": "Individuals",
    "22": "For-profit organizations", "23": "Small businesses", "25": "Others (see the notice)", "99": "Unrestricted",
}


NONPROFIT_WORDS = re.compile(r"non-?profit|\bNGOs?\b|non-?governmental organi[sz]ation|501\s*\(c\)|community[- ]based organi[sz]ation|faith-based", re.I)


NOT_NONPROFIT = re.compile(r"\b(?:no|not|nor|ineligible|excluded?|cannot|can't)\b[^.]{0,60}(?:non-?profit|NGO)", re.I)


def skipped(kept: set[str], failed: list[dict] | None = None) -> list[dict]:
    """Open and forecasted opportunities that are not in the data file, and why: Grants.gov doesn't list
    nonprofits among who can apply, or the opportunity's details couldn't be read this run."""
    hits, start = [], 0
    while True:
        data = _post("search2", {"oppStatuses": "forecasted|posted", "rows": PAGE_SIZE, "startRecordNum": start})
        page = data.get("oppHits", [])
        hits.extend(page)
        start += len(page)
        if not page or start >= data.get("hitCount", 0):
            break
        time.sleep(PAUSE_SECONDS)
    failed_ids = {str(h.get("id")) for h in failed or []}
    rows = []
    for hit in hits:
        oid = str(hit["id"])
        if oid in kept:
            continue
        row = {
            "source": "federal", "id": oid, "name": clean_text(hit.get("title")), "funder": clean_text(hit.get("agency")),
            "state": "", "url": f"https://www.grants.gov/search-results-detail/{oid}",
            "status": hit.get("oppStatus", ""), "close_date": _date(hit.get("closeDate")),
        }
        if oid in failed_ids:
            rows.append({**row, "reason": "read_failed", "detail": "Grants.gov did not return its details this run"})
            continue
        try:
            detail = _post("fetchOpportunity", {"opportunityId": int(oid)})
            block = (detail.get("forecast") if hit.get("oppStatus") == "forecasted" else detail.get("synopsis")) \
                or detail.get("synopsis") or detail.get("forecast") or {}
            codes = [a["id"] for a in block.get("applicantTypes") or []]
            who = "; ".join(ELIGIBILITY.get(c, c) for c in codes) or "not stated"
            note = clean_text(block.get("applicantEligibilityDesc"))[:400]
            # The codes leave nonprofits out, but the notes sometimes let them in ("individuals and NGOs can apply").
            reason = ("notes_mention_nonprofits" if NONPROFIT_WORDS.search(note) and not NOT_NONPROFIT.search(note)
                      else "not_nonprofit_eligible")
            rows.append({**row, "reason": reason, "detail": f"Who can apply: {who}." + (f" Notes: {note}" if note else "")})
        except Exception as exc:  # the list is a review aid; one unreadable record still gets a row
            rows.append({**row, "reason": "not_nonprofit_eligible", "detail": f"Eligibility could not be read ({exc})"})
        time.sleep(PAUSE_SECONDS)
    return rows


def write_skips(path: Path, rows: list[dict], error: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"fetched_at": datetime.now(timezone.utc).isoformat(timespec="minutes"), "rows": rows}
    if error:
        payload["error"] = error
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump(payload, f, separators=(",", ":"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="data/opportunities.json.gz", type=Path)
    parser.add_argument("--limit", type=int, default=None, help="fetch only the first N (for testing)")
    parser.add_argument("--skipped", type=Path, default=None, help="also write the opportunities left out, and why")
    args = parser.parse_args()
    build(args.out, args.limit, args.skipped)


if __name__ == "__main__":
    main()
