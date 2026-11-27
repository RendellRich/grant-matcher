// A profile in a state with no state catalog sees a plain note where the state tab would be (grantmatch/states.py
// publishes each state's status in meta.json), and a state with a catalog sees its tab and no note.
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { callsTally, grantsPhrase, localTally, noCatalogNote, programsFile, shownSources, type Meta } from "../src/data";
import { callState, programState } from "../src/entries";
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
    expect(note("AL", al)).toBe("No Alabama state catalog yet. What was checked for Alabama didn't give a grant list that can be read in yet. Federal grants cover Alabama.");
  });

  it("claims nothing about a state the research couldn't check", () => {
    const ks = note("KS")!;
    expect(ks).toBe("No Kansas state catalog yet. Kansas state grants aren't read in yet. Federal grants and foundations cover Kansas.");
    expect(ks).not.toMatch(/\bfound\b|no single|no current|only as/i);
  });

  it("says when rules, terms or a refusal to scripts keep a state's pages out", () => {
    const blocked: Meta = { ...meta, catalogs: { AL: { status: "blocked", source: "adeca.alabama.gov" } } };
    expect(note("AL", blocked)).toBe("No Alabama state catalog yet. Key grant sites for Alabama can't be used here: their rules or terms don't allow it, or they turn automated readers away, so Alabama state grants aren't read in. Federal grants cover Alabama.");
  });

  it("doesn't call the District of Columbia a state", () => {
    expect(note("DC")).toBe("No District of Columbia catalog yet. What was checked for the District of Columbia didn't give a grant list that can be read in yet. Federal grants and foundations cover the District of Columbia.");
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
    expect(app).toContain('hasProgs ? ` and ${grantsPhrase(st, stName)}` : ""');
  });
});

// `listed` calls that name nonprofits, `unstated` that don't say who may apply, `closed` that leave nonprofits out.
const calls = (listed: number, unstated = 0, closed = 0) => [
  ...Array.from({ length: listed }, () => ({ nonprofit_eligible: true, applicant_types: "Non-Profit" })),
  ...Array.from({ length: unstated }, () => ({ nonprofit_eligible: true, applicant_types: "Not stated on the state's listing; read the notice" })),
  ...Array.from({ length: closed }, () => ({ nonprofit_eligible: false, applicant_types: "State governments" })),
];

