// "Can we apply?" (src/ready.ts): each source's facts against the profile, and the card lines they replace.
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { federalEntry, floridaEntry, foundationEntry } from "../src/entries";
import { federalReadiness, floridaReadiness, foundationReadiness, readySummary, type ReadyCheck } from "../src/ready";
import { scoreFederal, scoreFlorida, scoreFoundations, type FederalRec, type FloridaRec, type FoundationRec, type Profile } from "../src/score";
import { grantSummary } from "../src/summary";

const profile = (extra: Partial<Profile> = {}): Profile => ({
  mission: "Free literacy tutoring for children.", keywords: ["literacy", "children"], has501c3: "Yes",
  budgetBand: "$50k to $250k", canCostShare: false, categories: [], includeForecasted: true, minDaysLeft: 0,
  today: new Date(2026, 10, 20), fiscalSponsor: false, delivery: "in_person", yearFounded: null, minorKeywords: [],
  registrations: [], ...extra,
});

const by = (checks: ReadyCheck[]) => Object.fromEntries(checks.map((c) => [c.key, c]));

const fed = (extra: Partial<FederalRec> = {}): FederalRec => ({
  id: "1", number: "ED-1", title: "Literacy for children", agency_code: "ED", agency: "Department of Education", status: "posted",
  close_date: "2027-02-01", award_ceiling: 100000, award_floor: 10000, cost_sharing: false, applicant_types: ["12"],
  categories: ["ED"], category_labels: ["Education"], description: "Literacy tutoring for children.", eligibility_text: "",
  url: "https://www.grants.gov/x", ...extra,
});

describe("federal", () => {
  it("always needs SAM.gov, and reads the 501(c)(3) and cost sharing codes", () => {
    const c = by(federalReadiness({ ...fed(), close: new Date(2027, 1, 1) }, profile()).checks);
    expect(c.sam).toMatchObject({ state: "check", label: "Needs SAM.gov" });
    expect(c["501c3"]).toMatchObject({ state: "ok", label: "501(c)(3): you have it" });
    expect(c.match).toMatchObject({ state: "ok", label: "No match required" });
    expect(c.open).toMatchObject({ state: "ok", label: "Open now" });
    expect(c.open.note).toContain("Feb 1, 2027");
    const ready = by(federalReadiness(fed({ cost_sharing: true }), profile({ registrations: ["sam"], canCostShare: true })).checks);
    expect(ready.sam.state).toBe("ok");
    expect(ready.match).toMatchObject({ state: "ok", label: "Match: you can" });
    const stuck = by(federalReadiness(fed({ cost_sharing: true }), profile({ has501c3: "No" })).checks);
    expect(stuck["501c3"]).toMatchObject({ state: "no", label: "Needs 501(c)(3)" });
    expect(stuck.match).toMatchObject({ state: "no", label: "Match required" });
    expect(by(federalReadiness(fed({ applicant_types: ["13"] }), profile({ has501c3: "No" })).checks)["501c3"].label).toBe("No 501(c)(3) needed");
    expect(by(federalReadiness(fed({ applicant_types: ["25"] }), profile()).checks)["501c3"]).toBeUndefined();
    expect(by(federalReadiness(fed({ status: "forecasted" }), profile()).checks).open).toMatchObject({ state: "check", label: "Not open yet" });
  });

  it("take the cautions they repeat off the card, and leave the rest", () => {
    const p = profile({ has501c3: "No" });
    const s = scoreFederal([fed({ cost_sharing: true })], p, null, new Date(2026, 10, 20))[0];
    const e = federalEntry(s, true, p);
    expect(e.cautions).toEqual(expect.arrayContaining(["Requires cost sharing or matching funds"]));
    expect(e.covered).toEqual(expect.arrayContaining(["Requires cost sharing or matching funds", "Requires 501(c)(3) status; you would need a fiscal sponsor"]));
    expect(federalEntry(s, true).ready).toBeUndefined(); // no profile, no checks
  });
});

const local = (extra: Partial<FloridaRec> = {}): FloridaRec => ({
  id: "local-sample-arts", csfa: "", title: "Community Arts Grants", agency: "Sample County", objectives: "Arts programs.",
  assistance: "Grant", applicant_types: "Nonprofits.", nonprofit_eligible: true, earmark: false, restrictions: "",
  application: "Apply online. Grants are reimbursements: pay the costs first.", award: "Up to $1,000; no match required.",
  deadlines: "Due December 6, 2026.", contact: "", web: "", subjects: "Arts", url: "https://example.org/arts", level: "County",
  area: "Sample County", places: ["sample county"], requires_501c3: false, opens: null, closes: "2026-12-06", checked: "2026-11-20", ...extra,
});

