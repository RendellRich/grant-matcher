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

import os

from grantmatch import embed
from grantmatch import ui_workspace as uiw
from grantmatch import workspace as wsp
from grantmatch.store import GitHubStore, LocalStore, StoreError
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
        "state": "FL", "cities": "Tampa, Bradenton, Sarasota, St. Petersburg",
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

st.set_page_config(page_title="Grant Matcher for small nonprofits", page_icon=":material/checklist:", layout="wide")

# Colour tokens for the few things the theme in .streamlit/config.toml can't reach (badges, meta text, icons).
# Every text pair here passes WCAG AA on its own background; the theme follows the visitor's light or dark setting.
TOKENS = {
    "light": {"muted": "#4b5753", "border": "#d5ddd9", "accent": "#2f6f5e", "caution": "#8a5a00",
              "strong-bg": "#e2f1e9", "strong-fg": "#17543f", "possible-bg": "transparent", "possible-fg": "#2f6f5e", "surface": "#f4f6f5",
              "long-bg": "#edf0ef", "long-fg": "#3b4744"},
    "dark": {"muted": "#a7b2ae", "border": "#34403b", "accent": "#6cc0a5", "caution": "#e0b45a",
             "strong-bg": "#173a2d", "strong-fg": "#a9e3c6", "possible-bg": "transparent", "possible-fg": "#6cc0a5", "surface": "#1b2220",
             "long-bg": "#252d2a", "long-fg": "#c6cfcb"},
}
_mode = "dark" if getattr(st.context.theme, "type", None) == "dark" else "light"
_vars = "".join(f"--gm-{k}:{v};" for k, v in TOKENS[_mode].items())
_CHECK = ("url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' "
          "stroke='black' stroke-width='2.6' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M5 12.5l4.5 "
          "4.5L19 7.5'/%3E%3C/svg%3E\")")
_ALERT = ("url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' "
          "stroke='black' stroke-width='2.2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M12 3.5 2.5 "
          "20h19z'/%3E%3Cpath d='M12 10v4.5M12 17.5v.01'/%3E%3C/svg%3E\")")
