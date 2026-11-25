"""What the shipped crawlers may not read (grantmatch/cycles.py off_limits). No network: robots.txt is passed in."""
from datetime import date
from urllib import robotparser

import pytest

from grantmatch import cycles, watch


def robots(monkeypatch, text, root="https://example.org"):
    """Pretend `root` serves this robots.txt; any other request fails the test."""
    lines = text.splitlines()
    rp = robotparser.RobotFileParser()
    rp.parse(lines)
    monkeypatch.setattr(cycles, "_robots", {root: (rp, lines)})

    def no_network():
        raise AssertionError("no request may be made")

    monkeypatch.setattr(cycles, "session", no_network)


def test_an_open_site_is_allowed(monkeypatch):
    robots(monkeypatch, "User-agent: *\nDisallow: /admin/\n")
    assert cycles.off_limits("https://example.org/grants") is None
    assert cycles.allowed("https://example.org/grants")
    assert not cycles.allowed("https://example.org/admin/x")


@pytest.mark.parametrize("agent", ["ClaudeBot", "claudebot", "anthropic-ai", "Claude-Web", "Claude-User",
                                   "Claude-SearchBot"])
def test_a_site_that_keeps_an_anthropic_agent_out_is_off_limits(monkeypatch, agent):
    robots(monkeypatch, f"User-agent: {agent}\nDisallow: /\n\nUser-agent: *\nAllow: /\n")
    assert "off limits" in cycles.off_limits("https://example.org/grants")


def test_a_site_that_keeps_this_crawler_out_is_off_limits(monkeypatch):
    robots(monkeypatch, "User-agent: grant-matcher\nDisallow: /\n")
    assert cycles.off_limits("https://example.org/grants") == "robots.txt asks automated visitors to stay out"


def test_a_claudebot_rule_for_one_path_blocks_only_that_path(monkeypatch):
    robots(monkeypatch, "User-agent: GPTBot\nUser-agent: ClaudeBot\nDisallow: /private/\n")
    assert not cycles.allowed("https://example.org/private/rfp")
    assert cycles.allowed("https://example.org/grants")


def test_wildcards_and_end_marks_are_read():
    lines = "User-agent: ClaudeBot\nDisallow: /*.pdf$\nDisallow: /search*?page=\nAllow: /public/*.pdf$".splitlines()
    assert cycles.robots_disallows(lines, "ClaudeBot", "/docs/rfp.pdf")
    assert not cycles.robots_disallows(lines, "ClaudeBot", "/docs/rfp.pdf.html")
    assert not cycles.robots_disallows(lines, "ClaudeBot", "/public/rfp.pdf")  # the longer Allow wins
    assert cycles.robots_disallows(lines, "ClaudeBot", "/search/all?page=2")
    assert not cycles.robots_disallows(lines, "grant-matcher", "/docs/rfp.pdf")  # not its group
    assert not cycles.robots_disallows(["User-agent: *", "Disallow:"], "ClaudeBot", "/x")
    # a crawl delay ends a group's list of agents, so another bot's ban never spreads to everyone
    delayed = "User-agent: *\nCrawl-delay: 10\n\nUser-agent: OtherBot\nDisallow: /".splitlines()
    assert not cycles.robots_disallows(delayed, "grant-matcher", "/x")
    assert cycles.robots_disallows(delayed, "OtherBot", "/x")


@pytest.mark.parametrize("url", [
    "https://apply.surveymonkey.com/x", "https://humanitiesiowa.submittable.com/submit", "https://county.bonfirehub.com/p",
    "https://www.in.gov/sba/grants", "https://www.nc.gov/grants", "https://dhhs.ne.gov/x",
])
def test_a_host_whose_terms_forbid_automation_is_off_limits_without_asking_it_anything(monkeypatch, url):
    robots(monkeypatch, "User-agent: *\nAllow: /\n")
    assert cycles.off_limits(url).startswith("site terms: ")


def test_the_blocklist_matches_whole_host_names_only():
    assert cycles.blocked_by_terms("https://notin.gov/x") is None
    assert cycles.blocked_by_terms("https://www.sc.gov/x") is None
    assert cycles.blocked_by_terms("https://example.org/surveymonkey.com") is None
    assert all(why and host == host.lower() for host, why in cycles.BLOCKED_HOSTS.items())


class Reply:
    def __init__(self, location=None, status=200):
        self.headers = {"location": location} if location else {"content-type": "text/html"}
        self.is_redirect = bool(location)
        self.status_code, self.ok = status, status < 400

    def close(self):
        pass


def test_a_redirect_to_a_blocked_host_is_never_followed(monkeypatch):
    robots(monkeypatch, "User-agent: *\nAllow: /\n")
    asked = []

    class Session:
        def get(self, url, **kwargs):
            assert kwargs["allow_redirects"] is False
            asked.append(url)
            return Reply("https://org.submittable.com/submit")

    monkeypatch.setattr(cycles, "session", Session)
    with pytest.raises(cycles.OffLimits):
        cycles.fetch_page("https://example.org/apply")
    assert asked == ["https://example.org/apply"]
    assert cycles.get("https://example.org/apply") is None
    assert watch.read("https://example.org/apply")["s"] == "blocked"


def test_the_watcher_reports_a_blocked_page_with_why_and_keeps_the_entry(monkeypatch):
    robots(monkeypatch, "User-agent: ClaudeBot\nDisallow: /\n")
    reading = watch.read("https://example.org/grants")
    assert reading["s"] == "blocked" and "ClaudeBot" in reading["why"]
    row = {"list": "local-FL", "key": "k", "name": "Synthetic Grant", "checked": "2026-11-25",
           "url": "https://example.org/grants"}
    results, _ = watch.run([row], {}, date(2026, 11, 26), 90, workers=1, reader=watch.read)
    text = watch.report(results, date(2026, 11, 26), first_run=True)
    assert "Blocked by robots.txt or site terms" in text and "## Synthetic Grant" in text


def test_a_blocked_page_is_not_retried_over_plain_http(monkeypatch):
    robots(monkeypatch, "User-agent: ClaudeBot\nDisallow: /\n")
    tried = []
    monkeypatch.setattr(cycles, "get", lambda url: tried.append(url))
    assert cycles.check("https://example.org/", date(2026, 11, 25)) == {"s": "error"}
    assert tried == ["https://example.org/"]


def test_robots_txt_is_asked_for_as_text_and_its_rules_are_read(monkeypatch):
    sent = {}

    class Session:
        def get(self, url, **kwargs):
            sent.update(kwargs["headers"], url=url)
            reply = Reply()
            reply.text = "\ufeffUser-agent: ClaudeBot\r\nDisallow: /\r\n"
            reply.content = reply.text.encode("utf-8")
            return reply

    monkeypatch.setattr(cycles, "_robots", {})
    monkeypatch.setattr(cycles, "session", Session)
    assert "ClaudeBot" in cycles.off_limits("https://example.org/grants")
    assert sent["url"] == "https://example.org/robots.txt" and sent["Accept"].startswith("text/plain")
