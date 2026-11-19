// Deadline reminders: which shortlisted grants go to the server, and the email that lists them.
import { describe, expect, it } from "vitest";
import type { Entry } from "../src/entries";
import { reminderEmail, type ReminderAccount } from "../src/server/reminder-email";
import { reminderItems, type Item, type Listed } from "../src/shortlist";

const today = new Date(2026, 10, 19);
const item = (key: string, over: Partial<Item> = {}): Item => ({
  key, source: "fdn", title: `Synthetic ${key}`, url: `https://example.org/${key}`, catalog: "", facts: [], side: "", score: 80,
  tier: "Strong", fits: [], cautions: [], also: [], status: [], stage: "saved", stageAt: "", ...over,
} as Entry & Item);

describe("reminder items", () => {
  it("sends each open shortlisted grant with a deadline today or later, soonest first", () => {
    const items = [
      item("fdn:a", { due: "2026-12-03" }),
      item("fdn:b", { due: "2026-11-18" }),                       // already past
      item("fdn:c", { due: "2026-11-25", stage: "submitted" }),   // done
      item("fdn:d"),                                              // no date
      item("fdn:e", { due: "2026-11-22", stage: "applying" }),
      item("fdn:f", { sortClose: new Date(2026, 11, 1).getTime() }), // listed date only
    ];
    expect(reminderItems(items, new Map(), today)).toEqual([
      { key: "fdn:e", title: "Synthetic fdn:e", url: "https://example.org/fdn:e", source: "fdn", stage: "applying", due: "2026-11-22" },
      { key: "fdn:f", title: "Synthetic fdn:f", url: "https://example.org/fdn:f", source: "fdn", stage: "saved", due: "2026-12-01" },
      { key: "fdn:a", title: "Synthetic fdn:a", url: "https://example.org/fdn:a", source: "fdn", stage: "saved", due: "2026-12-03" },
    ]);
  });
  it("follows today's federal listing and drops withdrawn grants", () => {
    const fed = item("fed:1", { source: "fed", sortClose: new Date(2026, 11, 1).getTime() });
    const moved: Listed = new Map([["fed:1", "2026-12-10"]]);
    expect(reminderItems([fed], moved, today)[0].due).toBe("2026-12-10");
    expect(reminderItems([fed], new Map([["fed:1", "gone"]]), today)).toEqual([]);
  });
});

describe("the reminder email", () => {
  const acct: ReminderAccount = { account_id: "a", email: "x@example.org", token: "t", items: [
    { key: "fdn:a", title: "Synthetic <Fund>", url: "https://example.org/a", source: "fdn", stage: "applying", due: "2026-12-03", days: 14 },
    { key: "fl:b", title: "Synthetic program", url: "", source: "fl", stage: "saved", due: "2026-11-22", days: 3 },
  ] };
  it("leads with the soonest deadline and escapes titles", () => {
    const m = reminderEmail(acct, "https://site/", "https://site/?reminders-off=t");
    expect(m.subject).toBe("2 grant deadlines coming up, the first due in 3 days");
    expect(m.html.indexOf("Synthetic program")).toBeLessThan(m.html.indexOf("Synthetic &lt;Fund&gt;"));
    expect(m.html).toContain("Nov 22, 2026</strong>, due in 3 days");
    expect(m.html).toContain('href="https://site/?reminders-off=t"');
    expect(m.text).toContain("Turn off deadline reminders: https://site/?reminders-off=t");
    expect(`${m.subject}${m.text}`).not.toMatch(/[–—]/);
  });
  it("names a single grant in the subject", () => {
    const one = { ...acct, items: [{ ...acct.items[1], days: 0 }] };
    expect(reminderEmail(one, "s", "u").subject).toBe("Grant deadline due today: Synthetic program");
  });
});
