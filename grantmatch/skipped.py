"""The grants Grant Matcher leaves out or hides, who they are and why, for a person to review.

Each refresh writes what it left out next to its data (the "skipped" files on the data-latest release):
  skipped-federal.json.gz      grantmatch.fetch       open federal opportunities not in the data file
  skipped-california.json.gz   grantmatch.california  open portal rows that were dropped
  skipped-foundations.jsonl.gz grantmatch.foundations private foundations read but not listed
  skipped-community.jsonl.gz   grantmatch.community   community foundations and United Ways read but not listed
The Florida and California program files also hold programs the site never shows (not open to nonprofits)
or hides unless asked (set aside by the Legislature for a named organization); this reads those too.

The report joins them into one CSV, one row per grant or funder with a plain reason, and a short Markdown
summary for the review issue: counts by source and reason, what is new since last week, and the rows most
worth a second look. Decisions a person makes go in data/skip-review.csv (source, id, decision, note), so a
reviewed row says so in every later report. The report never changes what the site shows.

Run:  python -m grantmatch.skipped --parts build/skips --florida build/florida.json.gz \
          --california build/california.json.gz --previous build/prev.csv --csv build/skipped-grants.csv --md build/report.md
"""
from __future__ import annotations

import argparse
import csv
import gzip
import io
import json
import os
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

LOCAL = Path(__file__).resolve().parent.parent / "data"

SOURCES = {
    "federal": "Federal (Grants.gov)",
    "california": "California Grants Portal",
    "illinois": "Illinois state notices (GATA)",
    "florida": "Florida state catalog",
    "foundation": "Private foundation (IRS 990-PF)",
    "community": "Community foundation or United Way (IRS 990)",
}

# code: (status, reason in plain words, why it is skipped, what to ask when reviewing)
REASONS = {
    "notes_mention_nonprofits": (
        "Left out", "Coded as not for nonprofits, but its notes mention them",
        "Grants.gov's eligibility codes leave nonprofits out, but the eligibility notes mention nonprofits, NGOs "
        "or community groups. These are the federal ones most worth a second look.",
        "Do the notes really let a nonprofit apply? If so, it should be included."),
    "not_nonprofit_eligible": (
        "Left out", "Nonprofits can't apply",
        "Grants.gov lists who may apply, and nonprofits are not on the list (for example, only states, universities, "
        "tribes or businesses).",
        "Could a small nonprofit still take part as a partner or subrecipient of an eligible applicant?"),
    "read_failed": (
        "Left out", "Couldn't be read this run",
        "Grants.gov did not return the details. It is usually back on the next refresh.",
        "Is it still missing after a day? Then it needs a look."),
    "deadline_passed": (
        "Left out", "Deadline already passed",
        "The portal still marks it open, but its deadline is behind us.",
        "Has the agency extended the deadline without updating the date?"),
    "no_title": ("Left out", "No title", "The portal row has no title to show.", "Is it a real call with a missing field?"),
    "no_portal_id": ("Left out", "No portal ID", "The row can't be linked to the portal.", "Is it a real call with a missing field?"),
    "state_not_nonprofit": (
        "Never shown", "The state says nonprofits can't apply",
        "The state's own listing names who may apply, and nonprofits are not among them.",
        "Does the program text say otherwise, or could a nonprofit partner with a city or county?"),
    "earmark": (
        "Hidden unless asked", "Set aside for a named organization",
        "The Legislature directed this money to a specific organization, so others can't apply.",
        "None usually; it is shown when someone ticks the earmark box."),
    "no_grants": (
        "Left out", "No grants to organizations in its latest return",
        "Its newest IRS return lists no grants paid to organizations. Many give only scholarships to individuals, "
        "run their own programs, or paid nothing that year.",
        "Did it give in earlier years, and does its website describe grants to nonprofits?"),
    "preselected": (
        "Left out", "Funds only charities it picks, with no way to apply",
        "It checked the IRS box saying it gives only to charities it selects, and its return gives no application "
        "details. Foundations that check the box but say how to apply are kept and shown on request.",
        "Does its website invite letters of inquiry anyway?"),
    "no_recent_return": (
        "Left out", "No return in the two newest filing years",
        "The refresh lists foundations that filed recently. One that hasn't may have closed, merged or filed late.",
        "Is it still active (website, recent news), and did it just file late?"),
    "older_return_listed": (
        "Left out", "Return read but not listed",
        "Its newest return passed the checks, but the foundation didn't end up in a state file.",
        "This shouldn't happen; each one is worth a look."),
}

COLUMNS = ["Source", "Status", "Reason", "Name", "Funder or agency", "State", "City", "ID", "Details", "Link",
           "Assets", "Tax year", "First seen", "Review decision", "Review note"]


def _read_rows(path: Path) -> tuple[list[dict], str]:
    """The rows in one skipped file, and the error its refresh recorded when it couldn't make the list."""
    raw = gzip.decompress(path.read_bytes()).decode("utf-8")
    if path.name.endswith(".jsonl.gz"):
        return [json.loads(line) for line in raw.splitlines() if line.strip()], ""
    data = json.loads(raw)
    if isinstance(data, dict):
        return data.get("rows", []), data.get("error", "")
    return data, ""


