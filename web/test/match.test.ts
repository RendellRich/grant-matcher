// "No match required" only when the source says none is needed; silence is "Match not stated" (src/ready.ts). The
// first block reads the same cases the Python adapters are checked against (tests/fixtures/match-statements.json).
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { floridaEntry } from "../src/entries";
import { federalReadiness, floridaReadiness, matchWords, readySummary, type ReadyCheck } from "../src/ready";
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
interface Words { name: string; text: string; purpose?: string; says: string; call: string; program: string }
const fixture = JSON.parse(readFileSync(new URL("../../tests/fixtures/match-statements.json", import.meta.url), "utf8")) as { cases: Case[]; words: Words[] };
const { cases, words } = fixture;
const UNKNOWN = "We couldn't tell whether matching funds are required; read the notice.";

describe("the shared word cases", () => {
  it.each(words)("$name", (c) => {
    expect(matchWords(c.text, c.purpose ?? "").says).toBe(c.says);
    const extra = { restrictions: c.text, objectives: c.purpose ?? "Literacy for children." };
    expect(match(program(extra)).label).toBe(c.program);
    expect(match(rec({ ...extra, match: "" })).label).toBe(c.call);
    const { plain, asks } = matchWords(c.text, c.purpose ?? "");
    if (plain || asks) expect(match(rec({ ...extra, match: "", match_none: true })).label).not.toBe("No match required");
    if (c.program === "Match not stated") expect(match(program(extra)).note).toBe(UNKNOWN);
  });
});

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
    expect(call).toMatchObject({ state: "check", label: "Match not stated", note: UNKNOWN });
  });

  it("never claims a program says nothing", () => {
    for (const objectives of ["Provide 70% cost-share funding to nurseries.", "Matching mentors with children.", "Reading."]) {
      expect(match(program({ objectives })).note).toBe(UNKNOWN);
    }
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
      expect(text).toContain(`- Check: ${UNKNOWN}`);
      expect(text).not.toContain("no matching funds");
    }
  });

  it("shows a program open by invitation as something to check", () => {
    const entry = (JSON.parse(readFileSync(new URL("../../data/local-FL.json", import.meta.url), "utf8")).programs as Record<string, unknown>[])
      .filter((e) => e.by_invitation === true);
    expect(entry.map((e) => e.slug)).toEqual(["miami-dade-cultural-advancement"]);
    const r = program({ id: "local-x", level: "County", area: "X County", places: ["x county"], requires_501c3: true,
      match: "100% in cash", by_invitation: true, opens: "2027-02-01", closes: "2027-03-08" });
    for (const today of [new Date(2026, 10, 25), new Date(2027, 1, 15)]) { // between rounds, and while a round is open
      const p = profile({ canCostShare: true, today });
      const { checks } = floridaReadiness(r, p);
      expect(checks.find((c) => c.key === "invite")).toMatchObject({ state: "check", label: "By invitation" });
      expect(readySummary(checks)).not.toBe("Nothing in the way that we can see");
      expect(grantSummary(floridaEntry(scoreFlorida([r], p, null, false, ["x county"])[0], true, p), today))
        .toContain("- Check: Only organizations that were invited, or recommended for funding before, may apply");
    }
    const scored = (x: FloridaRec) => scoreFlorida([x], profile(), null, false, ["x county"])[0];
    expect(scored(r).score).toBe(scored({ ...r, by_invitation: undefined }).score);
    expect(floridaReadiness({ ...r, by_invitation: undefined }, profile()).checks.find((c) => c.key === "invite")).toBeUndefined();
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
