"""What the web-page adapters share (grantmatch/webpages.py): the crawling rule, dates and dropped rows."""
import pytest

from grantmatch import cycles, refresh_states, states, webpages

MODULES = ("arkansas", "maryland", "northdakota", "wyoming")


def test_a_page_off_limits_is_never_asked_for(monkeypatch):
    asked = []
    monkeypatch.setattr(cycles, "off_limits", lambda url: "robots.txt asks automated visitors to stay out")
    monkeypatch.setattr(cycles, "session", lambda: asked.append("session"))
    with pytest.raises(cycles.OffLimits, match="stay out"):
        webpages.get("https://example.org/grants")
    assert asked == []


def test_every_request_goes_through_the_projects_fetch_and_agent():
    import importlib
    import inspect
    assert "grant-matcher" in cycles.AGENT and cycles.session().headers["User-Agent"] == cycles.AGENT
    assert webpages.fetch_page is cycles.fetch_page
    for name in MODULES:
        source = inspect.getsource(importlib.import_module(f"grantmatch.{name}"))
        assert "requests." not in source and "User-Agent" not in source, name   # no session of their own


def test_the_weekly_driver_checks_each_new_adapters_list_before_running_it():
    import importlib
    for code in ("AR", "MD", "ND", "WY"):
        assert code in refresh_states.weekly_states()
        module = importlib.import_module(f"grantmatch.{states.STATES[code]['module']}")
        assert "LIST" in refresh_states.ADDRESSES and module.LIST in states.STATES[code]["pages"], code


@pytest.mark.parametrize("text, want", [
    ("Applications are due Jan. 29, 2027.", "2027-01-29"), ("March 26, 2027", "2027-03-26"), ("12/09/26", "2026-12-09"),
    ("01/05/2027", "2027-01-05"), ("Rolling", None), ("February 30, 2027", None), ("", None),
])
def test_dates_as_the_pages_write_them(text, want):
    assert webpages.day(text) == want


def rec(**kwargs):
    return webpages.record("ND", kwargs.pop("key", "a"), kwargs.pop("title", "A"), "Agency", "https://x", "https://x",
                           "Nonprofits", True, **{"closes": "2027-01-01", **kwargs})


def test_rows_that_cannot_be_shown_are_dropped_with_a_reason():
    rows = [{"record": rec()}, {"record": rec()}, {"record": rec(key="b", title="")},
            {"record": rec(key="c"), "closed": "Applications are paused"}, {"record": rec(key="d", closes="2026-01-01")},
            {"record": rec(key="e", closes=None, deadline_words="spring")},
            {"record": rec(key="f", title="By invitation only grant")}, {"record": rec(key="g", closes=None, rolling=True)}]
    skips = []
    kept = webpages.keep_open("northdakota", rows, "2026-11-26", skips)
    assert [r["id"] for r in kept] == ["nd-a", "nd-g"]
    assert [s["reason"] for s in skips] == ["duplicate", "no_title", "not_taking", "deadline_passed", "no_deadline",
                                           "invitation_only"]
    from grantmatch import skipped
    assert all(s["reason"] in skipped.REASONS for s in skips)


def test_no_email_address_is_kept():
    r = webpages.record("ND", "a", "A", "Agency", "https://x", "https://x", "Write someone@example.org", True,
                        application="Email grants@example.org")
    assert not [v for v in r.values() if isinstance(v, str) and "@" in v]
