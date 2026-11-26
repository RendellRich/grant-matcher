"""The local funder directory: local governments that get HUD formula money (CDBG and HOME).

These are FUNDERS TO ASK, NOT OPEN GRANT CALLS. HUD money going to a government doesn't mean it funds nonprofits
now, and CDBG money for public services is limited and varies. Nothing here is scored, ranked, dated with a
deadline or said to be open to nonprofits, and neither scorer reads this file.

Two public federal files, both free, with no key or account:

  HUD    Community Planning and Development formula program allocations (an Excel workbook): each grantee and
         its CDBG and HOME amounts for the fiscal year
  Census Government Units listing (an Excel workbook in a zip): each local government's name, Census id, county
         area and the website it reported

Kept: cities, urban counties, Hawaii's three counties, HOME consortia and the District of Columbia (which HUD
lists with the states). Left out: states and insular areas (not local governments), and the other HUD programs. From the Census file only the unit's name, id, kind,
population, county and website are read: no street address, no job title, no name of a person, no email address.

A website is the one the government reported to the Census Bureau, or none. It is never guessed or searched for.
County names are those of data/counties.json.gz; a government that can't be matched to one reliably is listed
with no county ("state level only").

Run (downloads both files after the project's robots.txt and terms check):
  python -m grantmatch.funders --out data/funders.json.gz
or with copies already saved:
  python -m grantmatch.funders --hud <allocations.xlsx> --census <gov_units.zip> --out data/funders.json.gz

Once a year, when HUD publishes new allocations: update HUD_FILE, HUD_PAGE, HUD_AS_OF, CENSUS_FILE and
CENSUS_AS_OF below, run it, and update the counts in docs/county-coverage.md.
"""
from __future__ import annotations

import argparse
import gzip
import io
import json
import re
import tempfile
import unicodedata
import zipfile
from datetime import date
from pathlib import Path
from urllib.parse import urlparse
from xml.etree import ElementTree  # DTDs and entities are refused before parsing (_xml)

from . import local

AGENT = "grant-matcher (github.com/RendellRich/grant-matcher)"
OUT = local.LOCAL / "funders.json.gz"

HUD_PAGE = "https://www.hud.gov/hud-partners/community-budget-26"
HUD_FILE = "https://www.hud.gov/sites/dfiles/CPD/documents/FY2026-Formula-Allocations-All-Grantees.xlsx"
HUD_AS_OF = "2026-08-03"  # "Content current as of" on HUD_PAGE
CENSUS_PAGE = "https://www2.census.gov/programs-surveys/gus/datasets/"
CENSUS_FILE = CENSUS_PAGE + "2026/gov_units_2026.zip"
CENSUS_AS_OF = "2026-08-13"  # the date the file's documentation says the units were extracted
CENSUS_YEAR = "2026"

LEVELS = ("County", "City", "Other")
PROGRAMS = ("CDBG", "HOME")
LOCAL_TYPES = ("Principal City", "Metro City", "Urban County", "Hawaii County", "Consortia")
NOT_LOCAL = ("Non-entitlement", "Insular Area")  # states and territories
MIN_FUNDERS = 900  # HUD lists about 1,260 local grantees; far fewer means a file changed shape
MAX_PART = 300_000_000  # bytes a single part of a workbook may unpack to
MAX_DOWNLOAD = 100_000_000

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"

# The Census file's STATE column is the mailing address's state, which for a few border governments is not their own
# (Texarkana, Arkansas has a Texas address), so the state is read from the FIPS code, as HUD's keys use it too.
FIPS_STATES = dict(zip(
    ("01 02 04 05 06 08 09 10 11 12 13 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31 32 33 34 35 36 37 38 39 40 41 "
     "42 44 45 46 47 48 49 50 51 53 54 55 56 72").split(),
    ("AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR "
     "PA RI SC SD TN TX UT VT VA WA WV WI WY PR").split()))