describe("county, city and state programs", () => {
  it("read the program's own words for a match and reimbursement", () => {
    const c = by(floridaReadiness(local(), profile()).checks);
    expect(c["501c3"]).toMatchObject({ state: "ok", label: "No 501(c)(3) needed" });
    expect(c.match).toMatchObject({ state: "ok", label: "No match required" });
    expect(c.pay).toMatchObject({ state: "check", label: "Paid by reimbursement" });
    expect(c.open).toMatchObject({ state: "ok", label: "Open now" });
    expect(c.sam).toBeUndefined();
    const cash = by(floridaReadiness(local({ award: "Requires a 25% cash match.", application: "Apply online." }), profile()).checks);
    expect(cash.match).toMatchObject({ state: "no", label: "Match required" });
    expect(cash.pay).toBeUndefined();
  });

  it("say when a round is closed or not open yet", () => {
    expect(by(floridaReadiness(local({ closes: "2026-05-01" }), profile()).checks).open).toMatchObject({ state: "check", label: "Between rounds" });
    expect(by(floridaReadiness(local({ opens: "2027-01-11", closes: "2027-01-29" }), profile()).checks).open)
      .toMatchObject({ state: "check", label: "Opens Jan 11, 2027" });
  });

  it("check 501(c)(3) against the profile, with the fiscal sponsor way round", () => {
    const need = local({ requires_501c3: true });
    expect(by(floridaReadiness(need, profile({ has501c3: "Pending" })).checks)["501c3"].label).toBe("501(c)(3) pending");
    expect(by(floridaReadiness(need, profile({ has501c3: "No", fiscalSponsor: true })).checks)["501c3"].label).toBe("501(c)(3) via sponsor");
  });

  it("use an open call's own fields: match, loan and payment", () => {
    const call = local({ level: undefined, status: "active", match: "25%", loan: true, funding_method: "Reimbursement(s)", application: "", award: "" });
    const c = by(floridaReadiness(call, profile()).checks);
    expect(c.match.note).toContain("25%");
    expect(c.loan).toMatchObject({ state: "no" });
    expect(c.pay.label).toBe("Paid by reimbursement");
    expect(by(floridaReadiness({ ...call, funding_method: "Advances & Reimbursement(s)" }, profile()).checks).pay.label).toBe("Advance or reimbursement");
  });

  it("call a catalog program a program, not an open call", () => {
    const program = local({ level: undefined, closes: null, application: "", award: "" });
    expect(by(floridaReadiness(program, profile()).checks).open.label).toBe("Ask when it funds");
  });

  it("hide the window line the check repeats", () => {
    const p = profile();
    const e = floridaEntry(scoreFlorida([local()], p, null, false, ["sample county"])[0], true, p);
    expect(e.status).toContain("Taking applications now");
    expect(e.covered).toContain("Taking applications now");
  });
});

const fdn = (extra: Partial<FoundationRec> = {}): FoundationRec => ({
  ein: "123456789", name: "SAMPLE FAMILY FOUNDATION", city: "TAMPA", state: "FL", tax_year: "2024", website: null, preselected_only: false,
  apply: null, grant_count: 10, grant_median: 5000, grants_total: 60000, recipient_states: { FL: 10 }, top_purposes: ["literacy"],
  sample_grants: [], url: "https://projects.propublica.org/x", ...extra,
});

describe("foundations", () => {
  it("say whether it takes requests", () => {
    const out = (r: FoundationRec, lines: string[] = [], publishes = false, p = profile()) =>
      by(foundationReadiness({ ...r, in_state: 10 } as never, p, false, publishes, lines).checks);
    expect(out(fdn(), ["Says it only funds preselected organizations; an introduction letter may still be read"]).open.label).toBe("Invitation only");
    expect(out(fdn(), ["Says it does not accept unsolicited requests"]).open.label).toBe("No unsolicited requests");
    expect(out(fdn({ _cycle: { s: "closed", at: "2026-11-18" } as never })).open.label).toBe("Not taking requests");
    expect(out(fdn({ _cycle: { s: "open", at: "2026-11-18" } as never })).open.state).toBe("ok");
    expect(out(fdn(), [], true).open.label).toBe("Says how to apply");
    expect(out(fdn()).open).toMatchObject({ state: "check", label: "No process listed" });
    expect(out(fdn())["501c3"]).toBeUndefined(); // the profile has 501(c)(3) status and the return doesn't ask
    expect(out(fdn(), [], false, profile({ has501c3: "No" }))["501c3"].label).toBe("501(c)(3) usually expected");
  });

  it("come through the entry with the scorer's lines", () => {
    const p = profile();
    const scored = scoreFoundations([fdn({ preselected_only: true })], p, "FL", ["tampa"], null, true);
    const e = foundationEntry(scored[0], "FL", true, ["tampa"], p);
    expect(by(e.ready!).open.label).toBe("Invitation only");
    expect(e.covered).toEqual(expect.arrayContaining([expect.stringMatching(/^Says it only funds preselected/)]));
  });
});

