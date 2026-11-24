"""Iowa state grants from IowaGrants.gov, the state's grants system.

Iowa agencies post their funding opportunities on IowaGrants (a WebGrants site); its public storefront,
www.iowagrants.gov/storefrontFOList.do, lists every posted one with its ID, agency, program, title, posted date
and final application deadline. Each opportunity's public page adds the award range, project dates, whether it
recurs, the program officer and a description.

Iowa's listing has no field for who may apply; that is in the description, or only in the attached RFP. So
who may apply is read from the description: a description that names nonprofits keeps the grant; one that
limits it to cities, counties, school districts, employers or taxpayers leaves nonprofits out; and one that says
neither is kept, with a note on its card to read the notice. Department of Education grants that don't name
nonprofits are taken as school and district grants.

Records use the same fields as California's (grantmatch/california.py), so the same scorer reads them.

Run:  python -m grantmatch.iowa --out data/iowa.json.gz [--skipped build/skipped-iowa.json.gz]
"""
from __future__ import annotations

import argparse
import gzip
import html
import json
import re
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests

BASE = "https://www.iowagrants.gov/"
LIST = BASE + "storefrontFOList.do"
MIN_ROWS = 5  # Iowa posts a dozen or two at a time; fewer than this means the page changed
PAUSE = 0.5

session = requests.Session()
session.headers.update({"User-Agent": "grant-matcher (github.com/RendellRich/grant-matcher)"})

NONPROFIT = re.compile(r"non-?\s?profit|not-for-profit|community[- ]based organi[sz]ation|501\s*\(c\)|"
                       r"community action agenc", re.I)
NO_NONPROFIT = re.compile(r"\b(?:no|not|nor|ineligible|cannot)\b[^.]{0,50}(?:non-?\s?profit|not-for-profit)"
                          r"|(?:non-?\s?profit|not-for-profit)s?\b[^.;]{0,25}\b(?:not|ineligible|cannot)\b", re.I)
_WHO = r"(?:cit(?:y|ies)|count(?:y|ies)|school districts?|districts|local government|government agenc|state of iowa|" \
       r"community colleges?|school food authorit|SFAs?|taxpayers?|employers?|businesses|manufactur)"
ONLY_OTHERS = re.compile(
    rf"\b(?:must be|only|limited to|restricted to|must include|is open to)\b[^.]{{0,60}}\b{_WHO}"
    rf"|\b{_WHO}\w*\s+(?:must be the applicant|may apply|are eligible)"
    rf"|\beligible (?:applicants?|borrowers?)\W+(?:are\s+)?{_WHO}", re.I)
INVITATION = re.compile(r"\bby invitation only\b|\binvitation[- ]only\b", re.I)


