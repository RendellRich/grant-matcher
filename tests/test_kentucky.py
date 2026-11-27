"""The Kentucky Arts Council's grant pages into state program records (grantmatch/kentucky.py), and the limit to
/grants/."""
from pathlib import Path

import pytest

from grantmatch import cycles
from grantmatch import freshness
from grantmatch import kentucky as ky

FIXTURES = Path(__file__).parent / "fixtures"
read = lambda name: (FIXTURES / f"kentucky-{name}.html").read_text(encoding="utf-8")
LIST, PROGRAM = read("grants"), read("program")
MILES = (PROGRAM.replace("Kentucky Arts Rising", "Arts Miles").replace("<p>Eligibility</p>", "<p>Who May Apply</p>")
         .replace("be a free-standing arts group independent of any other organization.", "Any teacher at a Kentucky school.")
         .replace("currently have, and maintain during the grant cycle, IRS tax-exempt status.", ""))
TOURING = (PROGRAM.replace("Kentucky Arts Rising", "Kentucky Touring Grant")
           .replace("February 15, 2027 Grant Period: July 1, 2027 - June 30, 2028 Apply Here",
                    "March 31, 2026 This program is currently closed."))
TODAY = "2026-11-27"


def pages(**changed):
    saved = {"grants": LIST, "kentucky-arts-rising": PROGRAM, "arts-miles-program-grant": MILES,
             "kentucky-touring-grant": TOURING, **changed}
    return lambda url, name: saved[name]


def test_open_calls_a_nonprofit_could_apply_to_are_kept():
    skips = []
    recs = ky.build_records(ky.read_rows(pages(), TODAY), today=TODAY, skips=skips)
    assert [r["id"] for r in recs] == ["ky-kentucky-arts-rising"]
    assert [(s["id"], s["reason"]) for s in skips] == [("ky-arts-miles", "state_not_nonprofit"),
                                                      ("ky-kentucky-touring-grant", "not_taking")]
    r = recs[0]
    assert (r["closes"], r["nonprofit_eligible"]) == ("2027-02-15", True)
    assert "tax-exempt status" in r["applicant_types"] and "Earned revenue" not in r["applicant_types"]
    assert "$1,500" in r["award"] and "Apply Here" not in r["application"]


@pytest.mark.parametrize("name, old, new", [
    ("grants", "/grants/", "/programs/"), ("grants", "</main>", '<a href="/grants/page/2/">2</a></main>'),
    ("kentucky-arts-rising", "Application Deadline:", "Due:"), ("kentucky-arts-rising", "<p>Eligibility</p>", ""),
])
def test_a_page_that_changes_shape_stops_the_run(name, old, new):
    changed = pages()(None, name).replace(old, new)
    with pytest.raises(RuntimeError, match="keeping the previous data file"):
        ky.read_rows(pages(**{name: changed}), TODAY)


def test_each_page_is_asked_for_once_ten_seconds_apart(monkeypatch, tmp_path):
    asked, slept = [], []
    served = {ky.LIST: LIST, ky.LIST + "kentucky-arts-rising/": PROGRAM, ky.LIST + "arts-miles-program-grant/": MILES,
              ky.LIST + "kentucky-touring-grant/": TOURING}
    monkeypatch.setattr(ky.webpages, "get", lambda url: asked.append(url) or served[url])
    monkeypatch.setattr(ky.time, "sleep", slept.append)
    ky.build(tmp_path / "kentucky.json.gz")
    assert asked == list(served) and slept == [10, 10, 10]


@pytest.mark.parametrize("url", [
    "https://artscouncil.ky.gov/", "https://artscouncil.ky.gov/terms-of-service",
    "https://artscouncil.ky.gov/directory/grants/",
])
def test_nothing_outside_the_grant_pages_is_asked_for(url, monkeypatch):
    asked = []
    monkeypatch.setattr(cycles, "_robots_for", lambda root: asked.append(root))
    assert "/grants/" in cycles.off_limits(url) and asked == []   # not even robots.txt for a page we won't read


def test_the_freshness_check_asks_nothing_of_the_host():
    other = "https://art.mt.gov/sig"
    assert freshness.plan([ky.LIST, other], {ky.LIST}, {}) == [other]
