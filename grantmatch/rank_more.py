"""Scoring for private foundations (IRS 990-PF) and Florida state programs (CSFA)."""
from __future__ import annotations

import re
from statistics import median

import pandas as pd

from .match import BUDGET_BANDS, SEMANTIC_SPREAD, Profile, _keyword_hits, _money

NO_UNSOLICITED = re.compile(
    r"(no|not accept\w*|does not (accept|consider)|do not (accept|consider)) unsolicited|unsolicited (requests|applications|proposals) (are )?not"
    r"|by invitation only|invitation only|only to pre-?selected|preselected", re.I)
SCHOLARSHIP = re.compile(r"\bscholarships?\b|\btuition\b|\bstudent aid\b", re.I)
COMPETITIVE = re.compile(r"\b(competitive|request for (applications|proposals)|rfa|rfp|solicitation|notice of funding|scored|review panel)\b", re.I)


def _scale(semantic: dict[str, float] | None, ids: pd.Series) -> pd.Series:
    """Embedding similarity above this source's median, scaled to 0..1."""
    if not semantic:
        return pd.Series(0.5, index=ids.index)
    vals = ids.map(semantic)
    base = float(median([v for v in semantic.values()])) if semantic else 0.0
    return ((vals.fillna(base) - base) / SEMANTIC_SPREAD).clip(0, 1)


def _keyword_weights(keywords: list[str], texts: pd.Series) -> tuple[dict[str, float], float]:
    lower = texts.str.lower()
    weights = {}
    for kw in keywords:
        share = lower.apply(lambda t, k=kw: bool(_keyword_hits([k], t))).mean() if len(lower) else 0
        weights[kw] = 1.0 - min(0.85, share * 8)
    best3 = sum(sorted(weights.values(), reverse=True)[:3]) or 1.0
    return weights, best3


def _tier(points: float) -> str:
    return "Strong" if points >= 60 else "Possible" if points >= 35 else "Long shot"


# ---------------- foundations ----------------

def foundation_doc(rec: dict) -> str:
    restr = (rec.get("apply") or {}).get("restrictions", "")
    text = f"{rec['name']}. {rec.get('mission', '')} Grants for: " + "; ".join(rec.get("top_purposes", [])[:20]) + f". {restr}"
    if rec.get("top_recipients"):
        text += " Grantees: " + "; ".join(rec["top_recipients"][:40])
    return text


