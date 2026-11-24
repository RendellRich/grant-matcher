import gzip
import json

from grantmatch import skipped
from grantmatch.california import build_records
from grantmatch.fetch import NONPROFIT_WORDS, NOT_NONPROFIT
from grantmatch.foundations import write_left_out

FED = {"source": "federal", "id": "1", "name": "State Only Grant", "funder": "HHS", "state": "",
       "reason": "not_nonprofit_eligible", "detail": "Who can apply: State governments.", "url": "https://x"}
FDN = {"source": "foundation", "id": "123456789", "name": "Big Family Fund", "state": "FL", "city": "TAMPA",
       "reason": "preselected", "assets": 25_000_000, "tax_year": "2024", "url": "https://p"}


def test_rows_get_plain_reasons_and_first_seen_dates():
    out, text = skipped.build([FED, FDN], previous={("federal", "1"): "2026-11-01"}, decisions={},
                              today="2026-11-22", missing=[])
    by_id = {r["ID"]: r for r in out}
    assert by_id["1"]["Reason"] == "Nonprofits can't apply"
    assert by_id["1"]["First seen"] == "2026-11-01"           # carried from last week
    assert by_id["123456789"]["First seen"] == "2026-11-22"   # new this week
    assert by_id["123456789"]["Assets"] == "25000000"
    assert "New since the last report (1)" in text and "Big Family Fund" in text


def test_review_decisions_show_in_every_report():
    decisions = {("federal", "1"): {"decision": "keep skipping", "note": "states only"}}
    out, text = skipped.build([FED], previous={}, decisions=decisions, today="2026-11-22", missing=[])
    assert out[0]["Review decision"] == "keep skipping" and out[0]["Review note"] == "states only"
    assert "1 have a review decision" in text
    assert "New since" not in text  # the first report has nothing to compare with


def test_hidden_state_programs(tmp_path):
    path = tmp_path / "florida.json.gz"
    path.write_bytes(gzip.compress(json.dumps({"state": "FL", "programs": [
        {"id": "a", "title": "Open one", "nonprofit_eligible": True, "earmark": False},
        {"id": "b", "title": "Cities only", "nonprofit_eligible": False, "earmark": False, "applicant_types": "Local Government"},
        {"id": "c", "title": "Line item", "nonprofit_eligible": True, "earmark": True},
    ]}).encode()))
    rows = skipped.hidden_programs(path, "florida")
    assert {r["id"]: r["reason"] for r in rows} == {"b": "state_not_nonprofit", "c": "earmark"}


def test_federal_notes_that_let_nonprofits_in_are_flagged():
    def flag(note):
        return bool(NONPROFIT_WORDS.search(note)) and not NOT_NONPROFIT.search(note)
    assert flag("Individuals and NGOs can apply")
    assert flag("Eligible applicants include nonprofit organizations partnering with a state")
    assert not flag('ONLY STATE GOVERNMENTS MAY APPLY. "NO PRIVATE ORGANIZATION, RELIGIOUS, NON-PROFIT, OR INDIVIDUAL"')
    assert not flag("Open to state agencies only.")


def test_california_open_rows_with_a_passed_deadline_are_listed():
    rows = [
        {"Status": "active", "PortalID": "1", "Title": "Still open", "ApplicationDeadline": "2027-01-01", "AgencyDept": "A"},
        {"Status": "active", "PortalID": "2", "Title": "Stale", "ApplicationDeadline": "2026-01-01", "AgencyDept": "B"},
        {"Status": "closed", "PortalID": "3", "Title": "Closed", "ApplicationDeadline": "2026-01-01", "AgencyDept": "C"},
    ]
    skips = []
    kept = build_records(rows, today="2026-11-22", skips=skips)
    assert [r["title"] for r in kept] == ["Still open"]
    assert [(s["name"], s["reason"]) for s in skips] == [("Stale", "deadline_passed")]


def test_foundations_read_but_not_listed_are_written_with_why(tmp_path):
    seen = {
        "1": {"state": "FL", "filed": 2026, "tax_year": "2025", "why": "", "name": "Listed"},
        "2": {"state": "FL", "filed": 2026, "tax_year": "2025", "why": "no_grants", "name": "Gives nothing"},
        "3": {"state": "GA", "filed": 2023, "tax_year": "2022", "why": "", "name": "Went quiet", "assets": 5e6},
    }
    path = tmp_path / "skipped.jsonl.gz"
    assert write_left_out(path, seen, {"1"}, newest=2026, source="foundation") == 2
    rows = [json.loads(line) for line in gzip.decompress(path.read_bytes()).decode().splitlines()]
    assert {r["id"]: r["reason"] for r in rows} == {"2": "no_grants", "3": "no_recent_return"}
    assert path.name.endswith(".jsonl.gz") and not path.name.endswith(".json.gz")  # stays out of the state files


