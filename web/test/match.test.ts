// "No match required" only when the source says none is needed; silence is "Match not stated" (src/ready.ts). The
// first block reads the same cases the Python adapters are checked against (tests/fixtures/match-statements.json).
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { floridaEntry } from "../src/entries";
import { federalReadiness, floridaReadiness, readySummary, type ReadyCheck } from "../src/ready";
import { scoreFlorida, type FederalRec, type FloridaRec, type Profile } from "../src/score";
import { grantSummary } from "../src/summary";

const profile = (extra: Partial<Profile> = {}): Profile => ({
  mission: "Free literacy tutoring for children.", keywords: ["literacy", "children"], has501c3: "Yes",
  budgetBand: "$50k to $250k", canCostShare: false, categories: [], includeForecasted: true, minDaysLeft: 0,
  today: new Date(2026, 10, 25), fiscalSponsor: false, delivery: "in_person", yearFounded: null, minorKeywords: [],
  registrations: [], ...extra,
});

const rec = (extra: Partial<FloridaRec> = {}): FloridaRec => ({
  id: "xx-1", csfa: "", title: "Reading Grant", agency: "A", objectives: "Literacy for children.", assistance: "Grant",
  applicant_types: "Nonprofits.", nonprofit_eligible: true, earmark: false, restrictions: "", application: "Apply online.",
  award: "", deadlines: "", contact: "", web: "", subjects: "", url: "https://example.org/a", status: "active", ...extra,
});
const program = (extra: Partial<FloridaRec> = {}) => rec({ status: undefined, ...extra }); // a Florida catalog program
const match = (r: FloridaRec, p = profile()): ReadyCheck => floridaReadiness(r, p).checks.find((c) => c.key === "match")!;

interface Case { adapter: string; raw: unknown; record: { match: string; match_none?: boolean }; label: string }
const cases = JSON.parse(readFileSync(new URL("../../tests/fixtures/match-statements.json", import.meta.url), "utf8")).cases as Case[];

describe("what the list's match field says", () => {
  it.each(cases)("$adapter $raw shows $label", (c) => {
    expect(match(rec(c.record)).label).toBe(c.label);
  });

  it("never changes a score", () => {
    for (const canCostShare of [false, true]) {
      const one = (r: FloridaRec) => scoreFlorida([r], profile({ canCostShare }), null)[0];
      const silent = one(rec({ match: "" })), none = one(rec({ match: "", match_none: true }));
      expect([none.score, none.tier, none.reasons, none.cautions]).toEqual([silent.score, silent.tier, silent.reasons, silent.cautions]);
    }
  });
});

describe("what a program's words say", () => {
  const says = (award: string) => [match(rec({ match: "", award })).label, match(program({ award })).label];

  it("is 'No match required' only for words that say none is needed", () => {
    for (const words of ["No match required.", "NO MATCH REQUIRED", "A local match is not required.", "No matching funds are required.",
      "Matching funds are not required but are encouraged.", "Cost share is not required.", "No minimum match required.",
      "No matching fund requirements.", "While cost sharing is not a requirement, applicants may offer it.",
      "This program does not require matching funds.", "No cost sharing or matching funds required."]) {
      expect(says(words), words).toEqual(["No match required", "No match required"]);
    }
  });

  it("is never 'No match required' for silence, a cash-only line or words that say both", () => {
    for (const words of ["", "Up to $5,000.", "No cash match required.", "No match required for planning; construction requires a 25% match.",
      "No matching funds are required. A match is required for equipment."]) {
      expect(says(words), words).toEqual(["Match not stated", "Match not stated"]);
    }
  });

  it("still asks for a match the words plainly ask for", () => {
    expect(says("Requires a 25% cash match.")).toEqual(["Match required", "Match required"]);
  });

  it("doesn't turn an open call's passing mention into a requirement", () => {
    const call = match(rec({ match: "", award: "Matching funding is strongly encouraged." }));
    expect(call).toMatchObject({ state: "check", label: "Match not stated" });
    expect(call.note).toContain("without saying plainly");
  });

  it("tells a mention in the purpose from silence", () => {
    expect(match(program({ objectives: "Provide 70% cost-share funding to nurseries." })).note).toContain("without saying plainly");
    expect(match(program({ objectives: "Matching mentors with children." })).note).toContain("Nothing read from this program says");
  });

  it("covers a hand-kept program, whose match field still wins", () => {
    const local = program({ id: "local-x", level: "County", area: "X County", places: ["x"], requires_501c3: false });
    expect(match(local).label).toBe("Match not stated");
    expect(match({ ...local, match: "100% cash", award: "No match required." }).label).toBe("Match required");
  });
});

describe("the checklist and the copied summary", () => {
  it("never read silence as nothing in the way", () => {
    const r = program({ id: "local-x", level: "County", area: "X County", places: ["x county"], requires_501c3: false,
      opens: null, closes: "2026-12-30", checked: "2026-11-25" });
    for (const canCostShare of [false, true]) {
      const p = profile({ canCostShare });
      expect(readySummary(floridaReadiness(r, p).checks)).toBe("1 thing to check");
      const text = grantSummary(floridaEntry(scoreFlorida([r], p, null, false, ["x county"])[0], true, p), p.today);
      expect(text).toContain("CAN WE APPLY? 1 THING TO CHECK");
      expect(text).toContain("- Check: Nothing read from this program says whether matching funds are required; ask before you apply.");
      expect(text).not.toContain("no matching funds");
    }
  });

  it("keeps Grants.gov's no as a no, and says so when the record left it out", () => {
    const fed = { id: "1", number: "ED-1", title: "Literacy", agency_code: "ED", agency: "Education", status: "posted",
      close_date: "2027-02-01", award_ceiling: 100000, award_floor: 10000, cost_sharing: false, applicant_types: ["12"],
      categories: ["ED"], category_labels: ["Education"], description: "", eligibility_text: "", url: "https://www.grants.gov/x" } as FederalRec;
    const label = (r: FederalRec) => federalReadiness(r, profile()).checks.find((c) => c.key === "match")!.label;
    expect(label(fed)).toBe("No match required");
    expect(label({ ...fed, cost_sharing_unstated: true })).toBe("Match not stated");
    expect(label({ ...fed, cost_sharing: true })).toBe("Match required");
  });
});
