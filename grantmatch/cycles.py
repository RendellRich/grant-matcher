"""Check foundations' own websites for open grant cycles and deadlines.

IRS returns are one to two years old and say nothing about whether a funder is taking applications
today. This visits each foundation's website (its home page, and the grants or apply page it links to),
reads the text, and records one of:

  open      the site says applications are open or being accepted now
  deadline  the site gives an application deadline that is still ahead
  closed    the site says it is not taking applications or requests now
  none      the site was read but says nothing either way
  error     the site could not be reached, or it is off limits (off_limits below: robots.txt keeps out
            this crawler, ClaudeBot or another Anthropic agent, or the host's terms forbid automation)

It is a reading of the funder's words, not a promise: the site shows the line it found and when.

Run:
  python -m grantmatch.cycles --out build/cycles.json.gz            # every state on the release
  python -m grantmatch.cycles --out build/cycles.json.gz --states FL --limit 200
"""
from __future__ import annotations

import argparse
import gzip
import html
import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from urllib import robotparser
from urllib.parse import unquote, urljoin, urlparse

import requests

from . import local
from .display import present
from .export_web import fetch, foundation_states

AGENT = "grant-matcher/1.0 (+https://github.com/RendellRich/grant-matcher; weekly check of public grant pages)"
TOKEN = "grant-matcher"  # the name robots.txt rules would use for this crawler
# A site that keeps any of these out is treated as keeping this project out.
ANTHROPIC_AGENTS = ("ClaudeBot", "Claude-User", "Claude-SearchBot", "Claude-Web", "anthropic-ai")
# Hosts whose terms forbid automated reading or commercial reuse (Grant Matcher is a paid product), or whose terms
# can't be read to find out. robots.txt doesn't say this, so the list is kept by hand: add a host with its reason
# when a terms page says so. A host covers its subdomains. Last reviewed November 25, 2026.
BLOCKED_HOSTS = {
    "surveymonkey.com": "its Acceptable Uses Policy bars automated extraction without written permission",
    "eunasolutions.com": "the Euna Supplier Network terms bar screen scraping without a license",
    "gobonfire.com": "the Euna Supplier Network terms bar screen scraping without a license",
    "bonfirehub.com": "the Euna Supplier Network terms bar screen scraping without a license",
    "submittable.com": "its terms page sits behind a bot check, so permission can't be established",
    "in.gov": "its terms bar putting its content into an information retrieval system",
    "nc.gov": "its terms allow copying for non-commercial use only",
    "wisconsin.gov": "its site policy limits the material to noncommercial use",
    "nebraska.gov": "its terms bar robots and scrapers without written permission",
    "dhhs.ne.gov": "the Nebraska.gov terms, taken to cover it, bar robots and scrapers without written permission",
    "nmculture.dca.nm.gov": "its terms bar reproducing site content without permission",
    "nmad.dca.nm.gov": "the Cultural Affairs terms, taken to cover it, bar reproducing site content without permission",
    "kansascommerce.gov": "its terms limit reuse",
    "ed.sc.gov": "its terms bar reproducing the site's material without permission",
    "phila.gov": "its terms of use prohibit commercial use without written permission",
    "cambridgema.gov": "its disclaimer prohibits commercial use without written consent",
    "detroitmi.gov": "its privacy and disclaimer page prohibits commercial use without written permission",
    "kingcounty.gov": "its terms of use bar publishing or commercially exploiting its content without permission",
    "thechildrenstrust.org": "its terms of use prohibit copying, reproducing or reselling its resources",
}
MAX_REDIRECTS = 10
TIMEOUT = (6, 12)  # connect, read
MAX_BYTES = 1_500_000
SNIPPET = 160

# ---------------- reading a page ----------------

OPEN = re.compile(
    r"\b(?:applications?|grant (?:cycle|round|portal)|(?:the )?portal|letters? of (?:inquiry|intent)|lois?|proposals?|requests?)"
    r" (?:are|is) (?:now |currently )?(?:open|being accepted|available)\b"
    r"|\b(?:now|currently) accepting (?:grant )?(?:applications|proposals|letters|requests|lois?)\b"
    r"|\bopen grant (?:cycle|round|opportunit\w+)\b"
    r"|\b(?:request for proposals|rfp)\b[^.]{0,40}\b(?:is |are )?(?:now )?(?:open|available|released)\b", re.I)