# HUD's name for a government where the Census file words it another way: (state, HUD name) to the Census base name.
# Each was read in both files. Only the name is joined here; the website still comes from the Census record.
ALIASES = {
    ("FL", "Ft Lauderdale"): "Fort Lauderdale",
    ("FL", "Ft Myers"): "Fort Myers",
    ("GA", "Athens"): "Athens-Clarke County",
    ("GA", "Augusta"): "Augusta-Richmond County",
    ("KS", "Kansas City"): "Wyandotte County and Kansas City",
    ("KY", "Louisville-Jefferson MCG"): "Louisville-Jefferson County",
    ("LA", "Baton Rouge"): "Baton Rouge-East Baton Rouge",
    ("LA", "Houma-Terrebonne"): "Terrebonne",
    ("MI", "Muskegon Hts"): "Muskegon Heights",
    ("NY", "Glen Falls"): "Glens Falls",
    ("TN", "Nashville-Davidson"): "Nashville-Davidson County",
    ("UT", "West Valley"): "West Valley City",
}

# A city that is several whole counties, so its one Census county area would leave the rest out.
WHOLE_CITIES = {("NY", "New York"): ("Bronx", "Kings", "New York", "Queens", "Richmond")}

# Sites a few units reported that are plainly directories, not their own website.
NOT_OFFICIAL = ("city-data.com", "whitepages.com", "wikipedia.org")
# Addresses in the 2026 Census file that look like a misspelling of the government's own name, or are malformed
# ("w.w.w.", a dot inside "cityof"). Such an address can belong to anyone, so no link is shown; nothing is put in its
# place. A name here covers its subdomains. Read through again with each new file.
MISTYPED = ("avvada.org", "bristolya.org", "ci.neewah.wi.us", "city.of.bridgeton.com", "cityof.meriden.org",
            "ckkillen.tx.us", "educlairewi.gov", "lowermerian.org", "mobilcountyal.gov", "myhairlingen.us",
            "mypopanobeach.org", "passonegon.gov", "ppine.com", "taylorsvillut.gov", "voanokeva.gov", "w.austintexas.gov",
            "w.toaks.org", "w.w.w.hopewellva.gov")
# HUD's abbreviations, spelled out on the page.
SHORT = ((r"^Ft\b", "Fort"), (r"\bHts\b", "Heights"), (r"\bTwp\b", "Township"))


# ---------------- reading the workbooks (standard library only) ----------------

def _part(z: zipfile.ZipFile, name: str) -> bytes:
    if z.getinfo(name).file_size > MAX_PART:
        raise ValueError(f"{name} is too large to be one of these files")
    return z.read(name)


def _xml(raw: bytes) -> ElementTree.Element:
    """One part of a workbook. A workbook never declares a document type, so one that does is refused rather than
    handed to the parser (entity expansion and external entities)."""
    # Only UTF-8 gets as far as the parser, so the two checks below can't be written round in another encoding.
    declared = re.match(rb"""(?:\xef\xbb\xbf)?<\?xml[^>]*?encoding\s*=\s*["']([^"']+)["']""", raw)
    if b"\x00" in raw or (declared and declared.group(1).lower() != b"utf-8"):
        raise ValueError("a workbook part is not UTF-8")
    if b"<!DOCTYPE" in raw or b"<!ENTITY" in raw:
        raise ValueError("a workbook part declares a document type")
    return ElementTree.fromstring(raw)


def sheet_rows(book: bytes, sheet: str | None = None) -> list[dict[str, str]]:
    """A sheet's rows as {column letters: text}; the first sheet when no name is given."""
    with zipfile.ZipFile(io.BytesIO(book)) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            for si in _xml(_part(z, "xl/sharedStrings.xml")).findall(f"{NS}si"):
                shared.append("".join(t.text or "" for t in si.iter(f"{NS}t")))
        targets = {r.get("Id"): r.get("Target") for r in _xml(_part(z, "xl/_rels/workbook.xml.rels"))}
        listed = list(_xml(_part(z, "xl/workbook.xml")).iter(f"{NS}sheet"))
        found = [s for s in listed if sheet is None or s.get("name") == sheet]
        if not found:
            raise ValueError(f"the workbook has no sheet {sheet!r}")
        path = targets[found[0].get(REL)].lstrip("/")
        root = _xml(_part(z, path if path.startswith("xl/") else "xl/" + path))
    out = []
    for row in root.iter(f"{NS}row"):
        cells = {}
        for c in row.findall(f"{NS}c"):
            col = re.match(r"[A-Z]+", c.get("r") or "")
            if not col:
                raise ValueError("a cell has no position")
            v = c.find(f"{NS}v")
            if c.get("t") == "s" and v is not None:
                text = shared[int(v.text)]
            elif c.get("t") == "inlineStr":
                text = "".join(t.text or "" for t in c.iter(f"{NS}t"))
            else:
                text = (v.text or "") if v is not None else ""
            cells[col.group(0)] = text
        out.append(cells)
    return out


