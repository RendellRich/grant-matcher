"""Missouri's three agencies' pages into state program records (grantmatch/missouri.py), and the disclaimer the
state requires."""
from pathlib import Path

import pytest

from grantmatch import match_words, skipped, states
from grantmatch import missouri as mo

FIXTURES = Path(__file__).parent / "fixtures"
read = lambda name: (FIXTURES / f"missouri-{name}.html").read_text(encoding="utf-8")
PROGRAM = read("program")
TODAY = "2026-11-27"
# the words as https://mo.gov/data-policy gave them on 2026-11-27, verbatim
REQUIRED = (
    "The data made available here has been modified for use from its original source, which is the State of Missouri. "
    "THE STATE OF MISSOURI MAKES NO REPRESENTATIONS OR WARRANTY AS TO THE COMPLETENESS, ACCURACY, TIMELINESS, OR "
    "CONTENT OF ANY DATA MADE AVAILABLE THROUGH THIS SITE. THE STATE OF MISSOURI EXPRESSLY DISCLAIMS ALL WARRANTIES, "
    "WHETHER EXPRESS OR IMPLIED, INCLUDING ANY IMPLIED WARRANTIES OF MERCHANTABILITY, OR FITNESS FOR A PARTICULAR "
    "PURPOSE. The data is subject to change as modifications and updates are complete. It is understood that the "
    "information contained in the Web feed is being used at one’s own risk.")


def pages(**changed):
    saved = {"notices": read("notices"), "grants": read("grants"), "apply": read("apply"), "express": read("express"),
             "serve": read("serve"), "well-plugging-grant": PROGRAM,
             "lead-service-line": PROGRAM.replace("Awards are limited", "Grant Amounts</p><p>Awards are limited")
             .replace("<h2>Award Amounts and Match</h2>", "<h2>Award Amounts and Match</h2><p>Grant Amounts</p>"),
             "planning-grant": PROGRAM.replace("Community and not-for-profit noncommunity public water systems with at "
                                               "least one well", "Regional Planning Commissions")}
    saved.update(changed)
    return lambda url, name: saved[name]


def built(today=TODAY, **changed):
    skips = []
    recs = mo.build_records(mo.read_rows(pages(**changed), today), today=today, skips=skips)
    return {r["id"]: r for r in recs}, {s["id"]: s["reason"] for s in skips}


def test_only_open_calls_a_nonprofit_could_apply_to_are_kept():
    recs, skips = built()
    assert sorted(recs) == [
        "mo-americorps-state-national-funding-opportunity-formula-funding", "mo-annual-grants-fy2028",
        "mo-drinking-water-state-revolving-fund-dwsrf-lead-service-line-funding", "mo-express-grants",
        "mo-well-plugging-grant"]
    assert all(r["nonprofit_eligible"] for r in recs.values())
    assert skips == {
        "mo-water-quality-planning-grant": "state_not_nonprofit", "mo-state-parks-bus-grants": "page_not_read",
        "mo-americorps-state-national-funding-opportunity-competitive-funding": "deadline_passed",
        "mo-2027-spring-planning-grant-funding-opportunity": "not_taking",
        "mo-america-250-mini-grant-funding-opportunity": "not_taking"}


def test_dates_match_and_application_come_from_the_pages():
    recs, _ = built()
    well = recs["mo-well-plugging-grant"]
    assert (well["opens"], well["closes"], well["assistance"]) == ("2026-11-01", "2027-02-28", "Grant")
    assert well["match"] == "Plugging public water wells requires a cost-share of 25% for each well."
    assert "water@" not in well["application"] and well["application"].startswith("The department is accepting")
    # "Revolving Fund" in the title, but the page gives grant amounts
    lead = recs["mo-drinking-water-state-revolving-fund-dwsrf-lead-service-line-funding"]
    assert (lead["assistance"], lead["loan"]) == ("Grant", False)
    express = recs["mo-express-grants"]
    assert (express["deadlines"], express["match_none"], match_words.statement(express)) == \
        ("Ongoing", True, match_words.NONE)
    assert "not-for-profit corporation" in express["applicant_types"]
    assert recs["mo-annual-grants-fy2028"]["closes"] == "2027-01-04"
    formula = recs["mo-americorps-state-national-funding-opportunity-formula-funding"]
    assert (formula["closes"], formula["loi"]) == ("2027-03-19", True)
    assert formula["application"] == \
        "Notice of Intent deadline: February 19, 2027. Application deadline: March 19, 2027."
    late, _ = built(today="2027-03-01")
    assert "That date has passed" in \
        late["mo-americorps-state-national-funding-opportunity-formula-funding"]["application"]


@pytest.mark.parametrize("name, old, new", [
    ("notices", "</tbody>", '</tbody><a href="?page=1">Next</a>'), ("well-plugging-grant", "Who Can Apply", "Eligibility"),
    ("apply", "Who may apply", "Eligibility"), ("express", "The deadline for applications is", "Send it by"),
    ("grants", "deadline for the FY2028 Intent to Apply is", "Intent to Apply is due"),
    ("serve", "Funding Opportunity", "Chance"),
])
def test_a_page_that_loses_the_part_its_dates_come_from_stops_the_run(name, old, new):
    changed = pages()(None, name).replace(old, new)
    with pytest.raises(RuntimeError, match="keeping the previous data file"):
        built(**{name: changed})


def test_the_required_disclaimer_is_the_states_words():
    assert states.DISCLAIMERS == {"MO": {"name": "Missouri", "text": REQUIRED}}
    doc = (Path(mo.__file__).parent.parent / "docs/state-coverage.md").read_text(encoding="utf-8")
    assert REQUIRED in doc


def test_the_skipped_report_carries_the_disclaimer_only_when_it_lists_missouri_calls():
    row = {"source": "missouri", "id": "mo-a", "name": "A", "funder": "F", "state": "MO", "reason": "not_taking",
           "detail": "", "url": ""}
    text = skipped.build([row], {}, {}, "2026-11-27", [])[1]
    assert text.index(f"Notice for Missouri listings: {REQUIRED}") < text.index("| A |")
    assert "Notice for" not in skipped.build([{**row, "state": "OH", "source": "ohio"}], {}, {}, "2026-11-27", [])[1]
