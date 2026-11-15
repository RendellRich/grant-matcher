import { describe, expect, it } from "vitest";
import type { Entry } from "../src/entries";
import {
  byDeadline, comingUp, deadline, dueText, daysUntil, listedNow, parseShortlist, setDue, setStage, shortlistIcs, toggle,
  type Item,
} from "../src/shortlist";

const today = new Date(2026, 10, 15); // Nov 15, 2026, local
const local = (y: number, m: number, d: number) => new Date(y, m - 1, d).getTime();
const entry = (key: string, close: number | null = null, extra: Partial<Entry> = {}) =>
  ({ key, title: `Grant ${key}`, source: key.split(":")[0], catalog: "X-1", url: "https://example.org/g", sortClose: close, ...extra }) as unknown as Entry;
const list = (...es: Entry[]): Item[] => es.reduce<Item[]>((acc, e) => toggle(acc, e, today), []);

describe("deadlines", () => {
  it("counts days from today and words them", () => {
    expect(daysUntil("2026-11-15", today)).toBe(0);
    expect(daysUntil("2026-11-20", today)).toBe(5);
    expect(daysUntil("2026-11-14", today)).toBe(-1);
    expect([dueText(0), dueText(1), dueText(5), dueText(-1), dueText(-3)])
      .toEqual(["Due today", "Due tomorrow", "Due in 5 days", "Past due by 1 day", "Past due by 3 days"]);
  });
  it("uses your own date over the listed one, and clears it with an empty value", () => {
    let items = list(entry("fed:1", local(2026, 12, 1)));
    expect(deadline(items[0], new Map())).toEqual({ date: "2026-12-01", own: false, changedFrom: undefined, gone: false });
    items = setDue(items, "fed:1", "2026-11-25");
    expect(deadline(items[0], new Map())?.date).toBe("2026-11-25");
    expect(deadline(items[0], new Map())?.own).toBe(true);
    expect(deadline(setDue(items, "fed:1", "")[0], new Map())?.own).toBe(false);
  });
  it("keeps your date through a reload and drops a bad one", () => {
    const raw = JSON.stringify([{ ...entry("fdn:9"), stage: "saved", stageAt: "", due: "2026-12-10" }, { ...entry("fdn:8"), due: "soon" }]);
    const items = parseShortlist(raw);
    expect(items[0].due).toBe("2026-12-10");
    expect(items[1].due).toBeUndefined();
  });
  it("notices when Grants.gov moves a deadline or drops the grant", () => {
    const items = list(entry("fed:1", local(2026, 12, 1)), entry("fed:2", local(2026, 12, 5)), entry("fdn:3"));
    const listed = listedNow(items, [{ id: "1", close: new Date(2026, 11, 15) }]);
    expect(listed.get("fed:1")).toBe("2026-12-15");
    expect(listed.get("fed:2")).toBe("gone");
    expect(listed.has("fdn:3")).toBe(false);
    expect(deadline(items[0], listed)).toMatchObject({ date: "2026-12-15", changedFrom: "2026-12-01" });
    expect(deadline(items[1], listed)).toMatchObject({ date: "2026-12-05", gone: true });
    expect(deadline(items[2], listed)).toBeNull();
    expect(listedNow(items, null).size).toBe(0); // federal data not loaded yet: no claims either way
  });
  it("lists what is coming up, soonest first, leaving out submitted ones and far dates", () => {
    let items = list(entry("fed:1", local(2026, 12, 10)), entry("fed:2", local(2026, 11, 18)), entry("fed:3", local(2027, 3, 1)),
      entry("fdn:4"), entry("fed:5", local(2026, 11, 20)));
    items = setDue(items, "fdn:4", "2026-11-13");
    items = setStage(items, "fed:5", "submitted", today);
    const soon = comingUp(items, new Map(), today, 30);
    expect(soon.map((s) => [s.item.key, s.days])).toEqual([["fdn:4", -2], ["fed:2", 3], ["fed:1", 25]]);
    expect(byDeadline(items.filter((x) => x.stage !== "submitted"), new Map()).map((x) => x.key))
      .toEqual(["fdn:4", "fed:2", "fed:1", "fed:3"]);
  });
  it("writes a calendar with two reminders per deadline still ahead", () => {
    let items = list(entry("fed:1", local(2026, 12, 1), { title: "Reading, writing; more" }), entry("fed:2", local(2026, 11, 1)), entry("fdn:3"));
    items = setDue(items, "fdn:3", "2026-12-20");
    const ics = shortlistIcs(items, new Map(), today, new Date(Date.UTC(2026, 10, 15, 12)));
    expect(ics.match(/BEGIN:VEVENT/g)).toHaveLength(2); // the past one and the one with no date are left out
    expect(ics).toContain("DTSTART;VALUE=DATE:20261201");
    expect(ics).toContain("DTEND;VALUE=DATE:20261202");
    expect(ics).toContain("SUMMARY:Due: Reading\\, writing\\; more");
    expect(ics).toContain("SUMMARY:Your deadline: Grant fdn:3");
    expect(ics.match(/TRIGGER:-P14D/g)).toHaveLength(2);
    expect(ics.match(/TRIGGER:-P3D/g)).toHaveLength(2);
    expect(ics).toContain("DTSTAMP:20261115T120000Z");
    expect(ics.endsWith("END:VCALENDAR\r\n")).toBe(true);
  });
});
