import { describe, expect, it } from "vitest";
import { narrow, NO_NARROW, type Entry } from "../src/entries";

const base: Entry = {
  key: "x", source: "fed", title: "", url: "", catalog: "", facts: [], side: "", score: 50, tier: "Possible",
  fits: [], cautions: [], also: [], status: [],
};
const fed = (key: string, o: Partial<Entry>): Entry => ({ ...base, key, source: "fed", ...o });
const fdn = (key: string, o: Partial<Entry>): Entry => ({ ...base, key, source: "fdn", ...o });
const keys = (es: Entry[]) => es.map((e) => e.key);

describe("narrow", () => {
  const list = [
    fed("a", { title: "After School Literacy", agency: "Department of Education", amountLow: 10_000, amountHigh: 40_000, sortClose: new Date(2027, 0, 15).getTime() }),
    fed("b", { title: "Rural Health Network", agency: "HRSA", amountLow: 300_000, amountHigh: 900_000, sortClose: new Date(2027, 5, 1).getTime() }),
    fed("c", { title: "Amount unknown", agency: "HRSA", amountLow: null, amountHigh: null, sortClose: null }),
    fdn("d", { title: "Sunshine Fund", sortMedian: 5_000, publishesApply: true, local: true,
      grants: [{ to: "Reading Club", place: "Tampa, FL", amount: "$5,000", purpose: "literacy" }] }),
    fdn("e", { title: "Big Fund", sortMedian: 400_000, closedToUnsolicited: true }),
  ];

  it("returns everything with no filters", () => {
    expect(narrow(list, NO_NARROW)).toBe(list);
  });
  it("needs every search word, anywhere in the entry, details included", () => {
    expect(keys(narrow(list, { ...NO_NARROW, q: "tampa reading" }))).toEqual(["d"]);
    expect(keys(narrow(list, { ...NO_NARROW, q: "after school" }))).toEqual(["a"]);
  });
  it("keeps federal awards whose range overlaps the size band, and drops unknown amounts", () => {
    expect(keys(narrow(list, { ...NO_NARROW, size: "s" }).filter((e) => e.source === "fed"))).toEqual(["a"]);
    expect(keys(narrow(list, { ...NO_NARROW, size: "l" }).filter((e) => e.source === "fed"))).toEqual(["b"]);
  });
  it("uses the typical grant for foundations", () => {
    expect(keys(narrow(list, { ...NO_NARROW, size: "s" }).filter((e) => e.source === "fdn"))).toEqual(["d"]);
  });
  it("keeps federal deadlines on or before the chosen day", () => {
    expect(keys(narrow(list, { ...NO_NARROW, before: "2027-01-15" }).filter((e) => e.source === "fed"))).toEqual(["a"]);
  });
  it("filters by agency", () => {
    expect(keys(narrow(list, { ...NO_NARROW, agency: "HRSA" }))).toEqual(["b", "c"]);
  });
  it("applies the foundation checks only to foundations", () => {
    expect(keys(narrow(list, { ...NO_NARROW, apply: true, local: true }))).toEqual(["a", "b", "c", "d"]);
    expect(keys(narrow(list, { ...NO_NARROW, open: true }))).toEqual(["a", "b", "c", "d"]);
  });
});

describe("eligibility and new filters", () => {
  const list = [
    fdn("a", { asks501c3: true, isNew: true }),
    fdn("b", { asks501c3: false }),
    fed("c", { isNew: true }),
  ];
  it("hides foundations that ask for 501(c)(3) proof, and only foundations", () => {
    expect(keys(narrow(list, { ...NO_NARROW, no501: true }))).toEqual(["b", "c"]);
  });
  it("keeps only entries new since the last visit", () => {
    expect(keys(narrow(list, { ...NO_NARROW, fresh: true }))).toEqual(["a", "c"]);
  });
});
