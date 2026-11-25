// "Last checked" and the dead-link line on cards, from the stamps grantmatch/export_web.py writes. The stamps are
// display only: scores, reasons and cautions are the same with and without them.
import { describe, expect, it } from "vitest";
import { companyRows, DEAD_LINK, floridaEntry, lastChecked } from "../src/entries";
import { scoreFlorida, type FloridaRec, type Profile } from "../src/score";
import { grantSummary } from "../src/summary";
import { EntryView } from "../src/ui";

const rec = (extra: Partial<FloridaRec> = {}): FloridaRec => ({
  id: "fl-1", csfa: "48.001", title: "Synthetic Reading Program", agency: "Sample Department",
  objectives: "Literacy programs for children.", assistance: "Grant", applicant_types: "Nonprofit organizations",
  nonprofit_eligible: true, earmark: false, restrictions: "", application: "Apply online.", award: "Not stated.",
  deadlines: "", contact: "", web: "", subjects: "", url: "https://example.org/a", ...extra,
});

const profile: Profile = {
  mission: "Free literacy tutoring for children.", keywords: ["literacy", "children"], has501c3: "Yes",
  budgetBand: "$50k to $250k", canCostShare: false, categories: [], includeForecasted: true, minDaysLeft: 14,
  today: new Date(2026, 10, 26), fiscalSponsor: false, delivery: "in_person", yearFounded: null, minorKeywords: [],
};

const entry = (extra: Partial<FloridaRec> = {}) => floridaEntry(scoreFlorida([rec(extra)], profile, null)[0], true);

/** Every piece of text in a component's tree, in reading order, without a DOM. */
function words(node: unknown): string {
  if (node === null || node === undefined || typeof node === "boolean") return "";
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(words).join("");
  const v = node as { type?: unknown; props?: Record<string, unknown> };
  // plain elements only: child components (icons, details) keep their own state and have their own tests
  return typeof v.type === "string" ? words(v.props?.children) : "";
}

describe("last checked", () => {
  it("reads a day or a full timestamp, and says nothing without one", () => {
    expect(lastChecked({ _checked: "2026-11-25" })).toEqual({ checked: "Nov 25, 2026" });
    expect(lastChecked({ _checked: "2026-11-25T12:15+00:00" }).checked).toMatch(/^Nov 2[456], 2026$/);
    expect(lastChecked({})).toEqual({});
    expect(lastChecked({ _checked: "soon" })).toEqual({});
  });

  it("flags only a dead link", () => {
    expect(lastChecked({ _link: "dead", _link_at: "2026-11-26" })).toEqual({ dead: true });
    expect(lastChecked({ _link: "ok", _link_at: "2026-11-26" })).toEqual({});
  });

  it("never changes a score, reason or caution", () => {
    const plain = scoreFlorida([rec()], profile, null)[0];
    const stamped = scoreFlorida([rec({ _checked: "2026-11-25", _link: "dead" })], profile, null)[0];
    expect([stamped.score, stamped.tier, stamped.reasons, stamped.cautions])
      .toEqual([plain.score, plain.tier, plain.reasons, plain.cautions]);
    expect(entry({ _checked: "2026-11-25", _link: "dead" }).cautions).toEqual(entry().cautions);
  });

  it("is on the card as text a screen reader reads, with the dead link marked as a caution", () => {
    const card = (e: ReturnType<typeof entry>) => words(EntryView({ e, marked: false, onMark: () => {} }));
    const dead = card(entry({ _checked: "2026-11-25", _link: "dead" }));
    expect(dead).toContain(", Last checked Nov 25, 2026");
    expect(dead).toContain(`Caution: ${DEAD_LINK}`);
    expect(DEAD_LINK).toBe("Link didn't open when last checked");
    const fine = card(entry({ _checked: "2026-11-25" }));
    expect(fine).not.toContain(DEAD_LINK);
    expect(card(entry())).not.toContain("Last checked");
  });

  it("is in the one-page summary", () => {
    const text = grantSummary(entry({ _checked: "2026-11-25", _link: "dead" }), new Date(2026, 10, 26));
    expect(text).toContain("Last checked: Nov 25, 2026");
    expect(text).toContain("Link didn't open when last checked.");
    expect(grantSummary(entry())).not.toContain("Last checked");
  });

  it("marks a company program page that didn't open", () => {
    const c = { company: "Sample Co", program: { name: "Local Grants", who: "", amount: "", when: "", how: "", url: "https://example.org/g", checked: "2026-11-20" } };
    expect(companyRows(c).rows.some((r) => r.text === DEAD_LINK)).toBe(false);
    expect(companyRows({ ...c, program: { ...c.program, link: "dead" } }).rows.some((r) => r.text === DEAD_LINK)).toBe(true);
  });
});
