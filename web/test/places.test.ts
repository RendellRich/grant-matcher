// Must agree with tests/test_places.py: the same inputs give the same text and the same places.
import { describe, expect, it } from "vitest";
import { otherPlaces, queryText } from "../src/score";

const CASES: [string, string, string, string][] = [
  ["We rescue dogs in Manatee and Sarasota counties, run a clinic.", "", "", "We rescue dogs in the county, run a clinic. "],
  ["Serving Palm Beach County and Bradenton families.", "kids", "Bradenton", "Serving the county and families. kids"],
  ["In Manatee County we tutor kids.", "", "", "In the county we tutor kids. "],
  ["Across Hillsborough, Pinellas and Pasco counties we feed families.", "", "", "Across the county we feed families. "],
];

describe("place names", () => {
  it("takes county and city names out of the query", () => {
    for (const [m, k, c, want] of CASES) expect(queryText(m, k, c)).toBe(want);
  });
  it("finds titles that name only other places", () => {
    expect(otherPlaces("Centers for Independent Living Competition - Guam", "FL")).toEqual(["Guam"]);
    expect(otherPlaces("West Virginia Rural Health", "VA")).toEqual(["West Virginia"]);
    expect(otherPlaces("Florida and Georgia coastal resilience", "FL")).toEqual([]);
    expect(otherPlaces("Puerto Rico and Virgin Islands recovery", "FL")).toEqual(["Puerto Rico", "Virgin Islands"]);
    expect(otherPlaces("George Washington Carver fellowship", "FL")).toEqual([]);
    expect(otherPlaces("Anything in Guam", "")).toEqual([]);
  });
});
