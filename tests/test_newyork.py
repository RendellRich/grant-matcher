"""New York's Statewide Financial System grant grid into state program records (grantmatch/newyork.py)."""
import gzip
import json
from pathlib import Path

import pytest

from grantmatch import newyork as ny

PAGE = (Path(__file__).parent / "fixtures" / "newyork.html").read_text(encoding="utf-8")
TODAY = "2026-11-25"


def rows():
    return ny.parse(PAGE)[0]


def test_the_grid_is_read_by_element_id_with_the_pages_own_count():
    got, total = ny.parse(PAGE)
    assert total == 6 and len(got) == 6
    assert got[0] == {"event": "SAMPLE27", "agency": "AGM01", "title": "Sample School Food Grant & Training",
                      "status": "Available", "eligible": "Governmental Entity, Not-For-Profit, Tribal Organization",
                      "released": "09/15/26 9:00AM", "due": "01/22/2027 3:00PM EST"}


def test_a_row_becomes_an_open_call_that_links_the_search_page_and_says_so():
    rec = ny.normalize(rows()[0], TODAY)
    assert rec["id"] == "ny-agm01-sample27" and rec["number"] == "SAMPLE27" and rec["state"] == "NY"
    assert rec["url"] == rec["web"] == ny.SITE   # no link to one opportunity exists
    assert (rec["opens"], rec["closes"], rec["status"]) == ("2026-09-15", "2027-01-22", "active")
    assert "Event ID SAMPLE27" in rec["application"] and "no link to a single opportunity" in rec["application"]
    assert "cuts titles" not in rec["application"]   # a short title isn't said to be cut
    assert rec["nonprofit_eligible"] is True and rec["objectives"] == "" and rec["award"] == ""
    # an agency code with no verified name is shown as the code
    assert rec["agency"] == "State agency code AGM01"


def test_eligibility_status_titles_and_known_agency_codes():
    recs = [ny.normalize(r, TODAY) for r in rows()]
    assert recs[1]["nonprofit_eligible"] is False and recs[1]["agency"] == "New York State Department of Labor"
    assert "advertised only" in recs[1]["application"] and "cuts titles at 50" in recs[1]["application"]
    assert recs[2]["status"] == "forecasted" and recs[2]["opens"] == "2026-12-10"
    assert recs[4]["nonprofit_eligible"] is False and recs[4]["loan"] is False   # loan repayment isn't a loan
    assert recs[5]["nonprofit_eligible"] is True and "read the notice" in recs[5]["applicant_types"]   # blank list


def test_ids_stay_apart_across_agencies_and_dropped_rows_say_why():
    skips = []
    recs = ny.build_records([*rows(), rows()[0]], today=TODAY, skips=skips)
    ids = [r["id"] for r in recs]
    assert "ny-dol01-evt0000001" in ids and "ny-oas01-evt0000001" in ids and len(ids) == len(set(ids)) == 4
    assert sorted((s["id"], s["reason"]) for s in skips) == [
        ("ny-agm01-sample27", "duplicate"), ("ny-dec01-old1", "deadline_passed"), ("ny-prk01-nodate", "no_deadline")]
    assert all(s["source"] == "newyork" and s["state"] == "NY" for s in skips)


def test_a_page_with_too_few_rows_or_a_higher_count_keeps_the_old_file(monkeypatch):
    assert len(ny.read_rows(PAGE)) == 6
    with pytest.raises(RuntimeError, match="counter says 60"):
        ny.read_rows(PAGE.replace("1-6 of 6", "1-6 of 60"))   # paged: not every row is on the page
    with pytest.raises(RuntimeError, match="counter says None"):
        ny.read_rows(PAGE.replace("1-6 of 6", "all"))
    with pytest.raises(RuntimeError, match="Only 0 rows"):
        ny.read_rows("<html></html>")


def test_a_saved_copy_is_read_without_the_network(tmp_path, monkeypatch):
    monkeypatch.setattr(ny, "fetch_list", lambda: (_ for _ in ()).throw(AssertionError("no network in tests")))
    saved = tmp_path / "grid.html"
    saved.write_text(PAGE.replace("/2027", "/2099").replace("/2026", "/2099"), encoding="utf-8")
    out = tmp_path / "ny.json.gz"
    assert ny.build(out, tmp_path / "skipped.json.gz", saved) == 5   # the undated row is left out
    payload = json.loads(gzip.decompress(out.read_bytes()))
    assert payload["state"] == "NY" and payload["count"] == 5
