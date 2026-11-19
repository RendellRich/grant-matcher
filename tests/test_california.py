"""California Grants Portal rows into state program records (grantmatch/california.py)."""
import gzip
import json

import pytest

from grantmatch import california
from grantmatch.match import Profile
from grantmatch.rank_more import florida_doc, score_florida


def row(**over):
    base = {
        "PortalID": "101", "Status": "active", "LastUpdated": "2026-11-01 09:00:00", "AgencyDept": "State  Library",
        "Title": "Reading &amp; Literacy Grants", "Type": "Grant", "LOI": "Yes", "Categories": "Education; Libraries and Arts",
        "Purpose": "Help children read.", "Description": "Funds tutoring\xa0programs.",
        "ApplicantType": "Nonprofit; Public Agency", "ApplicantTypeNotes": "Must serve California residents.",
        "Geography": "Statewide", "MatchingFunds": "25%", "MatchingFundsNotes": "Cash or in kind.",
        "EstAvailFunds": "$1,000,000.00", "EstAwards": "Dependant on number of submissions received, application process, etc.",
        "EstAmounts": "Between $10,000.00 and $50,000.00", "FundingMethod": "Reimbursement(s)", "FundingMethodNotes": "",
        "OpenDate": "2026-10-01 07:00:00", "ApplicationDeadline": "2027-01-15 17:00:00", "AwardPeriod": "12 months",
        "ExpAwardDate": "March 2027", "ElecSubmission": "url: https://apply.example.ca.gov/;",
        "GrantURL": "https://example.ca.gov/grant", "AgencyURL": "https://example.ca.gov/",
        "ContactInfo": "name: Pat Lee; email: pat@example.ca.gov; tel: 1-916-555-0100;",
    }
    return {**base, **over}


def test_normalize_maps_the_portal_fields_onto_a_program_record():
    r = california.normalize(row())
    assert r["id"] == "ca-101" and r["state"] == "CA" and r["number"] == "101"
    assert r["title"] == "Reading & Literacy Grants" and r["agency"] == "State Library"
    assert r["objectives"] == "Help children read. Funds tutoring programs."
    assert r["applicant_types"] == "Nonprofit; Public Agency. Must serve California residents."
    assert r["nonprofit_eligible"] is True and r["earmark"] is False
    assert r["application"] == "A letter of intent is required. Apply online at https://apply.example.ca.gov/"
    assert r["award"] == ("Total available: $1,000,000.00. Award size: Between $10,000.00 and $50,000.00. "
                          "Paid by: Reimbursement(s). Award period: 12 months. Expected award date: March 2027.")
    assert r["restrictions"] == "Statewide Cash or in kind."
    assert r["contact"] == "Pat Lee, pat@example.ca.gov, 1-916-555-0100"
    assert (r["opens"], r["closes"], r["deadlines"]) == ("2026-10-01", "2027-01-15", "2027-01-15")
    assert (r["match"], r["loan"], r["loi"], r["funding_method"]) == ("25%", False, True, "Reimbursement(s)")
    assert r["url"] == "https://example.ca.gov/grant" and r["web"] == "https://example.ca.gov/"


def test_ongoing_deadlines_loans_and_missing_links():
    r = california.normalize(row(ApplicationDeadline="Ongoing", Type="Loan", MatchingFunds="Not Required", LOI="No",
                                 ElecSubmission="email: grants@example.ca.gov;", GrantURL="see website", AgencyURL=""))
    assert r["closes"] is None and r["deadlines"] == "Ongoing"
    assert r["loan"] is True and r["match"] == "" and r["loi"] is False
    assert r["application"] == "Apply by email to grants@example.ca.gov"
    assert r["url"] == california.PORTAL and r["web"] == ""
    assert california.normalize(row(Type="Grant; Loan"))["loan"] is False


def test_only_nonprofit_as_its_own_applicant_type_counts():
    assert california.normalize(row(ApplicantType="Public Agency; Tribal Government"))["nonprofit_eligible"] is False
    assert california.normalize(row(ApplicantType="Business; Nonprofit"))["nonprofit_eligible"] is True


def test_build_records_keeps_open_calls_once_and_drops_past_deadlines():
    rows = [row(), row(), row(PortalID="102", Status="closed"), row(PortalID="103", Status="forecasted"),
            row(PortalID="104", ApplicationDeadline="2026-11-01 17:00:00"), row(PortalID="105", Title=" "), row(PortalID="")]
    assert [r["id"] for r in california.build_records(rows, today="2026-11-19")] == ["ca-101", "ca-103"]


def test_build_refuses_a_file_with_too_few_open_calls(tmp_path):
    src = tmp_path / "ca.csv"
    src.write_text("PortalID,Status,Title\n1,active,Only one\n", encoding="utf-8")
    with pytest.raises(RuntimeError):
        california.build(tmp_path / "out.json.gz", src)
    assert not (tmp_path / "out.json.gz").exists()


def test_the_snapshot_scores_with_the_state_program_scorer():
    with gzip.open("data/california.json.gz", "rt", encoding="utf-8") as fh:
        payload = json.load(fh)
    recs = payload["programs"]
    assert payload["state"] == "CA" and len(recs) == payload["count"] >= california.MIN_ROWS
    assert len({r["id"] for r in recs}) == len(recs) and all(florida_doc(r) for r in recs)
    scored = score_florida(recs, Profile(mission="Reading help for children", keywords=["children", "education"]))
    assert len(scored) == sum(r["nonprofit_eligible"] for r in recs)
    assert scored.iloc[0]["score"] >= scored.iloc[-1]["score"]


def test_open_calls_lose_points_for_a_match_and_for_loans_and_flag_reimbursement():
    def one(profile=None, **over):
        rec = california.normalize(row(**{"MatchingFunds": "Not Required", "FundingMethod": "Advance(s)", **over}))
        return score_florida([rec], profile or Profile(mission="Reading help", keywords=["literacy"])).iloc[0]

    plain = one()
    assert plain["cautions"] == [] and plain["score"] > 30  # room to lose points before the floor at zero
    matched = one(MatchingFunds="25%")
    assert matched["cautions"] == ["Requires matching funds (25%)"] and abs(plain["score"] - matched["score"] - 20) <= 1  # each score is rounded on its own
    can = one(Profile(mission="Reading help", keywords=["literacy"], can_cost_share=True), MatchingFunds="25%")
    assert can["cautions"] == [] and can["score"] == plain["score"]
    loan = one(Type="Loan")
    assert loan["cautions"] == ["A loan, not a grant"] and abs(plain["score"] - loan["score"] - 25) <= 1
    paid_back = one(FundingMethod="Reimbursement(s)")
    assert paid_back["cautions"] == ["Pays by reimbursement: you spend first and are paid back"]
    assert paid_back["score"] == plain["score"]
    assert one(FundingMethod="Advances & Reimbursement(s)")["cautions"] == []
