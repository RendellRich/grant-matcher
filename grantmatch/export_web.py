"""Write the data the static site reads: records as JSON and embeddings as raw float16 rows.

The site in web/ scores in the browser, so it needs the same records and vectors the Streamlit app
loads. Sources are the data-latest release assets, falling back to the snapshot in data/.

Run:
  python -m grantmatch.export_web web/public/data
"""
from __future__ import annotations

import gzip
import io
import json
import argparse
import re
from datetime import date
from pathlib import Path

import numpy as np
import requests

from . import embed
from .display import assistance_label, bracket_caps, format_address, present, shouting, tidy_name, tidy_text

RELEASE = "https://github.com/RendellRich/grant-matcher/releases/download/data-latest/"
LOCAL = Path(__file__).resolve().parent.parent / "data"

# The examples on the page are scored before any model download, from vectors made here with the same
# model and text the browser would use (mission, a space, then the key words).
EXAMPLES = {
    "literacy": {
        "label": "Youth literacy and learning support",
        "mission": "We provide free and sliding-scale structured literacy instruction for children with dyslexia, "
                   "speech and language support, academic tutoring, and coping-skills coaching for children with "
                   "ADHD and autism, so that cost is never a barrier for families.",
        "keywords": "literacy, reading, dyslexia, tutoring, speech, language, children, youth, students, ADHD, autism, "
                    "disabilities, low-income families, after school",
        "categories": ["ED", "HL", "ISS"], "state": "FL", "cities": "Tampa, Bradenton, Sarasota, St. Petersburg",
    },
    "food": {
        "label": "Community food pantry",
        "mission": "We run a volunteer food pantry and weekend meal program for families facing food insecurity in our county.",
        "keywords": "food insecurity, food bank, pantry, nutrition, hunger, meals, families, low-income, community",
        "categories": ["FN", "ISS", "CD"], "state": "FL", "cities": "",
    },
    "arts": {
        "label": "Youth arts program",
        "mission": "We offer free after-school music and visual arts classes for middle and high school students in under-served neighborhoods.",
        "keywords": "arts, music, art education, youth, students, after school, creative, under-served",
        "categories": ["AR", "ED", "HU"], "state": "FL", "cities": "",
    },
}


LOCAL_ONLY = False


def fetch(name: str, local: str | None = None) -> bytes | None:
    if LOCAL_ONLY:
        path = LOCAL / (local or name)
        return path.read_bytes() if path.exists() else None
    try:
        r = requests.get(RELEASE + name, timeout=60)
        if r.ok:
            return r.content
    except requests.RequestException:
        pass
    path = LOCAL / (local or name)
    return path.read_bytes() if path.exists() else None


def vectors(raw: bytes | None) -> tuple[list[str], np.ndarray]:
    if not raw:
        return [], np.zeros((0, 384), dtype=np.float16)
    data = np.load(io.BytesIO(raw), allow_pickle=False)
    return [str(i) for i in data["ids"].tolist()], data["vecs"].astype(np.float16)


def tidy_foundation(rec: dict) -> dict:
    """Display copies of the raw IRS text, made by grantmatch.display so the site and the app agree.
    Fields starting with _ are for display only; scoring reads the raw fields."""
    apply = rec.get("apply") if isinstance(rec.get("apply"), dict) else {}
    rec["_name"] = tidy_name(rec.get("name"))
    rec["_city"] = tidy_name(rec.get("city"), "city")
    rec["_city_title"] = str(rec.get("city")).title()  # the scorer's own wording ("Based in Tampa")
    rec["_mission"] = tidy_text(rec.get("mission"))
    rec["_apply"] = {
        "contact": tidy_name(apply.get("contact")), "phone": present(apply.get("phone") or rec.get("phone")),
        "email": present(apply.get("email")).lower(), "address": format_address(apply.get("address"), rec.get("city", "")),
        "materials": tidy_text(apply.get("materials")), "deadlines": tidy_text(apply.get("deadlines")),
        "restrictions": tidy_text(apply.get("restrictions")),
    }
    for g in rec.get("sample_grants") or []:
        if isinstance(g, dict):
            g["_to"], g["_city"] = tidy_name(g.get("to")), tidy_name(g.get("city"), "city")
            g["_city_title"] = str(g.get("city", "")).title()
            g["_purpose"] = tidy_text(g.get("purpose"))
    site = present(rec.get("website"))
    rec["_site"] = (site.lower() if shouting(site) else site) if site and " " not in site.strip() and "." in site else ""
    return rec


