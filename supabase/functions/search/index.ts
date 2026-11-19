// The search gate. The page calls this with a profile and its mission vector.
//
//  - A visitor gets a preview: how many strong and possible matches each source has, and the top three
//    (src/server/preview.ts, the page's own scoring).
//  - A free account gets the counts and the top ten in every source, the same way.
//  - An active Pro or Consultant account gets short-lived links to the data files for its state, and the page
//    ranks them itself, the way it always has.
// public.record_search() says which plan the account has and logs each search once a month, as a hash.
//
// The data lives in the private "data" bucket, which only the service role reads. Built into one file by
// `npm run build:fn` in web/, which bundles the scoring code, and deployed with that file as index.ts.
import { FREE_SIZE, PREVIEW_SIZE, preview, searchSignature } from "../../../web/src/server/preview";
import { parseProfile, type ProfileForm } from "../../../web/src/profile";
import type { RankSources } from "../../../web/src/rank";
import { decodeF16 } from "../../../web/src/vectors";

declare const Deno: {
  env: { get(name: string): string | undefined };
  serve(handler: (req: Request) => Response | Promise<Response>): void;
};

const BASE = (Deno.env.get("SUPABASE_URL") ?? "").replace(/\/$/, "");
const SERVICE = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "";
const PUBLIC_KEY = (() => {
  try { return JSON.parse(Deno.env.get("SUPABASE_PUBLISHABLE_KEYS") ?? "{}").default ?? Deno.env.get("SUPABASE_ANON_KEY") ?? ""; } catch { return Deno.env.get("SUPABASE_ANON_KEY") ?? ""; }
})();
const BUCKET = "data";
const LINK_SECONDS = 15 * 60;
const LIST_SECONDS = 5 * 60;
const DIM = 384;
const MAX_BODY = 64_000;
const ORIGINS = (Deno.env.get("ALLOWED_ORIGINS") ?? "https://rendellrich.github.io,http://localhost:5173,http://localhost:4173").split(",").map((s) => s.trim());

// ---------- storage ----------
const service = { Authorization: `Bearer ${SERVICE}`, apikey: SERVICE };
let listing: { at: number; tags: Map<string, string> } | null = null;

/** Each file's eTag, so a cached copy is used until the data is replaced. */
async function tags(): Promise<Map<string, string>> {
  if (listing && Date.now() - listing.at < LIST_SECONDS * 1000) return listing.tags;
  const res = await fetch(`${BASE}/storage/v1/object/list/${BUCKET}`, {
    method: "POST", headers: { ...service, "Content-Type": "application/json" },
    body: JSON.stringify({ prefix: "", limit: 1000, offset: 0, sortBy: { column: "name", order: "asc" } }),
  });
  if (!res.ok) throw new Error(`list ${res.status}`);
  const rows = (await res.json()) as { name: string; updated_at?: string; metadata?: { eTag?: string } }[];
  listing = { at: Date.now(), tags: new Map(rows.filter((r) => r.metadata).map((r) => [r.name, String(r.metadata?.eTag ?? r.updated_at ?? "")])) };
  return listing.tags;
}

async function download(name: string): Promise<Uint8Array<ArrayBuffer>> {
  const res = await fetch(`${BASE}/storage/v1/object/authenticated/${BUCKET}/${name}`, { headers: service });
  if (!res.ok) throw new Error(`${name} ${res.status}`);
  return new Uint8Array(await res.arrayBuffer());
}

async function parseJson<T>(bytes: Uint8Array<ArrayBuffer>): Promise<T> {
  if (bytes[0] === 0x1f && bytes[1] === 0x8b) {
    const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream("gzip"));
    return JSON.parse(await new Response(stream).text()) as T;
  }
  return JSON.parse(new TextDecoder().decode(bytes)) as T;
}

// One worker keeps the small files and one state's foundations: California's alone is about 100 MB once read.
const memo = new Map<string, { tag: string; value: unknown }>();
async function cached<T>(name: string, make: () => Promise<T>): Promise<T | null> {
  const tag = (await tags()).get(name.split("|")[0]);
  if (tag === undefined) return null;
  const hit = memo.get(name);
  if (hit && hit.tag === tag) return hit.value as T;
  if (name.startsWith("foundations-")) for (const k of [...memo.keys()]) if (k.startsWith("foundations-")) memo.delete(k);
  const value = await make();
  memo.set(name, { tag, value });
  return value;
}

const json = <T>(name: string) => cached<T>(name, async () => parseJson<T>(await download(name)));

/** A source for the preview. Foundations come from their slim copy (grantmatch/server_data.py) when there is one. */
async function source<T>(name: string) {
  const have = await tags();
  if (!have.has(`${name}.f16`)) return null;
  const file = have.has(`${name}.slim.json.gz`) ? `${name}.slim.json.gz` : `${name}.json.gz`;
  return cached(`${file}|source`, async () => {
    const [payload, raw] = await Promise.all([
      parseJson<{ records: T[]; vec_ids: string[]; dim: number }>(await download(file)),
      download(`${name}.f16`),
    ]);
    const buf = raw.buffer.slice(raw.byteOffset, raw.byteOffset + raw.byteLength) as ArrayBuffer;
    return { records: payload.records, vecs: decodeF16(buf, payload.vec_ids, payload.dim) };
  });
}

