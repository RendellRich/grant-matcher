"""County and city programs entered by hand (data/local-FL.json, grantmatch/local.py)."""
import gzip
import json

import pytest

from grantmatch import changes, local
from grantmatch.match import Profile
from grantmatch.rank_more import score_florida

COUNTIES = {"Manatee": ["Bradenton", "Palmetto"], "Pinellas": ["Clearwater", "St. Petersburg"]}
PROFILE = Profile(mission="Free literacy tutoring for children with dyslexia.", keywords=["literacy", "children"])


def entry(**kw):
    base = {"slug": "sample-county-kids", "title": "Synthetic Children's Fund", "agency": "Sample County",
            "level": "County", "counties": ["Manatee"], "objectives": "Programs for children and families.",
            "who": "Nonprofits with 501(c)(3) status.", "requires_501c3": True, "application": "Apply online.",
            "award": "Not stated.", "opens": "2026-12-07", "closes": "2027-01-29", "url": "https://example.org/kids",
            "checked": "2026-11-18"}
    base.update(kw)
    return base


def test_the_real_file_loads_and_every_key_suits_eto():
    records = local.load()
    assert records, "data/local-FL.json should have programs"
    for r in records:
        assert r["id"].startswith("local-") and len(f"fl:{r['id']}") <= 63
        assert r["nonprofit_eligible"] and not r["earmark"]
        assert r["places"] or r["area"] == "all of Florida"  # statewide entries name no places


def test_bad_entries_are_named():
    problems = local.check(entry(slug="Bad Slug", counties=["Atlantis"], opens="Dec 7", requires_501c3="yes",
                                 url="http://example.org", title=""), COUNTIES)
    assert "missing title" in problems
    assert any("slug" in p for p in problems)
    assert "unknown county 'Atlantis'" in problems
    assert any(p.startswith("opens") for p in problems)
    assert "requires_501c3 must be true or false" in problems
    assert "url must start with https://" in problems
    assert local.check(entry(opens="2027-02-01"), COUNTIES) == ["opens is after closes"]


def test_a_file_with_a_bad_entry_stops_the_run(tmp_path):
    path = tmp_path / "local.json"
    path.write_text(json.dumps({"programs": [entry(), entry()]}), encoding="utf-8")
    with pytest.raises(ValueError, match="slug used twice"):
        local.load(path, COUNTIES)


def test_record_shape_places_and_deadline_text():
    r = local.to_record(entry(), COUNTIES, "2026-2027")
    assert r["id"] == "local-sample-county-kids"
    assert r["area"] == "Manatee County"
    assert {"manatee", "manatee county", "bradenton", "palmetto"} <= set(r["places"])
    assert r["deadlines"] == "Applications open December 7, 2026 and close January 29, 2027."
    two = local.to_record(entry(counties=["Manatee", "Pinellas"]), COUNTIES)
    assert two["area"] == "Manatee and Pinellas counties"
    assert local.to_record(entry(opens=None, closes=None), COUNTIES)["deadlines"].startswith("No set window")


def test_scoring_by_county_and_501c3_status():
    rec = local.to_record(entry(), COUNTIES)

    def one(p, cities):
        return score_florida([rec], p, cities=cities).iloc[0]

    there = one(PROFILE, ["Bradenton"])
    assert "Funds work in Manatee County, where you work" in there["reasons"]
    elsewhere = one(PROFILE, ["Clearwater"])
    assert elsewhere["cautions"] == ["Only for work in Manatee County"]
    assert there["score"] - elsewhere["score"] == 40
    assert one(PROFILE, [])["cautions"] == ["Only for work in Manatee County; add your cities to check"]
    assert one(PROFILE, ["manatee county"])["cautions"] == []

    pending = Profile(mission=PROFILE.mission, keywords=PROFILE.keywords, has_501c3="Pending")
    got = one(pending, ["Bradenton"])
    assert got["cautions"] == ["Requires 501(c)(3) status; apply once your IRS letter arrives"]
    assert there["score"] - got["score"] == 10
    sponsor = Profile(mission=PROFILE.mission, keywords=PROFILE.keywords, has_501c3="No", fiscal_sponsor=True)
    assert one(sponsor, ["Bradenton"])["cautions"] == [
        "Requires 501(c)(3) status; ask whether you can apply through your fiscal sponsor"]