CLOSED = re.compile(
    r"\b(?:applications?|grant (?:cycle|round|portal)|(?:the )?portal|submissions?) (?:are|is) (?:now |currently )?closed\b"
    r"|\b(?:not|no longer) (?:currently |presently )?(?:accepting|considering|reviewing) (?:new |any )?"
    r"(?:grant )?(?:applications|proposals|requests|unsolicited|lois?|letters)\b"
    r"|\bdo(?:es)? not (?:accept|consider|review) unsolicited\b|\bby invitation only\b|\binvitation[- ]only\b"
    r"|\bclosed to (?:new )?(?:applications|requests|proposals)\b", re.I)
DUE_WORDS = re.compile(
    r"\b(?:deadline|due|apply by|submit(?:ted)? by|applications? (?:close|accepted (?:until|through))|closes?|"
    r"letters? of (?:inquiry|intent)|lois?|cycle|round|rfp)\b", re.I)
# Dates near these words are about something other than applying (a final report, an event).
NOT_DUE = re.compile(r"\b(?:reports?|gala|golf|tournament|dinner|luncheon|breakfast|tickets?|registration|concert|event)\b", re.I)
# A link to an application, which many sites keep up all year: a weaker sign than saying "open".
APPLY_LINK = re.compile(r"^\s*(?:apply(?: now| online| here| for (?:a |an )?(?:grant|funding))?|grant application|start (?:an |your )?application"
                        r"|submit (?:a |an )?(?:grant )?(?:request|application|proposal|loi))\s*$", re.I)
MONTHS = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
DATE = re.compile(
    r"\b(?P<mon>jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.? (?P<day>\d{1,2})(?:st|nd|rd|th)?,? (?P<year>20\d\d)\b"
    r"|\b(?P<m>\d{1,2})/(?P<d>\d{1,2})/(?P<y>20\d\d)\b", re.I)
GRANT_LINK = re.compile(r"\b(?:grants?|apply|application|funding|rfp|opportunit\w*|how to apply|guidelines|nonprofits?)\b", re.I)
SKIP_LINK = re.compile(r"\.(?:pdf|docx?|xlsx?|jpe?g|png|zip)(?:$|\?)|^mailto:|^tel:|^javascript:|facebook|twitter|instagram|linkedin|youtube", re.I)


def page_text(raw: str) -> str:
    """The words a person would read: scripts, styles and tags removed, spacing collapsed."""
    raw = re.sub(r"(?is)<(script|style|noscript|svg|template)\b.*?</\1>", " ", raw)
    raw = re.sub(r"(?s)<!--.*?-->", " ", raw)
    raw = re.sub(r"(?i)<br\s*/?>", " ", raw)  # a line break inside a heading is not the end of a sentence
    raw = re.sub(r"(?i)</(p|div|li|h\d|tr|section|article)>", ". ", raw)
    text = html.unescape(re.sub(r"<[^>]+>", " ", raw))
    return re.sub(r"\s+", " ", text).strip()


def links(raw: str, base: str) -> list[tuple[str, str]]:
    out = []
    for m in re.finditer(r"""(?is)<a\b[^>]*?href\s*=\s*["']([^"'#]+)["'][^>]*>(.*?)</a>""", raw):
        href, label = m.group(1).strip(), page_text(m.group(2))
        if SKIP_LINK.search(href):
            continue
        out.append((urljoin(base, href), label))
    return out


def grants_page(raw: str, base: str) -> str | None:
    """The page on the same site most likely to describe grants and how to apply."""
    host = urlparse(base).netloc.lower().removeprefix("www.")
    best, best_score = None, 0
    for url, label in links(raw, base):
        p = urlparse(url)
        if p.scheme not in ("http", "https") or p.netloc.lower().removeprefix("www.") != host:
            continue
        if url.rstrip("/") == base.rstrip("/"):
            continue
        score = 2 * len(GRANT_LINK.findall(label)) + len(GRANT_LINK.findall(p.path.replace("-", " ").replace("/", " ")))
        if score > best_score:
            best, best_score = url, score
    return best