interface Meta { states: string[]; programs?: Record<string, { file: string }> }

/** The data files a profile in this state uses, by source. */
function filesFor(meta: Meta, state: string): Record<"fed" | "fdn" | "fl", string | null> {
  return {
    fed: "federal",
    fdn: meta.states.includes(state) ? `foundations-${state}` : null,
    fl: state === "FL" ? "florida" : meta.programs?.[state]?.file ?? null,
  };
}

async function sign(names: string[]): Promise<Map<string, string>> {
  const res = await fetch(`${BASE}/storage/v1/object/sign/${BUCKET}`, {
    method: "POST", headers: { ...service, "Content-Type": "application/json" },
    body: JSON.stringify({ expiresIn: LINK_SECONDS, paths: names }),
  });
  if (!res.ok) throw new Error(`sign ${res.status}`);
  const rows = (await res.json()) as { path: string; signedURL?: string; error?: string | null }[];
  return new Map(rows.filter((r) => r.signedURL).map((r) => [r.path, `${BASE}/storage/v1${r.signedURL}`]));
}

// ---------- accounts ----------
async function signedIn(token: string | null): Promise<boolean> {
  if (!token || token.split(".").length !== 3) return false;
  const res = await fetch(`${BASE}/auth/v1/user`, { headers: { apikey: PUBLIC_KEY, Authorization: `Bearer ${token}` } });
  return res.ok;
}

interface Count { full: boolean; plan?: string; repeat?: boolean }
async function recordSearch(token: string, sig: string): Promise<Count> {
  const res = await fetch(`${BASE}/rest/v1/rpc/record_search`, {
    method: "POST",
    headers: { apikey: PUBLIC_KEY, Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify({ p_sig: sig }),
  });
  if (!res.ok) throw new Error(`record_search ${res.status}`);
  return (await res.json()) as Count;
}

async function sha256(text: string): Promise<string> {
  const d = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(d)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

// ---------- the request ----------
function cors(origin: string | null): Record<string, string> {
  return {
    "Access-Control-Allow-Origin": origin && ORIGINS.includes(origin) ? origin : ORIGINS[0],
    "Access-Control-Allow-Headers": "authorization, apikey, content-type, x-client-info",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    Vary: "Origin",
  };
}

function reply(origin: string | null, status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { ...cors(origin), "Content-Type": "application/json" } });
}

function readVector(v: unknown): number[] | null {
  return Array.isArray(v) && v.length === DIM && v.every((x) => typeof x === "number" && Number.isFinite(x)) ? v : null;
}

export async function handle(req: Request): Promise<Response> {
  const origin = req.headers.get("origin");
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors(origin) });
  if (req.method !== "POST") return reply(origin, 405, { error: "POST only" });
  const text = await req.text();
  if (text.length > MAX_BODY) return reply(origin, 413, { error: "Request too large" });
  let form: ProfileForm, vector: number[] | null;
  try {
    const body = JSON.parse(text);
    form = parseProfile(JSON.stringify(body.form));
    vector = readVector(body.vector);
  } catch {
    return reply(origin, 400, { error: "Send a profile" });
  }
  try {
    const meta = await json<Meta>("meta.json");
    if (!meta) return reply(origin, 503, { error: "The data isn't loaded yet" });
    const token = req.headers.get("authorization")?.replace(/^Bearer\s+/i, "") ?? null;
    const user = token !== PUBLIC_KEY && (await signedIn(token));
    let count: Count | null = null;
    if (user) {
      count = await recordSearch(token!, await sha256(searchSignature(form)));
      if (count.full) {
        const files = filesFor(meta, form.state);
        const names = Object.values(files).filter(Boolean).flatMap((n) => [`${n}.json.gz`, `${n}.f16`]);
        const have = await tags();
        const links = await sign(names.filter((n) => have.has(n)));
        const out: Record<string, { name: string; json: string; f16: string; version: string } | null> = {};
        for (const [k, n] of Object.entries(files)) {
          const j = n && links.get(`${n}.json.gz`), v = n && links.get(`${n}.f16`);
          out[k] = n && j && v ? { name: n, json: j, f16: v, version: `${have.get(`${n}.json.gz`)}|${have.get(`${n}.f16`)}` } : null;
        }
        return reply(origin, 200, { access: "full", files: out, plan: count.plan ?? null });
      }
    }
    const files = filesFor(meta, form.state);
    const [fed, fdn, fl, counties] = await Promise.all([
      source<never>("federal"),
      files.fdn ? source<never>(files.fdn) : null,
      files.fl ? source<never>(files.fl) : null,
      json<Record<string, string[]>>(`counties-${form.state}.json`),
    ]);
    const src: RankSources = { fed, fdn, fl, flState: form.state, counties };
    const pv = user ? preview(form, src, vector, new Date(), FREE_SIZE, true) : preview(form, src, vector, new Date(), PREVIEW_SIZE);
    return reply(origin, 200, { access: "preview", reason: user ? "free" : "visitor", ...pv, plan: count?.plan ?? null });
  } catch (e) {
    console.error("search failed:", e instanceof Error ? e.message : String(e));
    return reply(origin, 500, { error: "Search is unavailable right now. Try again in a minute." });
  }
}

if (typeof Deno !== "undefined" && typeof Deno.serve === "function") Deno.serve(handle);