def test_state_programs_are_unchanged_by_cities():
    state = {"id": "fl-1", "csfa": "48.001", "title": "Reading Grants", "agency": "Department of Education",
             "objectives": "Literacy tutoring.", "assistance": "Grants", "applicant_types": "Nonprofit",
             "nonprofit_eligible": True, "earmark": False, "restrictions": "", "application": "", "award": "",
             "deadlines": "", "contact": "", "web": "", "subjects": "Education", "fiscal_year": "", "url": "https://example.org"}
    a = score_florida([state], PROFILE).iloc[0]
    b = score_florida([state], PROFILE, cities=["Clearwater"]).iloc[0]
    assert (a["score"], a["reasons"], a["cautions"]) == (b["score"], b["reasons"], b["cautions"])


def test_changes_carry_the_closing_date_and_website_status(tmp_path):
    rec = local.to_record(entry(), COUNTIES)
    rec["_cycle"] = {"s": "closed", "at": "2026-11-18"}
    state = {"id": "fl-1", "title": "State"}
    (tmp_path / "florida.json.gz").write_bytes(gzip.compress(json.dumps({"records": [state, rec]}).encode()))
    now = changes.current(tmp_path)
    assert now["fl"] == {"fl:local-sample-county-kids": {"d": "2027-01-29", "s": "closed"}}
    assert changes.events_for("fl:local-x", {"d": "2027-01-29", "s": "closed"}, {"d": "2027-01-29", "s": "open"},
                              "2026-12-07") == [{"k": "fl:local-x", "kind": "reopened", "from": "closed", "to": "open",
                                                 "at": "2026-12-07"}]


def test_site_targets_skip_pdfs_for_the_page_beside_them(tmp_path):
    path = tmp_path / "local.json"
    path.write_text(json.dumps({"programs": [
        entry(), entry(slug="pdf-only-program", url="https://example.org/packet.pdf", web="https://example.org/funding")]}),
        encoding="utf-8")
    assert local.site_targets(path) == {"local-sample-county-kids": "https://example.org/kids",
                                        "local-pdf-only-program": "https://example.org/funding"}


def test_county_programs_never_move_a_state_programs_score():
    state = [{"id": f"fl-{i}", "csfa": "", "title": t, "agency": "Agency", "objectives": o, "assistance": "Grants",
              "applicant_types": "Nonprofit", "nonprofit_eligible": True, "earmark": False, "restrictions": "",
              "application": "", "award": "", "deadlines": "", "contact": "", "web": "", "subjects": "", "fiscal_year": "",
              "url": "https://example.org"}
             for i, (t, o) in enumerate([("Reading Grants", "Literacy tutoring for children."),
                                         ("Water Projects", "Stormwater upgrades."), ("Arts", "Murals.")])]
    rec = local.to_record(entry(objectives="Literacy for children, children, children."), COUNTIES)
    sims = {"fl-0": 0.6, "fl-1": 0.2, "fl-2": 0.3, rec["id"]: 0.9}
    alone = score_florida(state, PROFILE, sims, cities=["Bradenton"]).set_index("id")["score"]
    mixed = score_florida(state + [rec], PROFILE, sims, cities=["Bradenton"]).set_index("id")["score"]
    assert mixed.drop(rec["id"]).sort_index().tolist() == alone.sort_index().tolist()


def test_statewide_and_community_foundation_entries():
    state = local.to_record(entry(level="State", counties=["Statewide"]), COUNTIES)
    assert state["area"] == "all of Florida" and state["places"] == [] and state["level"] == "State"
    assert local.check(entry(level="State", counties=["Statewide"]), COUNTIES) == []
    assert "not both" in " ".join(local.check(entry(counties=["Statewide", "Manatee"]), COUNTIES))
    cf = local.to_record(entry(level="Community foundation", counties=["Manatee"]), COUNTIES)
    assert cf["level"] == "Community foundation" and "manatee" in cf["places"]


def test_every_state_file_loads_with_its_own_keys():
    assert {"FL", "WA", "OH", "IA", "IL"} <= set(local.states())
    for st in ("OH", "IA", "IL"):
        rows = local.load(state=st)
        assert rows and all(r["id"].startswith(f"local-{st.lower()}-") and len(f"fl:{r['id']}") <= 63 for r in rows)
    wa = local.load(state="WA")
    assert wa and all(r["id"].startswith("local-wa-") and len(f"fl:{r['id']}") <= 63 for r in wa)
    assert all(r["places"] or r["area"] == "all of Washington" for r in wa)
    fl_ids = {r["id"] for r in local.load()}
    assert not fl_ids & {r["id"] for r in wa}


def test_florida_keeps_its_keys_and_other_states_add_theirs():
    assert local.record_id("kids", "FL") == "local-kids"
    assert local.record_id("kids", "wa") == "local-wa-kids"
    r = local.to_record(entry(counties=["Statewide"]), COUNTIES, state="WA")
    assert r["id"] == "local-wa-sample-county-kids" and r["area"] == "all of Washington" and r["places"] == []
