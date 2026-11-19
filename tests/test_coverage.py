"""The coverage report: registered foundations against what the state files hold (grantmatch/coverage.py)."""
import gzip
import json

from grantmatch import coverage, foundations


def bmf(ein, state, pf="1", ntee=""):
    return {"EIN": ein, "STATE": state, "PF_FILING_REQ_CD": pf, "NTEE_CD": ntee}


def idx(ein, kind="990PF"):
    return {"EIN": ein, "RETURN_TYPE": kind}


def state_file(folder, state, recs):
    folder.mkdir(parents=True, exist_ok=True)
    with gzip.open(folder / f"{state}.json.gz", "wt", encoding="utf-8") as fh:
        json.dump({"state": state, "foundations": recs}, fh)


def test_master_picks_private_and_community_and_skips_the_rest():
    orgs = coverage.master([
        bmf("1", "FL"), bmf("2", "FL", pf="0", ntee="T31"), bmf("3", "FL", pf="0", ntee="B20"),
        bmf("4", "", pf="1"), bmf("5", "GA", pf="1", ntee="T31"),
    ])
    assert orgs == {"1": ("FL", "private"), "2": ("FL", "community"), "5": ("GA", "private")}


def test_registered_counts_each_foundation_once_and_only_its_own_return_type():
    orgs = coverage.master([bmf("1", "FL"), bmf("2", "FL"), bmf("3", "FL", pf="0", ntee="T70")])
    reg = coverage.registered(orgs, [idx("1"), idx("1"), idx("3"), idx("3", "990"), idx("9")])
    assert reg == {"FL": {"private": 2, "community": 1, "private_efiled": 1, "community_efiled": 1}}


def test_listed_counts_home_state_separately_from_funders_giving_there(tmp_path):
    state_file(tmp_path, "FL", [
        {"ein": "1", "state": "FL", "tax_year": "2024", "website": "N/A", "apply": {"how": "letter"}},
        {"ein": "2", "state": "FL", "tax_year": "2025", "website": "example.org"},
        {"ein": "3", "state": "NY", "tax_year": "2025", "website": "example.com"},
    ])
    assert coverage.listed(tmp_path)["FL"] == {
        "home": 2, "giving_here": 3, "newest_tax_year": "2025", "with_website": 1, "with_how_to_apply": 1}


def test_tally_counts_current_filers_by_outcome():
    seen = {
        "1": {"state": "FL", "filed": 2026, "tax_year": "2025", "why": ""},
        "2": {"state": "FL", "filed": 2026, "tax_year": "2025", "why": "preselected"},
        "3": {"state": "FL", "filed": 2025, "tax_year": "2024", "why": "no_grants"},
        "4": {"state": "FL", "filed": 2026, "tax_year": "2025", "why": "no_grants"},  # an older return is listed
        "5": {"state": "FL", "filed": 2024, "tax_year": "2023", "why": ""},           # hasn't filed lately
        "6": {"state": "", "filed": 2026, "tax_year": "2025", "why": ""},
    }
    assert coverage.tally(seen, {"1", "4"}, 2026, 2) == {
        "states": {"FL": {"read": 4, "listed": 2, "preselected": 1, "no_grants": 1}}}


def test_note_keeps_the_latest_return_and_left_out_gives_the_reason():
    seen = {}
    rec = {"ein": "1", "state": "FL", "tax_year": "2024", "grants": [], "preselected_only": False}
    assert foundations.left_out(rec) == "no_grants"
    assert foundations.left_out({**rec, "grants": [{}], "preselected_only": True}) == "preselected"
    assert foundations.left_out({**rec, "grants": [{}], "preselected_only": True, "apply": {"how": "x"}}) == ""
    foundations.note(seen, rec, 2026, "no_grants")
    foundations.note(seen, {**rec, "tax_year": "2023"}, 2025, "")
    assert seen["1"]["why"] == "no_grants" and seen["1"]["filed"] == 2026


def test_report_joins_the_sources_and_totals_them(tmp_path):
    state_file(tmp_path / "foundations", "FL", [{"ein": "1", "state": "FL", "tax_year": "2025"}])
    state_file(tmp_path / "community", "FL", [{"ein": "3", "state": "FL", "tax_year": "2024"}])
    (tmp_path / "foundations" / "parsed.json").write_text(json.dumps({"states": {"FL": {"read": 2, "listed": 1, "preselected": 1}}}))
    reg = {"FL": {"private": 4, "private_efiled": 2, "community": 3, "community_efiled": 1}, "GA": {"private": 1}}
    rep = coverage.report(reg, coverage.listed(tmp_path / "foundations"), coverage.listed(tmp_path / "community"),
                          coverage.parsed(tmp_path / "foundations"), coverage.parsed(tmp_path / "community"), 2026)
    fl, ga = rep["states"]
    assert fl["private"]["listed_share"] == 0.5 and fl["private"]["read"]["preselected"] == 1
    assert fl["community"] == {"registered": 3, "efiled": 1, "listed": 1, "giving_here": 1, "newest_tax_year": "2024"}
    assert ga["private"]["listed"] == 0 and ga["private"]["listed_share"] is None
    assert rep["national"]["private"]["registered"] == 5 and rep["national"]["states_with_data"] == 1
    assert rep["filing_years"] == [2025, 2026] and rep["has_read_counts"] is True


def test_the_report_and_the_refresh_agree_on_what_counts_as_current():
    assert coverage.FILING_YEARS == foundations.CURRENT_FILING_YEARS
