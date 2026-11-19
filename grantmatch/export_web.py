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
from . import corporate
from . import local as local_programs
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


def foundation_states() -> list[str]:
    """The states with foundation files: the release's list when there is one, else the snapshot in data/."""
    local = {p.name.split(".")[0] for d in ("foundations", "community") for p in (LOCAL / d).glob("*.json.gz")}
    raw = None if LOCAL_ONLY else fetch("states.json")
    try:
        listed = set(json.loads(raw)) if raw else set()
    except ValueError:
        listed = set()
    return sorted(listed | local)


def website_cycles() -> dict[str, dict]:
    """What each foundation's website said at the last weekly check (grantmatch.cycles), by EIN, with the
    check's date as "at". Display only: scores never read it. Sites that said nothing or couldn't be
    reached are left out."""
    raw = None if LOCAL_ONLY else fetch("cycles.json.gz")
    if not raw:
        return {}
    try:
        payload = json.loads(gzip.decompress(raw))
    except (OSError, ValueError):
        return {}
    at = str(payload.get("checked_at", ""))[:10]
    return {ein: {**r, "at": at} for ein, r in (payload.get("sites") or {}).items()
            if isinstance(r, dict) and r.get("s") in ("open", "deadline", "closed", "apply")}


def national_programs(corp: dict[str, dict], cycles: dict[str, dict]) -> dict[str, tuple[dict, np.ndarray]]:
    """The record and vector of each company foundation with a national program (grantmatch/corporate.py),
    read from its home state's files, so it can be shown in every state the program serves."""
    out: dict[str, tuple[dict, np.ndarray]] = {}
    for home in sorted({e["home"] for e in corp.values() if e.get("serves")}):
        for prefix in ("foundations", "community"):
            raw = fetch(f"{prefix}-{home}.json.gz", f"{prefix}/{home}.json.gz")
            if not raw:
                continue
            wanted = {ein for ein, e in corp.items() if e.get("serves") and e["home"] == home}
            found = [r for r in json.loads(gzip.decompress(raw))["foundations"] if str(r.get("ein")) in wanted]
            if not found:
                continue
            ids, vecs = vectors(fetch(f"{prefix}-{home}.npz", f"{prefix}/{home}.npz"))
            row = {e: i for i, e in enumerate(ids)}
            for rec in found:
                ein = str(rec["ein"])
                if ein not in row:
                    continue
                rec.setdefault("kind", "Private foundation" if prefix == "foundations" else rec.get("kind"))
                tidy_foundation(rec)
                if cycles.get(ein):
                    rec["_cycle"] = cycles[ein]
                rec["_corp"] = corporate.overlay(corp[ein])
                out[ein] = (rec, vecs[row[ein]])
    return out


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


# States besides Florida with their own adapter: the data file's name, where it comes from, and the label
# the site puts before each call's number.
STATE_PROGRAMS = {
    "CA": {"file": "california", "source": "California Grants Portal", "catalog": "Grants Portal"},
}


def program_vectors(records: list[dict], raw: bytes | None) -> tuple[list[str], np.ndarray]:
    """Vectors for every record, in record order. The published vectors are used where they exist; a record
    without one (the vectors file is missing, or older than the records) is embedded here."""
    from .rank_more import florida_doc
    have: dict[str, np.ndarray] = {}
    if raw:
        ids, vecs = vectors(raw)
        have = dict(zip(ids, vecs))
    missing = [r for r in records if r["id"] not in have]
    if missing:
        new = embed.embed_texts([florida_doc(r)[:2000] for r in missing]).astype(np.float16)
        have.update(zip((r["id"] for r in missing), new))
    ids = [r["id"] for r in records]
    stacked = np.stack([have[i] for i in ids]).astype(np.float16) if ids else np.zeros((0, 384), dtype=np.float16)
    return ids, stacked


