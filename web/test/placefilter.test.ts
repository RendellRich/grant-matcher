// The state and county result filters (placefilter.ts).
import { describe, expect, it } from "vitest";
import { isNarrowed, narrow, NO_NARROW, type Entry } from "../src/entries";
import { countyChoices, countyPhrase, countyWord, foundationsByCounty, programsOutside, servesCounty, stateChoices } from "../src/placefilter";
import type { FloridaRec, FoundationRec } from "../src/score";

const towns = ["Bradenton", "Longboat Key", "St. Petersburg"];

describe("what the filters offer", () => {
  it("lists the other states that have foundation or program data, by name", () => {
    const meta = { states: ["FL", "NY", "ZZ"], florida: "2026-27", programs: { CA: { file: "programs-CA", source: "" } } };
    expect(stateChoices(meta, "FL")).toEqual(["CA", "NY"]);
    expect(stateChoices(meta, "AL")).toEqual(["CA", "FL", "NY"]);
    expect(stateChoices(null, "FL")).toEqual([]);
  });
  it("takes counties from the data file, mends its accents, and names them as the state does", () => {
    expect(countyChoices({ Sarasota: [], "DoÃ±a Ana": [] })).toEqual([["DoÃ±a Ana", "Doña Ana"], ["Sarasota", "Sarasota"]]);
    expect(countyChoices(null)).toEqual([]);
    expect(countyPhrase("FL", "Manatee")).toBe("Manatee County");
    expect(countyPhrase("LA", "Acadia")).toBe("Acadia Parish");
    expect(countyPhrase("DC", "District of Columbia")).toBe("District of Columbia");
    expect(countyPhrase("VA", "Alexandria")).toBe("Alexandria"); // an independent city, not "Alexandria County"
    expect(countyPhrase("PR", "Ponce")).toBe("Ponce Municipio");
    expect(["FL", "LA", "PR", "VA"].map(countyWord)).toEqual(["county", "parish", "municipio", "county"]);
  });
});

describe("county filter", () => {
  it("matches a county-wide limit on the county, not on a town it shares with a neighbor", () => {
    const sarasota = ["sarasota county", "sarasota", "longboat key"];
    expect(servesCounty(sarasota, "Sarasota", [])).toBe(true);
    expect(servesCounty(sarasota, "Manatee", towns)).toBe(false);
  });
  it("matches a town-only limit on the county's towns, however the town is written", () => {
    expect(servesCounty(["st petersburg"], "Manatee", towns)).toBe(true);
    expect(servesCounty(["tampa"], "Manatee", towns)).toBe(false);
  });
  it("hides only programs limited elsewhere; ones that name no place stay", () => {
    const prog = (id: string, places?: string[]) => ({ id, places }) as FloridaRec;
    const records = [prog("local-here", ["manatee county"]), prog("local-away", ["lee county"]), prog("local-statewide", []), prog("10.1")];
    expect([...programsOutside(records, "Manatee", towns)]).toEqual(["fl:local-away"]);
  });
  it("tells a foundation with nothing on file from one limited elsewhere", () => {
    const fdn = (ein: string, o: Partial<FoundationRec> = {}) =>
      ({ ein, city: "Miami", state: "FL", sample_grants: [], ...o }) as FoundationRec;
    const grant = (state: string) => [{ city: "Bradenton", state }] as FoundationRec["sample_grants"];
    const r = foundationsByCounty([
      fdn("based", { city: "BRADENTON" }),
      fdn("granted", { sample_grants: grant("FL") }),
      fdn("history", { hist: { y: [2025], n: [1], pl: { "longboat key": 2025 } } }),
      fdn("otherState", { city: "Bradenton", state: "GA", sample_grants: grant("GA") }),
      fdn("nothing"),
      fdn("company", { city: "Bradenton", _corp: { company: "Co", places: ["lee county"] } }),
      fdn("companyHere", { _corp: { company: "Co", places: ["manatee county"] } }),
    ], "FL", "Manatee", towns);
    expect([...r.outside]).toEqual(["fdn:company"]);
    expect([...r.unrecorded]).toEqual(["fdn:otherState", "fdn:nothing"]);
  });
  it("takes the picked keys out of the list and counts as a filter even when it takes none", () => {
    const entry = (key: string) => ({ key, source: "fdn", score: 70, tier: "Strong" }) as Entry;
    const list = [entry("a"), entry("b")];
    const out = narrow(list, { ...NO_NARROW, not: new Set(["b"]) });
    expect(out).toEqual([list[0]]);
    expect(out[0].score).toBe(70);
    expect(isNarrowed({ ...NO_NARROW, not: new Set() })).toBe(true);
    expect(isNarrowed(NO_NARROW)).toBe(false);
  });
});
