// A call that doesn't say who may apply never claims to be open to nonprofits (src/score.ts). The same cases run
// through the Python scorer in tests/test_eligibility_reasons.py, so the two stay in step.
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { floridaEntry } from "../src/entries";
import { scoreFlorida, type Profile } from "../src/score";

const CASES = JSON.parse(readFileSync(new URL("../../tests/fixtures/eligibility-reasons.json", import.meta.url), "utf8")) as {
  unstated: string; stated: string; cases: { id: string; applicant_types: string; reason: "stated" | "unstated" }[];
};

const p: Profile = {
  mission: "Arts for children.", keywords: ["arts"], has501c3: "Yes", budgetBand: "$50k to $250k", canCostShare: false,
  categories: [], includeForecasted: true, minDaysLeft: 0, today: new Date(2026, 10, 25), fiscalSponsor: false,
  delivery: "in_person", yearFounded: null, minorKeywords: [], registrations: [],
};

const records = CASES.cases.map((c) => ({
  id: c.id, csfa: "", title: "Arts grants", agency: "Sample", objectives: "", assistance: "Grant",
  applicant_types: c.applicant_types, nonprofit_eligible: true, earmark: false, restrictions: "", application: "",
  award: "", deadlines: "", contact: "", web: "", subjects: "", url: "", status: "active", closes: null,
}));

describe("the eligibility reason on a state call", () => {
  const scored = new Map(scoreFlorida(records, p, null).map((s) => [s.rec.id, s]));

  it("matches Python's for every case", () => {
    for (const c of CASES.cases) {
      const other = c.reason === "unstated" ? CASES.stated : CASES.unstated;
      expect(scored.get(c.id)!.reasons, c.id).toContain(CASES[c.reason]);
      expect(scored.get(c.id)!.reasons, c.id).not.toContain(other);
    }
  });

  it("is shown as a plain note, not as something that fits", () => {
    const e = floridaEntry(scored.get("dc-table")!, true, p);
    expect(e.also).toContain(CASES.unstated);
    expect(e.fits).not.toContain(CASES.unstated);
  });
});