st.markdown(
    f"""
    <style>
    :root {{{_vars}}}
    [data-testid="stMainBlockContainer"] {{max-width: 1080px; padding-top: 2.5rem; padding-bottom: 4rem;}}
    [data-testid="stMainBlockContainer"] [data-testid="stHeaderActionElements"] {{display: none;}}

    /* header */
    .gm-h1 {{font-size: clamp(1.75rem, 1.3rem + 1.6vw, 2.25rem) !important; letter-spacing: -0.01em; padding: 0 !important; margin: 0 0 .5rem;}}
    .stApp p.gm-lead {{font-size: 1.0625rem !important; line-height: 1.55; max-width: 65ch; margin: 0 0 .75rem;}}
    .stApp p.gm-notice {{font-size: .875rem !important; line-height: 1.5; color: var(--gm-muted); max-width: 72ch;
                         margin: 0 0 1rem;}}
    .stApp .gm-note {{font-size: .9375rem !important; line-height: 1.5; max-width: 72ch; margin: 0 0 .75rem;
                      padding: .625rem .875rem; border-radius: .5rem; background: var(--gm-surface);}}
    .gm-note p {{margin: 0; font-size: inherit !important;}}
    .gm-note ol {{margin: .5rem 0 0; padding-left: 1.25rem;}}
    .gm-note li {{margin: 0 0 .25rem; font-size: inherit !important;}}
    .gm-phone {{display: none;}}
    @media (max-width: 768px) {{ .gm-phone {{display: inline;}} }}
    .stApp p.gm-overview {{font-size: 1.0625rem !important; line-height: 1.5; max-width: 72ch; margin: .25rem 0 .75rem;}}
    .gm-quiet {{color: var(--gm-muted);}}

    /* tabs: 44px targets, wrap instead of scrolling, selected tab underlined */
    [data-testid="stTabs"] [role="tablist"] {{flex-wrap: wrap; gap: 0 1.5rem; overflow: visible !important;
                                               border-bottom: 1px solid var(--gm-border);}}
    [data-testid="stTabs"] [role="tab"] {{min-height: 44px; padding: 0 .125rem; font-weight: 500; flex: none;}}
    [data-testid="stTabs"] [role="tab"][aria-selected="true"] {{box-shadow: inset 0 -2px 0 var(--gm-accent);}}
    [data-testid^="stTabsScroll"] {{display: none !important;}}
    @media (max-width: 640px) {{ [data-testid="stTabs"] [role="tablist"] {{gap: 0 1rem;}} }}
    [data-testid="stTabs"] [role="tabpanel"] {{padding-top: 1.25rem;}}

    /* text */
    [data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p {{color: var(--gm-muted) !important; opacity: 1 !important;}}
    [data-testid="stMainBlockContainer"] [data-testid="stCaptionContainer"] {{max-width: 72ch;}}
    .gm-tally {{font-size: 1.5625rem !important; font-weight: 400 !important; line-height: 1.25; padding: 0 !important;
                margin: 0 0 .25rem;}}
    .gm-tally b {{font-weight: 650;}}
    .gm-section {{font-size: 1.5625rem !important; line-height: 1.25; padding: 1.5rem 0 0 !important; margin: 0 0 .25rem;
                  border-top: 1px solid var(--gm-border);}}
    .gm-section .gm-count {{color: var(--gm-muted); font-weight: 400;}}
    .gm-group {{font-size: .875rem !important; font-weight: 600 !important; color: var(--gm-muted);
                padding: 1rem 0 .375rem !important; margin: .5rem 0 0 !important; border-top: 1px solid var(--gm-border);}}
    .sr-only {{position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap;}}

    /* result cards */
    [class*="st-key-card_"] {{padding: 1.125rem 1.25rem .5rem; gap: .75rem;}}
    [class*="st-key-card_"] [data-testid="stExpander"] details {{border: none; border-top: 1px solid var(--gm-border);
                                                              border-radius: 0; margin: 0 -1.25rem; width: calc(100% + 2.5rem);}}
    [class*="st-key-card_"] [data-testid="stExpander"] summary {{padding-left: 1.25rem; padding-right: 1.25rem;}}
    [class*="st-key-card_"] [data-testid="stExpanderDetails"] {{padding-left: 1.25rem; padding-right: 1.25rem;}}
    @media (max-width: 640px) {{
        [class*="st-key-card_"] {{padding: 1rem 1rem .5rem;}}
        [class*="st-key-card_"] [data-testid="stExpander"] details {{margin: 0 -1rem; width: calc(100% + 2rem);}}
        [class*="st-key-card_"] [data-testid="stExpander"] summary,
        [class*="st-key-card_"] [data-testid="stExpanderDetails"] {{padding-left: 1rem; padding-right: 1rem;}}
    }}
    .gm-meta .item {{white-space: nowrap;}}
    .gm-head {{display: flex; flex-wrap: wrap; align-items: center; gap: .25rem .75rem; margin: 0;}}
    .gm-badge {{display: inline-block; padding: .125rem .625rem; border-radius: 999px; font-size: .8125rem; font-weight: 600; line-height: 1.5;}}
    .gm-badge.Strong {{background: var(--gm-strong-bg); color: var(--gm-strong-fg);}}
    .gm-badge.Possible {{background: var(--gm-possible-bg); color: var(--gm-possible-fg);
                         box-shadow: inset 0 0 0 1px var(--gm-possible-fg);}}
    .gm-badge.Long {{background: var(--gm-long-bg); color: var(--gm-long-fg);}}
    .gm-score {{font-size: .875rem; color: var(--gm-muted);}}
    h3.gm-title {{font-size: 1.25rem !important; line-height: 1.35; padding: 0 !important; margin: 0;}}
    @media (max-width: 640px) {{ .stApp p.gm-lead {{font-size: 1rem !important;}} }}
    h3.gm-title a {{display: block; padding: .5rem 0; min-height: 44px; box-sizing: border-box; color: inherit;
                    text-decoration-thickness: 1px; text-underline-offset: 3px; overflow-wrap: anywhere;}}
    h3.gm-title a:hover {{color: var(--gm-accent); text-decoration-thickness: 2px;}}
    .stApp p.gm-meta {{font-size: .875rem !important; line-height: 1.5; color: var(--gm-muted); margin: 0;}}
    .gm-meta .sep {{padding: 0 .375rem;}}
    ul.gm-why {{list-style: none; padding: 0; margin: .25rem 0 0;}}
    ul.gm-why li {{display: flex; gap: .5rem; margin: 0 0 .3rem; line-height: 1.45; padding: 0;}}
    ul.gm-why li::before {{content: ""; flex: none; width: 1rem; height: 1rem; margin-top: .2rem;
                           -webkit-mask: var(--icon) center / contain no-repeat; mask: var(--icon) center / contain no-repeat;}}
    ul.gm-why li.good::before {{--icon: {_CHECK}; background: var(--gm-accent);}}
    ul.gm-why li.warn::before {{--icon: {_ALERT}; background: var(--gm-caution);}}

    .stApp :is(input, textarea)::placeholder {{color: var(--gm-muted); opacity: 1;}}

    /* 44px targets and a visible focus ring everywhere */
    .stButton button, .stDownloadButton button, [data-testid="stFileUploader"] button,
    [data-testid="stExpander"] summary {{min-height: 44px;}}
    [data-testid="stTextInputRootElement"], [data-testid="stSelectbox"] [role="group"],
    [data-testid="stMultiSelect"] [role="group"] {{min-height: 44px;}}
    [data-testid="stRadio"] label, [data-testid="stCheckbox"] label {{min-height: 44px; align-items: center;}}
    :is(button[aria-label^="Help for"], [data-testid="stMultiSelect"] button, [data-testid="stSlider"] [role="slider"])
        {{position: relative;}}
    :is(button[aria-label^="Help for"], [data-testid="stMultiSelect"] button, [data-testid="stSlider"] [role="slider"])::after
        {{content: ""; position: absolute; left: 50%; top: 50%; width: 44px; height: 44px; transform: translate(-50%, -50%);}}
    .stApp main:focus-visible {{outline: 2px solid var(--gm-accent) !important; outline-offset: -2px;}}
    [data-testid="stSidebarCollapseButton"] button, [data-testid="stExpandSidebarButton"] {{min-width: 44px; min-height: 44px;}}
    [data-testid="stMultiSelect"] [data-tag] {{background: var(--gm-long-bg) !important; color: var(--gm-long-fg) !important;}}
    [data-testid="stMultiSelect"] [data-tag] svg {{fill: currentColor;}}
    .stApp :is(a, button, summary, [role="tab"], [role="radio"], [role="checkbox"], [role="switch"], input[type="radio"], input[type="checkbox"], [data-tag]):focus-visible
        {{outline: 2px solid var(--gm-accent) !important; outline-offset: 2px; box-shadow: none !important;}}
    .stApp :is([data-testid="stTextInputRootElement"], [data-testid="stTextAreaRootElement"],
               [data-testid="stSelectbox"] [role="group"], [data-testid="stMultiSelect"] [role="group"]):focus-within
        {{outline: 2px solid var(--gm-accent); outline-offset: 1px;}}

    /* footer */
    .gm-footer {{margin-top: 3rem; padding-top: 1.25rem; border-top: 1px solid var(--gm-border);
                 font-size: .8125rem; line-height: 1.55; color: var(--gm-muted); max-width: 72ch;}}
    .gm-footer p {{margin: 0 0 .5rem;}}
    .gm-footer a {{color: inherit; display: inline-block; padding: .75rem 0; min-height: 44px; box-sizing: border-box;
                   text-underline-offset: 3px;}}
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
    records, vecs, stamp = [], {}, ""
    for prefix, folder in (("foundations", "foundations"), ("community", "community")):
        raw = _fetch(f"{prefix}-{state}.json.gz", f"{folder}/{state}.json.gz")
        if raw is None:
            continue
        payload = json.loads(gzip.decompress(raw))
        for rec in payload["foundations"]:
            rec.setdefault("kind", "Private foundation")
        records += payload["foundations"]
        stamp = stamp or payload.get("fetched_at", "")
        vecs.update(_vectors(f"{prefix}-{state}.npz", f"{folder}/{state}.npz"))
    return records, stamp, vecs


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


def _s(value) -> str:
    """Text value from a mixed DataFrame row (missing values come back as NaN)."""
    return value if isinstance(value, str) else ""


TIER_LABEL = {"Strong": "Strong match", "Possible": "Possible match", "Long shot": "Long shot"}
SEP = "<span class='sep' aria-hidden='true'>·</span>"


def _esc(value) -> str:
    return html.escape(str(value)) if value is not None else ""


def _href(url) -> str:
    url = _s(url).strip()
    return html.escape(url, quote=True) if url.lower().startswith(("https://", "http://")) else "#"


def card_head(r, title: str, url: str, meta: list[str]) -> str:
    """Badge, score, title link and meta line for one result. Every value from the data is escaped."""
    tier = r["tier"]
    return (f"<p class='gm-head'><span class='gm-badge {tier.split()[0]}'>{TIER_LABEL.get(tier, tier)}</span>"
            f"<span class='gm-score'>Score {int(r['score'])} of 100</span></p>"
            f"<h3 class='gm-title'><a href='{_href(url)}' target='_blank' rel='noopener'>{_esc(title)}"
            f"<span class='sr-only'> (opens in a new tab)</span></a></h3>"
            f"<p class='gm-meta'>{SEP.join(_meta_item(m) for m in meta if m)}</p>")


def _meta_item(text) -> str:
    """Short facts (IDs, dates, amounts) never break mid-way; long names may wrap."""
    text = str(text)
    return f"<span class='item'>{_esc(text)}</span>" if len(text) <= 28 else _esc(text)


def why(r) -> str:
    items = "".join(f"<li class='good'><span class='sr-only'>Fits: </span>{_esc(x)}</li>" for x in r["reasons"])
    items += "".join(f"<li class='warn'><span class='sr-only'>Caution: </span>{_esc(x)}</li>" for x in r["cautions"])
    return f"<ul class='gm-why'>{items}</ul>"


def tally(results: pd.DataFrame, noun: str) -> tuple[int, int]:
    counts = results["tier"].value_counts() if not results.empty else {}
    s, p_, l = (int(counts.get(t, 0)) for t in ("Strong", "Possible", "Long shot"))
    st.markdown(f"<h2 class='gm-tally'><b>{s}</b> strong, <b>{p_}</b> possible, <b>{l:,}</b> long-shot {noun}</h2>",
                unsafe_allow_html=True)
    return s, p_


def result_list(results: pd.DataFrame, card, noun: str, key: str, after_matches=None) -> None:
    """Strong and possible matches first, then long shots in their own section behind a toggle."""
    good = results[results["tier"] != "Long shot"] if not results.empty else results
    longs = results[results["tier"] == "Long shot"] if not results.empty else results
    if good.empty:
        st.info(f"No strong or possible {noun} for this profile yet. Try more specific key words in your profile, "
                "or look through the long shots below.", icon=":material/search:")
    for _, r in good.head(40).iterrows():
        card(r)
    if after_matches is not None:
        after_matches()
    if not longs.empty:
        st.markdown(f"<h2 class='gm-section'>Long shots <span class='gm-count'>{len(longs):,}</span></h2>",
                    unsafe_allow_html=True)
        st.caption("These fit on a few points and miss on others. Read the cautions before spending time on one.")
        long_shots(longs.head(20), card, key)


@st.fragment
def long_shots(longs: pd.DataFrame, card, key: str) -> None:
    """Its own fragment, so the toggle reruns only this section instead of the whole page."""
    if st.toggle(f"Show the top {len(longs)} long shots", key=key):
        for _, r in longs.iterrows():
            card(r)


# ---------- header ----------
st.markdown(
    "<h1 class='gm-h1'>Grant Matcher</h1>"
    "<p class='gm-lead'>Grants a small nonprofit can realistically go after, from federal programs, private and community "
    "foundations, and Florida state programs, ranked against your mission with the reasons spelled out.</p>"
    f"<p class='gm-notice'>{NOTICE}</p>",
    unsafe_allow_html=True,
)

# ---------- workspace (sign-in) ----------
def _secret(section: str):
    try:
        return st.secrets[section]
    except Exception:
        return None


WS_CONF = _secret("workspace")
AUTH_ON = WS_CONF is not None and _secret("auth") is not None
store, who = None, ""
if os.environ.get("GM_LOCAL_STORE"):  # development: a local folder stands in for the private repo
    store, who = LocalStore(os.environ["GM_LOCAL_STORE"]), "local"
elif AUTH_ON and st.user.is_logged_in:
    who = (st.user.get("email") or "").lower()
    allowed = [e.strip().lower() for e in WS_CONF.get("allowed_emails", [])]
    if who in allowed:
        store = GitHubStore(WS_CONF["repo"].strip(), WS_CONF["github_token"])
ANTHROPIC = (_secret("anthropic") or {}).get("api_key", "").strip() or None if _secret("anthropic") else None

# ---------- profile ----------
with st.sidebar:
    if AUTH_ON:
        if not st.user.is_logged_in:
            st.button("Sign in to your workspace", on_click=st.login, width="stretch")
        else:
            st.caption(f"Signed in as {who}" + ("" if store else ". This account doesn't have a workspace."))
            st.button("Sign out", on_click=st.logout)
    st.header("Your organization")
    ss = st.session_state

    # Mission and key words keep their own state so switching examples never silently replaces edited text.
    def _preset_text(name: str) -> tuple[str, str]:
        p = PRESETS.get(name, {})
        return p.get("mission", ""), p.get("keywords", "")

    def _apply_preset(name: str) -> None:
        ss["mission"], ss["keywords"] = _preset_text(name)
        ss["_preset_applied"] = name
        ss.pop("_preset_pending", None)

    def _on_preset_change() -> None:
        new, prev = ss["preset"], ss.get("_preset_applied")
        current = (ss.get("mission", ""), ss.get("keywords", ""))
        if prev is not None and any(t.strip() for t in current) and current != _preset_text(prev):
            ss["_preset_pending"], ss["preset"] = new, prev
        else:
            _apply_preset(new)

    def _replace_text() -> None:
        new = ss["_preset_pending"]
        _apply_preset(new)
        ss["preset"] = new

    if "_preset_applied" not in ss:
        _apply_preset(next(iter(PRESETS)))

    preset_slot = st.container()  # drawn first, filled once we know whether a saved profile was loaded
    with st.expander("Load a saved profile"):
        uploaded = st.file_uploader("Profile file (.json)", type="json",
                                    help="A profile you downloaded from this page earlier.")
    saved = json.load(uploaded) if uploaded else None
    if saved is None and store is not None:
        try:
            saved = store.read(wsp.PROFILE_FILE)
        except StoreError as exc:
            st.warning(str(exc))
    saved_sig = json.dumps(saved, sort_keys=True) if saved else None
    if ss.get("_saved_sig") != saved_sig:  # a profile was just loaded or removed
        if saved:
            ss["mission"], ss["keywords"] = saved.get("mission", ""), saved.get("keywords", "")
        elif ss.get("_saved_sig"):
            _apply_preset(ss.get("preset", next(iter(PRESETS))))
        ss["_saved_sig"] = saved_sig
    with preset_slot:
        preset_name = st.selectbox("Start from an example", list(PRESETS), key="preset", on_change=_on_preset_change,
                                   disabled=saved is not None,
                                   help="Pick the one closest to your work and edit it, or start blank. "
                                        "A loaded profile replaces the example.")
        if ss.get("_preset_pending"):
            st.warning(f"Replace your mission and key words with the *{ss['_preset_pending']}* example?",
                       icon=":material/warning:")
            st.button("Replace my text", on_click=_replace_text, width="stretch")
            st.button("Keep my text", on_click=lambda: ss.pop("_preset_pending", None), width="stretch")
    base = saved or PRESETS[preset_name]

    def group(title: str) -> None:
        st.markdown(f"<h3 class='gm-group'>{title}</h3>", unsafe_allow_html=True)

    group("About your work")
    mission = st.text_area("Mission and programs", key="mission", height=170,
                           placeholder="Who you serve, where, and what you do for them.",
                           help="Two or three sentences. This counts most in the ranking.")
    keywords = st.text_area("Key words", key="keywords", height=96,
                            placeholder="For example: dyslexia, tutoring, after school",
                            help="Separate with commas. Use words a matching grant would use. "
                                 "Rare, specific words count more than common ones.")
    group("Where you work")
    state = st.selectbox("State you serve", STATES, index=STATES.index(base.get("state", "FL")))
    cities = st.text_input("Cities or counties (optional)", base.get("cities", ""),
                           placeholder="For example: Tampa, Hillsborough",
                           help="Separate with commas. Used to find foundations that already fund groups near you.")
    group("Eligibility")
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
    group("Keep this profile")
    if store is not None:
        if st.button("Save profile to workspace", width="stretch"):
            store.write(wsp.PROFILE_FILE, profile_dict, "Update search profile")
            st.toast("Profile saved. It will load automatically next time.")
    st.download_button("Download this profile", json.dumps(profile_dict, indent=2), "grant-profile.json",
                       "application/json", width="stretch")
    st.caption("Load it here next time to pick up where you left off.")

PHONE_HINT = "<span class='gm-phone'> On a phone, open that panel with the » button at the top left.</span>"
if not mission.strip() and not keywords.strip():
    st.markdown(
        "<div class='gm-note' role='note'><p><b>Tell us about your work to see matches.</b>" + PHONE_HINT + "</p>"
        "<ol><li>Describe your mission and programs under <b>Your organization</b>.</li>"
        "<li>Add a few key words a matching grant would use.</li>"
        "<li>Set your state and, if you like, your cities or counties.</li></ol></div>",
        unsafe_allow_html=True)
    st.stop()

if saved is None and preset_name != "Start blank" and (mission, keywords) == _preset_text(preset_name):
    st.markdown(
        f"<p class='gm-note' role='note'>Showing the example <i>{_esc(preset_name)}</i>. Edit <b>Your organization</b> "
        f"to see your own matches.{PHONE_HINT}</p>", unsafe_allow_html=True)

profile = Profile(
    mission=mission,
    keywords=[k.strip() for k in keywords.split(",") if k.strip()],
    has_501c3=has_501c3, budget_band=budget_band, can_cost_share=can_cost_share, categories=categories,
    include_forecasted=include_forecasted, min_days_left=min_days,
)
query_text = mission + " " + keywords
city_list = [c for c in cities.split(",") if c.strip()]
KINDS_ALL = ["Private foundation", "Community foundation", "Public foundation", "United Way or federated fund"]

# ---------- score every source first, so the overview and tab order can use all three ----------
with st.spinner("Updating matches"):
    df, fetched_at, vectors = load_federal()
    results = None if df.empty else score(df, profile, semantic=similarity(query_text, vectors))

    records, f_fetched, f_vecs = load_foundations(state)
    f_res = None
    if records:
        kinds = ss.get("fdn_kinds", KINDS_ALL)
        chosen = [r for r in records if r["kind"] in kinds]
        f_res = score_foundations(chosen, profile, state, city_list, similarity(query_text, f_vecs),
                                  ss.get("fdn_pre", False))

    programs, fy, fl_res = [], "", None
    if state == "FL":
        programs, fy, fl_vecs = load_florida()
        if programs:
            fl_res = score_florida(programs, profile, similarity(query_text, fl_vecs), ss.get("fl_ear", False))


def _count(res, tier: str) -> int:
    return 0 if res is None or res.empty else int((res["tier"] == tier).sum())


SOURCES = {"fed": ("Federal grants", "federal grants", results), "fdn": ("Foundations", "foundations", f_res)}
if state == "FL":
    SOURCES["fl"] = ("Florida programs", "Florida programs", fl_res)
strong = {k: _count(v[2], "Strong") for k, v in SOURCES.items()}
possible = {k: _count(v[2], "Possible") for k, v in SOURCES.items()}

# Most strong matches first. Keep the current order unless another source pulls ahead, so editing the
# profile doesn't shuffle the tabs under someone who is reading one.
ranked = sorted(SOURCES, key=lambda k: (-strong[k], -possible[k]))
order = ss.get("_tab_order")
if not order or sorted(order) != sorted(SOURCES) or strong[ranked[0]] > strong[order[0]]:
    order = ranked
ss["_tab_order"] = order

total = sum(strong.values())
parts = [f"{strong[k]:,} {SOURCES[k][1]}" for k in order]
listing = ", ".join(parts[:-1]) + (" and " if len(parts) > 1 else "") + parts[-1]
if total:
    overview = f"<b>{total:,} strong matches</b> for this profile: {listing}."
else:
    poss = ", ".join(f"{possible[k]:,} {SOURCES[k][1]}" for k in order)
    overview = (f"<b>No strong matches yet.</b> Possible matches: {poss}. "
                "More specific key words usually help.")
st.markdown(f"<p class='gm-overview'>{overview} <span class='gm-quiet'>Tabs with the most strong matches come "
            "first.</span></p>", unsafe_allow_html=True)

tab_keys = order + ["ready"] + (["workspace"] if store else [])
labels = {**{k: v[0] for k, v in SOURCES.items()}, "ready": "Before you apply", "workspace": "Workspace"}
TAB = dict(zip(tab_keys, st.tabs([labels[k] for k in tab_keys])))

# ---------- federal ----------
with TAB["fed"]:
    if results is None:
        st.error("The federal grant list could not be loaded right now. Try again in a few minutes.")
    else:
        n_strong, _ = tally(results, "grants")
        updated = datetime.fromisoformat(fetched_at).strftime("%b %d, %Y") if fetched_at else ""
        st.caption(f"{len(df):,} open and forecasted federal opportunities that list nonprofits as eligible"
                   + (f", updated {updated}." if updated else "."))
        if n_strong == 0:
            st.caption("No strong federal matches is common for small direct-service groups: much federal money "
                       "for local programs passes through state agencies first.")
        with st.expander("How the score works"):
            st.markdown(
                "- Up to 70 points for how closely the grant's description matches your mission, compared with how "
                "your mission matches grants in general\n"
                "- Up to 30 points for your key words, with rare words like *dyslexia* worth more than common ones like *children*\n"
                "- Points off for research grants, cost sharing you can't provide, award sizes far above your budget, "
                "a 501(c)(3) requirement you don't meet, and programs aimed at tribes, states, or embassies abroad\n"
                "- Strong is 60 and up, possible is 35 to 59")

        def fed_card(r):
            due = r["close"].strftime("%b %d, %Y") if pd.notna(r["close"]) and r["close"] else "not listed"
            label = "Est. due" if r["status"] == "forecasted" else "Due"
            with st.container(border=True, key=f"card_fed_{r['id']}"):
                st.markdown(card_head(r, r["title"], r["url"], [r["agency"], r["number"], f"{label} {due}",
                                                                 f"Award {r['award_range']}"]) + why(r),
                            unsafe_allow_html=True)
                if store is not None:
                    uiw.save_button(store, who, "federal", r, key=f"save_fed_{r['id']}")
                with st.expander("Summary"):
                    st.write(r["description"][:1500] + ("..." if len(r["description"]) > 1500 else ""))
                    if r["eligibility_text"]:
                        st.markdown("**Eligibility notes:** " + r["eligibility_text"][:800])

        def fed_downloads():
            picks = results[results["tier"] != "Long shot"]
            if picks.empty:
                return
            export = picks.assign(reasons=picks["reasons"].apply("; ".join), cautions=picks["cautions"].apply("; ".join))
            export = export[["score", "tier", "title", "agency", "number", "status", "close_date", "award_floor",
                             "award_ceiling", "cost_sharing", "reasons", "cautions", "url"]]
            d1, d2 = st.columns(2)
            d1.download_button("Download matches (CSV)", export.to_csv(index=False), "federal-matches.csv", "text/csv",
                               width="stretch")
            d2.download_button("Add deadlines to your calendar (.ics)", to_ics(picks), "grant-deadlines.ics",
                               "text/calendar", width="stretch")

        result_list(results, fed_card, "grants", "fed_long", after_matches=fed_downloads)

# ---------- foundations ----------
with TAB["fdn"]:
    if not records:
        st.warning(f"Foundation data for {state} is not available yet.")
    else:
        counts = pd.Series([r["kind"] for r in records]).value_counts()
        tally(f_res, "foundations")
        st.caption(f"{len(records):,} grantmakers based in {state} or giving there, from their latest IRS returns. "
                   "Most funders back groups they already know, so start with an introduction.")
        st.multiselect("Types", KINDS_ALL, default=KINDS_ALL, key="fdn_kinds",
                       format_func=lambda k: f"{k} ({int(counts.get(k, 0)):,})")
        st.checkbox("Include foundations that say they fund preselected groups only", value=False, key="fdn_pre")
        with st.expander("How the score works"):
            st.markdown(
                "- Up to 60 points for how closely the foundation's past grant purposes match your mission\n"
                "- Up to 15 points for your key words in its past grants\n"
                f"- Up to 20 points for how much it gives in {state}, plus up to 10 if it funded groups in your cities\n"
                "- Points off when its typical grant is large for your budget, when it says it doesn't take "
                "unsolicited requests, or when it mostly gives scholarships\n"
                "- Data comes from the foundation's own tax return, usually one to two years old")

        def fdn_card(r):
            apply = r.get("apply") if isinstance(r.get("apply"), dict) else {}
            with st.container(border=True, key=f"card_fdn_{r['ein']}"):
                st.markdown(card_head(r, r["name"].title(), r["url"], [
                    r["kind"], f"{r['city'].title()}, {r['state']}",
                    f"{r['grant_count']} grants, {_money(r['grants_total'])} total",
                    f"typical {_money(r['grant_median'])}", f"tax year {r['tax_year']}"]) + why(r),
                    unsafe_allow_html=True)
                if store is not None:
                    uiw.save_button(store, who, "foundation", r, key=f"save_fdn_{r['ein']}")
                with st.expander("How to apply and past grants"):
                    if _s(r.get("mission")):
                        st.markdown(f"**Mission:** {html.escape(_s(r.get('mission')).capitalize())}")
                    if _s(r.get("phone")) and not apply:
                        st.markdown(f"**Phone:** {_s(r.get('phone'))}")
                    if apply:
                        lines = []
                        for label, key in (("Contact", "contact"), ("Phone", "phone"), ("Email", "email"),
                                           ("Address", "address"), ("What to send", "materials"),
                                           ("Deadlines", "deadlines"), ("Restrictions", "restrictions")):
                            if apply.get(key):
                                lines.append(f"**{label}:** {html.escape(apply[key])}")
                        st.markdown("  \n".join(lines) or "No application details listed.")
                    elif r["kind"] == "Private foundation":
                        st.write("No application details listed on the return.")
                    if _s(r.get("website")):
                        st.markdown(f"**Website:** {_s(r.get('website'))}")
                    grants = pd.DataFrame(r["sample_grants"])
                    if not grants.empty:
                        local = grants[grants["state"] == state]
                        st.markdown(f"**Largest grants** ({len(local)} of these in {state})")
                        st.dataframe(grants[["to", "city", "state", "amount", "purpose"]].head(15).rename(columns={
                            "to": "Recipient", "city": "City", "state": "State", "amount": "Amount", "purpose": "Purpose"}),
                            hide_index=True, width="stretch",
                            column_config={"Amount": st.column_config.NumberColumn(format="$%d")})

        def fdn_downloads():
            if f_res.empty:
                return
            picks = f_res[f_res["tier"] != "Long shot"].copy()
            for col in ("apply", "website"):
                if col not in picks:
                    picks[col] = None
            if not picks.empty:
                export = picks.assign(
                    reasons=picks["reasons"].apply("; ".join), cautions=picks["cautions"].apply("; ".join),
                    contact=picks["apply"].apply(lambda a: (a or {}).get("contact", "") if isinstance(a, dict) else ""),
                    email=picks["apply"].apply(lambda a: (a or {}).get("email", "") if isinstance(a, dict) else ""),
                    phone=picks["apply"].apply(lambda a: (a or {}).get("phone", "") if isinstance(a, dict) else ""),
                    deadlines=picks["apply"].apply(lambda a: (a or {}).get("deadlines", "") if isinstance(a, dict) else ""),
                )[["score", "tier", "kind", "name", "city", "state", "ein", "website", "grant_count", "grant_median", "in_state",
                   "contact", "email", "phone", "deadlines", "reasons", "cautions", "url"]]
                st.download_button("Download foundation matches (CSV)", export.to_csv(index=False),
                                   "foundation-matches.csv", "text/csv")

        result_list(f_res, fdn_card, "foundations", "fdn_long", after_matches=fdn_downloads)

# ---------- Florida ----------
if "fl" in TAB:
    with TAB["fl"]:
        if not programs:
            st.warning("Florida program data is not available yet.")
        else:
            tally(fl_res, "programs")
            open_n = sum(1 for p_ in programs if p_["nonprofit_eligible"] and not p_["earmark"])
            st.caption(f"{open_n:,} of {len(programs):,} Florida programs (fiscal year {fy}) are open to nonprofits. "
                       "These are programs, not open calls: check each agency's site for the next window.")
            st.checkbox("Include programs the Legislature set aside for named organizations", value=False,
                        key="fl_ear")

            def fl_card(r):
                with st.container(border=True, key=f"card_fl_{r['id']}"):
                    st.markdown(card_head(r, r["title"], r["url"], [r["agency"], f"CSFA {r['csfa']}", r["assistance"]])
                                + why(r), unsafe_allow_html=True)
                    if store is not None:
                        uiw.save_button(store, who, "florida", r, key=f"save_fl_{r['id']}")
                    with st.expander("Details"):
                        for label, key in (("Objectives", "objectives"), ("Who can apply", "applicant_types"),
                                           ("How to apply", "application"), ("How awards are made", "award"),
                                           ("Deadlines", "deadlines"), ("Restrictions", "restrictions"),
                                           ("Contact", "contact")):
                            if r[key] and r[key].strip().upper() not in ("N/A", "NA", "NONE"):
                                st.markdown(f"**{label}:** {html.escape(r[key][:900])}")
                        if r["web"]:
                            st.markdown(f"**Agency site:** {r['web']}")

            result_list(fl_res, fl_card, "programs", "fl_long")

# ---------- workspace ----------
if store is not None:
    with TAB["workspace"]:
        uiw.render(store, who, ANTHROPIC)

# ---------- checklist ----------
with TAB["ready"]:
    st.header("Getting ready to apply")
    st.markdown(
        """
### For any funder
1. **Your IRS determination letter** showing 501(c)(3) status.
2. **A one-page organization summary:** mission, programs, who you serve, and the results you track.
3. **A simple annual budget** and, for larger requests, your most recent financial statements.
4. **Your board list** and a short bio for your director.

### For federal grants
These registrations take weeks, so start early.

1. **SAM.gov registration and a Unique Entity ID (UEI).** Free, required for every federal applicant, and renewed every year. Start at [sam.gov](https://sam.gov).
2. **A Grants.gov applicant account** linked to your organization. See [Grants.gov applicant registration](https://www.grants.gov/applicants/applicant-registration).

### For foundations
- Read the "How to apply" notes. Many want a short letter of inquiry first, not a full proposal.
- Look at who they funded last year. If they fund groups like yours near you, mention that connection.
- Community foundations in your county are often the best first call, and many run small grant cycles for new nonprofits.

### For Florida state programs
- The state pays grants and contracts to registered vendors. Register at [MyFloridaMarketPlace](https://www.myfloridamarketplace.com) and keep a Florida Substitute W-9 on file with the Department of Financial Services.
- Each agency posts its own application windows. Use the agency link on each program to find the next one.
        """
    )

st.markdown(
    f"<div class='gm-footer' role='contentinfo'><p>{NOTICE}</p>"
    "<p>Federal data from the Grants.gov API, refreshed nightly. Foundation data from IRS Form 990-PF and Form 990 "
    "Schedule I e-file returns. Florida data from the Department of Financial Services Catalog of State Financial "
    "Assistance.</p>"
    "<p>Scores are a starting point for your own review, not a guarantee of eligibility.</p>"
    "<p>Source code: <a href='https://github.com/RendellRich/grant-matcher'>github.com/RendellRich/grant-matcher</a></p>"
    "</div>",
    unsafe_allow_html=True,
)
