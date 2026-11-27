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
    assert "requires_501c3 must be true, false or null" in problems
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


def test_rolling_must_be_true_or_false_and_has_no_closing_date():
    assert "rolling must be true or false" in " ".join(local.check(entry(rolling="yes"), COUNTIES))
    assert "rolling programs have no closes date" in " ".join(local.check(entry(rolling=True), COUNTIES))
    r = local.to_record(entry(rolling=True, opens=None, closes=None), COUNTIES)
    assert r["rolling"] is True
    assert local.to_record(entry(), COUNTIES)["rolling"] is False


def test_programs_between_rounds_rank_below_open_ones():
    from datetime import date
    from grantmatch import rank_more
    from grantmatch.match import Profile
    day = date(2026, 11, 18)
    base = local.to_record(entry(counties=["Statewide"], opens=None, closes=None), COUNTIES, state="IA")
    assert rank_more.between_rounds(base, day)
    assert not rank_more.between_rounds({**base, "rolling": True}, day)
    assert not rank_more.between_rounds({**base, "opens": "2027-01-01", "closes": "2027-02-05"}, day)
    assert rank_more.between_rounds({**base, "opens": "2026-01-01", "closes": "2026-02-06"}, day)
    assert not rank_more.between_rounds({**base, "_cycle": {"s": "deadline", "at": "2026-11-12"}}, day)
    assert not rank_more.between_rounds({**base, "id": "il-4319"}, day)
    open_ = {**base, "id": "local-ia-open", "rolling": True}
    closed = {**base, "id": "local-ia-closed"}
    p = Profile(mission="Free literacy tutoring for children.", keywords=["literacy", "children"], today=day)
    out = rank_more.score_florida([closed, open_], p)
    assert list(out["id"]) == ["local-ia-open", "local-ia-closed"]
    assert out.iloc[0]["score"] - out.iloc[1]["score"] == 15
    assert rank_more.BETWEEN_ROUNDS in out.iloc[1]["cautions"]


TX = {"Harris": ["Houston", "Pasadena"], "Tarrant": ["Arlington", "Bedford", "Fort Worth"]}
NY = {"Kings": ["New York"], "New York": ["New York"]}


def test_a_city_program_names_only_its_places():
    e = entry(level="City", counties=["Harris"], area="Houston", places=["Houston"])
    assert local.check(e, TX, "TX") == []
    r = local.to_record(e, TX, state="TX")
    assert r["places"] == ["houston"] and r["area"] == "Houston"
    p = Profile(mission=PROFILE.mission, keywords=PROFILE.keywords)

    def where(cities):
        row = score_florida([r], p, cities=cities).iloc[0]
        return [x for x in list(row["reasons"]) + list(row["cautions"]) if "Houston" in x]

    assert where(["Houston"]) == ["Funds work in Houston, where you work"]
    assert where(["Pasadena"]) == ["Only for work in Houston"]  # same county, outside the city


def test_places_left_out_of_a_county():
    e = entry(counties=["Tarrant"], area="Tarrant County outside Fort Worth", exclude_places=["Fort Worth"])
    assert local.check(e, TX, "TX") == []
    r = local.to_record(e, TX, state="TX")
    assert r["places"] == ["arlington", "bedford", "tarrant", "tarrant county"]
    assert r["area"] == "Tarrant County outside Fort Worth"


def test_places_are_checked_against_the_counties():
    def problems(state="TX", known=TX, **kw):
        return local.check(entry(**{"counties": ["Harris"], **kw}), known, state)

    assert problems(area="Dallas", places=["Dallas"]) == ["places: 'Dallas' is not a place in its counties"]
    assert problems(area="x", exclude_places=["Harris"]) == ["exclude_places: 'Harris' is not a place in its counties"]
    assert problems(places=["Houston"]) == ["places needs an area, the words the card uses for them"]
    assert problems(area="Houston") == ["area is only used with places or exclude_places"]
    assert "use places or exclude_places, not both" in problems(area="x", places=["Houston"], exclude_places=["Pasadena"])
    assert "places must be a list of place names" in problems(area="x", places="Houston")
    assert "a statewide program has no places" in problems(counties=["Statewide"], area="x", places=["Houston"])
    assert problems("NY", NY, counties=["Kings"], area="Brooklyn", places=["Brooklyn", "Kings County"]) == []
    assert problems(area="x", places=["Brooklyn"]) == ["places: 'Brooklyn' is not a place in its counties"]