def _date(m: re.Match) -> date | None:
    try:
        if m.group("mon"):
            return date(int(m.group("year")), MONTHS[m.group("mon").lower()[:3]], int(m.group("day")))
        return date(int(m.group("y")), int(m.group("m")), int(m.group("d")))
    except (ValueError, KeyError):
        return None


def snippet(text: str, start: int, end: int) -> str:
    """The sentence around a match, cut to SNIPPET characters."""
    def begin(before: int) -> int:  # start of the sentence that ends before `before`
        i = text.rfind(". ", 0, before)
        return 0 if i < 0 else i + 2

    left = max(begin(start), start - 80, 0)
    if end - left < 40 and left > 0:  # a bare date or heading: take in the sentence before for context
        left = max(begin(left - 2), start - 100, 0)
    right = text.find(". ", end)
    right = min(right + 1 if right >= 0 else len(text), end + 100)
    s = text[left:right].strip()
    return s if len(s) <= SNIPPET else s[:SNIPPET - 1].rstrip() + "…"


def deadlines(text: str, today: date) -> list[tuple[date, int, int]]:
    """Dates still ahead (within about a year) that sit near words about applying."""
    found = []
    for m in DATE.finditer(text):
        d = _date(m)
        if not d or not (today <= d <= date(today.year + 1, 12, 31)):
            continue
        near = text[max(0, m.start() - 120):m.end() + 40]
        if DUE_WORDS.search(near) and not NOT_DUE.search(near):
            found.append((d, m.start(), m.end()))
    return sorted(found)


def fullest(pattern: re.Pattern, text: str) -> str:
    """Of the first few places a pattern matches, the one in the fullest sentence: headlines are often cut short."""
    found = [snippet(text, m.start(), m.end()) for m in list(pattern.finditer(text))[:5]]
    return max(found, key=lambda s: (len(s.split()), -found.index(s))) if found else ""


def classify(text: str, today: date) -> dict:
    """What the page says about applying now. Keys: s (status), d (next deadline), q (the words found)."""
    due = deadlines(text, today)
    o, c = OPEN.search(text), CLOSED.search(text)
    if o and (not c or o.start() < c.start() or due):
        out = {"s": "open", "q": fullest(OPEN, text)}
        if due:
            out["d"] = due[0][0].isoformat()
        return out
    if due:
        d, a, b = due[0]
        return {"s": "deadline", "d": d.isoformat(), "q": snippet(text, a, b)}
    if c:
        return {"s": "closed", "q": fullest(CLOSED, text)}
    return {"s": "none"}


def merge(home: dict, inner: dict | None) -> dict:
    """The grants page speaks for the funder more directly than the home page, except when it says nothing."""
    if not inner or inner["s"] == "none":
        return home
    if home["s"] == "open" and inner["s"] == "deadline":
        return {**home, "d": inner["d"]}
    return inner


# ---------------- fetching ----------------

def site_url(raw) -> str:
    """A usable https URL from what the return wrote ('WWW.EXAMPLE.ORG', 'N/A', 'example.org/grants')."""
    s = present(raw).strip().strip("/").replace(" ", "")
    if not s or "." not in s or "@" in s:
        return ""
    s = s.lower() if s.isupper() else s
    if not re.match(r"^https?://", s, re.I):
        s = "https://" + s
    host = urlparse(s).netloc
    if not host or "." not in host or host.endswith((".", "-")):
        return ""
    return s


_local = threading.local()
_robots: dict[str, tuple[robotparser.RobotFileParser, list[str]]] = {}
_robots_lock = threading.Lock()


class OffLimits(Exception):
    """A page the project's crawling rule says not to read; the message is why."""


def blocked_by_terms(url: str) -> str | None:
    """Why this address's host is on the terms blocklist (a subdomain counts), or None."""
    host = (urlparse(url).hostname or "").lower().rstrip(".")
    for blocked, why in BLOCKED_HOSTS.items():
        if host == blocked or host.endswith("." + blocked):
            return why
    return None


