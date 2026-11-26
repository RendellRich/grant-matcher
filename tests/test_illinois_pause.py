"""While the registry marks Illinois "paused" (grantmatch/states.py), nothing is asked of any Illinois host, and the
daily job's steps still succeed by republishing the last published files unchanged. No network: sessions are faked."""
import gzip
import json
import re
import shlex
import sys
from datetime import date
from urllib.parse import urlparse

import numpy as np
import pytest
import requests

from grantmatch import cycles, embed, export_web, freshness, illinois, states, watch

ROOT = export_web.LOCAL.parent
PAUSED = ["omb.illinois.gov", "il.amplifund.com"]
OMB = "https://omb.illinois.gov/PUBLIC/GATA/CSFA/Opportunity.aspx?nofo=1"
GMS = "https://il.amplifund.com/Public/Opportunities/Details/abc-123"
FETCHED = "2026-11-25T14:50+00:00"


def gz(obj) -> bytes:
    return gzip.compress(json.dumps(obj).encode("utf-8"))


def program(n, url):
    return {"id": f"il-{n}", "title": f"Reading Grant {n}", "agency": "Agency", "objectives": "Literacy.",
            "subjects": "", "url": url, "closes": None, "nonprofit_eligible": True}


DATA = gz({"fetched_at": FETCHED, "state": "IL", "count": 2, "programs": [program(1, OMB), program(2, GMS)]})
SKIPPED = gz({"fetched_at": FETCHED, "rows": [{"source": "illinois", "id": "il-9", "name": "Old", "reason": "x"}]})


class Answer:
    def __init__(self, code=200, content=b"", headers=None, url=""):
        self.status_code, self.content, self.url = code, content, url
        self.headers = headers or {"content-type": "text/html"}
        self.ok = 200 <= code < 300
        self.is_redirect = code in (301, 302) and "location" in self.headers
        self.text = content.decode("utf-8", errors="replace")

    def raise_for_status(self):
        if not self.ok:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def iter_content(self, size):
        yield self.content

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class Session:
    """Records every address asked for; `answers` maps one to its Answer (or an exception to raise)."""

    def __init__(self, answers=None, default=None):
        self.answers, self.default, self.asked = answers or {}, default or Answer(), []

    def get(self, url, **kwargs):
        self.asked.append(url)
        got = self.answers.get(url, self.default)
        if isinstance(got, Exception):
            raise got
        return got


def release(data=DATA, skipped=SKIPPED):
    def answer(raw):
        return raw if isinstance(raw, (Answer, Exception)) else Answer(content=raw) if raw is not None else Answer(404)
    return Session({export_web.RELEASE + "illinois.json.gz": answer(data),
                    export_web.RELEASE + "skipped-illinois.json.gz": answer(skipped)}, default=Answer(404))


def illinois_hosts(asked):
    return [u for u in asked if any(h in (urlparse(u).hostname or "") for h in PAUSED + ["illinois.gov", "amplifund"])]


def test_the_registry_switch_is_on_and_names_the_states_two_hosts():
    assert states.STATES["IL"]["paused"]["hosts"] == PAUSED
    assert states.check() == []
    for url in (OMB, GMS, "https://www.omb.illinois.gov/x", states.STATES["IL"]["pages"][0], illinois.LIST):
        assert states.paused_host(url) == "reading Illinois's list is paused pending the state's written OK", url
    for url in ("https://arts.illinois.gov/x", "https://notomb.illinois.gov.example.org/", export_web.RELEASE):
        assert states.paused_host(url) is None, url


