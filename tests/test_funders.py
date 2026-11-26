"""The local funder directory (grantmatch/funders.py): reading the two federal workbooks, joining them, and keeping
funders apart from grants. Every government and figure in the made-up rows is invented for the test."""
import gzip
import io
import json
import os
import re
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path
from xml.sax.saxutils import escape

import pytest

from grantmatch import cycles, export_web, freshness, funders, server_data

ROOT = Path(__file__).resolve().parent.parent
HUD_HEAD = ["NAME", "STA", "TYPE", "CDBG", "RHP", "HOME", "ESG", "HOPWA", "HTF", "KEY", "CNSRT"]
CENSUS_HEAD = ["CENSUS_ID_PID6", "UNIT_NAME", "UNIT_TYPE", "TITLE", "ADDRESS1", "CITY", "STATE", "WEB_ADDRESS",
               "POLITICAL_CODE_DESCRIPTION", "POPULATION", "FIPS_STATE", "FIPS_COUNTY", "COUNTY_AREA_NAME", "ACTIVE"]


def column(i: int) -> str:
    return chr(65 + i)


def workbook(sheets: dict[str, list[list[str]]]) -> bytes:
    """A small .xlsx with inline strings, enough for the reader."""
    out = io.BytesIO()
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    with zipfile.ZipFile(out, "w") as z:
        listed, targets = [], []
        for n, (name, rows) in enumerate(sheets.items(), 1):
            listed.append(f'<sheet name="{name}" sheetId="{n}" r:id="rId{n}"/>')
            targets.append(f'<Relationship Id="rId{n}" Type="x" Target="worksheets/sheet{n}.xml"/>')
            body = "".join(
                f'<row r="{r}">' + "".join(f'<c r="{column(i)}{r}" t="inlineStr"><is><t>{escape(v)}</t></is></c>'
                                           for i, v in enumerate(row) if v != "") + "</row>"
                for r, row in enumerate(rows, 1))
            z.writestr(f"xl/worksheets/sheet{n}.xml", f'<worksheet xmlns="{ns}"><sheetData>{body}</sheetData></worksheet>')
        z.writestr("xl/workbook.xml", f'<workbook xmlns="{ns}" xmlns:r="{rel}"><sheets>{"".join(listed)}</sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels",
                   f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{"".join(targets)}</Relationships>')
    return out.getvalue()


def hud_book(rows: list[list[str]], title="FY 2026 Community Planning and Development Formula Program Allocations") -> bytes:
    return workbook({"Allocations": [[title], HUD_HEAD, *rows]})


def hud_row(name, state, kind, cdbg="0", home="0", key="", consortium=""):
    return [name, state, kind, cdbg, "0", home, "0", "0", "0", key, consortium]


def census_zip(rows: list[list[str]]) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("Govt_Units.xlsx", workbook({"General Purpose": [CENSUS_HEAD, *rows], "Special District": [["x"]]}))
    return out.getvalue()


def unit(uid, name, kind="2 - MUNICIPAL", code="CITY", fips="48", county="201", area="HARRIS", web="", population="90,000",
         mailing="TX"):
    return [uid, name, kind, "SYNTHETIC OFFICER TITLE", "1 SYNTHETIC ST", "TOWN", mailing, web, code, population, fips,
            county, area, "Y"]


COUNTIES = {
    "TX": {"Harris": ["Houston", "Katy", "Bigtown"], "Fort Bend": ["Houston", "Katy"], "Waller": ["Katy"],
           "Houston": ["Crockett"], "Miller": ["Twintown"]},
    "AR": {"Miller": ["Twintown"]},
    "VA": {"Richmond": ["Richmond", "Warsaw"], "Norfolk": ["Norfolk"]},
    "CT": {"Hartford": ["Samplefield"]},
    "IL": {"McHenry": ["Samplefield"]},
    "NJ": {"Camden": ["Washington"], "Morris": ["Washington"]},
    "PR": {"Bayam\u00c3\u00b3n": ["Bayam\u00c3\u00b3n"]},  # as data/counties.json.gz holds it
    "DC": {"District of Columbia": ["Washington"]},
}


def built(hud_rows, units):
    fiscal_year, hud = funders.hud_rows(hud_book(hud_rows))
    out, stats = funders.build(hud, funders.census_units(census_zip(units)), COUNTIES, fiscal_year)
    assert funders.check(out) == []
    return {e["name"]: e for e in out}, stats


# ---------------- reading ----------------

def test_hud_rows_take_the_year_from_the_title_and_skip_footnotes():
    year, rows = funders.hud_rows(hud_book([
        hud_row("Bigtown", "TX", "Principal City", "100.4", "50.6", "480001", "48C001"),
        hud_row("*A footnote about one allocation.", "", ""),
    ]))
    assert year == "2026"
    assert rows == [{"name": "Bigtown", "state": "TX", "type": "Principal City", "key": "480001", "CDBG": 100,
                     "HOME": 51, "consortium": True}]


def test_a_repeated_key_in_the_consortium_column_is_not_a_consortium():
    _, rows = funders.hud_rows(hud_book([hud_row("District of Columbia", "DC", "Non-entitlement", "1", "1", "110006", "119999")]))
    assert rows[0]["consortium"] is False


@pytest.mark.parametrize("book", [
    hud_book([hud_row("X", "TX", "Some new type", "1")]),
    hud_book([], title="Formula allocations"),
    workbook({"Allocations": [["FY 2026"], ["NAME", "STA"]]}),
])
def test_a_file_that_changed_shape_stops_the_run(book):
    with pytest.raises(ValueError):
        funders.hud_rows(book)


def test_census_reads_the_state_from_fips_and_nothing_about_people():
    units = funders.census_units(census_zip([
        unit("1", "CITY OF TWINTOWN", fips="05", county="091", area="MILLER", mailing="TX"),
        unit("2", "CITY-PARISH OF SAMPLEVILLE", fips="22"),
        unit("3", "CHARTER TOWNSHIP OF SAMPLE", kind="3 - TOWNSHIP", code="CHARTER TOWNSHIP"),
    ]))
    assert [(u["name"], u["state"], u["kind"]) for u in units] == [
        ("TWINTOWN", "AR", "municipal"), ("SAMPLEVILLE", "LA", "municipal"), ("SAMPLE", "TX", "township")]
    assert "SYNTHETIC" not in json.dumps(units)  # no job title or street address is read


@pytest.mark.parametrize("part", [
    b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><x>&a;</x>',
    '<?xml version="1.0" encoding="UTF-16"?><x/>'.encode("utf-16"),
    b'<?xml version="1.0" encoding="cp037"?><x/>',
])
def test_a_workbook_part_with_a_document_type_or_another_encoding_is_refused(part):
    with pytest.raises(ValueError):
        funders._xml(part)


@pytest.mark.parametrize("raw, kept", [
    ("http://www.example.gov/", "http://www.example.gov/"),
    ("https://example.org/city#top", "https://example.org/city#top"),
    ("SAMPLECOUNTY.GOV", "http://SAMPLECOUNTY.GOV"),
    ("www.example.us", "http://www.example.us"),
    ("mayor@example.gov", ""),
    ("http://user@example.gov", ""),
    ("call the clerk", ""),
    ("mailto:clerk.example.gov", ""),
    ("javascript:alert(1)", ""),
    ("ftp://example.gov", ""),
    ("http://localhost", ""),
    ("Whitepages.com", ""),
    ("http://www.example.com.www.city-data.com/city/x.html", ""),
    ("http://www.avvada.org", ""),  # looks mistyped in the Census file: no link, and no guess in its place
    ("http://www.mobilcountyal.gov", ""),
    ("http://www.voanokeva.gov", ""),
    ("http://www.bristolya.org", ""),
    ("http://www.ppine.com", ""),
    ("http://www.grants.passonegon.gov", ""),
    ("http://www.w.w.w.hopewellva.gov", ""),
    ("http://www.w.austintexas.gov", ""),
    ("http://www.w.toaks.org", ""),
    ("http://www.cityof.meriden.org", ""),
    ("http://www.city.of.bridgeton.com", ""),
    ("http://www.austintexas.gov", "http://www.austintexas.gov"),  # only the malformed form is withheld
    ("http://www.cityof.lawton.ok.us", "http://www.cityof.lawton.ok.us"),
    ("http://[bad", ""),
    ("[bad", ""),
    ("", ""),
])
def test_a_website_is_the_census_one_or_none(raw, kept):
    assert funders.website(raw) == kept


# ---------------- joining ----------------

def test_an_urban_county_joins_by_fips_code_and_name():
    got, _ = built(
        [hud_row("Harris County", "TX", "Urban County", "200", "10", "489201", "48C900")],
        [unit("7", "COUNTY OF HARRIS", kind="1 - COUNTY", code="COUNTY", web="http://harris.example.gov")])
    e = got["Harris County"]
    assert (e["level"], e["kind"], e["counties"], e["area"]) == ("County", "County government", ["Harris"], "Harris County")
    assert e["programs"] == {"CDBG": 200, "HOME": 10} and e["home_consortium"] is True
    assert e["website"] == "http://harris.example.gov" and e["census_id"] == "7"
    assert (e["fiscal_year"], e["source"]) == ("2026", "HUD FY 2026 formula allocations") and e["as_of"]


def test_a_code_that_points_at_another_county_gets_no_website():
    got, stats = built(
        [hud_row("Fort Bend County", "TX", "Urban County", "200", key="489201")],
        [unit("7", "COUNTY OF HARRIS", kind="1 - COUNTY", code="COUNTY", web="http://harris.example.gov")])
    e = got["Fort Bend County"]
    assert "website" not in e and "census_id" not in e and e["counties"] == ["Fort Bend"]
    assert stats["no_census_record"]


def test_a_city_gets_the_census_county_never_one_guessed_from_a_place_name():
    # The places file has a "Houston" in Harris and Fort Bend; only the Census record's county is used.
    rows = [hud_row("Houston", "TX", "Principal City", "300", key="480010")]
    got, _ = built(rows, [unit("8", "CITY OF HOUSTON")])
    assert got["Houston"]["counties"] == ["Harris"] and got["Houston"]["area"] == "Harris County"
    got, _ = built(rows, [unit("8", "CITY OF HOUSTON"),
                          unit("9", "VILLAGE OF HOUSTON", code="VILLAGE", county="999", area="WALLER", population="400")])
    assert got["Houston"]["census_id"] == "8"  # the city, not the village of the same name


def test_a_name_two_governments_share_is_left_unmatched_rather_than_guessed():
    rows = [hud_row("Washington Township", "NJ", "Metro City", "100", key="340001")]
    units = [unit(str(i), "TOWNSHIP OF WASHINGTON", kind="3 - TOWNSHIP", code="TOWNSHIP", fips="34", area=area,
                  web=f"http://{area.lower()}.example.org", population="20,000")
             for i, area in enumerate(["CAMDEN", "MORRIS"])]
    got, stats = built(rows, units)
    assert "website" not in got["Washington Township"] and got["Washington Township"]["counties"] == []
    assert stats["no_county"] == ["NJ Washington Township (Township government)"]


def test_a_township_and_hud_abbreviations():
    got, _ = built([hud_row("Samplefield Twp", "IL", "Metro City", "100", key="170001")],
                   [unit("4", "TOWNSHIP OF SAMPLEFIELD", kind="3 - TOWNSHIP", code="TOWNSHIP", fips="17", area="MCHENRY")])
    e = got["Samplefield Township"]
    assert (e["level"], e["kind"], e["area"]) == ("Other", "Township government", "McHenry County")


def test_new_york_city_is_its_five_counties():
    fiscal_year, hud = funders.hud_rows(hud_book([hud_row("New York", "NY", "Principal City", "900", key="360001")]))
    units = funders.census_units(census_zip([unit("1", "CITY OF NEW YORK", fips="36", county="061", area="NEW YORK CITY")]))
    boroughs = ["Bronx", "Kings", "New York", "Queens", "Richmond"]
    out, _ = funders.build(hud, units, {"NY": {c: ["New York"] for c in boroughs}}, fiscal_year)
    assert out[0]["counties"] == boroughs
    assert out[0]["area"] == "Bronx, Kings, New York, Queens and Richmond counties"


def test_an_independent_city_that_shares_a_county_name_is_left_at_state_level():
    got, _ = built(
        [hud_row("Richmond", "VA", "Principal City", "100", key="510001"),
         hud_row("Norfolk", "VA", "Principal City", "100", key="510002")],
        [unit("1", "CITY OF RICHMOND", fips="51", county="760", area="RICHMOND CITY"),
         unit("2", "COUNTY OF RICHMOND", kind="1 - COUNTY", code="COUNTY", fips="51", county="159", area="RICHMOND"),
         unit("3", "CITY OF NORFOLK", fips="51", county="710", area="NORFOLK CITY")])
    assert got["Richmond"]["counties"] == [] and got["Richmond"]["area"] == ""
    assert got["Norfolk"]["counties"] == ["Norfolk"] and got["Norfolk"]["area"] == "Norfolk"


def test_a_planning_region_falls_back_to_a_place_name_in_one_county():
    got, _ = built([hud_row("Samplefield", "CT", "Metro City", "100", key="090001")],
                   [unit("5", "CITY OF SAMPLEFIELD", fips="09", county="110", area="CAPITOL")])
    assert got["Samplefield"]["counties"] == ["Hartford"]


def test_consortia_the_district_and_puerto_rico():
    got, _ = built(
        [hud_row("Harris County", "TX", "Consortia", home="500", key="48C100", consortium="48C100"),
         hud_row("District of Columbia", "DC", "Non-entitlement", "900", "100", "110006", "119999"),
         hud_row("Bayamon Municipio", "PR", "Metro City", "100", key="720001"),
         hud_row("State of Texas", "TX", "Non-entitlement", "900", key="489999"),
         hud_row("Guam", "GU", "Insular Area", "900", key="660001"),
         hud_row("Harris County", "KY", "Urban County", key="219111")],  # no CDBG or HOME: not listed
        [unit("6", "WASHINGTON DC", fips="11", county="001", area="WASHINGTON DC", web="http://dc.example.gov"),
         unit("7", "COUNTY OF HARRIS", kind="1 - COUNTY", code="COUNTY")])
    assert set(got) == {"Harris County", "District of Columbia", "Bayamon Municipio"}
    assert (got["Harris County"]["level"], got["Harris County"]["kind"]) == ("Other", "HOME consortium")
    dc = got["District of Columbia"]
    assert (dc["kind"], dc["counties"], dc["website"]) == ("District government", ["District of Columbia"], "http://dc.example.gov")
    assert "home_consortium" not in dc
    pr = got["Bayamon Municipio"]
    # the county name is kept as data/counties.json.gz has it, so the page matches it; the words are put right
    assert pr["counties"] == ["Bayam\u00c3\u00b3n"] and pr["area"] == "Bayam\u00f3n Municipio"


def test_a_government_hud_lists_twice_is_one_entry():
    got, _ = built(
        [hud_row("Bigtown", "TX", "Principal City", "200", key="480001"),
         hud_row("Bigtown", "TX", "Consortia", home="700", key="48C200", consortium="48C200")],
        [unit("3", "CITY OF BIGTOWN")])
    assert list(got) == ["Bigtown"]
    assert got["Bigtown"]["programs"] == {"CDBG": 200, "HOME": 700} and got["Bigtown"]["home_consortium"] is True


def test_two_grantees_on_one_census_record_stop_the_run():
    with pytest.raises(ValueError, match="same Census record"):
        built([hud_row("Bigtown", "TX", "Principal City", "200", key="480001"),
               hud_row("Bigtown City", "TX", "Metro City", "100", key="480002")], [unit("3", "CITY OF BIGTOWN")])


# ---------------- funders are not grants ----------------

GOOD = {"id": "hud-1", "name": "Sample County", "state": "TX", "level": "County", "kind": "County government",
        "counties": [], "area": "", "programs": {"CDBG": 5}, "fiscal_year": "2026", "source": "x", "as_of": "2026-01-01"}


@pytest.mark.parametrize("change", [
    {"score": 80}, {"deadline": "2027-01-01"}, {"nonprofit_eligible": True}, {"contact": "A Person"},
    {"email": "x"}, {"website": "clerk@example.gov"}, {"name": "ask clerk@example.gov"}, {"programs": {"ESG": 5}},
    {"programs": {}}, {"programs": {"CDBG": 0}}, {"level": "Foundation"},
])
def test_the_check_refuses_anything_that_reads_like_a_grant_or_a_contact(change):
    assert funders.check([GOOD]) == []
    assert funders.check([{**GOOD, **change}])


def test_neither_scorer_nor_the_ranking_reads_the_directory():
    for path in ("grantmatch/match.py", "grantmatch/rank_more.py", "web/src/score.ts", "web/src/rank.ts",
                 "web/src/entries.ts", "web/src/exports.ts", "web/src/summary.ts", "web/src/shortlist.ts",
                 "web/src/server/preview.ts", "web/src/server/digest.ts", "web/scripts/score-eto.ts"):
        assert not re.search(r"[\"'./]funders?(list)?[\"']|loadFunders|funders-", (ROOT / path).read_text(encoding="utf-8")), path


# ---------------- the committed directory ----------------

@pytest.fixture(scope="module")
def committed():
    return funders.load(ROOT / "data" / "funders.json.gz")


def test_the_committed_directory_is_whole_and_labelled(committed):
    rows = committed["funders"]
    assert committed["fiscal_year"] == "2026" and committed["fetched_at"] == "2026-11-25"  # a date, no time
    assert [s["page"] for s in committed["sources"]] == [funders.HUD_PAGE, funders.CENSUS_PAGE]
    assert len(rows) >= funders.MIN_FUNDERS and len({r["id"] for r in rows}) == len(rows)
    assert {"FL", "KS", "DC", "PR", "WY"} <= {r["state"] for r in rows}
    counties = json.loads(gzip.decompress((ROOT / "data" / "counties.json.gz").read_bytes()))
    for r in rows:
        assert set(r["counties"]) <= set(counties[r["state"]]), r["name"]
        assert r["programs"] and r["fiscal_year"] == "2026"
        assert bool(r["area"]) == bool(r["counties"])
    assert "@" not in json.dumps(rows)
    for r in rows:  # no withheld address is in the file
        assert "website" not in r or funders.website(r["website"]) == r["website"], r["name"]
    plantation = next(r for r in rows if r["state"] == "FL" and r["name"] == "Plantation")
    assert plantation["counties"] == ["Broward"]  # not Sarasota, which has another place of that name
    new_york = next(r for r in rows if r["state"] == "NY" and r["name"] == "New York")
    assert len(new_york["counties"]) == 5
    assert all(len(r["counties"]) <= 1 for r in rows if r is not new_york)
    manatee = next(r for r in rows if r["state"] == "FL" and r["name"] == "Manatee County")
    assert manatee["counties"] == ["Manatee"] and manatee["website"].startswith("http") and manatee["census_id"]


def test_the_coverage_table_in_the_docs_matches_the_directory(committed):
    text = (ROOT / "docs" / "county-coverage.md").read_text(encoding="utf-8")
    table = text.split("### Directory coverage by state")[1].split("\n## ")[0]
    rows = {m[0]: [int(x.replace(",", "")) for x in m[1:]]
            for m in re.findall(r"^\| ([A-Z]{2}|All) \| ([\d,]+) \| ([\d,]+) \| ([\d,]+) \| ([\d,]+) \|$", table, re.M)}
    expected = {st: [s["entries"], s["website"], s["no_website"], s["with_counties"]]
                for st, s in funders.summary(committed["funders"]).items()}
    expected["All"] = [sum(col) for col in zip(*expected.values())]
    assert rows == expected


# ---------------- export, site and freshness ----------------

def test_the_export_writes_one_small_file_per_state_with_nothing_to_rank_by(tmp_path, committed):
    meta: dict = {}
    export_web.write_funders(tmp_path, meta, ROOT / "data" / "funders.json.gz")
    info = meta["funders"]
    assert info["fiscal_year"] == "2026" and info["hud_page"] == funders.HUD_PAGE and info["census_page"] == funders.CENSUS_PAGE
    assert sorted(p.name for p in tmp_path.iterdir()) == [f"funders-{s}.json" for s in info["states"]]
    total = 0
    for state in info["states"]:
        rows = json.loads((tmp_path / f"funders-{state}.json").read_text(encoding="utf-8"))
        total += len(rows)
        for r in rows:
            assert set(r) <= set(export_web.FUNDER_FIELDS)
    assert total == len(committed["funders"])
    assert sum(p.stat().st_size for p in tmp_path.iterdir()) < 400_000  # all states together
    site = tmp_path / "site"
    assert server_data.copy_public(tmp_path, site) == sorted(f"funders-{s}.json" for s in info["states"])


def test_no_directory_means_no_section(tmp_path):
    meta: dict = {}
    export_web.write_funders(tmp_path, meta, tmp_path / "missing.json.gz")
    assert meta == {} and not list(tmp_path.iterdir())


def test_freshness_lists_the_directory_and_never_its_websites(committed):
    read = date.fromisoformat(committed["fetched_at"][:10])

    def source(today):
        sources, links, _ = freshness.inventory(today, lambda *a: None, ROOT / "data")
        return next(s for s in sources if s["key"] == "funders"), links

    got, links = source(read + timedelta(days=400))
    assert got["limit"] == 400 and not got["stale"] and got["pages"] == [funders.HUD_PAGE, funders.CENSUS_PAGE]
    assert source(read + timedelta(days=401))[0]["stale"]
    assert f"{len(committed['funders'])} funders" in got["notes"][0] and "aren't link-checked" in got["notes"][0]
    from_directory = {url for url, users in links.items() if any(u.endswith(got["name"]) for u in users)}
    assert from_directory == {funders.HUD_PAGE, funders.CENSUS_PAGE}
    # a government's own site is a link only if a hand-kept list or a state call already pointed at it
    for url, users in links.items():
        if url not in from_directory:
            assert not any("Local funder" in u for u in users)


def test_the_read_date_is_the_saved_copys_own_date(tmp_path):
    older, newer = tmp_path / "hud.xlsx", tmp_path / "census.zip"
    for path, day in ((older, date(2026, 3, 2)), (newer, date(2026, 4, 5))):
        path.write_bytes(b"x")
        noon = datetime(day.year, day.month, day.day, 12).timestamp()
        os.utime(path, (noon, noon))
    assert funders.read_day(newer, older) == date(2026, 3, 2)
    assert funders.read_day(None, newer) == date(2026, 4, 5)
    assert funders.read_day(None, None) == date.today()


def test_a_download_goes_through_the_crawling_rule_with_the_project_agent(tmp_path, monkeypatch):
    asked = []

    def off(url, **kwargs):
        asked.append((url, cycles.session().headers["User-Agent"]))
        raise cycles.OffLimits("robots.txt asks automated visitors to stay out")

    monkeypatch.setattr(cycles, "fetch_page", off)
    monkeypatch.setattr(cycles, "_local", type(cycles._local)())  # a session of its own, so no other test sees the agent
    with pytest.raises(cycles.OffLimits):
        funders.download(funders.HUD_FILE, tmp_path)
    assert asked == [(funders.HUD_FILE, "grant-matcher (github.com/RendellRich/grant-matcher)")]
    assert not list(tmp_path.iterdir())


def test_no_em_dashes_in_what_this_adds():
    for path in ("grantmatch/funders.py", "tests/test_funders.py", "web/src/funders.ts", "web/src/funderlist.tsx"):
        assert "\u2014" not in (ROOT / path).read_text(encoding="utf-8"), path
