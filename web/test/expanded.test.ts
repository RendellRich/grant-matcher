import { describe, expect, it } from "vitest";
import { profileNarrow, supportIn, type Entry } from "../src/entries";
import { BLANK, expandCities, expandKeywords, FOCUS_AREAS, ORG_TYPES, parseProfile, profileKeywords, type ProfileForm } from "../src/profile";

const base: Entry = {
  key: "x", source: "fed", title: "", url: "", catalog: "", facts: [], side: "", score: 50, tier: "Possible",
  fits: [], cautions: [], also: [], status: [],
};
const e = (key: string, o: Partial<Entry>): Entry => ({ ...base, key, ...o });
const keys = (r: { entries: Entry[] | null }) => (r.entries ?? []).map((x) => x.key);
const form = (o: Partial<ProfileForm>): ProfileForm => ({ ...BLANK, ...o });
const today = new Date(2026, 10, 15);
const day = (n: number) => new Date(2026, 10, 15 + n).getTime();

describe("profile", () => {
  it("turns checkbox groups into key words after the typed ones", () => {
    const kw = profileKeywords(form({ keywords: "Orton-Gillingham, reading", focus_areas: ["literacy"], ages: ["k5"] }));
    expect(kw.slice(0, 2)).toEqual(["Orton-Gillingham", "reading"]);
    expect(kw).toContain("phonics");
    expect(kw).toContain("elementary");
    expect(kw.filter((w) => w.toLowerCase() === "reading")).toHaveLength(1);
    expect(expandKeywords(["a"], ["nope"])).toEqual(["a"]);
  });
  it("expands a county into its places and keeps typed cities", () => {
    const counties = { Manatee: ["Bradenton", "Palmetto"], Sarasota: ["Sarasota", "Venice"] };
    expect(expandCities("Manatee County, Tampa", counties)).toEqual(["Manatee County", "Bradenton", "Palmetto", "Tampa"]);
    expect(expandCities("sarasota", counties)).toEqual(["sarasota", "Venice"]);
    expect(expandCities("Tampa", null)).toEqual(["Tampa"]);
  });
  it("loads an older saved profile with the new fields at their defaults", () => {
    const p = parseProfile(JSON.stringify({ mission: "m", keywords: "k", state: "FL" }));
    expect(p.focus_areas).toEqual([]);
    expect(p.funder_types).toEqual(BLANK.funder_types);
    expect(p.delivery).toBe("in_person");
    expect(p.include_rolling).toBe(true);
  });
  it("cleans what a saved profile carries", () => {
    const p = parseProfile(JSON.stringify({
      mission: "m", focus_areas: ["literacy", "made-up"], year_founded: "20x6", ask_min: "$1,000", ask_max: "-5",
      delivery: "teleport", hide: ["research", "x"], funder_types: [],
    }));
    expect(p.focus_areas).toEqual(["literacy"]);
    expect(p.year_founded).toBe("");
    expect([p.ask_min, p.ask_max]).toEqual(["1000", ""]);
    expect(p.delivery).toBe("in_person");
    expect(p.hide).toEqual(["research"]);
    expect(p.funder_types).toEqual([]); // a person may turn every funder type off
  });
});

describe("profile filters", () => {
  it("drops results that mention words to avoid", () => {
    const list = [e("a", { title: "Capital campaign for a new gym" }), e("b", { title: "Reading tutors" })];
    expect(keys(profileNarrow(list, form({ exclude_words: "capital campaign" }), today))).toEqual(["b"]);
  });
  it("keeps results of a chosen support type, and those that don't say", () => {
    const list = [e("a", { support: ["capital"] }), e("b", { support: ["general", "program"] }), e("c", { support: [] })];
    expect(keys(profileNarrow(list, form({ support_types: ["general"] }), today))).toEqual(["b", "c"]);
    expect(supportIn("General operating support for a new nonprofit")).toEqual(["general", "startup"]);
  });
  it("matches the ask range to federal award ranges and foundations' typical grants", () => {
    const list = [
      e("f1", { amountLow: 5_000, amountHigh: 20_000 }), e("f2", { amountLow: 200_000, amountHigh: 500_000 }),
      e("f3", { amountLow: null, amountHigh: null }),
      e("d1", { source: "fdn", sortMedian: 7_500 }), e("d2", { source: "fdn", sortMedian: 90_000 }),
    ];
    expect(keys(profileNarrow(list, form({ ask_min: "1000", ask_max: "25000" }), today))).toEqual(["f1", "f3", "d1"]);
  });
  it("keeps the chosen foundation kinds", () => {
    const list = [e("a", { source: "fdn", kind: "Private foundation" }), e("b", { source: "fdn", kind: "Community foundation" })];
    expect(keys(profileNarrow(list, form({ funder_types: ["federal", "Community foundation"] }), today))).toEqual(["b"]);
  });
  it("filters by timing, with rolling deadlines as a choice", () => {
    const list = [
      e("soon", { sortClose: day(20) }), e("later", { sortClose: day(80) }), e("none", { source: "fdn", sortClose: null }),
      e("fc", { forecast: true, sortClose: day(10) }), e("web", { source: "fdn", cycle: "open" }),
    ];
    expect(keys(profileNarrow(list, form({ timing: "30" }), today))).toEqual(["soon", "none", "fc", "web"]);
    expect(keys(profileNarrow(list, form({ timing: "30", include_rolling: false }), today))).toEqual(["soon", "fc"]);
    expect(keys(profileNarrow(list, form({ timing: "open", include_rolling: false }), today))).toEqual(["soon", "later", "web"]);
  });
  it("hides what the hide list names, reading the scorer's own cautions", () => {
    const list = [
      e("s", { cautions: ["Mostly scholarships paid to students, not grants to organizations"] }),
      e("i", { cautions: ["Its website says it isn't taking new requests now (website checked Nov 11)"] }),
      e("u", { cautions: ["Says it does not accept unsolicited requests"] }),
      e("p", { asks501c3: true }), e("r", { cautions: ["Research grant; usually needs a research team and institution"] }),
      e("c", { cautions: ["Requires cost sharing or matching funds"] }), e("ok", {}),
    ];
    const all = ["scholarship", "invitation", "unsolicited", "asks501", "research", "costshare"];
    const out = profileNarrow(list, form({ hide: all }), today);
    expect(keys(out)).toEqual(["ok"]);
    expect(out.hidden).toBe(6);
    expect(profileNarrow(null, form({}), today)).toEqual({ entries: null, hidden: 0 });
  });
});

describe("type of organization", () => {
  it("keeps a known type from a saved profile and drops an unknown one", () => {
    expect(parseProfile(JSON.stringify({ mission: "m", org_type: "animals" })).org_type).toBe("animals");
    expect(parseProfile(JSON.stringify({ mission: "m", org_type: "made-up" })).org_type).toBe("");
    expect(parseProfile(JSON.stringify({ mission: "m" })).org_type).toBe("");
  });
  it("only lists focus areas that exist", () => {
    const ids = new Set(FOCUS_AREAS.map((t) => t.id));
    for (const o of ORG_TYPES) for (const f of o.focus) expect(ids.has(f)).toBe(true);
  });
});