def table(rows: list[dict[str, str]], required: tuple[str, ...]) -> list[dict[str, str]]:
    """The rows under the header row (the first one holding every required column), keyed by column name."""
    for i, row in enumerate(rows[:10]):
        names = {col: value.strip() for col, value in row.items()}
        if set(required) <= set(names.values()):
            col = {name: c for c, name in names.items() if name in required}
            return [{name: r.get(c, "").strip() for name, c in col.items()} for r in rows[i + 1:]]
    raise ValueError(f"no header row with {', '.join(required)}: the file changed shape")


# ---------------- HUD ----------------

def _dollars(text: str) -> int:
    return round(float(text)) if text else 0


def hud_rows(book: bytes) -> tuple[str, list[dict]]:
    """(the fiscal year from the sheet's title, one row per HUD grantee with its CDBG and HOME dollars)."""
    rows = sheet_rows(book)
    title = " ".join(rows[0].values()) if rows else ""
    year = re.search(r"\bFY\s*(20\d\d)\b", title)
    if not year:
        raise ValueError("the allocations sheet's title names no fiscal year")
    got = table(rows, ("NAME", "STA", "TYPE", "CDBG", "HOME", "KEY", "CNSRT"))
    out = []
    for r in got:
        if not r["TYPE"]:
            continue  # footnotes
        if r["TYPE"] not in LOCAL_TYPES + NOT_LOCAL:
            raise ValueError(f"unknown grantee type {r['TYPE']!r}: check whether it is a local government")
        out.append({"name": " ".join(r["NAME"].split()), "state": r["STA"], "type": r["TYPE"], "key": r["KEY"],
                    "CDBG": _dollars(r["CDBG"]), "HOME": _dollars(r["HOME"]),
                    # A HOME consortium's code has a C after the state code ("12C972"). The District's row repeats
                    # its own key there, which is not a consortium.
                    "consortium": r["CNSRT"][2:3] == "C"})
    return year.group(1), out


# ---------------- Census ----------------

CENSUS_COLUMNS = ("CENSUS_ID_PID6", "UNIT_NAME", "UNIT_TYPE", "STATE", "WEB_ADDRESS", "POLITICAL_CODE_DESCRIPTION",
                  "POPULATION", "FIPS_STATE", "FIPS_COUNTY", "COUNTY_AREA_NAME")
OF = re.compile(r"^(?:CITY AND COUNTY|CITY AND BOROUGH|METROPOLITAN GOVERNMENT|METRO GOVERNMENT|CONSOLIDATED GOVERNMENT|"
                r"UNIFIED GOVERNMENT|URBAN COUNTY GOVERNMENT|CHARTER TOWNSHIP|CIVIL TOWNSHIP|CITY-PARISH|CORPORATION|PLANTATION|"
                r"MUNICIPALITY|TOWNSHIP|VILLAGE|BOROUGH|COUNTY|PARISH|CITY|TOWN) OF ", re.I)


def readable(name: str) -> str:
    """A name with its accents as written. data/counties.json.gz holds a few UTF-8 names read as Latin-1
    ("Do\u00c3\u00b1a Ana"); this puts them right and leaves every other name alone."""
    try:
        return name.encode("latin-1").decode("utf-8")
    except UnicodeError:
        return name


def key(name: str) -> str:
    """A name for joining: no case, accents, spaces or punctuation, and "Saint" as "St"."""
    plain = unicodedata.normalize("NFKD", readable(name)).encode("ascii", "ignore").decode()
    low = re.sub(r"\bsaint\b", "st", plain.lower())
    low = re.sub(r"\bsainte\b", "ste", low)
    return re.sub(r"[^a-z0-9]", "", low)


