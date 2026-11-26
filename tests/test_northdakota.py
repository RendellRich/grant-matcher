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