def robots_disallows(lines: list[str], token: str, path: str) -> bool:
    """Whether robots.txt keeps `token` off `path`, read as RFC 9309 says: the groups naming it (else "*"), `*`
    and `$` in paths, the longest matching rule winning and Allow on a tie. Python's own parser ignores the
    wildcards, so this is checked on top of it."""
    groups: list[tuple[list[str], list[tuple[bool, str]]]] = []
    named = True  # the next User-agent line starts a new group
    for line in lines:
        key, colon, value = line.split("#", 1)[0].partition(":")
        key, value = key.strip().lower(), value.strip()
        if not colon:
            continue
        if key == "user-agent":
            if named:
                groups.append(([], []))
                named = False
            groups[-1][0].append(value.split("/")[0].strip().lower())
        elif key in ("allow", "disallow", "crawl-delay", "request-rate"):
            named = True  # the group's list of agents is over
            if groups and key in ("allow", "disallow"):
                groups[-1][1].append((key == "allow", value))
    token = token.lower()
    mine = [g for g in groups if any(a and a != "*" and token.startswith(a) for a in g[0])] \
        or [g for g in groups if "*" in g[0]]
    best = (0, True)  # no rule at all means allowed
    path = unquote(path)
    for _, group_rules in mine:
        for allow, pattern in group_rules:
            if not pattern:  # "Disallow:" with nothing after it disallows nothing
                continue
            end = pattern.endswith("$")
            regex = ".*".join(re.escape(unquote(part)) for part in pattern.removesuffix("$").split("*"))
            if re.match(regex + ("$" if end else ""), path):
                best = max(best, (len(pattern), allow))
    return not best[1]


def _robots_for(root: str) -> tuple[robotparser.RobotFileParser, list[str]]:
    with _robots_lock:
        if root in _robots:
            return _robots[root]
    lines: list[str] = []
    try:
        # Asked for as text: some servers answer 406 to a request for HTML, which would read as "no rules".
        r = session().get(root + "/robots.txt", timeout=TIMEOUT, allow_redirects=True,
                          headers={"Accept": "text/plain,*/*;q=0.8"})
        if r.ok and len(r.content) < 500_000:
            lines = r.text.lstrip("\ufeff").splitlines()
    except requests.RequestException:
        pass
    rp = robotparser.RobotFileParser()
    rp.parse(lines)
    with _robots_lock:
        _robots[root] = (rp, lines)
    return rp, lines


def off_limits(url: str) -> str | None:
    """Why the project may not read this page, or None when it may. A site whose terms are on the blocklist, or
    whose robots.txt keeps out this crawler, ClaudeBot or another Anthropic agent, is off limits; the user agent
    is never changed to get around it."""
    why = blocked_by_terms(url)
    if why:
        return f"site terms: {why}"  # nothing is asked of the host, robots.txt included
    p = urlparse(url)
    rp, lines = _robots_for(f"{p.scheme}://{p.netloc}")
    path = (p.path or "/") + (f"?{p.query}" if p.query else "")
    if not rp.can_fetch(AGENT, url) or robots_disallows(lines, TOKEN, path):
        return "robots.txt asks automated visitors to stay out"
    for agent in ANTHROPIC_AGENTS:
        if not rp.can_fetch(agent, url) or robots_disallows(lines, agent, path):
            return f"robots.txt keeps {agent} out, which this project treats as off limits"
    return None


def allowed(url: str) -> bool:
    return off_limits(url) is None


def fetch_page(url: str, **kwargs) -> requests.Response:
    """GET that checks every address, redirects included, before asking for it. Raises OffLimits."""
    for _ in range(MAX_REDIRECTS + 1):
        why = off_limits(url)
        if why:
            raise OffLimits(why)
        r = session().get(url, allow_redirects=False, **kwargs)
        if not r.is_redirect:
            return r
        r.close()
        url = urljoin(url, r.headers["location"])
    raise requests.TooManyRedirects(url)


def session() -> requests.Session:
    if not hasattr(_local, "s"):
        s = requests.Session()
        s.headers.update({"User-Agent": AGENT, "Accept": "text/html,application/xhtml+xml"})
        _local.s = s
    return _local.s