def census_units(book_zip: bytes) -> list[dict]:
    """General purpose governments (counties, municipalities, townships) from the listing's zip."""
    with zipfile.ZipFile(io.BytesIO(book_zip)) as z:
        names = [n for n in z.namelist() if n.lower().endswith(".xlsx")]
        if len(names) != 1:
            raise ValueError("expected one workbook in the Census zip")
        book = _part(z, names[0])
    out = []
    for r in table(sheet_rows(book, "General Purpose"), CENSUS_COLUMNS):
        if not r["UNIT_NAME"]:
            continue
        kind = r["UNIT_TYPE"].split(" - ")[-1].strip().lower()  # county, municipal or township
        out.append({"id": r["CENSUS_ID_PID6"], "name": OF.sub("", r["UNIT_NAME"]).strip(), "kind": kind,
                    "code": r["POLITICAL_CODE_DESCRIPTION"].lower(),
                    "state": FIPS_STATES.get(r["FIPS_STATE"], r["STATE"]), "web": r["WEB_ADDRESS"],
                    "population": int(r["POPULATION"].replace(",", "") or 0), "fips_state": r["FIPS_STATE"],
                    "fips_county": r["FIPS_COUNTY"], "county_area": r["COUNTY_AREA_NAME"]})
    return out


def website(raw: str) -> str:
    """The website as the Census file has it, or "" when the cell isn't one (an email address, free text, a
    directory site). Only a missing "http://" is added; nothing else is changed or guessed."""
    s = (raw or "").strip()
    if not s or "@" in s or any(ch.isspace() for ch in s) or any(ch in s for ch in "<>\"'"):
        return ""
    if not re.match(r"^https?://", s, re.I):
        if "://" in s or ":" in s.split("/")[0]:
            return ""
        s = "http://" + s
    try:
        host = (urlparse(s).hostname or "").lower()
    except ValueError:  # an unfinished "[" and the like
        return ""
    if not re.fullmatch(r"[a-z0-9-]+(\.[a-z0-9-]+)*\.[a-z]{2,}", host):
        return ""
    if any(host == d or host.endswith("." + d) for d in NOT_OFFICIAL + MISTYPED):
        return ""
    return s


# ---------------- matching ----------------

SUFFIX = re.compile(r"\s+(charter township|township|twp|town|village|borough|city/county|city|municipio)\s*$", re.I)
COUNTY_SUFFIX = re.compile(r"\s+(county|parish)\s*$", re.I)
# The Census codes a HUD name's last word may stand for.
TOWNSHIPS = ("township", "charter township", "civil township")
SUFFIX_CODES = {"charter township": TOWNSHIPS, "township": TOWNSHIPS, "twp": TOWNSHIPS,
                "town": ("town", "township"), "village": ("village",), "borough": ("borough",), "city": ("city",)}


class Places:
    """The county names of data/counties.json.gz, for joining a government to them."""

    def __init__(self, counties: dict[str, dict[str, list[str]]]):
        self.counties = counties
        self.by_county = {st: {key(c): c for c in cs} for st, cs in counties.items()}
        self.by_place: dict[str, dict[str, list[str]]] = {}
        for st, cs in counties.items():
            for county, places in cs.items():
                for place in places:
                    self.by_place.setdefault(st, {}).setdefault(key(place), []).append(county)

    def county(self, state: str, name: str) -> str | None:
        return self.by_county.get(state, {}).get(key(COUNTY_SUFFIX.sub("", name)))

    def holding(self, state: str, name: str) -> list[str]:
        return self.by_place.get(state, {}).get(key(name), [])


