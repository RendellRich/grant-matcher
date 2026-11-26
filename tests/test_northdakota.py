"""The North Dakota Council on the Arts' pages into state program records (grantmatch/northdakota.py)."""
import gzip
import json
from pathlib import Path

import pytest

from grantmatch import northdakota as nd
from grantmatch import match_words, states, webpages

FIXTURES = Path(__file__).parent / "fixtures"
GRANTS = (FIXTURES / "northdakota-grants.html").read_text(encoding="utf-8")
PROGRAM = (FIXTURES / "northdakota-program.html").read_text(encoding="utf-8")
RESIDENCE = PROGRAM.replace(
    "<h3>Grant Award Range</h3>",
    "<h3>Eligibility</h3><p>A sample school district or nonprofit organization is eligible to apply.</p>"
    "<h3>Grant Award Range FY27 and Match</h3>").replace(
    "<li>20% match required</li>",
    "<li>A minimum 10% cash match is required.</li><li>A minimum 30% cash match is required.</li>")
# Special Projects' own page names no one: its card does.
SPECIAL = PROGRAM.replace("The Sample Program is a reimbursement grant program that provides up to $1,000 for North Dakota "
                          "nonprofit art organizations and individual artists to learn.",
                          "Sample grants provide up to $1,500 for North Dakota groups.").replace("<li>20% match required</li>", "")
PAGES = {"artist-residence": RESIDENCE, "professional-development": PROGRAM, "special-projects": SPECIAL}
TODAY = "2026-11-26"


def page_of(url):
    return PAGES[url.rsplit("/", 1)[-1]]


def built(grants=GRANTS, program_page=page_of):
    skips = []
    recs = nd.build_records(nd.read_rows(grants, program_page, TODAY), today=TODAY, skips=skips)
    return {r["id"]: r for r in recs}, skips


def test_only_cards_with_a_relative_deadline_are_followed():
    asked = []
    built(program_page=lambda url: asked.append(url) or page_of(url))
    assert asked == [f"https://www.arts.nd.gov/{p}" for p in
                     ("arts-education-0/artist-residence", "arts-organizations/professional-development",
                      "arts-organizations/special-projects")]


def test_each_open_program_takes_its_closing_date_match_and_eligibility_from_its_page():
    recs, _ = built()
    assert sorted(recs) == ["nd-artist-in-residence", "nd-professional-development", "nd-special-projects"]
    assert {r["closes"] for r in recs.values()} == {"2027-05-31"}
    air = recs["nd-artist-in-residence"]
    assert air["applicant_types"].startswith("A sample school district or nonprofit organization") and air["nonprofit_eligible"]
    assert air["match"] == "10% or 30%"
    pd = recs["nd-professional-development"]
    assert pd["nonprofit_eligible"] is True and "nonprofit art organizations" in pd["applicant_types"]
    assert (pd["match"], pd["funding_method"]) == ("20%", "Reimbursement")
    assert "photo caption" not in pd["objectives"] and pd["url"].endswith("/professional-development")
    assert "at least six weeks" in pd["application"]


def test_a_page_silent_on_match_says_so():
    recs, _ = built()
    special = recs["nd-special-projects"]
    assert special["applicant_types"] == "Non-profit organizations" and special["nonprofit_eligible"] is True
    assert special["match"] == "" and "match_none" not in special
    assert match_words.statement(special) == match_words.NOT_STATED


def test_past_cards_are_left_out_with_a_reason():
    _, skips = built()
    assert sorted((s["name"], s["reason"]) for s in skips) == [
        ("Accessibility Grant", "deadline_passed"), ("Artist Growth", "deadline_passed"),
        ("Community Arts Access", "deadline_passed")]


def test_a_paused_program_is_left_out():
    paused = PROGRAM.replace("A sample photo caption.", "We have temporarily paused applications for this grant.")
    recs, skips = built(program_page=lambda url: paused if "professional" in url else page_of(url))
    assert "nd-professional-development" not in recs
    assert ("Professional Development", "not_taking") in [(s["name"], s["reason"]) for s in skips]


def test_a_page_that_changed_shape_keeps_the_old_file():
    with pytest.raises(RuntimeError, match="grant cards"):
        built(grants="<main><h1>Grants at a Glance</h1></main>")
    with pytest.raises(RuntimeError, match="no deadline line"):
        built(grants=GRANTS.replace("<p><strong>Deadline:</strong> April 23, 2026 (annual)</p><p>*deadline has passed</p>", ""))
    with pytest.raises(RuntimeError, match="no longer says when applications close"):
        built(program_page=lambda url: PROGRAM.replace("will close on May 31, 2027", "closes in spring"))
    with pytest.raises(RuntimeError, match="no heading"):
        built(program_page=lambda url: "<main><p>Moved</p></main>")


def test_the_labels_say_it_is_one_agency():
    spec = states.STATE_PROGRAMS["ND"]
    assert "one agency, not a statewide list" in spec["source"] and "1 agency" in spec["catalog"]
    assert states.STATES["ND"]["pages"] == [nd.LIST]


