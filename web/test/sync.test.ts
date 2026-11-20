// Profile and shortlist on any device: how two copies of the shortlist come together (web/src/sync.ts).
import { describe, expect, it } from "vitest";
import type { Entry } from "../src/entries";
import { setDue, setStage, toggle, type Item } from "../src/shortlist";
import { mergeShortlists, onLoad, parseWorkspace, type Workspace } from "../src/sync";

const entry = (key: string) => ({ key, title: key, source: "fed" }) as unknown as Entry;
const t = (h: number) => new Date(Date.UTC(2026, 10, 20, h));
const ws = (shortlist: Item[] | null, version = 3): Workspace => ({ paid: true, on: true, profile: null, vector: null, version, shortlist });

describe("account sync", () => {
  it("dates every change, so the newer copy of an item wins", () => {
    const a = toggle([], entry("fed:1"), t(1));
    expect(a[0].at).toBe(t(1).toISOString());
    expect(setStage(a, "fed:1", "applying", t(2))[0].at).toBe(t(2).toISOString());
    expect(setDue(a, "fed:1", "2026-12-01", t(3))[0].at).toBe(t(3).toISOString());
    expect(setDue(a, "fed:1", "", t(4))).toEqual(a); // nothing changed, no new date
  });
  it("keeps everything on either list and the latest copy of each item", () => {
    const base = toggle(toggle([], entry("fed:1"), t(1)), entry("fed:2"), t(1));
    const phone = setStage(toggle(base, entry("fed:3"), t(2)), "fed:1", "applying", t(2));
    const laptop = setStage(base, "fed:1", "submitted", t(3));
    const merged = mergeShortlists(laptop, phone);
    expect(merged.map((x) => x.key)).toEqual(["fed:1", "fed:2", "fed:3"]);
    expect(merged[0].stage).toBe("submitted");
    expect(mergeShortlists(phone, laptop)[0].stage).toBe("submitted");
  });
  it("takes the account's copy when this browser has no changes of its own", () => {
    const local = toggle([], entry("fed:1"), t(1));
    const saved = toggle([], entry("fed:9"), t(2));
    expect(onLoad(local, { account: "a@x", version: 2, dirty: false }, "a@x", ws(saved))).toEqual({ items: saved, push: false });
  });
  it("saves this browser's changes over the version it started from, and merges over a newer one", () => {
    const local = toggle([], entry("fed:1"), t(1));
    const saved = toggle([], entry("fed:9"), t(2));
    expect(onLoad(local, { account: "a@x", version: 3, dirty: true }, "a@x", ws(saved, 3))).toEqual({ items: local, push: true });
    const r = onLoad(local, { account: "a@x", version: 2, dirty: true }, "a@x", ws(saved, 3));
    expect(r.push).toBe(true);
    expect(r.items.map((x) => x.key)).toEqual(["fed:1", "fed:9"]);
    expect(onLoad([], { account: "a@x", version: 3, dirty: true }, "a@x", ws(saved, 3))).toEqual({ items: [], push: true }); // cleared here
  });
  it("brings a browser's list into the account the first time, and never mixes two accounts", () => {
    const local = toggle([], entry("fed:1"), t(1));
    const saved = toggle([], entry("fed:9"), t(2));
    expect(onLoad(local, null, "a@x", ws(saved)).items.map((x) => x.key)).toEqual(["fed:1", "fed:9"]);
    expect(onLoad(local, null, "a@x", ws(null))).toEqual({ items: local, push: true });
    expect(onLoad([], null, "a@x", ws(saved))).toEqual({ items: saved, push: false });
    expect(onLoad(local, { account: "b@x", version: 5, dirty: true }, "a@x", ws(saved))).toEqual({ items: saved, push: false });
  });
  it("reads what the account sends", () => {
    expect(parseWorkspace(null)).toMatchObject({ paid: false, on: false, shortlist: null, version: 0 });
    const w = parseWorkspace({ paid: true, on: true, version: 4, vector: [1, 2], profile: { mission: "m" }, shortlist: [{ key: "fed:1" }, { nokey: 1 }] });
    expect(w.vector).toBeNull();
    expect(w.shortlist?.map((x) => x.key)).toEqual(["fed:1"]);
    expect(w.shortlist?.[0].stage).toBe("saved");
  });
});
