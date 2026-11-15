from datetime import date

from grantmatch.cycles import apply_link, classify, deadlines, grants_page, merge, page_text, site_url, snippet

TODAY = date(2026, 11, 15)


def test_page_text_keeps_words_and_drops_code():
    raw = "<html><head><style>p{color:red}</style><script>var x='open';</script></head>" \
          "<body><p>Applications are <b>now open</b>.</p><!-- hidden --></body></html>"
    text = page_text(raw)
    assert "Applications are now open" in text
    assert "color" not in text and "var x" not in text and "hidden" not in text


def test_open_with_a_deadline():
    r = classify("Grant Deadline: February 1, 2027. We are currently accepting applications.", TODAY)
    assert r["s"] == "open" and r["d"] == "2027-02-01"
    assert "currently accepting applications" in r["q"]


def test_deadline_only_when_near_words_about_applying():
    assert classify("Next grant application deadline is January 8, 2027.", TODAY) == {
        "s": "deadline", "d": "2027-01-08", "q": "Next grant application deadline is January 8, 2027."}
    assert classify("Join us at our gala on January 8, 2027.", TODAY)["s"] == "none"
    assert classify("The final report is due January 8, 2027.", TODAY)["s"] == "none"  # a report, not an application
    assert classify("Applications were due January 8, 2025.", TODAY)["s"] == "none"  # already past


def test_numeric_dates_and_far_future_dates():
    assert [d for d, *_ in deadlines("Deadline 3/15/2027", TODAY)] == [date(2027, 3, 15)]
    assert deadlines("Deadline March 1, 2031", TODAY) == []  # too far ahead to be a live cycle


def test_closed_and_invitation_only():
    assert classify("The Fall 2026 grant application portal is now closed.", TODAY)["s"] == "closed"
    assert classify("We accept grant applications by invitation only.", TODAY)["s"] == "closed"
    assert classify("MFF is currently not accepting unsolicited grant applications.", TODAY)["s"] == "closed"


def test_nothing_said():
    assert classify("We support education and the arts in Manatee County.", TODAY) == {"s": "none"}


def test_grants_page_beats_home_unless_it_says_nothing():
    home = {"s": "open", "q": "Applications are open"}
    assert merge(home, {"s": "none"}) is home
    assert merge(home, {"s": "deadline", "d": "2027-01-01", "q": "x"}) == {**home, "d": "2027-01-01"}
    inner = {"s": "closed", "q": "Applications are closed"}
    assert merge({"s": "none"}, inner) is inner


def test_finds_the_grants_page_on_the_same_site():
    raw = '<a href="/about">About us</a><a href="/grants/how-to-apply">How to apply</a>' \
          '<a href="https://other.org/grants">Grants elsewhere</a><a href="/docs/form.pdf">Grant form</a>'
    assert grants_page(raw, "https://www.example.org/") == "https://www.example.org/grants/how-to-apply"


def test_apply_link_goes_to_outside_portals():
    raw = '<a href="https://example.submittable.com/submit"> Apply now </a><a href="/apply">Apply for a job</a>'
    assert apply_link(raw, "https://example.org/") == "https://example.submittable.com/submit"


def test_site_url_reads_what_returns_write():
    assert site_url("WWW.EXAMPLE.ORG") == "https://www.example.org"
    assert site_url("HTTPS://POKAGONFUND.ORG/") == "https://pokagonfund.org"
    assert site_url("example.org/grants") == "https://example.org/grants"
    for junk in ("N/A", "NONE", "", None, "0", "info@example.org", "NOT APPLICABLE"):
        assert site_url(junk) == ""


def test_snippet_is_short_and_has_context():
    text = "Our grants. December 3, 2026. Other words follow here."
    s = snippet(text, text.index("December"), text.index("2026") + 4)
    assert "Our grants" in s and len(s) <= 160
