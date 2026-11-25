"""West Virginia's grants.wv.gov list into state program records (grantmatch/westvirginia.py)."""
from grantmatch import westvirginia as wv


def item(**over):
    base = {
        "Id": 72, "Title": "In Lieu Fee Program",
        "Division": "Department of Environmental Protection Division of Water and Waste Management",
        "TypeOfGrant": "Competitive", "EntityEligible": "Any For-Profit, Non-Profit or Government Agency",
        "PostedDate": "2026-09-15T04:00:00Z", "DueDate1": "2026-12-15T05:00:00Z", "Forecasted": None,
        "Details": "Grants to restore streams and wetlands.",
        "FullDetails": "<div class=\"ExternalClass1\">The <b>In Lieu Fee</b> program&#160;funds mitigation.</div>",
        "Guidelines": "<p>Any Non-Profit that specializes in stream restoration may apply.</p>",
        "HowToApply": "<div>Respond by email to the program.</div>", "LinkToApply": None,
        "ReadMoreLinkURL": "https://dep.wv.gov/wwe/programs/pages/in-lieu-fee.aspx", "LinkURL1": None,
        "ImportantDateTitle1": "Intent to Apply due", "ImportantDate1": "2026-11-30T05:00:00Z",
        "ContactName1": "Pat Lee", "ContactEmail1": "pat@example.gov", "ContactPhone1": "304-555-0100",
        "ContactName2": "Second Person", "Modified": "2026-05-15T13:28:18Z",
    }
    base.update(over)
    return base


def test_a_listing_becomes_an_open_call_record():
    rec = wv.normalize(item(), today="2026-11-25")
    assert rec["id"] == "wv-72" and rec["state"] == "WV" and rec["number"] == ""
    assert rec["title"] == "In Lieu Fee Program" and rec["agency"].startswith("Department of Environmental Protection")
    assert rec["objectives"] == "Grants to restore streams and wetlands. The In Lieu Fee program funds mitigation."
    assert rec["nonprofit_eligible"] is True and rec["applicant_types"] == "Any For-Profit, Non-Profit or Government Agency"
    assert (rec["opens"], rec["closes"], rec["deadlines"], rec["status"]) == ("2026-09-15", "2026-12-15", "2026-12-15", "active")
    assert rec["restrictions"] == "Any Non-Profit that specializes in stream restoration may apply."
    assert rec["application"] == "Respond by email to the program. Intent to Apply due: 2026-11-30."
    assert rec["url"] == rec["web"] == "https://dep.wv.gov/wwe/programs/pages/in-lieu-fee.aspx"
    assert rec["contact"] == "Pat Lee, 304-555-0100"   # the first contact's name and phone, no email address
    assert rec["award"] == "Type: Competitive." and rec["updated"] == "2026-05-15"


def test_dates_are_west_virginia_days_not_utc_days():
    assert wv._day("2026-12-15T05:00:00Z") == "2026-12-15"   # midnight EST
    assert wv._day("2026-07-01T04:00:00Z") == "2026-07-01"   # midnight EDT
    assert wv._day("2026-07-01T03:59:00Z") == "2026-06-30"   # 11:59 pm the night before
    assert wv._day(None) is None and wv._day("soon") is None


def test_the_states_own_eligibility_text_decides_who_can_apply():
    assert wv.who_can_apply("Any legal Entity")[0] is True
    assert wv.who_can_apply("501 C(3) or partner with a 501 C(3) organization")[0] is True
    assert wv.who_can_apply("Community Action Agencies")[0] is True
    assert wv.who_can_apply("Non-Profits; Law Enforcement")[0] is True
    assert wv.who_can_apply("State governments")[0] is False
    assert wv.who_can_apply("Local governments, Public Service Districts")[0] is False
    # nonprofits named only as reviewers don't make it a nonprofit grant
    no, said = wv.who_can_apply("State governments in the watershed can apply.  Projects are reviewed by a team made "
                                "up of state and federal agencies as well as non profits before award.")
    assert no is False and said.startswith("State governments in the watershed can apply.")
    assert wv.who_can_apply("Not open to non-profit organizations.")[0] is False
    yes, said = wv.who_can_apply("")
    assert yes is True and "read the notice" in said


