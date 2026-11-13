import gzip
import html
import io
import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import streamlit as st

from grantmatch import embed
from grantmatch.match import BUDGET_BANDS, CATEGORY_NAMES, Profile, _money, load_frame, score, to_ics
from grantmatch.rank_more import score_florida, score_foundations

RELEASE = "https://github.com/RendellRich/grant-matcher/releases/download/data-latest/"
LOCAL_DIR = Path(__file__).parent / "data"
NOTICE = "This product uses the Grants.gov API but is not endorsed or certified by the U.S. Department of Health and Human Services."
STATES = ["AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DC", "DE", "FL", "GA", "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA",
          "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR",
          "PA", "PR", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY"]

PRESETS = {
    "Youth literacy and learning support": {
        "mission": "We provide free and sliding-scale structured literacy instruction for children with dyslexia, "
                   "speech and language support, academic tutoring, and coping-skills coaching for children with "
                   "ADHD and autism, so that cost is never a barrier for families.",
        "keywords": "literacy, reading, dyslexia, tutoring, speech, language, children, youth, students, ADHD, autism, disabilities, low-income families, after school",
        "categories": ["ED", "HL", "ISS"],
        "state": "FL", "cities": "Tampa, Bradenton, Parrish, Sarasota, St. Petersburg",
    },
    "Community food pantry": {
        "mission": "We run a volunteer food pantry and weekend meal program for families facing food insecurity in our county.",
        "keywords": "food insecurity, food bank, pantry, nutrition, hunger, meals, families, low-income, community",
        "categories": ["FN", "ISS", "CD"],
        "state": "FL", "cities": "",
    },
    "Youth arts program": {
        "mission": "We offer free after-school music and visual arts classes for middle and high school students in under-served neighborhoods.",
        "keywords": "arts, music, art education, youth, students, after school, creative, under-served",
        "categories": ["AR", "ED", "HU"],
        "state": "FL", "cities": "",
    },
    "Start blank": {"mission": "", "keywords": "", "categories": [], "state": "FL", "cities": ""},
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


# ---------- data ----------
def _fetch(name: str, local: str | None = None) -> bytes | None:
    try:
        r = requests.get(RELEASE + name, timeout=30)
        if r.ok:
            return r.content
    except requests.RequestException:
        pass
    path = LOCAL_DIR / (local or name)
    return path.read_bytes() if path.exists() else None


def _vectors(name: str, local: str | None = None) -> dict:
    raw = _fetch(name, local)
    return embed.load(io.BytesIO(raw)) if raw else {}


@st.cache_data(ttl=6 * 3600, show_spinner="Loading federal grants")
def load_federal():
    raw = _fetch("opportunities.json.gz")
    if raw is None:
        return pd.DataFrame(), "", {}
    payload = json.loads(gzip.decompress(raw))
    return load_frame(payload["opportunities"]), payload.get("fetched_at", ""), _vectors("embeddings.npz")


@st.cache_data(ttl=24 * 3600, show_spinner="Loading foundations")
def load_foundations(state: str):
    raw = _fetch(f"foundations-{state}.json.gz", f"foundations/{state}.json.gz")
    if raw is None:
        return [], "", {}
    payload = json.loads(gzip.decompress(raw))
    vecs = _vectors(f"foundations-{state}.npz", f"foundations/{state}.npz")
    return payload["foundations"], payload.get("fetched_at", ""), vecs


@st.cache_data(ttl=24 * 3600, show_spinner="Loading Florida programs")
def load_florida():
    raw = _fetch("florida.json.gz")
    if raw is None:
        return [], "", {}
    payload = json.loads(gzip.decompress(raw))
    return payload["programs"], payload.get("fiscal_year", ""), _vectors("florida.npz")


@st.cache_resource(show_spinner=False)
def _query_vector(text: str):
    try:
        return embed.embed_query(text)
    except Exception:
        return None  # model unavailable; matchers fall back to key words and TF-IDF


def similarity(text: str, vectors: dict) -> dict:
    q = _query_vector(text) if text.strip() else None
    if q is None or not vectors:
        return {}
    ids = list(vectors)
    return dict(zip(ids, (np.stack([vectors[i] for i in ids]) @ q).tolist()))


def badge(r) -> str:
    return f"<span class='badge {r['tier'].split()[0]}'>{r['tier']} · {r['score']}</span>"


def why(r) -> str:
    items = "".join(f"<li class='good'>{html.escape(x)}</li>" for x in r["reasons"])
    items += "".join(f"<li class='warn'>{html.escape(x)}</li>" for x in r["cautions"])
    return f"<ul class='why'>{items}</ul>"


def tally(results: pd.DataFrame, noun: str) -> tuple[int, int]:
    counts = results["tier"].value_counts() if not results.empty else {}
    s, p_, l = (int(counts.get(t, 0)) for t in ("Strong", "Possible", "Long shot"))
    st.markdown(f"<div class='tally'><b>{s}</b> strong, <b>{p_}</b> possible, <b>{l:,}</b> long-shot {noun}</div>",
                unsafe_allow_html=True)
    return s, p_


# ---------- header ----------
st.title("Grant Matcher")
st.write("Grants a small nonprofit can realistically go after, from federal programs, private foundations, and Florida "
         "state programs, ranked against your mission with the reasons spelled out.")
st.markdown(f"<div class='notice'>{NOTICE}</div>", unsafe_allow_html=True)

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
    state = st.selectbox("State you serve", STATES, index=STATES.index(base.get("state", "FL")))
    cities = st.text_input("Cities or counties you serve (optional)", base.get("cities", ""),
                           help="Comma separated. Used to spot foundations that already fund groups near you.")
    has_501c3 = st.radio("501(c)(3) status", ["Yes", "Pending", "No"],
                         index=["Yes", "Pending", "No"].index(base.get("has_501c3", "Yes")), horizontal=True)
    budget_band = st.selectbox("Annual budget", list(BUDGET_BANDS),
                               index=list(BUDGET_BANDS).index(base.get("budget_band", "$50k to $250k")))
    can_cost_share = st.checkbox("We can provide matching funds", value=base.get("can_cost_share", False))
    with st.expander("Federal filters"):
        categories = st.multiselect("Funding categories", list(CATEGORY_NAMES), default=base.get("categories", []),
                                    format_func=lambda c: CATEGORY_NAMES[c])
        include_forecasted = st.checkbox("Include forecasts (not open yet)", value=base.get("include_forecasted", True))
        min_days = st.slider("Hide deadlines sooner than (days)", 0, 60, base.get("min_days_left", 14))

    profile_dict = {
        "mission": mission, "keywords": keywords, "state": state, "cities": cities, "has_501c3": has_501c3,
        "budget_band": budget_band, "can_cost_share": can_cost_share, "categories": categories,
        "include_forecasted": include_forecasted, "min_days_left": min_days,
    }
    st.download_button("Save this profile", json.dumps(profile_dict, indent=2), "grant-profile.json", "application/json")

if not mission.strip() and not keywords.strip():
    st.info("Add your mission and a few key words in the panel on the left to see matches.")
    st.stop()

profile = Profile(
    mission=mission,
    keywords=[k.strip() for k in keywords.split(",") if k.strip()],
    has_501c3=has_501c3, budget_band=budget_band, can_cost_share=can_cost_share, categories=categories,
    include_forecasted=include_forecasted, min_days_left=min_days,
)
query_text = mission + " " + keywords
city_list = [c for c in cities.split(",") if c.strip()]

tab_fed, tab_fdn, tab_fl, tab_ready = st.tabs(["Federal grants", "Foundations", "Florida programs", "Before you apply"])

# ---------- federal ----------
with tab_fed:
    df, fetched_at, vectors = load_federal()
    if df.empty:
        st.error("The federal grant list could not be loaded right now. Try again in a few minutes.")
    else:
        results = score(df, profile, semantic=similarity(query_text, vectors))
        updated = datetime.fromisoformat(fetched_at).strftime("%b %d, %Y") if fetched_at else ""
        st.caption(f"{len(df):,} open and forecasted federal opportunities that list nonprofits as eligible"
                   + (f", updated {updated}." if updated else "."))
        n_strong, _ = tally(results, "grants")
        if n_strong == 0:
            st.info("No strong federal matches right now. That is common for small direct-service nonprofits: much "
                    "federal money for local programs is passed through state agencies, and foundations fund more "
                    "early-stage work. Check the Foundations and Florida programs tabs.")
        with st.expander("How the score works"):
            st.markdown(
                "- Up to 70 points for how closely the grant's description matches your mission, compared with how "
                "your mission matches grants in general\n"
                "- Up to 30 points for your key words, with rare words like *dyslexia* worth more than common ones like *children*\n"
                "- Points off for research grants, cost sharing you can't provide, award sizes far above your budget, "
                "a 501(c)(3) requirement you don't meet, and programs aimed at tribes, states, or embassies abroad\n"
                "- Strong is 60 and up, possible is 35 to 59")
        show = st.radio("Show", ["Strong and possible", "All"], horizontal=True, label_visibility="collapsed", key="fed_show")
        view = results if show == "All" else results[results["tier"] != "Long shot"]
        for _, r in view.head(40).iterrows():
            due = r["close"].strftime("%b %d, %Y") if pd.notna(r["close"]) and r["close"] else "not listed"
            label = "Est. due" if r["status"] == "forecasted" else "Due"
            with st.container(border=True):
                st.markdown(f"{badge(r)}&nbsp; **[{r['title']}]({r['url']})**", unsafe_allow_html=True)
                st.markdown(f"<div class='meta'>{r['agency']} &nbsp;|&nbsp; {r['number']} &nbsp;|&nbsp; {label} {due}"
                            f" &nbsp;|&nbsp; Award {r['award_range']}</div>", unsafe_allow_html=True)
                st.markdown(why(r), unsafe_allow_html=True)
                with st.expander("Summary"):
                    st.write(r["description"][:1500] + ("..." if len(r["description"]) > 1500 else ""))
                    if r["eligibility_text"]:
                        st.markdown("**Eligibility notes:** " + r["eligibility_text"][:800])
        picks = results[results["tier"] != "Long shot"]
        if not picks.empty:
            export = picks.assign(reasons=picks["reasons"].apply("; ".join), cautions=picks["cautions"].apply("; ".join))
            export = export[["score", "tier", "title", "agency", "number", "status", "close_date", "award_floor",
                             "award_ceiling", "cost_sharing", "reasons", "cautions", "url"]]
            d1, d2 = st.columns(2)
            d1.download_button("Download matches (CSV)", export.to_csv(index=False), "federal-matches.csv", "text/csv")
            d2.download_button("Add deadlines to your calendar (.ics)", to_ics(picks), "grant-deadlines.ics", "text/calendar")

# ---------- foundations ----------
with tab_fdn:
    records, f_fetched, f_vecs = load_foundations(state)
    if not records:
        st.warning(f"Foundation data for {state} is not available yet.")
    else:
        show_pre = st.checkbox("Include foundations that say they fund preselected groups only", value=False)
        f_res = score_foundations(records, profile, state, city_list, similarity(query_text, f_vecs), show_pre)
        st.caption(f"{len(records):,} private foundations that are based in {state} or gave grants there, from their "
                   "latest IRS Form 990-PF. Most foundations fund groups they already know, so start with an introduction.")
        tally(f_res, "foundations")
        with st.expander("How the score works"):
            st.markdown(
                "- Up to 60 points for how closely the foundation's past grant purposes match your mission\n"
                "- Up to 15 points for your key words in its past grants\n"
                f"- Up to 20 points for how much it gives in {state}, plus up to 10 if it funded groups in your cities\n"
                "- Points off when its typical grant is large for your budget, when it says it doesn't take "
                "unsolicited requests, or when it mostly gives scholarships\n"
                "- Data comes from the foundation's own tax return, usually one to two years old")
        f_show = st.radio("Show", ["Strong and possible", "All"], horizontal=True, label_visibility="collapsed", key="fdn_show")
        f_view = f_res if f_show == "All" or f_res.empty else f_res[f_res["tier"] != "Long shot"]
        for _, r in f_view.head(40).iterrows():
            apply = r.get("apply") if isinstance(r.get("apply"), dict) else {}
            with st.container(border=True):
                st.markdown(f"{badge(r)}&nbsp; **[{r['name'].title()}]({r['url']})**", unsafe_allow_html=True)
                st.markdown(
                    f"<div class='meta'>{r['city'].title()}, {r['state']} &nbsp;|&nbsp; {r['grant_count']} grants, "
                    f"{_money(r['grants_total'])} total &nbsp;|&nbsp; typical {_money(r['grant_median'])} &nbsp;|&nbsp; "
                    f"tax year {r['tax_year']}</div>", unsafe_allow_html=True)
                st.markdown(why(r), unsafe_allow_html=True)
                with st.expander("How to apply and past grants"):
                    if apply:
                        lines = []
                        for label, key in (("Contact", "contact"), ("Phone", "phone"), ("Email", "email"),
                                           ("Address", "address"), ("What to send", "materials"),
                                           ("Deadlines", "deadlines"), ("Restrictions", "restrictions")):
                            if apply.get(key):
                                lines.append(f"**{label}:** {html.escape(apply[key])}")
                        st.markdown("  \n".join(lines) or "No application details listed.")
                    else:
                        st.write("No application details listed on the return.")
                    if r.get("website"):
                        st.markdown(f"**Website:** {r['website']}")
                    grants = pd.DataFrame(r["sample_grants"])
                    if not grants.empty:
                        local = grants[grants["state"] == state]
                        st.markdown(f"**Largest grants** ({len(local)} of these in {state})")
                        st.dataframe(grants[["to", "city", "state", "amount", "purpose"]].head(15).rename(columns={
                            "to": "Recipient", "city": "City", "state": "State", "amount": "Amount", "purpose": "Purpose"}),
                            hide_index=True, use_container_width=True,
                            column_config={"Amount": st.column_config.NumberColumn(format="$%d")})
        if not f_res.empty:
            picks = f_res[f_res["tier"] != "Long shot"]
            if not picks.empty:
                export = picks.assign(
                    reasons=picks["reasons"].apply("; ".join), cautions=picks["cautions"].apply("; ".join),
                    contact=picks["apply"].apply(lambda a: (a or {}).get("contact", "") if isinstance(a, dict) else ""),
                    email=picks["apply"].apply(lambda a: (a or {}).get("email", "") if isinstance(a, dict) else ""),
                    phone=picks["apply"].apply(lambda a: (a or {}).get("phone", "") if isinstance(a, dict) else ""),
                    deadlines=picks["apply"].apply(lambda a: (a or {}).get("deadlines", "") if isinstance(a, dict) else ""),
                )[["score", "tier", "name", "city", "state", "ein", "grant_count", "grant_median", "in_state",
                   "contact", "email", "phone", "deadlines", "reasons", "cautions", "url"]]
                st.download_button("Download foundation matches (CSV)", export.to_csv(index=False),
                                   "foundation-matches.csv", "text/csv")

# ---------- Florida ----------
with tab_fl:
    if state != "FL":
        st.info("State programs are available for Florida only so far.")
    else:
        programs, fy, fl_vecs = load_florida()
        if not programs:
            st.warning("Florida program data is not available yet.")
        else:
            show_ear = st.checkbox("Include programs the Legislature set aside for named organizations", value=False)
            fl_res = score_florida(programs, profile, similarity(query_text, fl_vecs), show_ear)
            open_n = sum(1 for p_ in programs if p_["nonprofit_eligible"] and not p_["earmark"])
            st.caption(f"{open_n:,} of {len(programs):,} programs in Florida's Catalog of State Financial Assistance "
                       f"(fiscal year {fy}) are open to nonprofits and not set aside for a named group. The catalog "
                       "lists programs, not open calls: check the agency's site for the next application window.")
            tally(fl_res, "programs")
            fl_show = st.radio("Show", ["Strong and possible", "All"], horizontal=True, label_visibility="collapsed", key="fl_show")
            fl_view = fl_res if fl_show == "All" or fl_res.empty else fl_res[fl_res["tier"] != "Long shot"]
            for _, r in fl_view.head(40).iterrows():
                with st.container(border=True):
                    st.markdown(f"{badge(r)}&nbsp; **[{r['title']}]({r['url']})**", unsafe_allow_html=True)
                    st.markdown(f"<div class='meta'>{r['agency']} &nbsp;|&nbsp; CSFA {r['csfa']} &nbsp;|&nbsp; "
                                f"{r['assistance']}</div>", unsafe_allow_html=True)
                    st.markdown(why(r), unsafe_allow_html=True)
                    with st.expander("Details"):
                        for label, key in (("Objectives", "objectives"), ("Who can apply", "applicant_types"),
                                           ("How to apply", "application"), ("How awards are made", "award"),
                                           ("Deadlines", "deadlines"), ("Restrictions", "restrictions"),
                                           ("Contact", "contact")):
                            if r[key] and r[key].strip().upper() not in ("N/A", "NA", "NONE"):
                                st.markdown(f"**{label}:** {html.escape(r[key][:900])}")
                        if r["web"]:
                            st.markdown(f"**Agency site:** {r['web']}")

# ---------- checklist ----------
with tab_ready:
    st.subheader("Getting ready to apply")
    st.markdown(
        """
**For any funder**
1. **Your IRS determination letter** showing 501(c)(3) status.
2. **A one-page organization summary:** mission, programs, who you serve, and the results you track.
3. **A simple annual budget** and, for larger requests, your most recent financial statements.
4. **Your board list** and a short bio for your director.

**For federal grants** (these registrations take weeks, so start early)
1. **SAM.gov registration and a Unique Entity ID (UEI).** Free, required for every federal applicant, and renewed every year. Start at [sam.gov](https://sam.gov).
2. **A Grants.gov applicant account** linked to your organization. See [Grants.gov applicant registration](https://www.grants.gov/applicants/applicant-registration).

**For foundations**
- Read the "How to apply" notes. Many want a short letter of inquiry first, not a full proposal.
- Look at who they funded last year. If they fund groups like yours near you, mention that connection.
- Community foundations in your county are often the best first call, and many run small grant cycles for new nonprofits.

**For Florida state programs**
- The state pays grants and contracts to registered vendors. Register at [MyFloridaMarketPlace](https://www.myfloridamarketplace.com) and keep a Florida Substitute W-9 on file with the Department of Financial Services.
- Each agency posts its own application windows. Use the agency link on each program to find the next one.
        """
    )

st.markdown("---")
st.markdown(
    f"<div class='meta'>{NOTICE} Federal data from the Grants.gov API, refreshed nightly. Foundation data from IRS Form "
    "990-PF e-file returns. Florida data from the Department of Financial Services Catalog of State Financial Assistance. "
    "Scores are a starting point for your own review, not a guarantee of eligibility. "
    "Source code: <a href='https://github.com/RendellRich/grant-matcher'>github.com/RendellRich/grant-matcher</a></div>",
    unsafe_allow_html=True,
)
