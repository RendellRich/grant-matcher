// Loads the files grantmatch/export_web.py writes. The small public ones (meta, examples, coverage, counties, the
// local funder directory) come with the site; the grant data comes from the private bucket through links the search
// gate sends.
import type { FileLink } from "./access";
import type { Funder, FundersMeta } from "./funders";
import { ELIGIBILITY_UNSTATED } from "./score";
import { decodeF16, type VectorSet } from "./vectors";

const BASE = `${import.meta.env.BASE_URL}data/`;

export interface Source<T> {
  records: T[];
  vecs: VectorSet;
  fetchedAt: string;
  fiscalYear?: string;
}

export interface Example {
  label: string;
  org_type?: string;
  mission: string;
  keywords: string;
  categories: string[];
  state: string;
  cities: string;
  vector: number[];
}

export interface Meta {
  states: string[];
  federal?: string;
  florida?: string;
  coverage?: boolean;
  /** States besides Florida with their own programs file: its name, its source and when it was fetched.
   *  who_listed is false when the state's list never says who may apply. local_only is true for a state with no
   *  state catalog whose file holds only hand-kept county and city programs; local is true when any state's file
   *  holds some of those. paused is true while reading that state's list is paused (grantmatch/states.py). */
  programs?: Record<string, { file: string; source: string; updated?: string; who_listed?: boolean; local_only?: boolean; local?: boolean; paused?: boolean }>;
  /** Every state's catalog status from grantmatch/states.py: built, next, decide, html, blocked, none or unchecked. */
  catalogs?: Record<string, { status: string; source: string }>;
  /** The local funder directory (funders.ts): which states have a funders-ST.json file, and its sources. */
  funders?: FundersMeta;
}

/** grantmatch/coverage.py: registered foundations against what the state files hold. */
export interface Coverage {
  made_at: string;
  filing_years: number[];
  national: {
    private: { registered: number; efiled: number; listed: number; listed_share: number | null };
    community: { registered: number; efiled: number; listed: number };
    states_with_data: number;
  };
  states: {
    state: string;
    private: { registered: number; efiled: number; listed: number; listed_share: number | null; giving_here: number };
    community: { registered: number; efiled: number; listed: number; giving_here: number };
  }[];
}

async function json<T>(name: string): Promise<T> {
  const r = await fetch(BASE + name);
  if (!r.ok) throw new Error(`${name}: ${r.status}`);
  return r.json() as Promise<T>;
}

/** Reads a data file through the browser's cache: the bucket's links last minutes, the cached copy until the
 *  data changes (the version is the file's tag in the bucket). Older versions of the same file are dropped. */
async function cachedBytes(name: string, version: string, url: string): Promise<ArrayBuffer> {
  const key = `https://gm-data.invalid/${name}?v=${encodeURIComponent(version)}`;
  let cache: Cache | null = null;
  try { cache = await caches.open("gm-data"); } catch { /* no Cache Storage (an old browser or a private window) */ }
  const hit = await cache?.match(key).catch(() => undefined);
  if (hit) return hit.arrayBuffer();
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${name}: ${r.status}`);
  const buf = await r.arrayBuffer();
  try {
    if (cache) {
      for (const old of await cache.keys()) if (old.url.startsWith(`https://gm-data.invalid/${name}?`) && old.url !== key) await cache.delete(old);
      await cache.put(key, new Response(buf.slice(0)));
    }
  } catch { /* storage full: it is fetched again next time */ }
  return buf;
}

function unpack<T>(bytes: Uint8Array<ArrayBuffer>): Promise<T> {
  if (bytes[0] === 0x1f && bytes[1] === 0x8b) {
    const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream("gzip"));
    return new Response(stream).text().then((s) => JSON.parse(s) as T);
  }
  return Promise.resolve(JSON.parse(new TextDecoder().decode(bytes)) as T);
}

/** A data file the search gate sent a link for (access.ts). */
export async function loadLinked<T>(link: FileLink): Promise<Source<T>> {
  const [jv, fv] = link.version.split("|");
  const [jsonBuf, f16] = await Promise.all([
    cachedBytes(`${link.name}.json.gz`, jv ?? link.version, link.json),
    cachedBytes(`${link.name}.f16`, fv ?? link.version, link.f16),
  ]);
  const payload = await unpack<{ records: T[]; vec_ids: string[]; dim: number; fetched_at?: string; fiscal_year?: string }>(new Uint8Array(jsonBuf));
  return {
    records: payload.records,
    vecs: decodeF16(f16, payload.vec_ids, payload.dim),
    fetchedAt: payload.fetched_at ?? "",
    fiscalYear: payload.fiscal_year,
  };
}

export const loadMeta = () => json<Meta>("meta.json");
export const loadCoverage = () => json<Coverage>("coverage.json");
export const loadExamples = () => json<Record<string, Example>>("examples.json");
/** The file holding a state's programs, or null when the state has none. Florida's keeps its own name. */
export const programsFile = (meta: Meta | null, state: string) => (state === "FL" ? "florida" : meta?.programs?.[state]?.file ?? null);
/** What a profile in a state with no state catalog sees above the tabs, or null when the state has one (or the
 *  data's list of states hasn't loaded). Plain words: what is missing, why, and what still covers it, including a
 *  tab of hand-kept county and city programs when there is one. */
