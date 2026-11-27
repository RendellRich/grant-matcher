// Missouri's required disclaimer travels with its listings: every place that lists a state call outside the page
// itself, and a check that the page's two list views draw it.
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { noticesFor } from "../src/disclaimers";
import type { Entry } from "../src/entries";
import { entriesCsv } from "../src/exports";
import { payloadFor } from "../src/parent";
import { combinedEmail, digestEmail } from "../src/server/digest";
import { reminderEmail } from "../src/server/reminder-email";
import { shortlistIcs, type Item } from "../src/shortlist";
import { summariesFile } from "../src/summary";
import { BLANK } from "../src/profile";

const START = "The data made available here has been modified for use from its original source, which is the State of Missouri.";
const END = "being used at one’s own risk.";
const item = (key: string, over: Partial<Item> = {}): Item => ({
  key, source: "fl", title: `Synthetic ${key}`, url: "https://example.org/x", catalog: "", facts: [], side: "", score: 80,
  tier: "Strong", fits: [], cautions: [], also: [], status: [], stage: "saved", stageAt: "", due: "2027-01-04", ...over,
} as Entry & Item);
const mo = item("fl:mo-express-grants");
const ky = item("fl:ky-kentucky-arts-rising");
const has = (s: string) => s.includes(START) && s.includes(END);

describe("a source's required words", () => {
  it("apply to Missouri calls only", () => {
    expect(noticesFor([mo.key]).map((n) => n.name)).toEqual(["Missouri"]);
    expect(noticesFor([ky.key, "fed:1", "fdn:591234567", "fl:local-mo-x", "fl:10.123"])).toEqual([]);
  });

  it("are a CSV column when a listed call needs them, filled for that call only", () => {
    const [head, first, second] = entriesCsv([mo, ky]).split("\r\n");
    expect(head.endsWith(",url,required_notice")).toBe(true);
    expect(has(first)).toBe(true);
    expect(second.endsWith("https://example.org/x,")).toBe(true);
    expect(entriesCsv([ky])).not.toContain("required_notice");
    expect(has(entriesCsv([mo], true))).toBe(true);
  });

  it("go in the one-page summaries and the calendar file", () => {
    expect(has(summariesFile([mo]))).toBe(true);
    expect(has(summariesFile([ky]))).toBe(false);
    const ics = shortlistIcs([mo], new Map(), new Date(2026, 10, 27)).replace(/\\([,;\\])/g, "$1");
    expect(has(ics)).toBe(true);
    expect(has(shortlistIcs([ky], new Map(), new Date(2026, 10, 27)))).toBe(false);
  });

  it("go in both parts of the weekly and reminder emails", () => {
    const mails = [
      digestEmail(BLANK, [mo], "https://site", "https://off"),
      combinedEmail([{ client: "A", fresh: [mo] }], "https://site", "https://off"),
      reminderEmail({ account_id: "a", email: "a@example.org", token: "t", items: [{ key: mo.key, title: mo.title,
        url: mo.url, source: "fl", stage: "saved", due: "2027-01-04", days: 14 }] }, "https://site", "https://off"),
    ];
    for (const m of mails) {
      expect(has(m.html)).toBe(true);
      expect(has(m.text)).toBe(true);
    }
    expect(has(digestEmail(BLANK, [ky], "https://site", "https://off").html)).toBe(false);
  });

  it("go to ETO's pipeline uncut, however long the summary", () => {
    const sent = payloadFor({ ...mo, summary: "x".repeat(3000) });
    expect(has(sent.summary)).toBe(true);
    expect(sent.summary.length).toBeLessThanOrEqual(1000);
    expect(payloadFor(ky).summary).toBe("");
  });

  it("are drawn by the result lists (results, long shots, previews) and the shortlist", () => {
    const src = (f: string) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");
    expect(src("ui.tsx")).toContain("<RequiredNotice keys={p.entries.map((e) => e.key)} />");
    expect(src("app.tsx")).toContain("<RequiredNotice keys={list.items.map((e) => e.key)} />");
  });
});
