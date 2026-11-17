import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { markNew, markOrgNew, newSince, strongKeys } from "../src/seen";

class Mem {
  data = new Map<string, string>();
  getItem(k: string) { return this.data.get(k) ?? null; }
  setItem(k: string, v: string) { this.data.set(k, v); }
}
const g = globalThis as unknown as { localStorage?: Mem; sessionStorage?: Mem };

describe("newSince", () => {
  beforeEach(() => { g.localStorage = new Mem(); g.sessionStorage = new Mem(); });
  afterEach(() => { delete g.localStorage; delete g.sessionStorage; });

  it("marks nothing on a first visit", () => {
    expect(newSince("fed", ["1", "2"]).since).toBeNull();
    expect(newSince("fed", ["1", "2"]).ids.size).toBe(0);
  });
  it("marks what arrived since the last visit, and keeps the marks on a reload", () => {
    newSince("fed", ["1", "2"], new Date("2026-11-14T12:00:00Z"));
    g.sessionStorage = new Mem(); // a new visit
    const now = newSince("fed", ["1", "2", "3"]);
    expect([...now.ids]).toEqual(["3"]);
    expect(now.since).toBe("2026-11-14T12:00:00.000Z");
    expect([...newSince("fed", ["1", "2", "3"]).ids]).toEqual(["3"]); // reload in the same tab
    g.sessionStorage = new Mem(); // the visit after that
    expect(newSince("fed", ["1", "2", "3"]).ids.size).toBe(0);
  });
  it("keeps each source and state apart", () => {
    newSince("fdn-FL", ["a"]);
    g.sessionStorage = new Mem();
    expect(newSince("fdn-GA", ["a", "b"]).since).toBeNull();
  });
});

describe("markNew", () => {
  it("sets isNew from the record id in the key", () => {
    const list: { key: string; isNew?: boolean }[] = [{ key: "fdn:1" }, { key: "fdn:2" }];
    const out = markNew(list, { ids: new Set(["2"]), since: "x" })!;
    expect(out.map((e) => Boolean(e.isNew))).toEqual([false, true]);
  });
});

describe("ETO's shared New marks", () => {
  const list: { key: string; tier: string; isNew?: boolean }[] = [{ key: "fed:1", tier: "Strong" }, { key: "fed:2", tier: "Strong" }, { key: "fdn:3", tier: "Possible" }, { key: "fed:1", tier: "Strong" }];
  it("marks strong matches ETO hasn't seen, and nothing before ETO's first count", () => {
    const marked = markOrgNew(list, { keys: new Set(["fed:1"]), since: "2026-11-17T10:00:00Z" })!;
    expect(marked.map((e) => !!e.isNew)).toEqual([false, true, false, false]);
    expect(markOrgNew(list, { keys: new Set(), since: null })!.some((e) => e.isNew)).toBe(false);
    expect(markOrgNew(null, { keys: new Set(), since: null })).toBeNull();
  });
  it("lists each strong key once, sorted and capped", () => {
    expect(strongKeys([list, null, [{ key: "fl:9", tier: "Strong" }]])).toEqual(["fed:1", "fed:2", "fl:9"]);
    expect(strongKeys([list], 1)).toEqual(["fed:1"]);
  });
});
