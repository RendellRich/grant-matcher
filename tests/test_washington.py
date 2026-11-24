"""FundHubWA listings into state program records (grantmatch/washington.py)."""
from grantmatch import washington as wa

TAX = {
    "funding-audience": {8: "Nonprofits", 19: "Businesses", 20: "Local Government", 21: "Individuals"},
    "funding-type": {6: "Grant", 15: "Loan", 16: "Rebate"},
    "funding-sector": {70: "Climate", 33: "Resilience"},
    "funding-disbursement-method": {39: "Reimbursement", 72: "Unspecified"},
}


def row(rid=2231, **acf):
    base = {
        "funding_status": "active", "federal_or_state": "state", "source": "Washington State Department of Commerce ",
        "application_open_date": "20261012", "application_close_date": "20261201", "internal_reference_id": "WAFHW2231",
        "total_amount": "10,544,325", "award_start": "50000", "ending_amount": "500000", "number_of_awards": "",
        "cost_share": "no", "pre_application": "no", "disbursement_notes": "",
        "description": "Grants to build systems that capture methane &amp; cut emissions.",
        "requirements": "<ul>\r\n<li>$2 million set aside.</li>\r\n</ul>",
        "eligibility": "<ul><li>Project must be in Washington.</li></ul>",
        "application_link": {"title": "Apply", "url": "https://app.example.com/form", "target": "_blank"},
        "contact": "Program manager <a href=\"mailto:grants@commerce.wa.gov\">grants@commerce.wa.gov</a>",
        "resources": "<h2>How to apply</h2>Read the RFA first.",
    }
    base.update(acf)
    return {"id": rid, "link": f"https://fundhub.wa.gov/funding/x-{rid}/", "title": {"rendered": "Dairy Digester Program"},
            "modified": "2026-11-05T16:39:01", "funding-type": [6], "funding-audience": [8, 19],
            "funding-sector": [70, 33], "funding-disbursement-method": [39], "acf": base}


def test_a_listing_becomes_an_open_call_record():
    rec = wa.normalize(row(), TAX)
    assert rec["id"] == "wa-2231" and rec["state"] == "WA" and rec["number"] == "WAFHW2231"
    assert rec["agency"] == "Washington State Department of Commerce"
    assert rec["objectives"] == "Grants to build systems that capture methane & cut emissions. $2 million set aside."
    assert rec["nonprofit_eligible"] is True
    assert rec["applicant_types"] == "Nonprofits, Businesses. Project must be in Washington."
    assert "Award size: $50,000 to $500,000." in rec["award"] and "Total available: $10,544,325." in rec["award"]
    assert (rec["opens"], rec["closes"], rec["deadlines"]) == ("2026-10-12", "2026-12-01", "2026-12-01")
    assert rec["funding_method"] == "Reimbursement" and rec["subjects"] == "Climate; Resilience"
    assert rec["web"] == "https://app.example.com/form" and rec["application"].endswith("Apply: https://app.example.com/form")
    assert rec["contact"] == "Program manager grants@commerce.wa.gov"
    assert rec["match"] == "" and rec["loan"] is False and rec["loi"] is False


def test_the_portals_audience_tags_decide_who_can_apply():
    homes = row()
    homes["funding-audience"] = [21]
    assert wa.normalize(homes, TAX)["nonprofit_eligible"] is False
    untagged = row(eligibility="<li>Non-profit 501(c)(3) organizations</li><li>Tribes</li>")
    untagged["funding-audience"] = []
    assert wa.normalize(untagged, TAX)["nonprofit_eligible"] is True
    cities = row(eligibility="Only cities and counties may apply.")
    cities["funding-audience"] = []
    assert wa.normalize(cities, TAX)["nonprofit_eligible"] is False
    silent = row(eligibility="")
    silent["funding-audience"] = []
    rec = wa.normalize(silent, TAX)
    assert rec["nonprofit_eligible"] is True and "read the program page" in rec["applicant_types"]


def test_only_open_state_money_is_kept():
    rows = [row(2231),
            row(2232, federal_or_state="federal"),                       # Grants.gov has it already
            row(2233, funding_status="closed"),                          # history, not a skip
            row(2234, application_close_date="20261101"),                # marked active, but closed
            row(2235, application_close_date="", description="Rolling.")]
    skips = []
    recs = wa.build_records(rows, TAX, today="2026-11-23", skips=skips)
    assert [r["id"] for r in recs] == ["wa-2231", "wa-2235"]
    assert recs[1]["deadlines"] == "Ongoing" and recs[1]["closes"] is None
    assert [(s["id"], s["reason"]) for s in skips] == [("wa-2234", "deadline_passed")]


def test_topic_tags_in_the_agency_field_are_not_shown_as_the_agency():
    rec = wa.normalize(row(source="Agriculture, Climate, Rural, Workforce Development"), TAX)
    assert rec["agency"] == "Washington state agency (named on the program page)"


def test_loans_cost_share_and_pre_applications_are_read():
    r = row(cost_share="yes", pre_application="yes")
    r["funding-type"] = [15]
    rec = wa.normalize(r, TAX)
    assert rec["loan"] is True and rec["match"] == "Required" and rec["loi"] is True and rec["assistance"] == "Loan"
