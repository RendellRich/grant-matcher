"""Private foundations from IRS Form 990-PF e-file data.

Every private foundation files a 990-PF each year. The e-filed returns are public XML that the IRS
publishes in monthly batches. Each return lists the grants the foundation paid (recipient, city,
state, purpose, amount) and, in its supplementary information, whether it accepts applications and
how to apply. That is the most direct public record of who a foundation actually funds.

Run:  python -m grantmatch.foundations --years 2025 --out data/foundations
Writes one gzip JSON per state (by the state the foundation is in or gives to) plus all.json.gz.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import io
import json
import re
import statistics
import sys
import time
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

import requests

from .coverage import tally
from .history import History, default_years

try:  # some IRS batches use Deflate64, which the standard zipfile cannot read
    import zipfile_deflate64  # noqa: F401  (patches zipfile on import)
except ImportError:
    pass

XML_ROOT = "https://apps.irs.gov/pub/epostcard/990/xml/{year}/"
MAX_GRANTS_KEPT = 40  # per foundation, largest first, for display and matching
session = requests.Session()
session.headers.update({"User-Agent": "grant-matcher (github.com/RendellRich/grant-matcher)"})


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _find(el, *path):
    """First descendant matching a local-name path, ignoring namespaces."""
    nodes = [el]
    for name in path:
        nxt = []
        for n in nodes:
            nxt.extend(c for c in n.iter() if _local(c.tag) == name and c is not n)
        if not nxt:
            return None
        nodes = nxt
    return nodes[0]


def _text(el, *path) -> str:
    node = _find(el, *path) if path else el
    if node is None:
        return ""
    return re.sub(r"\s+", " ", " ".join(t for t in node.itertext())).strip()


def _num(s: str) -> float | None:
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def _name(el) -> str:
    for p in (("RecipientBusinessName", "BusinessNameLine1Txt"), ("RecipientBusinessName", "BusinessNameLine1"),
              ("RecipientPersonNm",), ("RecipientNameBusiness", "BusinessNameLine1")):
        t = _text(el, *p)
        if t:
            return t
    return ""


def parse_return(xml: bytes) -> dict | None:
    root = ET.fromstring(xml)
    header = _find(root, "ReturnHeader")
    pf = _find(root, "IRS990PF")
    if header is None or pf is None:
        return None
    filer = _find(header, "Filer")
    rec = {
        "ein": _text(filer, "EIN"),
        "name": _text(filer, "BusinessName", "BusinessNameLine1Txt") or _text(filer, "BusinessNameLine1Txt"),
        "city": _text(filer, "CityNm"),
        "state": _text(filer, "StateAbbreviationCd"),
        "zip": _text(filer, "ZIPCd")[:5],
        "tax_year": _text(header, "TaxYr"),
        "assets": _num(_text(pf, "FMVAssetsEOYAmt")),
        "grants_total": _num(_text(pf, "ContriPaidRevAndExpnssAmt")),
        "website": _text(pf, "WebsiteAddressTxt"),
        "preselected_only": _text(pf, "OnlyContriToPreselectedInd").upper() in ("X", "TRUE", "1"),
    }
    app = _find(pf, "ApplicationSubmissionInfoGrp")
    if app is not None:
        rec["apply"] = {
            "contact": _text(app, "RecipientPersonNm") or _text(app, "RecipientBusinessName", "BusinessNameLine1Txt"),
            "phone": _text(app, "RecipientPhoneNum"),
            "email": _text(app, "RecipientEmailAddressTxt"),
            "address": " ".join(filter(None, [_text(app, "AddressLine1Txt"), _text(app, "CityNm"),
                                              _text(app, "StateAbbreviationCd"), _text(app, "ZIPCd")[:5]])),
            "materials": _text(app, "FormAndInfoAndMaterialsTxt")[:600],
            "deadlines": _text(app, "SubmissionDeadlinesTxt")[:300],
            "restrictions": _text(app, "RestrictionsOnAwardsTxt")[:600],
        }
    grants = []
    for g in pf.iter():
        if _local(g.tag) != "GrantOrContributionPdDurYrGrp":
            continue
        amt = _num(_text(g, "Amt"))
        if not amt or amt <= 0:
            continue
        grants.append({
            "to": _name(g)[:120],
            "city": _text(g, "CityNm")[:40],
            "state": _text(g, "StateAbbreviationCd"),
            "purpose": _text(g, "GrantOrContributionPurposeTxt")[:200],
            "amount": amt,
        })
    rec["grants"] = grants
    return rec


def summarize(rec: dict) -> dict:
    grants = rec.pop("grants")
    amounts = [g["amount"] for g in grants]
    states = Counter(g["state"] for g in grants if g["state"])
    purposes = Counter(g["purpose"].lower() for g in grants if g["purpose"])
    rec.update({
        "grant_count": len(grants),
        "grant_median": statistics.median(amounts) if amounts else None,
        "grant_min": min(amounts) if amounts else None,
        "grant_max": max(amounts) if amounts else None,
        "recipient_states": dict(states.most_common(12)),
        "top_purposes": [p for p, _ in purposes.most_common(25)],
        "sample_grants": sorted(grants, key=lambda g: -g["amount"])[:MAX_GRANTS_KEPT],
        "url": f"https://projects.propublica.org/nonprofits/organizations/{rec['ein']}",
    })
    return rec


def left_out(rec: dict) -> str:
    """Why a return isn't listed, or "" when it is. Listed foundations are ones a small nonprofit could
    approach: they pay grants to organizations and do not say they only fund preselected charities, or they
    publish how to apply."""
    if not rec["grants"]:
        return "no_grants"
    if rec["preselected_only"] and not rec.get("apply"):
        return "preselected"
    return ""


def _keep(rec: dict) -> bool:
    return not left_out(rec)


def note(seen: dict[str, dict], rec: dict, year: int, why: str) -> None:
    """Remember the outcome of a foundation's latest return, listed or not, for the coverage report."""
    prev = seen.get(rec["ein"])
    if prev is None or (year, rec["tax_year"]) >= (prev["filed"], prev["tax_year"]):
        seen[rec["ein"]] = {"state": rec["state"], "filed": year, "tax_year": rec["tax_year"], "why": why,
                            "name": rec.get("name", ""), "city": rec.get("city", ""), "assets": rec.get("assets"),
                            "website": rec.get("website", ""), "grant_count": len(rec.get("grants") or [])}


