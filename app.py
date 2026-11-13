import gzip
import io
import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import streamlit as st

from grantmatch import embed
from grantmatch.match import BUDGET_BANDS, CATEGORY_NAMES, Profile, load_frame, score, to_ics

RELEASE = "https://github.com/RendellRich/grant-matcher/releases/download/data-latest/"
LOCAL_DIR = Path(__file__).parent / "data"
NOTICE = "This product uses the Grants.gov API but is not endorsed or certified by the U.S. Department of Health and Human Services."

PRESETS = {
    "Youth literacy and learning support": {
        "mission": "We provide free and sliding-scale structured literacy instruction for children with dyslexia, "
                   "speech and language support, academic tutoring, and coping-skills coaching for children with "
                   "ADHD and autism, so that cost is never a barrier for families.",
        "keywords": "literacy, reading, dyslexia, tutoring, speech, language, children, youth, students, ADHD, autism, disabilities, low-income families, after school",
        "categories": ["ED", "HL", "ISS"],
    },
    "Community food pantry": {
        "mission": "We run a volunteer food pantry and weekend meal program for families facing food insecurity in our county.",
        "keywords": "food insecurity, food bank, pantry, nutrition, hunger, meals, families, low-income, community",
        "categories": ["FN", "ISS", "CD"],
    },
    "Youth arts program": {
        "mission": "We offer free after-school music and visual arts classes for middle and high school students in under-served neighborhoods.",
        "keywords": "arts, music, art education, youth, students, after school, creative, under-served",
        "categories": ["AR", "ED", "HU"],
    },
    "Start blank": {"mission": "", "keywords": "", "categories": []},
}

st.set_page_config(page_title="Grant Matcher for small nonprofits", page_icon="📋", layout="wide")
st.markdown(
    """
    <style>
    .block-container {padding-top: 2rem; max-width: 1200px;}
    .badge {display:inline-block; padding:2px 10px; border-radius:999px; font-size:0.85rem; font-weight:600;}
    .Strong {background:#dff3e8; color:#14532d;}
    .Possible {background:#fff4d6; color:#713f12;}
    .Long {background:#eceff3; color:#334155;}
    .meta {color:#5b6472; font-size:0.9rem;}
    .notice {font-size:0.85rem; color:#5b6472; border-left:3px solid #2f6f5e; padding-left:10px; margin:6px 0 18px;}
    ul.why {list-style:none; padding-left:0; margin:6px 0 4px;}
    ul.why li {margin:0 0 4px; line-height:1.4;}
    ul.why li.good::before {content:"✓ "; color:#2f6f5e; font-weight:700;}
    ul.why li.warn::before {content:"⚠ "; color:#9a6700;}
    .tally {font-size:1.05rem; margin:4px 0 10px;}
    </style>
    """,
    unsafe_allow_html=True,
)


def _fetch(name: str) -> bytes | None:
    try:
        r = requests.get(RELEASE + name, timeout=30)
        if r.ok:
            return r.content
    except requests.RequestException:
        pass
    local = LOCAL_DIR / name
    return local.read_bytes() if local.exists() else None


@st.cache_data(ttl=6 * 3600, show_spinner="Loading the latest grant list")
def load_data() -> tuple[pd.DataFrame, str, dict]:
    raw = _fetch("opportunities.json.gz")
    if raw is None:
        return pd.DataFrame(), "", {}
    payload = json.loads(gzip.decompress(raw))
    vectors = {}
    emb = _fetch("embeddings.npz")
    if emb is not None:
        vectors = embed.load(io.BytesIO(emb))
    return load_frame(payload["opportunities"]), payload.get("fetched_at", ""), vectors


@st.cache_data(ttl=24 * 3600, show_spinner="Reading your mission")
def mission_similarity(text: str, _vectors: dict, version: str) -> dict:
    """Cosine similarity between the mission and every opportunity (vectors are pre-normalized)."""
    if not _vectors or not text.strip():
        return {}
    try:
        q = embed.embed_query(text)
    except Exception:
        return {}  # model unavailable; the matcher falls back to TF-IDF
    ids = list(_vectors)
    mat = np.stack([_vectors[i] for i in ids])
    return dict(zip(ids, (mat @ q).tolist()))


df, fetched_at, vectors = load_data()

