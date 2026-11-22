from grantmatch import illinois as il

LIST = """
<table><tr><th>Opportunity Title</th><th>Agency</th><th>Application Date Range</th><th>Award Range</th></tr>
<tr><td><i Class='gms'>GMS</i>&nbsp;<a href='GMS.aspx?url=https%3a%2f%2fil.amplifund.com%2fPublic%2fOpportunities%2fDetails%2fabc-123&title=X' target='_blank'>Youth Reading Grant</a></td>
<td>ISBE (586)</td><td>11/02/2026 - 01/06/2027</td><td>$1000 - $25000</td></tr>
<tr><td><a href='Opportunity.aspx?nofo=4362'>Prison Education</a></td><td>IBHE (601)</td><td>04/03/2025 - No end date</td><td>Not Applicable</td></tr>
<tr><td><a href='Opportunity.aspx?nofo=99'>Old Notice</a></td><td>DNR (422)</td><td>01/01/2025 - 02/01/2025</td><td>$0 - $0</td></tr>
</table>"""

AMPLIFUND = """<div>Description</div><div>Grants for after-school reading programs.</div><div>More detail here.</div>
<div>Awarding Agency Name</div><div>Board of Education</div><div>Agency Contact Email</div><div>a@b.gov</div>
<div>Award Ceiling</div><div>$25,000.00</div><div>Award Floor</div><div>$1,000.00</div><div>Award Start Date</div>
<div>Matching Requirement</div><div>No</div><div>Eligible Applicants</div><div>Government Organizations, Nonprofit Organizations</div>
<div>Applicant Eligibility Information</div><div>Must serve Illinois students.</div><div>Beneficiary Eligibility Information</div><div>None</div>"""


def test_list_rows_read_both_kinds_of_link_and_the_window():
    rows = il.list_rows(LIST)
    assert [r["kind"] for r in rows] == ["gms", "csfa", "csfa"]
    assert rows[0]["detail"] == "https://il.amplifund.com/Public/Opportunities/Details/abc-123"
    assert rows[0]["title"] == "Youth Reading Grant"
    assert (rows[0]["opens"], rows[0]["closes"]) == ("2026-11-02", "2027-01-06")
    assert rows[1]["no_end"] and rows[1]["closes"] is None
    assert rows[1]["detail"].endswith("Opportunity.aspx?nofo=4362")


def test_amplifund_page_becomes_an_open_call_record():
    row = il.list_rows(LIST)[0]
    rec = il.normalize(row, il.fields(AMPLIFUND, il.AMPLIFUND_LABELS))
    assert rec["id"] == "il-abc-123" and rec["state"] == "IL"
    assert rec["objectives"] == "Grants for after-school reading programs. More detail here."
    assert rec["nonprofit_eligible"] is True
    assert rec["applicant_types"].startswith("Government Organizations, Nonprofit Organizations. Must serve")
    assert "Award size: $1,000 to $25,000." in rec["award"]
    assert rec["match"] == "" and rec["closes"] == "2027-01-06" and rec["deadlines"] == "2027-01-06"


def test_state_categories_decide_who_can_apply():
    row = il.list_rows(LIST)[1]
    edu = {"Eligible Applicants": "Education Organizations;",
           "Applicant Eligibility": "Illinois public and non-profit, independent four-year institutions"}
    assert il.normalize(row, edu)["nonprofit_eligible"] is False   # a university grant, not a nonprofit one
    others = {"Eligible Applicants": "Others", "Applicant Eligibility Information": "Illinois nonprofit organizations and farms"}
    assert il.normalize(row, others)["nonprofit_eligible"] is True
    nothing = il.normalize(row, {})
    assert nothing["nonprofit_eligible"] is True and "read the notice" in nothing["applicant_types"]
    assert nothing["deadlines"] == "Ongoing"


def test_closed_windows_are_skipped_with_a_reason():
    skips = []
    recs = il.build_records(il.list_rows(LIST), today="2026-11-22", skips=skips, fetch=lambda row: {})
    assert [r["title"] for r in recs] == ["Prison Education", "Youth Reading Grant"]
    assert [(s["name"], s["reason"]) for s in skips] == [("Old Notice", "deadline_passed")]


def test_money_is_written_the_same_way_everywhere():
    assert il._money("2120450.00") == "$2,120,450"
    assert il._money("$250000 - $25000000") == "$250,000 - $25,000,000"
    assert il._money("Not Applicable") == ""
