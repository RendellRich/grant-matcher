"""Build data/counties.json.gz: for each state, each county's cities, towns and Census places.

A person can type "Manatee" and still match grants that went to Bradenton, Palmetto or Ellenton.
Source: the Census Bureau's 2020 places-by-county reference file (public domain). Run when the
Census publishes a new file; the output is committed.

Run:
  python -m grantmatch.counties
"""
from __future__ import annotations

import gzip
import json
import re
from pathlib import Path

import requests

SOURCE = "https://www2.census.gov/geo/docs/reference/codes2020/national_place_by_county2020.txt"
OUT = Path(__file__).resolve().parent.parent / "data" / "counties.json.gz"
# Census names end in the place's legal kind ("Bradenton city", "Ellenton CDP"); people write the name alone.
KIND = re.compile(r"\s+(city and borough|consolidated government.*|metropolitan government.*|unified government.*|"
                  r"urban county|city|town|township|village|borough|municipality|CDP|comunidad|zona urbana)(\s*\(.*\))?$", re.I)
COUNTY = re.compile(r"\s+(County|Parish|Borough|Census Area|City and Borough|Municipality|Municipio|city)$")


def place_name(raw: str) -> str:
    return KIND.sub("", raw.strip()).strip()


def county_name(raw: str) -> str:
    return COUNTY.sub("", raw.strip()).strip()


def build(text: str) -> dict[str, dict[str, list[str]]]:
    out: dict[str, dict[str, set[str]]] = {}
    lines = text.splitlines()
    head = lines[0].split("|")
    col = {k: head.index(k) for k in ("STATE", "COUNTYNAME", "PLACENAME")}
    for line in lines[1:]:
        f = line.split("|")
        if len(f) < len(head):
            continue
        name = place_name(f[col["PLACENAME"]])
        if name:
            out.setdefault(f[col["STATE"]], {}).setdefault(county_name(f[col["COUNTYNAME"]]), set()).add(name)
    return {st: {c: sorted(p) for c, p in sorted(cs.items())} for st, cs in sorted(out.items())}


def main() -> None:
    r = requests.get(SOURCE, timeout=120)
    r.raise_for_status()
    data = build(r.content.decode("latin-1"))
    OUT.write_bytes(gzip.compress(json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode("utf-8"), mtime=0))
    print(f"{len(data)} states, {sum(len(c) for c in data.values())} counties, {OUT.stat().st_size / 1e3:.0f} kB")


if __name__ == "__main__":
    main()
