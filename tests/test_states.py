"""The registry of every state's catalog (grantmatch/states.py) and how export_web reads it."""
import importlib
from pathlib import Path

from grantmatch import export_web, states


def test_every_state_and_dc_has_one_entry_with_a_known_status():
    assert states.check() == []
    assert len(states.STATES) == 51 and "DC" in states.STATES and "PR" not in states.STATES


def test_state_programs_come_from_the_registry_and_keep_the_existing_states_as_they_were():
    progs = states.STATE_PROGRAMS
    assert "FL" not in progs   # Florida keeps its own export
    assert progs["CA"] == {"file": "california", "source": "California Grants Portal", "catalog": "Grants Portal"}
    assert progs["IL"] == {"file": "illinois", "source": "Illinois Catalog of State Financial Assistance", "catalog": "Illinois NOFO"}
    assert progs["IA"] == {"file": "iowa", "source": "IowaGrants.gov", "catalog": "IowaGrants"}
    assert progs["OH"] == {"file": "ohio", "source": "Ohio Grants Partnership", "catalog": "Ohio"}
    assert progs["WA"] == {"file": "washington", "source": "FundHubWA (Washington Department of Commerce)", "catalog": "FundHubWA"}
    assert set(progs) == {"CA", "DC", "IL", "IA", "MN", "NJ", "NY", "OH", "WA", "WV"}
    assert [c for c, s in progs.items() if "who_listed" in s] == ["DC", "NJ"]   # lists with no eligibility field
    assert progs["DC"]["who_listed"] is progs["NJ"]["who_listed"] is False
    assert export_web.STATE_PROGRAMS is progs


def test_each_built_state_has_an_adapter_with_the_shared_shape():
    for code, s in states.STATES.items():
        if s["status"] != "built":
            continue
        mod = importlib.import_module(f"grantmatch.{s['module']}")
        assert hasattr(mod, "build"), code
        if code != "FL":
            assert hasattr(mod, "build_records"), code


def test_meta_says_which_states_have_no_catalog():
    cat = states.catalogs()
    assert cat["AL"] == {"status": "blocked", "source": "adeca.alabama.gov (its robots.txt disallows ClaudeBot)"}
    assert cat["AK"]["status"] == cat["HI"]["status"] == "decide"
    assert cat["WV"]["status"] == cat["NJ"]["status"] == cat["FL"]["status"] == "built"
    assert cat["PA"]["status"] == "decide" and cat["DC"]["status"] == cat["NY"]["status"] == cat["MN"]["status"] == "built"
    assert list(cat) == sorted(cat)


def test_a_state_not_yet_in_the_release_ships_from_its_snapshot_in_data(monkeypatch):
    class Missing:
        ok = False

    monkeypatch.setattr(export_web, "LOCAL_ONLY", False)
    monkeypatch.setattr(export_web.requests, "get", lambda url, timeout=None: Missing())
    for code in ("WV", "NJ", "NY", "DC", "MN"):
        name = states.STATE_PROGRAMS[code]["file"]
        raw = export_web.fetch(f"{name}.json.gz")
        assert raw == (export_web.LOCAL / f"{name}.json.gz").read_bytes(), code
        # no vectors in data/: export_web embeds those records itself (program_vectors)
        assert export_web.fetch(f"{name}.npz") is None


def test_the_committed_snapshots_have_the_same_record_fields_as_ohio():
    import gzip
    import json
    import re

    from tests.test_ohio import item
    from grantmatch import ohio
    want = set(ohio.normalize(item()))
    email = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
    for name in ("westvirginia", "newjersey", "newyork", "districtofcolumbia", "minnesota"):
        payload = json.loads(gzip.decompress((export_web.LOCAL / f"{name}.json.gz").read_bytes()))
        assert payload["programs"] and payload["count"] == len(payload["programs"]), name
        assert len({r["id"] for r in payload["programs"]}) == len(payload["programs"]), name
        for rec in payload["programs"]:
            assert set(rec) == want, (name, rec["id"])
            assert not [k for k, v in rec.items() if isinstance(v, str) and email.search(v)], (name, rec["id"])