def test_past_undated_untitled_and_invitation_only_rows_are_skipped_with_a_reason():
    rows = [item(),
            item(Id=1, DueDate1="2023-05-01T04:00:00Z"),
            item(Id=2, DueDate1=None, Forecasted="Spring 2023", Modified="2023-01-24T10:00:00Z"),
            item(Id=3, DueDate1=None, Forecasted="Ongoing"),
            item(Id=4, Title=""),
            item(Id=5, HowToApply="Applications are by invitation only.")]
    skips = []
    recs = wv.build_records(rows, today="2026-11-25", skips=skips)
    assert [r["id"] for r in recs] == ["wv-3", "wv-72"]
    rolling = recs[0]
    assert rolling["closes"] is None and rolling["deadlines"] == "Ongoing" and "_rolling" not in rolling
    assert [(s["id"], s["reason"]) for s in skips] == [
        ("wv-1", "deadline_passed"), ("wv-2", "no_deadline"), ("wv-4", "no_title"), ("wv-5", "invitation_only")]
    assert "Spring 2023" in skips[1]["detail"] and "2023-01-24" in skips[1]["detail"]


def test_a_future_posting_is_forecasted_and_a_loan_is_marked():
    rec = wv.normalize(item(PostedDate="2027-01-01T05:00:00Z", Title="Brownfield Revolving Loan Funds",
                            ReadMoreLinkURL=None), today="2026-11-25")
    assert rec["status"] == "forecasted" and rec["opens"] == "2027-01-01"
    assert rec["loan"] is True and rec["assistance"] == "Loan"
    assert rec["url"] == wv.SITE   # no link of its own: the state's list


def test_a_saved_copy_is_read_without_the_network(tmp_path, monkeypatch):
    import gzip
    import json
    monkeypatch.setattr(wv, "fetch_list", lambda: (_ for _ in ()).throw(AssertionError("no network in tests")))
    monkeypatch.setattr(wv, "MIN_ROWS", 1)
    saved = tmp_path / "list.json"
    saved.write_text(json.dumps({"value": [item(DueDate1="2099-01-01T05:00:00Z")]}), encoding="utf-8")
    out = tmp_path / "wv.json.gz"
    assert wv.build(out, tmp_path / "skipped.json.gz", saved) == 1
    payload = json.loads(gzip.decompress(out.read_bytes()))
    assert payload["state"] == "WV" and payload["programs"][0]["id"] == "wv-72"


def test_a_bare_not_or_no_near_nonprofits_is_not_an_exclusion():
    for text in ("Not-for-profit and nonprofit organizations",
                 "No match is required for non-profit organizations",
                 "Local governments and not-for-profit or non-profit agencies",
                 "For-profit entities are not eligible; non-profits may apply"):
        assert wv.who_can_apply(text)[0] is True, text
    for text in ("Nonprofits are not eligible.", "Non-profit organizations may not apply.",
                 "Open to all entities except nonprofits."):
        assert wv.who_can_apply(text)[0] is False, text


def test_unclear_wording_keeps_the_grant_open_and_only_a_real_exclusion_closes_it():
    still_open = (
        "Nonprofits that cannot provide match may request a waiver",
        "Nonprofits may not receive more than $5,000.",             # a limit, not an exclusion
        "Nonprofits cannot apply directly; they must partner with a county.",
        "Nonprofits are not eligible as the lead applicant.",
        "No nonprofits or businesses may apply",                      # unclear: kept, with the state's words on the card
    )
    for text in still_open:
        yes, said = wv.who_can_apply(text)
        assert yes is True and said == text, text
    for text in ("Nonprofits not eligible", "No nonprofits.", "Nonprofits cannot be applicants.",
                 "Nonprofits may not receive funds.", "Not open to non-profit organizations."):
        assert wv.who_can_apply(text)[0] is False, text


def test_the_snapshot_keeps_no_email_addresses():
    import gzip
    import json
    from pathlib import Path
    payload = json.loads(gzip.decompress((Path(wv.__file__).parent.parent / "data" / "westvirginia.json.gz").read_bytes()))
    assert payload["programs"] and not any("@" in r["contact"] for r in payload["programs"])
