"""Streamlit screens for the signed-in workspace."""
from __future__ import annotations

import html
from datetime import date

import pandas as pd
import streamlit as st

from . import workspace as ws
from . import writer as wr

PRIVACY = ("Saved to your private workspace. Never enter children's names, family details, or anything "
           "that could identify a student or family.")


def funder_snapshot(source: str, r) -> dict:
    """What the pipeline keeps about a funder, enough to draft from later."""
    def g(key, default=""):
        v = r.get(key, default) if hasattr(r, "get") else default
        return default if v is None or (isinstance(v, float) and pd.isna(v)) else v

    if source == "federal":
        close = g("close_date")
        return {"source": source, "ref": str(g("id")), "name": g("title"), "funder": g("agency"),
                "url": g("url"), "deadline": close or "", "amount": g("award_range"),
                "details": {"name": g("agency"), "mission": g("description")[:1500], "notes": g("number")}}
    if source == "florida":
        return {"source": source, "ref": str(g("id")), "name": g("title"), "funder": g("agency"),
                "url": g("web") or g("url"), "deadline": "", "amount": "",
                "details": {"name": g("agency"), "mission": g("objectives")[:1500],
                            "apply": {"how": g("application")[:600], "contact": g("contact")[:300]}}}
    apply = g("apply", {})
    return {"source": "foundation", "ref": str(g("ein")), "name": str(g("name")).title(), "funder": str(g("name")).title(),
            "url": g("website") or g("url"), "deadline": "", "amount": f"typical ${g('grant_median', 0) or 0:,.0f}",
            "details": {"name": str(g("name")).title(), "kind": g("kind"), "city": str(g("city")).title(), "state": g("state"),
                        "grant_median": g("grant_median"), "top_purposes": list(g("top_purposes", []) or [])[:12],
                        "apply": apply if isinstance(apply, dict) else {}, "mission": g("mission"),
                        "sample_grants": list(g("sample_grants", []) or [])[:8]}}


def _url(u: str) -> str:
    u = (u or "").strip()
    return u if not u or u.lower().startswith(("http://", "https://")) else "https://" + u.lower()


def save_button(store, who: str, source: str, r, key: str) -> None:
    if st.button("Save to pipeline", key=key):
        item = funder_snapshot(source, r)
        item["url"] = _url(item.get("url", ""))
        _, added = ws.add_to_pipeline(store, item, who)
        st.toast("Saved to your pipeline" if added else "Already in your pipeline")


def render(store, who: str, writer_key: str | None) -> None:
    t_pipe, t_write, t_org, t_lib, t_docs = st.tabs(["Pipeline", "Write", "Organization", "Answer library", "Documents"])
    with t_pipe:
        _pipeline(store, who)
    with t_write:
        _write(store, who, writer_key)
    with t_org:
        _organization(store, who)
    with t_lib:
        _library(store, who)
    with t_docs:
        _documents(store)


def _pipeline(store, who: str) -> None:
    items = ws.load_pipeline(store)
    if not items:
        st.info("Nothing saved yet. Use **Save to pipeline** on any federal grant, foundation, or Florida program.")
        return
    soon = ws.upcoming(items)
    if soon:
        st.markdown("**Coming up:** " + "; ".join(f"{html.escape(i['name'])} in {i['days_left']} days" for i in soon[:5]))
    df = pd.DataFrame(items)
    for col in ("deadline", "next_step", "notes", "amount", "url"):
        if col not in df:
            df[col] = ""
    df["deadline"] = pd.to_datetime(df["deadline"], errors="coerce").dt.date
    edited = st.data_editor(
        df[["id", "name", "funder", "status", "deadline", "next_step", "notes", "amount", "url"]],
        hide_index=True, use_container_width=True, key="pipeline_editor",
        column_config={
            "id": None,
            "name": st.column_config.TextColumn("Opportunity", disabled=True),
            "funder": st.column_config.TextColumn("Funder", disabled=True),
            "status": st.column_config.SelectboxColumn("Status", options=ws.STATUSES, required=True),
            "deadline": st.column_config.DateColumn("Deadline"),
            "next_step": st.column_config.TextColumn("Next step"),
            "notes": st.column_config.TextColumn("Notes"),
            "amount": st.column_config.TextColumn("Amount", disabled=True),
            "url": st.column_config.LinkColumn("Link", display_text="Open"),
        })
    c1, c2 = st.columns([1, 3])
    if c1.button("Save changes", type="primary"):
        for _, row in edited.iterrows():
            ws.update_pipeline(store, row["id"], who, status=row["status"],
                               deadline=row["deadline"].isoformat() if pd.notna(row["deadline"]) else "",
                               next_step=row["next_step"] or "", notes=row["notes"] or "")
        st.success("Pipeline saved.")
    with c2.popover("Remove an item"):
        pick = st.selectbox("Item", items, format_func=lambda i: i["name"], key="rm_pick")
        if st.button("Remove", key="rm_go"):
            ws.remove_from_pipeline(store, pick["id"])
            st.rerun()


