"""The freshness check (grantmatch/freshness.py), its place in the weekly page watch, and the "last checked"
stamps the export writes. No network: the release, the link reader and robots.txt are passed in."""
import gzip
import json
import sys
from datetime import date
from urllib import robotparser

import pytest

from grantmatch import cycles, export_web, freshness, states, watch
from grantmatch.match import Profile
from grantmatch.rank_more import score_florida

TODAY = date(2026, 11, 26)


def gz(obj) -> bytes:
    return gzip.compress(json.dumps(obj).encode("utf-8"))


def no_release(name, head=False):
    return None


def fake_data(tmp_path):
    """A tiny data/ folder: one state call, one hand-kept file, one company program."""
    (tmp_path / "california.json.gz").write_bytes(gz({"fetched_at": "2026-11-01T00:00+00:00", "programs": [
        {"id": "ca-1", "title": "Open call", "url": "https://calls.example.org/open", "closes": "2027-01-01"},
        {"id": "ca-2", "title": "Closed call", "url": "https://calls.example.org/closed", "closes": "2026-11-01"}]}))
    entry = {"slug": "old-grant", "title": "Old Grant", "url": "https://county.example.org/old", "checked": "2026-07-01",
             "closes": "2026-09-01"}
    rolling = {"slug": "any-time", "title": "Any Time", "url": "https://county.example.org/any", "checked": "2026-11-20",
               "rolling": True, "closes": None}
    (tmp_path / "local-FL.json").write_text(json.dumps({"programs": [entry, rolling]}), encoding="utf-8")
    (tmp_path / "corporate.json").write_text(json.dumps({"foundations": [
        {"ein": "1", "company": "Sample Co", "program": {"url": "https://sample.example.com/giving", "checked": "2026-11-20"}}]}),
        encoding="utf-8")
    return tmp_path


def test_the_inventory_has_every_source_and_every_built_state():
    sources, links, _ = freshness.inventory(TODAY, no_release)
    keys = {s["key"] for s in sources}
    assert {"federal", "foundations", "community", "corporate", "counties", "websites", "coverage"} <= keys
    built = {c for c, s in states.STATES.items() if s["status"] == "built"}
    assert {f"state:{c}" for c in built} <= keys and "state:FL" in keys
    assert {f"local:{p.stem.split('-')[1]}" for p in freshness.DATA.glob("local-??.json")} <= keys
    for code in built:
        for url in states.STATES[code]["pages"]:
            assert url in links, code
    for s in sources:
        assert s["limit"] == freshness.MAX_DAYS[s["every"]], s["key"]
    # Florida's catalog pages are read by the Florida refresh, so they aren't opened again
    assert not [u for u in links if "searchCatalogResultsDetail" in u]


def test_the_registry_pages_match_what_the_adapters_read():
    from grantmatch import districtofcolumbia, minnesota, newjersey, newyork
    assert states.STATES["DC"]["pages"] == [districtofcolumbia.LIST]
    assert states.STATES["MN"]["pages"] == [minnesota.HEALTH, minnesota.JUSTICE]
    assert states.STATES["NJ"]["pages"] == [newjersey.SITE]
    assert states.STATES["NY"]["pages"] == [newyork.SITE]
    assert states.check() == []


def test_a_source_is_old_past_its_own_limit_or_without_a_date():
    def stale(every, stamp):
        return freshness.source("k", "n", every, stamp, "release", TODAY)["stale"]

    assert not stale("daily", "2026-11-23T10:00+00:00") and stale("daily", "2026-11-22T10:00+00:00")
    assert not stale("weekly", "2026-11-16") and stale("weekly", "2026-11-15")
    assert not stale("by hand", "2026-08-28") and stale("by hand", "2026-08-27")
    assert stale("monthly", None) and stale("monthly", "not a date")


def test_the_date_is_read_from_the_start_of_a_cut_off_file():
    whole = gz({"fetched_at": "2026-11-13T14:11+00:00", "foundations": [{"name": "x" * 40}] * 5000})
    assert freshness.stamp_of(whole[:600]) == "2026-11-13T14:11+00:00"
    assert freshness.stamp_of(gz({"checked_at": "2026-11-18T19:00:00+00:00", "sites": {}})).startswith("2026-11-18")
    assert freshness.stamp_of(b'{"made_at": "2026-11-19T09:41+00:00"}').startswith("2026-11-19")
    assert freshness.stamp_of(b"") is None and freshness.stamp_of(b"\x1f\x8bjunk") is None


