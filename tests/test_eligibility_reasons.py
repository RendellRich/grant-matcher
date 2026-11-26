"""A call that doesn't say who may apply never claims to be open to nonprofits (rank_more.py). The same cases run
through the TypeScript scorer in web/test/eligibility.test.ts, so the two stay in step."""
import json
from pathlib import Path

from grantmatch import districtofcolumbia, maryland, minnesota, newjersey, newyork, ohio, westvirginia
from grantmatch.match import Profile
from grantmatch.rank_more import ELIGIBILITY_UNSTATED, score_florida

CASES = json.loads((Path(__file__).parent / "fixtures" / "eligibility-reasons.json").read_text(encoding="utf-8"))


def record(case):
    return {"id": case["id"], "csfa": "", "title": "Arts grants", "agency": "Sample", "objectives": "", "assistance": "Grant",
            "applicant_types": case["applicant_types"], "nonprofit_eligible": True, "earmark": False, "restrictions": "",
            "application": "", "award": "", "deadlines": "", "contact": "", "web": "", "subjects": "", "url": "",
            "status": "active", "closes": None}


def test_each_case_gets_the_eligibility_reason_it_should():
    out = score_florida([record(c) for c in CASES["cases"]], Profile(mission="Arts for children.", keywords=["arts"]))
    reasons = dict(zip(out["id"], out["reasons"]))
    for case in CASES["cases"]:
        want = CASES[case["reason"]]
        other = CASES["stated" if case["reason"] == "unstated" else "unstated"]
        assert want in reasons[case["id"]] and other not in reasons[case["id"]], case["id"]


def test_every_adapters_blank_eligibility_wording_is_recognized():
    texts = [maryland.WHO, newyork.WHO, minnesota.WHO, districtofcolumbia.WHO, newjersey.WHO, westvirginia.who_can_apply("")[1],
             ohio.normalize({"Opportunity": {"OpportunityTitle": "A"}})["applicant_types"]]
    for text in texts:
        assert ELIGIBILITY_UNSTATED.search(text), text
