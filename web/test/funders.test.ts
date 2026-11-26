// "Local funders to ask" (src/funders.ts, src/funderlist.tsx): which funders show for a profile's places, how each is
// described, and that none of it reads like a grant. Every funder here is invented for the test.
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { funderFacts, fundersStatus, nearFunders, programsText, type Funder, type FundersMeta } from "../src/funders";
import { FUNDERS_TITLE, FUNDERS_WARNING, FundersView, type FundersViewProps } from "../src/funderlist";

const counties = {
  "Sample": ["Rivertown", "Palm Sample", "Katy"],
  "Other": ["Katy", "Elsewhere"],
  "Orange": ["Citrus Grove"],
  "Inland": ["Orange"],
  "St. Test": ["Saint Cloudy"],
};
const funder = (over: Partial<Funder> & { name: string }): Funder => ({
  id: over.name, level: "City", kind: "City government", counties: [], area: "", programs: { CDBG: 100 }, ...over,
});
const rows: Funder[] = [
  funder({ name: "Elsewhere Township", level: "Other", kind: "Township government", counties: ["Other"], area: "Other County" }),
  funder({ name: "Lonely", counties: [] }),
  funder({ name: "Orange County", level: "County", kind: "County government", counties: ["Orange"], area: "Orange County" }),
  funder({ name: "Rivertown", counties: ["Sample"], area: "Sample County", website: "http://rivertown.example.gov" }),
  funder({ name: "Sample County", level: "County", kind: "County government", counties: ["Sample"], area: "Sample County",
    programs: { CDBG: 1981290, HOME: 623461 }, home_consortium: true }),
  funder({ name: "St. Test County", level: "County", kind: "County government", counties: ["St. Test"], area: "St. Test County" }),
];
const names = (typed: string) => nearFunders(rows, typed, counties)?.map((f) => f.name) ?? null;

describe("funders near the profile's places", () => {
  it("is not decided when no place is typed", () => {
    expect(names("")).toBeNull();
    expect(names(" , ")).toBeNull();
  });

  it("takes everything in a typed county, with or without the word county", () => {
    expect(names("Sample")).toEqual(["Rivertown", "Sample County"]);
    expect(names("sample county")).toEqual(["Rivertown", "Sample County"]);
  });

  it("takes a typed city's own government and the others in its counties", () => {
    expect(names("rivertown")).toEqual(["Rivertown", "Sample County"]);
    expect(names("Palm Sample")).toEqual(["Rivertown", "Sample County"]);
    expect(names("Katy")).toEqual(["Elsewhere Township", "Rivertown", "Sample County"]);
    expect(names("Elsewhere")).toEqual(["Elsewhere Township"]);
  });

  it("finds a government by name when no county is matched", () => {
    expect(names("Lonely")).toEqual(["Lonely"]);
    expect(names("Lonely City")).toEqual([]);
  });

  it("keeps a county word to the county, and reads Saint as St", () => {
    expect(names("Orange")).toEqual(["Orange County"]); // the county of that name; no funder is in Inland
    expect(names("Citrus Grove")).toEqual(["Orange County"]);
    expect(names("Saint Test")).toEqual(["St. Test County"]);
    expect(names("St Cloudy")).toEqual(["St. Test County"]);
    expect(names("Inland County")).toEqual([]);
  });

  it("works from names alone before the county list loads", () => {
    expect(nearFunders(rows, "Rivertown", null)!.map((f) => f.name)).toEqual(["Rivertown"]);
  });
});

describe("what each funder says", () => {
  it("gives the kind, county and HUD amounts with their year", () => {
    expect(programsText(rows[4])).toBe("CDBG $1,981,290, HOME $623,461 (for a HOME consortium of local governments)");
    expect(funderFacts(rows[4], "2026")).toEqual(["County government", "HUD FY 2026: CDBG $1,981,290, HOME $623,461 (for a HOME consortium of local governments)"]);
    expect(funderFacts(rows[3], "2026")).toEqual(["City government", "Sample County", "HUD FY 2026: CDBG $100"]);
    expect(funderFacts(rows[1], "2026")[1]).toBe("County not matched");
  });

  it("says how many are shown", () => {
    expect(fundersStatus(88, null, false, "Florida")).toBe("88 listed for Florida. Add your cities or counties under Your organization to see the ones near you.");
    expect(fundersStatus(88, [], false, "Florida")).toBe("None of the 88 listed for Florida matches your cities or counties by name or county.");
    expect(fundersStatus(88, [rows[0]], false, "Florida")).toBe("Showing 1 of 88 listed for Florida that matches your cities or counties, by name.");
    expect(fundersStatus(1234, [rows[0], rows[1]], false, "Texas")).toBe("Showing 2 of 1,234 listed for Texas that match your cities or counties, by name.");
    expect(fundersStatus(88, null, true, "Florida")).toBe("Showing all 88 listed for Florida, by name.");
    expect(fundersStatus(1, null, true, "Vermont")).toBe("Showing the one funder listed for Vermont.");
  });
});

