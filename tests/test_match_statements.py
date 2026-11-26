"""The adapters keep "the list says no match is needed" apart from silence (tests/fixtures/match-statements.json, read
here and by web/test/match.test.ts), and that never changes a score."""
import json
from pathlib import Path

import pytest

from grantmatch import california, fetch, illinois, ohio, washington
from grantmatch.match import Profile
from grantmatch.rank_more import score_florida

CASES = json.loads((Path(__file__).parent / "fixtures" / "match-statements.json").read_text(encoding="utf-8"))["cases"]

ROW = {"detail": "https://omb.illinois.gov/PUBLIC/GATA/CSFA/Opportunity.aspx?nofo=1", "title": "Reading", "agency": "A",
       "opens": "2026-11-01", "closes": "2027-01-01", "no_end": False, "award_range": ""}


def record(adapter: str, raw) -> dict:
    if adapter == "california":
        return california.normalize({"PortalID": "1", "Title": "Reading", "MatchingFunds": raw})
    if adapter == "illinois":
        return illinois.normalize(ROW, {"Matching Requirement": raw})
    if adapter == "ohio":
        opportunity = {"OpportunityNumber": "X-1", "OpportunityTitle": "Reading"}
        if raw is not None:
            opportunity["MatchingRequired"] = raw
        return ohio.normalize({"Opportunity": opportunity})
    return washington.normalize({"id": 1, "acf": {"cost_share": raw}}, {})


@pytest.mark.parametrize("case", CASES, ids=[f"{c['adapter']}-{c['raw']}" for c in CASES])
def test_each_adapter_keeps_what_the_list_said_about_a_match(case):
    got = record(case["adapter"], case["raw"])
    assert got["match"] == case["record"]["match"]
    assert ("match_none" in got) == case["record"].get("match_none", False)
    assert got.get("match_none", True) is True


def test_saying_none_never_changes_a_score():
    base = {"id": "ca-1", "title": "Reading Grant", "agency": "A", "objectives": "Literacy for children.", "subjects": "",
            "applicant_types": "Nonprofit", "application": "", "award": "", "nonprofit_eligible": True, "earmark": False,
            "match": "", "status": "active"}
    for share in (False, True):
        p = Profile(mission="Free literacy tutoring.", keywords=["literacy"], can_cost_share=share)
        silent = score_florida([base], p, {"ca-1": 0.6})
        none = score_florida([{**base, "match_none": True}], p, {"ca-1": 0.6})
        for column in ("score", "tier", "reasons", "cautions"):
            assert list(silent[column]) == list(none[column]), column


def test_a_federal_record_marks_only_a_missing_cost_sharing_answer():
    def one(block):
        return fetch.normalize({"id": 1, "oppStatus": "posted"}, {"synopsis": block})

    assert "cost_sharing_unstated" not in one({"costSharing": False}) and one({"costSharing": False})["cost_sharing"] is False
    assert "cost_sharing_unstated" not in one({"costSharing": True})
    missing = one({})
    assert missing["cost_sharing"] is False and missing["cost_sharing_unstated"] is True