ZIP_LETTERS = "ABCDEFGH"  # a month's returns come in up to a few zips: 11A, 11B, ...


def zip_name(batch: str) -> str:
    """The zip for an index batch id. A few 2024 ids end in a lowercase letter (04a); the files never do."""
    return batch.upper()


def find_zips(year: int) -> list[str]:
    """A year's batch zips, as the IRS server has them."""
    found = []
    for month in range(1, 13):
        for letter in ZIP_LETTERS:
            name = f"{year}_TEOS_XML_{month:02d}{letter}"
            r = session.head(XML_ROOT.format(year=year) + f"{name}.zip", allow_redirects=False, timeout=60)
            if r.status_code != 200:  # a missing file redirects to the IRS 404 page
                break
            found.append(name)
    return found


def year_batches(year: int, wanted) -> dict[str, set[str]] | None:
    """The returns to read from one filing year, as {zip name: object ids}; wanted(row) picks index rows.
    None when the year has no index yet.

    The index can't be trusted to say which zip holds a return: indexes before 2024 have no batch column,
    and later ones file a month's second zip (05B) under the first (05A). So every zip of the year is read,
    keeping any return the index lists for the year."""
    r = session.get(XML_ROOT.format(year=year) + f"index_{year}.csv", timeout=300)
    if r.status_code != 200:
        return None
    reader = csv.DictReader(io.StringIO(r.content.decode("latin-1")))
    rows = [row for row in reader if wanted(row)]
    if not rows:
        return {}
    named = {zip_name(row["XML_BATCH_ID"]) for row in rows if row.get("XML_BATCH_ID")}
    zips = sorted(set(find_zips(year)) | named)
    if not zips:
        raise RuntimeError(f"{year}: the index lists {len(rows)} returns but no batch zips were found")
    ids = {row["OBJECT_ID"] for row in rows}
    return {z: ids for z in zips}


def batch_ids(year: int) -> dict[str, set[str]] | None:
    return year_batches(year, lambda row: row["RETURN_TYPE"] == "990PF")


def process_batch(year: int, batch: str, ids: set[str], tmp: Path, hist: History | None = None,
                  seen: dict[str, dict] | None = None) -> list[dict]:
    path = tmp / f"{batch}.zip"
    with session.get(XML_ROOT.format(year=year) + f"{batch}.zip", stream=True, timeout=600) as r:
        r.raise_for_status()
        with open(path, "wb") as fh:
            for chunk in r.iter_content(1 << 20):
                fh.write(chunk)
    out = []
    try:
        with zipfile.ZipFile(path) as z:
            for name in z.namelist():
                oid = name.rsplit("/", 1)[-1].split("_")[0]
                if oid not in ids:
                    continue
                try:
                    rec = parse_return(z.read(name))
                except ET.ParseError:
                    continue
                if rec and hist is not None:
                    hist.add(rec["ein"], rec["tax_year"], rec["grants"])  # every year's giving, kept or not
                if not rec:
                    continue
                why = left_out(rec)
                if seen is not None:
                    note(seen, rec, year, why)
                if not why:
                    out.append(summarize(rec))
    finally:
        path.unlink(missing_ok=True)
    return out


CURRENT_FILING_YEARS = 2


