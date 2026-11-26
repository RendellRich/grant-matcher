// The local funder directory (grantmatch/funders.py): local governments that get HUD CDBG or HOME money. They are
// funders to ask, not open grant calls, so nothing here is scored, ranked, given a deadline or said to be open to
// nonprofits, and none of it goes near the scorers, the results, the shortlist or the exports.
import { splitList } from "./profile";

export interface Funder {
  id: string;
  name: string;
  level: "County" | "City" | "Other";
  kind: string; // "County government", "HOME consortium"...
  counties: string[]; // names as in counties-ST.json; empty when it couldn't be matched
  area: string; // the same counties in words
  programs: { CDBG?: number; HOME?: number }; // dollars for the fiscal year
  home_consortium?: boolean; // the HOME amount is a consortium's, not this government's alone
  website?: string; // as reported to the Census Bureau; absent when the listing has none
}

/** What meta.json says about the directory. */
export interface FundersMeta {
  states: string[];
  fiscal_year: string;
  census_year: string;
  hud_page: string;
  hud_as_of: string;
  census_page: string;
  census_as_of: string;
}

/** counties-ST.json holds a few names as UTF-8 read as Latin-1 (the n with a tilde in Dona Ana is two characters);
 *  this puts them right and leaves other text alone. */
const readable = (s: string) => s.replace(/\u00c3[\u0080-\u00bf]/g,
  (m) => new TextDecoder().decode(Uint8Array.from(m, (c) => c.charCodeAt(0))));

/** A name for comparing: no case, accents or punctuation, "Saint" as "St" and "Ft" as "Fort". */
const fold = (s: string) => readable(s).normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase()
  .replace(/\bsaint\b/g, "st").replace(/\bft\b/g, "fort").replace(/[^a-z0-9]+/g, " ").trim();

const COUNTY_WORD = / (county|parish|municipio)$/;
const CITY_WORD = / (charter township|township|town|village|borough|city and county|city county|city|municipio)$/;
/** Everyday names for governments the list names another way (both sides as `fold` writes them). */
const ALSO_KNOWN: Record<string, string> = {
  "nashville": "nashville davidson", "lexington": "lexington fayette", "macon": "macon bibb county",
  "houma": "houma terrebonne", "new york city": "new york", "manhattan": "new york", "brooklyn": "new york",
  "queens": "new york", "bronx": "new york", "staten island": "new york",
};

/** The funders near the profile's typed cities and counties, in the list's own order (by name), or null when no place
 *  is typed. A typed county takes every funder in it. A typed city takes the funder of that name and every funder in
 *  a county that has a place of that name, since the county government (and the profile's neighbors) may fund there
 *  too. Same county names as the scorers use (counties-ST.json), but nothing here changes a score. */
export function nearFunders(funders: Funder[], typed: string, counties: Record<string, string[]> | null): Funder[] | null {
  const places = splitList(typed).map(fold).filter(Boolean);
  if (!places.length) return null;
  const names = new Set<string>();
  const wanted = new Set<string>();
  const table = Object.entries(counties ?? {}).map(([c, held]) => [fold(c), held.map(fold)] as const);
  for (const place of places) {
    const countyOnly = COUNTY_WORD.test(place);
    const bare = place.replace(COUNTY_WORD, "");
    names.add(place);
    if (ALSO_KNOWN[place]) names.add(ALSO_KNOWN[place]);
    for (const [county, held] of table) {
      if (county === bare || (!countyOnly && held.includes(place))) wanted.add(county);
    }
  }
  return funders.filter((f) => {
    const name = fold(f.name);
    return names.has(name) || names.has(name.replace(CITY_WORD, "")) || f.counties.some((c) => wanted.has(fold(c)));
  });
}

const dollars = (v: number) => `$${v.toLocaleString("en-US")}`;

/** The HUD amounts in words: "CDBG $1,981,290, HOME $623,461". */
export function programsText(f: Funder): string {
  const out: string[] = [];
  if (f.programs.CDBG) out.push(`CDBG ${dollars(f.programs.CDBG)}`);
  if (f.programs.HOME) out.push(`HOME ${dollars(f.programs.HOME)}${f.home_consortium ? " (for a HOME consortium of local governments)" : ""}`);
  return out.join(", ");
}

/** The facts under a funder's name. The county is left out when the name already says it. */
export function funderFacts(f: Funder, fiscalYear: string): string[] {
  const area = !f.area ? "County not matched" : f.area === f.name ? "" : f.area;
  return [f.kind, area, `HUD FY ${fiscalYear}: ${programsText(f)}`].filter(Boolean);
}

/** The line that says what the list below holds. */
export function fundersStatus(total: number, near: Funder[] | null, all: boolean, stateName: string): string {
  const n = (v: number) => v.toLocaleString("en-US");
  const listed = `${n(total)} listed for ${stateName}`;
  if (all) return total === 1 ? `Showing the one funder listed for ${stateName}.` : `Showing all ${listed}, by name.`;
  if (near === null) return `${listed}. Add your cities or counties under Your organization to see the ones near you.`;
  if (!near.length) return `None of the ${listed} matches your cities or counties by name or county.`;
  return `Showing ${n(near.length)} of ${listed} that ${near.length === 1 ? "matches" : "match"} your cities or counties, by name.`;
}