def test_saved_copies_are_read_without_the_network(tmp_path, monkeypatch):
    monkeypatch.setattr(webpages, "fetch_page", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no network")))
    (tmp_path / "grants.html").write_text(GRANTS, encoding="utf-8")
    for name, page in PAGES.items():
        (tmp_path / f"{name}.html").write_text(page.replace("May 31, 2027", "May 31, 2099"), encoding="utf-8")
    out = tmp_path / "nd.json.gz"
    assert nd.build(out, tmp_path / "skipped.json.gz", tmp_path) == 3
    assert json.loads(gzip.decompress(out.read_bytes()))["state"] == "ND"


def test_cards_for_organizations_are_open_to_nonprofits_from_the_card_alone():
    for who in ("Arts and non-arts organizations", "Arts & non-arts organizations", "Organizations & individuals"):
        card = {"title": "A", "url": nd.LIST, "what": "", "who": who, "deadline": "April 26, 2026", "passed": ""}
        assert nd.normalize(card, None, "2026-03-01")["nonprofit_eligible"] is True, who
    recs, _ = built_on("2026-03-01")
    assert recs["nd-accessibility-grant"]["nonprofit_eligible"] and recs["nd-community-arts-access"]["nonprofit_eligible"]


def built_on(today):
    recs = nd.build_records(nd.read_rows(GRANTS, page_of_any, today), today=today)
    return {r["id"]: r for r in recs}, today


def page_of_any(url):
    return PAGES.get(url.rsplit("/", 1)[-1], PROGRAM)


def test_the_next_round_is_shown_not_the_last():
    for today, closes in (("2026-03-01", "2026-04-26"), ("2026-04-26", "2026-04-26"), ("2026-05-01", "2026-09-20")):
        assert built_on(today)[0]["nd-community-arts-access"]["closes"] == closes, today
    assert "nd-community-arts-access" not in built_on("2026-09-21")[0]


def test_a_dated_card_that_leaves_nonprofits_out_is_checked_on_its_own_page():
    dated = GRANTS.replace("<p><strong>Who:</strong> Educational institutions</p><p><strong>Deadline:</strong> 6 weeks prior to project start date</p>",
                           "<p><strong>Who:</strong> Educational institutions</p><p><strong>Deadline:</strong> April 30, 2027</p>")
    assert dated != GRANTS
    asked = []
    rows = nd.read_rows(dated, lambda url: asked.append(url) or RESIDENCE, TODAY)
    assert any(u.endswith("/artist-residence") for u in asked)
    air = {r["record"]["id"]: r["record"] for r in rows}["nd-artist-in-residence"]
    assert air["nonprofit_eligible"] is True and air["closes"] == "2027-04-30"


def test_the_labels_say_which_match_is_whose():
    labelled = RESIDENCE.replace("<li>A minimum 10% cash match is required.</li><li>A minimum 30% cash match is required.</li>",
                                 "</ul><p>Sample Title 1 Schools:</p><ul><li>May request up to $3,000. A minimum 10% cash match is required.</li></ul>"
                                 "<p>Other Schools:</p><ul><li>May request up to $3,000. A minimum 30% cash match is required.</li>")
    assert labelled != RESIDENCE
    program = nd.parse_program(labelled)
    card = {"title": "Artist in Residence", "url": nd.LIST, "what": "", "who": "Educational institutions",
            "deadline": "6 weeks prior to project start date", "passed": ""}
    rec = nd.normalize(card, program, TODAY)
    assert rec["match"] == "10% for Sample Title 1 Schools; 30% for Other Schools"
    assert "Sample Title 1 Schools: May request" in rec["award"] and "Other Schools: May request" in rec["award"]


@pytest.mark.parametrize("what, open_", [
    ("Two grants of $5,000 to individual artists for new artwork", False),
    ("Up to $4,500 for master traditional artists to pass on skills", False),
    ("Grants to sample individual artists", False),
    ("Operating support to arts organizations", True),
    ("Up to $2,000 for a sample event", True),
])
def test_a_card_with_no_who_line_is_read_by_its_what_line(what, open_):
    card = {"title": "Sample", "url": "https://www.arts.nd.gov/sample", "what": what, "who": "",
            "deadline": "April 30, 2027", "passed": ""}
    r = nd.normalize(card, None, TODAY)
    assert r["nonprofit_eligible"] is open_
    silent = what == "Up to $2,000 for a sample event"
    assert r["applicant_types"].startswith("Not stated" if silent else "As the Council's card puts it:")


def test_individual_artist_grants_stay_closed_to_nonprofits_once_next_years_dates_appear():
    recs, _ = built(GRANTS.replace("April 30, 2026", "April 30, 2027"))
    assert recs["nd-artist-growth"]["nonprofit_eligible"] is False


def test_a_card_with_no_date_is_never_kept_whatever_it_says():
    grants = GRANTS.replace("<p><strong>Deadline:</strong> April 23, 2026 (annual)</p><p>*deadline has passed</p>",
                            "<p><strong>Deadline:</strong> Ongoing</p>")
    recs, skips = built(grants)
    assert "nd-accessibility-grant" not in recs
    assert ("nd-accessibility-grant", "not_taking") in [(s["id"], s["reason"]) for s in skips]
