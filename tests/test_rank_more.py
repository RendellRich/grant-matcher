from grantmatch.florida import _title, normalize as fl_normalize, parse_detail
from grantmatch.foundations import parse_return, summarize
from grantmatch.match import Profile
from grantmatch.rank_more import score_florida, score_foundations

PROFILE = Profile(mission="Free literacy tutoring for children with dyslexia.",
                  keywords=["literacy", "dyslexia", "tutoring", "children"])


def fdn(**kw):
    base = {
        "ein": "1", "name": "Sunshine Fund", "city": "TAMPA", "state": "FL", "zip": "33602", "tax_year": "2024",
        "assets": 2_000_000.0, "grants_total": 100_000.0, "website": "", "preselected_only": False,
        "apply": {"contact": "Jane Doe", "materials": "Letter of inquiry", "restrictions": "", "deadlines": "March 1"},
        "grant_count": 10, "grant_median": 5000.0, "grant_min": 1000.0, "grant_max": 20000.0,
        "recipient_states": {"FL": 9, "GA": 1},
        "top_purposes": ["children's literacy program", "after school tutoring"],
        "sample_grants": [{"to": "Reading Club", "city": "BRADENTON", "state": "FL", "purpose": "literacy", "amount": 5000.0}],
        "url": "https://example.org",
    }
    base.update(kw)
    return base


def test_local_literacy_funder_ranks_above_out_of_state_one():
    out = score_foundations(
        [fdn(ein="1"), fdn(ein="2", name="Far Away Fund", state="WA", recipient_states={"WA": 10},
                           top_purposes=["salmon habitat"], sample_grants=[])],
        PROFILE, "FL", ["Bradenton"])
    assert list(out["ein"]) == ["1", "2"]
    top = out.iloc[0]
    assert any("9 of its 10 grants went to FL" in r for r in top["reasons"])
    assert any("Bradenton" in r for r in top["reasons"])
    assert any("No grants to FL" in c for c in out.iloc[1]["cautions"])


def test_no_unsolicited_and_preselected_rules():
    closed = fdn(ein="3", apply={"restrictions": "The foundation does not accept unsolicited requests."})
    out = score_foundations([fdn(ein="1"), closed], PROFILE, "FL", [])
    assert out.set_index("ein").loc["3", "score"] < out.set_index("ein").loc["1", "score"]
    pre = fdn(ein="4", preselected_only=True)
    assert "4" not in set(score_foundations([pre, fdn()], PROFILE, "FL", [])["ein"])
    assert "4" in set(score_foundations([pre, fdn()], PROFILE, "FL", [], show_preselected=True)["ein"])


def test_large_typical_grant_is_flagged():
    p = Profile(**{**PROFILE.__dict__, "budget_band": "Under $50k"})
    out = score_foundations([fdn(grant_median=250_000.0)], p, "FL", [])
    assert any("large next to your budget" in c for c in out.iloc[0]["cautions"])


def prog(**kw):
    base = {"id": "fl-1", "csfa": "48.001", "title": "Reading Grants", "agency": "Department of Education",
            "objectives": "Literacy tutoring for struggling readers.", "assistance": "Grants",
            "applicant_types": "Nonprofit", "nonprofit_eligible": True, "earmark": False, "restrictions": "",
            "application": "Competitive request for applications.", "award": "", "deadlines": "", "contact": "",
            "web": "", "subjects": "Education", "fiscal_year": "2026-2027", "url": "https://example.org"}
    base.update(kw)
    return base


def test_florida_filters_earmarks_and_non_nonprofit_programs():
    rows = [prog(id="fl-1"), prog(id="fl-2", earmark=True), prog(id="fl-3", nonprofit_eligible=False)]
    out = score_florida(rows, PROFILE)
    assert list(out["id"]) == ["fl-1"]
    assert any("competitive" in r for r in out.iloc[0]["reasons"])
    assert set(score_florida(rows, PROFILE, show_earmarks=True)["id"]) == {"fl-1", "fl-2"}


