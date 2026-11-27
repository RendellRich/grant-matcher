"""Check how old the data behind the master list is, and whether the links it can check still open.

The page watch (grantmatch/watch.py) reads the pages behind the hand-kept lists. This adds the rest, and runs at
the end of the same weekly job, so no new job is needed:

  data      the date the data is from (federal, foundations, community foundations, the company list, the
            county names, the local funder directory, the funder website check, the coverage numbers, the built
            states and the hand-kept files), against how long each may go before it is old
  links     the public pages the sources are read from, and the links on state calls. Pages the page watch
            has just read are not asked for again. A link is dead when it answers 404 or 410, or can't be reached
            (a timeout, a refused connection, a 5xx) on two checks in a row, and stays dead until it answers.
            A page that is off limits (robots.txt, unread robots.txt, terms) or that answers any other error
            (400, 401, 403, 405, 429...) is reported on its own and never counted dead
  records   hand-kept programs whose closing date has passed with no next round entered
  by hand   hand-kept programs and company programs with a page that is off limits or turns automated readers away,
            so nothing can recheck it: each is named under "Check by hand" for a person to open in a browser

Pages are asked for only through cycles.fetch_page, which applies the project's crawling rule (off_limits) to the
address and every redirect and sends the project's own user agent. Requests to one host are spaced out, longer
when its robots.txt asks, and a run is capped (MAX_PAGES, PER_HOST, TIME_BUDGET): what doesn't fit waits for a
later week, oldest first.

Not link-checked: federal grant links (no job opens them; the Grants.gov refresh reads the API, not the grant
pages), Florida's catalog links and foundation websites (the Florida refresh and the funder website check read
those pages, but no link result is recorded from them), the government websites in the local funder directory
(about 1,200 of them: nothing opens them, so the weekly job's minutes don't grow) and pages on off-limits hosts.

A finding is listed in full the first time and only counted after that. A release file that couldn't be read is
reported as that, not as old data.

It never edits an entry. Results are written into the page watch's report and state file (under "_freshness").

Run on its own (reads the public release over HTTPS; the hand-kept pages are the watcher's and are left alone):
  python -m grantmatch.freshness --state build/freshness-state.json.gz --report build/freshness-report.md
"""
from __future__ import annotations

import argparse
import gzip
import json
import queue
import re
import threading
import time
import zlib
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlparse

import requests

from . import counties, cycles, funders, local
from .cycles import AGENT, TIMEOUT, OffLimits, blocked_by_terms, fetch_page, off_limits
from .display import STATE_NAMES
from .export_web import RELEASE
from .states import STATES, paused_host

DATA = local.LOCAL
KEY = "_freshness"  # where the results live inside the page watch's state file

# Days a source's data may be old before it is flagged, by how often it is meant to be read again. A daily
# source gets two missed runs, a weekly or monthly one a little over one; a snapshot with no job gets two weeks;
# hand-kept entries match the page watch's 90 days; the funder directory comes from yearly federal files, so it
# gets a year and about five weeks; the Census county file is replaced once a census.
MAX_DAYS = {"twice a day": 3, "daily": 3, "weekly": 10, "monthly": 45, "no job yet": 14, "by hand": 90,
            "yearly": 400, "each census": 4018}

# Public pages of the sources that aren't in the state registry (grantmatch/states.py has the states').
FEDERAL_PAGE = "https://www.grants.gov/"
FOUNDATIONS_PAGE = "https://www.irs.gov/charities-non-profits/form-990-series-downloads"
COMMUNITY_PAGE = ("https://www.irs.gov/charities-non-profits/"
                  "exempt-organizations-business-master-file-extract-eo-bmf")
CENSUS_YEAR = "2020-01-01"  # the county names file is the 2020 places-by-county file (grantmatch/counties.py)

MAX_PAGES = 150     # pages asked for in one run (robots.txt, once a host, comes on top)
PER_HOST = 20       # pages from one host in one run
HOST_DELAY = 2.0    # seconds before each request to a host; more when its robots.txt asks
# each asks for 10 seconds between requests
SLOW_HOSTS = {"communityaffairs.dc.gov": 10.0, "artscouncil.ky.gov": 10.0, **cycles.CRAWL_DELAYS}
TIME_BUDGET = 150   # seconds of link checking; no new request starts past it
RELEASE_BUDGET = 90  # seconds of reading the release; files after it are reported as not read
WORKERS = 8
GONE = (404, 410)
UNREAD = "could not read"  # a release file whose read failed or was skipped: not the same as old
FORGET_DAYS = 35    # a link no longer listed is remembered this long, so a file that failed to load loses nothing
SHOWN = 40          # lines of one kind in the report, for the lists that aren't findings
NEW_ROOM = 20_000   # characters of new findings in one report; the rest are listed in a later one
STAMP = re.compile(r'"(?:fetched_at|checked_at|made_at)"\s*:\s*"(\d{4}-\d{2}-\d{2}[^"]*)"')


