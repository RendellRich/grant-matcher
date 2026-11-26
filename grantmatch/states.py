"""Every state's grant catalog, or why there isn't one yet: the one place a state plugs in.

Each of the 50 states and the District of Columbia has an entry with its status:

  built      an adapter reads the state's own list (file, catalog and module are set)
  next       a machine-readable source exists and is worth an adapter next (none at the moment)
  decide     a machine-readable source works, but Ren decided to leave it out (2026-11-25; docs/state-coverage.md
             section (c) gives the reasons)
  html       the grant pages checked are web pages, a dashboard or a bid system, not a data file, and no adapter
             has been built from them (docs/state-coverage.md gives each state's reason)
  blocked    robots.txt or a site's terms keep our crawler or this use out, or the site turns scripts away, for
             the pages that would carry the state's calls. Nothing is read from them, and nothing learned from a
             page we may not use is recorded here: only the host and the reason
  none       nowhere the research looked has a current public list of state grant calls: past awards only, a
             login wall, or a list that is empty or abandoned. If any page it looked at posts current calls, the
             state is html instead
  unchecked  the research couldn't establish the answer (Massachusetts: the public bid search loads, but no grant
             call was seen on it; Mississippi: the one table that might list current calls is filled by script and
             wasn't read). Nothing is claimed about these states

Florida is built too, but keeps its own export (florida.py writes a catalog of programs, not open calls, with
county programs and its own vectors). Every other built state is listed in STATE_PROGRAMS, which export_web
reads; export_web also publishes each state's status in meta.json, so the site can say when a state has no
catalog. Sources and checks: docs/state-coverage.md (researched November 2026).

To add a state: write an adapter that produces the same record fields as ohio.py, set its entry here to
"built" with file, source, catalog, module, pages (the public pages the list is read from, which the weekly
freshness check in grantmatch/freshness.py opens), report (its heading in the skipped grants review) and refresh
(how often its refresh job runs; None until a refresh job exists), add "who_listed": False when its list never says
who may apply (the site then doesn't claim its calls list nonprofits), and add it to a refresh job: West Virginia and
New Jersey share .github/workflows/refresh-states.yml, weekly. Set "in_skip_report": False until
skipped-report.yml downloads the state's skipped file, so the Friday report doesn't call it missing. The state tab, the exports and the skipped report need no change; add the state's "For <state> state grants" note
and its sentence in the footer (web/src/app.tsx).

A state read from web pages can use grantmatch/webpages.py (the crawling rule, record fields and dropped rows), as
arkansas.py, maryland.py, montana.py, northdakota.py, tennessee.py and wyoming.py do.

To pause a built state's reads, give its entry "paused": {"why": ..., "hosts": [...]}. Nothing then asks those hosts for
anything: the adapter republishes its last published files unchanged (grantmatch/illinois.py), the page watch, the
freshness check and the website check treat the hosts as off limits without a request (cycles.off_limits), the data
keeps its old date, and the state's tab says reading is paused (export_web.py). Remove the key to resume.
"""
from __future__ import annotations

from urllib.parse import urlparse

from .display import STATE_NAMES

STATUSES = ("built", "next", "decide", "html", "blocked", "none", "unchecked")

