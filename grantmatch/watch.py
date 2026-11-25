"""Watch the pages behind the hand-kept lists and say which entries need a person to look again.

data/local-<ST>.json (one per state) and data/corporate.json are typed in by hand from each program's own page. Pages
change after that: a program goes on hold, a new cycle opens, an amount changes. This reads every page
those lists point to (HTML, PDF or Word), compares it with last week's reading, and writes a short
report of what needs review:

  status   the page has words like "on hold", "suspended", "now accepting" or "applications are
           closed" that it did not have last time (on the first run, every such line)
  changed  sentences were added or removed since last week (dates, copyright lines and other noise
           are ignored)
  blank    the page came back with almost no text, which usually means it is built in the browser
           and needs a person (or a real browser) to read it
  error    the page could not be reached; blocked means the page is off limits and was not read: robots.txt
           keeps out this crawler, ClaudeBot or another Anthropic agent, or the host's terms forbid
           automation (grantmatch/cycles.py). A blocked entry is reported, never deleted
  stale    the entry's checked date is older than --stale-days

It never edits an entry. A person reads the page and updates the entry and its checked date.

Run:
  python -m grantmatch.watch --state build/watch-state.json.gz --report build/watch-report.md
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import requests

from .cycles import CLOSED, OPEN, TIMEOUT, OffLimits, fetch_page, page_text, snippet

DATA = Path(__file__).resolve().parent.parent / "data"
MAX_BYTES = 8_000_000
KEEP_CHARS = 60_000  # text kept per page in the state file
BLANK_CHARS = 300
SHOW_ADDED, SHOW_REMOVED, SHOW_STATUS = 5, 3, 4

# Words that mean a program stopped, paused or changed course. OPEN and CLOSED come from cycles.py.
STOPPED = re.compile(
    r"\bon hold\b|\b(?:program|grants?|applications?|funding|cycle|period)\b[^.]{0,30}\b(?:suspended|paused|postponed|cancell?ed)\b"
    r"|\b(?:suspended|paused|postponed|cancell?ed) until\b|\buntil further notice\b"
    r"|\bdiscontinued\b|\bno longer (?:offer|available|accept|fund)\w*|\bhas been eliminated\b"
    r"|\b(?:application|grant) period is (?:now )?closed\b|\bnow open\b", re.I)
# Sentences that change every week without the program changing.
NOISE = re.compile(
    r"©|\bcopyright\b|\ball rights reserved\b|\bcookies?\b|\blast (?:updated|modified)\b|\bpage updated\b"
    r"|\bposted (?:on|by)\b|\bskip to\b|\bjavascript\b|\bsubscribe\b|\bsign (?:in|up)\b", re.I)
DIGITS = re.compile(r"\d+")


# ---------------- what to watch ----------------

def targets(data_dir: Path = DATA) -> list[dict]:
    """One row per page: the list it came from, the entry, its checked date and the URL."""
    rows = []
    for path in sorted(data_dir.glob("local-??.json")):
        local = json.loads(path.read_text(encoding="utf-8"))
        for p in local["programs"]:
            for url in dict.fromkeys(u for u in (p.get("url"), p.get("web")) if u):
                rows.append({"list": path.stem, "key": p["slug"], "name": p["title"], "checked": p.get("checked"), "url": url})
    corp = json.loads((data_dir / "corporate.json").read_text(encoding="utf-8"))
    for f in corp["foundations"]:
        prog = f.get("program") or {}
        if prog.get("url"):
            rows.append({"list": "corporate", "key": f["ein"], "name": f"{f['company']}: {prog.get('name', '')}".strip(),
                         "checked": prog.get("checked"), "url": prog["url"]})
    return rows


# ---------------- reading a page ----------------

def pdf_text(body: bytes) -> str:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(body))
    return " ".join((page.extract_text() or "") for page in reader.pages[:40])


def docx_text(body: bytes) -> str:
    from docx import Document
    doc = Document(io.BytesIO(body))
    parts = [p.text for p in doc.paragraphs]
    for t in doc.tables:
        parts += [c.text for row in t.rows for c in row.cells]
    return " ".join(parts)


def kind(url: str, content_type: str) -> str:
    ct, path = content_type.lower(), url.lower().split("?")[0]
    if "pdf" in ct or path.endswith(".pdf"):
        return "pdf"
    if "wordprocessingml" in ct or path.endswith(".docx"):
        return "docx"
    if "html" in ct or "xml" in ct or not ct:
        return "html"
    return "other"


def read(url: str) -> dict:
    """{"s": "ok", "text": ...} or {"s": "blocked" | "error", "why": ...}."""
    try:
        with fetch_page(url, timeout=TIMEOUT, stream=True,
                        headers={"Accept": "text/html,application/pdf,*/*;q=0.8"}) as r:
            if not r.ok:
                return {"s": "error", "why": f"HTTP {r.status_code}"}
            body = b""
            for chunk in r.iter_content(65536):
                body += chunk
                if len(body) > MAX_BYTES:
                    break
            k = kind(r.url, r.headers.get("content-type", ""))
            if k == "pdf":
                text = pdf_text(body)
            elif k == "docx":
                text = docx_text(body)
            elif k == "html":
                try:
                    raw = body.decode("utf-8")
                except UnicodeDecodeError:
                    raw = body.decode("cp1252", errors="replace")
                text = page_text(raw)
            else:
                return {"s": "error", "why": f"unexpected file type {r.headers.get('content-type', '')}"}
    except OffLimits as e:
        return {"s": "blocked", "why": str(e)}
    except requests.RequestException as e:
        return {"s": "error", "why": type(e).__name__}
    except Exception as e:  # a broken PDF or Word file
        return {"s": "error", "why": f"could not read the file ({type(e).__name__})"}
    return {"s": "ok", "text": re.sub(r"\s+", " ", text).strip()}


# ---------------- comparing readings ----------------

def sentences(text: str) -> list[str]:
    out = []
    for s in re.split(r"(?<=[.!?])\s+", text):
        s = s.strip()
        if len(s) < 25 or NOISE.search(s):
            continue
        out.append(s)
    return out


def _key(s: str) -> str:
    # Digits are kept: an amount or a date changing is exactly what we want to see.
    return re.sub(r"\W+", " ", s.lower()).strip()


def fingerprint(text: str) -> str:
    return hashlib.sha256("\n".join(sorted({_key(s) for s in sentences(text)})).encode()).hexdigest()[:16]


def differences(old: str, new: str) -> tuple[list[str], list[str]]:
    """Sentences added and removed, ignoring order and noise."""
    before, after = {_key(s): s for s in sentences(old)}, {_key(s): s for s in sentences(new)}
    added = [after[k] for k in after if k not in before]
    removed = [before[k] for k in before if k not in after]
    # A sentence edited in place shows as one added and one removed; keep both, they are the useful part.
    return added, removed


def status_lines(text: str) -> list[str]:
    seen, out = set(), []
    for pattern in (STOPPED, CLOSED, OPEN):
        for m in pattern.finditer(text):
            s = snippet(text, m.start(), m.end())
            if _key(s) not in seen:
                seen.add(_key(s))
                out.append(s)
    return out


def short(s: str, n: int = 200) -> str:
    s = s.lstrip(". ")
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def assess(row: dict, reading: dict, before: dict | None, today: date, stale_days: int) -> tuple[list[dict], dict]:
    """Findings for one page, and what to remember for next week."""
    found = []
    if row.get("checked"):
        try:
            age = (today - date.fromisoformat(row["checked"])).days
            if age > stale_days:
                found.append({"t": "stale", "lines": [f"checked {row['checked']}, {age} days ago"]})
        except ValueError:
            pass
    if reading["s"] != "ok":
        found.append({"t": "blocked" if reading["s"] == "blocked" else "error", "lines": [reading["why"]]})
        return found, (before or {}) | {"last_error": reading["why"]}
    text = reading["text"]
    if len(text) < BLANK_CHARS:
        found.append({"t": "blank", "lines": [f"only {len(text)} characters of text; check it in a browser"]})
    status = status_lines(text)
    old_status = set(before.get("status", [])) if before else set()
    new_status = [s for s in status if _key(s) not in old_status]
    if new_status:
        found.append({"t": "status", "lines": new_status[:SHOW_STATUS], "more": max(0, len(new_status) - SHOW_STATUS)})
    fp = fingerprint(text)
    if before and before.get("fp") and before["fp"] != fp:
        added, removed = differences(before.get("text", ""), text)
        if added or removed:
            found.append({"t": "changed", "added": added[:SHOW_ADDED], "removed": removed[:SHOW_REMOVED],
                          "more": max(0, len(added) - SHOW_ADDED) + max(0, len(removed) - SHOW_REMOVED)})
    memory = {"fp": fp, "text": text[:KEEP_CHARS], "status": sorted({_key(s) for s in status}),
              "seen": today.isoformat(), "last_error": None}
    memory["since"] = before.get("since", today.isoformat()) if before and before.get("fp") == fp else today.isoformat()
    return found, memory


# ---------------- the report ----------------

LABEL = {"status": "Status wording", "changed": "Page changed", "blank": "Blank page", "error": "Could not reach",
         "blocked": "Blocked by robots.txt or site terms", "stale": "Entry is old"}
ORDER = ["status", "error", "changed", "blank", "blocked", "stale"]


def report(results: list[tuple[dict, list[dict]]], today: date, first_run: bool) -> str:
    flagged = [(row, f) for row, f in results if f]
    lines = [f"# Page watcher, {today.isoformat()}", ""]
    lines.append(f"{len(results)} pages read, {len(flagged)} need a look."
                 + (" This is the first run, so there is nothing to compare yet: it lists current status wording only."
                    if first_run else ""))
    lines.append("")
    lines.append("Read each page, update the entry in its `data/local-<ST>.json` or `data/corporate.json` from the "
                 "official page, and set its `checked` date. Nothing here was changed automatically.")
    flagged.sort(key=lambda rf: (min(ORDER.index(x["t"]) for x in rf[1]), rf[0]["list"], rf[0]["key"]))
    for row, found in flagged:
        lines += ["", f"## {row['name']}", f"`{row['list']}` / `{row['key']}`: {row['url']}"]
        for x in sorted(found, key=lambda x: ORDER.index(x["t"])):
            lines.append(f"- **{LABEL[x['t']]}**")
            if x["t"] == "changed":
                lines += [f"  - added: {short(s)}" for s in x["added"]]
                lines += [f"  - removed: {short(s)}" for s in x["removed"]]
            else:
                lines += [f"  - {short(s)}" for s in x["lines"]]
            if x.get("more"):
                lines.append(f"  - and {x['more']} more")
    return "\n".join(lines) + "\n"


# ---------------- running it ----------------

def load_state(path: Path) -> dict:
    if not path.exists():
        return {}
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)


def run(rows: list[dict], state: dict, today: date, stale_days: int, workers: int = 8,
        reader=read) -> tuple[list[tuple[dict, list[dict]]], dict]:
    urls = list(dict.fromkeys(r["url"] for r in rows))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        readings = dict(zip(urls, pool.map(reader, urls)))
    results, new_state = [], {}
    for row in rows:
        found, memory = assess(row, readings[row["url"]], state.get(row["url"]), today, stale_days)
        new_state[row["url"]] = memory
        results.append((row, found))
    return results, new_state


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--state", type=Path, default=Path("build/watch-state.json.gz"))
    ap.add_argument("--report", type=Path, default=Path("build/watch-report.md"))
    ap.add_argument("--stale-days", type=int, default=90)
    ap.add_argument("--today", type=date.fromisoformat, default=date.today())
    args = ap.parse_args()

    state = load_state(args.state)
    rows = targets()
    results, new_state = run(rows, state, args.today, args.stale_days)
    text = report(results, args.today, first_run=not state)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(text, encoding="utf-8")
    save_state(args.state, new_state)
    flagged = sum(1 for _, f in results if f)
    print(f"{len(results)} pages, {flagged} need a look; report in {args.report}")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
            f.write(f"flagged={flagged}\n")


if __name__ == "__main__":
    main()
