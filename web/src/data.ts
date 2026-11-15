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

async function source<T>(name: string): Promise<Source<T>> {
  const [payload, buf] = await Promise.all([
    json<{ records: T[]; vec_ids: string[]; dim: number; fetched_at?: string; fiscal_year?: string }>(`${name}.json`),
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
