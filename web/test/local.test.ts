// County and city programs (data/local-FL.json): the Florida card shows the county, the window and the due date,
// and the scorer applies the same county and 501(c)(3) rules as grantmatch/rank_more.py.
import { describe, expect, it } from "vitest";
import { floridaEntry, localWindow } from "../src/entries";
import { BETWEEN_ROUNDS, betweenRounds, scoreFlorida, type FloridaRec, type Profile } from "../src/score";

const rec = (extra: Partial<FloridaRec> = {}): FloridaRec => ({
  id: "local-sample-county-kids", csfa: "", title: "Synthetic Children's Fund", agency: "Sample County",
  objectives: "Programs for children and families.", assistance: "Grant", applicant_types: "Nonprofits with 501(c)(3) status.",
  nonprofit_eligible: true, earmark: false, restrictions: "", application: "Apply online.", award: "Not stated.",
  deadlines: "Applications open December 7, 2026 and close January 29, 2027.", contact: "", web: "https://example.org/kids",
  subjects: "Children", url: "https://example.org/kids", level: "County", area: "Manatee County",
  places: ["manatee", "manatee county", "bradenton"], requires_501c3: true, opens: "2026-12-07", closes: "2027-01-29",
  checked: "2026-11-18", ...extra,
});

const profile = (extra: Partial<Profile> = {}): Profile => ({
  mission: "Free literacy tutoring for children.", keywords: ["literacy", "children"], has501c3: "Yes",
  budgetBand: "$50k to $250k", canCostShare: false, categories: [], includeForecasted: true, minDaysLeft: 14,
  today: new Date(2026, 10, 18), fiscalSponsor: false, delivery: "in_person", yearFounded: null, minorKeywords: [], ...extra,
});

describe("county programs", () => {
  it("score by county and 501(c)(3) status, in Python's words", () => {
    const one = (p: Profile, cities: string[]) => scoreFlorida([rec()], p, null, false, cities)[0];
    const there = one(profile(), ["Bradenton"]);
    expect(there.reasons).toContain("Funds work in Manatee County, where you work");
    const elsewhere = one(profile(), ["Clearwater"]);
    expect(elsewhere.cautions).toEqual(["Only for work in Manatee County"]);
    expect(there.score - elsewhere.score).toBe(40);
    expect(one(profile(), []).cautions).toEqual(["Only for work in Manatee County; add your cities to check"]);
    expect(one(profile({ has501c3: "Pending" }), ["Bradenton"]).cautions)
      .toEqual(["Requires 501(c)(3) status; apply once your IRS letter arrives"]);
    expect(one(profile({ has501c3: "No", fiscalSponsor: true }), ["Bradenton"]).cautions)
      .toEqual(["Requires 501(c)(3) status; ask whether you can apply through your fiscal sponsor"]);
  });

  it("show the window before it opens, while it is open, and nothing after it closes", () => {
    expect(localWindow(rec(), new Date(2026, 10, 18))).toEqual({ due: new Date(2027, 0, 29).getTime(), line: "Applications open Dec 07, 2026" });
    expect(localWindow(rec(), new Date(2026, 11, 10)).line).toBe("Taking applications now");
    expect(localWindow(rec(), new Date(2027, 1, 1))).toEqual({ due: null, line: undefined });
    expect(localWindow(rec({ opens: null, closes: null }), new Date(2026, 10, 18))).toEqual({ due: null, line: undefined });
  });

  it("read as a county program on the card, keyed for ETO", () => {
    const e = floridaEntry(scoreFlorida([rec({ closes: "2099-01-29", opens: "2026-01-01" })], profile(), null, false, ["Bradenton"])[0], true);
    expect(e.key).toBe("fl:local-sample-county-kids");
    expect(e.catalog).toBe("County program");
    expect(e.facts).toEqual(["Sample County", "Manatee County"]);
    expect(e.side).toMatch(/^Due /);
    expect(e.sortClose).toBe(new Date(2099, 0, 29).getTime());
    expect(e.rows?.some((r) => r.label === "Source" && r.text?.startsWith("Entered by hand"))).toBe(true);
  });

  it("leave state programs as they were", () => {
    const state = rec({ id: "fl-1", csfa: "48.001", level: undefined, area: undefined, places: undefined, requires_501c3: undefined,
      opens: undefined, closes: undefined, checked: undefined });
    const a = scoreFlorida([state], profile(), null)[0];
    const b = scoreFlorida([state], profile(), null, false, ["Clearwater"])[0];
    expect([b.score, b.reasons, b.cautions]).toEqual([a.score, a.reasons, a.cautions]);
    const e = floridaEntry(a, true);
    expect(e.catalog).toBe("CSFA 48.001");
    expect(e.side).toBe("");
  });
});