def get(url: str) -> tuple[str, str] | None:
    """The page's final URL and HTML, or None when it isn't reachable, isn't HTML, or is off limits."""
    try:
        with fetch_page(url, timeout=TIMEOUT, stream=True) as r:
            if not r.ok or "html" not in r.headers.get("content-type", "html").lower():
                return None
            body = b""
            for chunk in r.iter_content(65536):
                body += chunk
                if len(body) > MAX_BYTES:
                    break
            try:
                return r.url, body.decode("utf-8")
            except UnicodeDecodeError:  # most pages without UTF-8 are Windows-1252, whatever the header says
                enc = r.encoding if r.encoding and r.encoding.lower() not in ("iso-8859-1", "latin-1") else "cp1252"
                return r.url, body.decode(enc, errors="replace")
    except (OffLimits, requests.RequestException, UnicodeError, ValueError):
        return None


def check(url: str, today: date) -> dict:
    home = get(url)
    # Plain http is a second try for a broken certificate, never a way round a page that is off limits.
    if home is None and url.startswith("https://") and allowed(url):
        home = get("http://" + url[len("https://"):])
    if home is None:
        return {"s": "error"}
    final, raw = home
    result = {**classify(page_text(raw), today), "u": final}
    pages = [(final, raw)]
    inner_url = grants_page(raw, final)
    if inner_url:
        inner = get(inner_url)
        if inner:
            pages.append(inner)
            found = classify(page_text(inner[1]), today)
            if found["s"] != "none":
                merged = merge(result, found)
                result = {**merged, "u": inner[0] if merged is found else result["u"]}
    if result["s"] == "none":
        for base, page in reversed(pages):  # the grants page's own link first
            link = apply_link(page, base)
            if link:
                return {"s": "apply", "u": link}
    return result


def apply_link(raw: str, base: str) -> str | None:
    """Where an "Apply now" or "Grant application" link goes, including outside portals."""
    for url, label in links(raw, base):
        if urlparse(url).scheme in ("http", "https") and APPLY_LINK.match(label):
            return url
    return None


# ---------------- the run ----------------

def targets(states: list[str]) -> dict[str, str]:
    """EIN to website, for every foundation on the release with a usable website."""
    out: dict[str, str] = {}
    for state in states:
        for prefix in ("foundations", "community"):
            raw = fetch(f"{prefix}-{state}.json.gz", f"{prefix}/{state}.json.gz")
            if not raw:
                continue
            for rec in json.loads(gzip.decompress(raw))["foundations"]:
                url = site_url(rec.get("website"))
                if url:
                    out[str(rec["ein"])] = url
    return out


def run(sites: dict[str, str], today: date, workers: int = 48) -> dict[str, dict]:
    results: dict[str, dict] = {}
    by_url: dict[str, list[str]] = {}
    for ein, url in sites.items():
        by_url.setdefault(url.lower(), []).append(ein)  # funders sharing a site are visited once
    started = time.time()
    with ThreadPoolExecutor(workers) as pool:
        jobs = {pool.submit(check, sites[eins[0]], today): eins for eins in by_url.values()}
        for n, job in enumerate(as_completed(jobs), 1):
            try:
                found = job.result()
            except Exception:  # one odd site never stops the run
                found = {"s": "error"}
            for ein in jobs[job]:
                results[ein] = found
            if n % 500 == 0:
                print(f"{n}/{len(jobs)} sites in {time.time() - started:.0f}s", flush=True)
    return results


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    ap.add_argument("--states", help="comma-separated; default every state on the release")
    ap.add_argument("--limit", type=int, default=0, help="check only this many sites (for a trial)")
    ap.add_argument("--workers", type=int, default=48)
    args = ap.parse_args()
    states = args.states.split(",") if args.states else foundation_states()
    sites = targets(states)
    sites.update(local.site_targets())  # hand-kept programs (data/local-<ST>.json), keyed local-...
    if args.limit:
        sites = dict(list(sites.items())[:args.limit])
    print(f"{len(sites)} foundations with a website in {len(states)} states", flush=True)
    today = date.today()
    results = run(sites, today, args.workers)
    counts: dict[str, int] = {}
    for r in results.values():
        counts[r["s"]] = counts.get(r["s"], 0) + 1
    print("results:", counts)
    payload = {"checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "sites": results}
    text = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)  # a fresh runner has no build/ folder
    with open(args.out, "wb") as f:
        f.write(gzip.compress(text, compresslevel=9, mtime=0))


if __name__ == "__main__":
    main()