def test_dead_is_404_or_410_or_unreachable_on_two_checks_in_a_row():
    assert freshness.remember(None, freshness.from_code(404), TODAY)["s"] == "dead"
    assert freshness.remember(None, freshness.from_code(410), TODAY)["s"] == "dead"
    down = {"s": "unreachable", "why": "ConnectTimeout"}
    first = freshness.remember(None, down, TODAY)
    assert first["s"] == "unreachable"
    assert freshness.remember(first, down, TODAY)["s"] == "unreachable"  # a second run the same day isn't a second check
    assert freshness.remember(first, down, date(2026, 12, 3))["s"] == "dead"
    ok = freshness.remember(first, {"s": "ok"}, date(2026, 12, 3))
    assert ok == {"s": "ok", "d": "2026-12-03"}
    assert freshness.remember(ok, down, date(2026, 12, 10))["s"] == "unreachable"
    # unreachable, then not looked at, then unreachable is not twice in a row
    shut = freshness.remember(first, {"s": "blocked", "why": "robots.txt could not be read"}, date(2026, 12, 3))
    assert freshness.remember(shut, down, date(2026, 12, 10))["s"] == "unreachable"


def test_blocked_and_refused_pages_are_never_dead():
    for reading in ({"s": "blocked", "why": "robots.txt could not be read"}, freshness.from_code(403),
                    freshness.from_code(429)):
        memory = None
        for day in (TODAY, date(2026, 12, 3), date(2026, 12, 10)):
            memory = freshness.remember(memory, reading, day)
        assert memory["s"] in ("blocked", "refused") and memory["b"] == 3
    assert freshness.from_code(503)["s"] == "unreachable" and freshness.from_code(200) == {"s": "ok"}


def test_the_page_watchs_readings_become_link_results():
    assert freshness.from_watch({"s": "ok", "text": "hi"}) == {"s": "ok"}
    assert freshness.from_watch({"s": "error", "why": "HTTP 404"})["s"] == "gone"
    assert freshness.from_watch({"s": "error", "why": "HTTP 403"})["s"] == "refused"
    assert freshness.from_watch({"s": "error", "why": "ConnectionError"})["s"] == "unreachable"
    assert freshness.from_watch({"s": "error", "why": "could not read the file (ValueError)"}) == {"s": "ok"}
    assert freshness.from_watch({"s": "blocked", "why": "site terms: no"})["s"] == "blocked"


def test_a_page_off_limits_is_never_asked_for(monkeypatch):
    lines = "User-agent: ClaudeBot\nDisallow: /".splitlines()
    rp = robotparser.RobotFileParser()
    rp.parse(lines)
    monkeypatch.setattr(cycles, "_robots", {"https://example.org": (rp, lines), "https://down.example.org": None})

    def no_network():
        raise AssertionError("no request may be made")

    monkeypatch.setattr(cycles, "session", no_network)
    assert freshness.link_reading("https://example.org/grants")["s"] == "blocked"
    assert freshness.link_reading("https://down.example.org/x") == {"s": "blocked", "why": cycles.UNREAD_ROBOTS}
    assert freshness.link_reading("https://www.in.gov/grants")["s"] == "blocked"
    assert freshness.host_delay("https://www.in.gov/grants") == 0.0  # not even its robots.txt is asked for


def test_hosts_are_spaced_out_and_a_crawl_delay_is_honored(monkeypatch):
    rules = {}
    for root, text in (("https://slow.example.org", "User-agent: *\nCrawl-delay: 7"), ("https://a.example.org", ""),
                       ("https://communityaffairs.dc.gov", "")):
        rp = robotparser.RobotFileParser()
        rp.parse(text.splitlines())
        rules[root] = (rp, text.splitlines())
    monkeypatch.setattr(cycles, "_robots", rules)
    assert freshness.host_delay("https://slow.example.org/x") == 7
    assert freshness.host_delay("https://a.example.org/x") == freshness.HOST_DELAY
    assert freshness.host_delay("https://communityaffairs.dc.gov/node/26") == 10