describe("the line above a state's open calls", () => {
  it("counts calls that don't say who may apply apart from the ones that list nonprofits", () => {
    const source = "West Virginia grants.wv.gov list of available grants";
    expect(callsTally("WV", "West Virginia", calls(3, 1, 3), { source }, "Nov 25")).toBe(
      "3 of 7 open West Virginia state grant and loan calls list nonprofits as eligible; 1 more doesn't say who may apply. From the West Virginia grants.wv.gov list of available grants, updated Nov 25. County and city programs aren't covered for West Virginia yet.");
    // a paused list (grantmatch/states.py) says so, with the date it was read
    expect(callsTally("IL", "Illinois", calls(3), { source: "Illinois Catalog of State Financial Assistance", paused: true }, "Nov 25")).toContain(
      "updated Nov 25. Reading the Illinois state list is paused until the state gives its OK, so these state calls are as read on Nov 25. Newer calls aren't here, and a call may have changed or closed since. County");
    expect(callsTally("IL", "Illinois", calls(3), { paused: true }, "")).toContain("paused until the state gives its OK. Newer calls aren't here");
    expect(callsTally("OH", "Ohio", calls(3), { source: "Ohio" }, "Nov 25")).not.toContain("paused");
    expect(callsTally("IA", "Iowa", calls(0, 2), undefined, "")).toBe(
      "0 of 2 open Iowa state grant and loan calls list nonprofits as eligible; 2 more don't say who may apply. County and city programs aren't covered for Iowa yet.");
    expect(callsTally("IA", "Iowa", calls(1, 1), undefined, "Nov 25")).toContain("say who may apply. Updated Nov 25. County");
  });

  it("keeps its wording for a list that says who may apply", () => {
    expect(callsTally("OH", "Ohio", calls(12, 0, 3), { source: "Ohio Grants Partnership" }, "Nov 25")).toBe(
      "12 of 15 open Ohio state grant and loan calls list nonprofits as eligible, from the Ohio Grants Partnership, updated Nov 25. County and city programs aren't covered for Ohio yet.");
  });

  it("says when coverage is two agencies, not the state", () => {
    const source = "Minnesota Department of Health and Office of Justice Programs pages only (two agencies, not a statewide list)";
    expect(callsTally("MN", "Minnesota", calls(7, 0, 6), { source }, "")).toContain("(two agencies, not a statewide list)");
  });

  it("labels every one-agency or short list as partial wherever the page names the state", () => {
    const source = "Maryland Department of Commerce State Grants table only (a short list, not a statewide list)";
    expect(callsTally("MD", "Maryland", calls(0, 4), { source, who_listed: false }, "")).toContain("(a short list, not a statewide list)");
    const app = readFileSync(new URL("../src/app.tsx", import.meta.url), "utf8");
    const about = readFileSync(new URL("../src/coverage.tsx", import.meta.url), "utf8");
    const partial: [string, string, string][] = [
      ["AR", "Arkansas", "Arkansas data from the Arkansas Arts Council's art grants page only."],
      ["MD", "Maryland", "Maryland data from the State Grants table on the Department of Commerce's nonprofit page only, a short list."],
      ["ND", "North Dakota", "North Dakota data from the Council on the Arts' grant pages only."],
      ["WY", "Wyoming", "Wyoming data from the Wyoming Arts Council's grant pages only."],
      ["TN", "Tennessee", "Tennessee data from the Tennessee Arts Commission's grant pages only."],
      ["MT", "Montana", "Montana data from the Montana Arts Council's grant pages only."],
      ["KY", "Kentucky", "Kentucky data from the Kentucky Arts Council's grant pages only."],
    ];
    for (const [code, name, footer] of partial) {
      const note = app.slice(app.indexOf(`{state === "${code}" ? (`));
      expect(note.slice(0, 400), code).toContain(`<h3>For ${name} state grants</h3>`);
      expect(note.slice(0, 500), code).toContain("This isn't a statewide list. Only the ");
      expect(app, code).toContain(footer);
      expect(about, code).toMatch(new RegExp(`${name} \\((?:arts council only|a short list)\\)`));
    }
  });

  it("doesn't call the District a state or say its list names nonprofits", () => {
    const t = callsTally("DC", "District of Columbia", calls(0, 10), { source: "District Grants Clearinghouse (DC.gov, CC BY 3.0)", who_listed: false }, "Nov 25");
    expect(t).toBe("10 of 10 open District of Columbia grant calls are shown, from the District Grants Clearinghouse (DC.gov, CC BY 3.0), updated Nov 25. The list doesn't say who may apply, so read each notice.");
    expect(grantsPhrase("DC", "District of Columbia")).toBe("District of Columbia grants");
    expect(grantsPhrase("NY", "New York")).toBe("New York state grants");
  });
});

describe("the state an exported call came from", () => {
  it("is read off the key for every state with a list, with no list of states to keep", () => {
    expect(callState("fl:ny-agm01-x")).toEqual({ code: "NY", name: "New York" });
    expect(callState("fl:dc-x")).toEqual({ code: "DC", name: "District of Columbia" });
    expect(callState("fl:mn-health-x")?.name).toBe("Minnesota");
    expect(callState("fl:wv-72")?.name).toBe("West Virginia");
    expect(callState("fl:nj-x")?.name).toBe("New Jersey");
    expect(callState("fl:ca-123")?.name).toBe("California");
  });

  it("leaves Florida's catalog and hand-kept programs as they were", () => {
    for (const key of ["fl:fl-86722", "fl:local-sample-county-kids", "fl:local-wa-x", "fed:1", "fdn:2"]) {
      expect(callState(key)).toBeNull();
    }
  });
});

