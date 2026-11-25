"""Florida's records and scores stay exactly as they were before the state registry (grantmatch/states.py).

tests/fixtures/florida-baseline.json.gz was made from `python -m grantmatch.export_web <dir> --local --golden
<dir>/golden.json` run on main before the registry existed: a hash of the Florida records the export wrote, the
example missions' similarity to each record (from that export's vectors), and every parity profile's Florida
scores, reasons and cautions. This rebuilds Florida's records with today's export code from the same data/ files
and scores them with today's scorer. No network and no model are needed.

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


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def input_sha(name: str) -> str:
    """A data file's hash, with text files' line endings as git stores them, so Windows and CI agree."""
    raw = (DATA / name).read_bytes()
    return sha(raw if name.endswith(".gz") else raw.replace(b"\r\n", b"\n"))


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


def test_florida_records_are_identical(baseline, records):
    assert [r["id"] for r in records] == baseline["ids"]
    assert sha(json.dumps(records, sort_keys=True, ensure_ascii=False).encode("utf-8")) == baseline["records_sha256"]


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
        cities = [c for c in s["cities"].split(",") if c.strip()]
        df = score_florida(records, p, sims, s["show_earmarks"], cities)
        got = [{"id": str(r["id"]), "score": int(r["score"]), "tier": r["tier"], "reasons": list(r["reasons"]),
                "cautions": list(r["cautions"])} for _, r in df.iterrows()]
        assert got == case["florida"], case["name"]
