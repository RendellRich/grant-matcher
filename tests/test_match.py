from datetime import date

from grantmatch.fetch import _date, clean_text, normalize
from grantmatch.match import Profile, load_frame, score, to_ics

TODAY = date(2026, 11, 13)


def opp(**kw):
    base = {
        "id": "1", "number": "ED-26-001", "title": "Literacy grants", "agency_code": "ED", "agency": "Department of Education",
        "status": "posted", "open_date": "2026-10-01", "close_date": "2027-01-15", "award_ceiling": 250000.0,
        "award_floor": 50000.0, "estimated_funding": 2_000_000.0, "number_of_awards": 10.0, "cost_sharing": False,
        "applicant_types": ["12"], "categories": ["ED"], "category_labels": ["Education"], "instruments": ["G"],
        "aln": [], "description": "Supports reading and literacy programs for children with dyslexia.",
        "eligibility_text": "", "url": "https://www.grants.gov/search-results-detail/1",
    }
    base.update(kw)
    return base


PROFILE = Profile(
    mission="Free structured literacy instruction for children with dyslexia.",
    keywords=["literacy", "dyslexia", "children", "tutoring"],
    today=TODAY,
)


def ranked(*records, profile=PROFILE):
    return score(load_frame(list(records)), profile)


def test_relevant_grant_ranks_first():
    out = ranked(
        opp(id="1"),
        opp(id="2", title="Rural broadband expansion", description="Fiber internet for rural counties.", categories=["CD"]),
    )
    assert list(out["id"]) == ["1", "2"]
    assert out.loc[0, "tier"] == "Strong"
    assert "literacy" in out.loc[0, "matched"]


def test_cost_share_is_flagged_and_penalized():
    out = ranked(opp(id="1"), opp(id="2", cost_sharing=True))
    a, b = out.set_index("id").loc["1"], out.set_index("id").loc["2"]
    assert b["score"] < a["score"]
    assert any("cost sharing" in c for c in b["cautions"])


def test_requires_501c3_when_org_has_none():
    p = Profile(**{**PROFILE.__dict__, "has_501c3": "No"})
    out = ranked(opp(applicant_types=["12"]), profile=p)
    assert any("Requires 501(c)(3)" in c for c in out.loc[0, "cautions"])


def test_large_floor_flagged_for_small_budget():
    p = Profile(**{**PROFILE.__dict__, "budget_band": "Under $50k"})
    out = ranked(opp(award_floor=1_000_000.0, award_ceiling=3_000_000.0), profile=p)
    assert any("large for your budget" in c for c in out.loc[0, "cautions"])


def test_nih_research_flag():
    out = ranked(opp(number="RFA-HD-27-001", agency_code="HHS-NIH11"))
    assert any("Research grant" in c for c in out.loc[0, "cautions"])


def test_deadline_window_and_forecasts():
    soon = opp(id="2", close_date="2026-11-20")
    fc = opp(id="3", status="forecasted", close_date="2027-03-01")
    out = ranked(opp(id="1"), soon, fc)
    assert "2" not in set(out["id"])  # closes inside the 14-day window
    row = out.set_index("id").loc["3"]
    assert any("Forecast" in r for r in row["reasons"])
    p = Profile(**{**PROFILE.__dict__, "include_forecasted": False})
    assert "3" not in set(ranked(opp(id="1"), fc, profile=p)["id"])


def test_category_filter():
    p = Profile(**{**PROFILE.__dict__, "categories": ["HL"]})
    out = ranked(opp(id="1", categories=["ED"]), opp(id="2", categories=["HL"]), profile=p)
    assert list(out["id"]) == ["2"]


def test_ics_has_one_event_per_deadline():
    out = ranked(opp(id="1"), opp(id="2", close_date=None))
    ics = to_ics(out)
    assert ics.count("BEGIN:VEVENT") == 1
    assert "DTSTART;VALUE=DATE:20270115" in ics


def test_helpers():
    assert _date("Dec 16, 2026 12:00:00 AM EST") == "2026-12-16"
    assert _date("01/11/2027") == "2027-01-11"
    assert _date(None) is None
    assert clean_text("<p>Kids &amp; families</p>") == "Kids & families"


def test_normalize_forecast_uses_estimated_due_date():
    hit = {"id": 9, "number": "X-1", "title": "T", "agencyCode": "ED", "agency": "Education", "oppStatus": "forecasted",
           "openDate": "02/11/2026", "closeDate": ""}
    detail = {"forecast": {"estApplicationResponseDate": "Dec 15, 2026 12:00:00 AM EST", "forecastDesc": "<p>Hi</p>",
                           "awardCeiling": "600000", "applicantTypes": [{"id": "12"}],
                           "fundingActivityCategories": [{"id": "ED", "description": "Education"}]}}
    rec = normalize(hit, detail)
    assert rec["close_date"] == "2026-12-15"
    assert rec["award_ceiling"] == 600000.0
    assert rec["description"] == "Hi"


def test_semantic_scores_drive_ranking_when_given():
    a = opp(id="1", title="Program A", description="General support.")
    b = opp(id="2", title="Program B", description="General support.")
    out = score(load_frame([a, b]), PROFILE, semantic={"1": 0.60, "2": 0.80, "x": 0.55, "y": 0.58, "z": 0.62})
    assert list(out["id"]) == ["2", "1"]
    assert out.loc[0, "score"] >= 70


def test_targeted_programs_are_flagged():
    out = ranked(opp(id="1", title="Tribal Youth Literacy Program"), opp(id="2", title="U.S. Embassy Lima Public Diplomacy Literacy Grants"))
    notes = {r["id"]: " ".join(r["cautions"]) for _, r in out.iterrows()}
    assert "tribal" in notes["1"]
    assert "embassy" in notes["2"]


def test_placeholder_far_future_date_is_treated_as_missing():
    out = ranked(opp(close_date="2099-01-01"))
    assert any("No close date" in c for c in out.loc[0, "cautions"])
