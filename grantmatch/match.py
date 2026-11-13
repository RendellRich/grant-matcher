"""Rank grant opportunities against a nonprofit's profile and explain each score."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

BUDGET_BANDS = {
    "Under $50k": 50_000,
    "$50k to $250k": 250_000,
    "$250k to $1M": 1_000_000,
    "Over $1M": 5_000_000,
}
CATEGORY_NAMES = {
    "AG": "Agriculture", "AR": "Arts", "BC": "Business and commerce", "CD": "Community development",
    "CP": "Consumer protection", "DPR": "Disaster prevention and relief", "ED": "Education",
    "ELT": "Employment, labor and training", "EN": "Energy", "ENV": "Environment",
    "FN": "Food and nutrition", "HL": "Health", "HO": "Housing", "HU": "Humanities",
    "ISS": "Income security and social services", "IS": "Information and statistics",
    "LJL": "Law, justice and legal services", "NR": "Natural resources", "O": "Other",
    "RD": "Regional development", "RT": "Recreation and tourism",
    "ST": "Science, technology and research", "T": "Transportation",
}
RESEARCH_NUMBER = re.compile(r"^(RFA|PAR|PA|NOT)-", re.I)
# Grants that list nonprofits as eligible but are really aimed at someone else.
TARGETED = [
    (re.compile(r"\b(tribal|tribes|native american|indian health|alaska native)\b", re.I),
     "Appears limited to tribal organizations or tribal communities", 25),
    (re.compile(r"\b(state awards|state agencies|state arts agencies|states and territories|state and local governments)\b", re.I),
     "Appears aimed at state agencies", 20),
    (re.compile(r"\b(embassy|consulate|public diplomacy|mission \w+ public affairs)\b", re.I),
     "Run by a U.S. embassy for programs abroad", 25),
    (re.compile(r"\bindemnity\b", re.I),
     "Insurance for museum exhibitions, not a cash grant", 35),
]
RESEARCH_TITLE = re.compile(r"\b(research|investigators?|scientists?|fellowships?|clinical trials?)\b", re.I)
# Embedding similarity is judged against the mission's own baseline (its median over all grants):
# a grant this far above the median earns full mission points.
SEMANTIC_SPREAD = 0.14


@dataclass
class Profile:
    mission: str
    keywords: list[str] = field(default_factory=list)
    has_501c3: str = "Yes"  # "Yes", "Pending", "No"
    budget_band: str = "$50k to $250k"
    can_cost_share: bool = False
    categories: list[str] = field(default_factory=list)  # empty = all
    include_forecasted: bool = True
    min_days_left: int = 14
    today: date | None = None


def load_frame(records: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(records)
    close = pd.to_datetime(df["close_date"], errors="coerce")
    # Some notices use far-future placeholder dates (2099-01-01) to mean "rolling".
    close = close.where(close < pd.Timestamp.now() + pd.DateOffset(years=4))
    df["close"] = close.dt.date
    df["doc"] = (
        (df["title"] + ". ") * 2
        + df["category_labels"].apply(" ".join) + ". "
        + df["description"] + " " + df["eligibility_text"]
    )
    return df


def _keyword_hits(keywords: list[str], text: str) -> list[str]:
    text = text.lower()
    hits = []
    for kw in keywords:
        k = kw.strip().lower()
        if not k:
            continue
        stem = k[:-1] if k.endswith("s") and len(k) > 4 else k
        if re.search(r"\b" + re.escape(stem), text):
            hits.append(kw.strip())
    return hits


def _money(n: float | None) -> str:
    if n is None or pd.isna(n) or not n:
        return "not listed"
    if n >= 1_000_000:
        return f"${n / 1_000_000:.1f}M".replace(".0M", "M")
    if n >= 1_000:
        return f"${n / 1_000:.0f}k"
    return f"${n:,.0f}"


def _award_range(floor, ceiling) -> str:
    has_ceiling = ceiling is not None and not pd.isna(ceiling) and ceiling > 0
    if floor and has_ceiling and abs(floor - ceiling) < 1:
        return _money(ceiling)
    if floor and has_ceiling:
        return f"{_money(floor)} to {_money(ceiling)}"
    if has_ceiling:
        return f"up to {_money(ceiling)}"
    if floor:
        return f"from {_money(floor)}"
    return "amount not listed"


def score(df: pd.DataFrame, p: Profile, semantic: dict[str, float] | None = None) -> pd.DataFrame:
    """Rank opportunities. `semantic` maps opportunity id to embedding cosine similarity with the
    mission; without it, a TF-IDF similarity relative to the best match is used instead."""
    today = p.today or date.today()
    work = df.copy()

    if not p.include_forecasted:
        work = work[work["status"] == "posted"]
    if p.categories:
        work = work[work["categories"].apply(lambda cats: bool(set(cats) & set(p.categories)))]
    days_left = work["close"].apply(lambda d: (d - today).days if pd.notna(d) and d else None)
    work = work.assign(days_left=days_left)
    open_enough = work["days_left"].isna() | (work["days_left"] >= p.min_days_left)
    work = work[open_enough]
    if work.empty:
        return work.assign(score=[], tier=[], reasons=[], cautions=[], matched=[])

    if semantic:
        baseline = float(pd.Series(list(semantic.values())).median())
        raw = work["id"].map(semantic).fillna(baseline).to_numpy()
        sims = ((raw - baseline) / SEMANTIC_SPREAD).clip(0, 1)
    else:
        query = p.mission + " " + " ".join(p.keywords * 2)
        vec = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), min_df=1, sublinear_tf=True)
        matrix = vec.fit_transform(list(work["doc"]) + [query])
        tfidf = cosine_similarity(matrix[-1], matrix[:-1]).ravel()
        sims = tfidf / (tfidf.max() or 1.0)

    # Rare, specific words (dyslexia) count for more than common ones (children).
    texts = (work["title"] + " " + work["description"]).str.lower()
    weights = {}
    for kw in p.keywords:
        share = texts.apply(lambda t, k=kw: bool(_keyword_hits([k], t))).mean()
        weights[kw] = 1.0 - min(0.85, share * 8)  # a word in 10%+ of grants keeps only 15% weight
    best3 = sum(sorted(weights.values(), reverse=True)[:3]) or 1.0

    budget = BUDGET_BANDS.get(p.budget_band, 250_000)
    rows = []
    for sim, (_, r) in zip(sims, work.iterrows()):
        matched = _keyword_hits(p.keywords, r["title"] + " " + r["description"])
        coverage = min(1.0, sum(weights.get(m, 0.15) for m in matched) / best3)
        points = 100 * (0.70 * sim + 0.30 * coverage)
        reasons, cautions = [], []

        if matched:
            reasons.append("Mentions " + ", ".join(matched[:5]))
        cats = [CATEGORY_NAMES.get(c, c) for c in r["categories"]]
        if p.categories and set(r["categories"]) & set(p.categories):
            reasons.append("In your categories: " + ", ".join(cats))

        types = set(r["applicant_types"])
        if p.has_501c3 == "Yes":
            if "12" in types or "99" in types:
                reasons.append("Open to 501(c)(3) nonprofits")
            else:
                points -= 5
                cautions.append("Eligibility is \"other\"; read the eligibility notes")
        else:
            if "13" in types or "99" in types:
                reasons.append("Open to nonprofits without 501(c)(3) status")
            elif "12" in types and not types & {"13", "25", "99"}:
                points -= 40
                cautions.append("Requires 501(c)(3) status")
            else:
                points -= 5
                cautions.append("Eligibility is \"other\"; read the eligibility notes")

        if r["cost_sharing"] and not p.can_cost_share:
            points -= 20
            cautions.append("Requires cost sharing or matching funds")

        floor = r["award_floor"] if r["award_floor"] and r["award_floor"] > 1_000 else None
        size_ref = floor or r["award_ceiling"]
        if floor and floor > 3 * budget:
            points -= 15
            cautions.append(f"Smallest award ({_money(floor)}) is large for your budget; funders usually want a track record at that size")
        elif r["award_ceiling"] and r["award_ceiling"] > 10 * budget and not floor:
            points -= 5
            cautions.append(f"Awards go up to {_money(r['award_ceiling'])}; ask for an amount that fits your budget")

        nih = RESEARCH_NUMBER.match(r["number"] or "") and str(r["agency_code"]).startswith("HHS-NIH")
        if nih or RESEARCH_TITLE.search(r["title"]) or str(r["agency_code"]) == "NSF":
            points -= 35
            cautions.append("Research grant; usually needs a research team and institution")
        elif "ST" in r["categories"] and len(r["categories"]) == 1:
            points -= 8
            cautions.append("Research and development funding")

        for pattern, note, penalty in TARGETED:
            if pattern.search(r["title"]):
                points -= penalty
                cautions.append(note)
                break

        if r["status"] == "forecasted":
            due = f"estimated due {r['close']:%b %d, %Y}" if pd.notna(r["close"]) and r["close"] else "dates not set yet"
            reasons.append(f"Forecast, not open yet ({due}); time to prepare")
        elif r["days_left"] is not None and r["days_left"] < 30:
            cautions.append(f"Closes in {int(r['days_left'])} days")
        elif r["days_left"] is None:
            cautions.append("No close date listed; check the notice")

        final = max(0.0, min(100.0, points))
        tier = "Strong" if final >= 60 else "Possible" if final >= 35 else "Long shot"
        rows.append({
            "score": round(final),
            "tier": tier,
            "reasons": reasons,
            "cautions": cautions,
            "matched": matched,
            "award_range": _award_range(floor, r["award_ceiling"]),
            "size_ref": size_ref,
        })
    out = pd.concat([work.reset_index(drop=True), pd.DataFrame(rows)], axis=1)
    return out.sort_values(["score", "days_left"], ascending=[False, True]).reset_index(drop=True)


def to_ics(rows: pd.DataFrame) -> str:
    """Calendar file with one all-day event per deadline."""
    stamp = date.today().strftime("%Y%m%d")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//grant-matcher//EN", "CALSCALE:GREGORIAN"]
    for _, r in rows.iterrows():
        if not (pd.notna(r["close"]) and r["close"]):
            continue
        d = r["close"].strftime("%Y%m%d")
        label = "Est. due" if r["status"] == "forecasted" else "Due"
        title = re.sub(r"[,;\\]", " ", f"{label}: {r['title']}")[:150]
        lines += [
            "BEGIN:VEVENT",
            f"UID:grant-{r['id']}@grant-matcher",
            f"DTSTAMP:{stamp}T000000Z",
            f"DTSTART;VALUE=DATE:{d}",
            f"SUMMARY:{title}",
            f"DESCRIPTION:{r['agency']} {r['number']} {r['url']}",
            f"URL:{r['url']}",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
