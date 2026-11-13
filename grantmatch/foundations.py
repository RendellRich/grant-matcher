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


def _keep(rec: dict) -> bool:
    """Foundations a small nonprofit could approach: they pay grants to organizations and do not say
    they only fund preselected charities, or they publish how to apply."""
    if not rec["grants"]:
        return False
    if rec["preselected_only"] and not rec.get("apply"):
        return False
    return True


def batch_ids(year: int) -> dict[str, set[str]]:
    r = session.get(XML_ROOT.format(year=year) + f"index_{year}.csv", timeout=300)
    r.raise_for_status()
    batches: dict[str, set[str]] = defaultdict(set)
    for row in csv.DictReader(io.StringIO(r.content.decode("latin-1"))):
        if row["RETURN_TYPE"] == "990PF" and row.get("XML_BATCH_ID"):
            batches[row["XML_BATCH_ID"]].add(row["OBJECT_ID"])
    return batches


def process_batch(year: int, batch: str, ids: set[str], tmp: Path) -> list[dict]:
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
                if rec and _keep(rec):
                    out.append(summarize(rec))
    finally:
        path.unlink(missing_ok=True)
    return out


def build(years: list[int], out_dir: Path, only_batches: list[str] | None = None) -> None:
    tmp = out_dir / "_tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    latest: dict[str, dict] = {}
    failed: list[str] = []
    for year in years:
        try:
            batches = batch_ids(year)
        except requests.HTTPError as exc:
            print(f"{year}: no index yet ({exc}); skipping", flush=True)
            continue
        for batch, ids in sorted(batches.items()):
            if only_batches and batch not in only_batches:
                continue
            t0 = time.time()
            try:
                recs = process_batch(year, batch, ids, tmp)
            except Exception as exc:
                failed.append(batch)
                print(f"{batch}: FAILED {exc}", file=sys.stderr, flush=True)
                continue
            for rec in recs:  # keep the most recent return per foundation
                prev = latest.get(rec["ein"])
                if prev is None or rec["tax_year"] >= prev["tax_year"]:
                    latest[rec["ein"]] = rec
            print(f"{batch}: {len(ids)} returns, kept {len(recs)} ({time.time() - t0:.0f}s); total {len(latest)}", flush=True)
    tmp.rmdir()
    if len(failed) > 1 or not latest:
        raise RuntimeError(f"Batches failed: {failed}; keeping the previous data files")

    by_state: dict[str, list[dict]] = defaultdict(list)
    for rec in latest.values():
        states = {rec["state"]} | set(rec["recipient_states"])
        for st in states:
            if re.fullmatch(r"[A-Z]{2}", st or ""):
                by_state[st].append(rec)
    stamp = datetime.now(timezone.utc).isoformat(timespec="minutes")
    for st, recs in by_state.items():
        payload = {"fetched_at": stamp, "state": st, "years": years, "count": len(recs), "foundations": recs}
        with gzip.open(out_dir / f"{st}.json.gz", "wt", encoding="utf-8") as fh:
            json.dump(payload, fh, separators=(",", ":"))
    print(f"wrote {len(latest)} foundations into {len(by_state)} state files in {out_dir}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", default=str(datetime.now().year - 1), help="comma separated filing years")
    ap.add_argument("--out", default="data/foundations", type=Path)
    ap.add_argument("--batches", default="", help="only these batch ids (for testing)")
    args = ap.parse_args()
    years = [int(y) for y in args.years.split(",")]
    build(years, args.out, [b for b in args.batches.split(",") if b] or None)


if __name__ == "__main__":
    main()