# ---------------- reading the release ----------------

class Release:
    """The data-latest release over public HTTPS, as export_web reads it. None means no copy could be had."""

    def __init__(self, budget: float = RELEASE_BUDGET, clock=time.monotonic):
        self.clock, self.until = clock, None
        self.budget = budget
        self.failed: list[str] = []  # files that couldn't be read (a missing file is not a failure)
        self._local = threading.local()

    def _session(self) -> requests.Session:
        if not hasattr(self._local, "s"):
            self._local.s = requests.Session()
            self._local.s.headers["User-Agent"] = AGENT
        return self._local.s

    def __call__(self, name: str, head: bool = False) -> bytes | None:
        """The file, or with `head` just enough of its start to hold its date."""
        if self.until is None:
            self.until = self.clock() + self.budget
        if self.clock() > self.until:
            self.failed.append(name)
            return None
        try:
            with self._session().get(RELEASE + name, timeout=(6, 30), stream=head) as r:
                if r.status_code == 404:
                    return None
                if not r.ok:
                    self.failed.append(name)
                    return None
                if not head:
                    return r.content
                got = b""
                for chunk in r.iter_content(16384):
                    got += chunk
                    if stamp_of(got) or len(got) > 262_144:
                        break
                return got
        except requests.RequestException:
            self.failed.append(name)
            return None


def stamp_of(raw: bytes | None) -> str | None:
    """When a data file says it was read ("fetched_at" and the like), from the whole file or just its start."""
    if not raw:
        return None
    if raw[:2] == b"\x1f\x8b":
        try:
            raw = zlib.decompressobj(31).decompress(raw)
        except zlib.error:
            return None
    m = STAMP.search(raw[:4096].decode("utf-8", errors="ignore")) or STAMP.search(raw.decode("utf-8", errors="ignore"))
    return m.group(1) if m else None


def payload(raw: bytes | None) -> dict:
    if not raw:
        return {}
    try:
        data = json.loads(gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw)
    except (OSError, ValueError, EOFError, zlib.error):
        return {}
    return data if isinstance(data, dict) else {}


def asset(release, data_dir: Path, name: str, head: bool = False, snapshot: str | None = None) -> tuple[bytes | None, str]:
    """(bytes, "release" or "repository copy"), falling back to data/ as export_web does when the release has no
    copy. A read that failed or was skipped is (None, UNREAD): the older copy in data/ would read as old data."""
    raw = release(name, head)
    if raw:
        return raw, "release"
    if name in getattr(release, "failed", ()):
        return None, UNREAD
    path = data_dir / (snapshot or name)
    return (path.read_bytes(), "repository copy") if path.exists() else (None, "")