class Census:
    def __init__(self, units: list[dict]):
        self.by_name: dict[tuple[str, str], list[dict]] = {}
        self.by_fips: dict[tuple[str, str], list[dict]] = {}
        for u in units:
            self.by_name.setdefault((u["state"], key(u["name"])), []).append(u)
            self.by_fips.setdefault((u["state"], u["fips_county"]), []).append(u)

    def only(self, state: str) -> dict | None:
        """The single general purpose government of a place that has one (the District of Columbia)."""
        found = [u for (st, _), units in self.by_name.items() if st == state for u in units]
        return found[0] if len(found) == 1 else None

    def county_unit(self, state: str, hud_key: str, name: str) -> dict | None:
        """An urban county by HUD's code, which is the state code, 9, then the county's FIPS code. The unit's name
        must also agree, so a changed code can't attach another county's website."""
        if not re.fullmatch(r"\d{2}9\d{3}", hud_key):
            return None
        wanted = key(COUNTY_SUFFIX.sub("", name))
        here = [u for u in self.by_fips.get((state, hud_key[3:]), []) if u["fips_state"] == hud_key[:2]]
        for u in here:
            if u["kind"] == "county" and key(u["name"]) == wanted:
                return u
        # A county that merged with its city is listed as a municipality ("Jacksonville-Duval County").
        whole = [u for u in here if u["kind"] == "municipal"
                 and wanted in (key(u["name"]), key(f"{u['name']}-{u['county_area']}"))]
        return whole[0] if len(whole) == 1 else None

    def county_by_name(self, state: str, name: str) -> dict | None:
        """A county government by its name ("Hawaii County consortia", "County of Kauai")."""
        bare = COUNTY_SUFFIX.sub("", re.sub(r"^county of\s+", "", name, flags=re.I))
        found = [u for u in self.by_name.get((state, key(bare)), []) if u["kind"] == "county"]
        return found[0] if len(found) == 1 else None

    def city(self, state: str, name: str) -> dict | None:
        """A city, town or township by its name. When several share it, the HUD name's own last word decides,
        then municipalities come before townships, then the ones the Census calls a city, then a Metro City's
        50,000 people; if more than one is still left, none is picked."""
        alias = ALIASES.get((state, name))
        tries: list[tuple[str, tuple[str, ...]]] = [(alias or name, ())]
        m = SUFFIX.search(name)
        if m and not alias:
            word = m.group(1).lower()
            tries.append((name[: m.start()], SUFFIX_CODES.get(word, ())))
        if COUNTY_SUFFIX.search(name) and not alias:
            tries.append((COUNTY_SUFFIX.sub("", name), ()))  # a merged city and county ("Macon-Bibb County")
        for wanted, codes in tries:
            found = [u for u in self.by_name.get((state, key(wanted)), []) if u["kind"] != "county"]
            if codes:
                found = [u for u in found if u["code"] in codes] or found
            if len(found) > 1:
                found = [u for u in found if u["kind"] == "municipal"] or found
            if len(found) > 1 and not codes:
                found = [u for u in found if u["code"] == "city"] or found
            if len(found) > 1:
                found = [u for u in found if u["population"] >= 50_000]
            if len(found) == 1:
                return found[0]
        return None


AREA_SUFFIX = re.compile(r"\s+(city and county|city|municipality|borough|census area)$", re.I)


def city_counties(row: dict, unit: dict | None, census: Census, places: Places) -> list[str]:
    """The county a city, town or township is in: the Census record's county area. That is one county, the one most
    served, so a city that spans several lists only that one. The other counties are not guessed from place names,
    since a different place of the same name (Plantation, Florida) would add a county the city isn't in. New York
    City is the exception: its five counties are set. Without a county area that matches (Connecticut's are now
    planning regions) or without a record: only a name data/counties.json.gz has in exactly one county. An
    independent city that shares its name with a county (Richmond, Virginia; St. Louis; Baltimore) is left at state
    level."""
    state = row["state"]
    if (state, row["name"]) in WHOLE_CITIES:
        found = [places.county(state, c) for c in WHOLE_CITIES[(state, row["name"])]]
        return [c for c in found if c]
    if unit is not None:
        area = unit["county_area"]
        main = places.county(state, area)
        if not main and AREA_SUFFIX.search(area):
            bare = AREA_SUFFIX.sub("", area)
            if census.county_by_name(state, bare):
                return []  # the county of that name is another government
            main = places.county(state, bare)
        if main:
            return [main]
    held = places.holding(state, unit["name"] if unit else SUFFIX.sub("", row["name"]))
    return list(held) if len(held) == 1 else []


def area_text(state: str, counties: list[str]) -> str:
    """The counties in words ("Harris County", "Cass, Clay and Jackson counties"), "" when none is matched."""
    if not counties:
        return ""
    counties = [readable(c) for c in counties]
    if state in ("AK", "DC", "VA"):  # boroughs, census areas and independent cities don't take "County"
        return counties[0] if len(counties) == 1 else ", ".join(counties[:-1]) + " and " + counties[-1]
    one, many = {"LA": ("Parish", "parishes"), "PR": ("Municipio", "municipios")}.get(state, ("County", "counties"))
    if len(counties) == 1:
        return f"{counties[0]} {one}"
    return ", ".join(counties[:-1]) + f" and {counties[-1]} {many}"


