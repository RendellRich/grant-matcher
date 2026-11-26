"""The Tennessee Arts Commission's program pages into state program records (grantmatch/tennessee.py)."""
import gzip
import json
from pathlib import Path

import pytest

from grantmatch import match_words, states, webpages
from grantmatch import tennessee as tn

FIXTURES = Path(__file__).parent / "fixtures"
GRANTS = (FIXTURES / "tennessee-grants.html").read_text(encoding="utf-8")
PROGRAM = (FIXTURES / "tennessee-program.html").read_text(encoding="utf-8")
TODAY = "2026-11-26"
DEADLINE = "<p>Application Deadline: January 8, 2027</p>"
MONEY = "This grant requires a dollar-for-dollar match."


def titled(page, n):
    return page.replace("<h1>Sample Program 1</h1>", f"<h1>Sample Program {n}</h1>")


def one(page=PROGRAM, today=TODAY):
    return tn.parse_program(page, tn.LIST + "sample-1/", today)


def test_each_program_linked_from_the_list_is_read():
    assert tn.parse(GRANTS) == [f"{tn.LIST}sample-{n}/" for n in range(1, 11)]


def test_dates_eligibility_amount_and_match_come_from_the_pages_headings():
    row = one()
    r = row["record"]
    assert (r["state"], r["title"], r["closes"], r["agency"]) == ("TN", "Sample Program 1", "2027-01-08", tn.AGENCY)
    assert r["applicant_types"].startswith("501(c)3 Nonprofit organizations") and r["nonprofit_eligible"] is True
    assert (r["match"], r["funding_method"], r["objectives"]) == ("1:1", "Reimbursement", "Support for sample arts projects.")
    assert "$18,000" in r["award"] and r["restrictions"].startswith("For projects occurring: FY2028")
    assert r["loi"] is False and "first-time" not in r["applicant_types"].lower() and "UEI" not in r["restrictions"]
    assert row["closed"] == ""   # the footer below the address isn't the program's words


@pytest.mark.parametrize("words, match, none, card", [
    ("This grant requires a 4:1 cash or in-kind match commitment.", "4:1 cash or in-kind", False, match_words.REQUIRED),
    ("Up to $18,000 with a 1:1 match required.", "1:1", False, match_words.REQUIRED),
    ("Up to $25,000 (non-matching).", "", True, match_words.NONE),
    ("This grant does not require a match.", "", True, match_words.NONE),
    ("Tier 1: $12,000.", "", False, match_words.NOT_STATED),
])
def test_the_match_is_what_the_funding_heading_says(words, match, none, card):
    r = one(PROGRAM.replace(MONEY, words))["record"]
    assert (r["match"], r.get("match_none", False), match_words.statement(r)) == (match, none, card)


def test_rolling_relative_closed_and_undated_programs():
    rolling = PROGRAM.replace(DEADLINE, "<p>Application Deadline 30 days prior to the project</p><p>This is a Rolling Grant: "
                              "applications are accepted on a continual basis until funds are depleted and/or until April 1, 2027.</p>")
    assert one(rolling)["record"]["closes"] == "2027-04-01"
    relative = one(PROGRAM.replace(DEADLINE, "<p>Application Deadline: 30 days prior to the project</p>"))
    assert (relative["record"]["closes"], relative["record"]["deadlines"] != "Ongoing") == (None, True)
    closed = one(PROGRAM.replace("<p>Important:</p>", "<p>As of 9/4/2026, the Sample grant application is closed.</p>"))
    skips = []
    assert tn.build_records([relative, closed], today=TODAY, skips=skips) == []
    assert [s["reason"] for s in skips] == ["no_deadline", "not_taking"]


def test_a_program_for_schools_or_artists_only_is_not_open_to_nonprofits():
    for who in ("Public K-12 Schools", "Professional practicing Tennessee artists"):
        page = PROGRAM.replace("<ul><li>501(c)3 Nonprofit organizations chartered in Tennessee</li>"
                               "<li>Entities of Local Government within Tennessee</li></ul>", f"<p>{who}</p>")
        assert one(page)["record"]["nonprofit_eligible"] is False, who


def pages(page=PROGRAM):
    return lambda url: titled(page, url.rstrip("/").rsplit("-", 1)[-1])


def test_a_page_that_changed_shape_keeps_the_old_file():
    assert len(tn.read_rows(GRANTS, pages(), TODAY)) == 10
    with pytest.raises(RuntimeError, match="programs on the Tennessee"):
        tn.parse("<main><h1>Grant Opportunities</h1></main>")
    with pytest.raises(RuntimeError, match="dates heading"):
        tn.read_rows(GRANTS, pages(PROGRAM.replace("<h3>Application Dates &amp; Deadlines</h3>", "<h3>When</h3>")), TODAY)
    with pytest.raises(RuntimeError, match="no eligibility list"):
        one(PROGRAM.replace("<h3>Eligible Applicants</h3>", "<h3>Who</h3>"))
    with pytest.raises(RuntimeError, match="no heading"):
        one("<main><p>Moved</p></main>")


def test_the_labels_say_it_is_one_agency():
    spec = states.STATE_PROGRAMS["TN"]
    assert "one agency, not a statewide list" in spec["source"] and "1 agency" in spec["catalog"]
    assert states.STATES["TN"]["pages"] == [tn.LIST]


