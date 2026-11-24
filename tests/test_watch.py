"""Page watcher for the hand-kept lists (grantmatch/watch.py). No network: pages are passed in."""
from datetime import date

from grantmatch import watch

TODAY = date(2026, 11, 20)
ROW = {"list": "local-FL", "key": "sample-city-arts", "name": "Synthetic Arts Grant", "checked": "2026-11-19",
       "url": "https://example.org/arts"}
PAGE = ("Synthetic Arts Grant. The city gives grants of up to $2,500 to small arts nonprofits in the city. "
        "Applications are reviewed by a panel of residents each spring. "
        "Copyright 2026 Sample City. All rights reserved. ") * 3


def ok(text):
    return {"s": "ok", "text": text}


def kinds(found):
    return {x["t"] for x in found}


def test_the_real_lists_give_one_row_per_page():
    rows = watch.targets()
    assert rows and len({(r["list"], r["key"], r["url"]) for r in rows}) == len(rows)
    assert {"local-FL", "local-WA", "corporate"} <= {r["list"] for r in rows}
    assert all(r["url"].startswith("https://") for r in rows)


def test_first_reading_of_a_quiet_page_needs_nothing():
    found, memory = watch.assess(ROW, ok(PAGE), None, TODAY, 90)
    assert found == []
    assert memory["fp"] and memory["seen"] == "2026-11-20"


def test_same_page_next_week_needs_nothing_even_if_noise_moves():
    _, memory = watch.assess(ROW, ok(PAGE), None, TODAY, 90)
    noisy = PAGE.replace("Copyright 2026", "Copyright 2027") + " Last updated November 27, 2026 at 3:14 p.m."
    found, _ = watch.assess(ROW, ok(noisy), memory, date(2026, 11, 27), 90)
    assert found == []


def test_a_changed_amount_is_reported_as_added_and_removed():
    _, memory = watch.assess(ROW, ok(PAGE), None, TODAY, 90)
    found, _ = watch.assess(ROW, ok(PAGE.replace("$2,500", "$5,000")), memory, date(2026, 11, 27), 90)
    change = next(x for x in found if x["t"] == "changed")
    assert any("$5,000" in s for s in change["added"]) and any("$2,500" in s for s in change["removed"])


def test_on_hold_wording_is_reported_once():
    held = PAGE + " The Grant and Aid Program is on hold until further notice."
    _, memory = watch.assess(ROW, ok(PAGE), None, TODAY, 90)
    found, memory = watch.assess(ROW, ok(held), memory, date(2026, 11, 27), 90)
    assert "status" in kinds(found)
    assert any("on hold" in s for x in found if x["t"] == "status" for s in x["lines"])
    found, _ = watch.assess(ROW, ok(held), memory, date(2026, 12, 4), 90)
    assert "status" not in kinds(found)  # already reported last week


def test_blank_error_blocked_and_stale():
    assert "blank" in kinds(watch.assess(ROW, ok("Loading..."), None, TODAY, 90)[0])
    found, memory = watch.assess(ROW, {"s": "error", "why": "HTTP 404"}, {"fp": "abc"}, TODAY, 90)
    assert "error" in kinds(found) and memory["fp"] == "abc"  # last good reading is kept
    assert "blocked" in kinds(watch.assess(ROW, {"s": "blocked", "why": "robots.txt"}, None, TODAY, 90)[0])
    old = dict(ROW, checked="2026-06-01")
    assert "stale" in kinds(watch.assess(old, ok(PAGE), None, TODAY, 90)[0])


def test_file_types():
    assert watch.kind("https://x.gov/a.pdf", "") == "pdf"
    assert watch.kind("https://x.gov/a", "application/pdf") == "pdf"
    assert watch.kind("https://x.gov/a.docx", "application/octet-stream") == "docx"
    assert watch.kind("https://x.gov/a", "text/html; charset=utf-8") == "html"
    assert watch.kind("https://x.gov/a.png", "image/png") == "other"


def test_run_and_report_with_a_fake_reader():
    rows = [ROW, dict(ROW, key="sample-held", name="Held Grant", url="https://example.org/held")]
    pages = {ROW["url"]: ok(PAGE), "https://example.org/held": ok(PAGE + " Applications are on hold until further notice.")}
    results, state = watch.run(rows, {}, TODAY, 90, workers=2, reader=pages.get)
    text = watch.report(results, TODAY, first_run=True)
    assert set(state) == set(pages)
    assert "2 pages read, 1 need a look" in text and "## Held Grant" in text and "Synthetic Arts Grant" not in text
    assert "\u2014" not in text


def test_a_suspended_vendor_list_is_not_a_suspended_program():
    vendor = PAGE + " Purchasing Status: The vendor must not appear on the Suspended Vendor List."
    assert not watch.status_lines(vendor)
    assert watch.status_lines(PAGE + " The grant program has been suspended for 2027.")
    assert watch.status_lines(PAGE + " Applications are paused until the spring.")