def test_each_request_waits_and_the_time_budget_leaves_the_rest_for_later():
    now = [0.0]
    waits, asked = [], []

    def sleep(s):
        waits.append(s)
        now[0] += s

    urls = [f"https://one.example.org/{i}" for i in range(6)]
    readings, stats = freshness.check_links(urls, reader=lambda u: asked.append(u) or {"s": "ok"}, delay=lambda u: 10,
                                            sleep=sleep, clock=lambda: now[0], budget=35, workers=1, off=lambda u: None)
    assert asked == urls[:3] and waits == [10, 10, 10]
    assert (stats["pages"], stats["deferred"], stats["hosts"]) == (3, 3, 1) and set(readings) == set(urls[:3])
    # a page off limits is neither asked for nor waited for
    now[0], waits[:], asked[:] = 0.0, [], []
    readings, stats = freshness.check_links(urls[:3], reader=lambda u: asked.append(u) or {"s": "ok"},
                                            delay=lambda u: 10, sleep=sleep, clock=lambda: now[0], budget=35,
                                            workers=1, off=lambda u: "keeps out" if u == urls[0] else None)
    assert asked == urls[1:3] and waits == [10, 10] and readings[urls[0]] == {"s": "blocked", "why": "keeps out"}
    assert (stats["pages"], stats["blocked"], stats["deferred"]) == (2, 1, 0)


def test_the_plan_is_capped_and_takes_the_most_needed_first():
    many = [f"https://big.example.org/{i:03d}" for i in range(50)]
    others = [f"https://h{i}.example.org/" for i in range(200)]
    memory = {many[49]: {"s": "unreachable", "d": "2026-11-19", "n": 1}, others[0]: {"s": "ok", "d": "2026-11-19"},
              others[1]: {"s": "ok", "d": "2026-11-12"}}
    source_page = others[199]
    chosen = freshness.plan(many + others, {source_page}, memory)
    assert len(chosen) == freshness.MAX_PAGES
    assert chosen[:2] == [many[49], source_page]  # confirm a failure, then the sources' own pages
    assert sum(u.startswith("https://big.") for u in chosen) == freshness.PER_HOST
    assert others[0] not in chosen  # checked ones wait behind links never checked
    memory[others[2]] = {"s": "blocked", "d": "2026-11-01", "b": 3}
    few = freshness.plan([others[0], others[1], others[2]], set(), memory)
    assert few == [others[1], others[0], others[2]]  # longest unchecked first, off limits last


def test_past_closing_dates_with_no_next_round_are_found():
    base = {"title": "T", "slug": "a", "closes": "2026-09-01"}
    entries = [("FL", base), ("FL", dict(base, slug="rolling", rolling=True)),
               ("FL", dict(base, slug="ahead", closes="2027-01-01")), ("FL", dict(base, slug="open-now")),
               ("TX", dict(base, slug="tx"))]
    found = freshness.past_deadlines(entries, {"local-open-now": {"s": "open"}}, TODAY)
    assert [(p["list"], p["key"]) for p in found] == [("local-FL", "a"), ("local-TX", "tx")]


def run_check(tmp_path, previous=None, watched=None, today=TODAY, answers=None):
    answers = answers or {}
    asked = []

    def linker(urls):
        asked.extend(urls)
        got = {u: answers.get(u, {"s": "ok"}) for u in urls}
        return got, {"pages": len(got), "hosts": 2, "deferred": 0, "seconds": 3}

    result = freshness.check(previous, watched or {}, today, release=no_release, data_dir=fake_data(tmp_path), linker=linker)
    return result, asked