def describe(row: dict, unit: dict | None) -> tuple[str, str]:
    """(level, what kind of government it is, in words)."""
    if row["state"] == "DC":
        return "Other", "District government"
    if row["type"] == "Consortia":
        return "Other", "HOME consortium"
    if row["type"] in ("Urban County", "Hawaii County"):
        if row["state"] == "LA":
            return "County", "Parish government"
        if unit is not None and unit["kind"] != "county":
            return "County", "City and county government"
        return "County", "County government"
    if row["state"] == "PR":
        return "Other", "Municipio government"
    code = unit["code"] if unit else ""
    if unit is None:
        m = SUFFIX.search(row["name"])
        code = m.group(1).lower() if m else ""
    if code in ("town", "township", "charter township", "civil township", "village", "borough"):
        word = "township" if code.endswith("township") else code
        return "Other", f"{word.capitalize()} government"
    if code in ("city and county", "consolidated government", "unified government", "metro government",
                "metropolitan government", "urban county government") or row["name"].endswith(("County", "City/County")):
        return "City", "City and county government"
    return "City", "City government"


def shown_name(row: dict, unit: dict | None, places: Places) -> str:
    """HUD's name, with abbreviations spelled out and a county spelled as data/counties.json.gz has it (HUD writes
    "Mchenry County")."""
    name = row["name"]
    for short, long in SHORT:
        name = re.sub(short, long, name)
    if row["type"] == "Hawaii County":
        return COUNTY_SUFFIX.sub("", re.sub(r"^county of\s+", "", name, flags=re.I)) + " County"
    m = COUNTY_SUFFIX.search(name)
    if row["type"] in ("Urban County", "Consortia") and m:
        county = places.county(row["state"], name)
        if county:
            return f"{readable(county)} {m.group(1)}"
    return SUFFIX.sub(lambda s: " " + s.group(1).title(), name) if SUFFIX.search(name) else name


def match(row: dict, census: Census, places: Places) -> tuple[dict | None, list[str]]:
    """(the grantee's Census record or None, the counties it serves as far as they can be told)."""
    state, name = row["state"], row["name"]
    if state == "DC":
        return census.only(state), [places.county(state, name) or name]
    if row["type"] == "Urban County":
        unit = census.county_unit(state, row["key"], name)
        county = places.county(state, unit["county_area"]) if unit else None
        county = county or places.county(state, name)
        return unit, [county] if county else []
    if row["type"] == "Hawaii County":
        unit = census.county_by_name(state, name)
        county = places.county(state, re.sub(r"^county of\s+", "", name, flags=re.I))
        return unit, [county] if county else []
    if row["type"] == "Consortia":
        # HUD names a consortium by the government that leads it. Its members aren't listed, so the only county
        # given is the lead's own.
        if COUNTY_SUFFIX.search(name):
            unit = census.county_by_name(state, name) or census.city(state, name)
            county = places.county(state, name)
            return unit, [county] if county else []
        unit = census.city(state, name)
        return unit, city_counties(row, unit, census, places)
    unit = census.city(state, name)
    if state == "PR":
        county = places.county(state, SUFFIX.sub("", name))
        return unit, [county] if county else []
    return unit, city_counties(row, unit, census, places)