def test_a_second_report_the_same_day_counts_only_what_is_really_new(tmp_path, monkeypatch):
    parts = tmp_path / "parts"
    parts.mkdir()
    with gzip.open(parts / "skipped-federal.json.gz", "wt") as fh:
        json.dump({"rows": [FED, {**FED, "id": "2", "name": "Tribes Only"}]}, fh)
    today = skipped.datetime.now(skipped.timezone.utc).date().isoformat()
    prev = tmp_path / "prev.csv"
    prev.write_text("Source,ID,First seen\nFederal (Grants.gov),1," + today + "\n", encoding="utf-8")
    out_file = tmp_path / "gh.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out_file))
    monkeypatch.setattr("sys.argv", ["skipped", "--parts", str(parts), "--previous", str(prev),
                                     "--decisions", str(tmp_path / "none.csv"),
                                     "--csv", str(tmp_path / "s.csv"), "--md", str(tmp_path / "s.md")])
    skipped.main()
    assert "new=1" in out_file.read_text()


def test_a_show_decision_puts_a_hidden_state_call_back_with_the_note():
    from grantmatch.export_web import apply_reviews
    recs = [{"id": "ca-1", "nonprofit_eligible": False, "applicant_types": "Public Agency"},
            {"id": "ca-2", "nonprofit_eligible": False, "applicant_types": "Business"},
            {"id": "ca-3", "nonprofit_eligible": True, "applicant_types": "Nonprofit"}]
    decisions = {("california", "ca-1"): {"decision": "show", "note": "Community groups can apply."},
                 ("california", "ca-2"): {"decision": "justified", "note": "Businesses only."},
                 ("illinois", "ca-3"): {"decision": "show", "note": "x"}}
    assert apply_reviews(recs, "california", decisions) == 1
    assert recs[0]["nonprofit_eligible"] is True
    assert recs[0]["applicant_types"] == "Shown after review: Community groups can apply. Public Agency"
    assert recs[1]["nonprofit_eligible"] is False and recs[2]["applicant_types"] == "Nonprofit"


def test_a_hide_decision_takes_a_state_program_off_and_the_report_lists_it(tmp_path):
    from grantmatch.export_web import apply_reviews
    recs = [{"id": "fl-1", "nonprofit_eligible": True, "applicant_types": "Non-Profit"},
            {"id": "fl-2", "nonprofit_eligible": True, "applicant_types": "Non-Profit"}]
    decisions = {("florida", "fl-1"): {"decision": "hide", "note": "Student scholarship."}}
    assert apply_reviews(recs, "florida", decisions) == 1
    assert recs[0]["nonprofit_eligible"] is False and recs[1]["nonprofit_eligible"] is True
    path = tmp_path / "florida.json.gz"
    with gzip.open(path, "wt") as fh:
        json.dump({"programs": [{"id": "fl-1", "title": "Scholarship", "nonprofit_eligible": True, "earmark": False},
                                {"id": "fl-2", "title": "Open grant", "nonprofit_eligible": True, "earmark": False}]}, fh)
    rows = skipped.hidden_programs(path, "florida", decisions)
    assert [(r["id"], r["reason"]) for r in rows] == [("fl-1", "review_hidden")]


def test_a_confirmed_decision_replaces_the_read_the_notice_guess():
    from grantmatch.export_web import apply_reviews
    recs = [{"id": "ia-1", "nonprofit_eligible": True, "applicant_types": "Who may apply isn't stated on the listing; read the notice"},
            {"id": "ia-2", "nonprofit_eligible": False, "applicant_types": "City must be the applicant."}]
    decisions = {("iowa", "ia-1"): {"decision": "confirmed", "note": "Iowa law requires a 501(c)(3) provider."},
                 ("iowa", "ia-2"): {"decision": "confirmed", "note": "x"}}
    assert apply_reviews(recs, "iowa", decisions) == 1
    assert recs[0]["applicant_types"] == "Checked against the notice: Iowa law requires a 501(c)(3) provider."
    assert recs[1]["nonprofit_eligible"] is False   # confirmed never puts back a hidden one; that's show
