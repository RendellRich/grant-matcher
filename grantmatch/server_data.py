"""Get the exported data ready for the private bucket the search function reads, and upload it.

The page no longer ships the grant data. The deploy workflow exports it, keeps the small public files for
the site (meta, examples, coverage, changes, counties, the local funder directory), and puts everything in the
Supabase bucket "data".
Signed-in accounts get short-lived links to the files there; visitors get a preview the search function
ranks itself, and for that it reads a slim copy of each state's foundations: every sample grant keeps the
city, state and purpose the score uses, but only the first eight, which the page shows, keep the rest.
California's file is about a third smaller that way, which keeps a function worker under its memory limit.

Run:
  python -m grantmatch.server_data slim export/           # write the .slim.json.gz copies
  python -m grantmatch.server_data public export/ web/public/data   # copy the public files for the site
  python -m grantmatch.server_data upload export/         # needs GM_INGEST_URL and GM_INGEST_TOKEN
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import re
import shutil
import sys
from pathlib import Path

import requests

SHOWN = 8  # sample grants the page shows for a foundation (web/src/entries.ts)
SCORED = ("city", "state", "purpose", "_city_title")
PUBLIC = re.compile(r"^(meta|examples|coverage|changes)\.json$|^(counties|funders)-[A-Z]{2}\.json$")
UPLOAD = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]*(\.slim)?\.(json|json\.gz|f16)$")


def slim_record(r: dict) -> dict:
    samples = r.get("sample_grants") or []
    out = dict(r)
    out["sample_grants"] = samples[:SHOWN] + [
        {k: g.get(k) for k in SCORED if k in g} for g in samples[SHOWN:] if isinstance(g, dict)
    ]
    return out


def write_slim(folder: Path) -> list[Path]:
    made = []
    for path in sorted(folder.glob("foundations-*.json.gz")):
        if path.name.endswith(".slim.json.gz"):
            continue
        payload = json.loads(gzip.decompress(path.read_bytes()))
        payload["records"] = [slim_record(r) for r in payload["records"]]
        target = path.with_name(path.name.replace(".json.gz", ".slim.json.gz"))
        target.write_bytes(gzip.compress(json.dumps(payload, separators=(",", ":")).encode("utf-8"), mtime=0))
        made.append(target)
    return made


def copy_public(folder: Path, site: Path) -> list[str]:
    site.mkdir(parents=True, exist_ok=True)
    names = sorted(p.name for p in folder.iterdir() if PUBLIC.match(p.name))
    for name in names:
        shutil.copy2(folder / name, site / name)
    return names


def upload(folder: Path, url: str, token: str, session: requests.Session | None = None) -> int:
    """Asks the ingest function for one upload link per file, then uploads each. Returns how many went up."""
    http = session or requests.Session()
    names = sorted(p.name for p in folder.iterdir() if p.is_file() and UPLOAD.match(p.name))
    sent = 0
    for i in range(0, len(names), 100):
        batch = names[i:i + 100]
        res = http.post(url, json={"names": batch}, headers={"x-ingest-token": token}, timeout=60)
        res.raise_for_status()
        links = res.json()["links"]
        for name in batch:
            up = http.put(links[name], data=(folder / name).read_bytes(),
                          headers={"Content-Type": "application/octet-stream", "x-upsert": "true"}, timeout=300)
            if not up.ok:
                raise RuntimeError(f"{name}: upload failed ({up.status_code})")
            sent += 1
    return sent


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("action", choices=["slim", "public", "upload"])
    ap.add_argument("folder", type=Path)
    ap.add_argument("site", type=Path, nargs="?")
    args = ap.parse_args()
    if args.action == "slim":
        made = write_slim(args.folder)
        print(f"Wrote {len(made)} slim foundation files")
    elif args.action == "public":
        if not args.site:
            ap.error("public needs the site's data folder")
        print(f"Copied {len(copy_public(args.folder, args.site))} public files")
    else:
        url, token = os.environ.get("GM_INGEST_URL", ""), os.environ.get("GM_INGEST_TOKEN", "")
        if not url or not token:
            print("GM_INGEST_URL or GM_INGEST_TOKEN isn't set, so nothing was uploaded.", file=sys.stderr)
            sys.exit(1)
        print(f"Uploaded {upload(args.folder, url, token)} files")


if __name__ == "__main__":
    main()