def score_foundations(records: list[dict], p: Profile, state: str, cities: list[str],
                      semantic: dict[str, float] | None = None, show_preselected: bool = False) -> pd.DataFrame:
    if not records:
        return pd.DataFrame()
    df = pd.DataFrame(records)
    if "kind" not in df:
        df["kind"] = "Private foundation"
    df["kind"] = df["kind"].fillna("Private foundation")
    if "top_recipients" not in df:
        df["top_recipients"] = [[] for _ in range(len(df))]
    df["top_recipients"] = df["top_recipients"].apply(lambda v: v if isinstance(v, list) else [])
    df["purpose_text"] = df.apply(
        lambda r: " ".join(r["top_purposes"]) + " " + " ".join(g["purpose"] for g in r["sample_grants"])
        + " " + " ".join(r["top_recipients"]), axis=1)
    weights, best3 = _keyword_weights(p.keywords, df["purpose_text"])
    fit = _scale(semantic, df["ein"])
    budget = BUDGET_BANDS.get(p.budget_band, 250_000)
    city_set = {c.strip().lower() for c in cities if c.strip()}

    rows = []
    for i, r in df.iterrows():
        apply = r.get("apply") if isinstance(r.get("apply"), dict) else {}
        restrictions = (apply or {}).get("restrictions", "")
        reasons, cautions = [], []
        matched = _keyword_hits(p.keywords, r["purpose_text"])
        coverage = min(1.0, sum(weights.get(m, 0.15) for m in matched) / best3)
        points = 60 * fit.loc[i] + 15 * coverage
        if matched:
            reasons.append("Past grants mention " + ", ".join(matched[:5]))

        n = r["grant_count"] or 0
        in_state = r["recipient_states"].get(state, 0)
        share = in_state / n if n else 0
        if share >= 0.5:
            points += 20
            reasons.append(f"{in_state} of its {n} grants went to {state} organizations")
        elif share >= 0.2:
            points += 12
            reasons.append(f"{in_state} of its {n} grants went to {state} organizations")
        elif in_state:
            points -= 15 if share < 0.1 and r["state"] != state else 5
            cautions.append(f"Only {in_state} of its {n} grants went to {state}")
        elif r["state"] == state:
            points += 6
        else:
            points -= 20
            cautions.append(f"No grants to {state} in its latest return")
        public = r["kind"] != "Private foundation"
        if r["kind"] == "Community foundation" and r["state"] != state:
            points -= 25
            cautions.append(f"Serves a community outside {state}; its grants here are usually from donors' own funds")
        if str(r["city"]).lower() in city_set and r["state"] == state:
            points += 5
            reasons.append(f"Based in {r['city'].title()}, one of your cities")
        if n < 3:
            points -= 20
            cautions.append(f"Made only {n} grant{'s' if n != 1 else ''} last year, so its interests are hard to read")
        local = [g for g in r["sample_grants"] if g["city"].lower() in city_set and g["state"] == state]
        if local:
            points += 10 if len(local) >= 3 else 5
            names = sorted({g["city"].title() for g in local})
            reasons.append(f"Funded {len(local)} group{'s' if len(local) > 1 else ''} in {', '.join(names)}")
        serves_you = r["state"] == state and (str(r["city"]).lower() in city_set or len(local) >= 3)
        if r["kind"] == "Community foundation" and serves_you:
            points += 15
            reasons.insert(0, "A community foundation serving your area; these often run grant cycles for local nonprofits")

        med = r["grant_median"]
        if med and med > budget:
            points -= 10
            cautions.append(f"Typical grant ({_money(med)}) is large next to your budget")
        elif med and med < 1000:
            cautions.append(f"Mostly small gifts (typical {_money(med)})")
        elif med:
            reasons.append(f"Typical grant {_money(med)}")

        if public and isinstance(r.get("website"), str) and r.get("website"):
            reasons.append("Check its website for open grant cycles")
        if r["preselected_only"]:
            if not show_preselected:
                continue
            points -= 25
            cautions.append("Says it only funds preselected organizations; an introduction letter may still be read")
        if NO_UNSOLICITED.search(restrictions):
            points -= 30
            cautions.append("Says it does not accept unsolicited requests")
        if apply and (apply.get("materials") or apply.get("contact")):
            reasons.append("Publishes how to apply")
        purposes = " ".join(r["top_purposes"][:10])
        if SCHOLARSHIP.search(purposes) and len(SCHOLARSHIP.findall(purposes)) >= 3:
            points -= 15
            cautions.append("Mostly scholarships for individuals")

        if n < 3:
            points = min(points, 55)  # too little history to call it a strong match
        final = max(0.0, min(100.0, points))
        rows.append({**r.drop(labels=["purpose_text"]).to_dict(), "score": round(final), "tier": _tier(final),
                     "reasons": reasons, "cautions": cautions, "matched": matched, "in_state": in_state})
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.sort_values(["score", "grant_count"], ascending=[False, False]).reset_index(drop=True)


# ---------------- Florida programs ----------------

def florida_doc(rec: dict) -> str:
    return f"{rec['title']}. {rec['agency']}. {rec['objectives']} {rec.get('subjects', '')}"


def score_florida(records: list[dict], p: Profile, semantic: dict[str, float] | None = None,
                  show_earmarks: bool = False) -> pd.DataFrame:
    if not records:
        return pd.DataFrame()
    df = pd.DataFrame(records)
    df = df[df["nonprofit_eligible"]]
    if not show_earmarks:
        df = df[~df["earmark"]]
    if df.empty:
        return df
    df = df.reset_index(drop=True)
    text = df["title"] + " " + df["objectives"] + " " + df["subjects"]
    weights, best3 = _keyword_weights(p.keywords, text)
    fit = _scale(semantic, df["id"])
    rows = []
    for i, r in df.iterrows():
        matched = _keyword_hits(p.keywords, text.loc[i])
        coverage = min(1.0, sum(weights.get(m, 0.15) for m in matched) / best3)
        points = 75 * fit.loc[i] + 25 * coverage
        reasons = ["Open to nonprofits"]
        cautions = []
        if matched:
            reasons.insert(0, "Mentions " + ", ".join(matched[:5]))
        if COMPETITIVE.search(r["award"] + " " + r["application"]):
            reasons.append("Awarded through a competitive application")
        if SCHOLARSHIP.search(r["title"]) or re.search(r"\bstudent (assistance|aid) grant|tuition", r["title"], re.I):
            points -= 25
            cautions.append("Student aid paid to individuals or schools, not to nonprofits")
        if r["earmark"]:
            points -= 40
            cautions.append("Set aside by the Legislature for a named organization")
        final = max(0.0, min(100.0, points))
        rows.append({**r.to_dict(), "score": round(final), "tier": _tier(final),
                     "reasons": reasons, "cautions": cautions, "matched": matched})
    return pd.DataFrame(rows).sort_values("score", ascending=False).reset_index(drop=True)
