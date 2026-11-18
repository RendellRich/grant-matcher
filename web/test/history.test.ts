// A foundation's giving over several years (grantmatch/history.py): labels, a by-year row and three filters.
import { describe, expect, it } from "vitest";
import { historyFacts, narrow, NO_NARROW, type Entry } from "../src/entries";

const h = { y: [2021, 2022, 2023, 2024], n: [12, 15, 14, 18], steady: true, new: 0.39, pl: { bradenton: 2021, palmetto: 2024 } };

describe("giving history", () => {
  it("says it gives every year, funds groups new to it, and lists grants by year", () => {
    const got = historyFacts(h, ["Tampa"]);
    expect(got.lines).toEqual(["Gave every year from 2021 to 2024", "39% of its 2024 grantees were new to it"]);
    expect(got.row).toEqual({ label: "Grants by year", text: "2021: 12 · 2022: 15 · 2023: 14 · 2024: 18" });
    expect([got.steady, got.firstTime, got.newHere]).toEqual([true, true, false]);
  });

  it("notices when its first grants to one of your places came in its latest year", () => {
    expect(historyFacts(h, ["Manatee", "Palmetto"]).lines.at(-1)).toBe("Its first grants to Palmetto came in 2024");
    expect(historyFacts(h, ["Bradenton", "Palmetto"]).newHere).toBe(false); // it funded Bradenton back in 2021
    expect(historyFacts({ ...h, y: [2023, 2024], n: [1, 2] }, ["Palmetto"]).newHere).toBe(false); // too little history
  });

  it("says nothing without history or below the thresholds", () => {
    expect(historyFacts(undefined)).toEqual({ lines: [], steady: false, firstTime: false, newHere: false });
    const quiet = historyFacts({ y: [2024], n: [3], steady: false, new: 0.2 });
    expect([quiet.lines, quiet.row]).toEqual([[], undefined]);
  });

  it("narrows to each label", () => {
    const base: Entry = { key: "", source: "fdn", title: "", url: "", catalog: "", facts: [], side: "", score: 50, tier: "Possible",
      fits: [], cautions: [], also: [], status: [] };
    const list = [{ ...base, key: "a", steady: true }, { ...base, key: "b", firstTime: true }, { ...base, key: "c", newHere: true }];
    expect(narrow(list, { ...NO_NARROW, steady: true }).map((e) => e.key)).toEqual(["a"]);
    expect(narrow(list, { ...NO_NARROW, firstTime: true }).map((e) => e.key)).toEqual(["b"]);
    expect(narrow(list, { ...NO_NARROW, newHere: true }).map((e) => e.key)).toEqual(["c"]);
  });
});
