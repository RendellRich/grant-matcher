// The search function's preview (src/server/preview.ts): what a visitor sees before making an account.
import { existsSync, readFileSync } from "node:fs";
import { gunzipSync } from "node:zlib";
import { describe, expect, it } from "vitest";
import { BLANK, type ProfileForm } from "../src/profile";
import { rankAll } from "../src/rank";
import { profileNarrow } from "../src/entries";
import { FREE_SIZE, preview, PREVIEW_SIZE, searchSignature, shownSources } from "../src/server/preview";
import { decodeF16 } from "../src/vectors";

describe("the search signature", () => {
  const form: ProfileForm = { ...BLANK, mission: "Synthetic literacy", keywords: "reading", categories: ["ED", "HU"] };
  it("ignores refinements, so changing them never counts as a new search", () => {
    const refined = { ...form, min_days_left: 30, include_forecasted: false, ask_max: "5000", hide: ["declined"], timing: "open" as const };
    expect(searchSignature(refined)).toBe(searchSignature(form));
    expect(searchSignature({ ...form, categories: ["HU", "ED"] })).toBe(searchSignature(form));
  });
  it("changes with what is searched for", () => {
    expect(searchSignature({ ...form, mission: "Synthetic food pantry" })).not.toBe(searchSignature(form));
    expect(searchSignature({ ...form, state: "CA" })).not.toBe(searchSignature(form));
    expect(searchSignature({ ...form, focus_areas: ["animals"] })).not.toBe(searchSignature(form));
  });
  it("follows the profile's funder choices", () => {
    expect(shownSources(BLANK, true)).toEqual(["fed", "fdn", "fl"]);
    expect(shownSources({ ...BLANK, funder_types: ["federal"] }, true)).toEqual(["fed"]);
    expect(shownSources(BLANK, false)).toEqual(["fed", "fdn"]);
  });
  it("shows nothing for an empty profile", () => {
    expect(preview(BLANK, { fed: null, fdn: null, fl: null, counties: null }, null)).toEqual({ counts: {}, source: null, lists: {} });
  });
});

const DIR = new URL("../test-data/", import.meta.url);
const have = ["federal.json.gz", "florida.json.gz", "foundations-FL.json.gz", "examples.json"].every((f) => existsSync(new URL(f, DIR)));
function load(name: string) {
  const payload = JSON.parse(gunzipSync(readFileSync(new URL(`${name}.json.gz`, DIR))).toString("utf8"));
  const raw = readFileSync(new URL(`${name}.f16`, DIR));
  return { records: payload.records, vecs: decodeF16(raw.buffer.slice(raw.byteOffset, raw.byteOffset + raw.byteLength) as ArrayBuffer, payload.vec_ids, payload.dim) };
}

describe.skipIf(!have)("on the test data", () => {
  const src = have ? {
    fed: load("federal"), fl: load("florida"), fdn: load("foundations-FL"), flState: "FL",
    counties: existsSync(new URL("counties-FL.json", DIR)) ? JSON.parse(readFileSync(new URL("counties-FL.json", DIR), "utf8")) : null,
  } : null;
  const examples = have ? JSON.parse(readFileSync(new URL("examples.json", DIR), "utf8")) : {};
  const now = new Date(2026, 10, 19);
  it("counts and shows the same matches the full page ranks first", () => {
    for (const ex of Object.values(examples) as { mission: string; keywords: string; categories: string[]; state: string; cities: string; vector: number[] }[]) {
      const f: ProfileForm = { ...BLANK, mission: ex.mission, keywords: ex.keywords, categories: ex.categories, state: ex.state, cities: ex.cities };
      const full = rankAll(f, src!, ex.vector, now);
      const pv = preview(f, src!, ex.vector, now);
      for (const k of ["fed", "fdn", "fl"] as const) {
        const kept = profileNarrow(full[k], f, now).entries ?? [];
        expect(pv.counts[k]).toEqual({ strong: kept.filter((e) => e.tier === "Strong").length, possible: kept.filter((e) => e.tier === "Possible").length });
      }
      expect(pv.source).not.toBeNull();
      expect(Object.keys(pv.lists)).toEqual([pv.source]);
      const top = (profileNarrow(full[pv.source!], f, now).entries ?? []).slice(0, PREVIEW_SIZE);
      expect(pv.lists[pv.source!]!.map((e) => e.key)).toEqual(top.map((e) => e.key));
      expect(pv.lists[pv.source!]).toEqual(top);
      // a free account: the top ten in every source that has a match
      const free = preview(f, src!, ex.vector, now, FREE_SIZE, true);
      expect(free.counts).toEqual(pv.counts);
      for (const k of ["fed", "fdn", "fl"] as const) {
        const kept = (profileNarrow(full[k], f, now).entries ?? []).filter((e) => e.tier !== "Long shot");
        if (kept.length) expect(free.lists[k]).toEqual(kept.slice(0, FREE_SIZE));
        else expect(free.lists[k]).toBeUndefined();
      }
    }
  });
  it("ranks the same from the slim copy the search function reads", () => {
    if (!existsSync(new URL("foundations-FL.slim.json.gz", DIR))) return;
    const slimPayload = JSON.parse(gunzipSync(readFileSync(new URL("foundations-FL.slim.json.gz", DIR))).toString("utf8"));
    const slim = { ...src!, fdn: { records: slimPayload.records, vecs: src!.fdn.vecs } };
    for (const ex of Object.values(examples) as { mission: string; keywords: string; categories: string[]; state: string; cities: string; vector: number[] }[]) {
      const f: ProfileForm = { ...BLANK, mission: ex.mission, keywords: ex.keywords, categories: ex.categories, state: ex.state, cities: ex.cities };
      expect(preview(f, slim, ex.vector, now)).toEqual(preview(f, src!, ex.vector, now));
    }
  });
});