STATES: dict[str, dict] = {
    "AL": {"status": "blocked", "source": "adeca.alabama.gov (its robots.txt disallows ClaudeBot)"},
    "AK": {"status": "decide", "source": "State of Alaska Online Public Notices (RSS of every notice; a few are grants)"},
    "AZ": {"status": "none", "source": "grants.az.gov points to Euna Grants (eCivis), behind a subscriber login"},
    "AR": {"status": "built", "source": "Arkansas Arts Council art grants page only (one agency, not a statewide list)",
           "file": "arkansas", "catalog": "Arkansas, 1 agency", "module": "arkansas",
           "report": "Arkansas Arts Council", "refresh": None, "in_skip_report": False,
           "pages": ["https://www.arkansasheritage.com/funding/art-grants"]},
    "CA": {"status": "built", "source": "California Grants Portal", "file": "california", "catalog": "Grants Portal",
           "module": "california", "report": "California Grants Portal", "refresh": "daily",
           "pages": ["https://www.grants.ca.gov/"]},
    "CO": {"status": "blocked",
           "source": "colorado.gov agency sites turn scripts away; cde.state.co.us robots.txt disallows all crawlers"},
    "CT": {"status": "html",
           "source": "OPM and Office of the Arts pages (two dated calls); the CTsource Bid Board is filled by script"},
    "DE": {"status": "none", "source": "Past awards on data.delaware.gov; no open-call dataset"},
    "DC": {"status": "built", "source": "District Grants Clearinghouse (DC.gov, CC BY 3.0)",
           "file": "districtofcolumbia", "catalog": "DC Clearinghouse", "module": "districtofcolumbia",
           "report": "District Grants Clearinghouse", "refresh": None, "in_skip_report": False, "who_listed": False,
           "pages": ["https://communityaffairs.dc.gov/node/26"]},
    "FL": {"status": "built", "source": "Florida Catalog of State Financial Assistance", "file": "florida",
           "catalog": "CSFA", "module": "florida", "report": "Florida state catalog", "refresh": "weekly",
           "pages": ["https://apps.fldfs.com/fsaa/catalog.aspx"]},
    "GA": {"status": "html",
           "source": "Georgia Grants Portal (no applications available) and Criminal Justice Coordinating Council pages"},
    "HI": {"status": "decide", "source": "HANDS, Hawaii Awards and Notices Data System (undocumented JSON, mostly procurement)"},
    "ID": {"status": "html",
           "source": "Education, Serve Idaho, Health and Welfare, and Parks and Recreation grant pages"},
    "IL": {"status": "built", "source": "Illinois Catalog of State Financial Assistance", "file": "illinois",
           "catalog": "Illinois NOFO", "module": "illinois", "report": "Illinois state notices (GATA)", "refresh": "daily",
           "pages": ["https://omb.illinois.gov/PUBLIC/GATA/CSFA/OpportunityList.aspx"],
           # Paused 2026-11-25 on Ren's decision: omb.illinois.gov answers robots.txt with a web page, so the state's
           # written OK is wanted first. Remove this key to resume. il.amplifund.com is the state's grants system, where
           # most notices' own pages are.
           "paused": {"why": "pending the state's written OK", "hosts": ["omb.illinois.gov", "il.amplifund.com"]}},
    "IN": {"status": "blocked",
           "source": "gn.ecivis.com robots.txt disallows all crawlers; in.gov terms bar storing its content in a retrieval system"},
    "IA": {"status": "built", "source": "IowaGrants.gov", "file": "iowa", "catalog": "IowaGrants", "module": "iowa",
           "report": "IowaGrants.gov", "refresh": "daily",
           "pages": ["https://www.iowagrants.gov/storefrontFOList.do"]},
    "KS": {"status": "html",
           "source": "Kansas Children's Cabinet grants page (one agency); grants.ks.gov turns scripts away"},
    "KY": {"status": "html",
           "source": "Kentucky Arts Council (its terms links return 404) and Health and Family Services grant pages"},
    "LA": {"status": "blocked",
           "source": "The arts division's robots.txt disallows ClaudeBot; health, law enforcement, volunteer and parks sites turn scripts away"},
    "ME": {"status": "blocked", "source": "maine.gov turns scripts away, robots.txt included"},
    "MD": {"status": "built",
           "source": "Maryland Department of Commerce State Grants table only (a short list, not a statewide list)",
           "file": "maryland", "catalog": "Maryland, short list", "module": "maryland",
           "report": "Maryland Commerce State Grants table", "refresh": None, "in_skip_report": False,
           "who_listed": False, "pages": ["https://business.maryland.gov/nonprofit-opportunities/"]},
    "MA": {"status": "unchecked", "source": "COMMBUYS public bid search (no grant call seen on its first page of open bids)"},
    "MI": {"status": "html", "source": "MI Funding Hub (its search page has no grant rows without script)"},
    "MN": {"status": "built",
           "source": "Minnesota Department of Health and Office of Justice Programs pages only (two agencies, not a statewide list)",
           "file": "minnesota", "catalog": "Minnesota, 2 agencies", "module": "minnesota",
           "report": "Minnesota (Health and Justice Programs pages)", "refresh": None, "in_skip_report": False,
           "pages": ["https://www.health.state.mn.us/about/grants/index.html",
                     "https://dps.mn.gov/divisions/ojp/ojp-grants/funding-opportunities"]},
    "MS": {"status": "unchecked",
           "source": "Agency pages; the Human Services procurement table is filled by script and wasn't read"},
    "MO": {"status": "html", "source": "Natural Resources, Arts Council and ServMO grant pages (mo.gov data policy requires state disclaimers)"},
    "MT": {"status": "built", "source": "Montana Arts Council grant pages only (one agency, not a statewide list)",
           "file": "montana", "catalog": "Montana, 1 agency", "module": "montana", "report": "Montana Arts Council",
           "refresh": None, "in_skip_report": False,
           "pages": ["https://art.mt.gov/artsed", "https://art.mt.gov/artsinhealth", "https://art.mt.gov/sig"]},
    "NE": {"status": "blocked", "source": "nebraska.gov terms bar robots and scrapers without written permission"},
    "NV": {"status": "blocked", "source": "airtable.com robots.txt disallows the state's shared grant view"},
    "NH": {"status": "blocked", "source": "nh.gov agency sites turn scripts away"},
    "NJ": {"status": "built", "source": "New Jersey Treasury list of state grant opportunities", "file": "newjersey",
           "catalog": "New Jersey", "module": "newjersey", "report": "New Jersey Treasury list", "refresh": "weekly",
           "in_skip_report": False, "who_listed": False,
           "pages": ["https://www.nj.gov/treasury/grants-management/opportunities/state"]},
    "NM": {"status": "blocked",
           "source": "New Mexico Arts (Cultural Affairs terms bar reproducing its sites' content without permission)"},
    "NY": {"status": "built", "source": "New York Statewide Financial System, Search for Grant Opportunities",
           "file": "newyork", "catalog": "NY SFS", "module": "newyork", "report": "New York SFS grant search",
           "refresh": None, "in_skip_report": False,
           "pages": ["https://esupplier.sfs.ny.gov/psp/fscm/SUPPLIER/ERP/c/NY_SUPPUB_FL.AUC_RESP_INQ_AUC.GBL"]},
    "NC": {"status": "blocked", "source": "nc.gov terms allow copying for non-commercial use only"},
    "ND": {"status": "built", "source": "North Dakota Council on the Arts pages only (one agency, not a statewide list)",
           "file": "northdakota", "catalog": "North Dakota, 1 agency", "module": "northdakota",
           "report": "North Dakota Council on the Arts", "refresh": None, "in_skip_report": False,
           "pages": ["https://www.arts.nd.gov/grants"]},
    "OH": {"status": "built", "source": "Ohio Grants Partnership", "file": "ohio", "catalog": "Ohio", "module": "ohio",
           "report": "Ohio Grants Partnership", "refresh": "daily",
           "pages": ["https://grants.ohio.gov/funding-opportunities/find-current-opportunities"]},
    "OK": {"status": "html",
           "source": "oklahoma.gov pages (terms linked as its operator's bar robots and scrapers; held until it is settled "
                     "whether they cover the site)"},
    "OR": {"status": "none", "source": "Two housing datasets on data.oregon.gov, both empty"},
    "PA": {"status": "decide", "source": "pa.gov Discover State Grants (the site's own search proxy)"},
    "RI": {"status": "blocked", "source": "gn.ecivis.com robots.txt disallows all crawlers"},
    "SC": {"status": "html",
           "source": "South Carolina Arts Commission grants page (one agency; rolling grants paused)"},
    "SD": {"status": "html",
           "source": "Department of Social Services and other agency pages (the sd.gov disclaimer couldn't be read)"},
    "TN": {"status": "built", "source": "Tennessee Arts Commission grant pages only (one agency, not a statewide list)",
           "file": "tennessee", "catalog": "Tennessee, 1 agency", "module": "tennessee",
           "report": "Tennessee Arts Commission", "refresh": None, "in_skip_report": False,
           "pages": ["https://tnartscommission.org/grants/"]},
    "TX": {"status": "blocked",
           "source": "txsmartbuy.gov robots.txt disallows all crawlers; no usable terms were confirmed for the eGrants page"},
    "UT": {"status": "html",
           "source": "Utah Funding Opportunities Portal (Looker Studio report); agency pages with no open call for nonprofits found"},
    "VT": {"status": "blocked", "source": "agriculture.vermont.gov (its robots.txt disallows ClaudeBot)"},
    "VA": {"status": "html",
           "source": "Governor's Office Grants directory (its policy link returns 404; virginia.gov allows fair use only)"},
    "WA": {"status": "built", "source": "FundHubWA (Washington Department of Commerce)", "file": "washington",
           "catalog": "FundHubWA", "module": "washington", "report": "FundHubWA (Washington)", "refresh": "daily",
           "pages": ["https://fundhub.wa.gov/funding/"]},
    "WV": {"status": "built", "source": "West Virginia grants.wv.gov list of available grants", "file": "westvirginia",
           "catalog": "grants.wv.gov", "module": "westvirginia", "report": "grants.wv.gov (West Virginia)",
           "refresh": "weekly", "in_skip_report": False,
           "pages": ["https://grants.wv.gov/"]},
    "WI": {"status": "blocked", "source": "wisconsin.gov policy limits agency pages to noncommercial use"},
    "WY": {"status": "built", "source": "Wyoming Arts Council pages only (one agency, not a statewide list)",
           "file": "wyoming", "catalog": "Wyoming, 1 agency", "module": "wyoming",
           "report": "Wyoming Arts Council", "refresh": None, "in_skip_report": False,
           "pages": ["https://wyoarts.state.wy.us/grants/"]},
}