def test_florida_detail_parsing_and_earmark_detection():
    page = """<td>CSFA Number:</td><td>64.030</td><td>State Project Title:</td><td>COMMUNITY HEALTH INITIATIVES</td>
    <td>Agency:</td><td>Department of Health</td><td>Objectives:</td><td>To provide funds.</td>
    <td>Types Of Assistance:</td><td>Grants</td><td>Applicant Type:</td><td>Local Government, Non-Profit.</td>
    <td>Award Procedures:</td><td>Direct allocation (Earmark) from FY 2021-22 General Appropriations Act.</td>
    <td>Return To Top</td>"""
    rec = fl_normalize("9", parse_detail(page), "2026-2027")
    assert rec["csfa"] == "64.030" and rec["nonprofit_eligible"] and rec["earmark"]
    assert rec["title"] == "Community Health Initiatives"
    assert _title("FRIENDS OF THE LIBRARY") == "Friends of the Library"


SAMPLE_990PF = b"""<?xml version="1.0" encoding="utf-8"?>
<Return xmlns="http://www.irs.gov/efile"><ReturnHeader><TaxYr>2024</TaxYr><Filer><EIN>123456789</EIN>
<BusinessName><BusinessNameLine1Txt>GULF COAST KIDS FUND</BusinessNameLine1Txt></BusinessName>
<USAddress><CityNm>SARASOTA</CityNm><StateAbbreviationCd>FL</StateAbbreviationCd><ZIPCd>34236</ZIPCd></USAddress></Filer></ReturnHeader>
<ReturnData><IRS990PF><FMVAssetsEOYAmt>500000</FMVAssetsEOYAmt><ContriPaidRevAndExpnssAmt>30000</ContriPaidRevAndExpnssAmt>
<SupplementaryInformationGrp><ApplicationSubmissionInfoGrp><RecipientPersonNm>A SMITH</RecipientPersonNm>
<FormAndInfoAndMaterialsTxt>ONE PAGE LETTER</FormAndInfoAndMaterialsTxt><SubmissionDeadlinesTxt>NONE</SubmissionDeadlinesTxt>
</ApplicationSubmissionInfoGrp>
<GrantOrContributionPdDurYrGrp><RecipientBusinessName><BusinessNameLine1Txt>READ TOGETHER INC</BusinessNameLine1Txt></RecipientBusinessName>
<RecipientUSAddress><CityNm>BRADENTON</CityNm><StateAbbreviationCd>FL</StateAbbreviationCd></RecipientUSAddress>
<GrantOrContributionPurposeTxt>CHILDREN'S LITERACY</GrantOrContributionPurposeTxt><Amt>20000</Amt></GrantOrContributionPdDurYrGrp>
<GrantOrContributionPdDurYrGrp><RecipientBusinessName><BusinessNameLine1Txt>CITY BALLET</BusinessNameLine1Txt></RecipientBusinessName>
<RecipientUSAddress><CityNm>ATLANTA</CityNm><StateAbbreviationCd>GA</StateAbbreviationCd></RecipientUSAddress>
<GrantOrContributionPurposeTxt>GENERAL SUPPORT</GrantOrContributionPurposeTxt><Amt>10000</Amt></GrantOrContributionPdDurYrGrp>
</SupplementaryInformationGrp></IRS990PF></ReturnData></Return>"""


def test_990pf_parsing():
    rec = summarize(parse_return(SAMPLE_990PF))
    assert rec["ein"] == "123456789" and rec["state"] == "FL" and rec["name"] == "GULF COAST KIDS FUND"
    assert rec["grant_count"] == 2 and rec["grant_median"] == 15000
    assert rec["recipient_states"] == {"FL": 1, "GA": 1}
    assert rec["apply"]["materials"] == "ONE PAGE LETTER"
    assert rec["sample_grants"][0]["to"] == "READ TOGETHER INC"
    assert not rec["preselected_only"]