def test_a_source_note_is_carried_only_when_there_is_one():
    assert "source_note" not in local.to_record(entry(), COUNTIES)
    r = local.to_record(entry(source_note="The page gives two dates."), COUNTIES)
    assert r["source_note"] == "The page gives two dates."
    assert local.check(entry(source_note=""), COUNTIES) == ["source_note must be a sentence"]


def test_every_county_and_city_file_is_clean():
    import re
    from grantmatch import cycles
    email = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
    for st in ("AZ", "CA", "NV", "NY", "PA", "TX", "IL", "WA"):
        rows = [r for r in local.load(state=st) if r["level"] != "State"]
        assert rows, st
        for r in rows:
            assert r["id"].startswith(f"local-{st.lower()}-") and len(f"fl:{r['id']}") <= 63
            assert r["places"] and r["area"] and r["checked"] >= "2026-11-25"
            assert not [k for k, v in r.items() if isinstance(v, str) and email.search(v)], r["id"]
            for url in (r["url"], r["web"]):
                assert not cycles.blocked_by_terms(url), url


def test_the_seven_rechecked_florida_entries_are_loaded_with_what_their_guidelines_say():
    import re
    from datetime import date
    from pathlib import Path

    from grantmatch import cycles, rank_more

    assert not (Path(local.LOCAL) / "pending").exists()
    records = {r["id"]: r for r in local.load()}
    new = {i: r for i, r in records.items() if "miami-dade-" in i or i == "local-broward-csc-sponsorships"}
    assert len(new) == 7
    assert {i: r["requires_501c3"] for i, r in new.items()} == {
        "local-miami-dade-community-grants": None,        # a 501(c)(3) fiscal agent or another 501(c) type will do
        "local-miami-dade-cultural-advancement": True,
        "local-miami-dade-cultural-development": True,
        "local-miami-dade-developing-arts": None,         # not-for-profit, or through a fiscal agent
        "local-miami-dade-festivals-events": None,        # other 501(c) types case by case
        "local-miami-dade-hannibal-cox": None,            # other 501(c) types case by case
        "local-broward-csc-sponsorships": True,
    }
    assert all(r["match"].startswith("100%") for i, r in new.items() if "miami-dade-" in i)
    assert "match" not in new["local-broward-csc-sponsorships"]  # its pages don't state one
    assert [i for i, r in records.items() if r.get("by_invitation")] == ["local-miami-dade-cultural-advancement"]
    assert local.check(entry(by_invitation="yes"), COUNTIES) == ["by_invitation must be true or false"]
    assert "by_invitation" not in local.to_record(entry(by_invitation=False), COUNTIES)
    cg = new["local-miami-dade-community-grants"]
    assert (cg["opens"], cg["closes"]) == ("2027-01-22", "2027-02-18")  # not open on the day it was checked
    day = date(2026, 11, 25)
    assert not rank_more.between_rounds(cg, day) and not rank_more.between_rounds(new["local-broward-csc-sponsorships"], day)
    assert rank_more.between_rounds(new["local-miami-dade-cultural-advancement"], day)
    email = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
    for r in new.values():
        assert r["checked"] == "2026-11-25" and r["places"] and r["url"].startswith("https://")
        assert not cycles.blocked_by_terms(r["url"])
        assert not [v for v in r.values() if isinstance(v, str) and (email.search(v) or "\u2014" in v)], r["id"]


def test_no_florida_slug_reads_as_another_states_key():
    from grantmatch.display import STATE_NAMES
    for e in json.loads(local.file_for("FL").read_text(encoding="utf-8"))["programs"]:
        assert e["slug"][2] != "-" or e["slug"][:2].upper() not in STATE_NAMES, e["slug"]


