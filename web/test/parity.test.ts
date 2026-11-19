// The browser's scores must match Python's. `python -m grantmatch.export_web web/test-data --local
// --golden web/test-data/golden.json` writes the data and Python's results; this runs the same profiles here.
import { readFileSync, existsSync } from "node:fs";
import { gunzipSync } from "node:zlib";
import { describe, expect, it } from "vitest";
import { scoreFederal, scoreFlorida, scoreFoundations, pyRound, money, keywordHits, type Profile } from "../src/score";
import { decodeF16, similarities } from "../src/vectors";
import { expandKeywords, minorKeywords } from "../src/profile";

const DIR = new URL("../test-data/", import.meta.url);
const have = existsSync(new URL("golden.json", DIR));

function load(name: string) {
  const payload = JSON.parse(gunzipSync(readFileSync(new URL(`${name}.json.gz`, DIR))).toString("utf8"));
  const raw = readFileSync(new URL(`${name}.f16`, DIR));
  const buf = raw.buffer.slice(raw.byteOffset, raw.byteOffset + raw.byteLength);
  return { records: payload.records, vecs: decodeF16(buf, payload.vec_ids, payload.dim) };
}

describe("python helpers", () => {
  it("rounds halves to even", () => {
    expect([0.5, 1.5, 2.5, 59.5, 60.5, 34.5].map(pyRound)).toEqual([0, 2, 2, 60, 60, 34]);
  });
  it("formats money like the app", () => {
    expect(money(2500)).toBe("$2k");
    expect(money(1_500_000)).toBe("$1.5M");
    expect(money(2_000_000)).toBe("$2M");
    expect(money(950)).toBe("$950");
    expect(money(null)).toBe("not listed");
  });
  it("matches key word stems at word starts", () => {
    expect(keywordHits(["tutors", "ADHD", "art"], "Tutoring for adhd; partners")).toEqual(["tutors", "ADHD"]);
  });
});

describe.skipIf(!have)("parity with Python scoring", () => {
  const golden = have ? JSON.parse(readFileSync(new URL("golden.json", DIR), "utf8")) : { cases: [] };
  const examples = have ? JSON.parse(readFileSync(new URL("examples.json", DIR), "utf8")) : {};
  const fed = have ? load("federal") : null;
  const fl = have ? load("florida") : null;
  const fdn = have ? load("foundations-FL") : null;
  const ca = have && existsSync(new URL("programs-CA.json.gz", DIR)) ? load("programs-CA") : null;
  const [y, m, d] = (golden.today ?? "2026-11-14").split("-").map(Number);

  for (const c of golden.cases) {
    it(c.name, () => {
      const s = c.spec;
      const typed = s.keywords.split(",").map((k: string) => k.trim()).filter(Boolean);
      const groups = [s.focus_areas ?? [], s.ages ?? [], s.populations ?? []] as const;
      const keywords = expandKeywords(typed, ...groups);
      const minor = minorKeywords(typed, ...groups);
      if (s.expanded_keywords) expect(keywords, "checkbox groups turn into the same key words").toEqual(s.expanded_keywords);
      if (s.minor_keywords) expect(minor, "the same words count at half weight").toEqual(s.minor_keywords);
      const p: Profile = {
        mission: s.mission, keywords,
        has501c3: s.has_501c3, budgetBand: s.budget_band, canCostShare: s.can_cost_share, categories: s.categories,
        includeForecasted: s.include_forecasted, minDaysLeft: s.min_days_left, today: new Date(y, m - 1, d),
        fiscalSponsor: s.fiscal_sponsor ?? false, delivery: s.delivery ?? "in_person", yearFounded: s.year_founded ?? null,
        minorKeywords: minor,
      };
      const q = examples[c.example].vector;
      const cities = s.cities.split(",").filter((x: string) => x.trim());
      const got = {
        federal: scoreFederal(fed!.records, p, similarities(fed!.vecs, q)).map((r) => ({ id: r.rec.id, ...pick(r) })),
        foundations: scoreFoundations(fdn!.records, p, "FL", cities, similarities(fdn!.vecs, q), s.show_preselected)
          .map((r) => ({ id: r.rec.ein, ...pick(r) })),
        florida: scoreFlorida(fl!.records, p, similarities(fl!.vecs, q), s.show_earmarks, cities).map((r) => ({ id: r.rec.id, ...pick(r) })),
        california: ca ? scoreFlorida(ca.records, p, similarities(ca.vecs, q), false, cities).map((r) => ({ id: r.rec.id, ...pick(r) })) : [],
      };
      for (const src of ["federal", "foundations", "florida", "california"] as const) {
        const want = byId(c[src] ?? []);
        const have_ = byId(got[src]);
        expect([...have_.keys()].sort(), `${src} ids`).toEqual([...want.keys()].sort());
        for (const [id, w] of want) {
          const g = have_.get(id)!;
          // float32 sums can land a hair either side of a .5; a one-point difference is allowed, nothing more
          expect(Math.abs(g.score - w.score), `${src} ${id} score`).toBeLessThanOrEqual(1);
          if (g.score === w.score) expect(g.tier, `${src} ${id} tier`).toBe(w.tier);
          expect(g.reasons, `${src} ${id} reasons`).toEqual(w.reasons);
          expect(g.cautions, `${src} ${id} cautions`).toEqual(w.cautions);
        }
        const off = [...want].filter(([id, w]) => have_.get(id)!.score !== w.score).length;
        expect(off / Math.max(1, want.size), `${src} share of scores off by one`).toBeLessThan(0.01);
      }
    });
  }
});

function pick(r: { score: number; tier: string; reasons: string[]; cautions: string[] }) {
  return { score: r.score, tier: r.tier, reasons: r.reasons, cautions: r.cautions };
}

function byId(rows: { id: string; score: number; tier: string; reasons: string[]; cautions: string[] }[]) {
  const m = new Map<string, (typeof rows)[number]>();
  for (const r of rows) m.set(m.has(r.id) ? r.id + "#" + m.size : r.id, r);
  return m;
}
