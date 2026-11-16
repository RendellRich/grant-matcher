"""The expanded profile: checkbox groups as key words, a fiscal sponsor, online nationwide, a new organization,
and the county list."""
import gzip
import json
from pathlib import Path

from grantmatch.counties import build, county_name, place_name
from grantmatch.match import Profile
from grantmatch.rank_more import score_foundations
from grantmatch.terms import expand_keywords, terms
from tests.test_match import PROFILE as FED_PROFILE, opp, ranked
from tests.test_rank_more import PROFILE as FDN_PROFILE, fdn


def test_checkbox_groups_add_their_words_after_typed_ones_without_repeats():
    out = expand_keywords(["Orton-Gillingham", "Reading"], ["literacy", "dyslexia"], ["k5"], ["low_income"])
    assert out[:2] == ["Orton-Gillingham", "Reading"]
    assert "phonics" in out and "dyslexia" in out and "elementary" in out and "low-income" in out
    assert [w.lower() for w in out].count("reading") == 1 and [w.lower() for w in out].count("orton-gillingham") == 1
    assert expand_keywords(["a"], ["no-such-area"]) == ["a"]


def test_every_choice_has_words_and_unique_ids():
    t = terms()
    for group in ("focus_areas", "ages", "populations"):
        ids = [x["id"] for x in t[group]]
        assert len(ids) == len(set(ids))
        assert all(x["words"] and x["label"] for x in t[group])


def test_fiscal_sponsor_softens_a_federal_501c3_requirement():
    no = Profile(**{**FED_PROFILE.__dict__, "has_501c3": "Pending"})
    yes = Profile(**{**no.__dict__, "fiscal_sponsor": True})
    a, b = ranked(opp(applicant_types=["12"]), profile=no), ranked(opp(applicant_types=["12"]), profile=yes)
    assert b.loc[0, "score"] - a.loc[0, "score"] == 30
    assert "Requires 501(c)(3) status; apply through your fiscal sponsor" in b.loc[0, "cautions"]


def test_young_organization_and_a_large_federal_award():
    young = Profile(**{**FED_PROFILE.__dict__, "year_founded": 2026})
    out = ranked(opp(award_floor=50_000.0, award_ceiling=250_000.0), profile=young)
    assert any("new organization" in c for c in out.loc[0, "cautions"])
    small = ranked(opp(award_floor=5_000.0, award_ceiling=20_000.0), profile=young)
    assert not any("new organization" in c for c in small.loc[0, "cautions"])
    older = Profile(**{**young.__dict__, "year_founded": 2015})
    assert not any("new organization" in c for c in ranked(opp(), profile=older).loc[0, "cautions"])


def test_fiscal_sponsor_answers_a_foundation_asking_for_501c3_proof():
    asks = fdn(apply={"contact": "Jane", "materials": "Include your IRS determination letter", "restrictions": ""})
    pending = Profile(**{**FDN_PROFILE.__dict__, "has_501c3": "Pending"})
    sponsored = Profile(**{**pending.__dict__, "fiscal_sponsor": True})
    a = score_foundations([asks], pending, "FL", []).iloc[0]
    b = score_foundations([asks], sponsored, "FL", []).iloc[0]
    assert b["score"] - a["score"] == 10
    assert "Asks for proof of 501(c)(3) status; apply through your fiscal sponsor" in b["cautions"]


def test_online_nationwide_counts_funders_that_give_in_many_states():
    national = fdn(ein="9", state="NY", recipient_states={"NY": 4, "CA": 2, "TX": 2, "IL": 1, "WA": 1})
    regional = fdn(ein="8", state="NY", recipient_states={"NY": 9, "NJ": 1})
    online = Profile(**{**FDN_PROFILE.__dict__, "delivery": "online_national"})
    base = score_foundations([national, regional], FDN_PROFILE, "FL", []).set_index("ein")
    now = score_foundations([national, regional], online, "FL", []).set_index("ein")
    assert now.loc["9", "score"] - base.loc["9", "score"] == 15
    assert "No grants to FL in its latest return, but it gives in 5 states" in now.loc["9", "cautions"]
    assert now.loc["8", "score"] == base.loc["8", "score"]  # four states or fewer: still a regional funder


def test_county_file_names_and_build():
    assert place_name("Bradenton city") == "Bradenton" and place_name("Ellenton CDP") == "Ellenton"
    assert county_name("Manatee County") == "Manatee" and county_name("Orleans Parish") == "Orleans"
    text = "STATE|STATEFP|COUNTYFP|COUNTYNAME|PLACEFP|PLACENS|PLACENAME|TYPE|CLASSFP|FUNCSTAT\n" \
           "FL|12|081|Manatee County|07950|1|Bradenton city|INCORPORATED PLACE|C1|A\n" \
           "FL|12|081|Manatee County|20150|1|Ellenton CDP|CENSUS DESIGNATED PLACE|U1|S\n"
    assert build(text) == {"FL": {"Manatee": ["Bradenton", "Ellenton"]}}


def test_committed_county_file_covers_manatee():
    path = Path(__file__).resolve().parent.parent / "data" / "counties.json.gz"
    data = json.loads(gzip.decompress(path.read_bytes()))
    assert {"Bradenton", "Palmetto", "Ellenton", "Lakewood Ranch"} <= set(data["FL"]["Manatee"])
    assert len(data["FL"]) == 67
