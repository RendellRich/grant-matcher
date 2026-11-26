"""What a program's own words and its list say about matching funds, for the "Can we apply?" checklist.

The checklist is drawn in the browser (web/src/ready.ts); this is the same reading in Python, and the two are held
together by shared cases (tests/fixtures/match-statements.json, read by tests/test_match_statements.py and
web/test/match.test.ts). Change a pattern in both. No score reads this: points off for a match come only from a
record's `match` field (grantmatch/rank_more.py).

The rule: "No match required" is said only when the list's field or the words say none is needed. Words that ask for a
match anywhere beside such a line, or a line limited by "unless", "except" or "for ...", make it unclear; and words
that ask for a match are never read as silence.
"""
from __future__ import annotations

import re

REQUIRED, NONE, NOT_STATED = "Match required", "No match required", "Match not stated"

NONE_NEEDED = re.compile(
    r"\bno (?:local |minimum )?match(?:ing)?(?: funds?)?(?: is| are)? required\b"
    r"|\bno match(?:ing)?(?: fund)? requirements?\b"
    r"|\bno cost[- ]shar(?:e|ing)(?: or match(?:ing(?: funds?)?)?)?(?: is| are)? required\b"
    r"|\b(?:match(?:ing(?: funds?)?)?|cost[- ]shar(?:e|ing))(?: is| are)? not (?:required|a requirement)\b"
    r"|\bdo(?:es)? not require (?:a |any )?(?:local )?(?:match(?:ing(?: funds?)?)?|cost[- ]shar(?:e|ing))\b", re.I)
# A "none needed" line that only covers some cases.
LIMITED = re.compile(rf"(?:{NONE_NEEDED.pattern})[\s,]+(?:unless|except|for)\b", re.I)
# Words that ask someone for a match, in the ways the plain patterns below miss.
ASKS = re.compile(
    r"\b(?:must|shall)(?: \w+)? be matched\b(?! (?:to|with (?:a |an |the )?(?:mentors?|volunteers?))\b)"
    r"|\bmatched (?:dollar[- ]for[- ]dollar|on a)\b"
    r"|\brequired to (?:\w+ )?match\b"
    r"|\brequir(?:e|es|ed|ing) (?:a |an )?(?:local |cash |in-kind )?matching\b"
    r"|\bmatching ratios?\b"
    r"|\bmatch (?:rates?|ratios?|requirements?)\b"
    r"|\brequired (?:cash |local |in-kind )?match\b"
    r"|\bmatch(?:es)? required\b"
    r"|\bfor matching purposes\b"
    r"|\b(?:company|funding) match(?:es)?\b"
    r"|\b\d+ ?: ?\d+(?: (?:cash|in-kind|local|funding|or|and))* match"
    r"|\b\d+[- ]to[- ]\d+ (?:cash |funding )?match"
    r"|\bpercent(?:age)? (?:cash |local )?match"
    r"|\bmust (?:\w+ )?(?:provide|contribute)\b[^.]{0,40}\bmatch", re.I)
PLAIN_MATCH = re.compile(
    r"\bmatch (?:is |are )?required\b|\brequires? (?:a )?(?:\d{1,3} ?% )?(?:cash |local )?match\b"
    r"|\b\d{1,3} ?% (?:cash |local )?match\b", re.I)
CASH_ONLY = re.compile(r"\bno cash match", re.I)
MATCH = re.compile(
    r"\b(?:cash|in-kind|local|dollar-for-dollar|\d{1,3} ?%)\s+match\b|\bmatching (?:funds?|requirement|contribution)s?\b"
    r"|\bmatch (?:is |are )?required\b|\brequires? (?:a )?(?:cash )?match\b|\bcost[- ]shar(?:e|ing)\b", re.I)

TEXT_FIELDS = ("applicant_types", "application", "award", "restrictions", "deadlines")


def words(text: str, purpose: str = "") -> dict:
    """{"says": "none" | "mentioned" | "unclear" | "silent", "plain": bool, "asks": bool}. `text` is what a program
    says about applying; `purpose` (its objectives) can only turn silence or "none" into unclear. "silent" means no
    pattern here saw a match asked for, not that the program says nothing, so the card claims no more than that."""
    rest = NONE_NEEDED.sub(" ", text)
    plain = bool(PLAIN_MATCH.search(rest)) and not CASH_ONLY.search(text)
    asks = bool(ASKS.search(f"{rest}\n{NONE_NEEDED.sub(' ', purpose)}"))
    if rest != text:
        limited = asks or bool(PLAIN_MATCH.search(rest)) or bool(LIMITED.search(text))
        says = "unclear" if limited else "none"
    elif CASH_ONLY.search(text):
        says = "unclear"
    elif MATCH.search(text):
        says = "mentioned"
    else:
        says = "unclear" if asks else "silent"
    return {"says": says, "plain": plain, "asks": asks}


def statement(record: dict) -> str:
    """The match line a state, county or city program's card shows (floridaReadiness in web/src/ready.ts), before the
    profile's own answer: a required match reads "Match required" for a profile that can't provide one."""
    if record.get("match"):
        return REQUIRED
    text = " \n ".join(record[k] for k in TEXT_FIELDS if isinstance(record.get(k), str))
    said = words(text, record.get("objectives") or "")
    if not record.get("status"):  # a catalog or hand-kept program: its words only
        return {"none": NONE, "mentioned": REQUIRED}.get(said["says"], NOT_STATED)
    listed = record.get("match_none") is True  # an open call whose list says none is needed
    if listed or said["says"] == "none":
        return NOT_STATED if said["plain"] or said["asks"] or LIMITED.search(text) else NONE
    return REQUIRED if said["plain"] and said["says"] == "mentioned" else NOT_STATED