def test_one_run_flags_old_data_dead_links_and_past_deadlines(tmp_path):
    watched = {"https://county.example.org/old": {"s": "error", "why": "HTTP 404"},
               "https://county.example.org/any": {"s": "blocked", "why": "robots.txt could not be read"},
               "https://sample.example.com/giving": {"s": "ok", "text": "x"}}
    answers = {"https://calls.example.org/closed": {"s": "gone", "why": "HTTP 410"},
               "https://calls.example.org/open": {"s": "blocked", "why": "robots.txt keeps ClaudeBot out"}}
    result, asked = run_check(tmp_path, watched=watched, answers=answers)
    assert not set(watched) & set(asked)  # the page watch already read those
    text = result["text"]
    memory = result["memory"]["links"]
    assert memory["https://county.example.org/old"]["s"] == "dead"
    assert memory["https://calls.example.org/closed"]["s"] == "dead"
    assert memory["https://county.example.org/any"]["s"] == "blocked"
    assert "## Dead links" in text and "HTTP 410" in text and "local-FL: old-grant" in text
    assert "## Closing date passed, no next round entered" in text and "`old-grant`" in text
    assert "state:CA" in text and "25 days old" in text
    blocked = text[text.index("## Not checked"):text.index("## Every source")]
    assert "calls.example.org" in blocked and "county.example.org" not in blocked  # the watch lists its own
    dead = [u for u, m in memory.items() if m["s"] == "dead"]
    assert result["flagged"] == len(dead) + len(result["past"]) + sum(s["stale"] for s in result["sources"])
    assert "\u2014" not in text


def test_a_link_unreachable_two_weeks_running_turns_dead(tmp_path):
    down = {"https://calls.example.org/open": {"s": "unreachable", "why": "ReadTimeout"}}
    first, _ = run_check(tmp_path, answers=down)
    assert first["memory"]["links"]["https://calls.example.org/open"]["s"] == "unreachable"
    assert "Didn't open once" in first["text"]
    second, asked = run_check(tmp_path, previous=first["memory"], answers=down, today=date(2026, 12, 3))
    assert asked[0] == "https://calls.example.org/open"  # confirmed first
    assert second["memory"]["links"]["https://calls.example.org/open"]["s"] == "dead"


# ---------------- inside the page watch ----------------

PAGE = "The city gives grants of up to $2,500 to small arts nonprofits in the city. " * 6
ROW = {"list": "local-FL", "key": "sample", "name": "Sample", "checked": "2026-11-20", "url": "https://example.org/a"}


def run_watch(tmp_path, monkeypatch, check):
    out = tmp_path / "output"
    state, report = tmp_path / "state.json.gz", tmp_path / "report.md"
    monkeypatch.setattr(watch, "targets", lambda: [ROW])
    monkeypatch.setattr(watch, "read", lambda url: {"s": "ok", "text": PAGE})
    monkeypatch.setattr(freshness, "check", check)
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.setattr(sys, "argv", ["watch", "--state", str(state), "--report", str(report), "--today", "2026-11-26"])
    watch.main()
    return watch.load_state(state), report.read_text(encoding="utf-8"), out.read_text(encoding="utf-8")


def test_a_freshness_error_never_stops_the_page_watch(tmp_path, monkeypatch):
    earlier = {"checked": "2026-11-19", "links": {"https://example.org/b": {"s": "dead", "d": "2026-11-19"}}}
    watch.save_state(tmp_path / "state.json.gz", {"_freshness": earlier})

    def broken(*args, **kwargs):
        raise RuntimeError("boom")

    state, report, out = run_watch(tmp_path, monkeypatch, broken)
    assert state[ROW["url"]]["fp"] and state["_freshness"] == earlier  # this week's pages kept, last results too
    assert "# Page watcher" in report and "freshness check did not finish (RuntimeError)" in report
    assert out == "flagged=1\n"


def test_the_freshness_results_join_the_report_state_and_count(tmp_path, monkeypatch):
    seen = {}

    def ok(previous, readings, today):
        seen.update(readings)
        return {"text": "# Freshness check\n\nTwo things.\n", "flagged": 2, "memory": {"links": {}}}

    state, report, out = run_watch(tmp_path, monkeypatch, ok)
    assert list(seen) == [ROW["url"]]  # handed what the watch had just read
    assert state["_freshness"] == {"links": {}} and set(state) == {ROW["url"], "_freshness"}
    assert report.index("# Page watcher") < report.index("# Freshness check")
    assert out == "flagged=2\n"