def hidden_programs(path: Path, source: str) -> list[dict]:
    """Programs in a state file that the site never shows (not open to nonprofits) or hides (earmarks)."""
    payload = json.loads(gzip.decompress(path.read_bytes()))
    rows = []
    for r in payload.get("programs", []):
        if not r.get("nonprofit_eligible", True):
            reason = "state_not_nonprofit"
        elif r.get("earmark"):
            reason = "earmark"
        else:
            continue
        rows.append({"source": source, "id": r.get("id", ""), "name": r.get("title", ""), "funder": r.get("agency", ""),
                     "state": payload.get("state") or ("FL" if source == "florida" else ""), "reason": reason,
                     "detail": f"Who can apply: {r.get('applicant_types', '')}"[:400], "url": r.get("url", "")})
    return rows


def load_decisions(path: Path | None) -> dict[tuple[str, str], dict]:
    path = path or LOCAL / "skip-review.csv"
    if not path.exists():
        return {}
    return {(row["source"], row["id"]): row for row in csv.DictReader(io.StringIO(path.read_text(encoding="utf-8")))
            if row.get("source") and row.get("id")}


def load_previous(path: Path | None) -> dict[tuple[str, str], str]:
    """(source, id) -> the date it was first seen, from last week's CSV."""
    if not path or not path.exists():
        return {}
    out = {}
    for row in csv.DictReader(io.StringIO(path.read_text(encoding="utf-8-sig"))):
        src = next((k for k, v in SOURCES.items() if v == row.get("Source")), row.get("Source", ""))
        out[(src, row.get("ID", ""))] = row.get("First seen", "")
    return out


def to_csv_row(r: dict, first_seen: str, decision: dict | None) -> dict:
    status, reason, _, _ = REASONS.get(r["reason"], ("Left out", r["reason"], "", ""))
    assets = r.get("assets")
    return {
        "Source": SOURCES.get(r["source"], r["source"]), "Status": status, "Reason": reason,
        "Name": r.get("name", ""), "Funder or agency": r.get("funder", ""), "State": r.get("state", ""),
        "City": r.get("city", ""), "ID": r.get("id", ""), "Details": r.get("detail", ""), "Link": r.get("url", ""),
        "Assets": f"{assets:.0f}" if isinstance(assets, (int, float)) else "", "Tax year": r.get("tax_year", ""),
        "First seen": first_seen, "Review decision": (decision or {}).get("decision", ""),
        "Review note": (decision or {}).get("note", ""),
    }


def money(n) -> str:
    if not isinstance(n, (int, float)) or n <= 0:
        return ""
    return f"${n / 1e9:.1f}B" if n >= 1e9 else f"${n / 1e6:.1f}M" if n >= 1e6 else f"${n / 1e3:.0f}K"


def md_escape(s: str) -> str:
    return (s or "").replace("|", "/").replace("\n", " ").strip()


