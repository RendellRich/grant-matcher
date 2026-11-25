"""Every state's grant catalog, or why there isn't one yet: the one place a state plugs in.

Each of the 50 states and the District of Columbia has an entry with its status:

  built      an adapter reads the state's own list (file, catalog and module are set)
  next       a machine-readable source exists and is worth an adapter next (none at the moment)
  decide     a machine-readable source works, but Ren decided to leave it out (2026-11-25; docs/state-coverage.md
             section (c) gives the reasons)
  html       the grant pages checked are web pages, a dashboard or a bid system, not a data file
  none       nowhere the research looked has a current public list of state grant calls: past awards only, a
             login wall, or a list that is empty or abandoned. If any page it looked at posts current calls, the
             state is html instead
  unchecked  the research couldn't establish the answer: the site turned scripts away, showed a captcha, wasn't
             tested, or a check couldn't be completed (Texas: the research session's own permission check blocked
             the probe). Nothing is claimed about these states; they need a look in a browser

Florida is built too, but keeps its own export (florida.py writes a catalog of programs, not open calls, with
county programs and its own vectors). Every other built state is listed in STATE_PROGRAMS, which export_web
reads; export_web also publishes each state's status in meta.json, so the site can say when a state has no
catalog. Sources and checks: docs/state-coverage.md (researched November 2026).

To add a state: write an adapter that produces the same record fields as ohio.py, set its entry here to
"built" with file, source, catalog, module, report (its heading in the skipped grants review) and refresh (how
often its refresh job runs; None until a refresh job exists, and the proposal for new states is weekly), and
propose a refresh job. The site and the skipped report need no change.
"""
from __future__ import annotations

from .display import STATE_NAMES

STATUSES = ("built", "next", "decide", "html", "none", "unchecked")

STATES: dict[str, dict] = {
    "AL": {"status": "html", "source": "ADECA Funding Opportunities and Grant Calendar (one agency)"},
    "AK": {"status": "decide", "source": "State of Alaska Online Public Notices (RSS of every notice; a few are grants)"},
    "AZ": {"status": "none", "source": "grants.az.gov points to Euna Grants (eCivis), behind a subscriber login"},
    "AR": {"status": "unchecked", "source": "DFA Intergovernmental Services grant program pages (found by search, not tested)"},
    "CA": {"status": "built", "source": "California Grants Portal", "file": "california", "catalog": "Grants Portal",
           "module": "california", "report": "California Grants Portal", "refresh": "daily"},
    "CO": {"status": "unchecked", "source": "OEDIT Programs and Funding, SIPA govgrants (blocked to scripts)"},
    "CT": {"status": "html", "source": "CTsource Bid Board (Nonprofit Grant Program rounds); past awards on data.ct.gov"},
    "DE": {"status": "none", "source": "Past awards on data.delaware.gov; no open-call dataset"},
    "DC": {"status": "html", "source": "District Grants Clearinghouse (Serve DC)"},
    "FL": {"status": "built", "source": "Florida Catalog of State Financial Assistance", "file": "florida",
           "catalog": "CSFA", "module": "florida", "report": "Florida state catalog", "refresh": "weekly"},
    "GA": {"status": "html", "source": "Georgia Grants Portal (OPB only, empty when checked)"},
    "HI": {"status": "decide", "source": "HANDS, Hawaii Awards and Notices Data System (undocumented JSON, mostly procurement)"},
    "ID": {"status": "unchecked", "source": "Idaho Commerce grants page (blocked to scripts)"},
    "IL": {"status": "built", "source": "Illinois Catalog of State Financial Assistance", "file": "illinois",
           "catalog": "Illinois NOFO", "module": "illinois", "report": "Illinois state notices (GATA)", "refresh": "daily"},
    "IN": {"status": "html", "source": "State Agency Grant Opportunities (Euna Grants list)"},
    "IA": {"status": "built", "source": "IowaGrants.gov", "file": "iowa", "catalog": "IowaGrants", "module": "iowa",
           "report": "IowaGrants.gov", "refresh": "daily"},
    "KS": {"status": "unchecked", "source": "grants.ks.gov and the KS Infrastructure Hub (blocked to scripts)"},
    "KY": {"status": "unchecked", "source": "CHFS, KDE and eMARS pages (found by search, not tested)"},
    "LA": {"status": "unchecked", "source": "LaPAC (procurement bids); LED's monthly Opportunity Roadmap PDF not opened"},
    "ME": {"status": "html", "source": "Maine Community Funding Finder"},
    "MD": {"status": "none", "source": "grants.maryland.gov list, abandoned since September 2023"},
    "MA": {"status": "html", "source": "COMMBUYS bid search"},
    "MI": {"status": "html", "source": "MI Funding Hub"},
    "MN": {"status": "unchecked", "source": "Office of Grants Management, Find a Grant (served a bot captcha)"},
    "MS": {"status": "unchecked", "source": "Agency pages such as MDHS Grant Opportunities (not tested)"},
    "MO": {"status": "unchecked", "source": "Agency pages (not tested); data.mo.gov has no opportunity dataset"},
    "MT": {"status": "html", "source": "Montana WebGrants storefront (mostly expired)"},
    "NE": {"status": "unchecked", "source": "Agency pages; DED uses AmpliFund (not tested)"},
    "NV": {"status": "html", "source": "Office of Federal Assistance grant opportunities (Airtable view)"},
    "NH": {"status": "unchecked", "source": "No source named; nothing tested"},
    "NJ": {"status": "built", "source": "New Jersey Treasury list of state grant opportunities", "file": "newjersey",
           "catalog": "New Jersey", "module": "newjersey", "report": "New Jersey Treasury list", "refresh": None},
    "NM": {"status": "unchecked", "source": "SHARE NM, reportedly login-based (not tested)"},
    "NY": {"status": "html", "source": "Statewide Financial System, Search for Grant Opportunities"},
    "NC": {"status": "html", "source": "NC.gov Grant Opportunities table"},
    "ND": {"status": "html", "source": "North Dakota WebGrants storefront"},
    "OH": {"status": "built", "source": "Ohio Grants Partnership", "file": "ohio", "catalog": "Ohio", "module": "ohio",
           "report": "Ohio Grants Partnership", "refresh": "daily"},
    "OK": {"status": "unchecked", "source": "OK Grants needs registration; what agency pages list isn't recorded"},
    "OR": {"status": "none", "source": "Two housing datasets on data.oregon.gov, both empty"},
    "PA": {"status": "decide", "source": "pa.gov Discover State Grants (the site's own search proxy)"},
    "RI": {"status": "html", "source": "Grants Management Office funding opportunities (Euna Grants list)"},
    "SC": {"status": "unchecked", "source": "Agency pages (not tested); data.sc.gov didn't respond"},
    "SD": {"status": "unchecked", "source": "Agency pages and sd.gov posts (not tested); data.sd.gov didn't respond"},
    "TN": {"status": "unchecked", "source": "Central Procurement Office grant page (blocked to scripts)"},
    "TX": {"status": "unchecked", "source": "Electronic State Business Daily, Grants (data endpoint not verified)"},
    "UT": {"status": "html", "source": "Utah Funding Opportunities Portal (Looker Studio report)"},
    "VT": {"status": "html", "source": "Agency grant pages such as the Agriculture grants calendar; past awards on data.vermont.gov"},
    "VA": {"status": "html", "source": "Governor's Office Grants directory"},
    "WA": {"status": "built", "source": "FundHubWA (Washington Department of Commerce)", "file": "washington",
           "catalog": "FundHubWA", "module": "washington", "report": "FundHubWA (Washington)", "refresh": "daily"},
    "WV": {"status": "built", "source": "West Virginia grants.wv.gov list of available grants", "file": "westvirginia",
           "catalog": "grants.wv.gov", "module": "westvirginia", "report": "grants.wv.gov (West Virginia)", "refresh": None},
    "WI": {"status": "unchecked", "source": "Agency pages (not tested); data.wi.gov didn't respond"},
    "WY": {"status": "html", "source": "Wyoming Grants Connect Hub (Power BI report)"},
}

