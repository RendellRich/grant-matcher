import { describe, expect, it } from "vitest";
import type { Entry } from "../src/entries";
import { dropSubmitted, parseShortlist, setStage, submittedKeys, toggle } from "../src/shortlist";

const entry = (key: string, extra: Partial<Entry> = {}) => ({ key, title: key, source: "fed", ...extra }) as unknown as Entry;
const at = new Date("2026-11-15T12:00:00Z");

describe("shortlist stages", () => {
  it("reads a shortlist saved before stages as all saved", () => {
    const items = parseShortlist(JSON.stringify([entry("fed:1"), entry("fdn:2")]));
    expect(items.map((x) => x.stage)).toEqual(["saved", "saved"]);
    expect(items[0].stageAt).toBe("");
  });
  it("ignores stored data it can't read", () => {
    expect(parseShortlist("not json")).toEqual([]);
    expect(parseShortlist('{"a":1}')).toEqual([]);
    expect(parseShortlist(null)).toEqual([]);
  });
  it("adds as saved with the date, drops the new mark, and removes on a second press", () => {
    const one = toggle([], entry("fed:1", { isNew: true }), at);
    expect(one).toHaveLength(1);
    expect(one[0].stage).toBe("saved");
    expect(one[0].stageAt).toBe("2026-11-15T12:00:00.000Z");
    expect("isNew" in one[0]).toBe(false);
    expect(toggle(one, entry("fed:1"))).toEqual([]);
  });
  it("moves one entry to a stage and dates the move", () => {
    const items = toggle(toggle([], entry("fed:1"), at), entry("fed:2"), at);
    const later = new Date("2026-12-01T09:00:00Z");
    const moved = setStage(items, "fed:2", "submitted", later);
    expect(moved.map((x) => x.stage)).toEqual(["saved", "submitted"]);
    expect(moved[1].stageAt).toBe("2026-12-01T09:00:00.000Z");
    expect(setStage(moved, "fed:2", "submitted", new Date())[1].stageAt).toBe(moved[1].stageAt); // no change, same date
  });
  it("takes submitted entries out of the results and counts them", () => {
    let items = toggle(toggle([], entry("fed:1"), at), entry("fed:2"), at);
    items = setStage(items, "fed:1", "submitted", at);
    const done = submittedKeys(items);
    const out = dropSubmitted([entry("fed:1"), entry("fed:2"), entry("fed:3")], done);
    expect(out.entries?.map((e) => e.key)).toEqual(["fed:2", "fed:3"]);
    expect(out.hidden).toBe(1);
    expect(dropSubmitted(null, done)).toEqual({ entries: null, hidden: 0 });
    expect(dropSubmitted([entry("fed:9")], new Set()).hidden).toBe(0);
  });
});