def test_the_skipped_report_takes_every_built_state_from_the_registry():
    from grantmatch import skipped
    built = {s["file"] for c, s in states.STATES.items() if s["status"] == "built" and c != "FL"}
    assert set(skipped.STATE_SOURCES) == built
    assert all(src in skipped.SOURCES for src in built | {"florida"})
    expected, optional = skipped.expected_parts()
    for code, r in states.REPORT.items():
        if code == "FL":
            continue
        name = f"skipped-{r['source']}.json.gz"
        wanted = bool(r["refresh"]) and r["in_skip_report"]
        assert (name in expected) == wanted and (name in optional) == (not wanted), code
    # the labels the Friday issue already used for the refreshed states are unchanged
    assert expected["skipped-ohio.json.gz"] == "Ohio (after the next daily refresh)"
    assert skipped.SOURCES["washington"] == "FundHubWA (Washington)"
    assert set(optional) == {f"skipped-{n}.json.gz" for n in
                             ("westvirginia", "newjersey", "newyork", "districtofcolumbia", "minnesota")}


def test_the_skipped_report_accepts_a_programs_file_for_every_built_state(tmp_path, monkeypatch):
    import gzip
    import json
    import sys

    from grantmatch import skipped
    parts = tmp_path / "parts"
    parts.mkdir()
    args = ["skipped", "--parts", str(parts), "--csv", str(tmp_path / "out.csv"), "--md", str(tmp_path / "out.md")]
    for src in skipped.STATE_SOURCES:
        f = tmp_path / f"{src}.json.gz"
        f.write_bytes(gzip.compress(json.dumps({"programs": [{"id": f"{src}-1", "title": "A", "nonprofit_eligible": False,
                                                              "earmark": False, "agency": "X", "url": ""}]}).encode()))
        args += [f"--{src}", str(f)]
    monkeypatch.setattr(sys, "argv", args)
    skipped.main()
    report = (tmp_path / "out.md").read_text(encoding="utf-8")
    for src in skipped.STATE_SOURCES:
        assert f"## {skipped.SOURCES[src]} (1)" in report, src


def test_closed_calls_are_left_out_at_export_and_open_ones_kept():
    from datetime import date
    recs = [{"id": "a", "closes": "2026-11-24"}, {"id": "b", "closes": "2026-11-25"}, {"id": "c", "closes": None},
            {"id": "d"}, {"id": "e", "closes": ""}]
    kept, closed = export_web.still_open(recs, date(2026, 11, 25))
    assert [r["id"] for r in kept] == ["b", "c", "d", "e"] and closed == 1


def test_the_export_drops_closed_snapshot_calls_but_not_florida_or_hand_kept_programs():
    import inspect
    src = inspect.getsource(export_web.main)
    loop = src[src.index("for state, spec in STATE_PROGRAMS.items()"):]
    # still_open runs on the adapter's records before the hand-kept ones join, and never on Florida's
    assert loop.index("still_open(payload[\"programs\"]") < loop.index("local_programs.load(state=state)")
    assert "still_open" not in inspect.getsource(export_web.florida_records)
    assert "still_open" not in src[:src.index("for state, spec in STATE_PROGRAMS.items()")]


def test_every_state_has_the_status_the_research_established():
    by = {st: {c for c, s in states.STATES.items() if s["status"] == st} for st in states.STATUSES}
    assert by["built"] == {"CA", "DC", "FL", "IA", "IL", "MN", "NJ", "NY", "OH", "WA", "WV"}
    # robots.txt, terms or a refusal to scripts keep the pages out
    assert by["blocked"] == {"AL", "CO", "IN", "LA", "ME", "NC", "NE", "NH", "NM", "NV", "RI", "TX", "VT", "WI"}
    assert by["unchecked"] == {"MS"}   # the only one the research couldn't establish
    # "none" only where nowhere the research looked posts current state calls
    assert by["none"] == {"AZ", "DE", "OR"} and by["decide"] == {"AK", "HI", "PA"} and by["next"] == set()
    assert len(by["html"]) == 19 and {"KS", "MD", "TN"} <= by["html"]


