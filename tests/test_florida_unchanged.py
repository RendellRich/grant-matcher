"""Florida's records and scores stay exactly as they were before the state registry (grantmatch/states.py).

tests/fixtures/florida-baseline.json.gz was made from `python -m grantmatch.export_web <dir> --local --golden
<dir>/golden.json` run on main before the registry existed: a hash of the Florida records the export wrote, the
example missions' similarity to each record (from that export's vectors), and every parity profile's Florida
scores, reasons and cautions. This rebuilds Florida's records with today's export code from the same data/ files
and scores them with today's scorer. No network and no model are needed.

One change was made on purpose and approved (2026-11-25): seven county programs (NEW below) were added to the end of
local-FL.json. They are the only difference allowed: the file without them must hash as it did, every record that was
there must be identical, and scoring with the new records present must give every existing record the same score,
reasons, cautions and order.

When Florida's inputs change on purpose (the weekly catalog, a hand-kept entry in local-FL.json, a review
decision), the hashes below no longer match and the test skips; it guards code changes, not data changes.
"""
import gzip
import hashlib
import json
from datetime import date
from pathlib import Path

import pytest

from grantmatch import export_web
from grantmatch.match import Profile
from grantmatch.rank_more import score_florida
from grantmatch.terms import expand_keywords, minor_keywords

FIXTURE = Path(__file__).parent / "fixtures" / "florida-baseline.json.gz"
DATA = export_web.LOCAL
# The seven programs added to data/local-FL.json after the baseline was made.
NEW = ["local-miami-dade-community-grants", "local-miami-dade-cultural-advancement",
       "local-miami-dade-cultural-development", "local-miami-dade-developing-arts", "local-miami-dade-festivals-events",
       "local-miami-dade-hannibal-cox", "local-broward-csc-sponsorships"]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def input_sha(name: str) -> str:
    """A data file's hash, with text files' line endings as git stores them, so Windows and CI agree."""
    raw = (DATA / name).read_bytes()
    if name.endswith(".gz"):
        return sha(raw)
    raw = raw.replace(b"\r\n", b"\n")
    return sha(without_new(raw) if name == "local-FL.json" else raw)


def without_new(raw: bytes) -> bytes:
    """local-FL.json with the block of added entries cut off the end of its list, byte for byte as it was."""
    start = raw.find(b',\n    {\n      "slug": "' + NEW[0].removeprefix("local-").encode() + b'"')
    return raw if start < 0 else raw[:start] + b"\n  ]\n}\n"


@pytest.fixture(scope="module")
def baseline():
    fx = json.loads(gzip.decompress(FIXTURE.read_bytes()))
    changed = [n for n, h in fx["inputs"].items() if input_sha(n) != h]
    if changed:
        pytest.skip(f"Florida's inputs changed since the baseline ({', '.join(changed)}); this guards code, not data")
    return fx


@pytest.fixture(scope="module")
def records(baseline):
    export_web.LOCAL_ONLY = True   # as --local does: no website check results from the release
    try:
        payload = json.loads(gzip.decompress((DATA / "florida.json.gz").read_bytes()))
        recs, _ = export_web.florida_records(payload)
    finally:
        export_web.LOCAL_ONLY = False
    return recs


def test_the_baseline_still_guards_the_hand_kept_file(baseline):
    """The block of new entries is all that was added: without it local-FL.json is the file the baseline was made from
    (otherwise the fixture above skips, so this names the check that must not go quiet)."""
    assert input_sha("local-FL.json") == baseline["inputs"]["local-FL.json"]
    entries = json.loads((DATA / "local-FL.json").read_text(encoding="utf-8"))["programs"]
    assert [f"local-{e['slug']}" for e in entries[-len(NEW):]] == NEW


def test_existing_florida_records_are_identical_and_only_the_seven_are_new(baseline, records):
    old = [r for r in records if r["id"] not in NEW]
    assert [r["id"] for r in old] == baseline["ids"]
    assert [r["id"] for r in records] == baseline["ids"] + NEW  # added at the end, nothing else added or moved
    assert sha(json.dumps(old, sort_keys=True, ensure_ascii=False).encode("utf-8")) == baseline["records_sha256"]


def test_florida_scores_reasons_and_cautions_are_identical_for_every_parity_profile(baseline, records):
    today = date.fromisoformat(baseline["today"])
    assert len(baseline["cases"]) == 18
    for case in baseline["cases"]:
        s = case["spec"]
        typed = [k.strip() for k in s["keywords"].split(",") if k.strip()]
        keywords = expand_keywords(typed, s["focus_areas"], s["ages"], s["populations"])
        minor = minor_keywords(typed, s["focus_areas"], s["ages"], s["populations"])
        assert keywords == s["expanded_keywords"] and minor == s["minor_keywords"], case["name"]
        p = Profile(mission=s["mission"], keywords=keywords, has_501c3=s["has_501c3"], budget_band=s["budget_band"],
                    can_cost_share=s["can_cost_share"], categories=s["categories"],
                    include_forecasted=s["include_forecasted"], min_days_left=s["min_days_left"], today=today,
                    fiscal_sponsor=s["fiscal_sponsor"], delivery=s["delivery"], year_founded=s["year_founded"],
                    minor_keywords=minor, state=s["state"])
        sims = dict(zip(baseline["ids"], baseline["sims"][case["example"]]))
        sims.update({i: 0.99 for i in NEW})  # a close match for each new record must still move nothing else
        cities = [c for c in s["cities"].split(",") if c.strip()]
        df = score_florida(records, p, sims, s["show_earmarks"], cities)
        got = [{"id": str(r["id"]), "score": int(r["score"]), "tier": r["tier"], "reasons": list(r["reasons"]),
                "cautions": list(r["cautions"])} for _, r in df.iterrows() if r["id"] not in NEW]
        assert got == case["florida"], case["name"]
