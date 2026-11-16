"""The profile's checkbox choices (focus areas, ages, populations) turned into key words.

The lists live in web/src/terms.json so the browser and Python read the same words and score alike.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

TERMS = Path(__file__).resolve().parent.parent / "web" / "src" / "terms.json"


@lru_cache(maxsize=1)
def terms() -> dict:
    return json.loads(TERMS.read_text(encoding="utf-8"))


def expand_keywords(keywords: list[str], focus_areas=(), ages=(), populations=()) -> list[str]:
    """The typed key words first, then each chosen group's words, without repeats (ignoring case)."""
    t = terms()
    out, seen = [], set()

    def add(word: str) -> None:
        w = word.strip()
        if w and w.lower() not in seen:
            seen.add(w.lower())
            out.append(w)

    for k in keywords:
        add(k)
    for group, chosen in (("focus_areas", focus_areas), ("ages", ages), ("populations", populations)):
        for item in t[group]:
            if item["id"] in chosen:
                for w in item["words"]:
                    add(w)
    return out


def minor_keywords(keywords: list[str], focus_areas=(), ages=(), populations=()) -> list[str]:
    """The words only the ages and populations choices added: the scorers count these at half weight."""
    major = {w.lower() for w in expand_keywords(keywords, focus_areas)}
    return [w for w in expand_keywords(keywords, focus_areas, ages, populations) if w.lower() not in major]
