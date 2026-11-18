"""A foundation's giving over several years (grantmatch/history.py)."""
from grantmatch.history import History, default_years


def g(to, city="Bradenton", state="FL"):
    return {"to": to, "city": city, "state": state, "amount": 1000.0}


def sample():
    h = History()
    h.add("123456789", "2021", [g("Reading Club"), g("Food Bank", "Tampa")])
    h.add("123456789", "2022", [g("Reading Club"), g("Arts Center", "Tampa")])
    h.add("123456789", "2023", [g("Reading Club")])
    h.add("123456789", "2024", [g("READING CLUB, INC"), g("New Literacy Group", "Palmetto"), g("Youth Choir", "Sarasota"),
                                g("Garden Project", "Atlanta", "GA")])
    return h


def test_summary_counts_years_steadiness_and_new_grantees():
    s = sample().summary("123456789", "2024")
    assert s["y"] == [2021, 2022, 2023, 2024] and s["n"] == [2, 2, 1, 4]
    assert s["steady"] is True
    # "READING CLUB, INC" is the same grantee as "Reading Club", so 3 of its 4 grantees are new
    assert s["new"] == 0.75


def test_same_grantee_with_the_same_name_is_not_new():
    h = History()
    for y in ("2021", "2022"):
        h.add("1", y, [g("Reading Club"), g("Food Bank")])
    h.add("1", "2023", [g("reading club"), g("Food Bank"), g("Choir"), g("Garden")])
    assert h.summary("1", "2023")["new"] == 0.5


def test_too_little_history_gives_no_new_share_and_a_gap_breaks_steady():
    h = History()
    h.add("1", "2023", [g("A"), g("B"), g("C")])
    h.add("1", "2024", [g("A"), g("B"), g("D")])
    s = h.summary("1", "2024")
    assert s["new"] is None and s["steady"] is False
    h.add("2", "2020", [g("A")])
    h.add("2", "2022", [g("A")])
    h.add("2", "2023", [g("A")])
    h.add("2", "2024", [g("A")])
    assert h.summary("2", "2024")["steady"] is False


def test_years_after_the_latest_return_and_amendments():
    h = sample()
    h.add("123456789", "2025", [g("Later")])
    assert h.summary("123456789", "2024")["y"][-1] == 2024
    h.add("123456789", "2024", [g("Only one")])  # an amended 2024 return replaces the first
    assert h.summary("123456789", "2024")["n"][-1] == 1


def test_places_per_state_with_first_year_and_the_copy_for_a_state_file():
    h = sample()
    assert h.places("123456789", "FL", "2024") == {"bradenton": 2021, "palmetto": 2024, "sarasota": 2024, "tampa": 2021}
    assert h.places("123456789", "GA", "2024") == {"atlanta": 2024}
    rec = {"ein": "123456789", "tax_year": "2024", "name": "Sample Fund"}
    fl = h.for_state(rec, "FL")
    assert fl["hist"]["pl"]["palmetto"] == 2024 and "hist" not in rec  # the shared record is left alone
    assert h.for_state({"ein": "999", "tax_year": "2024"}, "FL") == {"ein": "999", "tax_year": "2024"}


def test_default_years_cover_five_tax_years():
    assert default_years(2026) == [2021, 2022, 2023, 2024, 2025, 2026]


def test_grantee_names_match_across_small_differences():
    from grantmatch.history import recipient_key as k
    assert k("Reading Club, Inc.", "FL") == k("The Reading Club", "fl") == k("READING CLUB INCORPORATED", "FL")
    assert k("Boys & Girls Club of Manatee", "FL") == k("Boys and Girls Club Manatee", "FL")
    assert k("Reading Club", "FL") != k("Reading Club", "GA")
