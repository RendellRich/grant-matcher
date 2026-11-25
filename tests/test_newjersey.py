"""New Jersey Treasury's state grant opportunities CSV into state program records (grantmatch/newjersey.py)."""
from grantmatch import newjersey as nj

CSV = (
    "Environment,Natural Climate Solutions Grant Program Round 2,https://dep.nj.gov/ncs_r2_nofa.pdf,"
    "NJ Department of Environmental Protection,12/31/2026\n"
    "Labor ,Opportunity Partnership Grant (OPG),https://www.nj.gov/labor/opg.pdf,NJ Department of Labor & Workforce Development,11/18/2026\n"
    "Environment,Drinking Water State Revolving Fund,https://dep.nj.gov/dwsrf/,NJ Department of Environmental Protection,Rolling \n"
    "Health; Community Development ,\"Healthy Homes, Healthy Kids 2027\",https://www.nj.gov/dca/hh.pdf,NJ Department of Community Affairs ,6/30/2027\n"
    "short,row\n"
)


def test_rows_are_read_by_position_and_trimmed():
    rows = nj.rows(CSV)
    assert len(rows) == 4   # the short row is left out
    assert rows[1]["category"] == "Labor" and rows[2]["deadline"] == "Rolling"
    assert rows[3]["title"] == "Healthy Homes, Healthy Kids 2027" and rows[3]["agency"] == "NJ Department of Community Affairs"


def test_a_row_becomes_an_open_call_that_says_to_read_the_notice():
    rec = nj.normalize(nj.rows(CSV)[0])
    assert rec["id"] == "nj-natural-climate-solutions-grant-program-round-2" and rec["state"] == "NJ"
    assert rec["title"] == "Natural Climate Solutions Grant Program Round 2"
    assert rec["agency"] == "NJ Department of Environmental Protection"
    assert rec["url"] == "https://dep.nj.gov/ncs_r2_nofa.pdf" and rec["web"] == nj.SITE
    assert (rec["closes"], rec["deadlines"], rec["status"]) == ("2026-12-31", "2026-12-31", "active")
    # no eligibility field: kept, with a note to read the notice (as Iowa's "says neither" grants are)
    assert rec["nonprofit_eligible"] is True and rec["applicant_types"] == nj.WHO and "read the notice" in nj.WHO
    assert rec["subjects"] == "Environment" and rec["assistance"] == "Grant" and rec["loan"] is False


def test_rolling_calls_have_no_deadline_and_revolving_funds_are_loans():
    rec = nj.normalize(nj.rows(CSV)[2])
    assert rec["closes"] is None and rec["deadlines"] == "Ongoing"
    assert rec["loan"] is True and rec["assistance"] == "Loan"
    assert nj.normalize(nj.rows(CSV)[3])["subjects"] == "Health; Community Development"


def test_past_and_untitled_rows_are_skipped_with_a_reason():
    rows = nj.rows(CSV) + [{"category": "Law", "title": "", "url": "", "agency": "NJ Department of Law", "deadline": "1/5/2027"}]
    skips = []
    recs = nj.build_records(rows, today="2026-11-25", skips=skips)
    assert [r["id"] for r in recs] == ["nj-drinking-water-state-revolving-fund", "nj-healthy-homes-healthy-kids-2027",
                                       "nj-natural-climate-solutions-grant-program-round-2"]
    assert [(s["id"], s["reason"]) for s in skips] == [("nj-opportunity-partnership-grant-opg", "deadline_passed"), ("nj-", "no_title")]


def test_a_saved_copy_with_a_byte_order_mark_is_read_without_the_network(tmp_path, monkeypatch):
    import gzip
    import json
    monkeypatch.setattr(nj, "fetch_list", lambda: (_ for _ in ()).throw(AssertionError("no network in tests")))
    monkeypatch.setattr(nj, "MIN_ROWS", 1)
    saved = tmp_path / "state-data.csv"
    saved.write_bytes(b"\xef\xbb\xbf" + b"Economic,RETROFIT NJ Program,https://www.njeda.gov/retrofit/,NJ Economic Development Authority,Rolling\n")
    out = tmp_path / "nj.json.gz"
    assert nj.build(out, tmp_path / "skipped.json.gz", saved) == 1
    payload = json.loads(gzip.decompress(out.read_bytes()))
    assert payload["state"] == "NJ" and payload["programs"][0]["id"] == "nj-retrofit-nj-program"
    assert payload["programs"][0]["subjects"] == "Economic"   # the byte order mark isn't part of the first category


def test_titles_that_differ_only_at_the_end_stay_two_records():
    long = "Growing Apprenticeship in Nontraditional Sectors (GAINS) Round"
    rows = [{"category": "Labor", "title": f"{long} {n}", "url": f"https://www.nj.gov/labor/gains-r{n}.pdf",
             "agency": "NJ Department of Labor & Workforce Development", "deadline": "12/4/2026"} for n in (1, 2)]
    skips = []
    recs = nj.build_records(rows, today="2026-11-25", skips=skips)
    assert [r["id"] for r in recs] == ["nj-growing-apprenticeship-in-nontraditional-sectors-gains-round-1",
                                       "nj-growing-apprenticeship-in-nontraditional-sectors-gains-round-2"]
    assert skips == []


def test_the_same_title_twice_keeps_both_keyed_by_its_link_and_a_true_repeat_is_skipped():
    row = {"category": "Health", "title": "Healthcare Preparedness Program", "url": "https://example.nj.gov/a.pdf",
           "agency": "NJ Department of Health", "deadline": "12/4/2026"}
    skips = []
    recs = nj.build_records([row, {**row, "url": "https://example.nj.gov/b.pdf"}, row], today="2026-11-25", skips=skips)
    ids = [r["id"] for r in recs]
    assert len(ids) == 2 and ids[0] == "nj-healthcare-preparedness-program"
    assert ids[1].startswith("nj-healthcare-preparedness-program-") and len(ids[1]) == len(ids[0]) + 7
    assert [s["reason"] for s in skips] == ["duplicate"]
    again = nj.build_records([row, {**row, "url": "https://example.nj.gov/b.pdf"}], today="2026-11-25")
    assert [r["id"] for r in again] == ids   # the same keys on the next refresh


def test_titles_that_say_municipal_or_county_grants_are_not_open_to_nonprofits():
    for title in ("NJ Water Bank Sewer Overflow and Stormwater Reuse Municipal Grants",
                  "County Environmental Health Act Grants (CEHA)"):
        rec = nj.normalize({"category": "Environment", "title": title, "url": "https://dep.nj.gov/x/",
                            "agency": "NJ Department of Environmental Protection", "deadline": "Rolling"})
        assert rec["nonprofit_eligible"] is False and rec["applicant_types"] == nj.GOVERNMENT_SAYS, title
    rec = nj.normalize({"category": "Environment", "title": "Urban & Community Forestry Program", "url": "",
                        "agency": "NJ DEP", "deadline": "Rolling"})
    assert rec["nonprofit_eligible"] is True and rec["applicant_types"] == nj.WHO


def test_a_county_title_that_names_nonprofits_or_a_county_college_stays_open():
    for title in ("Cape May County Open Space Grants for Nonprofit Organizations", "County College Opportunity Grant"):
        rec = nj.normalize({"category": "x", "title": title, "url": "", "agency": "NJ", "deadline": "Rolling"})
        assert rec["nonprofit_eligible"] is True and rec["applicant_types"] == nj.WHO, title