st.title("Grant Matcher")
st.write("Federal grants a small nonprofit can realistically go after, ranked against your mission, with the reasons spelled out.")
st.markdown(f"<div class='notice'>{NOTICE}</div>", unsafe_allow_html=True)

if df.empty:
    st.error("The grant list could not be loaded right now. Try again in a few minutes.")
    st.stop()

# ---------- profile ----------
with st.sidebar:
    st.header("Your organization")
    uploaded = st.file_uploader("Load a saved profile", type="json", help="A profile you downloaded from this page earlier.")
    saved = json.load(uploaded) if uploaded else None

    preset_name = st.selectbox("Start from an example", list(PRESETS), disabled=saved is not None)
    base = saved or PRESETS[preset_name]

    mission = st.text_area("Mission and programs", base.get("mission", ""), height=170,
                           help="Two or three sentences on who you serve and what you do. This drives the ranking.")
    keywords = st.text_area("Key words", base.get("keywords", ""), height=90,
                            help="Comma separated. Words a matching grant would likely use.")
    has_501c3 = st.radio("501(c)(3) status", ["Yes", "Pending", "No"],
                         index=["Yes", "Pending", "No"].index(base.get("has_501c3", "Yes")), horizontal=True)
    budget_band = st.selectbox("Annual budget", list(BUDGET_BANDS),
                               index=list(BUDGET_BANDS).index(base.get("budget_band", "$50k to $250k")))
    can_cost_share = st.checkbox("We can provide matching funds", value=base.get("can_cost_share", False))
    categories = st.multiselect("Funding categories (optional)", list(CATEGORY_NAMES),
                                default=base.get("categories", []), format_func=lambda c: CATEGORY_NAMES[c])
    include_forecasted = st.checkbox("Include forecasts (not open yet)", value=base.get("include_forecasted", True))
    min_days = st.slider("Hide deadlines sooner than (days)", 0, 60, base.get("min_days_left", 14))

    profile_dict = {
        "mission": mission, "keywords": keywords, "has_501c3": has_501c3, "budget_band": budget_band,
        "can_cost_share": can_cost_share, "categories": categories,
        "include_forecasted": include_forecasted, "min_days_left": min_days,
    }
    st.download_button("Save this profile", json.dumps(profile_dict, indent=2), "grant-profile.json", "application/json")

if not mission.strip() and not keywords.strip():
    st.info("Add your mission and a few key words in the panel on the left to see matches.")
    st.stop()

profile = Profile(
    mission=mission,
    keywords=[k.strip() for k in keywords.split(",") if k.strip()],
    has_501c3=has_501c3,
    budget_band=budget_band,
    can_cost_share=can_cost_share,
    categories=categories,
    include_forecasted=include_forecasted,
    min_days_left=min_days,
)
semantic = mission_similarity(mission + " " + keywords, vectors, fetched_at)
results = score(df, profile, semantic=semantic)

updated = ""
if fetched_at:
    updated = datetime.fromisoformat(fetched_at).strftime("%b %d, %Y")
st.caption(f"{len(df):,} open and forecasted federal opportunities that list nonprofits as eligible"
           + (f", updated {updated}." if updated else "."))

tab_matches, tab_table, tab_ready = st.tabs(["Matches", "Table and downloads", "Before you apply"])

