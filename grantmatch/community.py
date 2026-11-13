"""Community foundations, public foundations, and United Ways from IRS Form 990 e-file data.

These are public charities, so they file Form 990 instead of 990-PF, and the grants they make to other
organizations appear on Schedule I (grants over $5,000 per recipient). The IRS Exempt Organizations
Business Master File gives each organization an NTEE activity code, which is how they are found:
  T31 community foundations, T30 public foundations, T70 federated giving programs (United Ways).

Run:  python -m grantmatch.community --years 2025,2026 --out data/community
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

from .foundations import XML_ROOT, _find, _local, _num, _text, session

try:
    import zipfile_deflate64  # noqa: F401
except ImportError:
    pass

BMF = "https://www.irs.gov/pub/irs-soi/eo{n}.csv"
KINDS = {"T31": "Community foundation", "T30": "Public foundation", "T70": "United Way or federated fund"}
MAX_GRANTS_KEPT = 40


def bmf_orgs() -> dict[str, dict]:
    orgs = {}
    for n in range(1, 5):
        r = session.get(BMF.format(n=n), timeout=300)
        r.raise_for_status()
        for row in csv.DictReader(io.StringIO(r.content.decode("latin-1"))):
            code = (row.get("NTEE_CD") or "")[:3]
            if code in KINDS:
                orgs[row["EIN"]] = {"kind": KINDS[code], "ntee": row["NTEE_CD"]}
    return orgs


def parse_return(xml: bytes) -> dict | None:
    root = ET.fromstring(xml)
    header = _find(root, "ReturnHeader")
    f990 = _find(root, "IRS990")
    if header is None or f990 is None:
        return None
    filer = _find(header, "Filer")
    grants = []
    for t in root.iter():
        if _local(t.tag) != "RecipientTable":
            continue
        amt = (_num(_text(t, "CashGrantAmt")) or 0) + (_num(_text(t, "NonCashAssistanceAmt")) or 0)
        if amt <= 0:
            continue
        grants.append({
            "to": (_text(t, "RecipientBusinessName", "BusinessNameLine1Txt") or _text(t, "RecipientPersonNm"))[:120],
            "city": _text(t, "CityNm")[:40],
            "state": _text(t, "StateAbbreviationCd"),
            "purpose": _text(t, "PurposeOfGrantTxt")[:200],
            "amount": amt,
        })
    return {
        "ein": _text(filer, "EIN"),
        "name": _text(filer, "BusinessName", "BusinessNameLine1Txt"),
        "city": _text(filer, "CityNm"),
        "state": _text(filer, "StateAbbreviationCd"),
        "zip": _text(filer, "ZIPCd")[:5],
        "phone": _text(filer, "PhoneNum"),
        "tax_year": _text(header, "TaxYr"),
        "website": _text(f990, "WebsiteAddressTxt"),
        "mission": (_text(f990, "ActivityOrMissionDesc") or _text(f990, "MissionDesc"))[:600],
        "assets": _num(_text(f990, "TotalAssetsEOYAmt")),
        "grants_total": _num(_text(f990, "GrantsToDomesticOrgsGrp", "TotalAmt")),
        "grants": grants,
    }


def summarize(rec: dict, kind: str) -> dict:
    grants = rec.pop("grants")
    amounts = [g["amount"] for g in grants]
    purposes = Counter(g["purpose"].lower() for g in grants if g["purpose"])
    recipients = Counter(g["to"].lower() for g in grants if g["to"])
    rec.update({
        "kind": kind,
        "preselected_only": False,
        "grant_count": len(grants),
        "grant_median": statistics.median(amounts) if amounts else None,
        "grant_min": min(amounts) if amounts else None,
        "grant_max": max(amounts) if amounts else None,
        "recipient_states": dict(Counter(g["state"] for g in grants if g["state"]).most_common(12)),
        "top_purposes": [p for p, _ in purposes.most_common(25)],
        "top_recipients": [r for r, _ in recipients.most_common(60)],
        "sample_grants": sorted(grants, key=lambda g: -g["amount"])[:MAX_GRANTS_KEPT],
        "url": f"https://projects.propublica.org/nonprofits/organizations/{rec['ein']}",
    })
    return rec


def build(years: list[int], out_dir: Path) -> None:
    orgs = bmf_orgs()
    print(f"{len(orgs)} organizations coded T31, T30 or T70 in the IRS master file", flush=True)
    tmp = out_dir / "_tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    latest: dict[str, dict] = {}
    for year in years:
        r = session.get(XML_ROOT.format(year=year) + f"index_{year}.csv", timeout=300)
        if r.status_code != 200:
            print(f"{year}: no index yet; skipping", flush=True)
            continue
        batches: dict[str, set[str]] = defaultdict(set)
        for row in csv.DictReader(io.StringIO(r.content.decode("latin-1"))):
            if row["RETURN_TYPE"] == "990" and row["EIN"] in orgs and row.get("XML_BATCH_ID"):
                batches[row["XML_BATCH_ID"]].add(row["OBJECT_ID"])
        for batch, ids in sorted(batches.items()):
            t0, kept = time.time(), 0
            path = tmp / f"{batch}.zip"
            try:
                with session.get(XML_ROOT.format(year=year) + f"{batch}.zip", stream=True, timeout=600) as resp:
                    resp.raise_for_status()
                    with open(path, "wb") as fh:
                        for chunk in resp.iter_content(1 << 20):
                            fh.write(chunk)
                with zipfile.ZipFile(path) as z:
                    for name in z.namelist():
                        if name.rsplit("/", 1)[-1].split("_")[0] not in ids:
                            continue
                        try:
                            rec = parse_return(z.read(name))
                        except ET.ParseError:
                            continue
                        if not rec or not rec["grants"] or rec["ein"] not in orgs:
                            continue
                        rec = summarize(rec, orgs[rec["ein"]]["kind"])
                        prev = latest.get(rec["ein"])
                        if prev is None or rec["tax_year"] >= prev["tax_year"]:
                            latest[rec["ein"]] = rec
                        kept += 1
            except Exception as exc:
                print(f"{batch}: FAILED {exc}", file=sys.stderr, flush=True)
            finally:
                path.unlink(missing_ok=True)
            print(f"{batch}: {len(ids)} returns, kept {kept} ({time.time() - t0:.0f}s); total {len(latest)}", flush=True)
    tmp.rmdir()
    if not latest:
        raise RuntimeError("No returns parsed; keeping the previous data files")

    by_state: dict[str, list[dict]] = defaultdict(list)
    for rec in latest.values():
        for st in {rec["state"]} | set(rec["recipient_states"]):
            if re.fullmatch(r"[A-Z]{2}", st or ""):
                by_state[st].append(rec)
    stamp = datetime.now(timezone.utc).isoformat(timespec="minutes")
    for st, recs in by_state.items():
        payload = {"fetched_at": stamp, "state": st, "years": years, "count": len(recs), "foundations": recs}
        with gzip.open(out_dir / f"{st}.json.gz", "wt", encoding="utf-8") as fh:
            json.dump(payload, fh, separators=(",", ":"))
    kinds = Counter(r["kind"] for r in latest.values())
    print(f"wrote {len(latest)} grantmaking public charities ({dict(kinds)}) into {len(by_state)} state files")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", default=f"{datetime.now().year - 1},{datetime.now().year}")
    ap.add_argument("--out", default="data/community", type=Path)
    args = ap.parse_args()
    build([int(y) for y in args.years.split(",")], args.out)


if __name__ == "__main__":
    main()