def _organization(store, who: str) -> None:
    org = ws.load_org(store)
    st.caption("These facts feed every draft. Fill them once and update them as things change. " + PRIVACY)
    with st.form("org_form"):
        values = {}
        for key, label, help_ in ws.ORG_FIELDS:
            long = key in {"mission", "programs", "population", "budget", "outcomes", "board", "partners", "story", "team"}
            widget = st.text_area if long else st.text_input
            values[key] = widget(label, org.get(key, ""), help=help_ or None, key=f"org_{key}")
        if st.form_submit_button("Save organization facts", type="primary"):
            ws.save_org(store, values, who)
            st.success("Saved.")
    gaps = ws.missing_facts(org)
    if gaps:
        st.warning("Drafts will leave placeholders for: " + ", ".join(gaps))


def _library(store, who: str) -> None:
    lib = ws.load_library(store)
    st.caption("Every answer you approve lands here and is reused in later drafts, so the drafts sound more like "
               "you over time. Paste answers from past applications to give it a head start.")
    with st.expander("Add an answer from a past application"):
        with st.form("lib_add", clear_on_submit=True):
            q = st.text_input("Question")
            a = st.text_area("Your answer", height=160)
            if st.form_submit_button("Save answer") and q.strip() and a.strip():
                ws.save_answer(store, q, a, kind="answer", who=who)
                st.success("Saved to the library.")
                st.rerun()
    if not lib:
        st.write("No approved answers yet.")
    for a in sorted(lib, key=lambda x: x.get("saved_at", ""), reverse=True):
        with st.container(border=True):
            st.markdown(f"**{html.escape(a['question'])}**  \n<span class='meta'>{a.get('kind', 'answer')}"
                        f"{' for ' + html.escape(a['funder']) if a.get('funder') else ''} | saved {a.get('saved_at', '')[:10]}</span>",
                        unsafe_allow_html=True)
            st.write(a["answer"])
            if st.button("Delete", key=f"del_{a['id']}"):
                ws.delete_answer(store, a["id"])
                st.rerun()


def _documents(store) -> None:
    docs = ws.list_docs(store)
    if not docs:
        st.write("Approved letters and applications will be listed here.")
        return
    org = ws.load_org(store)
    for d in docs:
        with st.container(border=True):
            st.markdown(f"**{html.escape(d.get('title', 'Document'))}**  \n<span class='meta'>{d.get('kind', '')} | "
                        f"updated {d.get('updated_at', '')[:10]}</span>", unsafe_allow_html=True)
            if d.get("kind") == "letter":
                st.download_button("Download Word file", wr.letter_docx(d.get("text", ""), org),
                                   f"{_slug(d.get('title', 'letter'))}.docx", key=f"dl_{d['id']}")
            else:
                st.download_button("Download Word file", wr.answers_docx(d.get("title", "Application"), d.get("answers", [])),
                                   f"{_slug(d.get('title', 'application'))}.docx", key=f"dl_{d['id']}")