def build(rows: list[dict], previous: dict[tuple[str, str], str], decisions: dict[tuple[str, str], dict],
          today: str, missing: list[str], csv_link: str = "") -> tuple[list[dict], str]:
    out, new = [], []
    for r in rows:
        key = (r["source"], r.get("id", ""))
        first = previous.get(key) or today
        if key not in previous:
            new.append(r)
        out.append(to_csv_row(r, first, decisions.get(key)))
    order = {k: i for i, k in enumerate(SOURCES)}
    out.sort(key=lambda c: (order.get(next((k for k, v in SOURCES.items() if v == c["Source"]), ""), 9), c["Reason"], c["State"], c["Name"]))

    counts: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        counts[r["source"]][r["reason"]] += 1
    reviewed = sum(1 for r in rows if (r["source"], r.get("id", "")) in decisions)
    lines = [f"# Skipped grants review, {today}", "",
             f"{len(rows):,} grants and funders are left out or hidden. {reviewed:,} have a review decision. "
             + (f"The full list is the CSV on the data-latest release: {csv_link}" if csv_link else ""), "",
             "Nothing here changes the site. To record a decision, add a row to `data/skip-review.csv` "
             "(source, id, decision, note); every later report carries it.", ""]
    if missing:
        lines += ["**Not in this report yet:** " + "; ".join(missing), ""]
    lines += ["## By source and reason", "", "| Source | Reason | Status | Count |", "|---|---|---|---:|"]
    for src in SOURCES:
        for code, n in counts.get(src, Counter()).most_common():
            status, reason, _, _ = REASONS.get(code, ("Left out", code, "", ""))
            lines.append(f"| {SOURCES[src]} | {reason} | {status} | {n:,} |")
    lines += ["", "## Why each reason is skipped", ""]
    used = {code for c in counts.values() for code in c}
    for code, (status, reason, why, ask) in REASONS.items():
        if code in used:
            lines.append(f"- **{reason}** ({status.lower()}). {why} *Review question:* {ask}")

    def table(items: list[dict], limit: int, with_assets: bool = False) -> list[str]:
        head = "| Name | Funder or agency | State | Reason | " + ("Assets | " if with_assets else "") + "Details |"
        sep = "|---|---|---|---|" + ("---:|" if with_assets else "") + "---|"
        body = []
        for r in items[:limit]:
            name = md_escape(r.get("name", ""))[:90]
            link = f"[{name}]({r['url']})" if r.get("url") else name
            cells = [link, md_escape(r.get("funder", ""))[:50], r.get("state", ""), REASONS.get(r["reason"], ("", r["reason"]))[1]]
            if with_assets:
                cells.append(money(r.get("assets")))
            cells.append(md_escape(r.get("detail", "") or (f"Tax year {r.get('tax_year')}" if r.get("tax_year") else ""))[:160])
            body.append("| " + " | ".join(cells) + " |")
        more = len(items) - limit
        return [head, sep, *body] + ([f"", f"...and {more:,} more in the CSV."] if more > 0 else [])

    if new and previous:  # the first report has nothing to compare with
        lines += ["", f"## New since the last report ({len(new):,})", ""]
        new.sort(key=lambda r: (r["source"] in ("foundation", "community"), -(r.get("assets") or 0)))
        lines += table(new, 40, with_assets=any(r.get("assets") for r in new))
    rank = {code: i for i, code in enumerate(REASONS)}
    for src in ("federal", "california", "illinois", "florida"):
        # Earmarks are only counted above: by law nobody else can apply, and the CSV lists them all.
        items = [r for r in rows if r["source"] == src and r["reason"] != "earmark"]
        if items:
            lines += ["", f"## {SOURCES[src]} ({len(items):,})", ""]
            lines += table(sorted(items, key=lambda r: (rank.get(r["reason"], 99), r.get("name", ""))), 60)
    for src in ("foundation", "community"):
        items = [r for r in rows if r["source"] == src and r["reason"] in ("preselected", "no_recent_return", "older_return_listed")]
        if items:
            biggest = sorted(items, key=lambda r: -(r.get("assets") or 0))
            lines += ["", f"## {SOURCES[src]}: the largest ones left out", "",
                      "Most are left out because they give nothing to organizations; those are in the CSV. "
                      "These are the largest of the ones that might still be worth approaching.", ""]
            lines += table(biggest, 30, with_assets=True)
    text = "\n".join(lines) + "\n"
    if len(text) > 60000:  # GitHub caps an issue body at 65,536 characters
        text = text[:60000].rsplit("\n", 1)[0] + "\n\n(Cut to fit the issue; the CSV has everything.)\n"
    return out, text


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--parts", type=Path, required=True, help="folder holding the skipped-*.json(l).gz files")
    ap.add_argument("--florida", type=Path)
    ap.add_argument("--california", type=Path)
    ap.add_argument("--illinois", type=Path)
    ap.add_argument("--previous", type=Path, help="last report's CSV, for first-seen dates and what is new")
    ap.add_argument("--decisions", type=Path, help="review decisions (default data/skip-review.csv)")
    ap.add_argument("--csv", type=Path, required=True)
    ap.add_argument("--md", type=Path, required=True)
    ap.add_argument("--csv-link", default="")
    args = ap.parse_args()

    rows, missing = [], []
    expected = {"skipped-federal.json.gz": "federal (after the next twice-daily refresh)",
                "skipped-california.json.gz": "California (after the next daily refresh)",
                "skipped-illinois.json.gz": "Illinois (after the next daily refresh)",
                "skipped-foundations.jsonl.gz": "private foundations (after the next monthly foundation refresh)",
                "skipped-community.jsonl.gz": "community foundations (after the next monthly foundation refresh)"}
    for name, label in expected.items():
        path = args.parts / name
        if path.exists():
            part, err = _read_rows(path)
            rows += part
            if err:
                missing.append(f"{label.split(' (')[0]}: the last refresh couldn't make its list ({err[:120]})")
        else:
            missing.append(label)
    if args.florida and args.florida.exists():
        rows += hidden_programs(args.florida, "florida")
    else:
        missing.append("Florida catalog")
    for path, source in ((args.california, "california"), (args.illinois, "illinois")):
        if path and path.exists():
            rows += hidden_programs(path, source)
    today = datetime.now(timezone.utc).date().isoformat()
    previous = load_previous(args.previous)
    out, text = build(rows, previous, load_decisions(args.decisions), today, missing, args.csv_link)
    args.csv.parent.mkdir(parents=True, exist_ok=True)
    with open(args.csv, "w", newline="", encoding="utf-8-sig") as fh:  # the BOM lets Excel read the accents
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(out)
    args.md.write_text(text, encoding="utf-8")
    # New means not in the last report's CSV; a first-seen date of today is not enough, since a report can run twice a day
    fresh = sum(1 for r in rows if (r["source"], r.get("id", "")) not in previous) if previous else 0
    print(f"{len(out):,} rows; new since last report: {fresh:,}")
    gh_out = os.environ.get("GITHUB_OUTPUT")
    if gh_out:
        with open(gh_out, "a", encoding="utf-8") as fh:
            fh.write(f"rows={len(out)}\nnew={fresh}\n")


if __name__ == "__main__":
    main()
