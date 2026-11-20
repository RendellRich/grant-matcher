// One-page grant summaries (src/summary.ts): built from the card, plain text, no line the checklist repeats.
import { describe, expect, it } from "vitest";
import { federalEntry, floridaEntry, foundationEntry } from "../src/entries";
import { grantSummary, summariesFile, summaryFileName } from "../src/summary";
import { scoreFederal, scoreFlorida, scoreFoundations, type Profile } from "../src/score";

const p: Profile = {
  mission: "Free literacy tutoring for children.", keywords: ["literacy", "children", "arts"], has501c3: "Yes",
  budgetBand: "$50k to $250k", canCostShare: false, categories: [], includeForecasted: true, minDaysLeft: 0,
  today: new Date(2026, 10, 20), fiscalSponsor: false, delivery: "in_person", yearFounded: null, minorKeywords: [], registrations: [],
};
const today = new Date(2026, 10, 20);

const fed = federalEntry(scoreFederal([{ id: "1", number: "ED-1", title: "Literacy for children", agency_code: "ED",
  agency: "Department of Education", status: "posted", close_date: "2027-02-01", award_ceiling: 750000, award_floor: 150000,
  cost_sharing: true, applicant_types: ["12"], categories: ["ED"], category_labels: ["Education"],
  description: "Literacy tutoring for children in high-need schools. ".repeat(40), eligibility_text: "Nonprofits with 501(c)(3) status.",
  url: "https://www.grants.gov/x" }], p, null, today)[0], true, p);

const local = floridaEntry(scoreFlorida([{ id: "local-arts", csfa: "", title: "Community Arts Grants", agency: "Sample Arts Council",
  objectives: "Arts programs for children and literacy through the arts.", assistance: "Grant", applicant_types: "Nonprofits.",
  nonprofit_eligible: true, earmark: false, restrictions: "", application: "Apply online. Grants are reimbursements.",
  award: "Up to $1,000; no match required.", deadlines: "Due December 6, 2026.", contact: "grants@example.org", web: "",
  subjects: "Arts", url: "https://example.org/cag", level: "County", area: "Sample County", places: ["sample county"],
  requires_501c3: false, opens: null, closes: "2026-12-06", checked: "2026-11-20" }], p, null, false, ["sample county"])[0], true, p);

const fdn = foundationEntry(scoreFoundations([{ ein: "591234567", name: "SAMPLE FAMILY FOUNDATION", _name: "Sample Family Foundation",
  city: "TAMPA", state: "FL", tax_year: "2024", website: null, preselected_only: false,
  apply: { contact: "Jane Doe", materials: "A two-page letter", deadlines: "March 1" }, _apply: { contact: "Jane Doe", materials: "A two-page letter", deadlines: "March 1" },
  grant_count: 24, grant_median: 5000, grants_total: 160000, recipient_states: { FL: 22 }, top_purposes: ["literacy programs for children"],
  sample_grants: [{ to: "READ TAMPA", _to: "Read Tampa", city: "TAMPA", state: "FL", purpose: "literacy", amount: 10000 }],
  url: "https://projects.propublica.org/x" }], p, "FL", ["tampa"], null, false)[0], "FL", true, ["tampa"], p);

describe("one-page summaries", () => {
  it("put the name, the link, the deadline and the checks first", () => {
    const t = grantSummary(fed, today);
    const lines = t.split("\n");
    expect(lines[0]).toBe("Literacy for children");
    expect(lines[1]).toBe("Federal grant · ED-1 · Department of Education · Award $150k to $750k");
    expect(lines[2]).toBe("https://www.grants.gov/x");
    expect(t).toContain("Deadline: Feb 01, 2027");
    expect(t).toContain("CAN WE APPLY? 1 THING STOPS YOU, 1 TO CHECK");
    expect(t).toContain("- Stops you: Matching funds are required (cost sharing); your profile says you can't provide them.");
    expect(t).toContain("- Check: Every federal grant needs an active SAM.gov registration and a UEI.");
    expect(t).not.toContain("Requires cost sharing or matching funds"); // the checklist already says it
    expect(t).toContain("From Grant Matcher on Nov 20, 2026.");
  });

  it("keep long text to a page", () => {
    const t = grantSummary(fed, today);
    expect(t.length).toBeLessThan(3500);
    expect(t).toMatch(/SUMMARY\nLiteracy tutoring .*\.\.\.\n/);
  });

  it("carry a county program's rows and a foundation's way to apply and past grants", () => {
    const t = grantSummary(local, today);
    expect(t.split("\n")[1]).toBe("County program · Sample Arts Council · Sample County");
    expect(t).toContain("- Check: It pays by reimbursement");
    expect(t).toContain("How awards are made: Up to $1,000; no match required.");
    const f = grantSummary(fdn, today);
    expect(f).toContain("Size: Typical $5k");
    expect(f).toContain("HOW TO APPLY");
    expect(f).toContain("What to send: A two-page letter");
    expect(f).toContain("- Read Tampa, TAMPA, FL, $10,000");
  });

  it("join several, and name the file from the title", () => {
    expect(summariesFile([fed, local], today).split("==========")).toHaveLength(2);
    expect(summaryFileName(local)).toBe("community-arts-grants-summary.txt");
    expect([fed, local, fdn].every((e) => !grantSummary(e, today).includes("—"))).toBe(true);
  });
});