def write(out: Path, name: str, payload: dict, ids: list[str], vecs: np.ndarray) -> None:
    payload = {**payload, "vec_ids": ids, "dim": int(vecs.shape[1]) if len(ids) else 384}
    # Stored gzipped: with every state's foundations the plain JSON would pass GitHub Pages' 1 GB limit.
    # The browser unpacks it (data.ts); mtime=0 keeps the bytes the same when the data hasn't changed.
    text = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    (out / f"{name}.json.gz").write_bytes(gzip.compress(text, compresslevel=9, mtime=0))
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
        records = [tidy_program(r) for r in payload["programs"]]
        # County and city programs entered by hand (grantmatch/local.py) join the state's, embedded here.
        extra = local_programs.load(fiscal_year=payload.get("fiscal_year", ""))
        if extra:
            from .rank_more import florida_doc
            sites = website_cycles()
            for r in extra:
                tidy_program(r)
                if sites.get(r["id"]):
                    r["_cycle"] = sites[r["id"]]
            records += extra
            ids = ids + [r["id"] for r in extra]
            vecs = np.concatenate([vecs, embed.embed_texts([florida_doc(r) for r in extra]).astype(np.float16)])
        write(out, "florida", {"fetched_at": payload.get("fetched_at", ""), "fiscal_year": payload.get("fiscal_year", ""),
                               "records": records}, ids, vecs)
        meta["florida"] = payload.get("fiscal_year", "")

    # Other states' programs (STATE_PROGRAMS), one file each; the site's state tab follows the profile's state.
    for state, spec in STATE_PROGRAMS.items():
        raw = fetch(f"{spec['file']}.json.gz")
        if not raw:
            continue
        payload = json.loads(gzip.decompress(raw))
        records = [tidy_program(r) for r in payload["programs"]]
        for r in records:
            r["_catalog"] = f"{spec['catalog']} {r.get('number', '')}".strip()
            r["_assist"] = (r.get("assistance") or "").replace("; ", " or ")
        ids, vecs = program_vectors(records, fetch(f"{spec['file']}.npz"))
        write(out, f"programs-{state}", {"fetched_at": payload.get("fetched_at", ""), "state": state, "records": records}, ids, vecs)
        meta.setdefault("programs", {})[state] = {"file": f"programs-{state}", "source": spec["source"],
                                                  "updated": payload.get("fetched_at", "")}

    # Foundations: private (990-PF) and community/public (Schedule I), one file per state.
    states = foundation_states()
    cycles = website_cycles()
    corp = corporate.load()
    extra = national_programs(corp, cycles)
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
                found = cycles.get(str(rec.get("ein")))
                if found:
                    rec["_cycle"] = found
                if str(rec.get("ein")) in corp:
                    rec["_corp"] = corporate.overlay(corp[str(rec.get("ein"))])
            records += payload["foundations"]
            stamp = stamp or payload.get("fetched_at", "")
            ids, vecs = vectors(fetch(f"{prefix}-{state}.npz", f"{prefix}/{state}.npz"))
            all_ids += ids
            all_vecs.append(vecs)
        if records and extra:
            corporate.add_national(state, records, all_ids, all_vecs, extra, corp)
        if records:
            # Later files win for a repeated EIN, as dict.update does in the Streamlit app.
            index = {e: i for i, e in enumerate(all_ids)}
            stacked = np.concatenate(all_vecs) if all_vecs else np.zeros((0, 384), dtype=np.float16)
            keep = sorted(index.values())
            write(out, f"foundations-{state}", {"fetched_at": stamp, "state": state, "records": records},
                  [all_ids[i] for i in keep], stacked[keep])
            meta["states"].append(state)

    # How much of each state's registered foundations the files hold (grantmatch/coverage.py).
    raw = fetch("coverage.json")
    if raw:
        (out / "coverage.json").write_bytes(raw)
        meta["coverage"] = True

    examples = {}
    for key, ex in EXAMPLES.items():
        vec = embed.embed_query(ex["mission"] + " " + ex["keywords"])
        examples[key] = {**ex, "vector": [round(float(x), 6) for x in vec]}
    (out / "examples.json").write_text(json.dumps(examples, separators=(",", ":")), encoding="utf-8")
    # Each state's counties and their places, so "Manatee" also finds Bradenton (grantmatch/counties.py).
    counties_file = LOCAL / "counties.json.gz"
    if counties_file.exists():
        for state, counties in json.loads(gzip.decompress(counties_file.read_bytes())).items():
            (out / f"counties-{state}.json").write_text(json.dumps(counties, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    (out / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    total = sum(p.stat().st_size for p in out.iterdir() if p.is_file())
    print(f"data folder: {total / 1e6:.0f} MB")
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
    # The expanded profile: checkbox groups turned into key words, a fiscal sponsor, online nationwide, a new group.
    {"has_501c3": "Pending", "fiscal_sponsor": True, "delivery": "online_national", "year_founded": 2026,
     "budget_band": "Under $10k", "focus_areas": ["literacy", "dyslexia", "speech", "tutoring", "adhd_autism", "social_emotional", "special_ed"],
     "ages": ["k5", "g6_8", "g9_12", "families"], "populations": ["low_income", "disabilities"]},
    {"has_501c3": "No", "fiscal_sponsor": True, "delivery": "online_state", "year_founded": 2024, "categories": []},
]
GOLDEN_DAY = date(2026, 11, 14)


def golden(out: Path, examples: dict, path: Path) -> None:
    import pandas as pd

    from .match import Profile, load_frame, score
    from .rank_more import score_florida, score_foundations
    from .terms import expand_keywords, minor_keywords

    def load(name):
        payload = json.loads(gzip.decompress((out / f"{name}.json.gz").read_bytes()))
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
    ca = load("programs-CA") if (out / "programs-CA.json.gz").exists() else None
    cases = []
    for key, ex in examples.items():
        q = np.array(ex["vector"], dtype=np.float32)
        for n, v in enumerate(VARIANTS):
            spec = {"has_501c3": "Yes", "budget_band": "$50k to $250k", "can_cost_share": False,
                    "include_forecasted": True, "min_days_left": 14, "show_preselected": False, "show_earmarks": False,
                    "categories": ex["categories"], "keywords": ex["keywords"], "mission": ex["mission"],
                    "cities": ex["cities"], "state": ex["state"], "fiscal_sponsor": False, "delivery": "in_person",
                    "year_founded": None, "focus_areas": [], "ages": [], "populations": [], **v}
            typed = [k.strip() for k in spec["keywords"].split(",") if k.strip()]
            spec["expanded_keywords"] = expand_keywords(typed, spec["focus_areas"], spec["ages"], spec["populations"])
            spec["minor_keywords"] = minor_keywords(typed, spec["focus_areas"], spec["ages"], spec["populations"])
            p = Profile(mission=spec["mission"], keywords=spec["expanded_keywords"],
                        has_501c3=spec["has_501c3"], budget_band=spec["budget_band"], can_cost_share=spec["can_cost_share"],
                        categories=spec["categories"], include_forecasted=spec["include_forecasted"],
                        min_days_left=spec["min_days_left"], today=GOLDEN_DAY, fiscal_sponsor=spec["fiscal_sponsor"],
                        delivery=spec["delivery"], year_founded=spec["year_founded"], minor_keywords=spec["minor_keywords"])
            cities = [c for c in spec["cities"].split(",") if c.strip()]
            cases.append({
                "name": f"{key}-{n}", "example": key, "spec": spec,
                "federal": rows(score(frame, p, semantic=sims(fed_ids, fed_v, q)), "id"),
                "foundations": rows(score_foundations(fdn, p, "FL", cities, sims(fdn_ids, fdn_v, q),
                                                      spec["show_preselected"]), "ein"),
                "florida": rows(score_florida(fl, p, sims(fl_ids, fl_v, q), spec["show_earmarks"], cities), "id"),
                # Another state's open calls through the same scorer: matching funds, loans and reimbursement.
                "california": rows(score_florida(ca[0], p, sims(ca[1], ca[2], q), False, cities), "id") if ca else [],
            })
    path.write_text(json.dumps({"today": GOLDEN_DAY.isoformat(), "cases": cases}), encoding="utf-8")
    print(f"golden: {len(cases)} cases to {path}")


if __name__ == "__main__":
    main()
