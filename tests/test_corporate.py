"""Company foundations entered by hand (data/corporate.json, grantmatch/corporate.py)."""
import json

import numpy as np
import pytest

from grantmatch import corporate


def test_the_real_file_loads():
    entries = corporate.load()
    assert entries and all(len(ein) == 9 for ein in entries)
    walmart = entries["205639919"]
    assert walmart["serves"] == "*" and walmart["program"]["amount"] == "$250 to $5,000"


def test_bad_entries_are_named(tmp_path):
    bad = {"ein": "12-345", "company": "", "home": "Florida", "serves": ["Florida"],
           "program": {"name": "Grants", "url": "http://example.org", "checked": "Nov 18"}}
    problems = corporate.check(bad)
    assert "ein must be 9 digits" in problems
    assert "missing company" in problems
    assert "home must be a two-letter state" in problems
    assert any(p.startswith("serves") for p in problems)
    assert "program missing who" in problems
    assert "program url must start with https://" in problems
    assert "program checked must be a yyyy-mm-dd date" in problems
    path = tmp_path / "c.json"
    ok = {"ein": "123456789", "company": "Sample", "home": "FL", "serves": None}
    path.write_text(json.dumps({"foundations": [ok, ok]}), encoding="utf-8")
    with pytest.raises(ValueError, match="listed twice"):
        corporate.load(path)


def test_national_programs_join_the_states_they_serve():
    entries = {"111111111": {"ein": "111111111", "company": "Sample Stores", "home": "AR", "serves": "*"},
               "222222222": {"ein": "222222222", "company": "Sample Grocers", "home": "FL", "serves": ["FL", "GA"]}}
    extra = {"111111111": ({"ein": "111111111", "name": "Sample Stores Foundation"}, np.ones(4, dtype=np.float16)),
             "222222222": ({"ein": "222222222", "name": "Sample Grocers Charities"}, np.ones(4, dtype=np.float16))}
    records, ids, vecs = [{"ein": "222222222"}], ["222222222"], [np.zeros((1, 4), dtype=np.float16)]
    assert corporate.add_national("FL", records, ids, vecs, extra, entries) == 1  # the grocer is already there
    assert ids == ["222222222", "111111111"] and np.concatenate(vecs).shape == (2, 4)
    records, ids, vecs = [], [], []
    assert corporate.add_national("TX", records, ids, vecs, extra, entries) == 1  # only the national one serves Texas
    assert ids == ["111111111"]


def test_overlay_keeps_the_company_and_its_program():
    assert corporate.overlay({"company": "Sample", "serves": None}) == {"company": "Sample"}
    got = corporate.overlay({"company": "Sample", "program": {"name": "Grants", "focus": ""}})
    assert got == {"company": "Sample", "program": {"name": "Grants"}}


def test_a_national_copy_drops_its_home_states_places():
    entries = {"111111111": {"ein": "111111111", "company": "Sample", "home": "AR", "serves": "*"}}
    rec = {"ein": "111111111", "hist": {"y": [2023, 2024], "n": [1, 2], "pl": {"bentonville": 2023}}}
    records, ids, vecs = [], [], []
    corporate.add_national("FL", records, ids, vecs, {"111111111": (rec, np.ones(4, dtype=np.float16))}, entries)
    assert records[0]["hist"] == {"y": [2023, 2024], "n": [1, 2]} and "pl" in rec["hist"]


def test_counties_become_places_for_their_state_only():
    entry = {"company": "Duke Energy", "counties": {"FL": ["Pinellas", "Pasco"]}}
    fl = corporate.overlay(entry, "FL")
    assert fl["area"] == "the 2 counties Duke Energy serves in Florida"
    assert {"pinellas", "pinellas county", "pasco"} <= set(fl["places"])
    assert "st. petersburg" in fl["places"]  # a Pinellas city, from data/counties.json.gz
    assert "places" not in corporate.overlay(entry, "NC") and "places" not in corporate.overlay(entry)


def test_unknown_county_names_are_rejected():
    bad = {"ein": "123456789", "company": "X", "home": "FL", "serves": None, "counties": {"FL": ["Pinelas"]}}
    assert any("no county named 'Pinelas'" in p for p in corporate.check(bad))
