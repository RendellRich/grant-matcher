"""The registry of every state's catalog (grantmatch/states.py) and how export_web reads it."""
import importlib

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
    assert set(progs) == {"CA", "IL", "IA", "NJ", "OH", "WA", "WV"}
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
    assert cat["KS"] == {"status": "unchecked", "source": "grants.ks.gov and the KS Infrastructure Hub (blocked to scripts)"}
    assert cat["AK"]["status"] == cat["HI"]["status"] == "decide"
    assert cat["WV"]["status"] == cat["NJ"]["status"] == cat["FL"]["status"] == "built"
    assert cat["PA"]["status"] == "decide" and cat["DC"]["status"] == "html"
    assert list(cat) == sorted(cat)


def test_a_state_not_yet_in_the_release_ships_from_its_snapshot_in_data(monkeypatch):
    class Missing:
        ok = False

    monkeypatch.setattr(export_web, "LOCAL_ONLY", False)
    monkeypatch.setattr(export_web.requests, "get", lambda url, timeout=None: Missing())
    for code in ("WV", "NJ"):
        name = states.STATE_PROGRAMS[code]["file"]
        raw = export_web.fetch(f"{name}.json.gz")
        assert raw == (export_web.LOCAL / f"{name}.json.gz").read_bytes(), code
        # no vectors in data/: export_web embeds those records itself (program_vectors)
        assert export_web.fetch(f"{name}.npz") is None


def test_the_committed_snapshots_have_the_same_record_fields_as_ohio():
    import gzip
    import json

    from tests.test_ohio import item
    from grantmatch import ohio
    want = set(ohio.normalize(item()))
    for name in ("westvirginia", "newjersey"):
        payload = json.loads(gzip.decompress((export_web.LOCAL / f"{name}.json.gz").read_bytes()))
        assert payload["programs"], name
        for rec in payload["programs"]:
            assert set(rec) == want, (name, rec["id"])


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
        assert (name in expected) == bool(r["refresh"]) and (name in optional) == (not r["refresh"]), code
    # the labels the Friday issue already used for the refreshed states are unchanged
    assert expected["skipped-ohio.json.gz"] == "Ohio (after the next daily refresh)"
    assert skipped.SOURCES["washington"] == "FundHubWA (Washington)"
    assert set(optional) == {"skipped-westvirginia.json.gz", "skipped-newjersey.json.gz"}


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


def test_states_the_research_couldnt_check_claim_nothing():
    unchecked = {c for c, s in states.STATES.items() if s["status"] == "unchecked"}
    assert unchecked == {"AR", "CO", "ID", "KS", "KY", "MN", "MS", "MO", "NE", "NH", "NM", "SC", "SD", "TN", "TX", "WI"}
    for code in unchecked | {c for c, s in states.STATES.items() if s["status"] == "none"}:
        assert "only" not in states.STATES[code]["source"].lower(), code   # no "agency pages only" without a check
