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
export const loadExamples = () => json<Record<string, Example>>("examples.json");
export const loadFederal = () => source<FederalRec>("federal");
export const loadFlorida = () => source<FloridaRec>("florida");
export const loadFoundations = (state: string) => source<FoundationRec>(`foundations-${state}`);
/** A state's counties and the cities, towns and Census places in each (grantmatch/counties.py). */
export const loadCounties = (state: string) => json<Record<string, string[]>>(`counties-${state}.json`);