export function noCatalogNote(meta: Meta | null, state: string, name: string): string | null {
  const localOnly = Boolean(meta?.programs?.[state]?.local_only);
  if (!meta || (!meta.catalogs && !meta.programs) || (programsFile(meta, state) && !localOnly)) return null; // no list loaded: say nothing
  const status = meta.catalogs?.[state]?.status;
  const kind = state === "DC" || state === "PR" ? "" : "state ";
  // Mid-sentence the District takes "the"; at the start of a sentence, "The".
  const the = state === "DC" ? `the ${name}` : name;
  const The = state === "DC" ? `The ${name}` : name;
  const grants = kind ? `${the} state grants` : `grants from ${the}`;
  const cover = `${meta.states.includes(state) ? "Federal grants and foundations cover" : "Federal grants cover"} ${the}.`;
  // A state that has a catalog whose file didn't come through: say only that, not that there's no catalog.
  if (status === "built") return `${The} ${kind}grants aren't available right now. ${cover}`;
  // Each says no more than the research showed (grantmatch/states.py): "unchecked" makes no claim at all.
  const Grants = kind ? `${The} state grants` : `Grants from ${the}`;
  const why = status === "html" ? ` What was checked for ${the} didn't give a grant list that can be read in yet.`
    : status === "decide" ? ` ${The} has a machine-readable grant list that isn't read in yet.`
    : status === "next" ? ` A source for ${grants} is being looked at.`
    : status === "none" ? ` No current public list of ${grants} was found.`
    : status === "blocked" ? ` Key grant sites for ${the} can't be used here: their rules or terms don't allow it, or they turn automated readers away, so ${grants} aren't read in.`
    : status === "unchecked" ? ` ${Grants} aren't read in yet.`
    : "";
  const partial = !localOnly ? ""
    : meta.programs?.[state]?.local
      ? ` The ${name} local programs tab has county and city programs only, entered by hand from each program's own page: a partial list, not every county or city.`
      : ` The ${name} programs tab has state programs only, entered by hand from each program's own page: not a statewide list.`;
  return `No ${name} ${kind}catalog yet.${why}${partial} ${cover}`;
}
/** The line above the local programs of a state with no state catalog. */
export const localTally = (name: string, count: number, local = true) =>
  `${count.toLocaleString("en-US")} ${local ? "county and city" : "state"} ${count === 1 ? "program" : "programs"} in ${name}, entered by hand from each program's own page. This is partial coverage, with no ${name} state catalog; each card shows when it was checked.`;
/** "Ohio state grants", but "District of Columbia grants": the District isn't a state. */
export const grantsPhrase = (state: string, name: string) => `${name} ${state === "DC" ? "" : "state "}grants`;

/** The line above a state's open calls: how many, from where, how fresh, and what isn't covered. Programs kept by
 *  hand (they have a level) aren't the state's list, and some are between rounds, so they are counted apart. */
export function callsTally(state: string, name: string, records: { nonprofit_eligible: boolean; applicant_types?: string; level?: string }[],
                           info: { source?: string; who_listed?: boolean; paused?: boolean } | undefined, updated: string): string {
  const count = (n: number) => n.toLocaleString("en-US");
  const dc = state === "DC";
  const calls = records.filter((r) => !r.level);
  const hand = records.length - calls.length;
  const local = records.filter((r) => r.level && r.level !== "State").length;
  const shown = calls.filter((r) => r.nonprofit_eligible);
  // A call that doesn't say who may apply is shown, but it doesn't "list nonprofits as eligible": counted apart.
  const unstated = shown.filter((r) => ELIGIBILITY_UNSTATED.test(r.applicant_types ?? "")).length;
  const from = info?.source ? `, from the ${info.source}` : "";
  const when = updated ? `, updated ${updated}` : "";
  const what = `of ${count(calls.length)} open ${name} ${dc ? "" : "state "}grant`;
  const listed = `${count(shown.length - unstated)} ${what} and loan calls list nonprofits as eligible`;
  const source = `${from}${when}`.slice(2); // "from the ..., updated ..." as its own sentence
  const line = info?.who_listed === false
    ? `${count(shown.length)} ${what} calls are shown${from}${when}. The list doesn't say who may apply, so read each notice.`
    : unstated
      ? `${listed}; ${count(unstated)} more ${unstated === 1 ? "doesn't" : "don't"} say who may apply.${source ? ` ${source[0].toUpperCase()}${source.slice(1)}.` : ""}`
      : `${listed}${from}${when}.`;
  const plus = hand ? ` Plus ${count(hand)} ${hand === 1 ? "program" : "programs"} entered by hand from ${hand === 1 ? "its own page" : "their own pages"}.` : "";
  // A paused list (grantmatch/states.py) is old data: say so, with the date it was read.
  const paused = info?.paused
    ? ` Reading the ${name} state list is paused until the state gives its OK${updated ? `, so these state calls are as read on ${updated}` : ""}. Newer calls aren't here, and a call may have changed or closed since.`
    : "";
  if (dc) return line + plus;
  const cover = local
    ? `County and city programs are only partly covered for ${name}: ${count(local)} of those ${local === 1 ? "is a county or city program" : "are county or city programs"}.`
    : `County and city programs aren't covered for ${name} yet.`;
  return `${line}${paused}${plus} ${cover}`;
}

/** The result tabs to show: the state tab only when the profile's state has programs, so a preview's counts from
 *  the last state (a "Kansas programs, 0" tab) don't linger while a new search for a state without one runs. */
export const shownSources = <K extends string>(keys: K[], hasPrograms: boolean): K[] =>
  keys.filter((k) => k !== "fl" || hasPrograms);
/** A state's counties and the cities, towns and Census places in each (grantmatch/counties.py). */
export const loadCounties = (state: string) => json<Record<string, string[]>>(`counties-${state}.json`);
/** A state's local funders (grantmatch/funders.py). Funders, not grants: never scored or listed with results. */
export const loadFunders = (state: string) => json<Funder[]>(`funders-${state}.json`);
