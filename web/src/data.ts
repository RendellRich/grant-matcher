// Loads the files grantmatch/export_web.py writes. The small public ones (meta, examples, coverage, counties)
// come with the site; the grant data comes from the private bucket through links the search gate sends.
import type { FileLink } from "./access";
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
  /** States besides Florida with their own programs file: its name, its source and when it was fetched. */
  programs?: Record<string, { file: string; source: string; updated?: string }>;
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
/** A state's counties and the cities, towns and Census places in each (grantmatch/counties.py). */
export const loadCounties = (state: string) => json<Record<string, string[]>>(`counties-${state}.json`);
