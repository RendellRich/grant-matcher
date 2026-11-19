// Another state's open calls (grantmatch/california.py) on the state tab: the scorer's cautions in Python's
// words, the card's dates, and which programs file a profile's state reads.
import { describe, expect, it } from "vitest";
import { programsFile } from "../src/data";
import { floridaEntry } from "../src/entries";
import { rankAll } from "../src/rank";
import { BLANK } from "../src/profile";
import { scoreFlorida, type FloridaRec, type Profile } from "../src/score";

const rec = (extra: Partial<FloridaRec> = {}): FloridaRec => ({
  id: "ca-101", csfa: "", number: "101", state: "CA", title: "Reading and Literacy Grants", agency: "State Library",
  objectives: "Help children read. Funds literacy tutoring programs.", assistance: "Grant",
  applicant_types: "Nonprofit; Public Agency", nonprofit_eligible: true, earmark: false, restrictions: "Statewide",
  application: "Apply online at https://apply.example.ca.gov/", award: "Total available: $1,000,000.00.",
  deadlines: "2027-01-15", contact: "", web: "https://example.ca.gov/", subjects: "Education", url: "https://example.ca.gov/grant",
  status: "active", opens: "2026-10-01", closes: "2027-01-15", match: "", loan: false, funding_method: "Advance(s)",
  loi: false, _catalog: "Grants Portal 101", _assist: "Grant", ...extra,
});

const profile = (extra: Partial<Profile> = {}): Profile => ({
  mission: "Free literacy tutoring for children.", keywords: ["literacy", "children"], has501c3: "Yes",
  budgetBand: "$50k to $250k", canCostShare: false, categories: [], includeForecasted: true, minDaysLeft: 14,
  today: new Date(2026, 10, 19), fiscalSponsor: false, delivery: "in_person", yearFounded: null, minorKeywords: [], ...extra,
});

describe("open calls", () => {
  const one = (r: FloridaRec, p = profile()) => scoreFlorida([r], p, null)[0];

  it("lose points for a match you can't provide and for loans, and flag reimbursement", () => {
    const plain = one(rec());
    expect(plain.cautions).toEqual([]);
    const matched = one(rec({ match: "25%" }));
    expect(matched.cautions).toEqual(["Requires matching funds (25%)"]);
    expect(plain.score).toBeGreaterThan(30); // room to lose points before the floor at zero
    expect(Math.abs(plain.score - matched.score - 20)).toBeLessThanOrEqual(1); // each score is rounded on its own
    expect(one(rec({ match: "25%" }), profile({ canCostShare: true })).cautions).toEqual([]);
    const loan = one(rec({ loan: true }));
    expect(loan.cautions).toEqual(["A loan, not a grant"]);
    expect(Math.abs(plain.score - loan.score - 25)).toBeLessThanOrEqual(1);
    const paidBack = one(rec({ funding_method: "Reimbursement(s)" }));
    expect(paidBack.cautions).toEqual(["Pays by reimbursement: you spend first and are paid back"]);
    expect(paidBack.score).toBe(plain.score);
    expect(one(rec({ funding_method: "Advances & Reimbursement(s)" })).cautions).toEqual([]);
  });

  it("show their portal number, due date and funding on the card", () => {
    const e = floridaEntry(one(rec()), true);
    expect(e.key).toBe("fl:ca-101");
    expect(e.catalog).toBe("Grants Portal 101");
    expect(e.facts).toEqual(["State Library", "Grant"]);
    expect(e.side).toBe("Due Jan 15, 2027");
    const rows = e.rows ?? [];
    expect(rows.map((r) => r.label)).toEqual(["Purpose", "Who can apply", "How to apply", "Funding", "Deadlines", "Where and conditions", "Agency site"]);
    expect(rows.find((r) => r.label === "Deadlines")?.text).toBe("Jan 15, 2027");
  });

  it("say so when there is no set deadline or the call isn't open yet", () => {
    const ongoing = floridaEntry(one(rec({ closes: null, deadlines: "Ongoing" })), true);
    expect(ongoing.side).toBe("Ongoing");
    expect(ongoing.sortClose).toBeNull();
    expect(ongoing.status).toContain("Taking applications with no set deadline");
    const later = floridaEntry(one(rec({ status: "forecasted", opens: "2099-01-01", closes: null, deadlines: "" })), true);
    expect(later.status[0]).toMatch(/^Applications open /);
  });
});

describe("the state tab's data", () => {
  const meta = { states: [], programs: { CA: { file: "programs-CA", source: "California Grants Portal" } } };

  it("reads Florida's own file, another state's listed file, and nothing elsewhere", () => {
    expect(programsFile(meta, "FL")).toBe("florida");
    expect(programsFile(meta, "CA")).toBe("programs-CA");
    expect(programsFile(meta, "NY")).toBeNull();
    expect(programsFile({ states: [] }, "CA")).toBeNull();
    expect(programsFile(null, "FL")).toBe("florida");
  });

  it("ranks a state's programs only for a profile in that state", () => {
    const form = { ...BLANK, mission: "Free literacy tutoring for children.", keywords: "literacy", state: "CA" };
    const src = { fed: null, fdn: null, fl: { records: [rec()], vecs: { ids: [], dim: 0, data: new Float32Array(0) } as never }, flState: "CA", counties: null };
    expect(rankAll(form, src, null)?.fl?.map((e) => e.key)).toEqual(["fl:ca-101"]);
    expect(rankAll({ ...form, state: "FL" }, src, null).fl).toBeNull();
    expect(rankAll(form, { ...src, flState: undefined }, null).fl).toBeNull();
  });
});
