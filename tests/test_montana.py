"""The Montana Arts Council's grant pages into state program records (grantmatch/montana.py)."""
import gzip
import json
from pathlib import Path

import pytest

from grantmatch import match_words, states, webpages
from grantmatch import montana as mt

FIXTURES = Path(__file__).parent / "fixtures"
read = lambda name: (FIXTURES / f"montana-{name}.html").read_text(encoding="utf-8")
ARTSED, GUIDE, HEALTH, SIG = read("artsed"), read("guidelines"), read("health"), read("sig")
# the Residencies guidelines: one deadline, past, and a match
RESIDENCIES = (GUIDE.replace("Experiences", "Residencies")
               .replace("Grant awards are between $250 and $2,500. No match is required, but the grant is reimbursement-based.",
                        "Grant awards are between $2500 and $10,000 and require a 1:1 match.")
               .replace("<li>December 10, 2026 at 11:59 PM</li>", "").replace("August 13, 2026", "March 19, 2026"))
TODAY = "2026-11-26"


def pages(**changed):
    saved = {"artsed": ARTSED, "experiences": GUIDE, "residencies": RESIDENCIES, "artsinhealth": HEALTH, "sig": SIG}
    saved.update(changed)
    return lambda url, name: saved[name]


def built(today=TODAY, **changed):
    skips = []
    recs = mt.build_records(mt.read_rows(pages(**changed), today), today=today, skips=skips)
    return {r["id"]: r for r in recs}, skips


def test_each_open_grant_takes_its_dates_eligibility_and_match_from_its_pages():
    recs, skips = built()
    assert sorted(recs) == ["mt-arts-education-experiences", "mt-arts-in-health", "mt-strategic-investment-grants"]
    assert [(s["id"], s["reason"]) for s in skips] == [("mt-arts-education-residencies", "deadline_passed")]
    exp = recs["mt-arts-education-experiences"]
    assert (exp["closes"], exp["nonprofit_eligible"], exp["funding_method"]) == ("2026-12-10", True, "Reimbursement")
    assert exp["url"] == "https://art.mt.gov/ArtsEducationExperiencesSample"
    assert exp["applicant_types"].startswith("Nonprofit organization with an IRS 501(c)(3) ruling")
    assert "must submit a sample letter" in exp["applicant_types"] and "may not be awarded to individuals" in exp["applicant_types"]
    assert (exp["match"], exp["match_none"], match_words.statement(exp)) == ("", True, match_words.NONE)
    assert "SAM UEI" in exp["restrictions"] and "Project timeframe: Projects between February 1" in exp["application"]
    assert "closed" not in json.dumps(exp)   # the application form below the guidelines isn't read
    health = recs["mt-arts-in-health"]
    assert (health["opens"], health["closes"], health["status"]) == ("2026-12-10", "2027-01-18", "forecasted")
    assert health["applicant_types"] == mt.UNSTATED and match_words.statement(health) == match_words.NOT_STATED
    sig = recs["mt-strategic-investment-grants"]
    assert (sig["closes"], sig["deadlines"], sig["nonprofit_eligible"]) == (None, "Ongoing", True)
    assert sig["application"].startswith("Applications are due on the 15th of each month") and "@" not in sig["application"]
    assert match_words.statement(sig) == match_words.NOT_STATED


@pytest.mark.parametrize("said", [
    "Applications are paused.", "Funds have run out for this year.", "This program is on hold.",
    "We have stopped taking requests.", "The fund is fully committed.", "Check back next spring.",
])
def test_the_monthly_grant_goes_when_its_page_says_anything_against_it(said):
    recs, skips = built(sig=SIG.replace("<h3>Application Deadline</h3>", f"<p>{said}</p><h3>Application Deadline</h3>"))
    assert "mt-strategic-investment-grants" not in recs
    assert ("mt-strategic-investment-grants", "not_taking") in [(s["id"], s["reason"]) for s in skips]


def test_the_monthly_grant_needs_the_page_to_say_it_takes_applications():
    recs, skips = built(sig=SIG.replace("due on the 15th of each month by 11:59 p.m.", "due on a date to be announced."))
    assert "mt-strategic-investment-grants" not in recs
    assert ("mt-strategic-investment-grants", "no_deadline") in [(s["id"], s["reason"]) for s in skips]


def test_past_dates_are_left_out():
    recs, _ = built(today="2027-02-01")
    assert sorted(recs) == ["mt-strategic-investment-grants"]


@pytest.mark.parametrize("name, old, new, match", [
    ("artsed", "GRANTS LOGIN", "SIGN IN", "menu or footer"),
    ("artsed", "Experiences FY27 Guidelines (HTML)", "Experiences guide", "no longer links both"),
    ("artsed", 'href="ArtsEducationExperiencesSample"', 'href="/obsolete/old"', "somewhere new"),
    ("artsed", 'href="ArtsEducationExperiencesSample"', 'href="https://example.org/x"', "somewhere new"),
    ("experiences", "All applicants must be one of the following:", "Applicants:", "who may apply"),
    ("artsinhealth", "Next opportunity", "Later", "Next opportunity"),
    ("artsinhealth", "Deadline for application submissions", "Entries", "gives its deadline"),
    ("sig", "<h3>Application Deadline</h3>", "<h3>When</h3>", "Application Deadline"),
    ("sig", "provide up to $1000", "help", "who or how much"),
])
def test_a_page_that_changed_shape_keeps_the_old_file(name, old, new, match):
    page = {"artsed": ARTSED, "experiences": GUIDE, "artsinhealth": HEALTH, "sig": SIG}[name]
    assert old in page
    with pytest.raises(RuntimeError, match=match):
        built(**{name: page.replace(old, new)})
    with pytest.raises(RuntimeError, match="no deadline"):
        built(experiences=GUIDE.replace(" at 11:59 PM", ""))


def test_the_labels_say_it_is_one_agency():
    spec = states.STATE_PROGRAMS["MT"]
    assert "one agency, not a statewide list" in spec["source"] and "1 agency" in spec["catalog"]
    assert states.STATES["MT"]["pages"] == [mt.LIST, mt.HEALTH, mt.INVESTMENT]
    assert not [u for u in states.STATES["MT"]["pages"] if "/obsolete" in u]


def test_saved_copies_are_read_without_the_network(tmp_path, monkeypatch):
    monkeypatch.setattr(webpages, "fetch_page", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no network")))
    later = lambda s: s.replace(", 2027", ", 2099").replace(", 2026", ", 2099")
    for name, body in (("artsed", ARTSED), ("experiences", GUIDE), ("residencies", RESIDENCIES), ("artsinhealth", HEALTH),
                       ("sig", SIG)):
        (tmp_path / f"{name}.html").write_text(later(body), encoding="utf-8")
    out = tmp_path / "mt.json.gz"
    assert mt.build(out, tmp_path / "skipped.json.gz", tmp_path) == 4
    assert json.loads(gzip.decompress(out.read_bytes()))["state"] == "MT"
