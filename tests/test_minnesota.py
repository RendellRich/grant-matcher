"""Minnesota's Health and Justice Programs pages into state program records (grantmatch/minnesota.py)."""
import gzip
import json
from pathlib import Path

import pytest

from grantmatch import minnesota as mn
from grantmatch import states

FIXTURES = Path(__file__).parent / "fixtures"
HEALTH = (FIXTURES / "minnesota-health.html").read_text(encoding="utf-8")
JUSTICE = (FIXTURES / "minnesota-justice.html").read_text(encoding="utf-8")
TODAY = "2026-11-25"


def built():
    skips = []
    recs = mn.build_records(mn.read_rows(HEALTH, JUSTICE), today=TODAY, skips=skips)
    return {r["title"]: r for r in recs}, skips


def test_each_health_entry_is_read_with_its_dates_and_eligible_applicants():
    rows = mn.parse_health(HEALTH)
    assert [r["title"] for r in rows] == [
        "Sample Suicide Prevention Grant", "Sample Dental Safety Net Program", "Sample Fluoridation Grant",
        "Sample Past Grant", "Sample Lead Remediation Grant", "Sample Research Cost Program"]
    first = rows[0]
    assert first["url"] == "https://www.health.state.mn.us/communities/sample/rfp.html"
    assert first["eligible"] == "Local Public Health; Nonprofit Organizations; Tribal Governments"
    assert rows[1]["url"].endswith("/facilities/sample/index.html") and rows[1]["intent_letter"] is True
    assert rows[-1]["eligible"] == "Hospitals"   # nothing from the tags below the list


def test_health_calls_become_records_with_the_agencys_own_eligibility():
    recs, _ = built()
    r = recs["Sample Suicide Prevention Grant"]
    assert r["id"].startswith("mn-health-sample-suicide-prevention-grant-") and r["agency"] == mn.HEALTH_AGENCY
    assert (r["state"], r["closes"], r["nonprofit_eligible"]) == ("MN", "2027-01-08", True)
    assert r["application"].startswith("Intent to apply deadline: Wednesday, December 2, 2026")
    assert "has passed" not in r["application"] and r["contact"] == ""
    dental = recs["Sample Dental Safety Net Program"]
    assert dental["loi"] is True and "Letter of intent deadline: Friday, October 16, 2026" in dental["application"]
    assert "That date has passed" in dental["application"] and dental["nonprofit_eligible"] is True
    # only others named: not shown as open to nonprofits
    assert recs["Sample Fluoridation Grant"]["nonprofit_eligible"] is False
    lead = recs["Sample Lead Remediation Grant"]
    assert (lead["closes"], lead["deadlines"], lead["nonprofit_eligible"]) == (None, "Ongoing", False)


def test_the_justice_call_is_read_and_its_pdf_only_linked():
    recs, _ = built()
    r = recs["2027 Sample Reinvestment Grants"]
    assert r["id"].startswith("mn-justice-2027-sample-reinvestment-grants-") and r["agency"] == mn.JUSTICE_AGENCY
    assert r["closes"] == "2026-12-02" and r["url"] == mn.JUSTICE and r["nonprofit_eligible"] is True
    assert r["objectives"].startswith("The office is seeking proposals") and "Applications are due" not in r["objectives"]
    assert r["award"] == "The maximum request is $150,000."
    assert "Request for proposals: https://assets.dps.mn.gov/files/ojp/sample-RFP.pdf?v=1" in r["application"]
    assert len([r for r in recs.values() if r["agency"] == mn.JUSTICE_AGENCY]) == 1   # other headings aren't calls


def test_past_and_undated_entries_are_skipped_with_a_reason():
    _, skips = built()
    assert sorted((s["name"], s["reason"]) for s in skips) == [
        ("Sample Past Grant", "deadline_passed"), ("Sample Research Cost Program", "no_deadline")]


def test_a_blank_eligibility_list_is_kept_with_a_note():
    rec = mn.normalize({"agency": "health", "title": "A", "url": mn.HEALTH, "intent": "N/A", "intent_letter": False,
                        "deadline": "December 1, 2026", "window": "", "eligible": ""}, TODAY)
    assert rec["nonprofit_eligible"] is True and "read the notice" in rec["applicant_types"]


