// Consultant emails: the weekly email per client or combined (src/server/digest.ts), and reminders that say
// which client a deadline is for (src/server/reminder-email.ts).
import { describe, expect, it } from "vitest";
import type { Entry } from "../src/entries";
import { BLANK, type ProfileForm } from "../src/profile";
import { COMBINED_LIMIT, combinedEmail, digestEmail } from "../src/server/digest";
import { reminderEmail } from "../src/server/reminder-email";

const entry = (i: number): Entry => ({
  key: `fed:${i}`, source: "fed", title: `Synthetic grant ${i}`, url: `https://example.org/${i}`, catalog: "", facts: [],
  side: "", score: 90 - i, tier: "Strong", fits: ["Mentions literacy"], cautions: [], also: [], status: [],
});
const f: ProfileForm = { ...BLANK, mission: "Synthetic adult literacy" };

describe("Consultant emails", () => {
  it("names the client in a per-client email", () => {
    const m = digestEmail(f, [entry(1)], "https://site/", "https://off/", "Tampa Literacy <Project>");
    expect(m.subject).toBe("1 new strong grant match this week for Tampa Literacy <Project>");
    expect(m.html).toContain("<strong>Tampa Literacy &lt;Project&gt;</strong>");
    expect(m.text).toContain("since last week for Tampa Literacy <Project>: Synthetic adult literacy");
    expect(digestEmail(f, [entry(1)], "s", "u").text).toContain("since last week for: Synthetic adult literacy");
  });
  it("puts every client with new matches in one combined email, and skips the rest", () => {
    const many = Array.from({ length: COMBINED_LIMIT + 3 }, (_, i) => entry(i));
    const m = combinedEmail([{ client: "Food Pantry", fresh: [entry(1), entry(2)] }, { client: "Quiet One", fresh: [] }, { client: "Big Client", fresh: many }],
      "https://site/", "https://off/");
    expect(m.subject).toBe(`${2 + many.length} new strong grant matches this week across 2 clients`);
    expect(m.html).toContain("Food Pantry");
    expect(m.html).not.toContain("Quiet One");
    expect(m.html).toContain("And 3 more.");
    expect(m.text).toContain("== Big Client:");
    expect(m.text).toContain("Turn off this email: https://off/");
    expect(m.text).not.toMatch(/[–—]/);
  });
  it("says which client each deadline is for", () => {
    const m = reminderEmail({ account_id: "a", email: "e", token: "t", items: [
      { key: "fed:1", client: "c1", client_label: "Food Pantry", title: "Synthetic food grant", url: "", source: "fed", stage: "saved", due: "2030-01-05", days: 3 },
      { key: "fed:2", client: "", client_label: "", title: "Synthetic plain grant", url: "", source: "fdn", stage: "applying", due: "2030-01-10", days: 8 },
    ] }, "https://site/", "https://off/");
    expect(m.html).toContain("Saved &middot; Food Pantry");
    expect(m.text).toContain("due in 3 days | for Food Pantry");
    expect(m.text).not.toContain("| for \n");
  });
});