describe("a state with county and city programs but no state catalog", () => {
  const local: Meta = {
    states: ["TX"],
    programs: { TX: { file: "programs-TX", source: "county and city programs entered by hand", local_only: true, local: true } },
    catalogs: { TX: { status: "blocked", source: "txsmartbuy.gov" } },
  };

  it("keeps its tab and says above it that the tab holds hand-kept county and city programs only", () => {
    expect(programsFile(local, "TX")).toBe("programs-TX");
    expect(noCatalogNote(local, "TX", "Texas")).toBe(
      "No Texas state catalog yet. Key grant sites for Texas can't be used here: their rules or terms don't allow it, or they turn automated readers away, so Texas state grants aren't read in. The Texas local programs tab has county and city programs only, entered by hand from each program's own page: a partial list, not every county or city. Federal grants and foundations cover Texas.");
  });

  it("counts them as county and city programs, not state calls", () => {
    expect(localTally("Texas", 8)).toBe(
      "8 county and city programs in Texas, entered by hand from each program's own page. This is partial coverage, with no Texas state catalog; each card shows when it was checked.");
    expect(localTally("Nevada", 1)).toContain("1 county and city program in Nevada");
  });

  it("names the tab local and leaves the state-call wording out", () => {
    const app = readFileSync(new URL("../src/app.tsx", import.meta.url), "utf8");
    expect(app).toContain("fl: localOnly ? [`${state} local programs`, `${state} local programs`, `${state} local program`]");
    expect(app).toContain("localOnly ? localTally(stName, all.length, Boolean(info?.local)) : callsTally(st, stName, all, info, updated)");
  });
});

describe("hand-kept state programs in a state with no state catalog", () => {
  const meta: Meta = {
    states: ["CT"],
    programs: { CT: { file: "programs-CT", source: "state programs entered by hand", local_only: true, local: false } },
    catalogs: { CT: { status: "html", source: "portal.ct.gov" } },
  };

  it("are called state programs and not a statewide list", () => {
    const note = noCatalogNote(meta, "CT", "Connecticut")!;
    expect(note).toContain("The Connecticut programs tab has state programs only");
    expect(note).not.toContain("county");
    expect(localTally("Connecticut", 2, false)).toContain("2 state programs in Connecticut, entered by hand");
  });

  it("say so in a blocked state too (Massachusetts), after why there is no catalog", () => {
    const ma: Meta = {
      states: ["MA"],
      programs: { MA: { file: "programs-MA", source: "state programs entered by hand", local_only: true, local: false } },
      catalogs: { MA: { status: "blocked", source: "mass.gov" } },
    };
    const note = noCatalogNote(ma, "MA", "Massachusetts")!;
    expect(note).toContain("Key grant sites for Massachusetts can't be used here");
    expect(note).toContain("The Massachusetts programs tab has state programs only");
  });
});

describe("hand-kept programs beside a state's open calls", () => {
  const hand = (level: string, k: number) => Array.from({ length: k }, () => ({ nonprofit_eligible: true, applicant_types: "Nonprofits", level }));

  it("are counted apart from the state's list, and county coverage is said to be partial", () => {
    expect(callsTally("CA", "California", [...calls(2), ...hand("County", 5), ...hand("City", 1)], { source: "California Grants Portal" }, "")).toBe(
      "2 of 2 open California state grant and loan calls list nonprofits as eligible, from the California Grants Portal. Plus 6 programs entered by hand from their own pages. County and city programs are only partly covered for California: 6 of those are county or city programs.");
  });

  it("don't claim county coverage when they are all state calls", () => {
    expect(callsTally("OH", "Ohio", [...calls(3), ...hand("State", 1)], undefined, "")).toBe(
      "3 of 3 open Ohio state grant and loan calls list nonprofits as eligible. Plus 1 program entered by hand from its own page. County and city programs aren't covered for Ohio yet.");
  });
});

describe("a hand-kept program on an export", () => {
  it("is labelled with its own state, read off the key", () => {
    expect(programState("fl:local-tx-houston-x")).toBe("Texas");
    expect(programState("fl:local-ny-nyc-x")).toBe("New York");
    expect(programState("fl:local-wa-x")).toBe("Washington");
    expect(programState("fl:local-manatee-childrens")).toBe("Florida");
    expect(programState("fl:48.001")).toBe("Florida");
  });
});
