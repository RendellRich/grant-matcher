"""Scoring for private foundations (IRS 990-PF) and Florida state programs (CSFA)."""
from __future__ import annotations

import re
from statistics import median

import pandas as pd

from .match import BUDGET_BANDS, MINOR_WEIGHT, SEMANTIC_SPREAD, current_band, Profile, _keyword_hits, _money

NO_UNSOLICITED = re.compile(
    r"(no|not accept\w*|does not (accept|consider)|do not (accept|consider)) unsolicited|unsolicited (requests|applications|proposals) (are )?not"
    r"|by invitation only|invitation only|only to pre-?selected|preselected", re.I)
SCHOLARSHIP = re.compile(r"\bscholarships?\b|\btuition\b|\bstudent aid\b", re.I)
SCHOLARSHIP_SHARE = 0.6  # share of a foundation's listed grants that are scholarships before it counts as a scholarship fund
SCHOLARSHIP_PENALTY = 40  # enough to take a scholarship fund out of the strong tier
# A foundation's own words, in its how-to-apply section, asking for 501(c)(3) status or the IRS letter that proves it.
ASKS_501C3 = re.compile(r"501\s*\(?\s*c\s*\)?\s*\(?\s*3|tax[- ]exempt|determination letter|public charit|509\s*\(?\s*a", re.I)
ASKS_501C3_PENALTY = {"Pending": 10, "No": 20}
ASKS_501C3_CAUTION = {
    "Pending": "Asks for proof of 501(c)(3) status; apply once your IRS letter arrives, or through a fiscal sponsor",
    "No": "Asks for proof of 501(c)(3) status; you would need a fiscal sponsor",
}
ASKS_501C3_SPONSOR = "Asks for proof of 501(c)(3) status; apply through your fiscal sponsor"
NATIONAL_STATES = 5  # a funder whose latest grants reached this many states gives nationally
COMPETITIVE = re.compile(r"\b(competitive|request for (applications|proposals)|rfa|rfp|solicitation|notice of funding|scored|review panel)\b", re.I)


def _scale(semantic: dict[str, float] | None, ids: pd.Series, yardstick: dict[str, float] | None = None) -> pd.Series:
    """Embedding similarity above this source's median, scaled to 0..1. The median comes from the yardstick
    records when given (Florida's state programs, so hand-entered county programs never move it)."""
    if not semantic:
        return pd.Series(0.5, index=ids.index)
    vals = ids.map(semantic)
    base = float(median([v for v in (yardstick or semantic).values()]))
    return ((vals.fillna(base) - base) / SEMANTIC_SPREAD).clip(0, 1)


def _keyword_weights(keywords: list[str], texts: pd.Series, minor=()) -> tuple[dict[str, float], float]:
    lower = texts.str.lower()
    weights = {}
    for kw in keywords:
        share = lower.apply(lambda t, k=kw: bool(_keyword_hits([k], t))).mean() if len(lower) else 0
        weights[kw] = 1.0 - min(0.85, share * 8)
        if kw in minor:
            weights[kw] *= MINOR_WEIGHT
    best3 = sum(sorted(weights.values(), reverse=True)[:3]) or 1.0
    return weights, best3


def _tier(points: float) -> str:
    """Callers pass the rounded score, so the tier always agrees with the score on the card."""
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
    weights, best3 = _keyword_weights(p.keywords, df["purpose_text"], p.minor_keywords)
    fit = _scale(semantic, df["ein"])
    budget = BUDGET_BANDS.get(current_band(p.budget_band), 250_000)
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
        # A group serving people online across the country can reach a funder that gives in many states.
        reach = sum(1 for v in r["recipient_states"].values() if v)
        national = p.delivery == "online_national" and reach >= NATIONAL_STATES
        if share >= 0.5:
            points += 20
            reasons.append(f"Its only grant went to a {state} organization" if n == 1 else f"{in_state} of its {n} grants went to {state} organizations")
        elif share >= 0.2:
            points += 12
            reasons.append(f"Its only grant went to a {state} organization" if n == 1 else f"{in_state} of its {n} grants went to {state} organizations")
        elif in_state:
            points -= 0 if national else 15 if share < 0.1 and r["state"] != state else 5
            cautions.append(f"Only {in_state} of its {n} grants went to {state}")
        elif r["state"] == state:
            points += 6
        elif national:
            points -= 5
            cautions.append(f"No grants to {state} in its latest return, but it gives in {reach} states")
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
        apply_text = " ".join(v for v in (apply or {}).values() if isinstance(v, str))
        if p.has_501c3 in ASKS_501C3_PENALTY and ASKS_501C3.search(apply_text):
            if p.fiscal_sponsor:
                cautions.append(ASKS_501C3_SPONSOR)
            else:
                points -= ASKS_501C3_PENALTY[p.has_501c3]
                cautions.append(ASKS_501C3_CAUTION[p.has_501c3])
        # Scholarship funds pay students (or a college on a student's behalf), so a nonprofit cannot apply.
        # Judge by what its grants were for: most of the listed grants, or a purpose list made of scholarships.
        samples = r["sample_grants"]
        scholar = sum(1 for g in samples if SCHOLARSHIP.search(g["purpose"]))
        purposes = " ".join(r["top_purposes"][:10])
        if (samples and scholar / len(samples) >= SCHOLARSHIP_SHARE) or len(SCHOLARSHIP.findall(purposes)) >= 3:
            points -= SCHOLARSHIP_PENALTY
            cautions.append("Mostly scholarships paid to students, not grants to organizations")

        if n < 3:
            points = min(points, 55)  # too little history to call it a strong match
        final = max(0.0, min(100.0, points))
        rows.append({**r.drop(labels=["purpose_text"]).to_dict(), "score": round(final), "tier": _tier(round(final)),
                     "reasons": reasons, "cautions": cautions, "matched": matched, "in_state": in_state})
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    # Equal scores are common once the meaning points top out, so the closer meaning comes first among them.
    out["_sim"] = out["ein"].map(semantic or {}).fillna(0.0)
    return (out.sort_values(["score", "_sim", "grant_count"], ascending=[False, False, False])
               .drop(columns="_sim").reset_index(drop=True))