def test_a_state_with_no_catalog_gets_a_local_only_file(tmp_path, monkeypatch):
    import numpy as np

    from grantmatch import embed, export_web

    monkeypatch.setattr(export_web, "LOCAL_ONLY", True)
    monkeypatch.setattr(embed, "embed_texts", lambda texts: np.ones((len(texts), 384), dtype=np.float32))
    # CA, IL, NY and WA have their own adapters
    assert export_web.local_only_states() == ["AZ", "CT", "KS", "MA", "MS", "NV", "PA", "TX"]
    meta = {}
    export_web.write_local_only(tmp_path, meta)
    assert sorted(meta["programs"]) == ["AZ", "CT", "KS", "MA", "MS", "NV", "PA", "TX"]
    assert not meta["programs"]["MA"]["local"] and meta["programs"]["MS"]["source"] == "state programs entered by hand"
    assert not meta["programs"]["CT"]["local"] and meta["programs"]["KS"]["source"] == "state programs entered by hand"
    tx = meta["programs"]["TX"]
    assert tx["local_only"] and tx["local"] and tx["file"] == "programs-TX" and tx["updated"] == "2026-11-25T12:00+00:00"
    payload = json.loads(gzip.decompress((tmp_path / "programs-TX.json.gz").read_bytes()))
    assert payload["vec_ids"] == [r["id"] for r in payload["records"]]
    assert all(r["level"] != "State" and r["_title"] for r in payload["records"])


def test_a_built_states_hand_kept_programs_join_its_tab():
    from grantmatch import export_web
    for st, n in (("IL", 3), ("WA", 4), ("CA", 6), ("NY", 3)):
        rows = export_web.hand_kept(st)
        assert export_web.has_local(rows) and sum(r["level"] != "State" for r in rows) == n, st
    assert not export_web.has_local(export_web.hand_kept("OH"))


def test_a_required_match_costs_points_when_you_cant_cost_share():
    assert local.check(entry(match="25%"), COUNTIES) == []
    assert local.check(entry(match=""), COUNTIES) == ["match must say how much, for example 25%"]
    plain = local.to_record(entry(), COUNTIES)
    assert "match" not in plain  # records without one are as they were
    r = local.to_record(entry(match="25%"), COUNTIES)

    def one(rec, share):
        p = Profile(mission=PROFILE.mission, keywords=PROFILE.keywords, can_cost_share=share)
        return score_florida([rec], p, cities=["Bradenton"]).iloc[0]

    assert "Requires matching funds (25%)" in one(r, False)["cautions"]
    assert one(plain, False)["score"] - one(r, False)["score"] == 20
    assert one(r, True)["score"] == one(plain, True)["score"]


def test_a_tax_status_answer_can_be_neither_yes_nor_no():
    e = entry(requires_501c3=None)
    assert local.check(e, COUNTIES) == []
    missing = {k: v for k, v in e.items() if k != "requires_501c3"}
    assert local.check(missing, COUNTIES) == ["requires_501c3 must be true, false or null"]
    r = local.to_record(e, COUNTIES)
    assert r["requires_501c3"] is None
    pending = Profile(mission=PROFILE.mission, keywords=PROFILE.keywords, has_501c3="No")
    assert not [c for c in score_florida([r], pending, cities=["Bradenton"]).iloc[0]["cautions"] if "501(c)(3)" in c]


def test_the_match_and_tax_status_rules_found_in_the_guidelines():
    records = {r["id"]: r for st in ("AZ", "CA", "IL", "TX", "WA") for r in local.load(state=st)}
    matches = {i: r["match"] for i, r in records.items() if "match" in r}
    assert matches == {
        "local-az-maricopa-home-chdo-py27": "25%", "local-ca-lac-arts-ogp": "100% cash",
        "local-ca-lac-arts-ciag": "100% cash", "local-il-cook-esg-2026": "100%", "local-tx-tarrant-esg-py2027": "100%",
    }
    required = sorted(i for i, r in records.items() if r.get("level") not in (None, "State") and r["requires_501c3"] is True)
    assert required == ["local-az-maricopa-cdbg-py27", "local-az-maricopa-esg-cdbg-ps-py27", "local-il-cook-cdbg-2026",
                        "local-il-cook-esg-2026", "local-tx-san-antonio-arts-operational-fy27"]
    sb = records["local-ca-sbc-cdbg-py2027"]
    assert len(sb["places"]) == 14 and "surrounding communities" in sb["source_note"]


