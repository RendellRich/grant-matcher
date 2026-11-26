"""The Maryland Commerce page's State Grants table into state program records (grantmatch/maryland.py)."""
import gzip
import json
from pathlib import Path

import pytest

from grantmatch import maryland as md
from grantmatch import match_words, states, webpages
from grantmatch.rank_more import ELIGIBILITY_UNSTATED

PAGE = (Path(__file__).parent / "fixtures" / "maryland.html").read_text(encoding="utf-8")
TODAY = "2026-11-26"


def built():
    skips = []
    recs = md.build_records(md.parse(PAGE), today=TODAY, skips=skips)
    return {r["title"]: r for r in recs}, skips


def test_only_the_state_grants_table_is_read():
    rows = md.parse(PAGE)
    assert len(rows) == 5 and not [r for r in rows if "Federal" in r["title"] or "Local" in r["title"]]
    assert rows[1]["url"] == "https://example.maryland.gov/buildings?a=1&b=2"
    assert rows[2]["url"] == "https://business.maryland.gov/arts"


def test_open_calls_say_to_read_the_notice_and_state_no_match():
    recs, _ = built()
    assert sorted(recs) == ["Sample Arts in Education", "Sample Buildings Grant Program", "Sample Training Grant"]
    r = recs["Sample Buildings Grant Program"]
    assert (r["state"], r["closes"], r["agency"]) == ("MD", "2026-12-09", "Sample Energy Office")
    assert r["applicant_types"] == md.WHO and ELIGIBILITY_UNSTATED.search(md.WHO) and r["nonprofit_eligible"] is True
    assert (r["match"], r["award"], r["objectives"]) == ("", "", "") and "match_none" not in r
    assert match_words.statement(r) == match_words.NOT_STATED
    rolling = recs["Sample Training Grant"]
    assert (rolling["closes"], rolling["deadlines"]) == (None, "Ongoing")


def test_past_and_undated_rows_are_left_out_with_a_reason():
    _, skips = built()
    assert sorted((s["name"], s["reason"]) for s in skips) == [
        ("Sample Capital Requests", "no_deadline"), ("Sample Past Heritage Grant", "deadline_passed")]


@pytest.mark.parametrize("old, new", [
    ('class="wp-block-heading">State Grants</h2>', 'class="wp-block-heading">Grants from the State</h2>'),
    ("<strong>Grant Name</strong></td><td><strong style", "<strong>Program</strong></td><td><strong style"),
    ("<td>Sample Energy Office</td>", ""),
])
def test_a_page_that_changed_shape_keeps_the_old_file(old, new):
    assert old in PAGE
    with pytest.raises(RuntimeError, match="keeping the previous data file"):
        md.parse(PAGE.replace(old, new))


def test_a_table_with_no_readable_date_or_gone_stops_the_run():
    dates = PAGE.replace("11/20/26", "soon").replace("12/09/26", "soon").replace("12/15/26", "soon").replace(">Rolling<", ">soon<")
    with pytest.raises(RuntimeError, match="No date"):
        md.parse(dates)
    with pytest.raises(RuntimeError, match="No table under"):
        md.parse('<h2>State Grants</h2><p>None</p><h2>Local Grants</h2><table></table>')


def test_the_labels_say_it_is_a_short_list():
    spec = states.STATE_PROGRAMS["MD"]
    assert "not a statewide list" in spec["source"] and "short list" in spec["catalog"] and spec["who_listed"] is False
    assert states.STATES["MD"]["pages"] == [md.LIST]


def test_a_saved_copy_is_read_without_the_network(tmp_path, monkeypatch):
    monkeypatch.setattr(webpages, "fetch_page", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no network")))
    page = tmp_path / "md.html"
    page.write_text(PAGE.replace("/26<", "/60<"), encoding="utf-8")   # two-digit years run to 2068
    out = tmp_path / "md.json.gz"
    assert md.build(out, tmp_path / "skipped.json.gz", page) == 4
    assert json.loads(gzip.decompress(out.read_bytes()))["state"] == "MD"


@pytest.mark.parametrize("cell", ["Rolling (closed)", "Rolling - funds exhausted", "Rolling; paused", "TBD"])
def test_a_rolling_row_is_listed_only_while_its_cell_says_so_and_nothing_else(cell):
    skips = []
    recs = md.build_records(md.parse(PAGE.replace("<td>Rolling</td>", f"<td>{cell}</td>")), today=TODAY, skips=skips)
    assert "Sample Training Grant" not in {r["title"] for r in recs}
    assert "Sample Training Grant" in {s["name"] for s in skips}


def test_a_notice_above_the_table_closes_the_rolling_row():
    page = PAGE.replace('<figure class="wp-block-table is-style-stripes">',
                        '<p>Funding has been exhausted.</p><figure class="wp-block-table is-style-stripes">')
    recs = md.build_records(md.parse(page), today=TODAY)
    assert "Sample Training Grant" not in {r["title"] for r in recs}
