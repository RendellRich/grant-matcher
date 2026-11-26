"""The Arkansas Arts Council's art grants page into state program records (grantmatch/arkansas.py)."""
import gzip
import json
from pathlib import Path

import pytest

from grantmatch import arkansas as ar
from grantmatch import match_words, states, webpages

FIXTURE = Path(__file__).parent / "fixtures" / "arkansas.html"
PAGE = FIXTURE.read_text(encoding="utf-8")
TODAY = "2026-11-26"


def built(today=TODAY, page=PAGE):
    skips = []
    recs = ar.build_records(ar.parse(page, today), today=today, skips=skips)
    return {r["id"]: r for r in recs}, skips


def test_each_program_is_read_with_the_pages_dates_and_eligibility():
    recs, _ = built()
    assert sorted(recs) == ["ar-arts-in-education-major", "ar-arts-on-tour", "ar-general-operating-support"]
    gos = recs["ar-general-operating-support"]
    assert (gos["state"], gos["closes"], gos["loi"], gos["nonprofit_eligible"]) == ("AR", "2027-01-14", True, True)
    assert "Letter of Intent Applications are due Dec. 3, 2026" in gos["application"]
    assert gos["url"] == ar.LIST and gos["agency"] == ar.AGENCY and gos["contact"] == ""
    aie = recs["ar-arts-in-education-major"]
    assert aie["closes"] == "2027-01-29" and aie["applicant_types"].startswith("These grants are awarded to schools and nonprofit")
    tour = recs["ar-arts-on-tour"]
    assert (tour["closes"], tour["deadlines"], tour["funding_method"]) == (None, "Ongoing", "Reimbursement")


def test_the_match_is_the_pages_words_and_silence_stays_silent():
    recs, _ = built()
    # shown on the card as "Matching funds are required (amount not stated)"
    assert recs["ar-general-operating-support"]["match"] == "amount not stated"
    assert match_words.statement(recs["ar-general-operating-support"]) == match_words.REQUIRED
    assert recs["ar-arts-in-education-major"]["match"] == "1:1, half may be in-kind"
    tour = recs["ar-arts-on-tour"]
    assert tour["match"] == "" and "match_none" not in tour and match_words.statement(tour) == match_words.NOT_STATED


def test_closed_and_past_programs_are_left_out_with_a_reason():
    _, skips = built()
    assert [(s["name"], s["reason"]) for s in skips] == [("Community Arts Project grant", "not_taking")]
    recs, skips = built(today="2027-01-20")
    assert sorted(recs) == ["ar-arts-in-education-major", "ar-arts-on-tour"]
    assert ("General Operating Support (year one)", "deadline_passed") in [(s["name"], s["reason"]) for s in skips]


def test_a_program_the_page_pauses_is_left_out_whatever_its_dates():
    page = PAGE.replace("These grants are awarded to", "Applications are temporarily paused. These grants are awarded to")
    recs, skips = built(page=page)
    assert "ar-arts-in-education-major" not in recs
    assert ("Arts in Education major grants", "not_taking") in [(s["name"], s["reason"]) for s in skips]


@pytest.mark.parametrize("old, new", [
    ("<h2>When To Apply</h2>", "<h2>Dates</h2>"),
    ("Mini grants are closed and will reopen", "Mini grants are open and close"),
    ("<li>All Arts in Education Major grants open Oct. 15. Applications are due Jan. 29, 2027.</li>", ""),
    ("Year One application is due Jan. 14, 2027.", "Year One application is due in January."),
    ("GENERAL OPERATING SUPPORT</strong>", "OPERATING SUPPORT</strong>"),
    ("Application Deadline Ongoing.", "Apply soon."),
    ("This grant is currently closed for applications.", "Apply 60 days before your event."),
    ("These grants are awarded to", "Grants go to"),
])
def test_a_page_that_changed_shape_keeps_the_old_file(old, new):
    assert old in PAGE
    with pytest.raises(RuntimeError, match="keeping the previous data file"):
        ar.parse(PAGE.replace(old, new), TODAY)


def test_the_labels_say_it_is_one_agency():
    spec = states.STATE_PROGRAMS["AR"]
    assert "one agency, not a statewide list" in spec["source"] and "1 agency" in spec["catalog"]
    assert states.STATES["AR"]["pages"] == [ar.LIST]