def parallel(fn, items: list, workers: int = WORKERS) -> list:
    """fn over items, a few at a time, results in order."""
    out = [None] * len(items)
    todo: queue.Queue = queue.Queue()
    for i, item in enumerate(items):
        todo.put((i, item))

    def work():
        while True:
            try:
                i, item = todo.get_nowait()
            except queue.Empty:
                return
            try:
                out[i] = fn(item)
            except Exception as exc:  # one odd file or host never stops the check
                print(f"freshness: {item!r}: {type(exc).__name__}: {exc}")

    threads = [threading.Thread(target=work) for _ in range(min(workers, len(items)))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return out


# ---------------- the inventory ----------------

def age(stamp: str | None, today: date) -> int | None:
    try:
        return (today - date.fromisoformat(str(stamp)[:10])).days
    except ValueError:
        return None


def source(key: str, name: str, every: str, stamp: str | None, where: str, today: date,
           pages: tuple | list = (), notes: tuple | list = (), partial: int = 0, paused: str = "") -> dict:
    """One source. `partial` counts the files of a many-file source that couldn't be read."""
    days = age(stamp, today)
    limit = MAX_DAYS[every]
    unread = where == UNREAD
    return {"key": key, "name": name, "every": every, "date": str(stamp)[:10] if days is not None else None,
            "days": days, "limit": limit, "stale": not unread and (days is None or days > limit), "unread": unread,
            "partial": partial, "where": where, "pages": list(pages), "paused": paused,
            "notes": ([f"reading is paused {paused}"] if paused else []) + list(notes)}


def _count(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def _web(url) -> str:
    return url if isinstance(url, str) and url.startswith(("https://", "http://")) else ""


def _entries(data_dir: Path) -> list[tuple[str, dict]]:
    """Every hand-kept program with its state, from data/local-<ST>.json."""
    out = []
    for path in sorted(data_dir.glob("local-??.json")):
        state = path.stem.split("-", 1)[1].upper()
        out += [(state, e) for e in json.loads(path.read_text(encoding="utf-8")).get("programs", [])]
    return out


def past_deadlines(entries: list[tuple[str, dict]], websites: dict, today: date) -> list[dict]:
    """Hand-kept programs whose closing date has passed, with no next window entered, not rolling, and whose own
    page didn't say applications are open at the last website check."""
    out = []
    for state, e in entries:
        closes = e.get("closes")
        if not closes or closes >= today.isoformat() or e.get("rolling"):
            continue
        seen = websites.get(local.record_id(e["slug"], state)) or {}
        if seen.get("s") == "open" or (seen.get("s") == "deadline" and str(seen.get("d", "")) >= today.isoformat()):
            continue
        out.append({"list": f"local-{state}", "key": e["slug"], "name": e.get("title", ""), "closes": closes})
    return out


def inventory(today: date, release=None, data_dir: Path = DATA) -> tuple[list[dict], dict[str, list[str]], list[dict]]:
    """(the sources with the date their data is from, the links to check with what uses them, past deadlines)."""
    release = release or Release()
    sources: list[dict] = []
    links: dict[str, list[str]] = {}

    def link(url, used_by: str) -> None:
        if _web(url):
            users = links.setdefault(url, [])
            if used_by not in users:
                users.append(used_by)

    def add(*args, **kwargs) -> None:
        s = source(*args, **kwargs)
        sources.append(s)
        for url in s["pages"]:
            link(url, f"source page: {s['name']}")

    raw, where = asset(release, data_dir, "opportunities.json.gz", head=True)
    add("federal", "Federal grants (Grants.gov)", "twice a day", stamp_of(raw), where, today, [FEDERAL_PAGE])

    # Foundation files: one per state and kind. The oldest is the source's date. Only their starts are read.
    listed = set()
    states_raw = release("states.json")
    list_unread = "states.json" in getattr(release, "failed", ())
    try:
        listed = set(json.loads(states_raw)) if states_raw else set()
    except (ValueError, TypeError):
        pass
    for prefix, key, name, page in (("foundations", "foundations", "Private foundations (IRS 990-PF)", FOUNDATIONS_PAGE),
                                    ("community", "community", "Community foundations and United Ways (IRS 990)",
                                     COMMUNITY_PAGE)):
        codes = sorted(listed | {p.name.split(".")[0] for p in (data_dir / prefix).glob("*.json.gz")})
        read = parallel(lambda code: asset(release, data_dir, f"{prefix}-{code}.json.gz", True,
                                           f"{prefix}/{code}.json.gz"), codes)
        found = [(stamp_of(r[0]), r[1], code) for code, r in zip(codes, read) if r and r[0]]
        dated = sorted(f for f in found if f[0])
        from_copy = sum(1 for f in found if f[1] != "release")
        notes = [f"{len(found)} state files read" + (f", {from_copy} from the repository copy" if from_copy else "")]
        if dated:
            notes.append(f"oldest is {dated[0][2]}")
        failed = sum(1 for r in read if r and r[1] == UNREAD) + list_unread
        if failed:
            notes.append(f"{_count(failed, 'file', 'files')} could not be read")
        where = "release" if found and not from_copy else "repository copy" if found else ""
        add(key, name, "monthly", dated[0][0] if dated else None, UNREAD if failed and not dated else where, today,
            [page], notes, partial=failed)

    # The funder website check also tells which hand-kept programs say they are open.
    raw, where = asset(release, data_dir, "cycles.json.gz")
    sites = payload(raw).get("sites") or {}
    add("websites", "Funder website check", "weekly", stamp_of(raw), where, today)
    # Without it, a program whose website says applications are open can't be told from one past its closing date.
    sources[-1]["unusable"] = not isinstance(payload(raw).get("sites"), dict)
    raw, where = asset(release, data_dir, "coverage.json")
    add("coverage", "Foundation coverage numbers", "monthly", stamp_of(raw), where, today)

    # The local funder directory: yearly federal files, committed in data/. Only the two source pages are
    # link-checked; the governments' own websites never are.
    path = data_dir / "funders.json.gz"
    directory = payload(path.read_bytes()) if path.exists() else {}
    add("funders", "Local funder directory (HUD allocations and Census government units)", "yearly",
        directory.get("fetched_at"), "repository copy", today, [funders.HUD_PAGE, funders.CENSUS_PAGE],
        [f"{len(directory.get('funders') or [])} funders, fiscal year {directory.get('fiscal_year', 'unknown')}; "
         "their websites aren't link-checked"])

    add("counties", "County and place names (Census)", "each census",
        CENSUS_YEAR if (data_dir / "counties.json.gz").exists() else None, "repository copy", today, [counties.SOURCE],
        ["the 2020 census file"])

    # Every built state, from the registry. Florida's catalog pages are read by its own weekly refresh, so only its
    # date is checked here; the other states' calls have their links checked.
    for code, s in sorted(STATES.items()):
        if s["status"] != "built":
            continue
        name = f"{s['file']}.json.gz"
        raw, where = asset(release, data_dir, name, head=code == "FL")
        records = [] if code == "FL" else payload(raw).get("programs") or []
        notes = []
        if code != "FL" and where != UNREAD:
            past = sum(1 for r in records if r.get("closes") and str(r["closes"]) < today.isoformat())
            notes.append(f"{len(records)} calls in the file" + (f", {past} past deadline (the export leaves them out)"
                                                               if past else ""))
            for r in records:
                link(r.get("url"), f"{code} state call: {str(r.get('title', ''))[:80]}")
        if where == "repository copy":
            notes.append("read from the repository copy; the release has none")
        add(f"state:{code}", s["report"] if STATE_NAMES.get(code, code) in s["report"]
            else f"{STATE_NAMES.get(code, code)}: {s['report']}", s["refresh"] or "no job yet",
            stamp_of(raw), where, today, s["pages"], notes, paused=(s.get("paused") or {}).get("why", ""))

    # Hand-kept files and the company list: the oldest checked date. The page watch lists each old entry by name.
    entries = _entries(data_dir)
    for state in sorted({st for st, _ in entries}):
        mine = [e for st, e in entries if st == state]
        checked = sorted(str(e.get("checked") or "") for e in mine)
        old = sum(1 for e in mine if (age(e.get("checked"), today) or 0) > MAX_DAYS["by hand"])
        add(f"local:{state}", f"Hand-kept programs, {STATE_NAMES.get(state, state)} (data/local-{state}.json)",
            "by hand", checked[0] if checked else None, "repository copy", today,
            notes=[_count(len(mine), "entry", "entries") + (f", {old} checked over 90 days ago" if old else "")])
        for e in mine:
            for url in (e.get("url"), e.get("web")):
                link(url, f"local-{state}: {e.get('slug')}")
    corp_file = data_dir / "corporate.json"
    firms = json.loads(corp_file.read_text(encoding="utf-8")).get("foundations", []) if corp_file.exists() else []
    programs = [(f, f["program"]) for f in firms if f.get("program")]
    checked = sorted(str(p.get("checked") or "") for _, p in programs)
    old = sum(1 for _, p in programs if (age(p.get("checked"), today) or 0) > MAX_DAYS["by hand"])
    add("corporate", "Company programs (data/corporate.json)", "by hand", checked[0] if checked else None,
        "repository copy", today,
        notes=[_count(len(programs), "program", "programs") + (f", {old} checked over 90 days ago" if old else "")])
    for f, p in programs:
        link(p.get("url"), f"corporate: {f.get('company')}")
    return sources, links, past_deadlines(entries, sites, today)


def hand_pages(data_dir: Path) -> list[dict]:
    """Each hand-kept program and company program with the pages it points to."""
    rows = [{"list": f"local-{state}", "key": e.get("slug", ""), "name": e.get("title", ""),
             "urls": list(dict.fromkeys(u for u in (e.get("url"), e.get("web")) if _web(u)))}
            for state, e in _entries(data_dir)]
    corp_file = data_dir / "corporate.json"
    firms = json.loads(corp_file.read_text(encoding="utf-8")).get("foundations", []) if corp_file.exists() else []
    for f in firms:
        program = f.get("program") or {}
        if _web(program.get("url")):
            rows.append({"list": "corporate", "key": str(f.get("ein", "")), "urls": [program["url"]],
                         "name": f"{f.get('company', '')}: {program.get('name', '')}".rstrip(": ")})
    return rows


def by_hand(pages: list[dict], memory: dict) -> list[dict]:
    """The entries with a page that couldn't be looked at (blocked or turned away at its last check). A dead page
    is listed with the dead links instead, and one that didn't open once may open next week."""
    out = []
    for row in pages:
        shut = [(u, memory[u].get("why", "")) for u in row["urls"]
                if (memory.get(u) or {}).get("s") in ("blocked", "refused")]
        if shut:
            out.append({**row, "shut": shut})
    return out


# ---------------- checking links ----------------

def from_code(code: int) -> dict:
    if 200 <= code < 300:
        return {"s": "ok"}
    why = f"HTTP {code}"
    # Only a 5xx says the site is in trouble; any other error (400, 403, 405...) is an answer that turns this away.
    return {"s": "gone" if code in GONE else "unreachable" if code >= 500 else "refused", "why": why}


def link_reading(url: str) -> dict:
    """Whether the page answers. Only the status is read, never the body."""
    try:
        with fetch_page(url, timeout=TIMEOUT, stream=True,
                        headers={"Accept": "text/html,application/pdf,*/*;q=0.8"}) as r:
            return from_code(r.status_code)
    except OffLimits as e:
        return {"s": "blocked", "why": str(e)}
    except Exception as e:  # a refused connection, a timeout, a bad certificate, a broken address
        return {"s": "unreachable", "why": type(e).__name__}


def from_watch(reading: dict) -> dict:
    """The page watch's reading of a page (watch.read) as a link result."""
    if reading.get("s") == "ok":
        return {"s": "ok"}
    why = str(reading.get("why", ""))
    if reading.get("s") == "blocked":
        return {"s": "blocked", "why": why}
    code = re.fullmatch(r"HTTP (\d{3})", why)
    if code:
        return from_code(int(code.group(1)))
    if why.startswith(("could not read the file", "unexpected file type")):
        return {"s": "ok"}  # the page answered; its contents are the watcher's business
    return {"s": "unreachable", "why": why}


def remember(before: dict | None, reading: dict, today: date) -> dict:
    """What to keep for a link after this reading. n counts checks in a row, on separate days, that couldn't
    reach it (two make it dead) or couldn't look at it. A dead link stays dead until a reading is ok."""
    day = today.isoformat()
    s = reading["s"]
    if s == "ok":
        return {"s": "ok", "d": day}
    if s == "gone":
        return {"s": "dead", "d": day, "why": reading.get("why", "")}
    if (before or {}).get("s") == "dead":  # a page that can't be reached or looked at hasn't come back
        return {**before, "d": day} if s == "unreachable" else dict(before)
    chain = "n" if s == "unreachable" else "b"
    n = (before or {}).get(chain, 0)
    if not n or (before or {}).get("d") != day:  # a second run the same day isn't a second check
        n += 1
    if s == "unreachable":
        s = "dead" if n >= 2 else "unreachable"
    return {"s": s, "d": day, "why": reading.get("why", ""), chain: n}


def plan(urls: list[str], source_pages: set[str], memory: dict) -> list[str]:
    """The links to ask for this run, most needed first, within the caps: those to confirm as dead, then the
    sources' own pages, then dead ones again, then links never checked, then the longest unchecked, and last
    those that were off limits or turned scripts away."""
    def rank(url):
        m = memory.get(url) or {}
        if m.get("s") == "unreachable":
            return (0, "", url)
        if url in source_pages:
            return (1, m.get("d", ""), url)
        if m.get("s") == "dead":
            return (2, m.get("d", ""), url)
        if not m:
            return (3, "", url)
        return (5 if m.get("s") in ("blocked", "refused") else 4, m.get("d", ""), url)

    chosen, per_host = [], {}
    for url in sorted(urls, key=rank):
        host = (urlparse(url).hostname or "").lower()
        if host in cycles.ONLY_UNDER:  # read by its adapter alone, so one request a page a week
            continue
        if len(chosen) >= MAX_PAGES:
            break
        if per_host.get(host, 0) >= PER_HOST:
            continue
        per_host[host] = per_host.get(host, 0) + 1
        chosen.append(url)
    return chosen


def host_delay(url: str) -> float:
    """Seconds to wait before each request to this host. Reads its robots.txt (kept for the checks that follow),
    except for a host on the terms blocklist, which is never asked for anything."""
    if paused_host(url) or blocked_by_terms(url):
        return 0.0
    p = urlparse(url)
    rules = cycles._robots_for(f"{p.scheme}://{p.netloc}")
    asked = rules[0].crawl_delay(AGENT) if rules else None
    return max(HOST_DELAY, float(asked or 0), SLOW_HOSTS.get((p.hostname or "").lower(), 0.0))


def check_links(urls: list[str], reader=link_reading, delay=host_delay, sleep=time.sleep, clock=time.monotonic,
                budget: float = TIME_BUDGET, workers: int = WORKERS, off=off_limits) -> tuple[dict[str, dict], dict]:
    """Readings for the planned links, one host at a time each and spaced out. Hosts run side by side. A page
    off limits is recorded without being asked for or waited for; links the time budget doesn't reach are left
    for a later run."""
    hosts: dict[str, list[str]] = {}
    for url in urls:
        hosts.setdefault((urlparse(url).netloc or url).lower(), []).append(url)
    started = clock()
    readings: dict[str, dict] = {}
    asked: list[str] = []

    def one_host(mine: list[str]) -> None:
        if clock() - started >= budget:
            return
        wait = delay(mine[0])
        for url in mine:
            if clock() - started + wait > budget:
                return
            why = off(url)
            if why:
                readings[url] = {"s": "blocked", "why": why}
                continue
            if wait:
                sleep(wait)
            asked.append(url)
            readings[url] = reader(url)

    parallel(one_host, list(hosts.values()), workers)
    return readings, {"pages": len(asked), "hosts": len({(urlparse(u).netloc or u).lower() for u in asked}),
                      "blocked": len(readings) - len(asked), "deferred": len(urls) - len(readings),
                      "seconds": round(clock() - started)}


# ---------------- the report ----------------

def _cut(lines: list[str]) -> list[str]:
    more = len(lines) - SHOWN
    return lines[:SHOWN] + ([f"- and {more} more"] if more > 0 else [])


def findings(sources: list[dict], links: dict[str, list[str]], memory: dict, past: list[dict],
             hand: list[dict] = ()) -> list[tuple[str, str, str]]:
    """Everything that needs a person, each as (a key that stays the same from week to week, its kind, its line)."""
    out = []
    for s in sources:
        if s["stale"]:
            said = f"data from {s['date']}, {s['days']} days old" if s["date"] else "no date could be read"
            out.append((f"stale:{s['key']}", "stale",
                        f"- **{s['name']}** (`{s['key']}`): {said}; the limit is {s['limit']} days "
                        f"(refresh: {s['every']})."
                        + (f" Reading is paused {s['paused']}, so this is expected." if s.get("paused") else "")))
    for url in sorted(links):
        m = memory.get(url) or {}
        if m.get("s") == "dead":
            out.append((f"dead:{url}", "dead",
                        f"- {url} : {m.get('why', '')}" + (f", {m['n']} checks in a row" if m.get("n") else "")
                        + f". Used by: {'; '.join(links[url][:3])}" + (" and others" if len(links[url]) > 3 else "")))
    for p in past:
        out.append((f"past:{p['list']}/{p['key']}/{p['closes']}", "past",
                    f"- `{p['list']}` / `{p['key']}`: {p['name']}, closed {p['closes']}"))
    for h in hand:
        out.append((f"hand:{h['list']}/{h['key']}", "hand",
                    f"- `{h['list']}` / `{h['key']}`: {h['name']}. "
                    + "; ".join(f"{url} : {why}" for url, why in h["shut"])))
    return out


# kind: (heading for new ones, one, many) for the carried-over count
KINDS = {"stale": ("Data that is old or missing", "old source", "old sources"),
         "dead": ("Dead links", "dead link", "dead links"),
         "past": ("Closing date passed, no next round entered", "closing date passed", "closing dates passed"),
         "hand": ("Check by hand", "entry to check by hand", "entries to check by hand")}


def condition(s: dict, memory: dict) -> str:
    """A source's state in a few words, to tell whether it changed since the last report."""
    data = "could not read" if s["unread"] else "old" if s["stale"] else "ok"
    page = ", ".join(sorted({(memory.get(u) or {}).get("s", "not checked") for u in s["pages"]}))
    return f"{data}; {page}"


def report(sources: list[dict], links: dict[str, list[str]], memory: dict, past: list[dict], stats: dict,
           today: date, watched: set[str], previous: dict,
           hand: list[dict] = ()) -> tuple[str, int, list[str], dict[str, str]]:
    """(the section added to the page watch's report, how many findings are new, the keys of the findings already
    reported, each source's condition). New findings are listed in full; ones reported before are only counted."""
    items = findings(sources, links, memory, past, hand)
    reported = set(previous.get("flagged") or [])
    # With no website check to read, hold new past closing dates: some may be programs that say they are open.
    no_websites = any(s.get("unusable") for s in sources)
    if no_websites:
        items = [i for i in items if i[1] != "past" or i[0] in reported]
    new = [i for i in items if i[0] not in reported]
    carried = [i for i in items if i[0] in reported]
    shown, room = [], NEW_ROOM
    for item in new:
        if len(item[2]) + 1 > room:
            break
        shown.append(item)
        room -= len(item[2]) + 1
    never = sum(1 for u in links if u not in memory)
    lines = [f"# Freshness check, {today.isoformat()}", "",
             f"{len(sources)} sources and {len(links)} links. {len(new)} newly need a look and {len(carried)} are "
             f"carried over from earlier reports. This run asked for "
             f"{stats['pages']} pages on {stats['hosts']} hosts in {stats['seconds']} seconds"
             + (f", left {stats['blocked']} unasked as off limits" if stats.get("blocked") else "")
             + (f"; {len(stats.get('watched', []))} came from the page watch" if stats.get("watched") else "")
             + f"; {stats['deferred']} planned pages ran out of time and {never} links have not been checked yet."]
    for kind, (heading, _, _) in KINDS.items():
        mine = [line for _, k, line in shown if k == kind]
        if mine and kind != "hand":
            lines += ["", f"## New: {heading[0].lower()}{heading[1:]}", "", *mine]
    # Its own section, every run: new entries in full, then the ones already reported, still by name.
    listed = [line for _, k, line in shown if k == "hand"]
    carried_keys = {i[0] for i in carried if i[1] == "hand"}
    waiting = [f"{h['name']} (`{h['list']}/{h['key']}`)" for h in hand if f"hand:{h['list']}/{h['key']}" in carried_keys]
    if listed or waiting:
        lines += ["", "## Check by hand", "",
                  "A page of each of these is off limits or turns automated readers away, so nothing rechecks it. Open "
                  "it in a browser, update the entry from the page and set its `checked` date."]
        if listed:
            lines += ["", "New:", "", *listed]
        if waiting:
            lines += ["", f"Reported before and still to check by hand ({len(waiting)}): {'; '.join(waiting)}."]
    if len(new) > len(shown):
        lines += ["", f"{len(new) - len(shown)} more new findings didn't fit here; a later report lists them."]
    if carried:
        counts = [_count(sum(1 for _, k, _ in carried if k == kind), one, many)
                  for kind, (_, one, many) in KINDS.items() if any(k == kind for _, k, _ in carried)]
        lines += ["", "## Still open from earlier reports", "",
                  f"{', '.join(counts)}. Each was listed in full when first reported and isn't counted again."]
        old = [f"{s['name']} (`{s['key']}`)" for s in sources if s["stale"] and f"stale:{s['key']}" in reported]
        if old:
            lines += ["", f"Old sources still open: {'; '.join(old)}."]
    if no_websites:
        lines += ["", "The funder website check couldn't be read, so no new past closing dates are listed this run."]
    unread = [s for s in sources if s["unread"] or s["partial"]]
    if unread:
        lines += ["", "## Could not read this run (not counted as old)", ""]
        lines += _cut([f"- {s['name']} (`{s['key']}`)"
                       + (f": {_count(s['partial'], 'file', 'files')}" if s["partial"] else "") for s in unread])
    once = sorted(u for u in links if memory.get(u, {}).get("s") == "unreachable")
    if once:
        lines += ["", "## Didn't open once (dead if it fails again next check)", ""]
        lines += _cut([f"- {u} : {memory[u].get('why', '')}" for u in once])

    shut: dict[tuple[str, str], list[str]] = {}
    named = {url for h in hand for url, _ in h["shut"]}
    for url in links:
        m = memory.get(url) or {}
        # The watched pages that are blocked or turned away are in the page watch's own list above, and the
        # hand-kept ones are under Check by hand.
        if m.get("s") in ("blocked", "refused") and url not in watched | named:
            shut.setdefault((urlparse(url).netloc, m.get("why", "")), []).append(url)
    lines += ["", "## Not link-checked", "",
              "- Federal grant links: no job opens them (the Grants.gov refresh reads the API, not the grant pages).",
              "- Florida catalog links: the weekly Florida refresh reads the catalog pages; no link result is kept.",
              "- Foundation websites: the weekly website check reads them; no link result is kept.",
              "- Local funder directory websites: government sites from the Census listing; none are opened.",
              "- Off-limits hosts and pages that turn scripts away (never counted as dead). Hand-kept and company "
              "programs are named under Check by hand" + ("; the other pages:" if shut else ".")]
    rows = []
    for (host, why), urls in sorted(shut.items()):
        weeks = max(memory[u].get("b", 1) for u in urls)
        rows.append(f"  - {host}: {why} ({_count(len(urls), 'page', 'pages')}"
                    + (f", {weeks} checks in a row" if weeks > 1 else "") + ")")
    lines += _cut(rows)

    conditions = {s["key"]: condition(s, memory) for s in sources}
    before = previous.get("sources") or {}
    changed = [s for s in sources if before.get(s["key"]) != conditions[s["key"]]]
    lines += ["", "## Sources new or changed since the last report", ""]
    if changed:
        lines += ["| Source | Data from | Limit (days) | Refresh | Its page | Notes |", "|---|---|---:|---|---|---|"]
    for s in changed:
        page = conditions[s["key"]].split("; ", 1)[1]
        said = s["date"] or ("could not read" if s["unread"] else "unknown")
        lines.append(f"| {s['name']} | {said}{' (old)' if s['stale'] else ''} | {s['limit']} "
                     f"| {s['every']} | {page} | {'; '.join(s['notes'])} |")
    if len(changed) < len(sources):
        lines += ([""] if changed else []) + [f"{len(sources) - len(changed)} other sources are as they were."]

    keys = {i[0] for i in carried} | {i[0] for i in shown}
    if no_websites:
        keys |= {k for k in reported if k.startswith("past:")}
    # What couldn't be looked at this run stays reported, so it isn't listed as new when it can be read again.
    if unread:
        keys |= reported & {f"stale:{s['key']}" for s in unread}
        keys |= {k for k in reported if k.startswith("dead:") and (memory.get(k[len("dead:"):]) or {}).get("s") == "dead"}
    return "\n".join(lines) + "\n", len(new), sorted(keys), conditions


# ---------------- running it ----------------

def check(previous: dict | None, watch_readings: dict[str, dict], today: date, release=None,
          data_dir: Path = DATA, linker=check_links, skip: set[str] = frozenset()) -> dict:
    """One run. `previous` is what the last run kept, `watch_readings` the page watch's readings by address (those
    pages aren't asked for again) and `skip` addresses to leave alone. Returns the report text, how many findings
    are new, what to keep and the run's numbers."""
    release = release or Release()
    sources, links, past = inventory(today, release, data_dir)
    previous = previous or {}
    old = previous.get("links") or {}
    pages = {u for s in sources for u in s["pages"]}
    asked = [u for u in links if u not in watch_readings and u not in skip]
    readings, stats = linker(plan(asked, pages, old))
    watched = {u: from_watch(r) for u, r in watch_readings.items() if u in links}
    stats["watched"] = sorted(watched)
    readings = {**readings, **watched}
    keep_after = (today - timedelta(days=FORGET_DAYS)).isoformat()
    memory = {u: m for u, m in old.items() if u in links or str(m.get("d", "")) >= keep_after}
    for url, reading in readings.items():
        memory[url] = remember(old.get(url), reading, today)
    hand = by_hand(hand_pages(data_dir), memory)
    text, count, keys, conditions = report(sources, links, memory, past, stats, today, set(watch_readings) | set(skip),
                                           previous, hand)
    return {"text": text, "flagged": count,
            "memory": {"checked": today.isoformat(), "links": memory, "flagged": keys, "sources": conditions},
            "stats": stats, "sources": sources, "past": past, "links": links, "hand": hand}


def main() -> None:
    from .watch import load_state, save_state, targets

    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--state", type=Path, default=Path("build/freshness-state.json.gz"))
    ap.add_argument("--report", type=Path, default=Path("build/freshness-report.md"))
    ap.add_argument("--today", type=date.fromisoformat, default=date.today())
    args = ap.parse_args()
    state = load_state(args.state)
    started = time.monotonic()
    result = check(state.get(KEY), {}, args.today, skip={r["url"] for r in targets()})
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(result["text"], encoding="utf-8")
    save_state(args.state, {**state, KEY: result["memory"]})
    s = result["stats"]
    print(f"{len(result['sources'])} sources, {len(result['links'])} links, {s['pages']} pages asked for on "
          f"{s['hosts']} hosts, {s['deferred']} deferred, {result['flagged']} new findings; link checks "
          f"{s['seconds']}s, whole run {round(time.monotonic() - started)}s; report in {args.report}")


if __name__ == "__main__":
    main()
