// The shared ranking (src/rank.ts) that the page and the background scorer both use.
import { existsSync, readFileSync } from "node:fs";
import { gunzipSync } from "node:zlib";
import { describe, expect, it } from "vitest";
import { federalEntry, floridaEntry, foundationEntry, type Entry } from "../src/entries";
import { BLANK, expandCities, type ProfileForm } from "../src/profile";
import { isBlank, KINDS, queryText, rankAll, strongItems, toProfile } from "../src/rank";
import { scoreFederal, scoreFlorida, scoreFoundations } from "../src/score";
import { decodeF16, similarities } from "../src/vectors";

const entry = (key: string, tier: string, extra: Partial<Entry> = {}) =>
  ({ key, source: key.split(":")[0], title: `Title ${key}`, tier, ...extra }) as Entry;

describe("strong items", () => {
  it("keeps each strong grant once, in key order, with a funder and a deadline date", () => {
    const close = new Date(2027, 0, 15).getTime();
    const items = strongItems([
      [entry("fed:2", "Strong", { agency: "Synthetic Agency", sortClose: close }), entry("fed:3", "Possible")],
      [entry("fdn:591234567", "Strong"), entry("fed:2", "Strong")],
      null,
      [entry("fl:fl-1", "Strong", { sortClose: null })],
    ]);
    expect(items).toEqual([
      { k: "fdn:591234567", title: "Title fdn:591234567", funder: "Title fdn:591234567", deadline: null },
      { k: "fed:2", title: "Title fed:2", funder: "Synthetic Agency", deadline: "2027-01-15" },
      { k: "fl:fl-1", title: "Title fl:fl-1", funder: null, deadline: null },
    ]);
    expect(strongItems([[entry("fed:1", "Strong"), entry("fed:2", "Strong")]], 1).map((i) => i.k)).toEqual(["fed:1"]);
  });
});

describe("the saved profile", () => {
  const form: ProfileForm = { ...BLANK, mission: "Synthetic literacy", keywords: "reading, tutoring", has_501c3: "Pending", year_founded: "2020" };
  it("reads the same way the page reads it", () => {
    const p = toProfile(form, new Date(2026, 10, 17, 15, 30));
    expect(p.today).toEqual(new Date(2026, 10, 17));
    expect(p.keywords).toContain("reading");
    expect(p.yearFounded).toBe(2020);
    expect(queryText(form)).toBe("Synthetic literacy reading, tutoring");
    expect(isBlank(BLANK)).toBe(true);
    expect(isBlank(form)).toBe(false);
  });
  it("ranks nothing for an empty profile", () => {
    expect(rankAll(BLANK, { fed: null, fdn: null, fl: null, counties: null }, null)).toEqual({ fed: null, fdn: null, fl: null });
  });
});

const DIR = new URL("../test-data/", import.meta.url);
const have = existsSync(new URL("federal.json.gz", DIR)) && existsSync(new URL("foundations-FL.json.gz", DIR));
function load(name: string) {
  const payload = JSON.parse(gunzipSync(readFileSync(new URL(`${name}.json.gz`, DIR))).toString("utf8"));
  const raw = readFileSync(new URL(`${name}.f16`, DIR));
  return { records: payload.records, vecs: decodeF16(raw.buffer.slice(raw.byteOffset, raw.byteOffset + raw.byteLength) as ArrayBuffer, payload.vec_ids, payload.dim) };
}

describe.skipIf(!have)("on the test data", () => {
  const fed = have ? load("federal") : null, fl = have ? load("florida") : null, fdn = have ? load("foundations-FL") : null;
  const examples = have ? JSON.parse(readFileSync(new URL("examples.json", DIR), "utf8")) : {};
  const ex = Object.values(examples)[0] as { mission: string; keywords: string; vector: number[] } | undefined;
  const counties = existsSync(new URL("counties-FL.json", DIR)) ? JSON.parse(readFileSync(new URL("counties-FL.json", DIR), "utf8")) : null;
  const form: ProfileForm = { ...BLANK, mission: ex?.mission ?? "", keywords: ex?.keywords ?? "", state: "FL", cities: "Tampa" };
  const now = new Date(2026, 10, 17);

  it("gives the same lists as scoring each source by hand, the way the page did before", () => {
    const got = rankAll(form, { fed, fdn, fl, counties }, ex!.vector, now);
    const p = toProfile(form, now), hasKw = p.keywords.length > 0;
    expect(got.fed).toEqual(scoreFederal(fed!.records, p, similarities(fed!.vecs, ex!.vector)).map((s) => federalEntry(s, hasKw)));
    expect(got.fdn).toEqual(scoreFoundations(fdn!.records.filter((r: { kind?: string }) => KINDS.includes(r.kind || "Private foundation")), p, "FL",
      expandCities("Tampa", counties), similarities(fdn!.vecs, ex!.vector), false).map((s) => foundationEntry(s, "FL", hasKw, expandCities("Tampa", counties))));
    expect(got.fl).toEqual(scoreFlorida(fl!.records, p, similarities(fl!.vecs, ex!.vector), false, expandCities("Tampa", counties)).map((s) => floridaEntry(s, hasKw)));
  });

  it("leaves Florida programs out for another state", () => {
    expect(rankAll({ ...form, state: "GA" }, { fed, fdn: null, fl, counties: null }, ex!.vector, now).fl).toBeNull();
  });
});
