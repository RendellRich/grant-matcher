"""Workspace data: organization facts, funder pipeline, answer library, and saved documents."""
from __future__ import annotations

import re
import uuid
from datetime import date, datetime, timezone

ORG_FIELDS = [
    ("legal_name", "Legal name", ""),
    ("ein", "EIN", "Federal tax ID, like 12-3456789"),
    ("uei", "SAM.gov UEI", "Only needed for federal grants"),
    ("founded", "Year founded", ""),
    ("address", "Mailing address", ""),
    ("website", "Website", ""),
    ("contact_name", "Grants contact", "Who signs letters and takes calls"),
    ("contact_title", "Contact title", ""),
    ("contact_email", "Contact email", ""),
    ("contact_phone", "Contact phone", ""),
    ("mission", "Mission", "One or two sentences"),
    ("programs", "Programs", "What you do, one program per line"),
    ("population", "Who you serve", "Ages, needs, income levels, how many"),
    ("geography", "Where you serve", "Cities and counties"),
    ("budget", "Annual budget", "Total, and how it is spent"),
    ("team", "Staff and volunteers", ""),
    ("outcomes", "Results so far", "Numbers you can stand behind, with dates"),
    ("board", "Board", "Names and roles"),
    ("partners", "Partners", "Schools, agencies, and other groups you work with"),
    ("story", "A short story", "One family's or child's experience, shared with permission and without identifying details"),
]
STATUSES = ["Interested", "Contacted", "Applied", "Awarded", "Declined"]
ORG_FILE, PIPELINE_FILE, LIBRARY_FILE, PROFILE_FILE = "org.json", "pipeline.json", "library.json", "profile.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------- organization ----------

def load_org(store) -> dict:
    return store.read(ORG_FILE, {}) or {}


def save_org(store, org: dict, who: str = "") -> None:
    store.write(ORG_FILE, {**org, "updated_at": _now(), "updated_by": who}, "Update organization facts")


def missing_facts(org: dict) -> list[str]:
    key = {"legal_name", "ein", "mission", "programs", "population", "geography", "budget", "contact_name"}
    return [label for k, label, _ in ORG_FIELDS if k in key and not str(org.get(k, "")).strip()]


# ---------- pipeline ----------

def load_pipeline(store) -> list[dict]:
    return store.read(PIPELINE_FILE, []) or []


def add_to_pipeline(store, item: dict, who: str = "") -> tuple[list[dict], bool]:
    items = load_pipeline(store)
    if any(i["source"] == item["source"] and i["ref"] == item["ref"] for i in items):
        return items, False
    items.append({
        "id": uuid.uuid4().hex[:10], "status": "Interested", "notes": "", "next_step": "",
        "added_at": _now(), "added_by": who, "updated_at": _now(), **item,
    })
    store.write(PIPELINE_FILE, items, f"Add {item.get('name', 'funder')} to pipeline")
    return items, True


def update_pipeline(store, item_id: str, who: str = "", **changes) -> list[dict]:
    items = load_pipeline(store)
    for i in items:
        if i["id"] == item_id:
            i.update(changes, updated_at=_now(), updated_by=who)
    store.write(PIPELINE_FILE, items, "Update pipeline")
    return items


def remove_from_pipeline(store, item_id: str) -> list[dict]:
    items = [i for i in load_pipeline(store) if i["id"] != item_id]
    store.write(PIPELINE_FILE, items, "Remove from pipeline")
    return items


def upcoming(items: list[dict], today: date | None = None, days: int = 45) -> list[dict]:
    today = today or date.today()
    out = []
    for i in items:
        try:
            d = date.fromisoformat(str(i.get("deadline", ""))[:10])
        except ValueError:
            continue
        if 0 <= (d - today).days <= days and i["status"] not in ("Awarded", "Declined"):
            out.append({**i, "days_left": (d - today).days})
    return sorted(out, key=lambda i: i["days_left"])


# ---------- answer library (how the workspace learns) ----------

def load_library(store) -> list[dict]:
    return store.read(LIBRARY_FILE, []) or []


def save_answer(store, question: str, answer: str, funder: str = "", kind: str = "answer", who: str = "") -> list[dict]:
    """Approved text is saved and reused as an example in later drafts. A newer answer to the same
    question replaces the older one, so the library keeps your latest wording."""
    lib = load_library(store)
    norm = _norm(question)
    lib = [a for a in lib if not (_norm(a["question"]) == norm and a.get("kind") == kind)]
    lib.append({"id": uuid.uuid4().hex[:10], "question": question.strip(), "answer": answer.strip(),
                "funder": funder, "kind": kind, "saved_at": _now(), "saved_by": who})
    store.write(LIBRARY_FILE, lib, "Save approved answer")
    return lib


def delete_answer(store, answer_id: str) -> list[dict]:
    lib = [a for a in load_library(store) if a["id"] != answer_id]
    store.write(LIBRARY_FILE, lib, "Remove answer")
    return lib


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()


def similar_answers(library: list[dict], question: str, k: int = 4, kind: str | None = None) -> list[dict]:
    """Past approved answers most like this question, for the drafter to reuse."""
    pool = [a for a in library if kind is None or a.get("kind") == kind]
    if not pool:
        return []
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    texts = [a["question"] + " " + a["answer"][:400] for a in pool]
    vec = TfidfVectorizer(stop_words="english", ngram_range=(1, 2)).fit(texts + [question])
    sims = cosine_similarity(vec.transform([question]), vec.transform(texts)).ravel()
    ranked = sorted(zip(sims, pool), key=lambda x: -x[0])
    return [a for s, a in ranked[:k] if s > 0.05] or [a for _, a in ranked[:1]]


# ---------- saved documents ----------

def save_doc(store, doc: dict, who: str = "") -> dict:
    doc = {**doc, "id": doc.get("id") or uuid.uuid4().hex[:10], "updated_at": _now(), "updated_by": who}
    doc.setdefault("created_at", _now())
    store.write(f"docs/{doc['id']}.json", doc, f"Save {doc.get('title', 'document')}")
    return doc


def list_docs(store) -> list[dict]:
    docs = [store.read(f"docs/{name}") for name in store.list("docs")]
    return sorted([d for d in docs if d], key=lambda d: d.get("updated_at", ""), reverse=True)
