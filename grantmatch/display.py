"""Tidy raw IRS text for display. Display only: the data and the ranking never see these changes.

Most 990-PF fields arrive in ALL CAPS. Plain title case gets names wrong ("Mcwethy", "O'donnell",
"C/o") and keeps words such as "OR" and "IN" in capitals because they look like state codes.
"""
import re

STATES = ["AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DC", "DE", "FL", "GA", "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA",
          "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR",
          "PA", "PR", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY"]

EMPTY_VALUES = {"", "NONE", "N/A", "NA", "NOT APPLICABLE", "0", "-", "NULL"}
# Kept in capitals wherever they appear.
ACRONYMS = {"PO", "LLC", "LLP", "USA", "US", "YMCA", "YWCA", "II", "III", "IV", "CPA", "MD", "PA", "PC",
            "FBO", "DBA", "FKA", "AKA", "UA", "UAD", "IRA", "TTEE", "JTWROS", "PHD", "DDS", "VA", "MBA", "LGBTQ", "USF", "UCF",
            "FSU", "UF", "FIU", "FAU"}
DIRECTIONS = {"N", "S", "E", "W", "NE", "NW", "SE", "SW"}
# Single letters are left out: in a name "A" is almost always an initial.
SMALL_WORDS = {"and", "of", "the", "for", "in", "to", "an", "at", "by", "on", "or", "de", "la", "del"}
# Two-letter words with no vowel that are words, not initials.
NOT_INITIALS = {"DR", "ST", "JR", "SR", "MR", "MS", "RD", "CT", "PL", "LN", "FT", "MT", "PT", "BR", "SQ", "TR", "FR"}
# Words after which a lone "A" is the article ("Make a Wish"), not an initial ("Ruth A Gilmore").
BEFORE_ARTICLE = {"MAKE", "LEND", "GIVE", "GET", "BE", "BUILD", "ADOPT", "SPONSOR", "FEED", "SAVE", "HAVE", "FOR", "WITH",
                  "AS", "IS", "ONCE", "FIND", "PLANT", "SHARE", "TAKE", "HOLD", "OPEN", "LIGHT", "CHANGE", "START", "HELP"}
STATE_SCHOOL = {"STATE", "UNIVERSITY", "UNIV", "SOCIETY", "TECH"}
ZIP = re.compile(r"^\d{5}(-\d{4})?$")


def _s(value) -> str:
    return value if isinstance(value, str) else ""


def present(value) -> str:
    """The value as text, or '' when the return left it empty or wrote NONE or N/A."""
    text = _s(value).strip()
    return "" if text.upper() in EMPTY_VALUES else text


def shouting(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    return len(letters) > 3 and sum(c.isupper() for c in letters) / len(letters) > 0.8


def _cap(part: str) -> str:
    """Capitalise one name part: McWethy, O'Donnell, D'Addario."""
    if not part:
        return part
    low = part.lower()
    if re.fullmatch(r"mc[a-z]{2,}", low):
        return "Mc" + low[2:].capitalize()
    if re.fullmatch(r"[od]'[a-z]{2,}", low):
        return low[0].upper() + "'" + low[2:].capitalize()
    return low.capitalize()


def _word(core: str) -> str:
    """Case one word that has no surrounding punctuation."""
    if core == "C/O":
        return "c/o"
    if any(c.isdigit() for c in core):
        letters = sum(c.isalpha() for c in core)
        if re.fullmatch(r"\d+(ST|ND|RD|TH)", core):
            return core.lower()  # 11th, 2nd
        return core if letters <= 2 else core.capitalize()  # 5C, 1501N, 3PT stay; SOAR365 becomes Soar365
    if core in ACRONYMS:
        return core
    if len(core) == 2 and core.isalpha() and not re.search(r"[AEIOUY]", core) and core not in NOT_INITIALS:
        return core  # initials such as JC or RB
    if "&" in core:  # A&M, AT&T
        return core if all(len(p) <= 2 for p in core.split("&")) else "&".join(_cap(p) for p in core.split("&"))
    return "-".join(_cap(p) for p in core.split("-"))


def tidy_name(value, kind: str = "name") -> str:
    """Title case for ALL CAPS names, cities and addresses.

    kind is "name" (people and organizations), "city", or "address". State codes stay in capitals
    only before a ZIP code or as the last word, so "OR" and "IN" inside a name read as words.
    """
    text = present(value)
    if not shouting(text):
        return text
    tokens = text.split()
    out = []
    for i, w in enumerate(tokens):
        m = re.fullmatch(r"([(\"']*)(.*?)([).,;:\"']*)", w)
        lead, core, tail = m.groups()
        up = core.upper()
        nxt = tokens[i + 1].strip(".,") if i + 1 < len(tokens) else ""
        last = i == len(tokens) - 1
        if not core:
            word = core
        elif up == "CO" and nxt.upper() in ("INC", "LLC", "LTD", "LLP"):
            word = "Co"  # company: "Thriving Grant Co Inc"
        elif up == "CO" and not last and kind != "city":
            word = "c/o"  # "care of", often cut to CO on the return; at the end it is Colorado
        elif up in STATES and (ZIP.match(nxt) or (last and i) or nxt.upper() in STATE_SCHOOL or (up == "UT" and i == 0)
                                  or (i and tokens[i - 1].upper() in ("NE", "NW", "SE", "SW"))):
            word = up  # "Boston MA 02199", "Seattle WA", "GA State University", "National MS Society", "UT Dallas"
        elif up == "A" and i and tokens[i - 1].strip(".,").upper().rstrip("'") in BEFORE_ARTICLE | {"CHASIN"}                 or up == "A" and i and re.search(r"(ING|IN')$", tokens[i - 1].upper()):
            word = "a"
        elif up in ("NE", "NW", "SE", "SW") or (kind == "address" and up in DIRECTIONS):
            word = up
        elif lead.startswith("(") and tail.startswith(")") and len(core) <= 6 and core.isalpha():
            word = up  # an acronym in brackets: (MANNA), (LISC)
        elif i and core.lower() in SMALL_WORDS:
            word = core.lower()
        else:
            word = _word(up)
        out.append(lead + word + tail)
    return " ".join(out)


def tidy_text(value) -> str:
    """Sentence case for ALL CAPS sentences such as missions, purposes and instructions."""
    text = present(value)
    return text[:1].upper() + text[1:].lower() if shouting(text) else text