def build(hud: list[dict], units: list[dict], counties: dict, fiscal_year: str) -> tuple[list[dict], dict]:
    """(one entry per local government with CDBG or HOME money, what was left out and what didn't match)."""
    census, places = Census(units), Places(counties)
    out, stats = [], {"grantees": len(hud), "states_and_territories": 0, "no_cdbg_or_home": 0,
                      "no_census_record": [], "no_county": []}
    seen: set[str] = set()
    for row in hud:
        if row["type"] in NOT_LOCAL and row["state"] != "DC":
            stats["states_and_territories"] += 1
            continue
        programs = {p: row[p] for p in PROGRAMS if row[p] > 0}
        if not programs:
            stats["no_cdbg_or_home"] += 1
            continue
        if not row["key"] or row["key"] in seen:
            raise ValueError(f"{row['name']}: HUD key missing or used twice")
        seen.add(row["key"])
        unit, served = match(row, census, places)
        level, kind = describe(row, unit)
        entry = {
            "id": f"hud-{row['key']}",
            "name": shown_name(row, unit, places),
            "state": row["state"],
            "level": level,
            "kind": kind,
            "counties": served,
            "area": area_text(row["state"], served),
            "programs": programs,
            "fiscal_year": fiscal_year,
            "source": f"HUD FY {fiscal_year} formula allocations",
            "as_of": HUD_AS_OF,
        }
        if row["consortium"] and "HOME" in programs:
            entry["home_consortium"] = True  # the HOME amount is for the whole consortium this government leads
        site = website(unit["web"]) if unit else ""
        if unit:
            entry["census_id"] = unit["id"]
        if site:
            entry["website"] = site
        out.append(entry)
    out = one_each(out)
    for e in out:
        if not e["counties"]:
            stats["no_county"].append(f"{e['state']} {e['name']} ({e['kind']})")
        if "census_id" not in e:
            stats["no_census_record"].append(f"{e['state']} {e['name']} ({e['kind']})")
    out.sort(key=lambda e: (e["state"], e["name"].lower(), e["id"]))
    return out, stats


def one_each(entries: list[dict]) -> list[dict]:
    """One entry per government. HUD lists a government that gets its own CDBG money and also leads a HOME consortium
    under a different name twice; the consortium row's money joins the government's own entry. Any other pair sharing
    a Census record means a wrong join, and stops the run."""
    out: list[dict] = []
    by_unit: dict[str, dict] = {}
    for e in sorted(entries, key=lambda e: e["kind"] == "HOME consortium"):
        first = by_unit.get(e.get("census_id", ""))
        if first is None:
            out.append(e)
            if "census_id" in e:
                by_unit[e["census_id"]] = e
            continue
        if e["kind"] != "HOME consortium" or set(first["programs"]) & set(e["programs"]):
            raise ValueError(f"{e['state']} {e['name']} and {first['name']} matched the same Census record")
        first["programs"] = {p: v for p in PROGRAMS for v in [first["programs"].get(p) or e["programs"].get(p)] if v}
        first["home_consortium"] = True
        first["counties"] = sorted(set(first["counties"]) | set(e["counties"]))
        first["area"] = area_text(first["state"], first["counties"])
    return out


def check(funders: list[dict]) -> list[str]:
    """What is wrong with the entries, in plain words; empty when fine. The export runs this too."""
    problems = []
    allowed = {"id", "name", "state", "level", "kind", "counties", "area", "programs", "fiscal_year", "source", "as_of",
               "home_consortium", "website", "census_id"}
    for f in funders:
        who = f"{f.get('state')} {f.get('name')}"
        if set(f) - allowed:  # no score, deadline, eligibility or contact field can slip in
            problems.append(f"{who}: unexpected fields {sorted(set(f) - allowed)}")
        if not f.get("name") or f.get("level") not in LEVELS:
            problems.append(f"{who}: needs a name and a level of {', '.join(LEVELS)}")
        programs = f.get("programs") or {}
        if not programs or set(programs) - set(PROGRAMS) or any(not isinstance(v, int) or v <= 0 for v in programs.values()):
            problems.append(f"{who}: programs must be CDBG or HOME dollar amounts above 0")
        if "website" in f and website(f["website"]) != f["website"]:
            problems.append(f"{who}: website {f['website']!r} isn't a web address")
        if any("@" in str(v) for v in f.values()):
            problems.append(f"{who}: holds an @, which could be an email address")
    return problems


def load(path: Path = OUT) -> dict:
    """The committed directory, or {} when there is none. A bad entry stops the export."""
    if not path.exists():
        return {}
    payload = json.loads(gzip.decompress(path.read_bytes()))
    problems = check(payload.get("funders") or [])
    if problems:
        raise ValueError(f"{path.name} has problems:\n  " + "\n  ".join(problems[:20]))
    return payload


# ---------------- running it ----------------