def test_nothing_learned_from_a_page_we_may_not_use_is_recorded():
    root = Path(export_web.__file__).parent.parent
    text = "".join((root / p).read_text(encoding="utf-8") for p in
                   ("grantmatch/states.py", "docs/state-coverage.md", "README.md"))
    for gone in ("adeca.alabama.gov/about", "grants/calendar", "kansascommerce.gov/grantscalendar", "crt.state.la.us/",
                 "crt.louisiana.gov/", "gn.ecivis.com/GO", "airtable.com/app", "txsmartbuy.gov/esbd", "maine.gov/moca",
                 "gov.texas.gov/", "(gov.texas.gov)", "Governor's site policies"):
        assert gone not in text, gone
    # gov.texas.gov's robots.txt keeps ClaudeBot out, so Texas's reason doesn't use what its pages say
    assert states.STATES["TX"]["source"] == ("txsmartbuy.gov robots.txt disallows all crawlers; "
                                             "no usable terms were confirmed for the eGrants page")


def test_the_new_states_have_no_refresh_job_yet():
    for code in ("NY", "DC", "MN"):
        assert states.STATES[code]["refresh"] is None and states.REPORT[code]["in_skip_report"] is False, code


def test_west_virginia_and_new_jersey_refresh_weekly_but_the_friday_report_doesnt_expect_them_yet():
    from grantmatch import skipped
    for code in ("WV", "NJ"):
        assert states.STATES[code]["refresh"] == "weekly" and states.REPORT[code]["in_skip_report"] is False, code
    expected, optional = skipped.expected_parts()
    # skipped-report.yml doesn't download these files yet, so the report must not list them as missing
    assert "skipped-westvirginia.json.gz" not in expected and "skipped-newjersey.json.gz" not in expected
    assert {"skipped-westvirginia.json.gz", "skipped-newjersey.json.gz"} <= set(optional)
    workflow = (Path(export_web.__file__).parent.parent / ".github" / "workflows" / "skipped-report.yml").read_text(encoding="utf-8")
    assert "skipped-westvirginia" not in workflow and "skipped-newjersey" not in workflow   # flip in_skip_report when it does


def test_the_state_refresh_workflow_runs_the_registry_states_weekly_and_publishes_what_the_export_reads():
    import re
    path = Path(export_web.__file__).parent.parent / ".github" / "workflows" / "refresh-states.yml"
    text = path.read_text(encoding="utf-8")
    assert re.search(r'^\s*- cron: "17 13 \* \* 1"', text, re.M)   # weekly, Mondays 13:17 UTC
    refreshed = [c for c, s in states.STATES.items() if s.get("refresh") == "weekly" and c != "FL"]
    assert sorted(refreshed) == ["NJ", "WV"]
    uploads = re.search(r"gh release upload data-latest (.+?) --clobber", text).group(1).split()
    want = []
    for code in refreshed:
        f = states.STATE_PROGRAMS[code]["file"]
        assert f"python -m grantmatch.{states.STATES[code]['module']} --out build/{f}.json.gz --skipped build/skipped-{f}.json.gz" in text
        assert f"python -m grantmatch.embed programs build/{f}.json.gz build/{f}.npz" in text
        # the names export_web.fetch asks the release for, and the skipped file the report would read
        want += [f"build/{f}.json.gz", f"build/{f}.npz", f"build/skipped-{f}.json.gz"]
    assert sorted(uploads) == sorted(want) and len(uploads) == 6
    assert "refresh-states.yml/enable" in text
