import pytest

from grantmatch.display import present, tidy_name, tidy_text


@pytest.mark.parametrize("raw, want", [
    ("THE MCWETHY FOUNDATION", "The McWethy Foundation"),
    ("THE MCCADDIN-MCQUIRK FOUNDATION INC", "The McCaddin-McQuirk Foundation Inc"),
    ("THOMAS R O'DONNELL SCHOLARSHIP FUND", "Thomas R O'Donnell Scholarship Fund"),
    ("D'ADDARIO FOUNDATION INC", "D'Addario Foundation Inc"),
    ("JC & JESSIE SEACREST FAMILY FNDTN", "JC & Jessie Seacrest Family Fndtn"),
    ("JOHN A SMITH FOUNDATION", "John A Smith Foundation"),
    ("MADELINE OR ARNOLD SCHUSTER", "Madeline or Arnold Schuster"),
    ("FRIENDS OF THE ARTS IN TAMPA", "Friends of the Arts in Tampa"),
    ("MERCHANTS FOUNDATION CO JULIA KAERC", "Merchants Foundation c/o Julia Kaerc"),
    ("ARPIN CHARITABLE FUND INC (DBA ARPIN STRONG)", "Arpin Charitable Fund Inc (DBA Arpin Strong)"),
    ("NEEDHAM SEPTEMBER 11TH SCHOLARSHIP FUND", "Needham September 11th Scholarship Fund"),
    ("ROBERT & SHERRY ROGERS MD FOUNDATION", "Robert & Sherry Rogers MD Foundation"),
    ("SHARON SHUBIN VICE-PRESIDENT", "Sharon Shubin Vice-President"),
    ("DR JANE DOE", "Dr Jane Doe"),
    ("O'Braitis Family Foundation", "O'Braitis Family Foundation"),  # already mixed case: left alone
])
def test_names(raw, want):
    assert tidy_name(raw) == want


@pytest.mark.parametrize("raw, want", [
    ("MCDONOUGH", "McDonough"),
    ("LA JOLLA", "La Jolla"),
    ("DE LEON SPRINGS", "De Leon Springs"),
    ("ST PETERSBURG", "St Petersburg"),
])
def test_cities(raw, want):
    assert tidy_name(raw, "city") == want


@pytest.mark.parametrize("raw, want", [
    ("C/O SCS FINANCIAL 888 BOYLSTON ST BOSTON MA 02199", "c/o Scs Financial 888 Boylston St Boston MA 02199"),
    ("1173 S 250 W ST GEORGE UT 84770", "1173 S 250 W St George UT 84770"),
    ("309 EAST PACES FERRY RD NE STE 400 ATLANTA GA 30305", "309 East Paces Ferry Rd NE Ste 400 Atlanta GA 30305"),
    ("76 WAREHAM ST UNIT 5C BOSTON MA 02118", "76 Wareham St Unit 5C Boston MA 02118"),
    ("2811 PONCE DE LEON BLVD CORAL GABLES FL 33134", "2811 Ponce de Leon Blvd Coral Gables FL 33134"),
    ("1 MAIN ST PORTLAND OR 97201-1234", "1 Main St Portland OR 97201-1234"),
])
def test_addresses(raw, want):
    assert tidy_name(raw, "address") == want


def test_empty_values_hidden():
    assert present("NONE") == "" and present(" n/a ") == "" and tidy_name(None) == ""


def test_sentence_case():
    assert tidy_text("SUPPORTS YOUTH PROGRAMS") == "Supports youth programs"
    assert tidy_text("Already fine.") == "Already fine."


@pytest.mark.parametrize("raw, want", [
    ("SEATTLE FOUNDATION SEATTLE WA", "Seattle Foundation Seattle WA"),
    ("DISTINGUISHED YOUNG WOMEN OF GRANT CO", "Distinguished Young Women of Grant CO"),
    ("NE FORESTS FOUNDATION", "NE Forests Foundation"),
    ("SOAR365", "Soar365"),
    ("BEAVER DAM YOUTH GIRLS 3PT CLUB", "Beaver Dam Youth Girls 3PT Club"),
    ("EMMA WALKER CO TEXAS A&M UNIVERSITY", "Emma Walker c/o Texas A&M University"),
    ("METROPOLITAN AIDS NEIGHBORHOOD NUTRITION ALLIANCE (MANNA)", "Metropolitan Aids Neighborhood Nutrition Alliance (MANNA)"),
    ("LONNIE BOB HURST SCHOLARSHIP TR", "Lonnie Bob Hurst Scholarship Tr"),
])
def test_names_from_the_data(raw, want):
    assert tidy_name(raw) == want


@pytest.mark.parametrize("raw, kind, want", [
    ("MARLBOROUGH MA", "city", "Marlborough MA"),
    ("GA STATE UNIVERSITY", "name", "GA State University"),
    ("NATIONAL MS SOCIETY", "name", "National MS Society"),
    ("FR ED JALBERT", "name", "Fr Ed Jalbert"),
    ("KOKUA NA LANI", "name", "Kokua Na Lani"),
    ("MAKE A WISH FOUNDATION GEORGIA", "name", "Make a Wish Foundation Georgia"),
    ("LONG ISLAND LENDING A HELPING HAND", "name", "Long Island Lending a Helping Hand"),
    ("GARY D AND RUTH A GILMORE FAMILY", "name", "Gary D and Ruth A Gilmore Family"),
])
def test_more_names_from_the_data(raw, kind, want):
    assert tidy_name(raw, kind) == want


@pytest.mark.parametrize("raw, want", [
    ("THRIVING GRANT CO INC", "Thriving Grant Co Inc"),
    ("THE VA HOME", "The VA Home"),
    ("AMERICAN RED CROSS SW MI CHAPTER", "American Red Cross SW MI Chapter"),
    ("HELP A DIABETIC CHILD", "Help a Diabetic Child"),
])
def test_last_edge_cases(raw, want):
    assert tidy_name(raw) == want


def test_short_caps_cities():
    assert tidy_name("RYE", "city") == "Rye" and tidy_name("Rye", "city") == "Rye"


@pytest.mark.parametrize("raw, want", [
    ("Grants", "Paid as grants"),
    ("Cooperative Agreements Grants", "Paid as cooperative agreements and grants"),
    ("Direct Appropriations Grants Other", "Paid as direct appropriations, grants and other assistance"),
    ("", ""),
])
def test_assistance_label(raw, want):
    from grantmatch.display import assistance_label
    assert assistance_label(raw) == want


@pytest.mark.parametrize("raw, city, want", [
    ("622 EAST TARPON AVENUE TARPON SPRINGS FL 34689", "TARPON SPRINGS", "622 East Tarpon Avenue, Tarpon Springs, FL 34689"),
    ("PO BOX 1272 MCMURRAY PA 15317", "", "PO Box 1272 McMurray, PA 15317"),
    ("SEE ATTACHED", "TAMPA", "See Attached"),
])
def test_format_address(raw, city, want):
    from grantmatch.display import format_address
    assert format_address(raw, city) == want
