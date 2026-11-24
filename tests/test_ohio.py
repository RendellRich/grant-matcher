"""Ohio Grants Partnership opportunities into state program records (grantmatch/ohio.py)."""
from grantmatch import ohio


def item(**over):
    opp = {
        "OpportunityNumber": "DEV-HAGP26", "OpportunityTitle": "Housing Assistance Grant Program",
        "ApplicationStartDate": "2026-11-04T00:00:00", "ApplicationDueDate": "2026-12-02T00:00:00",
        "DisplayAEndDate": "12/02/2026", "MoreInformationURL": "https://development.ohio.gov/housing",
        "OverviewDetails": "Application through OH|ID.<br>\n\nGoal: affordable housing for very low-income families.",
        "ProvidedProjectDescription": "", "EstimatedFunding": 5000000, "AwardFloor": 100000, "AwardCeiling": 1200000,
        "AverageAwardSize": 300000, "MatchingRequired": True, "FinancialDetails": "Ohio Housing Trust Fund.",
        "ContactFirstName": "Pat", "ContactLastName": "Lee", "ContactEmail": "pat@example.gov", "ContactPhone": "",
        "AgencyBusinessUnitDescription": "Office of Community Enhancements", "RegistrationRequired": False,
        "GUID": "666a5829-e5d6-f111-8f3c-00505680042e", "InsertedDate": "2026-11-01T08:00:00", "UpdatedDate": None,
        "AgencyDivision": {"DivisionName": "No Division", "Agency": {"AgencyName": "Department of Development", "AgencyCode": "DEV"}},
    }
    opp.update(over.pop("opp", {}))
    base = {"Opportunity": opp, "OpportunityCategories": [{"Code": "Housing", "IsValid": True}],
            "EligibleApplicants": [{"Code": "Non-Profit", "IsValid": True}, {"Code": "County", "IsValid": True}],
            "AssistanceListings": []}
    base.update(over)
    return base


def test_an_opportunity_becomes_an_open_call_record():
    rec = ohio.normalize(item())
    assert rec["id"] == "oh-dev-hagp26" and rec["state"] == "OH" and rec["number"] == "DEV-HAGP26"
    assert rec["agency"] == "Department of Development, Office of Community Enhancements"
    assert rec["objectives"] == "Application through OH|ID. Goal: affordable housing for very low-income families."
    assert rec["nonprofit_eligible"] is True and rec["applicant_types"] == "Non-Profit; County"
    assert "Award size: $100,000 to $1,200,000." in rec["award"] and "Total available: $5,000,000." in rec["award"]
    assert (rec["opens"], rec["closes"], rec["deadlines"]) == ("2026-11-04", "2026-12-02", "2026-12-02")
    assert rec["match"] == "Required" and rec["subjects"] == "Housing"
    assert rec["url"].endswith("detailid=666a5829-e5d6-f111-8f3c-00505680042e")
    assert rec["contact"] == "Pat Lee, pat@example.gov"


def test_the_states_applicant_types_decide_who_can_apply():
    gov = ohio.normalize(item(EligibleApplicants=[{"Code": "Township"}, {"Code": "Village"}, {"Code": "Houses of Worship"}]))
    assert gov["nonprofit_eligible"] is False
    faith = ohio.normalize(item(EligibleApplicants=[{"Code": "Faith-based Associations/Organizations"}]))
    assert faith["nonprofit_eligible"] is True
    invalid = ohio.normalize(item(EligibleApplicants=[{"Code": "Non-Profit", "IsValid": False}, {"Code": "City"}]))
    assert invalid["nonprofit_eligible"] is False
    none = ohio.normalize(item(EligibleApplicants=[]))
    assert none["nonprofit_eligible"] is True and "read the notice" in none["applicant_types"]


def test_closed_untitled_and_invitation_only_rows_are_skipped_with_a_reason():
    rows = [item(),
            item(opp={"OpportunityNumber": "OLD-1", "ApplicationDueDate": "2026-10-01T00:00:00"}),
            item(opp={"OpportunityNumber": "X-2", "OpportunityTitle": ""}),
            item(opp={"OpportunityNumber": "INV-3", "OverviewDetails": "This grant is by invitation only."})]
    skips = []
    recs = ohio.build_records(rows, today="2026-11-23", skips=skips)
    assert [r["id"] for r in recs] == ["oh-dev-hagp26"]
    assert [(s["id"], s["reason"]) for s in skips] == [
        ("oh-old-1", "deadline_passed"), ("oh-x-2", "no_title"), ("oh-inv-3", "invitation_only")]


def test_no_amounts_and_a_missing_guid_still_give_a_usable_record():
    rec = ohio.normalize(item(opp={"AwardFloor": 0, "AwardCeiling": 0, "EstimatedFunding": None, "AverageAwardSize": 0,
                                   "FinancialDetails": "", "GUID": "", "MatchingRequired": False}))
    assert rec["award"] == "" and rec["match"] == ""
    assert rec["url"] == ohio.SITE
