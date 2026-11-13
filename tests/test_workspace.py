import io
from datetime import date

import docx

from grantmatch import workspace as ws
from grantmatch import writer as wr
from grantmatch.store import LocalStore


def test_pipeline_add_dedupe_update_remove(tmp_path):
    store = LocalStore(tmp_path)
    item = {"source": "foundation", "ref": "123", "name": "White Family Foundation", "funder": "White Family Foundation"}
    items, added = ws.add_to_pipeline(store, item, "ren@example.org")
    assert added and items[0]["status"] == "Interested"
    _, added_again = ws.add_to_pipeline(store, item)
    assert not added_again
    item_id = items[0]["id"]
    items = ws.update_pipeline(store, item_id, status="Contacted", deadline="2026-12-01", notes="Called Amy")
    assert items[0]["status"] == "Contacted" and items[0]["notes"] == "Called Amy"
    assert ws.upcoming(items, today=date(2026, 11, 13))[0]["days_left"] == 18
    assert ws.remove_from_pipeline(store, item_id) == []


def test_answer_library_replaces_and_retrieves(tmp_path):
    store = LocalStore(tmp_path)
    ws.save_answer(store, "Describe your program", "Old answer")
    ws.save_answer(store, "Describe your program.", "New answer about structured literacy tutoring")
    ws.save_answer(store, "What is your budget?", "Our annual budget is $80,000.")
    lib = ws.load_library(store)
    assert len(lib) == 2
    top = ws.similar_answers(lib, "Please describe the literacy program you run", k=1)
    assert top[0]["answer"].startswith("New answer")


def test_org_facts_and_gaps(tmp_path):
    store = LocalStore(tmp_path)
    ws.save_org(store, {"legal_name": "Exceed the Odds", "mission": "Literacy for every child"}, "ren")
    org = ws.load_org(store)
    assert org["updated_by"] == "ren"
    assert "EIN" in ws.missing_facts(org) and "Legal name" not in ws.missing_facts(org)


def test_documents_round_trip(tmp_path):
    store = LocalStore(tmp_path)
    saved = ws.save_doc(store, {"kind": "letter", "title": "Letter to X", "text": "Dear X"})
    docs = ws.list_docs(store)
    assert docs[0]["id"] == saved["id"] and docs[0]["text"] == "Dear X"


def _form(*paragraphs) -> bytes:
    d = docx.Document()
    for p in paragraphs:
        d.add_paragraph(p)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def test_fill_docx_inserts_answers_after_questions():
    form = _form("Organization name:", "1. Describe the need your program addresses.", "", "2. How will you measure success?", "")
    filled, count = wr.fill_docx(form, [
        {"question": "Describe the need your program addresses.", "answer": "Many children read below grade level."},
        {"question": "How will you measure success?", "answer": "Reading assessments every eight weeks."},
        {"question": "A question not in the form", "answer": "x"},
    ])
    assert count == 2
    text = [p.text for p in docx.Document(io.BytesIO(filled)).paragraphs]
    i = text.index("1. Describe the need your program addresses.")
    assert text[i + 1] == "Many children read below grade level."
    assert "Reading assessments every eight weeks." in text


def test_extract_text_and_exports():
    assert "Describe" in wr.extract_text(_form("Describe your work"), "form.docx")
    assert wr.extract_text(b"plain text", "q.txt") == "plain text"
    assert docx.Document(io.BytesIO(wr.letter_docx("Dear funder,\nThank you.", {"legal_name": "ETO"}))).paragraphs[0].text == "ETO"
    assert len(docx.Document(io.BytesIO(wr.answers_docx("App", [{"question": "Q1", "answer": "A1"}]))).paragraphs) >= 3


class _FakeBlock:
    type = "text"

    def __init__(self, text):
        self.text = text


class _FakeClient:
    def __init__(self, reply):
        self.reply, self.calls = reply, []
        self.messages = self

    def create(self, **kw):
        self.calls.append(kw)
        return type("Msg", (), {"content": [_FakeBlock(self.reply)]})()


def test_writer_prompts_use_facts_examples_and_clean_dashes():
    w = wr.Writer.__new__(wr.Writer)
    w.model, w.client = "test", _FakeClient("Dear friends — thank you.")
    out = w.letter_of_inquiry({"legal_name": "Exceed the Odds", "mission": "Literacy"},
                              {"name": "White Family Foundation", "top_purposes": ["youth literacy"]},
                              [{"question": "Mission", "answer": "We teach reading."}], "$5,000", "tutoring")
    assert "—" not in out
    prompt = w.client.calls[0]["messages"][0]["content"]
    assert "Exceed the Odds" in prompt and "White Family Foundation" in prompt and "We teach reading." in prompt
    assert "em dash" in w.client.calls[0]["system"]


def test_extract_questions_parses_json():
    w = wr.Writer.__new__(wr.Writer)
    w.model, w.client = "test", _FakeClient('Here: [{"question": "Describe the need.", "limit": "250 words"}]')
    assert w.extract_questions("form text") == [{"question": "Describe the need.", "limit": "250 words"}]