describe("hand-kept programs between rounds", () => {
  const day = new Date(2026, 10, 18);
  const state = (extra: Partial<FloridaRec> = {}) =>
    rec({ id: "local-ia-sample", level: "State", area: "all of Iowa", places: [], opens: null, closes: null, ...extra });

  it("are only the ones with no window open, announced or always open", () => {
    expect(betweenRounds(state(), day)).toBe(true);
    expect(betweenRounds(state({ rolling: true }), day)).toBe(false);
    expect(betweenRounds(state({ opens: "2027-01-01", closes: "2027-02-05" }), day)).toBe(false);
    expect(betweenRounds(state({ closes: "2026-11-18" }), day)).toBe(false);
    expect(betweenRounds(state({ opens: "2026-01-01", closes: "2026-02-06" }), day)).toBe(true);
    expect(betweenRounds(state({ _cycle: { s: "open", at: "2026-11-12" } }), day)).toBe(false);
    expect(betweenRounds(state({ _cycle: { s: "closed", at: "2026-11-12" } }), day)).toBe(true);
    expect(betweenRounds(state({ id: "il-4319" }), day)).toBe(false); // a state list's own call
  });

  it("rank below an open program by 15 points, with a caution", () => {
    const [open, closed] = [state({ id: "local-ia-open", rolling: true }), state({ id: "local-ia-closed" })];
    const out = scoreFlorida([closed, open], profile(), null);
    expect(out.map((s) => s.rec.id)).toEqual(["local-ia-open", "local-ia-closed"]);
    expect(out[0].score - out[1].score).toBe(15);
    expect(out[1].cautions).toContain(BETWEEN_ROUNDS);
    expect(out[0].cautions).not.toContain(BETWEEN_ROUNDS);
  });

  it("say a rolling program takes applications any time", () => {
    expect(localWindow(state({ rolling: true }), day).line).toBe("Taking applications with no set deadline");
  });
});

describe("county and city programs outside Florida", () => {
  const houston = rec({ id: "local-tx-x", level: "City", area: "Houston", places: ["houston"], requires_501c3: false });

  it("serve only the places they name, in Python's words", () => {
    const one = (cities: string[]) => scoreFlorida([houston], profile(), null, false, cities)[0];
    expect(one(["Houston"]).reasons).toContain("Funds work in Houston, where you work");
    expect(one(["Pasadena"]).cautions).toContain("Only for work in Houston");
  });

  it("show a note about the program's page in the details, only when there is one", () => {
    const entry = (r: FloridaRec) => floridaEntry(scoreFlorida([r], profile(), null)[0], true);
    expect(entry(houston).rows?.some((x) => x.label === "Note")).toBe(false);
    expect(entry({ ...houston, source_note: "The page gives two dates." }).rows)
      .toContainEqual({ label: "Note", text: "The page gives two dates." });
  });
});

describe("match and tax status on a hand-kept program's card", () => {
  const checks = (r: FloridaRec, extra: Partial<Profile> = {}) =>
    Object.fromEntries((floridaEntry(scoreFlorida([r], profile(extra), null)[0], true, profile(extra)).ready ?? []).map((c) => [c.key, c]));
  const base = rec({ level: "County", requires_501c3: null, applicant_types: "Nonprofits.", award: "Up to $10,000." });

  it("says a required match stops an organization that can't provide one, and takes 20 points", () => {
    const r = { ...base, match: "25%" };
    expect(checks(r).match).toMatchObject({ state: "no", label: "Match required" });
    expect(checks(r).match.note).toContain("(25%)");
    expect(checks(r, { canCostShare: true }).match.state).toBe("ok");
    const [without, withIt] = [scoreFlorida([base], profile(), null)[0], scoreFlorida([r], profile(), null)[0]];
    expect(withIt.cautions).toContain("Requires matching funds (25%)");
    expect(without.score - withIt.score).toBe(20);
  });

  it("says a match isn't stated when the program doesn't mention one", () => {
    expect(checks(base).match).toMatchObject({ state: "check", label: "Match not stated" });
  });

  it("asks an organization without 501(c)(3) to check when the answer isn't a yes or no", () => {
    for (const has501c3 of ["No", "Pending"] as const) {
      expect(checks(base, { has501c3 })["501c3"]).toMatchObject({ state: "check", label: "Check tax status" });
      expect(checks(base, { has501c3, fiscalSponsor: true })["501c3"].label).toBe("Check tax status");
    }
    expect(checks(base, { has501c3: "Yes" })["501c3"]).toBeUndefined();
    expect(checks({ ...base, requires_501c3: false }, { has501c3: "No" })["501c3"].label).toBe("No 501(c)(3) needed");
    expect(checks({ ...base, requires_501c3: true }, { has501c3: "No" })["501c3"].label).toBe("Needs 501(c)(3)");
  });
});