def _clean(s: str | None) -> str:
    s = re.sub(r"<\s*(?:br|p|li|h\d|div)\b[^>]*>", " ", s or "", flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", html.unescape(s).replace("\xa0", " ")).strip()


def _day(s: str | None) -> str | None:
    s = _clean(s)
    for fmt in ("%b %d, %Y %I:%M %p", "%b %d, %Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def list_rows(page: str) -> list[dict]:
    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", page, re.S | re.I):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S | re.I)
        if len(cells) < 8:
            continue
        link = re.search(r"href=['\"]([^'\"]*viewStorefrontOpportunity[^'\"]*)['\"]", cells[5])
        if not link:
            continue
        due = _clean(cells[7])
        rows.append({
            "id": _clean(cells[0]), "status": _clean(cells[1]), "categories": _clean(cells[2]).replace(",", ", "),
            "agency": _clean(cells[3]), "program": _clean(cells[4]), "title": _clean(cells[5]),
            "posted": _day(cells[6]), "closes": _day(due), "no_end": not _day(due),
            "detail": urljoin(BASE, html.unescape(link.group(1))),
        })
    return rows


def fields(page: str) -> dict[str, str]:
    """The label/value pairs on an opportunity page, and its description."""
    out = {}
    for label, value in re.findall(r"<span class='field-label'>([^<]+)</span>\s*<span class='field'>(.*?)</span>\s*</p>",
                                   page, re.S | re.I):
        out[_clean(label)] = _clean(value)
    out.pop("Email", None)  # the site hides addresses from scripts; the program officer's name and phone are enough
    desc = re.search(r"id='OpportunitySynopsis_synopsis'>(.*?)<legend>", page, re.S | re.I)
    out["Description"] = _clean(desc.group(1)) if desc else ""
    links = re.findall(r"id='OpportunityLinks_\w+'>(.*?)</span>", page, re.S | re.I)
    out["_links"] = " ".join(_clean(x) for x in links if _clean(x).startswith("http"))
    return out


def _money(s: str) -> str:
    s = _clean(s)
    if not s or s.lower() == "not applicable":
        return ""
    def one(m: re.Match) -> str:
        return f"${float(m.group(0).replace('$', '').replace(',', '')):,.0f}"
    s = re.sub(r"\$\d[\d,]*(?:\.\d+)?", one, s)
    return re.sub(r"^No Limit - ", "Up to ", s)


def _around(text: str, m: re.Match) -> str:
    """The words around a match, cut at sentence ends where there are any."""
    stop = text.rfind(". ", 0, m.start())
    start = max(stop + 2 if stop != -1 else 0, m.start() - 160, 0)
    end = text.find(". ", m.end())
    end = min(end + 1 if end != -1 else len(text), m.end() + 160)
    return text[start:end].strip()


ELIGIBILITY_WORDS = re.compile(r"eligib|appl(?:y|icant|ication)|may (?:apply|submit)|must be|open to|award", re.I)


def who_can_apply(agency: str, text: str) -> tuple[bool, str]:
    """(nonprofits can apply, what the card says about who can) from the description."""
    named = [_around(text, m) for m in NONPROFIT.finditer(text)]
    named_as_applicant = [x for x in named if ELIGIBILITY_WORDS.search(x)]
    only = ONLY_OTHERS.search(text)
    refused = NO_NONPROFIT.search(text)
    if refused:
        return False, _around(text, refused)
    if named_as_applicant or (named and not only):
        return True, (named_as_applicant or named)[0]
    if only:
        return False, _around(text, only)
    if re.fullmatch(r"(?:Department of )?Education", agency.strip(), re.I):
        return False, "A Department of Education grant for schools and districts; nonprofits aren't named"
    return True, "Who may apply isn't stated on the listing; read the notice"


def normalize(row: dict, f: dict) -> dict:
    text = f.get("Description", "")
    nonprofit, who = who_can_apply(row["agency"], text)
    title = row["title"]
    loan = bool(re.search(r"\bloans?\b", title, re.I))
    credit = bool(re.search(r"\btax credits?\b", title, re.I))
    award = [f"{label}: {value}." for label, value in (
        ("Award size", _money(f.get("Award Amount Range", ""))),
        ("Project dates", "" if _clean(f.get("Project Dates", "")) in ("", "-") else _clean(f.get("Project Dates"))),
        ("Recurring", "Yes" if f.get("Recurring Opportunity", "").lower() == "yes" else ""),
    ) if value]
    contact = ", ".join(t for t in (f.get("Program Officer", ""), f.get("Phone", "")) if t)
    return {
        "id": f"ia-{row['id']}",
        "csfa": "",
        "number": row["id"],
        "state": "IA",
        "title": title,
        "agency": ", ".join(t for t in (row["agency"], row["program"]) if t and t != title),
        "objectives": text[:3000],
        "assistance": "Loan" if loan else "Tax credit" if credit else "Grant",
        "applicant_types": who[:1200],
        "nonprofit_eligible": nonprofit,
        "earmark": False,
        "restrictions": "",
        "application": "Apply on IowaGrants.gov from the opportunity's page; you'll need an IowaGrants account.",
        "award": " ".join(award)[:800],
        "deadlines": "Ongoing" if row["no_end"] else (row["closes"] or ""),
        "contact": contact[:600],
        "web": f.get("_links", "").split(" ")[0],
        "subjects": row["categories"],
        "fiscal_year": "",
        "url": row["detail"],
        "status": "active",
        "opens": row["posted"],
        "closes": row["closes"],
        "match": "",
        "loan": loan,
        "funding_method": "",
        "loi": False,
        "updated": row["posted"],
    }


def _get(url: str) -> str:
    r = session.get(url, timeout=60)
    r.raise_for_status()
    return r.text


def build_records(rows: list[dict], today: str | None = None, skips: list[dict] | None = None,
                  fetch=lambda row: fields(_get(row["detail"]))) -> list[dict]:
    today = today or date.today().isoformat()
    out: dict[str, dict] = {}
    for row in rows:
        base = {"source": "iowa", "id": f"ia-{row['id']}", "name": row["title"] or "(no title)", "state": "IA",
                "funder": row["agency"], "url": row["detail"]}
        if row["status"].lower() not in ("posted", "open", ""):
            continue
        if row["closes"] and row["closes"] < today:
            if skips is not None:
                skips.append({**base, "reason": "deadline_passed", "detail": f"Listed, but its deadline was {row['closes']}"})
            continue
        try:
            f = fetch(row)
        except Exception as exc:  # one unreadable page shouldn't sink the refresh
            print(f"skip {row['title']}: {exc}", file=sys.stderr)
            if skips is not None:
                skips.append({**base, "reason": "read_failed", "detail": f"The opportunity's page couldn't be read ({exc})"[:300]})
            continue
        if INVITATION.search(f.get("Description", "")):
            if skips is not None:
                skips.append({**base, "reason": "invitation_only", "detail": "The description says: by invitation only"})
            continue
        rec = normalize(row, f)
        out[rec["id"]] = rec
        time.sleep(PAUSE)
    return sorted(out.values(), key=lambda r: r["id"])


def build(out: Path, skipped_out: Path | None = None) -> int:
    rows = list_rows(_get(LIST))
    if len(rows) < MIN_ROWS:
        raise RuntimeError(f"Only {len(rows)} rows on the IowaGrants list; keeping the previous data file")
    skips: list[dict] = []
    records = build_records(rows, skips=skips)
    payload = {
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "source": "IowaGrants.gov, posted funding opportunities",
        "state": "IA", "count": len(records), "programs": records,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(out, "wt", encoding="utf-8") as fh:
        json.dump(payload, fh, separators=(",", ":"))
    print(f"wrote {len(records)} open Iowa opportunities to {out}; {sum(r['nonprofit_eligible'] for r in records)} open to nonprofits")
    if skipped_out is not None:
        from .fetch import write_skips
        write_skips(skipped_out, skips)
    return len(records)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="data/iowa.json.gz", type=Path)
    ap.add_argument("--skipped", type=Path)
    args = ap.parse_args()
    build(args.out, args.skipped)


if __name__ == "__main__":
    main()
