// Loads the files grantmatch/export_web.py writes into public/data.
import type { FederalRec, FloridaRec, FoundationRec } from "./score";
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

/** Reads a gzipped JSON file. Unpacks it here unless the server already did (sent it with Content-Encoding). */
async function gzJson<T>(name: string): Promise<T> {
  const r = await fetch(BASE + name);
  if (!r.ok) throw new Error(`${name}: ${r.status}`);
  const bytes = new Uint8Array(await r.arrayBuffer());
  if (bytes[0] === 0x1f && bytes[1] === 0x8b) {
    const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream("gzip"));
    return JSON.parse(await new Response(stream).text()) as T;
  }
  return JSON.parse(new TextDecoder().decode(bytes)) as T;
}

async function source<T>(name: string): Promise<Source<T>> {
  const [payload, buf] = await Promise.all([
    gzJson<{ records: T[]; vec_ids: string[]; dim: number; fetched_at?: string; fiscal_year?: string }>(`${name}.json.gz`),
    fetch(`${BASE}${name}.f16`).then((r) => {
      if (!r.ok) throw new Error(`${name}.f16: ${r.status}`);
      return r.arrayBuffer();
    }),
  ]);
  return {
    records: payload.records,
    vecs: decodeF16(buf, payload.vec_ids, payload.dim),
    fetchedAt: payload.fetched_at ?? "",
    fiscalYear: payload.fiscal_year,
  };
}

export const loadMeta = () => json<Meta>("meta.json");
export const loadCoverage = () => json<Coverage>("coverage.json");
export const loadExamples = () => json<Record<string, Example>>("examples.json");
export const loadFederal = () => source<FederalRec>("federal");
export const loadFlorida = () => source<FloridaRec>("florida");
/** The file holding a state's programs, or null when the state has none. Florida's keeps its own name. */
export const programsFile = (meta: Meta | null, state: string) => (state === "FL" ? "florida" : meta?.programs?.[state]?.file ?? null);
export const loadPrograms = (file: string) => source<FloridaRec>(file);
export const loadFoundations = (state: string) => source<FoundationRec>(`foundations-${state}`);
/** A state's counties and the cities, towns and Census places in each (grantmatch/counties.py). */
export const loadCounties = (state: string) => json<Record<string, string[]>>(`counties-${state}.json`);
