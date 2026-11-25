"""Run every state adapter that is meant to refresh weekly, in one job.

The states come from the registry (grantmatch/states.py): every built state but Florida whose refresh is weekly or
has no job yet. The daily states keep their own jobs. Each state's pages are checked against the project's
crawling rule (cycles.off_limits) first, and a state that fails, is off limits, writes nothing or comes back with
no calls never stops the others: its previous file is left exactly as it was. A state's data file and skipped list are written into the
out folder only when its whole run succeeded, and the states written are listed in <out>/refreshed.txt, one file
name per line, for the job's embedding and upload steps. The exit code is 1 when any state failed.

Run:  python -m grantmatch.refresh_states --out build
      add --states WV NJ to run only some of them
"""
from __future__ import annotations

import argparse
import importlib
import os
import shutil
import sys
from pathlib import Path

from .cycles import OffLimits, off_limits
from .states import STATES

MANIFEST = "refreshed.txt"
ADDRESSES = ("LIST", "HEALTH", "JUSTICE")  # the names the adapters give the addresses they read


def weekly_states() -> list[str]:
    return [code for code, s in STATES.items()
            if s["status"] == "built" and code != "FL" and s["refresh"] in ("weekly", None)]


def refresh_one(code: str, out: Path, allowed=None) -> None:
    """One state's data file and skipped list into `out`. Raises, leaving `out` as it was, when it can't."""
    allowed = allowed or off_limits
    spec = STATES[code]
    adapter = importlib.import_module(f"grantmatch.{spec['module']}")
    for name in ADDRESSES:
        url = getattr(adapter, name, None)
        why = allowed(url) if url else None
        if why:
            raise OffLimits(f"{url}: {why}")
    name = spec["file"]
    work = out / f".new-{name}"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    try:
        data, skipped = work / f"{name}.json.gz", work / f"skipped-{name}.json.gz"
        calls = adapter.build(data, skipped)
        if not data.exists():
            raise RuntimeError("the adapter wrote no data file")
        if not calls:  # a renamed field can drop every row: keep the last file and have a person look
            raise RuntimeError("the adapter read no open calls")
        if skipped.exists():
            os.replace(skipped, out / skipped.name)
        os.replace(data, out / data.name)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def refresh(out: Path, codes: list[str] | None = None, allowed=None) -> tuple[list[str], dict[str, str]]:
    """(states written, {state: why it failed})."""
    out.mkdir(parents=True, exist_ok=True)
    manifest = out / MANIFEST
    manifest.unlink(missing_ok=True)  # an earlier run's list must never be uploaded as this one's
    done, failed = [], {}
    for code in codes or weekly_states():
        print(f"--- {code}", flush=True)
        try:
            refresh_one(code, out, allowed)
            done.append(code)
        except (Exception, SystemExit) as e:  # one state never stops the others
            failed[code] = f"{type(e).__name__}: {e}"
            print(f"{code} failed, its previous file is unchanged: {failed[code]}", file=sys.stderr, flush=True)
    names = [STATES[c]["file"] for c in done]
    manifest.write_text("".join(f"{n}\n" for n in names), encoding="utf-8", newline="\n")
    return done, failed


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=Path, default=Path("build"))
    ap.add_argument("--states", nargs="+", choices=weekly_states(), help="default: every weekly state")
    args = ap.parse_args()
    done, failed = refresh(args.out, args.states)
    print("\nwritten:")
    for code in done:
        for f in (f"{STATES[code]['file']}.json.gz", f"skipped-{STATES[code]['file']}.json.gz"):
            if (args.out / f).exists():
                print(f"  {args.out / f}")
    if failed:
        print("failed:", file=sys.stderr)
        for code, why in failed.items():
            print(f"  {code}: {why}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
