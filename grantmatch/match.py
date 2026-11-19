"""Rank grant opportunities against a nonprofit's profile and explain each score."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

BUDGET_BANDS = {
    "Under $10k": 10_000,
    "$10k to $50k": 50_000,
    "$50k to $250k": 250_000,
    "$250k to $1M": 1_000_000,
    "Over $1M": 5_000_000,
}
# Band names saved in profiles before the small bands were split, mapped to the band that took their place.
OLD_BUDGET_BANDS = {"Under $50k": "$10k to $50k"}


def current_band(name):
    """The band a saved name means today, so profiles saved before a rename still load."""
    return OLD_BUDGET_BANDS.get(name, name)


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
# A title that names one state or territory is usually for groups there ("Centers for Independent Living - Guam").
STATE_NAMES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "CO": "Colorado",
    "CT": "Connecticut", "DC": "District of Columbia", "DE": "Delaware", "FL": "Florida", "GA": "Georgia", "HI": "Hawaii",
    "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana",
    "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey",
    "NM": "New Mexico", "NY": "New York", "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "PR": "Puerto Rico", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia",
    "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
}
# Washington alone is too often a person or the capital, so only "Washington State" counts.
PLACE_NAMES = sorted({*(v for k, v in STATE_NAMES.items() if k != "WA"), "Washington State", "Guam", "American Samoa",
                      "Virgin Islands", "Northern Mariana Islands", "Palau", "Micronesia", "Marshall Islands"},
                     key=lambda n: (-len(n), n))
PLACE = re.compile(r"\b(" + "|".join(re.escape(n) for n in PLACE_NAMES) + r")\b")
PLACE_PENALTY = 25


def other_places(title: str, state: str) -> list[str]:
    """States or territories a title names, when none of them is the profile's own state."""
    if not state:
        return []
    found = list(dict.fromkeys(PLACE.findall(title)))
    home = STATE_NAMES.get(state, "")
    home_names = {home, "Washington State"} if state == "WA" else {home}
    return [] if not found or home_names & set(found) else found


# Place names in a mission ("Manatee and Sarasota counties") pull the meaning model toward unrelated programs
# (Manatee Management & Care), so the text it reads swaps them for "the county". Location is scored elsewhere.
# A capitalized word that begins a sentence ("In", "Serving") is not part of the name.
_LEAD = r"(?!(?:In|We|Our|Serving|Across|Throughout|For|Of|At|To|From|With|Within|The|And)\b)"
_NAME = _LEAD + r"[A-Z][\w.'-]*(?:\s+" + _LEAD + r"[A-Z][\w.'-]*)*"
COUNTY_PHRASE = re.compile(_NAME + r"(?:\s*,\s*(?:and\s+|&\s+)?" + _NAME + r"|\s+(?:and|&)\s+" + _NAME + r")*"
                           r"\s+(?:County|Counties|county|counties|Parish|Parishes|parish|parishes)\b")


def query_text(mission: str, keywords: str, cities: str = "") -> str:
    """The text the meaning model reads: the mission and key words, with county and typed city names taken out."""
    text = COUNTY_PHRASE.sub("the county", mission)
    for city in sorted((c.strip() for c in cities.split(",") if len(c.strip()) >= 3), key=len, reverse=True):
        text = re.sub(r"\b" + re.escape(city) + r"\b", "", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip() + " " + keywords


RESEARCH_TITLE = re.compile(r"\b(research|investigators?|scientists?|fellowships?|clinical trials?)\b", re.I)
# Embedding similarity is judged against the mission's own baseline (its median over all grants):
# a grant this far above the median earns full mission points.
SEMANTIC_SPREAD = 0.14
# A word from the ages or populations choices counts this much of a typed word or a focus area word.
MINOR_WEIGHT = 0.5
# With a fiscal sponsor, a 501(c)(3) requirement is a step to arrange, not a wall.
SPONSOR_PENALTY = 10
# Organizations this young rarely win large federal awards, which ask for past performance.
YOUNG_YEARS = 3
YOUNG_AWARD = 100_000
YOUNG_CAUTION = "A large federal award for a new organization; most go to groups with a few years of results"


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
    fiscal_sponsor: bool = False  # can apply through a fiscal sponsor while 501(c)(3) status is pending or absent
    delivery: str = "in_person"  # "in_person", "online_state", "online_national"
    year_founded: int | None = None
    # Words from the ages and populations choices: they describe who is served, not the work, so they count half.
    minor_keywords: list[str] = field(default_factory=list)
    state: str = ""  # two-letter code; a grant whose title names only other states or territories loses points


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
        if kw in p.minor_keywords:
            weights[kw] *= MINOR_WEIGHT
    best3 = sum(sorted(weights.values(), reverse=True)[:3]) or 1.0

    budget = BUDGET_BANDS.get(current_band(p.budget_band), 250_000)
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
                if p.fiscal_sponsor:
                    points -= SPONSOR_PENALTY
                    cautions.append("Requires 501(c)(3) status; apply through your fiscal sponsor")
                else:
                    points -= 40
                    cautions.append("Requires 501(c)(3) status; apply once your IRS letter arrives, or through a fiscal sponsor"
                                    if p.has_501c3 == "Pending" else "Requires 501(c)(3) status; you would need a fiscal sponsor")
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

        ceiling = r["award_ceiling"] if r["award_ceiling"] and not pd.isna(r["award_ceiling"]) else 0
        biggest = max(floor or 0, ceiling)
        if p.year_founded and today.year - p.year_founded < YOUNG_YEARS and biggest >= YOUNG_AWARD:
            points -= 5
            cautions.append(YOUNG_CAUTION)

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
        places = other_places(r["title"], p.state)
        if places:
            points -= PLACE_PENALTY
            cautions.append("Appears limited to " + " and ".join(places))

        if r["status"] == "forecasted":
            due = f"estimated due {r['close']:%b %d, %Y}" if pd.notna(r["close"]) and r["close"] else "dates not set yet"
            reasons.append(f"Forecast, not open yet ({due}); time to prepare")
        elif r["days_left"] is not None and r["days_left"] < 30:
            cautions.append(f"Closes in {int(r['days_left'])} days")
        elif r["days_left"] is None:
            cautions.append("No close date listed; check the notice")

        final = max(0.0, min(100.0, points))
        shown = round(final)  # the tier follows the score people see, so "Score 35" is never a long shot
        tier = "Strong" if shown >= 60 else "Possible" if shown >= 35 else "Long shot"
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