def current(latest: dict[str, dict], filed: dict[str, int], newest: int) -> dict[str, dict]:
    """Only foundations with a return filed in the newest CURRENT_FILING_YEARS filing years. Older years
    are read for history; a foundation that hasn't filed since may have closed, so it isn't listed."""
    return {ein: rec for ein, rec in latest.items() if filed.get(ein, 0) > newest - CURRENT_FILING_YEARS}


def write_left_out(path: Path, seen: dict[str, dict], listed: set[str], newest: int, source: str) -> int:
    """Every return read that isn't listed, with why, one JSON line each, for the skipped-grants review
    (grantmatch/skipped.py). The .jsonl name keeps it out of the per-state *.json.gz files."""
    n = 0
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        for ein, s in seen.items():
            if ein in listed:
                continue
            why = "no_recent_return" if s["filed"] <= newest - CURRENT_FILING_YEARS else (s["why"] or "older_return_listed")
            fh.write(json.dumps({"source": source, "id": ein, "name": s.get("name", ""), "state": s.get("state", ""),
                                 "city": s.get("city", ""), "reason": why, "tax_year": s.get("tax_year", ""),
                                 "filed": s["filed"], "assets": s.get("assets"), "website": s.get("website", ""),
                                 "url": f"https://projects.propublica.org/nonprofits/organizations/{ein}"},
                                separators=(",", ":")) + "\n")
            n += 1
    return n


def build(years: list[int], out_dir: Path, only_batches: list[str] | None = None) -> None:
    tmp = out_dir / "_tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    latest: dict[str, dict] = {}
    hist = History()
    filed: dict[str, int] = {}  # the latest filing year each foundation's return appeared in
    seen: dict[str, dict] = {}  # every return read, listed or not, for the coverage report
    failed: list[tuple[int, str]] = []
    for year in years:
        try:
            batches = batch_ids(year)
        except Exception as exc:  # an index we can't read, or an old year whose zips can't be found
            failed.append((year, "index"))
            print(f"{year}: FAILED {exc}", file=sys.stderr, flush=True)
            continue
        if batches is None:
            print(f"{year}: no index yet; skipping", flush=True)
            continue
        for batch, ids in sorted(batches.items()):
            if only_batches and batch not in only_batches:
                continue
            t0 = time.time()
            try:
                recs = process_batch(year, batch, ids, tmp, hist, seen)
            except Exception as exc:
                failed.append((year, batch))
                print(f"{batch}: FAILED {exc}", file=sys.stderr, flush=True)
                continue
            for rec in recs:  # keep the most recent return per foundation
                prev = latest.get(rec["ein"])
                if prev is None or rec["tax_year"] >= prev["tax_year"]:
                    latest[rec["ein"]] = rec
                filed[rec["ein"]] = max(filed.get(rec["ein"], year), year)
            print(f"{batch}: kept {len(recs)} ({time.time() - t0:.0f}s); total {len(latest)}", flush=True)
    tmp.rmdir()
    # A failed batch from an older year only thins the history; the two newest years carry the current data.
    recent = [f for f in failed if f[0] >= max(years) - 1]
    if len(recent) > 1 or len(failed) > 5 or not latest:
        raise RuntimeError(f"Batches failed: {failed}; keeping the previous data files")

    latest = current(latest, filed, max(years))
    by_state: dict[str, list[dict]] = defaultdict(list)
    for rec in latest.values():
        states = {rec["state"]} | set(rec["recipient_states"])
        for st in states:
            if re.fullmatch(r"[A-Z]{2}", st or ""):
                by_state[st].append(hist.for_state(rec, st))
    stamp = datetime.now(timezone.utc).isoformat(timespec="minutes")
    for st, recs in by_state.items():
        payload = {"fetched_at": stamp, "state": st, "years": years, "count": len(recs), "foundations": recs}
        with gzip.open(out_dir / f"{st}.json.gz", "wt", encoding="utf-8") as fh:
            json.dump(payload, fh, separators=(",", ":"))
    (out_dir / "parsed.json").write_text(json.dumps(tally(seen, set(latest), max(years), CURRENT_FILING_YEARS)), encoding="utf-8")
    write_left_out(out_dir / "skipped.jsonl.gz", seen, set(latest), max(years), "foundation")
    steady = sum(1 for rec in latest.values() if (hist.summary(rec["ein"], rec["tax_year"]) or {}).get("steady"))
    print(f"wrote {len(latest)} foundations into {len(by_state)} state files in {out_dir}; {steady} gave every year")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", default=",".join(map(str, default_years(datetime.now().year))),
                    help="comma separated IRS filing years (default: enough for five tax years of history)")
    ap.add_argument("--out", default="data/foundations", type=Path)
    ap.add_argument("--batches", default="", help="only these batch ids (for testing)")
    args = ap.parse_args()
    years = [int(y) for y in args.years.split(",")]
    build(years, args.out, [b for b in args.batches.split(",") if b] or None)


if __name__ == "__main__":
    main()
