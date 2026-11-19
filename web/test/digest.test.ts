// The weekly email (src/server/digest.ts): which strong matches are new, and what the email says.
import { existsSync, readFileSync } from "node:fs";
import { gunzipSync } from "node:zlib";
import { describe, expect, it } from "vitest";
import type { Entry } from "../src/entries";
import { BLANK, type ProfileForm } from "../src/profile";
import { DIGEST_LIMIT, digestEmail, newStrong } from "../src/server/digest";
import { preview } from "../src/server/preview";
import { decodeF16 } from "../src/vectors";

const entry = (i: number, over: Partial<Entry> = {}): Entry => ({
  key: `fed:${i}`, source: "fed", title: `Synthetic grant ${i} <b>`, url: `https://example.org/${i}`, catalog: "", facts: [],
  side: "Closes Dec 1", score: 90 - i, tier: "Strong", fits: ["Mentions literacy"], cautions: [], also: [], status: [], ...over,
});

describe("the weekly email", () => {
  const f: ProfileForm = { ...BLANK, mission: "Synthetic after-school literacy & tutoring" };
  it("counts, lists and escapes the new matches, with a working unsubscribe link", () => {
    const m = digestEmail(f, [entry(1), entry(2, { source: "fdn", side: "" })], "https://site/", "https://fn/?off=abc");
    expect(m.subject).toBe("2 new strong grant matches this week");
    expect(m.html).toContain("Synthetic grant 1 &lt;b&gt;");
    expect(m.html).not.toContain("<b>");
    expect(m.html).toContain("after-school literacy &amp; tutoring");
    expect(m.html).toContain("Foundation");
    expect(m.html).toContain('href="https://fn/?off=abc"');
    expect(m.text).toContain("Turn off this email: https://fn/?off=abc");
    expect(m.text).not.toMatch(/[–—]/);
  });
  it("says one match in the singular and caps a long list", () => {
    expect(digestEmail(f, [entry(1)], "s", "u").subject).toBe("1 new strong grant match this week");
    const many = Array.from({ length: DIGEST_LIMIT + 4 }, (_, i) => entry(i));
    const m = digestEmail(f, many, "s", "u");
    expect(m.html).toContain("And 4 more.");
    expect(m.text.match(/^Synthetic grant/gm)).toHaveLength(DIGEST_LIMIT);
  });
});

const DIR = new URL("../test-data/", import.meta.url);
const have = ["federal.json.gz", "florida.json.gz", "foundations-FL.json.gz", "examples.json"].every((x) => existsSync(new URL(x, DIR)));
function load(name: string) {
  const payload = JSON.parse(gunzipSync(readFileSync(new URL(`${name}.json.gz`, DIR))).toString("utf8"));
  const raw = readFileSync(new URL(`${name}.f16`, DIR));
  return { records: payload.records, vecs: decodeF16(raw.buffer.slice(raw.byteOffset, raw.byteOffset + raw.byteLength) as ArrayBuffer, payload.vec_ids, payload.dim) };
}

describe.skipIf(!have)("new strong matches on the test data", () => {
  const src = have ? { fed: load("federal"), fl: load("florida"), fdn: load("foundations-FL"), flState: "FL", counties: null } : null;
  const ex = have ? (Object.values(JSON.parse(readFileSync(new URL("examples.json", DIR), "utf8")))[0] as
    { mission: string; keywords: string; categories: string[]; state: string; cities: string; vector: number[] }) : null;
  const now = new Date(2026, 10, 19);
  const f: ProfileForm = ex ? { ...BLANK, mission: ex.mission, keywords: ex.keywords, categories: ex.categories, state: ex.state, cities: ex.cities } : BLANK;
  it("remembers every strong match the search shows, and nothing weaker", () => {
    const { all } = newStrong(f, src!, ex!.vector, null, now);
    const pv = preview(f, src!, ex!.vector, now, 1e9, true);
    const strong = Object.values(pv.lists).flatMap((l) => (l ?? []).filter((e) => e.tier === "Strong").map((e) => e.key));
    expect(all.length).toBeGreaterThan(0);
    expect(new Set(all)).toEqual(new Set(strong));
  });
  it("sends only what wasn't there last week", () => {
    const { all } = newStrong(f, src!, ex!.vector, null, now);
    expect(newStrong(f, src!, ex!.vector, all, now).fresh).toEqual([]);
    const lastWeek = all.slice(2);
    const { fresh } = newStrong(f, src!, ex!.vector, lastWeek, now);
    expect(new Set(fresh.map((e) => e.key))).toEqual(new Set(all.slice(0, 2)));
    expect(fresh.every((e) => e.tier === "Strong")).toBe(true);
  });
});
