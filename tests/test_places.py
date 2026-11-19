"""Place names: kept out of the text the meaning model reads, and grants limited to other places marked down."""
from grantmatch.match import other_places, query_text

CASES = [
    ("We rescue dogs in Manatee and Sarasota counties, run a clinic.", "", "", "We rescue dogs in the county, run a clinic. "),
    ("Serving Palm Beach County and Bradenton families.", "kids", "Bradenton", "Serving the county and families. kids"),
    ("In Manatee County we tutor kids.", "", "", "In the county we tutor kids. "),
    ("Across Hillsborough, Pinellas and Pasco counties we feed families.", "", "", "Across the county we feed families. "),
]


def test_county_and_city_names_are_taken_out_of_the_query():
    for mission, keywords, cities, want in CASES:
        assert query_text(mission, keywords, cities) == want


def test_titles_naming_only_other_places():
    assert other_places("Centers for Independent Living Competition - Guam", "FL") == ["Guam"]
    assert other_places("West Virginia Rural Health", "VA") == ["West Virginia"]
    assert other_places("Florida and Georgia coastal resilience", "FL") == []
    assert other_places("Puerto Rico and Virgin Islands recovery", "FL") == ["Puerto Rico", "Virgin Islands"]
    assert other_places("George Washington Carver fellowship", "FL") == []
    assert other_places("Anything in Guam", "") == []
