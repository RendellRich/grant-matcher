"""IowaGrants.gov opportunities into state program records (grantmatch/iowa.py)."""
from grantmatch import iowa

LIST = """<table><tr><th>ID</th><th>Status</th><th>Categorical Area</th><th>Agency</th><th>Program Area</th><th>Title</th>
<th>Posted Date</th><th>Final-Application Due Date</th></tr>
<tr><td class="text-center">686491</TD><td><span class="label label-Posted">Posted</span></TD><td>Community Development,Volunteerism</TD>
<td>Iowa Commission on Volunteer Service</TD><td>AmeriCorps</TD>
<td><a href="viewStorefrontOpportunity.do?OIDString=1787247195083|Opportunity">AmeriCorps State 2027-2028</a></TD>
<td>Oct 1, 2026 9:00 AM</TD><td>Dec 1, 2026 11:59 PM</TD></tr>
<tr><td>371353</TD><td><span>Posted</span></TD><td>History</TD><td>Economic Development Authority</TD><td>Historic Preservation Tax Credit</TD>
<td><a href="viewStorefrontOpportunity.do?OIDString=1598543429719|Opportunity">Historic Preservation Tax Credit - Small Projects</a></TD>
<td>Oct 31, 2024 2:28 PM</TD><td>Not Applicable</TD></tr>
<tr><td>100</TD><td><span>Posted</span></TD><td>Health</TD><td>Health</TD><td>Old</TD>
<td><a href="viewStorefrontOpportunity.do?OIDString=1|Opportunity">Old RFP</a></TD><td>Jan 1, 2026 9:00 AM</TD><td>Feb 1, 2026 4:00 PM</TD></tr>
</table>"""

PAGE = """<h4>Final Application Deadline: Dec 1, 2026 11:59 PM</h4>
<p><span class='field-label'>Status</span> <span class='field'>Posted</span></p>
<p><span class='field-label'>Award Amount Range</span><span class='field'>No Limit - $250,000.00</span></p>
<p><span class='field-label'>Project Dates</span> <span class='field'>08/01/2027 - 12/31/2028</span></p>
<p><span class='field-label'>Recurring Opportunity</span> <span class='field'>Yes</span></p>
<p><span class='field-label'>Program Officer</span> <span class='field'>Pat Lee</span></p>
<p><span class='field-label'>Phone</span> <span class='field'>(515) 555-0100</span></p>
<p><span class='field-label'>Email</span> <span class='field'><a href="/cdn-cgi/l/email-protection#ab">[email&#160;protected]</a></span></p>
<legend>Description</legend><ul><li><span class='field' id='OpportunitySynopsis_synopsis'><p>AmeriCorps State places members
in Iowa communities.</p><p>Eligible applicants include nonprofit organizations, cities and schools.</p></span></li></ul>
<legend>Attachments</legend>"""


def test_list_rows_read_the_window_and_rolling_deadlines():
    rows = iowa.list_rows(LIST)
    assert [r["id"] for r in rows] == ["686491", "371353", "100"]
    assert rows[0]["title"] == "AmeriCorps State 2027-2028" and rows[0]["categories"] == "Community Development, Volunteerism"
    assert (rows[0]["posted"], rows[0]["closes"], rows[0]["no_end"]) == ("2026-10-01", "2026-12-01", False)
    assert rows[1]["closes"] is None and rows[1]["no_end"] is True
    assert rows[0]["detail"] == "https://www.iowagrants.gov/viewStorefrontOpportunity.do?OIDString=1787247195083|Opportunity"


def test_an_opportunity_page_becomes_a_record_without_the_hidden_email():
    f = iowa.fields(PAGE)
    assert "Email" not in f
    rec = iowa.normalize(iowa.list_rows(LIST)[0], f)
    assert rec["id"] == "ia-686491" and rec["state"] == "IA" and rec["number"] == "686491"
    assert rec["agency"] == "Iowa Commission on Volunteer Service, AmeriCorps"
    assert rec["nonprofit_eligible"] is True
    assert rec["applicant_types"] == "Eligible applicants include nonprofit organizations, cities and schools."
    assert rec["award"] == "Award size: Up to $250,000. Project dates: 08/01/2027 - 12/31/2028. Recurring: Yes."
    assert rec["contact"] == "Pat Lee, (515) 555-0100" and rec["deadlines"] == "2026-12-01"


def test_who_can_apply_is_read_from_the_description():
    yes, said = iowa.who_can_apply("Health", "Applicants must be 501(c)(3) organizations serving Iowa.")
    assert yes and said.startswith("Applicants must be 501(c)(3)")
    no, said = iowa.who_can_apply("Economic Development Authority", "Maximum grants: $100,000. City must be the applicant.")
    assert not no and "City must be the applicant" in said
    no, _ = iowa.who_can_apply("Administrative Services",
                               "The request must be made by a State of Iowa, county, or local government agency. "
                               "The agency can outsource the website to a non-profit organization.")
    assert not no   # a nonprofit named only as a vendor doesn't make it a nonprofit grant
    no, _ = iowa.who_can_apply("Health", "Nonprofits are not eligible for this funding.")
    assert not no
    no, said = iowa.who_can_apply("Education", "Districts will submit a claim through IowaGrants.")
    assert not no and "schools and districts" in said
    yes, said = iowa.who_can_apply("Health", "The purpose of this RFP is to fund HIV client services.")
    assert yes and "read the notice" in said


def test_closed_and_invitation_only_rows_are_skipped_and_tax_credits_named():
    rows = iowa.list_rows(LIST)
    pages = {rows[0]["id"]: {"Description": "By invitation only. Nonprofits may apply."},
             rows[1]["id"]: {"Description": "Only an eligible taxpayer may apply for tax credits under this program."}}
    skips = []
    recs = iowa.build_records(rows, today="2026-11-23", skips=skips, fetch=lambda r: pages[r["id"]])
    assert [r["id"] for r in recs] == ["ia-371353"]
    assert recs[0]["assistance"] == "Tax credit" and recs[0]["nonprofit_eligible"] is False and recs[0]["deadlines"] == "Ongoing"
    assert [(s["id"], s["reason"]) for s in skips] == [("ia-686491", "invitation_only"), ("ia-100", "deadline_passed")]
