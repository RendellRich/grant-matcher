"""What the web-page adapters share (grantmatch/webpages.py): the crawling rule, dates and dropped rows."""
import pytest

from grantmatch import cycles, refresh_states, states, webpages

# closed wording the rule wasn't written from: what a rolling call's page might say instead of a date
CLOSED_WORDS = [
    "Applications are no longer being accepted.", "We are no longer taking applications.",
    "Funds have been depleted for FY27.", "All FY27 funds have been awarded.", "This grant opportunity has closed.",
    "Funding has been exhausted.", "We have stopped taking requests.", "This program is on a waiting list.",
    "No funding remains this year.", "The fund is fully committed.", "The program has ended.",
    "Submissions closed early.", "This grant is unavailable.", "Check back next spring.",
    "The Council has discontinued this grant.", "Applications will not be accepted at this time.",
    "Money for this year has run out.", "The round was cancelled.", "Applications will reopen in the spring.",
    "No new applications will be accepted this year.", "We cannot accept new applications at this time.",
    "We have suspended this program.", "Applications are on a temporary hold.", "The deadline has passed.",
    "This program has been eliminated.", "The FY27 budget has been spent.", "We are at capacity.",
    "Awards will resume when the legislature meets.", "No applications are being accepted.",
]
# words about what happens one day, or about late or ineligible applications, which close nothing today
OPEN_WORDS = [
    "Applications are accepted until funds are depleted.", "Funds will be awarded until they are depleted.",
    "Once all funds have been awarded, later requests wait for next year.", "If funds are exhausted, we will say so here.",
    "Grants are paid after the project's close-out report.", "Late applications will not be accepted.",
    "Grantees must not be debarred or suspended.", "The Strategic committee meets monthly; meetings are open to the public.",
    "Funds are expended on a reimbursement basis.", "Funds are not available for equipment.",
    "No applications will be accepted that are missing a budget.", "We will not accept late applications.",
    "Funds are awarded on a first-come, first-served basis.",
]


MODULES = ("arkansas", "kentucky", "maryland", "missouri", "montana", "northdakota", "tennessee", "wyoming")


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
    for code in ("AR", "KY", "MD", "MO", "MT", "ND", "TN", "WY"):
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
            {"record": rec(key="f", title="By invitation only grant")},
            {"record": rec(key="g", closes=None, rolling=True), "rolling": ["Apply any time."]}]
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


@pytest.mark.parametrize("text, want", [
    ("11/01/26 - 12/15/26", "2026-12-15"), ("Opens 12/01/26, due 01/15/27", "2027-01-15"),
    ("January 5, 2027 through February 1, 2027", "2027-02-01"), ("December 18, 2026 (NEW earlier deadline)", "2026-12-18"),
])
def test_a_range_gives_its_closing_date(text, want):
    assert webpages.day(text) == want


@pytest.mark.parametrize("said", [
    "Applications are closed.", "This grant is closed for applications.", "Applications are currently closed.",
    "We are no longer accepting applications.", "Arts on Tour is on hold until July.", "This program has been suspended.",
    "The grant is now closed.", "Applications are temporarily closed.",
    "AE-CI applications are not being accepted for new projects.", "The FY27 application is now closed as of 9/8/2026.",
])
def test_the_ways_a_page_says_it_is_not_taking_applications(said):
    assert webpages.not_taking([said], "2026-11-26") == said


@pytest.mark.parametrize("said", [
    "Applicants must not be debarred or suspended.", "Late applications will not be accepted.",
    "All other counties not listed above are now closed.", "Grants must be closed out by June 15.",
])
def test_other_words_do_not_close_a_call(said):
    assert webpages.not_taking([said], "2026-11-26") == ""


