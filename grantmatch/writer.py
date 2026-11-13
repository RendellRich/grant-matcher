"""Drafting with Claude: letters of inquiry and application answers, plus Word export and form filling.

Every draft is built from three things only: the organization facts you saved, what is known about the
funder, and answers you approved before. Missing facts become [bracketed placeholders] instead of
guesses, so nothing invented goes out under your name.
"""
from __future__ import annotations

import io
import json
import re

MODEL = "claude-sonnet-5-5"

SYSTEM = """You write grant materials for a small nonprofit. Rules:
- Use only the facts provided. If a fact you need is missing, write a short placeholder in square brackets, like [number of students served in 2026], instead of guessing.
- Never invent numbers, names, dates, partners, or outcomes.
- When past approved answers are provided, reuse their facts and phrasing where they fit. They are the organization's own voice.
- Plain, warm, specific language. Short paragraphs. Active voice. No jargon, no hype, no cliches.
- Do not use em dashes. Use commas, periods, or separate sentences instead.
- Never include information that could identify a child or family.
- Return only the requested text, with no preamble or commentary."""

ORG_ORDER = ["legal_name", "ein", "founded", "address", "website", "contact_name", "contact_title", "contact_email",
             "contact_phone", "mission", "programs", "population", "geography", "budget", "team", "outcomes", "board",
             "partners", "story", "uei"]


def org_context(org: dict) -> str:
    lines = [f"{k.replace('_', ' ')}: {str(org[k]).strip()}" for k in ORG_ORDER if str(org.get(k, "")).strip()]
    return "\n".join(lines) or "(no organization facts saved yet)"


def examples_block(examples: list[dict]) -> str:
    if not examples:
        return "(none yet)"
    return "\n\n".join(f"Question: {e['question']}\nApproved answer: {e['answer']}" for e in examples)


def funder_context(f: dict) -> str:
    parts = [f"Funder: {f.get('name', '')}"]
    for key, label in (("kind", "Type"), ("city", "City"), ("state", "State"), ("grant_median", "Typical grant"),
                       ("top_purposes", "What it funded"), ("apply", "How to apply"), ("mission", "Funder mission"),
                       ("notes", "Our notes")):
        val = f.get(key)
        if not val:
            continue
        if isinstance(val, list):
            val = "; ".join(map(str, val[:15]))
        if isinstance(val, dict):
            val = "; ".join(f"{k}: {v}" for k, v in val.items() if v)
        parts.append(f"{label}: {val}")
    grants = f.get("sample_grants") or []
    if grants:
        parts.append("Recent grants: " + "; ".join(
            f"{g.get('to', '')} ({g.get('city', '')}, {g.get('state', '')}) ${g.get('amount', 0):,.0f} for {g.get('purpose', '')}"
            for g in grants[:10]))
    return "\n".join(parts)


class Writer:
    def __init__(self, api_key: str, model: str = MODEL):
        import anthropic

        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def _ask(self, prompt: str, max_tokens: int = 1500) -> str:
        msg = self.client.messages.create(model=self.model, max_tokens=max_tokens, system=SYSTEM,
                                          messages=[{"role": "user", "content": prompt}])
        text = "".join(block.text for block in msg.content if getattr(block, "type", "") == "text")
        return clean(text)

    def letter_of_inquiry(self, org: dict, funder: dict, examples: list[dict], ask: str = "", project: str = "") -> str:
        prompt = f"""Write a one-page letter of inquiry from our organization to this funder.

Our organization:
{org_context(org)}

{funder_context(funder)}

What we want to ask for: {ask or '[amount]'}
Project or purpose: {project or 'general operating support for our programs'}

Past approved writing to reuse where it fits:
{examples_block(examples)}

Structure: date and greeting, one paragraph on who we are, one on the need and what we do about it, one linking our work to what this funder already supports (name a recent grantee or purpose of theirs when it fits), the ask, and a short close signed by our grants contact. Under 400 words."""
        return self._ask(prompt, 1200)

    def extract_questions(self, document_text: str) -> list[dict]:
        prompt = f"""This is a grant application form. List every question or prompt the applicant must answer in writing,
in order. Skip plain fields like name, address, EIN, or phone. Return JSON only: a list of objects with
"question" (exact wording) and "limit" (word or character limit as written, or "" if none).

Form text:
{document_text[:30000]}"""
        raw = self._ask(prompt, 3000)
        match = re.search(r"\[.*\]", raw, re.S)
        try:
            items = json.loads(match.group(0) if match else raw)
        except json.JSONDecodeError:
            return []
        return [{"question": str(i.get("question", "")).strip(), "limit": str(i.get("limit", "")).strip()}
                for i in items if isinstance(i, dict) and i.get("question")]

    def answer(self, org: dict, question: str, limit: str, examples: list[dict], funder: dict | None = None) -> str:
        prompt = f"""Answer this grant application question for our organization.

Question: {question}
Length limit: {limit or 'about 150 words'}

Our organization:
{org_context(org)}

{funder_context(funder) if funder else ''}

Past approved answers to reuse where they fit:
{examples_block(examples)}"""
        return self._ask(prompt, 1200)


def clean(text: str) -> str:
    """Belt and braces for the writing rules."""
    text = text.replace(" — ", ", ").replace("—", ", ").replace(" – ", ", ")
    return text.strip()


# ---------- files ----------

def extract_text(data: bytes, filename: str) -> str:
    name = filename.lower()
    if name.endswith(".pdf"):
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    if name.endswith(".docx"):
        import docx

        d = docx.Document(io.BytesIO(data))
        parts = [p.text for p in d.paragraphs]
        for table in d.tables:
            for row in table.rows:
                parts.append(" | ".join(c.text for c in row.cells))
        return "\n".join(parts)
    return data.decode("utf-8", errors="replace")


def letter_docx(text: str, org: dict) -> bytes:
    import docx
    from docx.shared import Pt

    d = docx.Document()
    style = d.styles["Normal"]
    style.font.name, style.font.size = "Calibri", Pt(11)
    if org.get("legal_name"):
        head = d.add_paragraph()
        run = head.add_run(org["legal_name"])
        run.bold = True
        for line in (org.get("address", ""), org.get("website", "")):
            if line:
                d.add_paragraph(line)
    for para in text.split("\n"):
        d.add_paragraph(para)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def answers_docx(title: str, qas: list[dict]) -> bytes:
    import docx

    d = docx.Document()
    d.add_heading(title, level=1)
    for qa in qas:
        d.add_heading(qa["question"], level=3)
        for para in qa.get("answer", "").split("\n"):
            d.add_paragraph(para)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def fill_docx(original: bytes, qas: list[dict]) -> tuple[bytes, int]:
    """Insert each answer right after its question in a copy of the funder's own Word form.
    Returns the new file and how many questions were found and filled."""
    import copy

    import docx
    from docx.text.paragraph import Paragraph

    d = docx.Document(io.BytesIO(original))
    filled = 0
    paragraphs = list(d.paragraphs)
    for qa in qas:
        target = _norm(qa["question"])[:80]
        for p in paragraphs:
            if target and target in _norm(p.text):
                new_p = copy.deepcopy(p._p)
                p._p.addnext(new_p)
                para = Paragraph(new_p, p._parent)
                for run in para.runs[1:]:
                    run._r.getparent().remove(run._r)
                if para.runs:
                    para.runs[0].text = qa.get("answer", "")
                    para.runs[0].bold = False
                else:
                    para.add_run(qa.get("answer", ""))
                filled += 1
                break
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue(), filled


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", s.lower())).strip()