# ---------------- Florida programs ----------------

def florida_doc(rec: dict) -> str:
    return f"{rec['title']}. {rec['agency']}. {rec['objectives']} {rec.get('subjects', '')}"


# County and city programs (grantmatch/local.py) serve named counties and may need 501(c)(3) status.
REQUIRES_501C3_CAUTION = {
    "Pending": "Requires 501(c)(3) status; apply once your IRS letter arrives",
    "No": "Requires 501(c)(3) status",
}
REQUIRES_501C3_SPONSOR = "Requires 501(c)(3) status; ask whether you can apply through your fiscal sponsor"


def local_checks(r: dict, p: Profile, city_set: set[str]) -> tuple[int, list[str], list[str]]:
    """Points, reasons and cautions for a county or city program; nothing for a state program."""
    places = r.get("places")
    if not isinstance(places, list) or not places:
        return 0, [], []
    points, reasons, cautions = 0, [], []
    area = r.get("area") or "its county"
    if city_set & set(places):
        reasons.append(f"Funds work in {area}, where you work")
    elif city_set:
        points -= 40
        cautions.append(f"Only for work in {area}")
    else:
        points -= 10
        cautions.append(f"Only for work in {area}; add your cities to check")
    if r.get("requires_501c3") is True and p.has_501c3 in ASKS_501C3_PENALTY:
        if p.fiscal_sponsor:
            cautions.append(REQUIRES_501C3_SPONSOR)
        else:
            points -= ASKS_501C3_PENALTY[p.has_501c3]
            cautions.append(REQUIRES_501C3_CAUTION[p.has_501c3])
    return points, reasons, cautions


# Open calls (grantmatch/california.py) say what a catalog of programs doesn't: a required match, loans, and
# how the money is paid.
LOAN_CAUTION = "A loan, not a grant"
REIMBURSED_CAUTION = "Pays by reimbursement: you spend first and are paid back"


def call_checks(r: dict, p: Profile) -> tuple[int, list[str]]:
    """Points and cautions for an open call's own facts; nothing for a catalog program."""
    points, cautions = 0, []
    match = r.get("match")
    if isinstance(match, str) and match and not p.can_cost_share:
        points -= 20
        cautions.append(f"Requires matching funds ({match})")
    if r.get("loan") is True:
        points -= 25
        cautions.append(LOAN_CAUTION)
    method = r.get("funding_method")
    if isinstance(method, str) and method.startswith("Reimbursement"):
        cautions.append(REIMBURSED_CAUTION)
    return points, cautions


def score_florida(records: list[dict], p: Profile, semantic: dict[str, float] | None = None,
                  show_earmarks: bool = False, cities: list[str] | tuple = ()) -> pd.DataFrame:
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
    # Word rarity and the similarity median are measured on the state programs only, so adding or editing a
    # hand-entered county program (grantmatch/local.py) never changes a state program's score.
    state = ~df["id"].astype(str).str.startswith("local-")
    weights, best3 = _keyword_weights(p.keywords, text[state] if state.any() else text, p.minor_keywords)
    yardstick = {k: v for k, v in semantic.items() if not str(k).startswith("local-")} if semantic else None
    fit = _scale(semantic, df["id"], yardstick or None)
    city_set = {c.strip().lower() for c in cities if c.strip()}
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
        extra, more_reasons, more_cautions = local_checks(r.to_dict(), p, city_set)
        points += extra
        reasons += more_reasons
        cautions += more_cautions
        extra, more_cautions = call_checks(r.to_dict(), p)
        points += extra
        cautions += more_cautions
        final = max(0.0, min(100.0, points))
        rows.append({**r.to_dict(), "score": round(final), "tier": _tier(round(final)),
                     "reasons": reasons, "cautions": cautions, "matched": matched})
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out["_sim"] = out["id"].map(semantic or {}).fillna(0.0)
    return out.sort_values(["score", "_sim"], ascending=[False, False]).drop(columns="_sim").reset_index(drop=True)