def run_workflow_steps(tmp_path, monkeypatch, session):
    """The adapter and embed commands exactly as .github/workflows/refresh-illinois.yml runs them, in tmp_path."""
    workflow = (ROOT / ".github" / "workflows" / "refresh-illinois.yml").read_text(encoding="utf-8")
    commands = [shlex.split(c)[2:] for c in re.findall(r"run: (python -m grantmatch\.\S+ .+)", workflow)]
    assert [c[0] for c in commands] == ["grantmatch.illinois", "grantmatch.embed"]
    uploads = re.search(r"gh release upload data-latest (.+?) --clobber", workflow).group(1).split()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(illinois, "session", session)
    monkeypatch.setattr(embed, "embed_texts", lambda texts: np.ones((len(texts), 384), dtype=np.float32))
    for module, command in zip((illinois, embed), commands):
        monkeypatch.setattr(sys, "argv", command)
        module.main()
    return uploads


def test_the_daily_job_succeeds_and_republishes_the_same_data_without_asking_illinois(tmp_path, monkeypatch, capsys):
    session = release()
    uploads = run_workflow_steps(tmp_path, monkeypatch, session)
    assert uploads == ["build/illinois.json.gz", "build/illinois.npz", "build/skipped-illinois.json.gz"]
    assert all((tmp_path / u).stat().st_size > 0 for u in uploads)
    assert (tmp_path / "build/illinois.json.gz").read_bytes() == DATA  # unchanged, old fetched_at and all
    assert (tmp_path / "build/skipped-illinois.json.gz").read_bytes() == SKIPPED
    assert embed.load(tmp_path / "build/illinois.npz").keys() == {"il-1", "il-2"}
    assert session.asked == [export_web.RELEASE + n for n in ("illinois.json.gz", "skipped-illinois.json.gz")]
    assert not illinois_hosts(session.asked)
    said = capsys.readouterr().out
    assert "paused" in said and FETCHED in said


@pytest.mark.parametrize("data, skipped", [
    (Answer(500), SKIPPED), (requests.ConnectionError("down"), SKIPPED), (None, SKIPPED),
    (gz({"fetched_at": FETCHED, "programs": []}), SKIPPED), (gz({"programs": [program(1, OMB)]}), SKIPPED),
    (b"not gzip", SKIPPED), (DATA, Answer(503)), (DATA, requests.Timeout("slow")),
    (DATA, b""), (DATA, b"<html>sign in</html>"), (DATA, SKIPPED[:20]), (DATA, gzip.compress(b"not json")),
    (DATA, gz(["a list"])), (DATA, gz({"fetched_at": FETCHED})),
], ids=["server error", "no connection", "no copy anywhere", "no calls", "no date", "corrupt", "skip list error",
        "skip list timeout", "skip list empty", "skip list not gzip", "skip list cut off", "skip list not json",
        "skip list not an object", "skip list without rows"])
def test_when_the_published_files_cannot_be_had_the_run_fails_and_writes_nothing(tmp_path, monkeypatch, data, skipped):
    monkeypatch.setattr(illinois, "LOCAL", tmp_path / "no-snapshot")
    monkeypatch.setattr(illinois, "session", release(data, skipped))
    with pytest.raises(Exception):
        illinois.build(tmp_path / "build" / "illinois.json.gz", tmp_path / "build" / "skipped-illinois.json.gz")
    assert not (tmp_path / "build").exists()  # the job stops here, so the release keeps its files


def test_a_snapshot_stands_in_only_when_the_release_has_no_copy(tmp_path, monkeypatch):
    (tmp_path / "illinois.json.gz").write_bytes(DATA)
    monkeypatch.setattr(illinois, "LOCAL", tmp_path)
    monkeypatch.setattr(illinois, "session", release(None, None))
    out, skips = tmp_path / "build" / "illinois.json.gz", tmp_path / "build" / "skipped-illinois.json.gz"
    assert illinois.build(out, skips) == 2
    assert out.read_bytes() == DATA
    assert json.loads(gzip.decompress(skips.read_bytes()))["rows"] == []  # none was published: nothing is replaced
    monkeypatch.setattr(illinois, "session", release(Answer(500), None))  # a failed read never falls back
    with pytest.raises(requests.HTTPError):
        illinois.build(out, skips)