def _write(store, who: str, writer_key: str | None) -> None:
    if not writer_key:
        st.warning("Drafting needs a Claude API key in the app's secrets ([anthropic] api_key).")
        return
    writer = wr.Writer(writer_key)
    org = ws.load_org(store)
    if ws.missing_facts(org):
        st.info("Tip: fill in the Organization tab first. Drafts use only the facts saved there.")
    items = ws.load_pipeline(store)
    mode = st.radio("What do you want to write?", ["Letter of inquiry", "Fill in an application"], horizontal=True)
    funder_pick = st.selectbox("For which funder", [None] + items,
                               format_func=lambda i: "Choose from your pipeline" if i is None else f"{i['name']} ({i['status']})")
    funder = (funder_pick or {}).get("details", {}) if funder_pick else {}
    lib = ws.load_library(store)

    if mode == "Letter of inquiry":
        c1, c2 = st.columns(2)
        ask = c1.text_input("Amount to ask for", placeholder="$10,000")
        project = c2.text_input("For what", placeholder="Reading tutoring for 30 students this spring")
        if st.button("Draft letter", type="primary", disabled=not funder_pick):
            examples = ws.similar_answers(lib, f"letter of inquiry {project}", k=3, kind="letter") + \
                ws.similar_answers(lib, project or "mission and programs", k=3, kind="answer")
            with st.spinner("Drafting"):
                st.session_state["loi_text"] = writer.letter_of_inquiry(org, funder, examples, ask, project)
        if st.session_state.get("loi_text"):
            text = st.text_area("Edit the draft, then approve it", st.session_state["loi_text"], height=420, key="loi_edit")
            if st.button("Approve and save", type="primary"):
                name = funder_pick["name"] if funder_pick else "funder"
                ws.save_doc(store, {"kind": "letter", "title": f"Letter of inquiry to {name}", "text": text,
                                    "funder": name, "ask": ask, "project": project}, who)
                ws.save_answer(store, f"Letter of inquiry: {project or 'general support'}", text, funder=name, kind="letter", who=who)
                st.success("Saved to Documents, and added to the answer library for future drafts.")
            st.download_button("Download Word file", wr.letter_docx(text, org), "letter-of-inquiry.docx")
        return

    upload = st.file_uploader("Upload the funder's application (Word, PDF, or text)", type=["docx", "pdf", "txt"])
    if upload and st.button("Find the questions", type="primary"):
        raw = upload.getvalue()
        st.session_state["app_file"] = (upload.name, raw)
        with st.spinner("Reading the form"):
            st.session_state["app_qs"] = writer.extract_questions(wr.extract_text(raw, upload.name))
        st.session_state.pop("app_answers", None)
    qs = st.session_state.get("app_qs")
    if not qs:
        return
    st.write(f"Found {len(qs)} questions.")
    if st.button("Draft all answers"):
        answers = []
        bar = st.progress(0.0)
        for n, q in enumerate(qs, 1):
            answers.append(writer.answer(org, q["question"], q["limit"], ws.similar_answers(lib, q["question"], k=4), funder))
            bar.progress(n / len(qs))
        st.session_state["app_answers"] = answers
    answers = st.session_state.get("app_answers")
    if not answers:
        for q in qs:
            st.markdown(f"- {html.escape(q['question'])}" + (f" *({q['limit']})*" if q["limit"] else ""))
        return
    final = []
    for n, (q, a) in enumerate(zip(qs, answers)):
        label = q["question"] + (f" ({q['limit']})" if q["limit"] else "")
        final.append({"question": q["question"], "answer": st.text_area(label, a, height=180, key=f"ans_{n}")})
    title = st.text_input("Save as", f"Application to {funder_pick['name']}" if funder_pick else "Application")
    if st.button("Approve all and save", type="primary"):
        ws.save_doc(store, {"kind": "application", "title": title, "answers": final,
                            "funder": funder_pick["name"] if funder_pick else ""}, who)
        for qa in final:
            if qa["answer"].strip():
                ws.save_answer(store, qa["question"], qa["answer"], funder=funder_pick["name"] if funder_pick else "", who=who)
        st.success("Saved. Your edited answers are now in the library and will shape the next application.")
    c1, c2 = st.columns(2)
    c1.download_button("Download answers (Word)", wr.answers_docx(title, final), f"{_slug(title)}.docx")
    name, raw = st.session_state.get("app_file", ("", b""))
    if name.lower().endswith(".docx"):
        filled, count = wr.fill_docx(raw, final)
        c2.download_button(f"Download their form, filled in ({count} of {len(final)} placed)", filled,
                           f"{_slug(title)}-filled.docx")


def _slug(s: str) -> str:
    import re

    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60] or "document"
