"""The District Grants Clearinghouse tables into state program records (grantmatch/districtofcolumbia.py)."""
import gzip
import json
from pathlib import Path

import pytest

from grantmatch import districtofcolumbia as dc

PAGE = (Path(__file__).parent / "fixtures" / "districtofcolumbia.html").read_text(encoding="utf-8")
TODAY = "2026-11-25"


def built():
    skips = []
    return dc.build_records(dc.read_rows(PAGE), today=TODAY, skips=skips), skips


def test_both_tables_are_read_with_title_agency_links_and_deadline():
    items, clearinghouse = dc.parse(PAGE)
    assert clearinghouse == 6 and len(items) == 7
    housing = next(i for i in items if i["agency"] == "Department of Sample Finance")
    assert housing["title"] == "FY27 Sample Housing Grant" and housing["deadline"] == "4:00 pm December 14, 2026"
    assert housing["notice"] == [("NOFA", "https://communityaffairs.dc.gov/sites/moca/files/Sample%20NOFA.docx")]
    fund = items[0]
    assert fund["agency"] == dc.MAYORS_OFFICE and fund["deadline"] == "November 27, 2026 at 5:00PM"


def test_a_notice_becomes_an_open_call_that_says_to_read_the_notice():
    recs, _ = built()
    r = next(r for r in recs if r["agency"] == "Department of Sample Finance")
    assert r["id"].startswith("dc-fy27-sample-housing-grant-")
    assert (r["state"], r["closes"], r["status"]) == ("DC", "2026-12-14", "active")
    assert r["url"].endswith("Sample%20NOFA.docx") and r["web"] == dc.LIST
    assert r["nonprofit_eligible"] is True and r["applicant_types"] == dc.WHO and "read the notice" in dc.WHO
    assert "RFA (corrected): https://communityaffairs.dc.gov/sites/moca/files/Sample%20RFA.pdf" in r["application"]
    today = next(r for r in recs if "today" in r["id"])
    assert today["closes"] == TODAY and today["url"] == dc.LIST   # due today stays; no link: the clearinghouse page


def test_a_school_system_grant_is_not_open_to_nonprofits():
    recs, _ = built()
    lea = next(r for r in recs if "school-health" in r["id"])
    assert lea["nonprofit_eligible"] is False and lea["applicant_types"] == dc.SCHOOLS_SAYS


def test_past_and_yearless_deadlines_are_skipped_and_a_repeated_title_keeps_both():
    recs, skips = built()
    assert sorted((s["name"], s["reason"]) for s in skips) == [
        ("FY27 Sample Passed Grant", "deadline_passed"), ("FY27 Sample Yearless Grant", "no_deadline")]
    twice = [r["id"] for r in recs if r["title"] == "FY27 Sample Housing Grant"]
    assert len(twice) == len(set(twice)) == 2


def notice(link, deadline="December 20, 2026", agency="Sample Office"):
    links = [("NOFA", f"https://communityaffairs.dc.gov/publication/{link}")] if link else []
    return {"title": "Same Grant", "agency": agency, "notice": links, "packet": [], "deadline": deadline}


def test_a_repeated_titles_ids_survive_expiry_reorder_and_the_title_standing_alone():
    a, b = notice("a", "December 1, 2026"), notice("b")
    ids = {r["url"]: r["id"] for r in dc.build_records([a, b], today=TODAY)}
    b_url = b["notice"][0][1]
    assert len(set(ids.values())) == 2
    assert {r["url"]: r["id"] for r in dc.build_records([b, a], today=TODAY)} == ids   # reordered
    assert [r["id"] for r in dc.build_records([a, b], today="2026-12-05")] == [ids[b_url]]   # a expired
    assert [r["id"] for r in dc.build_records([b], today=TODAY)] == [ids[b_url]]   # no longer repeated
    # rows with no link of their own are told apart by agency
    assert len(dc.build_records([notice("", agency="One"), notice("", agency="Two")], today=TODAY)) == 2
    skips = []
    assert len(dc.build_records([a, dict(a)], today=TODAY, skips=skips)) == 1 and skips[0]["reason"] == "duplicate"


def test_a_changed_page_keeps_the_old_file():
    with pytest.raises(RuntimeError, match="keeping the previous data file"):
        dc.read_rows("<table><tr><td>Public Notices</td></tr></table>")


def test_email_addresses_never_reach_a_record():
    rec = dc.normalize({"title": "Write to jane@example.org Grant", "agency": "a@example.org", "notice": [], "packet": [],
                        "deadline": "December 1, 2026"})
    assert not any("@" in v for v in rec.values() if isinstance(v, str))


def test_a_saved_copy_is_read_without_the_network(tmp_path, monkeypatch):
    monkeypatch.setattr(dc, "fetch_list", lambda: (_ for _ in ()).throw(AssertionError("no network in tests")))
    saved = tmp_path / "page.html"
    saved.write_text(PAGE.replace(", 2026", ", 2099").replace(", 2027", ", 2099"), encoding="utf-8")
    out = tmp_path / "dc.json.gz"
    assert dc.build(out, tmp_path / "skipped.json.gz", saved) == 6
    payload = json.loads(gzip.decompress(out.read_bytes()))
    assert payload["state"] == "DC" and "CC BY 3.0" in payload["source"]