def test_the_combined_report_fits_in_a_github_issue():
    long = watch.with_freshness("page line\n" * 20000, "fresh line\n" * 10000)
    assert len(long) <= watch.MAX_REPORT and "page line" in long and "fresh line" in long and "Cut to fit" in long
    assert watch.with_freshness("a\n", "b\n") == "a\n\nb\n"


# ---------------- "last checked" on records ----------------

RECORD = {"id": "fl-1", "csfa": "1", "title": "Reading Program", "agency": "Dept", "objectives": "literacy for children",
          "assistance": "Grant", "applicant_types": "Nonprofit organizations", "nonprofit_eligible": True,
          "earmark": False, "restrictions": "", "application": "", "award": "", "deadlines": "", "contact": "",
          "web": "", "subjects": "", "url": "https://example.org/a"}


def test_records_are_stamped_with_when_their_source_was_read_and_the_link_result():
    links = {"https://example.org/a": {"s": "dead", "d": "2026-11-26"},
             "https://example.org/b": {"s": "blocked", "d": "2026-11-26"},
             "https://example.org/c": {"s": "ok", "d": "2026-11-19"}}
    recs = [dict(RECORD), dict(RECORD, url="https://example.org/b", checked="2026-11-18"),
            dict(RECORD, url="https://example.org/c"), dict(RECORD, url="https://example.org/unknown")]
    export_web.stamp(recs, "2026-11-23T21:53+00:00", links)
    assert (recs[0]["_checked"], recs[0]["_link"], recs[0]["_link_at"]) == ("2026-11-23T21:53+00:00", "dead", "2026-11-26")
    assert recs[1]["_checked"] == "2026-11-18" and "_link" not in recs[1]  # hand-kept date; a blocked page says nothing
    assert recs[2]["_link"] == "ok" and "_link" not in recs[3]
    bare = export_web.stamp([dict(RECORD)], "")
    assert bare == [RECORD]


def test_stamps_never_change_a_score():
    profile = Profile(mission="literacy", keywords=["literacy", "children"], has_501c3="Yes", budget_band="$50k to $250k",
                      can_cost_share=False, categories=[], today=TODAY)
    plain = score_florida([dict(RECORD)], profile, {"fl-1": 0.6})
    marked = score_florida(export_web.stamp([dict(RECORD)], "2026-11-23", {RECORD["url"]: {"s": "dead", "d": "2026-11-26"}}),
                           profile, {"fl-1": 0.6})
    for column in ("score", "tier", "reasons", "cautions"):
        assert list(plain[column]) == list(marked[column]), column


def test_the_export_reads_link_results_from_the_published_watch_state(monkeypatch):
    links = {"https://example.org/a": {"s": "ok", "d": "2026-11-26"}}
    monkeypatch.setattr(export_web, "fetch", lambda name, local=None: gz({"_freshness": {"links": links}}))
    assert export_web.link_checks() == links
    for raw in (None, gz({"https://example.org/a": {"fp": "x"}}), b"not gzip", gz([1])):
        monkeypatch.setattr(export_web, "fetch", lambda name, local=None, raw=raw: raw)
        assert export_web.link_checks() == {}


def test_a_company_program_page_that_did_not_open_is_marked():
    recs = [{"_corp": {"program": {"url": "https://example.org/a"}}}, {"_corp": {"company": "x"}}, {}]
    export_web.stamp_company_links(recs, {"https://example.org/a": {"s": "dead", "d": "2026-11-26"}})
    assert recs[0]["_corp"]["program"]["link"] == "dead" and recs[1:] == [{"_corp": {"company": "x"}}, {}]


def test_the_release_reader_stops_at_its_time_budget():
    now = [0.0]
    release = freshness.Release(budget=5, clock=lambda: now[0])
    release.until = 5.0
    now[0] = 6.0
    assert release("opportunities.json.gz") is None and release.failed == ["opportunities.json.gz"]


@pytest.mark.parametrize("path", ["grantmatch/freshness.py", "grantmatch/refresh_states.py", "docs/freshness.md",
                                  "docs/proposed-workflows/refresh-states.yml.txt"])
def test_no_em_dashes_in_what_this_adds(path):
    assert "\u2014" not in (export_web.LOCAL.parent / path).read_text(encoding="utf-8")
