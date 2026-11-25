"""Every state's grant catalog, or why there isn't one yet: the one place a state plugs in.

Each of the 50 states and the District of Columbia has an entry with its status:

  built    an adapter reads the state's own list (file, catalog and module are set)
  next     a machine-readable source exists and is worth an adapter next
  decide   a source works, but whether to use it is Ren's call (docs/state-coverage.md says why)
  html     the state lists its grants only as web pages, a dashboard or a bid system
  none     no single public list of the state's grant calls was found, or the one that exists is empty or abandoned

Florida is built too, but keeps its own export (florida.py writes a catalog of programs, not open calls, with
county programs and its own vectors). Every other built state is listed in STATE_PROGRAMS, which export_web
reads; export_web also publishes each state's status in meta.json, so the site can say when a state has no
catalog. Sources and checks: docs/state-coverage.md (researched November 2026).

To add a state: write an adapter that produces the same record fields as ohio.py, set its entry here to
"built" with file, source, catalog and module, and propose a refresh job. The site needs no change.
"""
from __future__ import annotations

from .display import STATE_NAMES

STATUSES = ("built", "next", "decide", "html", "none")

STATES: dict[str, dict] = {
    "AL": {"status": "html", "source": "ADECA Funding Opportunities and Grant Calendar (one agency)"},
    "AK": {"status": "next", "source": "State of Alaska Online Public Notices (RSS, Grants category)"},
    "AZ": {"status": "none", "source": "grants.az.gov points to Euna Grants (eCivis), which needs an account"},
    "AR": {"status": "none", "source": "Agency pages only"},
    "CA": {"status": "built", "source": "California Grants Portal", "file": "california", "catalog": "Grants Portal",
           "module": "california"},
    "CO": {"status": "none", "source": "Agency pages only (blocked to scripts)"},
    "CT": {"status": "none", "source": "Past awards on data.ct.gov; calls on the CTsource bid board"},
    "DE": {"status": "none", "source": "Past awards on data.delaware.gov only"},
    "DC": {"status": "html", "source": "District Grants Clearinghouse (Serve DC)"},
    "FL": {"status": "built", "source": "Florida Catalog of State Financial Assistance", "file": "florida",
           "catalog": "CSFA", "module": "florida"},
    "GA": {"status": "html", "source": "Georgia Grants Portal (OPB only, empty when checked)"},
    "HI": {"status": "next", "source": "HANDS, Hawaii Awards and Notices Data System (JSON)"},
    "ID": {"status": "none", "source": "Agency pages only (blocked to scripts)"},
    "IL": {"status": "built", "source": "Illinois Catalog of State Financial Assistance", "file": "illinois",
           "catalog": "Illinois NOFO", "module": "illinois"},
    "IN": {"status": "html", "source": "State Agency Grant Opportunities (Euna Grants list)"},
    "IA": {"status": "built", "source": "IowaGrants.gov", "file": "iowa", "catalog": "IowaGrants", "module": "iowa"},
    "KS": {"status": "none", "source": "grants.ks.gov needs a login (blocked to scripts)"},
    "KY": {"status": "none", "source": "Agency pages only"},
    "LA": {"status": "none", "source": "Agency pages only"},
    "ME": {"status": "html", "source": "Maine Community Funding Finder"},
    "MD": {"status": "none", "source": "grants.maryland.gov list, abandoned since September 2023"},
    "MA": {"status": "html", "source": "COMMBUYS bid search"},
    "MI": {"status": "html", "source": "MI Funding Hub"},
    "MN": {"status": "html", "source": "Office of Grants Management, Find a Grant"},
    "MS": {"status": "none", "source": "Agency pages only"},
    "MO": {"status": "none", "source": "Agency pages only"},
    "MT": {"status": "html", "source": "Montana WebGrants storefront (mostly expired)"},
    "NE": {"status": "none", "source": "Agency pages only"},
    "NV": {"status": "html", "source": "Office of Federal Assistance grant opportunities (Airtable view)"},
    "NH": {"status": "none", "source": "Agency pages only"},
    "NJ": {"status": "built", "source": "New Jersey Treasury list of state grant opportunities", "file": "newjersey",
           "catalog": "New Jersey", "module": "newjersey"},
    "NM": {"status": "none", "source": "Agency pages only"},
    "NY": {"status": "html", "source": "Statewide Financial System, Search for Grant Opportunities"},
    "NC": {"status": "html", "source": "NC.gov Grant Opportunities table"},
    "ND": {"status": "html", "source": "North Dakota WebGrants storefront"},
    "OH": {"status": "built", "source": "Ohio Grants Partnership", "file": "ohio", "catalog": "Ohio", "module": "ohio"},
    "OK": {"status": "none", "source": "OK Grants needs an account"},
    "OR": {"status": "none", "source": "Two housing datasets on data.oregon.gov, both empty"},
    "PA": {"status": "decide", "source": "pa.gov Discover State Grants (the site's own search proxy)"},
    "RI": {"status": "html", "source": "Grants Management Office funding opportunities (Euna Grants list)"},
    "SC": {"status": "none", "source": "Agency pages only"},
    "SD": {"status": "none", "source": "Agency pages only"},
    "TN": {"status": "none", "source": "Agency pages only (blocked to scripts)"},
    "TX": {"status": "html", "source": "Electronic State Business Daily, Grants (robots.txt disallows crawling)"},
    "UT": {"status": "html", "source": "Utah Funding Opportunities Portal (Looker Studio report)"},
    "VT": {"status": "none", "source": "Past awards on data.vermont.gov only"},
    "VA": {"status": "html", "source": "Governor's Office Grants directory"},
    "WA": {"status": "built", "source": "FundHubWA (Washington Department of Commerce)", "file": "washington",
           "catalog": "FundHubWA", "module": "washington"},
    "WV": {"status": "built", "source": "West Virginia grants.wv.gov list of available grants", "file": "westvirginia",
           "catalog": "grants.wv.gov", "module": "westvirginia"},
    "WI": {"status": "none", "source": "Agency pages only"},
    "WY": {"status": "html", "source": "Wyoming Grants Connect Hub (Power BI report)"},
}

# States besides Florida with their own adapter: the data file's name, where it comes from, and the label the
# site puts before each call's number. Read by export_web.
STATE_PROGRAMS: dict[str, dict] = {
    code: {"file": s["file"], "source": s["source"], "catalog": s["catalog"]}
    for code, s in STATES.items() if s["status"] == "built" and code != "FL"
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
        for k in ("file", "catalog", "module"):
            if built != bool(s.get(k)):
                problems.append(f"{code}: {k} is {'needed' if built else 'only for built states'}")
    return problems
