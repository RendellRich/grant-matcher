"""The adapters keep "the list says no match is needed" apart from silence, and grantmatch/match_words.py reads a
program's own words as the card does (tests/fixtures/match-statements.json, read here and by web/test/match.test.ts).
None of it changes a score."""
import gzip
import json
import re
from pathlib import Path

import pytest

from grantmatch import california, fetch, illinois, local, match_words, ohio, washington
from grantmatch.match import Profile
from grantmatch.rank_more import score_florida

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "match-statements.json").read_text(encoding="utf-8"))
CASES, WORDS = FIXTURE["cases"], FIXTURE["words"]
ROOT = Path(__file__).parent.parent

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
    assert match_words.statement({**got, "status": "active"}) == case["label"]


@pytest.mark.parametrize("case", WORDS, ids=[c["name"] for c in WORDS])
def test_a_programs_words_read_the_same_as_on_the_card(case):
    purpose = case.get("purpose", "")
    assert match_words.words(case["text"], purpose)["says"] == case["says"]
    program = {"restrictions": case["text"], "objectives": purpose}
    assert match_words.statement(program) == case["program"]
    assert match_words.statement({**program, "status": "active", "match": ""}) == case["call"]
    if case["says"] not in ("none", "silent"):  # an open list saying "none" never wins over words that ask for one
        listed = match_words.statement({**program, "status": "active", "match": "", "match_none": True})
        asks = match_words.words(case["text"], purpose)
        assert listed == "Match not stated" or not (asks["plain"] or asks["asks"])


def test_the_florida_records_that_state_a_match_are_never_read_as_silent_or_none():
    path = ROOT / "data" / "florida.json.gz"
    recs = {r["id"]: r for r in json.loads(gzip.decompress(path.read_bytes()))["programs"]}
    for rid in ("fl-87527", "fl-87345", "fl-88595", "fl-88611", "fl-88748", "fl-88798", "fl-90605"):
        if rid not in recs:  # the weekly catalog moved on; the cut sentences in the fixture still stand
            continue
        r = recs[rid]
        text = " \n ".join(r.get(k) or "" for k in match_words.TEXT_FIELDS)
        assert match_words.words(text, r["objectives"])["says"] == "unclear", rid
        assert match_words.statement(r) == "Match not stated", rid


def test_the_two_readings_use_the_same_patterns():
    """Each pattern in match_words.py is in web/src/ready.ts, written the same way."""
    ts = (ROOT / "web" / "src" / "ready.ts").read_text(encoding="utf-8")
    for name in ("NONE_NEEDED", "ASKS", "PLAIN_MATCH", "CASH_ONLY", "MATCH"):
        found = re.search(rf"^const {name} = /(.*)/g?i;$", ts, re.M)
        assert found and found.group(1) == getattr(match_words, name).pattern, name
    limits = "(?:unless|except|for|if|when|during|from|to apply|at the time)"
    assert limits in match_words.LIMITED.pattern and limits in re.search(r"^const LIMITED = .*$", ts, re.M).group(0)


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