def test_saved_copies_are_read_without_the_network(tmp_path, monkeypatch):
    monkeypatch.setattr(webpages, "fetch_page", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no network")))
    (tmp_path / "grants.html").write_text(GRANTS, encoding="utf-8")
    for n in range(1, 11):
        body = titled(PROGRAM, n).replace("January 8, 2027", "January 8, 2099")
        (tmp_path / f"sample-{n}.html").write_text(body, encoding="utf-8")
    out = tmp_path / "tn.json.gz"
    assert tn.build(out, tmp_path / "skipped.json.gz", tmp_path) == 10
    assert json.loads(gzip.decompress(out.read_bytes()))["state"] == "TN"


FIRST = ("<p>First-time applicants to this category must:</p><ul><li>contact a program director, and then</li>"
         "<li>submit a letter requesting entry into the category by October 30. The letter says why.</li></ul>")
LISTED = "<li>501(c)3 Nonprofit organizations chartered in Tennessee</li>"


def operating(extra="<li>Requires an approved formal request submitted by email for entry by October 30.</li>"):
    return PROGRAM.replace("<p>Important:</p>", f"{FIRST}<p>Important:</p>").replace(LISTED, LISTED + extra)


def test_a_first_time_requirement_leads_how_to_apply_and_says_when_it_has_passed():
    r = one(operating())["record"]
    assert r["application"].startswith("First-time applicants to this category must: contact a program director; submit a "
                                       "letter requesting entry into the category by October 30. That date has passed; "
                                       "check the notice before you start.")
    assert r["loi"] is True
    assert "For first-time applicants: Requires an approved formal request" in r["applicant_types"]
    # before the date, the same words without "passed"; the year is the one before the January deadline
    early = one(operating(), "2026-10-01")["record"]
    assert "That date has passed" not in early["application"] and early["loi"] is True
    assert early["application"].startswith("First-time applicants to this category must:")


def test_who_can_apply_says_first_time_even_without_an_entry_line():
    assert "first-time" in one(operating(""))["record"]["applicant_types"].lower()


def test_a_first_time_date_it_cannot_read_stops_the_run():
    with pytest.raises(RuntimeError, match="can't read"):
        one(operating().replace("by October 30", "by the end of October"))


def test_no_match_said_anywhere_above_the_footer_is_read():
    said = "<p>Fellowships are $5,000. No matching funds are required.</p>"
    page = PROGRAM.replace(MONEY, "Fellowships of $5,000.").replace("<p>Important:</p>", f"{said}<p>Important:</p>")
    r = one(page)["record"]
    assert (r["match"], r["match_none"], match_words.statement(r)) == ("", True, match_words.NONE)
    assert "No matching funds are required." in r["restrictions"]
    below = one(PROGRAM.replace(MONEY, "Up to $5.").replace("<p>This grant is closed.</p>", said))["record"]
    assert "match_none" not in below
    # a required match wins over such a line elsewhere on the page
    both = one(PROGRAM.replace("<p>Important:</p>", f"{said}<p>Important:</p>"))["record"]
    assert both["match"] == "1:1" and "match_none" not in both


def test_a_renamed_funding_heading_stops_the_run():
    with pytest.raises(RuntimeError, match="Funding Requests"):
        one(PROGRAM.replace("<h3>Funding Requests</h3>", "<h3>Award Amounts</h3>"))


@pytest.mark.parametrize("said", [
    "Unique Entity ID (UEI): All applicants are required to have a Unique Entity ID.",
    "While not required to submit an application, the UEI will be required prior to receiving grant funding.",
])
def test_the_uei_requirement_is_in_the_record(said):
    r = one(PROGRAM.replace("<h3>Grantee Reporting Requirements</h3>", f"<p>{said}</p><h3>Grantee Reporting Requirements</h3>"))
    assert said in r["record"]["restrictions"]


ROLL = ("<p>Application Deadline 30 days prior to the project</p><p>This is a Rolling Grant: applications will be accepted "
        "on a continual basis until funds are depleted and/or until April 1, 2027.</p>")


@pytest.mark.parametrize("said", [
    "Applications are no longer being accepted.", "We are no longer taking applications.",
    "Funds have been depleted for FY27.", "All FY27 funds have been awarded.", "This grant opportunity has closed.",
    "Funding has been exhausted.", "The fund is fully committed.", "This program is on a waiting list.",
    "No funding remains this year.",
])
def test_a_rolling_program_goes_on_any_closed_wording(said):
    rolling = PROGRAM.replace(DEADLINE, ROLL)
    assert tn.build_records([one(rolling)], today=TODAY)
    skips = []
    closed = one(rolling.replace("<p>Important:</p>", f"<p>{said}</p><p>Important:</p>"))
    assert tn.build_records([closed], today=TODAY, skips=skips) == [] and skips[0]["reason"] == "not_taking"


def test_a_grant_marked_non_matching_keeps_its_no_match_card():
    said = "<p>The grant does not require a match during the FY28 cycle.</p><p>Important:</p>"
    r = one(PROGRAM.replace(MONEY, "Up to $25,000 (non-matching).").replace("<p>Important:</p>", said))["record"]
    assert r["match_none"] is True and match_words.statement(r) == match_words.NONE
