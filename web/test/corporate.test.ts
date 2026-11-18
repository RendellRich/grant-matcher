// Company foundations (data/corporate.json): the card names the company and its program, and the list can be
// narrowed to them. Nothing here changes a score.
import { describe, expect, it } from "vitest";
import { companyRows, isNarrowed, narrow, NO_NARROW, type Entry } from "../src/entries";

const program = {
  company: "Sample Stores",
  program: { name: "Sample local grants", who: "501(c)(3) public charities near a store.", amount: "$250 to $5,000",
    when: "Three cycles a year.", how: "Apply online.", focus: "Hunger relief", url: "https://example.org/grants", checked: "2026-11-18" },
};

describe("company foundations", () => {
  it("show the program as detail rows, with its amount on the right", () => {
    const got = companyRows(program);
    expect(got.side).toBe("Grants $250 to $5,000");
    expect(got.line).toBe("Runs Sample local grants, $250 to $5,000");
    expect(got.rows.map((r) => r.label)).toEqual(
      ["Company program", "Who can apply", "Amount", "When to apply", "How to apply", "Focus", "Program page", "Source"]);
    expect(got.rows.at(-1)?.text).toBe("Entered by hand from Sample Stores's giving page, checked Nov 18, 2026");
  });

  it("keep the typical grant on the right when the amount isn't a range, and show nothing for a label-only entry", () => {
    expect(companyRows({ ...program, program: { ...program.program, amount: "Not stated" } }).side).toBeUndefined();
    expect(companyRows({ company: "Sample Energy" })).toEqual({ rows: [] });
    expect(companyRows(undefined)).toEqual({ rows: [] });
  });

  it("narrow to company foundations only", () => {
    const base: Entry = { key: "x", source: "fdn", title: "", url: "", catalog: "", facts: [], side: "", score: 50, tier: "Possible",
      fits: [], cautions: [], also: [], status: [] };
    const list = [{ ...base, key: "a", corp: "Sample Stores" }, { ...base, key: "b" }, { ...base, key: "c", source: "fed" as const }];
    const only = { ...NO_NARROW, corp: true };
    expect(narrow(list, only).map((e) => e.key)).toEqual(["a", "c"]);
    expect(isNarrowed(only)).toBe(true);
    expect(isNarrowed(NO_NARROW)).toBe(false);
  });
});
