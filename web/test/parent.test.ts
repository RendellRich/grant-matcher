import { describe, expect, it } from "vitest";
import { profileNarrow, type Entry } from "../src/entries";
import { embedParent, isAllowedParent, payloadFor, readMessage } from "../src/parent";
import { BLANK } from "../src/profile";

const loc = (search: string, ancestors: string[] = []) => ({ search, ancestorOrigins: ancestors });

describe("embedding", () => {
  it("turns on only inside an allowed site, with ?embed=eto", () => {
    expect(embedParent(loc("?embed=eto", ["https://exceedtheodds.com"]), "", true)).toBe("https://exceedtheodds.com");
    expect(embedParent(loc("?embed=eto"), "https://www.exceedtheodds.com/grant-matcher", true)).toBe("https://www.exceedtheodds.com");
    expect(embedParent(loc("?embed=eto", ["https://evil.example"]), "", true)).toBeNull();
    expect(embedParent(loc("?embed=eto", ["https://exceedtheodds.com.evil.example"]), "", true)).toBeNull();
    expect(embedParent(loc("", ["https://exceedtheodds.com"]), "", true)).toBeNull(); // no switch
    expect(embedParent(loc("?embed=eto", ["https://exceedtheodds.com"]), "", false)).toBeNull(); // not in a frame
    expect(embedParent(loc("?embed=eto"), "not a url", true)).toBeNull();
    expect(isAllowedParent("http://localhost:5173")).toBe(true);
    expect(isAllowedParent("http://localhost:5174")).toBe(false);
  });
});

describe("messages from ETO", () => {
  it("cleans a profile like a loaded file", () => {
    const m = readMessage({ type: "eto:profile", profile: { mission: "m", focus_areas: ["literacy", "bogus"], hide: ["inpipeline", "x"], state: "ZZ" } });
    expect(m?.type).toBe("eto:profile");
    if (m?.type !== "eto:profile") return;
    expect(m.profile.focus_areas).toEqual(["literacy"]);
    expect(m.profile.hide).toEqual(["inpipeline"]);
    expect(m.profile.state).toBe("FL");
  });
  it("keeps only well-formed pipeline items", () => {
    const m = readMessage({ type: "eto:in-pipeline", items: [{ key: "fdn:1", stage: "Prospect" }, { stage: "x" }, null, "x", { key: "fed:2", closed: true }] });
    expect(m).toEqual({ type: "eto:in-pipeline", items: [{ key: "fdn:1", stage: "Prospect", closed: false }, { key: "fed:2", stage: "", closed: true }] });
  });
  it("reads a send result and never calls an unknown status a success", () => {
    expect(readMessage({ type: "eto:sent", key: "fdn:1", ok: true, status: "saved", stage: "Prospect" }))
      .toEqual({ type: "eto:sent", key: "fdn:1", ok: true, status: "saved", stage: "Prospect", message: "" });
    expect(readMessage({ type: "eto:sent", key: "fdn:1", ok: true, status: "weird" })).toMatchObject({ ok: false, status: "error" });
  });
  it("ignores anything else", () => {
    for (const d of [null, "eto:profile", 5, {}, { type: "gm:send" }, { type: "eto:delete-everything" }]) expect(readMessage(d)).toBeNull();
  });
});

describe("what is sent to the pipeline", () => {
  const base: Entry = {
    key: "x", source: "fed", title: "", url: "", catalog: "", facts: [], side: "", score: 50, tier: "Possible",
    fits: [], cautions: [], also: [], status: [],
  };
  it("a federal grant: the notice, the agency, the award range and the deadline", () => {
    const p = payloadFor({ ...base, key: "fed:355824", title: "Literacy grants", agency: "Department of Education", url: "https://www.grants.gov/x",
      catalog: "ED-26-001", amountLow: 50_000, amountHigh: 250_000, sortClose: new Date(2027, 0, 15).getTime(), fits: ["Mentions literacy"] });
    expect(p).toMatchObject({ source: "federal", funder: "Department of Education", ein: null, url: "https://www.grants.gov/x",
      deadline: "2027-01-15", amount_low: 50_000, amount_high: 250_000, catalog: "ED-26-001", fits: ["Mentions literacy"] });
  });
  it("a foundation: its EIN, website, the website's apply link and quote, and its typical grant", () => {
    const p = payloadFor({ ...base, key: "fdn:591234567", source: "fdn", title: "Sunshine Fund", sortMedian: 5_000, catalog: "EIN 59-1234567",
      rows: [{ label: "Website", href: "https://sunshine.org", linkText: "sunshine.org" },
        { label: "On its website", text: "“Applications are open.”" },
        { label: "Application link", href: "https://sunshine.submittable.com/submit", linkText: "x" }] });
    expect(p).toMatchObject({ source: "foundation", funder: "Sunshine Fund", ein: "591234567", website: "https://sunshine.org",
      url: "https://sunshine.submittable.com/submit", website_note: "“Applications are open.”", amount_low: 5_000, amount_high: 5_000, deadline: null });
  });
  it("hides what is in the pipeline, or was declined, when asked", () => {
    const list = [{ ...base, key: "a" }, { ...base, key: "b" }, { ...base, key: "c" }];
    const pipeline = new Map([["a", { closed: false }], ["b", { closed: true }]]);
    const keys = (h: string[]) => (profileNarrow(list, { ...BLANK, hide: h }, new Date(), pipeline).entries ?? []).map((e) => e.key);
    expect(keys([])).toEqual(["a", "b", "c"]);
    expect(keys(["inpipeline"])).toEqual(["b", "c"]);
    expect(keys(["declined"])).toEqual(["a", "c"]);
  });
});
