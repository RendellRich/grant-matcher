"""The Wyoming Arts Council's grant pages into state program records (grantmatch/wyoming.py)."""
import gzip
import json
from pathlib import Path

import pytest

from grantmatch import match_words, states, webpages
from grantmatch import wyoming as wy

GRANTS = (Path(__file__).parent / "fixtures" / "wyoming-grants.html").read_text(encoding="utf-8")
TODAY = "2026-11-26"


def page(title, body):
    # made-up wording in the shape of a grant's page
    return f"<main><h1>{title}</h1><p>Sample subtitle for {title}.</p>{body}</main>"


SUPPORT = page("Community Support Grant", """
<h4>Grant Opens: February 15, 2027</h4><h4>Grant Closes: Mar 26, 2027</h4>
<p>An organization is eligible to receive up to $10,000 in sample support.</p>
<ul><li>Open to Wyoming-based 501(c)(3) nonprofit organizations and government agencies</li>
<li>Grants require a 1:1 cash match</li></ul>""")
ACCESS = page("Arts Access Project Grant", """
<h4>Round One: May 1 – June 1, 2026 for projects starting between July – Sept 2026</h4>
<h4>Round Two: Dec 1 – Feb 1, 2027 for projects starting between March – June 2027</h4>
<p>The grant is available to organizations for sample access projects.</p>
<p>An organization is eligible to receive up to $1000. Individual artists cannot apply for this grant.</p>
<p>No cash match is required, and In-kind contributions will be reported.</p>""")
MENTORING = page("Mentoring Project Grants", """
<h4>Grant Opens: February 1, 2026</h4><h4>Grant Closes: June 22, 2026</h4>
<p>Open to Wyoming-based mentor artists and apprentices.</p>""")
PAGES = {"community-support": SUPPORT, "arts-access": ACCESS, "mentoring": MENTORING}


def page_of(url):
    return PAGES[url.rstrip("/").rsplit("/", 1)[-1]]


def built(today=TODAY, program_page=page_of):
    skips = []
    recs = wy.build_records(wy.read_rows(GRANTS, program_page, today), today=today, skips=skips)
    return {r["id"]: r for r in recs}, skips


def test_each_grant_linked_from_the_list_is_read():
    assert wy.parse(GRANTS) == [f"https://wyoarts.state.wy.us/grants/{p}/" for p in PAGES]


def test_dates_eligibility_and_match_come_from_the_grants_own_page():
    recs, _ = built()
    r = recs["wy-community-support-grant"]
    assert (r["opens"], r["closes"], r["status"]) == ("2027-02-15", "2027-03-26", "forecasted")
    assert r["applicant_types"] == "Open to Wyoming-based 501(c)(3) nonprofit organizations and government agencies"
    assert r["nonprofit_eligible"] is True and r["match"] == "1:1 cash" and "$10,000" in r["award"]
    assert "February 15, 2027" in r["application"] and r["url"].endswith("/community-support/")


def test_the_next_round_that_has_not_closed_is_shown():
    recs, _ = built()
    r = recs["wy-arts-access-project-grant"]
    assert (r["opens"], r["closes"]) == ("2026-12-01", "2027-02-01")   # the start takes the year before the end's
    assert "Individual artists cannot apply" in r["applicant_types"] and r["nonprofit_eligible"] is True
    # "No cash match" is not "no match": the card says it isn't stated
    assert r["match"] == "" and "match_none" not in r and match_words.statement(r) == match_words.NOT_STATED
    early, _ = built(today="2026-05-02")
    assert early["wy-arts-access-project-grant"]["closes"] == "2026-06-01"


def test_a_grant_open_to_artists_only_is_not_open_to_nonprofits_and_a_past_one_is_left_out():
    _, skips = built()
    assert [(s["name"], s["reason"]) for s in skips] == [("Mentoring Project Grants", "deadline_passed")]
    recs, _ = built(today="2026-05-02")
    assert recs["wy-mentoring-project-grants"]["nonprofit_eligible"] is False


def test_a_page_that_changed_shape_keeps_the_old_file():
    with pytest.raises(RuntimeError, match="grants on the Wyoming"):
        wy.parse("<main><h1>Grants</h1></main>")
    with pytest.raises(RuntimeError, match="no closing date or rounds"):
        built(program_page=lambda url: page("Community Support Grant", "<p>Dates to come.</p>"))
    with pytest.raises(RuntimeError, match="no heading"):
        built(program_page=lambda url: "<main><p>Moved</p></main>")


def test_the_labels_say_it_is_one_agency():
    spec = states.STATE_PROGRAMS["WY"]
    assert "one agency, not a statewide list" in spec["source"] and "1 agency" in spec["catalog"]
    assert states.STATES["WY"]["pages"] == [wy.LIST]


def test_saved_copies_are_read_without_the_network(tmp_path, monkeypatch):
    monkeypatch.setattr(webpages, "fetch_page", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no network")))
    (tmp_path / "grants.html").write_text(GRANTS, encoding="utf-8")
    for name, body in PAGES.items():
        (tmp_path / f"{name}.html").write_text(body.replace(", 2027", ", 2099").replace(", 2026", ", 2099"), encoding="utf-8")
    out = tmp_path / "wy.json.gz"
    assert wy.build(out, tmp_path / "skipped.json.gz", tmp_path) == 3
    assert json.loads(gzip.decompress(out.read_bytes()))["state"] == "WY"