def test_a_saved_copy_is_read_without_the_network(tmp_path, monkeypatch):
    monkeypatch.setattr(webpages, "fetch_page", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no network")))
    out = tmp_path / "ar.json.gz"
    page = tmp_path / "ar.html"
    page.write_text(PAGE.replace(", 2027", ", 2099").replace(", 2026", ", 2099"), encoding="utf-8")
    assert ar.build(out, tmp_path / "skipped.json.gz", page) == 3
    assert json.loads(gzip.decompress(out.read_bytes()))["state"] == "AR"


@pytest.mark.parametrize("after", [0, 1, 2, 3])
def test_a_missing_apply_button_stops_the_run_whichever_section_it_ends(after):
    """Without it a section would run into the next program and borrow its words ("closed", a match)."""
    marks = [i for i, line in enumerate(PAGE.split("\n")) if "APPLY NOW</a>" in line or "APPLY HERE</a>" in line]
    assert len(marks) == 4
    lines = PAGE.split("\n")
    del lines[marks[after]]
    with pytest.raises(RuntimeError, match="has no end"):
        ar.parse("\n".join(lines), TODAY)


def test_closed_wording_takes_arts_on_tour_off():
    page = PAGE.replace("<p>Application Deadline Ongoing.</p>",
                        "<p>Application Deadline Ongoing.</p><p>Applications are currently closed.</p>")
    recs, skips = built(page=page)
    assert "ar-arts-on-tour" not in recs
    assert ("Arts on Tour grant", "not_taking") in [(s["name"], s["reason"]) for s in skips]


def test_operating_support_says_the_intent_date_and_income_floor_first():
    gos = built()[0]["ar-general-operating-support"]
    assert gos["application"].startswith("Letter of intent deadline: Dec. 3, 2026, for new or newly returning applicants.")
    assert gos["applicant_types"].startswith("The program is for local arts agencies") and "$50,000" in gos["applicant_types"]
    assert "That date has passed" not in gos["application"]
    later = built(today="2026-12-10")[0]["ar-general-operating-support"]
    assert "That date has passed; check the notice before you start." in later["application"]


def tour_gone(page):
    recs, skips = built(page=page)
    return "ar-arts-on-tour" not in recs and "Arts on Tour grant" in [s["name"] for s in skips]


@pytest.mark.parametrize("said", [
    "Applications are no longer being accepted.", "We are no longer taking applications.",
    "Funds have been depleted for FY27.", "All FY27 funds have been awarded.", "This grant opportunity has closed.",
    "Funding has been exhausted.", "The fund is fully committed.", "Check back next spring.",
])
def test_closed_words_inside_the_section_or_naming_the_program_take_arts_on_tour_off(said):
    line = "<p>Application Deadline Ongoing.</p>"
    assert tour_gone(PAGE.replace(line, f"{line}<p>{said}</p>"))
    assert tour_gone(PAGE.replace("<h3>How To Apply</h3>", f"<h3>How To Apply</h3><p>Arts on Tour: {said}</p>"))


def test_a_deadline_that_no_longer_says_it_is_taking_applications_takes_it_off():
    for line in ("Application Deadline to be announced.", "Application Deadline Closed."):
        assert tour_gone(PAGE.replace("Application Deadline Ongoing.", line)), line


def test_a_note_on_a_programs_heading_closes_it_with_or_without_its_apply_button():
    page = PAGE.replace("ARTS ON TOUR GRANT</strong>", "ARTS ON TOUR GRANT (Closed for this cycle)</strong>")
    assert tour_gone(page)
    recs, skips = built(page=PAGE.replace("GENERAL OPERATING SUPPORT</strong>", "GENERAL OPERATING SUPPORT (Paused)</strong>"))
    assert "ar-general-operating-support" not in recs
    assert ("General Operating Support (year one)", "not_taking") in [(s["name"], s["reason"]) for s in skips]


def test_a_when_to_apply_line_about_arts_on_tour_is_read_with_it():
    page = PAGE.replace("<li>Mini grants are closed", "<li>Arts on Tour is paused.</li><li>Mini grants are closed")
    assert tour_gone(page)


def test_closed_mini_grants_do_not_close_arts_on_tour():
    assert "ar-arts-on-tour" in built()[0]