# States besides Florida with their own adapter: the data file's name, where it comes from, and the label the
# site puts before each call's number. Read by export_web.
STATE_PROGRAMS: dict[str, dict] = {
    code: {"file": s["file"], "source": s["source"], "catalog": s["catalog"],
           **({"who_listed": False} if s.get("who_listed") is False else {})}
    for code, s in STATES.items() if s["status"] == "built" and code != "FL"
}

# For the weekly skipped grants review (grantmatch/skipped.py): each built state's source key (its file name),
# its heading in the report, how often its refresh job runs, and whether skipped-report.yml downloads its skipped
# file yet. A state with no refresh job, or one the report doesn't fetch yet, isn't expected in the report: its
# skipped list is read when it is there, and never reported missing.
REPORT: dict[str, dict] = {
    code: {"source": s["file"], "label": s["report"], "refresh": s["refresh"], "name": STATE_NAMES[code],
           "in_skip_report": s.get("in_skip_report", True)}
    for code, s in STATES.items() if s["status"] == "built"
}


def paused_host(url: str) -> str | None:
    """Why nothing may be asked of this address's host while its state's reads are paused, or None."""
    host = (urlparse(url).hostname or "").lower().rstrip(".")
    for code, s in STATES.items():
        pause = s.get("paused")
        if pause and any(host == h or host.endswith("." + h) for h in pause["hosts"]):
            return f"reading {STATE_NAMES.get(code, code)}'s list is paused {pause['why']}"
    return None


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
        if "in_skip_report" in s and (not built or not isinstance(s["in_skip_report"], bool)):
            problems.append(f"{code}: in_skip_report is true or false, for built states only")
        if "who_listed" in s and (not built or s["who_listed"] is not False):
            problems.append(f"{code}: who_listed is only ever false, for built states only")
        if "paused" in s:
            pause = s["paused"]
            if not (built and isinstance(pause, dict) and pause.get("why") and pause.get("hosts")):
                problems.append(f"{code}: paused is why and hosts, for built states only")
        pages = s.get("pages")
        if built != bool(pages) or not all(str(u).startswith("https://") for u in pages or []):
            problems.append(f"{code}: pages is a list of https addresses, for built states only")
    return problems