def test_closed_beside_a_later_window_or_about_an_earlier_year_does_not_close_the_call():
    # the wording on Wyoming's pages, beside windows that open in 2027
    wait = "The application period for this grant is currently closed. The FY28 application will open in February 2027."
    assert webpages.not_taking([wait], "2026-11-26", "2027-02-15") == ""
    assert webpages.not_taking([wait], "2027-02-20", "2027-02-15") == ""   # the line is out of date once it opens
    old = "The Fiscal Year 2026 Sample Grant application period is now closed."
    assert webpages.not_taking([old], "2026-11-26", "2027-01-01") == ""
    assert webpages.not_taking([old], "2027-01-15", "2027-01-01") == ""
    # with no later window, closed is closed; and a pause holds whatever the window says
    assert webpages.not_taking(["Applications are closed."], "2026-11-26") != ""
    assert webpages.not_taking(["This grant is on hold."], "2026-11-26", "2027-02-15") != ""


@pytest.mark.parametrize("who, open_", [
    ("Arts and non-arts organizations", True), ("Arts & non-arts organizations", True), ("Organizations & individuals", True),
    ("Organizations", True), ("Non-profit organizations", True), ("501(c)3 arts organizations", True), ("", True),
    ("Individual artists cannot apply. The grant is available to organizations.", True),
    ("Open to nonprofit organizations. For-profit organizations are not eligible.", True),
    ("This grant is open to individual artists. Organizations are not eligible.", False),
    ("Individual artists, not organizations, are eligible.", False),
    ("Nonprofit organizations are not eligible; this is open to individual artists only.", False),
    ("Non-profit organizations are not eligible", False), ("This grant is open to individuals.", False),
    ("Educational institutions", False), ("Public K-12 Schools", False),
])
def test_who_may_apply_in_the_pages_words(who, open_):
    assert webpages.open_to_nonprofits(who) is open_


def undated(rolling, about=(), **kwargs):
    row = {"record": rec(key="r", closes=None, rolling=True), "rolling": [rolling], "about": [rolling, *about], **kwargs}
    skips = []
    return bool(webpages.keep_open("northdakota", [row], "2026-11-26", skips)), skips


@pytest.mark.parametrize("said", [
    "Application Deadline Ongoing.", "Rolling", "Applications will be accepted on a continual basis until funds are depleted.",
    "We are currently accepting applications.", "Applications are due on the 15th of each month.",
    "Applications are accepted year-round.", "Apply at any time.",
])
def test_a_call_with_no_date_is_listed_when_its_page_says_it_is_taking_applications(said):
    assert undated(said)[0] is True


@pytest.mark.parametrize("said", [
    "Application Deadline TBA.", "See the guidelines.", "Contact the program manager about dates.",
    "Application Deadline Closed.", "", "Applications are reviewed by a panel.",
])
def test_no_closed_phrase_is_never_enough(said):
    kept, skips = undated(said)
    assert kept is False and skips[0]["reason"] == "not_taking"


def test_a_rolling_record_that_brings_no_words_is_not_listed():
    assert webpages.keep_open("northdakota", [{"record": rec(key="r", closes=None, rolling=True)}], "2026-11-26") == []


@pytest.mark.parametrize("said", CLOSED_WORDS)
def test_a_yes_beside_any_closed_wording_is_not_taking(said):
    kept, skips = undated("Application Deadline Ongoing.", [said])
    assert kept is False and skips[0]["reason"] == "not_taking" and "The page says:" in skips[0]["detail"]


@pytest.mark.parametrize("said", OPEN_WORDS)
def test_words_about_one_day_or_late_applications_close_nothing(said):
    assert undated("Application Deadline Ongoing.", [said])[0] is True
    assert webpages.not_taking([said], "2026-11-26") == ""


@pytest.mark.parametrize("said", CLOSED_WORDS[:6])
def test_the_phrasings_the_review_found_close_a_dated_call_too(said):
    assert webpages.not_taking([f"Sample words. {said} More words."], "2026-11-26") == said


def test_money_gone_in_an_earlier_year_does_not_close_this_one():
    assert webpages.not_taking(["All FY26 funds have been awarded."], "2026-11-26") == ""


def test_an_opening_day_that_has_come_is_no_doubt():
    said = "For FY27, applications for this grant will open July 1, 2026."
    assert undated("Applications are accepted year-round.", [said])[0] is True
    assert undated("Applications are accepted year-round.", ["Applications will open July 1, 2027."])[0] is False