with tab_matches:
    counts = results["tier"].value_counts()
    n_strong, n_possible, n_long = (int(counts.get(t, 0)) for t in ("Strong", "Possible", "Long shot"))
    st.markdown(
        f"<div class='tally'><b>{n_strong}</b> strong, <b>{n_possible}</b> possible, "
        f"<b>{n_long:,}</b> long shots</div>", unsafe_allow_html=True)
    if n_strong == 0:
        st.info(
            "No strong federal matches right now. That is common for small direct-service nonprofits: much federal "
            "money for local programs is passed through state agencies, and foundations fund more early-stage work. "
            "The possible matches below are still worth a read, and the Before you apply tab has next steps.")
    with st.expander("How the score works"):
        st.markdown(
            "- Up to 70 points for how closely the grant's description matches your mission, compared with "
            "how your mission matches grants in general\n"
            "- Up to 30 points for your key words, with rare words like *dyslexia* worth more than common ones like *children*\n"
            "- Points off for research grants, cost sharing you can't provide, award sizes far above your budget, "
            "a 501(c)(3) requirement you don't meet, and programs aimed at tribes, states, or embassies abroad\n"
            "- Strong is 60 and up, possible is 35 to 59")

    show = st.radio("Show", ["Strong and possible", "All"], horizontal=True, label_visibility="collapsed")
    view = results if show == "All" else results[results["tier"] != "Long shot"]
    if view.empty:
        st.write("No strong or possible matches with these settings. Try more key words, fewer categories, or a shorter deadline window.")
    for _, r in view.head(40).iterrows():
        due = r["close"].strftime("%b %d, %Y") if pd.notna(r["close"]) and r["close"] else "not listed"
        due_label = "Est. due" if r["status"] == "forecasted" else "Due"
        tier_class = r["tier"].split()[0]
        with st.container(border=True):
            st.markdown(
                f"<span class='badge {tier_class}'>{r['tier']} · {r['score']}</span>&nbsp; "
                f"**[{r['title']}]({r['url']})**", unsafe_allow_html=True)
            st.markdown(
                f"<div class='meta'>{r['agency']} &nbsp;|&nbsp; {r['number']} &nbsp;|&nbsp; {due_label} {due}"
                f" &nbsp;|&nbsp; Award {r['award_range']}</div>", unsafe_allow_html=True)
            items = "".join(f"<li class='good'>{x}</li>" for x in r["reasons"])
            items += "".join(f"<li class='warn'>{x}</li>" for x in r["cautions"])
            st.markdown(f"<ul class='why'>{items}</ul>", unsafe_allow_html=True)
            with st.expander("Summary"):
                st.write(r["description"][:1500] + ("..." if len(r["description"]) > 1500 else ""))
                if r["eligibility_text"]:
                    st.markdown("**Eligibility notes:** " + r["eligibility_text"][:800])

with tab_table:
    table = results[["score", "tier", "title", "agency", "status", "close", "award_range", "url"]].rename(columns={
        "score": "Score", "tier": "Fit", "title": "Opportunity", "agency": "Agency", "status": "Status",
        "close": "Due", "award_range": "Awards", "url": "Link"})
    st.dataframe(table, hide_index=True, use_container_width=True,
                 column_config={"Link": st.column_config.LinkColumn("Link", display_text="Open")})
    picks = results[results["tier"] != "Long shot"]
    export = picks.assign(reasons=picks["reasons"].apply("; ".join), cautions=picks["cautions"].apply("; ".join))
    export = export[["score", "tier", "title", "agency", "number", "status", "close_date", "award_floor",
                     "award_ceiling", "cost_sharing", "reasons", "cautions", "url"]]
    buf = io.StringIO()
    export.to_csv(buf, index=False)
    d1, d2 = st.columns(2)
    d1.download_button("Download strong and possible (CSV)", buf.getvalue(), "grant-matches.csv", "text/csv")
    d2.download_button("Add deadlines to your calendar (.ics)", to_ics(picks), "grant-deadlines.ics", "text/calendar")

with tab_ready:
    st.subheader("What a federal application needs")
    st.markdown(
        """
Federal grants ask for a few registrations before you can submit. Several take weeks, so start them before you find the perfect grant.

1. **SAM.gov registration and a Unique Entity ID (UEI).** Free. Every federal applicant needs it, and it has to be renewed every year. Start at [sam.gov](https://sam.gov).
2. **A Grants.gov applicant account** linked to your organization, with someone set up to submit. See [Grants.gov applicant registration](https://www.grants.gov/applicants/applicant-registration).
3. **Your IRS determination letter** showing 501(c)(3) status, if the grant requires it.
4. **A simple organizational budget** and, for larger grants, financial statements or an audit.
5. **Your board list, mission, and a short program description** with the people you serve and the results you track.

**Tips for a young nonprofit**
- Federal funding often flows through your state. Many education and family programs are re-granted by state agencies, so check your state's grant portal too.
- Ask for an amount that fits your budget. A first award that is a fraction of the ceiling is normal.
- Forecasts are the best time to start. They give you weeks or months to line up partners and letters of support.
- Private foundations and local community foundations are often a better first step than federal grants. This tool covers federal grants only for now.
        """
    )

st.markdown("---")
st.markdown(
    f"<div class='meta'>{NOTICE} Data from the Grants.gov API, refreshed nightly. "
    "Scores are a starting point for your own review, not a guarantee of eligibility. "
    "Source code: <a href='https://github.com/RendellRich/grant-matcher'>github.com/RendellRich/grant-matcher</a></div>",
    unsafe_allow_html=True,
)