def test_words_about_a_match_agree_with_the_match_field():
    # The card reads a program's words too (web/src/ready.ts), so they must not suggest a match that isn't required.
    import re
    for st in ("AZ", "CA", "IL", "NV", "NY", "PA", "TX", "WA"):
        for r in local.load(state=st):
            if r["level"] == "State" or "match" in r:
                continue
            words = " ".join((r["applicant_types"], r["application"], r["award"], r["deadlines"]))
            if re.search(r"matching|\bmatch\b", words, re.I):
                assert re.search(r"no match required", words, re.I), r["id"]


def test_connecticut_and_kansas_hand_entries_are_loaded_and_watched():
    from grantmatch import freshness

    ct, ks = local.load(state="CT"), local.load(state="KS")
    assert [(r["id"], r["closes"]) for r in ct + ks] == [
        ("local-ct-arts-endowment-fund", "2026-12-15"),
        ("local-ct-opm-nonprofit-grant-program", "2027-01-05"),
        ("local-ks-early-childhood-block-grant", "2027-01-08")]
    assert all(r["level"] == "State" and len(f"fl:{r['id']}") <= 63 for r in ct + ks)
    watched = {(row["list"], row["key"]) for row in freshness.hand_pages(local.LOCAL)}
    assert {("local-CT", "arts-endowment-fund"), ("local-CT", "opm-nonprofit-grant-program"),
            ("local-KS", "early-childhood-block-grant")} <= watched
    assert {r["id"] for r in ct + ks} <= set(local.site_targets())


def test_massachusetts_and_mississippi_hand_entries_are_loaded_and_watched():
    from grantmatch import cycles, freshness

    ma, ms = local.load(state="MA"), local.load(state="MS")
    assert [(r["id"], r["closes"], r["rolling"]) for r in ma + ms] == [
        ("local-ma-pathmaker-training-provider", "2027-04-16", False),
        ("local-ma-cyber-resilient-massachusetts", None, True),
        ("local-ma-technology-innovation-ecosystem-awards", None, True),
        ("local-ms-sexual-risk-avoidance-education", "2026-12-10", False),
        ("local-ms-americorps-state-formula", "2027-01-15", False),
        ("local-ms-creative-aging-grant", "2027-03-01", False)]
    assert all(r["level"] == "State" and len(f"fl:{r['id']}") <= 63 for r in ma + ms)
    watched = {row["key"] for row in freshness.hand_pages(local.LOCAL) if row["list"] in ("local-MA", "local-MS")}
    assert watched == {r["id"].split("-", 2)[2] for r in ma + ms}
    assert {r["id"] for r in ma + ms} <= set(local.site_targets())
    # no entry reads a host whose terms keep this use out; doe.mass.edu isn't swept up by the www.mass.edu entry
    assert not any(cycles.blocked_by_terms(u) for r in ma + ms for u in (r["url"], r["web"]))
    for url in ("https://massculturalcouncil.org/", "https://www.masscec.com/", "https://www.mass.edu/"):
        assert cycles.blocked_by_terms(url), url
    assert not cycles.blocked_by_terms("https://www.doe.mass.edu/")


def test_the_website_check_waits_a_hosts_crawl_delay_before_its_second_page(monkeypatch):
    from datetime import date
    from urllib import robotparser

    from grantmatch import cycles

    rules = robotparser.RobotFileParser()
    rules.parse(["User-agent: *", "Crawl-delay: 10"])
    seen = []
    monkeypatch.setattr(cycles, "_robots", {"https://example.org": (rules, [])})
    monkeypatch.setattr(cycles, "get", lambda url: seen.append(url) or (url, "<p>x</p>"))
    monkeypatch.setattr(cycles, "grants_page", lambda raw, base: "https://example.org/grants/")
    monkeypatch.setattr(cycles.time, "sleep", seen.append)
    cycles.check("https://example.org/a", date(2026, 11, 27))
    assert seen == ["https://example.org/a", 10.0, "https://example.org/grants/"]