# States besides Florida with their own adapter: the data file's name, where it comes from, and the label the
# site puts before each call's number. Read by export_web.
STATE_PROGRAMS: dict[str, dict] = {
    code: {"file": s["file"], "source": s["source"], "catalog": s["catalog"]}
    for code, s in STATES.items() if s["status"] == "built" and code != "FL"
}

# For the weekly skipped grants review (grantmatch/skipped.py): each built state's source key (its file name),
# its heading in the report, and how often its refresh job runs. None means no refresh job yet: the state ships
# from a snapshot in data/, so its skipped list isn't expected in the report.
REPORT: dict[str, dict] = {
    code: {"source": s["file"], "label": s["report"], "refresh": s["refresh"], "name": STATE_NAMES[code]}
    for code, s in STATES.items() if s["status"] == "built"
}


def catalogs() -> dict[str, dict]:
    """What meta.json carries for the site: each state's status and source, so a state with no catalog can say so."""
    return {code: {"status": s["status"], "source": s["source"]} for code, s in sorted(STATES.items())}


def check() -> list[str]:
    """Problems with the registry, in plain words; empty when it is fine."""
    problems = []
    want = set(STATE_NAMES) - {"PR"}  # the 50 states and DC; territories are out of scope
    if set(STATES) != want:
        problems.append(f"missing {sorted(want - set(STATES))}, extra {sorted(set(STATES) - want)}")
    for code, s in STATES.items():
        if s.get("status") not in STATUSES:
            problems.append(f"{code}: status must be one of {', '.join(STATUSES)}")
        if not s.get("source"):
            problems.append(f"{code}: no source")
        built = s.get("status") == "built"
        for k in ("file", "catalog", "module", "report"):
            if built != bool(s.get(k)):
                problems.append(f"{code}: {k} is {'needed' if built else 'only for built states'}")
        if built != ("refresh" in s) or s.get("refresh") not in (None, "daily", "weekly"):
            problems.append(f"{code}: refresh is daily, weekly or None, for built states only")
    return problems
