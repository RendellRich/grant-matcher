"""Deadline and status changes between data refreshes, published as changes.json for Exceed the Odds.

ETO's CRM reads this file to spot when a grant it is already pursuing moves its deadline, closes, or reopens
(Phase 3, deadline watch). It holds public data only: what Grants.gov and the weekly funder website check
said, and when that changed. It knows nothing about ETO or anyone's profile.

Each run reads the data export_web just wrote, compares it with the changes.json the live site published last
time, and writes a new one:

  {"updated_at": "2026-11-17", "baseline": false,
   "records": {"fed:355824": {"d": "2027-03-01", "s": "posted"}, "fdn:591234567": {"d": null, "s": "open"}},
   "events": [{"k": "fed:355824", "kind": "moved", "from": "2027-02-15", "to": "2027-03-01", "at": "2026-11-17"}]}

Events kept for 60 days: moved, set and cleared (a deadline), posted (a federal forecast now takes
applications), closed and reopened (a funder's or county program's website), gone (a federal notice left
Grants.gov). County and city programs ("fl:local-...") carry the closing date entered by hand.
A record that drops out of the data for a day and comes back makes no event.

Run after export_web:
  python -m grantmatch.changes web/public/data --previous https://rendellrich.github.io/grant-matcher/data/changes.json
"""
from __future__ import annotations

import argparse
import gzip
import json
import re
from datetime import date, timedelta
from pathlib import Path

import requests

KEEP_DAYS = 60  # events older than this are dropped
GONE_DAYS = 2  # a federal notice missing this many days counts as gone; refreshes run twice a day
FORGET_DAYS = 10  # a funder website missing longer than this (the check is weekly) is dropped quietly
PARTIAL = 0.5  # a source with under half its previous records is treated as a failed fetch and carried over
WEBSITE = ("open", "deadline", "closed")
DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def day(value) -> str | None:
    s = str(value or "")[:10]
    return s if DAY.match(s) else None


def read_gz(path: Path) -> dict:
    return json.loads(gzip.decompress(path.read_bytes()))


def current(out: Path) -> dict[str, dict | None]:
    """What the exported data says now, by source: {"fed": {key: {"d", "s"}}, "fdn": {...}}.
    A source with no file this run is None, so its records are carried over instead of counted as missing."""
    fed_file = out / "federal.json.gz"
    fed = None
    if fed_file.exists():
        fed = {f"fed:{r['id']}": {"d": day(r.get("close_date")), "s": str(r.get("status") or "")}
               for r in read_gz(fed_file).get("records", []) if r.get("id") is not None}
    fdn_files = sorted(out.glob("foundations-*.json.gz"))
    fdn = None
    if fdn_files:
        fdn = {}
        for f in fdn_files:
            for r in read_gz(f).get("records", []):
                c = r.get("_cycle")
                if isinstance(c, dict) and c.get("s") in WEBSITE and r.get("ein"):
                    fdn[f"fdn:{r['ein']}"] = {"d": day(c.get("d")), "s": c["s"]}
    # County and city programs (grantmatch/local.py): the window's closing date entered by hand, else what
    # their page said at the weekly check. State programs have no dates, so they are left out.
    fl_file = out / "florida.json.gz"
    fl = None
    if fl_file.exists():
        fl = {}
        for r in read_gz(fl_file).get("records", []):
            if not str(r.get("id", "")).startswith("local-"):
                continue
            c = r.get("_cycle") if isinstance(r.get("_cycle"), dict) else {}
            s = c.get("s") if c.get("s") in WEBSITE else ""
            fl[f"fl:{r['id']}"] = {"d": day(r.get("closes")) or day(c.get("d")), "s": s}
    return {"fed": fed, "fdn": fdn, "fl": fl}


def events_for(key: str, before: dict, now: dict, today: str) -> list[dict]:
    out = []
    a, b = before.get("d"), now.get("d")
    if a and b and a != b:
        out.append({"k": key, "kind": "moved", "from": a, "to": b, "at": today})
    elif b and not a:
        out.append({"k": key, "kind": "set", "from": None, "to": b, "at": today})
    elif a and not b:
        out.append({"k": key, "kind": "cleared", "from": a, "to": None, "at": today})
    sa, sb = before.get("s"), now.get("s")
    if key.startswith("fed:") and sa == "forecasted" and sb == "posted":
        out.append({"k": key, "kind": "posted", "from": sa, "to": sb, "at": today})
    if key.startswith(("fdn:", "fl:")):
        if sb == "closed" and sa in ("open", "deadline"):
            out.append({"k": key, "kind": "closed", "from": sa, "to": sb, "at": today})
        elif sa == "closed" and sb in ("open", "deadline"):
            out.append({"k": key, "kind": "reopened", "from": sa, "to": sb, "at": today})
    return out


def update(previous: dict | None, now: dict[str, dict | None], today: date) -> dict:
    """The next changes.json from the last one and the data now. With no usable last one, this run is the
    baseline: it records the data and reports no events."""
    t = today.isoformat()
    if not previous or not isinstance(previous.get("records"), dict):
        records = {k: v for src in now.values() if src for k, v in src.items()}
        return {"updated_at": t, "baseline": True, "records": dict(sorted(records.items())), "events": []}

    old = previous["records"]
    records: dict[str, dict] = {}
    events: list[dict] = []
    for prefix, src in now.items():
        before = {k: v for k, v in old.items() if k.startswith(f"{prefix}:")}
        present = sum(1 for v in before.values() if not v.get("m"))
        if src is None or (present and len(src) < present * PARTIAL):
            records.update(before)  # this source failed or came back short: keep what was there, report nothing
            continue
        for key, rec in src.items():
            prev = before.get(key)
            if prev:
                events += events_for(key, prev, rec, t)
            records[key] = rec
        for key, prev in before.items():
            if key in src:
                continue
            missing = day(prev.get("m")) or t
            days = (today - date.fromisoformat(missing)).days
            if prefix == "fed" and days >= GONE_DAYS:
                events.append({"k": key, "kind": "gone", "from": prev.get("d"), "to": None, "at": t})
            elif prefix in ("fdn", "fl") and days > FORGET_DAYS:
                pass
            else:
                records[key] = {**{k: v for k, v in prev.items() if k != "m"}, "m": missing}

    cutoff = (today - timedelta(days=KEEP_DAYS)).isoformat()
    kept = [e for e in previous.get("events") or [] if isinstance(e, dict) and str(e.get("at", "")) >= cutoff]
    return {"updated_at": t, "baseline": False, "records": dict(sorted(records.items())),
            "events": sorted(kept + events, key=lambda e: (e["at"], e["k"], e["kind"]))}


def load_previous(where: str | None) -> dict | None:
    """The last published changes.json, from a URL or a file. None when it can't be read."""
    if not where:
        return None
    try:
        if where.startswith("https://"):
            r = requests.get(where, timeout=30)
            if not r.ok:
                return None
            data = r.json()
        else:
            data = json.loads(Path(where).read_text(encoding="utf-8"))
    except (requests.RequestException, OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out", type=Path, help="the folder export_web wrote")
    ap.add_argument("--previous", help="URL or file of the last published changes.json")
    args = ap.parse_args()
    result = update(load_previous(args.previous), current(args.out), date.today())
    (args.out / "changes.json").write_text(json.dumps(result, separators=(",", ":")), encoding="utf-8")
    print(f"changes: {len(result['records'])} records, {len(result['events'])} events"
          f"{' (baseline: no earlier file)' if result['baseline'] else ''}")


if __name__ == "__main__":
    main()
