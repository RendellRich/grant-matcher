// The result filters for state and county. They narrow or switch what is shown and never change a score.
// States come from meta.json and counties from counties-ST.json, so new data shows up without code changes.
import type { Meta } from "./data";
import { fold, readable } from "./funders";
import { STATE_NAMES } from "./profile";
import type { FloridaRec, FoundationRec } from "./score";

const NAMES: Record<string, string> = STATE_NAMES;

/** The other states with foundation or program data, by name. */
export function stateChoices(meta: Meta | null, home: string): string[] {
  const codes = new Set([...(meta?.states ?? []), ...Object.keys(meta?.programs ?? {}), ...(meta?.florida ? ["FL"] : [])]);
  return [...codes].filter((c) => c !== home && c in NAMES).sort((a, b) => NAMES[a].localeCompare(NAMES[b]));
}

/** The county names of counties-ST.json as [value, shown name], in order. */
export const countyChoices = (counties: Record<string, string[]> | null | undefined): [string, string][] =>
  Object.keys(counties ?? {}).map((c): [string, string] => [c, readable(c)]).sort((a, b) => a[1].localeCompare(b[1]));

export const countyWord = (state: string) => (state === "LA" ? "parish" : "county");

/** "Manatee County", "Acadia Parish"; Alaska's areas and the District go by their own names. */
export const countyPhrase = (state: string, county: string) =>
  state === "AK" || state === "DC" ? readable(county) : `${readable(county)} ${state === "LA" ? "Parish" : "County"}`;

/** Whether money limited to `places` (grantmatch/local.py writes them) can be spent in this county. A list that
 *  names whole counties is matched on those; one that names only towns, on the county's towns. */
export function servesCounty(places: string[], county: string, towns: string[]): boolean {
  const named = places.map(fold);
  const k = fold(county);
  if (named.includes(`${k} county`)) return true;
  if (named.some((p) => p.endsWith(" county"))) return false;
  const inside = new Set([k, ...towns.map(fold)]);
  return named.some((p) => inside.has(p));
}

/** Keys of the programs limited to places outside the county. A program that names no place stays. */
export const programsOutside = (records: FloridaRec[], county: string, towns: string[]): Set<string> =>
  new Set(records.filter((r) => r.places?.length && !servesCounty(r.places, county, towns)).map((r) => `fl:${r.id}`));

/** A state's foundations against one of its counties. `outside` are company foundations whose own page limits
 *  grants elsewhere. `unrecorded` have nothing on file in the county (address, listed grant, funded town or
 *  company program). That is not "doesn't give there": returns don't say which counties a foundation serves. */
export function foundationsByCounty(records: FoundationRec[], state: string, county: string, towns: string[]) {
  const inside = new Set(towns.map(fold));
  const there = (city: string | undefined) => inside.has(fold(city ?? ""));
  const outside = new Set<string>();
  const unrecorded = new Set<string>();
  for (const r of records) {
    const key = `fdn:${r.ein}`;
    const limit = r._corp?.places;
    if (limit?.length) {
      if (!servesCounty(limit, county, towns)) outside.add(key);
      continue;
    }
    const onRecord = (r.state === state && there(r.city))
      || r.sample_grants.some((g) => g.state === state && there(g.city))
      || Object.keys(r.hist?.pl ?? {}).some(there);
    if (!onRecord) unrecorded.add(key);
  }
  return { outside, unrecorded };
}
