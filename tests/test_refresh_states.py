"""The weekly state refresh driver (grantmatch/refresh_states.py) and the proposed workflows that use it
(docs/proposed-workflows/, text files nothing runs). No network: the adapters' build functions are replaced."""
import importlib
import re
import sys

import pytest

from grantmatch import export_web, refresh_states, skipped, states

ROOT = export_web.LOCAL.parent
CODES = ["AR", "DC", "MD", "MN", "MT", "NJ", "NY", "ND", "TN", "WV", "WY"]   # the registry's order


def test_the_driver_runs_every_built_state_that_has_no_daily_job():
    assert refresh_states.weekly_states() == CODES
    assert refresh_states.weekly_states() == [c for c, s in states.STATES.items()
                                              if s["status"] == "built" and c != "FL" and s["refresh"] != "daily"]


def fake_adapters(monkeypatch, broken=(), silent=(), empty=()):
    """Each adapter writes its two files, except the broken ones, which write half a file and fail."""
    for code in CODES:
        module = importlib.import_module(f"grantmatch.{states.STATES[code]['module']}")

        def build(out, skipped_out=None, saved=None, code=code):
            if code in silent:
                return 0
            out.write_bytes(f"new {code}".encode())
            if code in broken:
                raise RuntimeError("the page changed shape")
            skipped_out.write_bytes(f"skipped {code}".encode())
            return 0 if code in empty else 1

        monkeypatch.setattr(module, "build", build)


def name(code):
    return states.STATES[code]["file"]


def test_one_state_failing_keeps_its_file_and_does_not_stop_the_others(tmp_path, monkeypatch):
    (tmp_path / "minnesota.json.gz").write_bytes(b"last week")
    fake_adapters(monkeypatch, broken={"MN"}, silent={"NJ"})
    done, failed = refresh_states.refresh(tmp_path, allowed=lambda url: None)
    assert done == ["AR", "DC", "MD", "MT", "NY", "ND", "TN", "WV", "WY"] and sorted(failed) == ["MN", "NJ"]
    assert "page changed shape" in failed["MN"] and "no data file" in failed["NJ"]
    assert (tmp_path / "minnesota.json.gz").read_bytes() == b"last week"
    assert not (tmp_path / "newjersey.json.gz").exists() and not (tmp_path / "skipped-minnesota.json.gz").exists()
    assert (tmp_path / "newyork.json.gz").read_bytes() == b"new NY"
    assert (tmp_path / "skipped-westvirginia.json.gz").exists()
    assert (tmp_path / "refreshed.txt").read_text(encoding="utf-8").split() == [name(c) for c in done]
    assert not list(tmp_path.glob(".new-*"))


def test_a_page_off_limits_is_not_read(tmp_path, monkeypatch):
    fake_adapters(monkeypatch)
    asked = []

    def allowed(url):
        asked.append(url)
        return "robots.txt keeps ClaudeBot out" if "dps.mn.gov" in url else None

    done, failed = refresh_states.refresh(tmp_path, allowed=allowed)
    assert done == [c for c in CODES if c != "MN"] and "ClaudeBot" in failed["MN"]
    assert not (tmp_path / "minnesota.json.gz").exists()
    for code in CODES:  # every address an adapter reads is checked first
        module = importlib.import_module(f"grantmatch.{states.STATES[code]['module']}")
        for attr in refresh_states.ADDRESSES:
            if hasattr(module, attr):
                assert getattr(module, attr) in asked, (code, attr)


def test_the_exit_code_signals_a_failure_and_the_files_are_listed(tmp_path, monkeypatch, capsys):
    fake_adapters(monkeypatch, broken={"NY"})
    monkeypatch.setattr(refresh_states, "off_limits", lambda url: None)
    monkeypatch.setattr(sys, "argv", ["refresh_states", "--out", str(tmp_path)])
    with pytest.raises(SystemExit) as stop:
        refresh_states.main()
    assert stop.value.code == 1
    said = capsys.readouterr()
    assert "skipped-westvirginia.json.gz" in said.out and "newyork.json.gz" not in said.out and "NY:" in said.err

    fake_adapters(monkeypatch)
    refresh_states.main()  # no SystemExit when every state is written
    assert (tmp_path / "refreshed.txt").read_text(encoding="utf-8").split() == [name(c) for c in CODES]


def test_a_state_that_comes_back_with_no_calls_keeps_its_old_file(tmp_path, monkeypatch):
    """Renamed fields can drop every row: the adapter writes an empty file and returns 0."""
    (tmp_path / "westvirginia.json.gz").write_bytes(b"last week")
    (tmp_path / "skipped-westvirginia.json.gz").write_bytes(b"last skipped")
    fake_adapters(monkeypatch, empty={"WV"})
    done, failed = refresh_states.refresh(tmp_path, allowed=lambda url: None)
    assert "WV" not in done and "no open calls" in failed["WV"]
    assert (tmp_path / "westvirginia.json.gz").read_bytes() == b"last week"
    assert (tmp_path / "skipped-westvirginia.json.gz").read_bytes() == b"last skipped"
    assert "westvirginia" not in (tmp_path / "refreshed.txt").read_text(encoding="utf-8")


def proposed(which):
    return (ROOT / "docs" / "proposed-workflows" / f"{which}.yml.txt").read_text(encoding="utf-8")


def test_the_proposed_refresh_workflow_agrees_with_the_registry():
    text = proposed("refresh-states")
    assert text.startswith("name: Refresh state lists")  # deploy and enable steps know workflows by name and file
    assert re.search(r'^\s*- cron: "17 13 \* \* 1"', text, re.M)
    assert len(re.findall(r"^\s*runs-on:", text, re.M)) == 1  # one job
    assert "run: python -m grantmatch.refresh_states --out build\n" in text and "--states" not in text
    assert "for f in $(cat build/refreshed.txt)" in text  # what the driver wrote, so no state is named twice
    assert 'python -m grantmatch.embed programs "build/$f.json.gz" "build/$f.npz"' in text
    for part in ("build/$f.json.gz", "build/$f.npz", "build/skipped-$f.json.gz"):
        assert f'"{part}"' in text
    assert "gh release upload data-latest $(cat build/upload.txt) --clobber" in text
    assert text.count("if: ${{ !cancelled() }}") == 2  # embed and publish still run when one state failed
    assert "if [ ! -f build/refreshed.txt ]" in text and "if [ ! -s build/upload.txt ]" in text
    assert "refresh-states.yml/enable" in text
    # no state is spelled out, so the registry is the only list
    assert not [c for c in CODES if f"grantmatch.{states.STATES[c]['module']}" in text]


def test_the_proposed_skipped_report_takes_every_state_the_driver_runs():
    text = proposed("skipped-report")
    for code in refresh_states.weekly_states():
        f = name(code)
        assert f"-p 'skipped-{f}.json.gz'" in text, code
        assert f"-p {f}.json.gz" in text and f"--{f} build/{f}.json.gz" in text, code
        assert f in skipped.STATE_SOURCES
    live = (ROOT / ".github" / "workflows" / "skipped-report.yml").read_text(encoding="utf-8")
    kept = [line for line in live.splitlines() if line.strip() and "washington.json.gz ||" not in line]
    assert not [line for line in kept if line not in text.splitlines()]  # nothing the report does now is dropped