BROKEN_APOSTROPHE = re.compile(r"(?<=\w)[\ufffd\u00bf](?=s\b)")


def fix_title(text: str) -> str:
    """Display only: some source titles carry U+FFFD or an inverted question mark where an apostrophe was."""
    return BROKEN_APOSTROPHE.sub("\u2019", text or "")


def tidy_program(rec: dict) -> dict:
    rec["_title"] = fix_title(bracket_caps(rec.get("title")))
    rec["_assist"] = assistance_label(rec.get("assistance"))
    return rec


def write(out: Path, name: str, payload: dict, ids: list[str], vecs: np.ndarray) -> None:
    payload = {**payload, "vec_ids": ids, "dim": int(vecs.shape[1]) if len(ids) else 384}
    (out / f"{name}.json").write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    (out / f"{name}.f16").write_bytes(np.ascontiguousarray(vecs, dtype="<f2").tobytes())
    print(f"{name}: {len(payload.get('records', []))} records, {len(ids)} vectors")


def main() -> None:
    global LOCAL_ONLY
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("out", type=Path)
    ap.add_argument("--local", action="store_true", help="read only the snapshot in data/, not the release")
    ap.add_argument("--golden", type=Path, help="also write Python's scores for the parity test to this file")
    args = ap.parse_args()
    LOCAL_ONLY = args.local
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    meta: dict = {"states": []}

    raw = fetch("opportunities.json.gz")
    if raw:
        payload = json.loads(gzip.decompress(raw))
        ids, vecs = vectors(fetch("embeddings.npz"))
        write(out, "federal", {"fetched_at": payload.get("fetched_at", ""), "records": [{**r, "_title": fix_title(r.get("title"))} for r in payload["opportunities"]]}, ids, vecs)
        meta["federal"] = payload.get("fetched_at", "")

    raw = fetch("florida.json.gz")
    if raw:
        payload = json.loads(gzip.decompress(raw))
        ids, vecs = vectors(fetch("florida.npz"))
        write(out, "florida", {"fetched_at": payload.get("fetched_at", ""), "fiscal_year": payload.get("fiscal_year", ""),
                               "records": [tidy_program(r) for r in payload["programs"]]}, ids, vecs)
        meta["florida"] = payload.get("fiscal_year", "")

    # Foundations: private (990-PF) and community/public (Schedule I), one file per state.
    states = sorted({p.name.split(".")[0] for d in ("foundations", "community") for p in (LOCAL / d).glob("*.json.gz")})
    for state in states:
        records, all_ids, all_vecs, stamp = [], [], [], ""
        for prefix in ("foundations", "community"):
            raw = fetch(f"{prefix}-{state}.json.gz", f"{prefix}/{state}.json.gz")
            if not raw:
                continue
            payload = json.loads(gzip.decompress(raw))
            for rec in payload["foundations"]:
                rec.setdefault("kind", "Private foundation")
                tidy_foundation(rec)
            records += payload["foundations"]
            stamp = stamp or payload.get("fetched_at", "")
            ids, vecs = vectors(fetch(f"{prefix}-{state}.npz", f"{prefix}/{state}.npz"))
            all_ids += ids
            all_vecs.append(vecs)
        if records:
            # Later files win for a repeated EIN, as dict.update does in the Streamlit app.
            index = {e: i for i, e in enumerate(all_ids)}
            stacked = np.concatenate(all_vecs) if all_vecs else np.zeros((0, 384), dtype=np.float16)
            keep = sorted(index.values())
            write(out, f"foundations-{state}", {"fetched_at": stamp, "state": state, "records": records},
                  [all_ids[i] for i in keep], stacked[keep])
            meta["states"].append(state)

    examples = {}
    for key, ex in EXAMPLES.items():
        vec = embed.embed_query(ex["mission"] + " " + ex["keywords"])
        examples[key] = {**ex, "vector": [round(float(x), 6) for x in vec]}
    (out / "examples.json").write_text(json.dumps(examples, separators=(",", ":")), encoding="utf-8")
    (out / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    print("meta:", meta)
    if args.golden:
        golden(out, examples, args.golden)


# Profiles the parity test runs through both scorers: each example as it is, then the same missions
# with the other eligibility answers and filters, so every branch of the rules is reached.
VARIANTS = [
    {},
    {"has_501c3": "No", "budget_band": "Under $10k"},
    {"has_501c3": "Pending", "can_cost_share": True, "budget_band": "Over $1M", "include_forecasted": False,
     "min_days_left": 30, "show_preselected": True, "show_earmarks": True, "categories": []},
    {"budget_band": "Under $50k"},  # a band name from before the split, read as $10k to $50k
]
GOLDEN_DAY = date(2026, 11, 14)


def golden(out: Path, examples: dict, path: Path) -> None:
    import pandas as pd

    from .match import Profile, load_frame, score
    from .rank_more import score_florida, score_foundations

    def load(name):
        payload = json.loads((out / f"{name}.json").read_text(encoding="utf-8"))
        vecs = np.frombuffer((out / f"{name}.f16").read_bytes(), dtype="<f2").reshape(-1, payload["dim"]).astype(np.float32)
        return payload["records"], payload["vec_ids"], vecs

    def sims(ids, vecs, q):
        return dict(zip(ids, (vecs @ q).tolist()))

    def rows(df, key):
        if df is None or len(df) == 0:
            return []
        return [{"id": str(r[key]), "score": int(r["score"]), "tier": r["tier"], "reasons": list(r["reasons"]),
                 "cautions": list(r["cautions"])} for _, r in df.iterrows()]

    fed, fed_ids, fed_v = load("federal")
    fl, fl_ids, fl_v = load("florida")
    fdn, fdn_ids, fdn_v = load("foundations-FL")
    frame = load_frame(fed)
    cases = []
    for key, ex in examples.items():
        q = np.array(ex["vector"], dtype=np.float32)
        for n, v in enumerate(VARIANTS):
            spec = {"has_501c3": "Yes", "budget_band": "$50k to $250k", "can_cost_share": False,
                    "include_forecasted": True, "min_days_left": 14, "show_preselected": False, "show_earmarks": False,
                    "categories": ex["categories"], "keywords": ex["keywords"], "mission": ex["mission"],
                    "cities": ex["cities"], "state": ex["state"], **v}
            p = Profile(mission=spec["mission"], keywords=[k.strip() for k in spec["keywords"].split(",") if k.strip()],
                        has_501c3=spec["has_501c3"], budget_band=spec["budget_band"], can_cost_share=spec["can_cost_share"],
                        categories=spec["categories"], include_forecasted=spec["include_forecasted"],
                        min_days_left=spec["min_days_left"], today=GOLDEN_DAY)
            cities = [c for c in spec["cities"].split(",") if c.strip()]
            cases.append({
                "name": f"{key}-{n}", "example": key, "spec": spec,
                "federal": rows(score(frame, p, semantic=sims(fed_ids, fed_v, q)), "id"),
                "foundations": rows(score_foundations(fdn, p, "FL", cities, sims(fdn_ids, fdn_v, q),
                                                      spec["show_preselected"]), "ein"),
                "florida": rows(score_florida(fl, p, sims(fl_ids, fl_v, q), spec["show_earmarks"]), "id"),
            })
    path.write_text(json.dumps({"today": GOLDEN_DAY.isoformat(), "cases": cases}), encoding="utf-8")
    print(f"golden: {len(cases)} cases to {path}")


if __name__ == "__main__":
    main()