// The view has no hooks, so its tree can be walked without a browser.
type Node = { type: unknown; props: Record<string, unknown> };
function walk(node: unknown, seen: Node[]): string {
  if (node == null || typeof node === "boolean") return "";
  if (Array.isArray(node)) return node.map((c) => walk(c, seen)).join("");
  if (typeof node !== "object") return String(node);
  const v = node as Node;
  if (typeof v.type === "function") return walk((v.type as (p: unknown) => unknown)(v.props), seen);
  seen.push(v);
  return walk(v.props.children, seen);
}
const info: FundersMeta = {
  states: ["FL"], fiscal_year: "2026", census_year: "2026", hud_page: "https://hud.example/page", hud_as_of: "2026-08-03",
  census_page: "https://census.example/page", census_as_of: "2026-08-13",
};
function view(over: Partial<FundersViewProps> = {}) {
  const seen: Node[] = [];
  const text = walk(FundersView({ rows, near: null, all: true, onAll: () => undefined, state: "FL", stateName: "Florida", info, ...over }), seen)
    .replace(/\s+/g, " ");
  return { text, tags: (tag: string) => seen.filter((n) => n.type === tag), seen };
}

describe("the section", () => {
  it("says first that these are funders and not open grant calls", () => {
    expect(FUNDERS_TITLE).toBe("Local funders to ask");
    const { text } = view();
    expect(text.indexOf(FUNDERS_WARNING)).toBe(0);
    expect(text).toContain("That doesn't mean it funds nonprofits now: CDBG money for public services is limited and varies from place to place.");
    expect(text).toContain("They aren't scored, ranked or counted in your matches.");
  });

  it("never reads like a grant", () => {
    const { text, seen } = view();
    expect(text).not.toMatch(/open to nonprofits|deadline|apply by|closes|strong match|possible match|score \d|out of 100/i);
    expect(seen.map((n) => String(n.props.class ?? ""))).not.toEqual(expect.arrayContaining([expect.stringMatching(/\b(score|tier|rule|mark-btn|entry-actions)\b/)]));
  });

  it("links a government's website only where there is one, and names it for screen readers", () => {
    const { text, tags } = view();
    const sites = tags("a").filter((a) => a.props.class === "funder-site");
    expect(sites.map((a) => a.props.href)).toEqual(["http://rivertown.example.gov"]);
    expect(sites[0].props.rel).toBe("noopener noreferrer");
    expect(walk(sites[0], []).replace(/\s+/g, " ")).toBe("Website for Rivertown (opens in a new tab)");
    expect(text.match(/No website listed\./g)).toHaveLength(rows.length - 1);
    expect(tags("h3").map((h) => walk(h, []))).toEqual(rows.map((f) => f.name));
  });

  it("names its sources with their dates and says websites aren't checked", () => {
    const { text, tags } = view();
    expect(tags("a").map((a) => a.props.href)).toEqual(expect.arrayContaining([info.hud_page, info.census_page]));
    expect(text).toContain("(as of August 3, 2026)");
    expect(text).toContain("It isn't checked here");
    expect(text).toContain("Places not listed may get CDBG money through Florida's own program, which isn't listed here.");
    expect(view({ state: "DC", stateName: "District of Columbia" }).text).not.toContain("own program");
  });

  it("shows the near ones, with a button for the whole state", () => {
    let asked: boolean | null = null;
    const near = view({ near: [rows[3]], all: false, onAll: (v) => { asked = v; } });
    expect(near.tags("h3").map((h) => walk(h, []))).toEqual(["Rivertown"]);
    const button = near.tags("button")[0];
    expect(button.props.type).toBe("button");
    expect(walk(button, [])).toBe("Show all 6 in Florida");
    (button.props.onClick as () => void)();
    expect(asked).toBe(true);
    expect(walk(view({ near: [rows[3]], all: true }).tags("button")[0], [])).toBe("Show only the ones near your places");
    const none = view({ near: null, all: false });
    expect(none.tags("h3")).toHaveLength(0);
    expect(none.tags("ul")).toHaveLength(0);
    expect(walk(view({ near: null, all: true }).tags("button")[0], [])).toBe("Hide the full list");
    expect(view({ near: rows, all: false }).tags("button")).toHaveLength(0);
    expect(near.tags("p").some((p) => p.props.role === "status")).toBe(true);
  });

  it("lets a long list be skipped", () => {
    const many = Array.from({ length: 11 }, (_, i) => funder({ name: `Town ${i}` }));
    const long = view({ rows: many });
    expect(long.tags("a").map((a) => a.props.href)).toContain("#funders-source");
    expect(long.tags("p").some((p) => p.props.id === "funders-source" && p.props.tabIndex === -1)).toBe(true);
    expect(view().tags("a").map((a) => a.props.href)).not.toContain("#funders-source");
  });
});

describe("where it sits", () => {
  const read = (path: string) => readFileSync(new URL(`../src/${path}`, import.meta.url), "utf8");

  it("is below the result tabs, not inside them, and only for states with a file", () => {
    const app = read("app.tsx");
    expect(app.match(/<Funders /g)).toHaveLength(1);
    expect(app).toContain("meta?.funders?.states.includes(st)");
    expect(app.indexOf("<Funders ")).toBeGreaterThan(app.indexOf('role="tabpanel"'));
  });

  it("is a disclosure with its heading in the summary, which a keyboard opens", () => {
    const src = read("funderlist.tsx");
    expect(src).toMatch(/<details class="ready funders"[^>]*onToggle/);
    expect(src).toContain("<summary><h2>{FUNDERS_TITLE}</h2></summary>");
  });

  it("is never read by the ranking, the shortlist or the exports", () => {
    for (const path of ["score.ts", "rank.ts", "entries.ts", "exports.ts", "summary.ts", "shortlist.ts"]) {
      expect(read(path), path).not.toMatch(/from "\.\/funder(s|list)"|loadFunders|funders-/);
    }
  });
});
