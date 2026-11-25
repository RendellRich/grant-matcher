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
    assert cat["KS"] == {"status": "none", "source": "grants.ks.gov needs a login (blocked to scripts)"}
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
