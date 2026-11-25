// A profile in a state with no state catalog sees a plain note where the state tab would be (grantmatch/states.py
// publishes each state's status in meta.json), and a state with a catalog sees its tab and no note.
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { noCatalogNote, programsFile, shownSources, type Meta } from "../src/data";
import { STATE_NAMES } from "../src/profile";

const meta: Meta = {
  states: ["FL", "KS", "WV", "NJ", "DC"],
  programs: {
    WV: { file: "programs-WV", source: "West Virginia grants.wv.gov list of available grants" },
    NJ: { file: "programs-NJ", source: "New Jersey Treasury list of state grant opportunities" },
  },
  catalogs: {
    FL: { status: "built", source: "Florida Catalog of State Financial Assistance" },
    WV: { status: "built", source: "West Virginia grants.wv.gov list of available grants" },
    NJ: { status: "built", source: "New Jersey Treasury list of state grant opportunities" },
    CA: { status: "built", source: "California Grants Portal" },
    KS: { status: "unchecked", source: "grants.ks.gov and the KS Infrastructure Hub (blocked to scripts)" },
    MD: { status: "none", source: "grants.maryland.gov list, abandoned since September 2023" },
    DC: { status: "html", source: "District Grants Clearinghouse (Serve DC)" },
    HI: { status: "decide", source: "HANDS" },
    PA: { status: "decide", source: "pa.gov" },
    XX: { status: "next", source: "x" },
  },
};
const note = (st: string, m: Meta | null = meta) => noCatalogNote(m, st, STATE_NAMES[st] ?? st);

describe("a state with no catalog", () => {
  it("says so in plain words and names what still covers it", () => {
    expect(note("MD")).toBe("No Maryland state catalog yet. No current public list of Maryland state grants was found. Federal grants cover Maryland.");
    expect(note("HI")).toBe("No Hawaii state catalog yet. Hawaii has a machine-readable grant list that isn't read in yet. Federal grants cover Hawaii.");
    expect(note("PA")).toContain("Pennsylvania has a machine-readable grant list that isn't read in yet.");
    expect(noCatalogNote(meta, "XX", "Somewhere")).toContain("A source for Somewhere state grants is being looked at.");
    const al: Meta = { ...meta, catalogs: { AL: { status: "html", source: "ADECA" } } };
    expect(note("AL", al)).toBe("No Alabama state catalog yet. The grant pages checked for Alabama are web pages or a dashboard, not a data file, so they aren't read in yet. Federal grants cover Alabama.");
  });

  it("claims nothing about a state the research couldn't check", () => {
    const ks = note("KS")!;
    expect(ks).toBe("No Kansas state catalog yet. Kansas state grants aren't read in yet. Federal grants and foundations cover Kansas.");
    expect(ks).not.toMatch(/\bfound\b|no single|no current|only as/i);
  });

  it("doesn't call the District of Columbia a state", () => {
    expect(note("DC")).toBe("No District of Columbia catalog yet. The grant pages checked for the District of Columbia are web pages or a dashboard, not a data file, so they aren't read in yet. Federal grants and foundations cover the District of Columbia.");
    const none: Meta = { ...meta, catalogs: { DC: { status: "none", source: "x" } } };
    expect(note("DC", none)).toBe("No District of Columbia catalog yet. No current public list of grants from the District of Columbia was found. Federal grants and foundations cover the District of Columbia.");
    const unchecked: Meta = { ...meta, catalogs: { DC: { status: "unchecked", source: "x" } } };
    expect(note("DC", unchecked)).toBe("No District of Columbia catalog yet. Grants from the District of Columbia aren't read in yet. Federal grants and foundations cover the District of Columbia.");
  });

  it("still reads when the data predates the registry or a built state's file is missing", () => {
    const old: Meta = { states: ["KS"], programs: { CA: { file: "programs-CA", source: "California Grants Portal" } } };
    expect(note("KS", old)).toBe("No Kansas state catalog yet. Federal grants and foundations cover Kansas.");
    // a built state whose file didn't come through doesn't claim there is no catalog
    expect(note("CA")).toBe("California state grants aren't available right now. Federal grants cover California.");
    expect(note("PR")).toBe("No Puerto Rico catalog yet. Federal grants cover Puerto Rico.");
  });
});

describe("a state with a catalog", () => {
  it("gets its tab and no note, Florida included", () => {
    for (const st of ["WV", "NJ", "FL"]) {
      expect(note(st), st).toBeNull();
      expect(programsFile(meta, st), st).not.toBeNull();
    }
  });

  it("gets no note while the data's list of states is loading or failed to load", () => {
    expect(note("KS", null)).toBeNull();
    expect(note("KS", { states: [] })).toBeNull();
  });
});

describe("the result tabs", () => {
  it("drop the state tab for a state without programs, even while a preview from the last state is showing", () => {
    expect(shownSources(["fed", "fdn", "fl"], false)).toEqual(["fed", "fdn"]);
    expect(shownSources(["fl", "fdn", "fed"], true)).toEqual(["fl", "fdn", "fed"]);
  });
});

describe("the page", () => {
  const app = readFileSync(new URL("../src/app.tsx", import.meta.url), "utf8");

  it("shows the note as a plain paragraph above the result tabs, not as an empty tab", () => {
    const at = app.indexOf('<p class="note" id="no-catalog">{noCatalog}</p>');
    expect(at).toBeGreaterThan(0);
    expect(app.indexOf('role="tablist"', at)).toBeGreaterThan(at);
    // the state tab exists only when the state has a programs file
    expect(app).toContain('if (hasProgs && applied.funder_types.includes("florida")) lists.fl = flEntries;');
    expect(app).toContain("const keys = shownSources(pv ? (Object.keys(pv.counts) as SourceKey[]) : (Object.keys(lists) as SourceKey[]), hasProgs);");
  });

  it("names the state's source in the lede when there is one", () => {
    expect(app).toContain('hasProgs ? ` and ${stName} state grants` : ""');
  });
});