describe("summary", () => {
  it("counts what stops you and what to check", () => {
    const c = (state: ReadyCheck["state"]): ReadyCheck => ({ key: "open", state, label: "", note: "" });
    expect(readySummary([c("ok")])).toBe("Nothing in the way that we can see");
    expect(readySummary([c("check"), c("ok")])).toBe("1 thing to check");
    expect(readySummary([c("no"), c("check"), c("check")])).toBe("1 thing stops you, 2 to check");
  });
});

describe("company foundations limited to named counties", () => {
  it("rank like a county program", () => {
    const corp = { company: "Sample Power", places: ["pinellas", "pinellas county", "st. petersburg"], area: "the 1 counties Sample Power serves in Florida" };
    const p = profile();
    const plain = scoreFoundations([fdn()], p, "FL", ["st. petersburg"], null)[0].score;
    const inside = scoreFoundations([fdn({ _corp: corp })], p, "FL", ["st. petersburg"], null)[0];
    const outside = scoreFoundations([fdn({ _corp: corp })], p, "FL", ["bradenton"], null)[0];
    const noCities = scoreFoundations([fdn({ _corp: corp })], p, "FL", [], null)[0];
    expect(inside.score).toBe(plain);
    expect(inside.reasons).toContain("Funds work in the 1 counties Sample Power serves in Florida, where you work");
    expect(outside.score).toBe(Math.max(0, plain - 40));
    expect(outside.cautions).toContain("Only for work in the 1 counties Sample Power serves in Florida");
    expect(noCities.cautions.at(-1)).toMatch(/add your cities to check$/);
  });
});

describe("a hand-kept program whose tax status rule isn't a yes or no", () => {
  const clean = "Nothing in the way that we can see";
  const question = "This program's tax status rule isn't a simple yes or no; read Who can apply before you start.";
  // Every such entry in the county and city files, as the card sees it, checked on a day when it is open.
  const entries = ["AZ", "CA", "IL", "NV", "NY", "PA", "TX", "WA"].flatMap((st) =>
    (JSON.parse(readFileSync(new URL(`../../data/local-${st}.json`, import.meta.url), "utf8")).programs as Record<string, unknown>[])
      .filter((e) => e.level !== "State" && e.requires_501c3 === null)
      .map((e) => ({ ...e, id: `local-${st.toLowerCase()}-${e.slug}`, applicant_types: e.who, restrictions: "",
        nonprofit_eligible: true, earmark: false, csfa: "", assistance: "Grant", contact: "" }) as unknown as FloridaRec));
  const openDay = (r: FloridaRec) => (r.closes ? new Date(`${r.closes}T12:00:00`) : new Date(2026, 10, 25));

  it("never reads as a clean yes to an organization without 501(c)(3)", () => {
    expect(entries.map((e) => e.id)).toEqual(expect.arrayContaining([
      "local-pa-phila-cultural-fund-art-culture", "local-pa-phila-cultural-fund-community-impact",
      "local-wa-king-4culture-facility-development", "local-ca-alameda-artsfund-2027"]));
    const open = { ...entries[0], id: "local-tx-open", rolling: true, closes: null, opens: null, match: undefined,
      applicant_types: "Nonprofits.", application: "Apply online.", award: "Not stated.", deadlines: "Any time." } as FloridaRec;
    for (const r of [open, ...entries]) {
      for (const has501c3 of ["No", "Pending"] as const) {
        for (const fiscalSponsor of [false, true]) {
          for (const canCostShare of [false, true]) {
            const p = profile({ has501c3, fiscalSponsor, canCostShare, today: openDay(r) });
            const { checks } = floridaReadiness(r, p);
            expect(readySummary(checks), r.id).not.toBe(clean);
            expect(checks.filter((c) => c.key === "501c3"), r.id).toEqual([{ key: "501c3", state: "check", label: "Check tax status", note: question }]);
          }
        }
      }
    }
  });

  it("says the same in the copied summary", () => {
    const r = entries.find((e) => e.id === "local-pa-phila-cultural-fund-art-culture")!;
    const p = profile({ has501c3: "No", fiscalSponsor: false, canCostShare: false, today: openDay(r) });
    const text = grantSummary(floridaEntry(scoreFlorida([r], p, null)[0], true, p), p.today);
    expect(text).toContain("CAN WE APPLY? 2 THINGS TO CHECK"); // tax status, and its pages don't state a match
    expect(text).toContain(`- Check: ${question}`);
    expect(text).not.toContain(clean);
  });

  it("adds nothing once the organization has the status, or for a state program", () => {
    const keys = (r: FloridaRec, has501c3: "Yes" | "No") => floridaReadiness(r, profile({ has501c3 })).checks.map((c) => c.key);
    expect(keys(entries[0], "Yes")).not.toContain("501c3");
    expect(keys({ ...entries[0], level: undefined } as FloridaRec, "No")).not.toContain("501c3");
  });
});