def test_florida_named_recipients_and_scholarships():
    from grantmatch.florida import is_earmark
    assert is_earmark("Big Brothers Big Sisters", "To generate revenue for Big Brothers Big Sisters.", "Other", "N/A", "")
    assert is_earmark("Moffitt Cancer Center License Plates", "", "Other", "N/A", "")
    assert is_earmark("Pinellas Goodwill Pathways", "", "Grants", "Notice to enroll and complete Budget Proposal", "")
    assert not is_earmark("Mentoring / Student Assistance Initiatives", "Mentoring for at-risk students.", "Grants",
                          "Department awards grants after program application and budget review.", "")
    out = score_florida([prog(id="fl-1"), prog(id="fl-2", title="Minority Teacher Scholarship Program")], PROFILE)
    assert any("Student aid" in c for c in out.set_index("id").loc["fl-2", "cautions"])


def test_community_foundation_rules():
    local_cf = fdn(ein="10", name="Manatee Community Foundation", city="BRADENTON", kind="Community foundation",
                   apply=None, website="www.example.org", top_recipients=["reading club inc"])
    far_cf = fdn(ein="11", name="Spokane Community Foundation", city="SPOKANE", state="WA", kind="Community foundation",
                 apply=None, website="", recipient_states={"WA": 8, "FL": 1})
    out = score_foundations([local_cf, far_cf], PROFILE, "FL", ["Bradenton"]).set_index("ein")
    assert any("Based in Bradenton" in r for r in out.loc["10", "reasons"])
    assert any("website" in r for r in out.loc["10", "reasons"])
    assert not any("No grants to FL" in c for c in out.loc["10", "cautions"])
    assert any("outside FL" in c for c in out.loc["11", "cautions"])
    assert out.loc["10", "score"] > out.loc["11", "score"]


SAMPLE_990 = b"""<?xml version="1.0" encoding="utf-8"?>
<Return xmlns="http://www.irs.gov/efile"><ReturnHeader><TaxYr>2024</TaxYr><Filer><EIN>650833500</EIN>
<BusinessName><BusinessNameLine1Txt>MANATEE COMMUNITY FOUNDATION INC</BusinessNameLine1Txt></BusinessName><PhoneNum>9415550100</PhoneNum>
<USAddress><CityNm>BRADENTON</CityNm><StateAbbreviationCd>FL</StateAbbreviationCd><ZIPCd>34205</ZIPCd></USAddress></Filer></ReturnHeader>
<ReturnData><IRS990><WebsiteAddressTxt>WWW.EXAMPLE.ORG</WebsiteAddressTxt><ActivityOrMissionDesc>STRENGTHEN OUR COMMUNITY</ActivityOrMissionDesc></IRS990>
<IRS990ScheduleI><RecipientTable><RecipientBusinessName><BusinessNameLine1Txt>READING CLUB INC</BusinessNameLine1Txt></RecipientBusinessName>
<USAddress><CityNm>BRADENTON</CityNm><StateAbbreviationCd>FL</StateAbbreviationCd></USAddress><CashGrantAmt>12000</CashGrantAmt>
<PurposeOfGrantTxt>PROGRAM SUPPORT</PurposeOfGrantTxt></RecipientTable></IRS990ScheduleI></ReturnData></Return>"""


def test_990_schedule_i_parsing():
    from grantmatch.community import parse_return as parse_990, summarize as summarize_990
    rec = summarize_990(parse_990(SAMPLE_990), "Community foundation")
    assert rec["name"] == "MANATEE COMMUNITY FOUNDATION INC" and rec["phone"] == "9415550100"
    assert rec["website"] == "WWW.EXAMPLE.ORG" and rec["mission"] == "STRENGTHEN OUR COMMUNITY"
    assert rec["grant_count"] == 1 and rec["top_recipients"] == ["reading club inc"]
    assert rec["kind"] == "Community foundation"


def test_tier_follows_the_shown_score():
    from grantmatch.rank_more import _tier
    # the card shows round(points); a 34.6 shows "Score 35", so it must be a possible match, not a long shot
    assert _tier(round(34.6)) == "Possible" and _tier(round(59.6)) == "Strong" and _tier(round(34.4)) == "Long shot"
