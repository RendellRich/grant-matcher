import gzip
import json
from datetime import date

from grantmatch.changes import current, load_previous, update

D1, D2, D3, D4 = date(2026, 11, 17), date(2026, 11, 18), date(2026, 11, 19), date(2026, 11, 20)


def fed(**recs):
    return {f"fed:{k}": {"d": d, "s": s} for k, (d, s) in recs.items()}


def kinds(result):
    return [(e["k"], e["kind"], e["from"], e["to"]) for e in result["events"]]


def test_first_run_is_a_baseline_with_no_events():
    r = update(None, {"fed": fed(a=("2027-03-01", "posted")), "fdn": None}, D1)
    assert r["baseline"] is True and r["events"] == []
    assert r["records"] == {"fed:a": {"d": "2027-03-01", "s": "posted"}}


def test_moved_set_cleared_and_posted():
    prev = update(None, {"fed": fed(a=("2027-02-15", "posted"), b=(None, "forecasted"), c=("2027-01-10", "posted")), "fdn": None}, D1)
    r = update(prev, {"fed": fed(a=("2027-03-01", "posted"), b=("2027-04-01", "posted"), c=(None, "posted")), "fdn": None}, D2)
    assert r["baseline"] is False
    assert sorted(kinds(r)) == sorted([
        ("fed:a", "moved", "2027-02-15", "2027-03-01"),
        ("fed:b", "set", None, "2027-04-01"),
        ("fed:b", "posted", "forecasted", "posted"),
        ("fed:c", "cleared", "2027-01-10", None),
    ])
    assert all(e["at"] == "2026-11-18" for e in r["events"])


def test_unchanged_data_makes_no_events():
    now = {"fed": fed(a=("2027-02-15", "posted")), "fdn": {"fdn:1": {"d": None, "s": "open"}}}
    prev = update(None, now, D1)
    assert update(prev, now, D2)["events"] == []


def test_funder_websites_close_and_reopen():
    prev = update(None, {"fed": None, "fdn": {"fdn:1": {"d": "2027-01-15", "s": "deadline"}, "fdn:2": {"d": None, "s": "closed"}}}, D1)
    r = update(prev, {"fed": None, "fdn": {"fdn:1": {"d": None, "s": "closed"}, "fdn:2": {"d": None, "s": "open"}}}, D2)
    assert ("fdn:1", "closed", "deadline", "closed") in kinds(r)
    assert ("fdn:2", "reopened", "closed", "open") in kinds(r)


def test_a_one_day_dropout_makes_no_event_and_a_longer_one_is_gone():
    many = {str(i): ("2027-01-01", "posted") for i in range(10)}
    prev = update(None, {"fed": fed(**many), "fdn": None}, D1)
    without = {k: v for k, v in many.items() if k != "3"}
    day2 = update(prev, {"fed": fed(**without), "fdn": None}, D2)
    assert day2["events"] == [] and day2["records"]["fed:3"]["m"] == "2026-11-18"
    back = update(day2, {"fed": fed(**many), "fdn": None}, D3)
    assert back["events"] == [] and "m" not in back["records"]["fed:3"]
    day3 = update(day2, {"fed": fed(**without), "fdn": None}, D3)
    day4 = update(day3, {"fed": fed(**without), "fdn": None}, D4)
    assert day3["events"] == []
    assert kinds(day4) == [("fed:3", "gone", "2027-01-01", None)]
    assert "fed:3" not in day4["records"]


def test_a_failed_or_short_fetch_is_carried_over_quietly():
    many = {str(i): ("2027-01-01", "posted") for i in range(10)}
    prev = update(None, {"fed": fed(**many), "fdn": {"fdn:1": {"d": None, "s": "open"}}}, D1)
    missing = update(prev, {"fed": None, "fdn": {"fdn:1": {"d": None, "s": "open"}}}, D2)
    assert missing["events"] == [] and missing["records"] == prev["records"]
    short = update(prev, {"fed": fed(**{"0": ("2027-05-05", "posted")}), "fdn": {"fdn:1": {"d": None, "s": "open"}}}, D2)
    assert short["events"] == [] and short["records"]["fed:0"]["d"] == "2027-01-01"


def test_old_events_are_dropped_after_60_days():
    prev = {"records": {}, "events": [{"k": "fed:x", "kind": "moved", "from": "a", "to": "b", "at": "2026-09-01"},
                                      {"k": "fed:y", "kind": "moved", "from": "a", "to": "b", "at": "2026-10-01"}]}
    r = update(prev, {"fed": {}, "fdn": None}, D1)
    assert [e["k"] for e in r["events"]] == ["fed:y"]


def test_reads_the_exported_files(tmp_path):
    def gz(name, payload):
        (tmp_path / name).write_bytes(gzip.compress(json.dumps(payload).encode()))
    gz("federal.json.gz", {"records": [{"id": 9, "close_date": "2027-02-01T00:00:00", "status": "posted"}, {"id": 8, "close_date": "", "status": "forecasted"}]})
    gz("foundations-FL.json.gz", {"records": [
        {"ein": "11", "_cycle": {"s": "deadline", "d": "2027-01-15", "q": "x", "at": "2026-11-15"}},
        {"ein": "12", "_cycle": {"s": "apply", "u": "https://x"}}, {"ein": "13"}]})
    now = current(tmp_path)
    assert now["fed"] == {"fed:9": {"d": "2027-02-01", "s": "posted"}, "fed:8": {"d": None, "s": "forecasted"}}
    assert now["fdn"] == {"fdn:11": {"d": "2027-01-15", "s": "deadline"}}
    assert current(tmp_path / "nothing") == {"fed": None, "fdn": None, "fl": None}


def test_previous_file_that_cannot_be_read_is_none(tmp_path):
    assert load_previous(None) is None
    assert load_previous(str(tmp_path / "missing.json")) is None
    bad = tmp_path / "bad.json"
    bad.write_text("not json", encoding="utf-8")
    assert load_previous(str(bad)) is None