def download(url: str, folder: Path) -> Path:
    """One file into `folder`, after the project's crawling rule (robots.txt, terms) for it and every redirect."""
    from . import cycles  # here, not at the top: cycles imports export_web, which imports this module

    cycles.session().headers.update({"User-Agent": AGENT, "Accept": "*/*"})
    with cycles.fetch_page(url, timeout=(10, 300), stream=True) as r:
        r.raise_for_status()
        path = folder / url.rsplit("/", 1)[1]
        size = 0
        with path.open("wb") as fh:
            for chunk in r.iter_content(65536):
                size += len(chunk)
                if size > MAX_DOWNLOAD:
                    raise ValueError(f"{url} is larger than expected")
                fh.write(chunk)
    print(f"read {url} ({size:,} bytes)")
    return path


def read_day(*saved: Path | None) -> date:
    """The day the data was read: a saved copy's own date (the older of them), or today for a fresh download."""
    return min((date.fromtimestamp(p.stat().st_mtime) for p in saved if p), default=date.today())


def write(path: Path, funders: list[dict], fiscal_year: str, read_at: str) -> None:
    payload = {
        "fetched_at": read_at,
        "fiscal_year": fiscal_year,
        "census_year": CENSUS_YEAR,
        "sources": [
            {"name": f"HUD FY {fiscal_year} CPD formula program allocations", "page": HUD_PAGE, "file": HUD_FILE,
             "as_of": HUD_AS_OF},
            {"name": f"Census Bureau {CENSUS_YEAR} Government Units listing", "page": CENSUS_PAGE, "file": CENSUS_FILE,
             "as_of": CENSUS_AS_OF},
        ],
        "funders": funders,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    path.write_bytes(gzip.compress(text, compresslevel=9, mtime=0))


def summary(funders: list[dict]) -> dict[str, dict[str, int]]:
    """Per state: entries, with and without a website, matched to a county, with a Census record."""
    out: dict[str, dict[str, int]] = {}
    for f in funders:
        s = out.setdefault(f["state"], {"entries": 0, "county": 0, "city": 0, "other": 0, "website": 0, "no_website": 0,
                                        "with_counties": 0, "census": 0})
        s["entries"] += 1
        s[f["level"].lower()] += 1
        s["website" if f.get("website") else "no_website"] += 1
        s["with_counties"] += bool(f["counties"])
        s["census"] += "census_id" in f
    return dict(sorted(out.items()))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--hud", type=Path, help="a saved copy of the HUD allocations workbook")
    ap.add_argument("--census", type=Path, help="a saved copy of the Census Government Units zip")
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--read-at", type=date.fromisoformat,
                    help="the day the files were read, yyyy-mm-dd (default: today, or the older saved copy's own date)")
    args = ap.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        hud_path = args.hud or download(HUD_FILE, folder)
        census_path = args.census or download(CENSUS_FILE, folder)
        fiscal_year, hud = hud_rows(hud_path.read_bytes())
        units = census_units(census_path.read_bytes())
    counties = json.loads(gzip.decompress((local.LOCAL / "counties.json.gz").read_bytes()))
    funders, stats = build(hud, units, counties, fiscal_year)
    problems = check(funders)
    if len(funders) < MIN_FUNDERS:
        problems.append(f"only {len(funders)} funders; keeping the previous file")
    if problems:
        raise SystemExit("\n".join(problems[:40]))
    write(args.out, funders, fiscal_year, (args.read_at or read_day(args.hud, args.census)).isoformat())
    with_site = sum(1 for f in funders if f.get("website"))
    print(f"{stats['grantees']} HUD grantee rows; {stats['states_and_territories']} states and territories and "
          f"{stats['no_cdbg_or_home']} with no CDBG or HOME money left out; {len(units)} Census units read")
    print(f"wrote {len(funders)} funders to {args.out} ({args.out.stat().st_size / 1e3:.1f} kB): "
          f"{sum('census_id' in f for f in funders)} matched to a Census record, {with_site} with a website, "
          f"{sum(bool(f['counties']) for f in funders)} matched to a county")
    for label, rows in (("No Census record", stats["no_census_record"]), ("No county", stats["no_county"])):
        print(f"{label} ({len(rows)}): " + "; ".join(rows))


if __name__ == "__main__":
    main()