def test_a_page_that_changed_shape_keeps_the_old_file():
    with pytest.raises(RuntimeError, match="Minnesota Health page"):
        mn.read_rows("<main></main>", JUSTICE)
    with pytest.raises(RuntimeError, match="Justice Programs page"):
        mn.read_rows(HEALTH, "<main><h1>Funding opportunities</h1></main>")
    assert mn.parse_justice("<main><p>There are no current funding opportunities.</p></main>") == []


def test_an_entry_without_its_intent_line_stops_the_run():
    intent = "<strong>Intent to Apply Deadline:</strong> N/A<br>"
    fluoride = f"<strong>Sample Fluoridation Grant</strong></a><br>{intent}"
    assert fluoride in HEALTH
    # in the middle it would be read as part of the entry above, which would take its deadline and eligibility
    with pytest.raises(RuntimeError, match="no intent deadline line"):
        mn.parse_health(HEALTH.replace(fluoride, "<strong>Sample Fluoridation Grant</strong></a><br>"))
    # at the top it would not be read at all
    first = "<strong>Intent to Apply Deadline:</strong> Wednesday, December 2, 2026, 4:30 p.m. CT<br>"
    assert first in HEALTH
    with pytest.raises(RuntimeError, match="no intent deadline line"):
        mn.parse_health(HEALTH.replace(first, ""))
    with pytest.raises(RuntimeError, match="keeping the previous data file"):
        mn.parse_health(HEALTH.replace("<p>* Eligibility has been corrected.</p>", "<p>Eligible Applicants: Schools</p>"))


def entry(title="Same Grant", url="https://www.health.state.mn.us/a.html", deadline="December 14, 2099"):
    return {"agency": "health", "title": title, "url": url, "intent": "N/A", "intent_letter": False,
            "deadline": deadline, "window": "", "eligible": "Nonprofit Organizations"}


def test_a_repeated_titles_ids_survive_expiry_reorder_and_the_title_standing_alone():
    a = entry(url="https://www.health.state.mn.us/a.html", deadline="December 1, 2026")
    b = entry(url="https://www.health.state.mn.us/b.html", deadline="December 20, 2026")
    ids = {r["url"]: r["id"] for r in mn.build_records([a, b], today=TODAY)}
    assert len(set(ids.values())) == 2
    assert {r["url"]: r["id"] for r in mn.build_records([b, a], today=TODAY)} == ids   # reordered
    assert [r["id"] for r in mn.build_records([a, b], today="2026-12-05")] == [ids[b["url"]]]   # a expired
    assert [r["id"] for r in mn.build_records([b], today=TODAY)] == [ids[b["url"]]]   # no longer repeated
    skips = []
    assert len(mn.build_records([a, dict(a)], today=TODAY, skips=skips)) == 1 and skips[0]["reason"] == "duplicate"


def test_a_hospital_only_grant_isnt_open_to_nonprofits_generally():
    text = ("An eligible applicant for this grant program is a non-federal, general acute care hospital in Minnesota "
            "that: Is located in a rural area, Has 50 or fewer beds, and Is not for profit.")
    rec = mn.normalize({**entry(), "eligible": text}, TODAY)
    assert rec["nonprofit_eligible"] is False and rec["applicant_types"] == text
    dental = ("The provider is a nonprofit organization; The provider is not affiliated with, owned by, or managed by "
              "a hospital or medical group")
    assert mn.normalize({**entry(), "eligible": dental}, TODAY)["nonprofit_eligible"] is True


def test_the_label_the_site_shows_says_it_is_two_agencies_not_the_state():
    spec = states.STATE_PROGRAMS["MN"]
    assert "two agencies, not a statewide list" in spec["source"] and "2 agencies" in spec["catalog"]


def test_saved_copies_are_read_without_the_network_and_no_email_is_kept(tmp_path, monkeypatch):
    monkeypatch.setattr(mn, "fetch_page", lambda url: (_ for _ in ()).throw(AssertionError("no network in tests")))
    health = tmp_path / "health.html"
    health.write_text(HEALTH.replace(", 2026", ", 2099").replace(", 2027", ", 2099")
                      .replace("Public Water Suppliers", "Public Water Suppliers; ask someone@example.org"), encoding="utf-8")
    out = tmp_path / "mn.json.gz"
    assert mn.build(out, tmp_path / "skipped.json.gz", (health, FIXTURES / "minnesota-justice.html")) >= 5
    payload = json.loads(gzip.decompress(out.read_bytes()))
    assert payload["state"] == "MN"
    assert not any("@" in v for r in payload["programs"] for v in r.values() if isinstance(v, str))