def test_without_the_switch_the_adapter_reads_illinois_again(tmp_path, monkeypatch):
    monkeypatch.delitem(states.STATES["IL"], "paused")
    session = Session(default=Answer(content=b"<table></table>"))
    monkeypatch.setattr(illinois, "session", session)
    with pytest.raises(RuntimeError, match="rows on the Illinois list"):
        illinois.build(tmp_path / "illinois.json.gz")
    assert session.asked == [illinois.LIST]


def test_no_shipped_code_asks_the_paused_hosts_for_anything(monkeypatch):
    web = Session()
    monkeypatch.setattr(cycles, "_robots", {})
    monkeypatch.setattr(cycles, "session", lambda: web)
    monkeypatch.setattr(illinois, "session", web)
    for url in (OMB, GMS, illinois.LIST, OMB.replace("https:", "http:")):
        assert cycles.off_limits(url).startswith("reading Illinois"), url  # not even robots.txt
        assert freshness.host_delay(url) == 0.0
        assert freshness.link_reading(url)["s"] == "blocked"
        assert watch.read(url)["s"] == "blocked"
        assert cycles.get(url) is None and cycles.check(url, date(2026, 11, 26)) == {"s": "error"}
        with pytest.raises(RuntimeError, match="paused"):
            illinois._get(url)
    assert web.asked == []


def test_a_redirect_into_a_paused_host_is_not_followed(monkeypatch):
    start = "https://agency.example.org/grant"
    web = Session({start: Answer(302, headers={"location": OMB}), "https://agency.example.org/robots.txt": Answer(404)})
    monkeypatch.setattr(cycles, "_robots", {})
    monkeypatch.setattr(cycles, "session", lambda: web)
    with pytest.raises(cycles.OffLimits, match="paused"):
        cycles.fetch_page(start)
    assert not illinois_hosts(web.asked)


def paused_release(name, head=False):
    return DATA if name == "illinois.json.gz" else None


def test_the_freshness_check_flags_the_old_data_says_it_is_paused_and_asks_illinois_nothing(tmp_path, monkeypatch):
    web = Session(default=Answer(content=b""))
    monkeypatch.setattr(cycles, "_robots", {})
    monkeypatch.setattr(cycles, "session", lambda: web)

    def linker(urls):
        mine = [u for u in urls if "illinois" in u or "amplifund" in u]
        assert {OMB, GMS, states.STATES["IL"]["pages"][0]} <= set(mine)  # they are planned, and then not asked
        return freshness.check_links(mine, sleep=lambda s: None)

    result = freshness.check(None, {}, date(2026, 12, 5), release=paused_release, linker=linker)
    assert not [u for u in web.asked if any(h in u for h in PAUSED)]
    for url in (OMB, GMS, states.STATES["IL"]["pages"][0]):
        assert result["memory"]["links"][url]["s"] == "blocked"
    line = next(x for x in result["text"].splitlines() if "`state:IL`" in x and "days old" in x)
    assert "data from 2026-11-25" in line and "Reading is paused pending the state's written OK" in line


def test_the_export_marks_the_paused_state_and_keeps_its_data_date(tmp_path, monkeypatch):
    monkeypatch.setattr(export_web, "LOCAL_ONLY", True)
    monkeypatch.setattr(export_web, "fetch", lambda name, local=None: DATA if name == "illinois.json.gz" else None)
    monkeypatch.setattr(export_web, "foundation_states", lambda: [])
    monkeypatch.setattr(export_web.corporate, "load", lambda: {})
    monkeypatch.setattr(embed, "embed_texts", lambda texts: np.ones((len(texts), 384), dtype=np.float32))
    monkeypatch.setattr(embed, "embed_query", lambda text: np.ones(384, dtype=np.float32))
    monkeypatch.setattr(sys, "argv", ["export_web", str(tmp_path), "--local"])
    export_web.main()
    info = json.loads((tmp_path / "meta.json").read_text(encoding="utf-8"))["programs"]
    assert info["IL"]["paused"] is True and info["IL"]["updated"] == FETCHED
    assert not [s for s, i in info.items() if s != "IL" and "paused" in i]
