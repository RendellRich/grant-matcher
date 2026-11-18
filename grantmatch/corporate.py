"""Company foundations, entered by hand (data/corporate.json).

The IRS data can't tell a company's foundation from a family's, and it doesn't describe the local
grant programs companies run through their foundations. This file names company foundations by EIN,
the company behind each, and, where the company's own giving page says so, the program a small
nonprofit can apply to. export_web adds it to each matching foundation record as "_corp". It never
changes a score; the page shows it and can narrow the list to company foundations.

A national program (Walmart's Spark Good grants, given through every store) is shown in each state
it serves, even when the foundation's IRS return lists other states among its top 12.

Run:  python -m grantmatch.corporate      # check the file
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

LOCAL = Path(__file__).resolve().parent.parent / "data"
EIN = re.compile(r"^\d{9}$")
STATE = re.compile(r"^[A-Z]{2}$")
DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
PROGRAM_FIELDS = ("name", "who", "amount", "when", "how", "url", "checked")


def check(entry: dict) -> list[str]:
    problems = []
    if not EIN.match(str(entry.get("ein", ""))):
        problems.append("ein must be 9 digits")
    if not entry.get("company"):
        problems.append("missing company")
    if not STATE.match(str(entry.get("home", ""))):
        problems.append("home must be a two-letter state")
    serves = entry.get("serves")
    if serves not in (None, "*") and not (isinstance(serves, list) and serves and all(STATE.match(str(s)) for s in serves)):
        problems.append('serves must be null, "*" or a list of two-letter states')
    prog = entry.get("program")
    if prog is not None:
        if not isinstance(prog, dict):
            problems.append("program must be an object")
        else:
            problems += [f"program missing {k}" for k in PROGRAM_FIELDS if not prog.get(k)]
            if prog.get("url") and not str(prog["url"]).startswith("https://"):
                problems.append("program url must start with https://")
            if prog.get("checked") and not DAY.match(str(prog["checked"])):
                problems.append("program checked must be a yyyy-mm-dd date")
    return problems


def load(path: Path | None = None) -> dict[str, dict]:
    """Entries by EIN. A bad entry stops the run with what is wrong, so a typo never reaches the site."""
    path = path or LOCAL / "corporate.json"
    if not path.exists():
        return {}
    entries = json.loads(path.read_text(encoding="utf-8")).get("foundations", [])
    problems, out = [], {}
    for e in entries:
        problems += [f"{e.get('ein', '?')}: {p}" for p in check(e)]
        if str(e.get("ein")) in out:
            problems.append(f"{e['ein']}: listed twice")
        out[str(e.get("ein"))] = e
    if problems:
        raise ValueError("data/corporate.json has problems:\n  " + "\n  ".join(problems))
    return out


def serves(entry: dict, state: str) -> bool:
    s = entry.get("serves")
    return s == "*" or (isinstance(s, list) and state in s)


def overlay(entry: dict) -> dict:
    """What the page shows: the company, and its program when there is one."""
    out = {"company": entry["company"]}
    if entry.get("program"):
        out["program"] = {k: v for k, v in entry["program"].items() if isinstance(v, str) and v}
    return out


def add_national(state: str, records: list[dict], ids: list[str], vecs: list, extra: dict[str, tuple[dict, object]],
                 entries: dict[str, dict]) -> int:
    """Append the national program foundations this state's files are missing. extra maps EIN to its
    (record, vector) from its home state. Returns how many were added."""
    have = {str(r.get("ein")) for r in records}
    added = 0
    for ein, (rec, vec) in extra.items():
        if ein in have or not serves(entries[ein], state):
            continue
        copy = dict(rec)
        if isinstance(copy.get("hist"), dict):  # its places are for its home state, not this one
            copy["hist"] = {k: v for k, v in copy["hist"].items() if k != "pl"}
        records.append(copy)
        ids.append(ein)
        vecs.append(vec.reshape(1, -1))
        added += 1
    return added


def main() -> None:
    try:
        entries = load()
    except ValueError as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)
    for ein, e in entries.items():
        prog = (e.get("program") or {}).get("name", "label only")
        print(f"{ein}: {e['company']} ({prog}); serves {e.get('serves') or 'its IRS states'}")
    print(f"{len(entries)} company foundations")


if __name__ == "__main__":
    main()
