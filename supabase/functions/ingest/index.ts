// Lets the deploy workflow put freshly exported data in the private "data" bucket without holding a
// database key. The workflow sends the file names and the INGEST_TOKEN secret; this answers with a
// one-time upload link for each name, and the workflow uploads each file to its link.
//
//   POST { "names": ["federal.json.gz", "federal.f16", ...] }   header x-ingest-token: <INGEST_TOKEN>
//   ->   { "links": { "federal.json.gz": "https://...", ... } }
declare const Deno: {
  env: { get(name: string): string | undefined };
  serve(handler: (req: Request) => Response | Promise<Response>): void;
};

const BASE = (Deno.env.get("SUPABASE_URL") ?? "").replace(/\/$/, "");
const SERVICE = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "";
const TOKEN = Deno.env.get("INGEST_TOKEN") ?? "";
const NAME = /^[A-Za-z0-9][A-Za-z0-9-]*(\.slim)?\.(json|json\.gz|f16)$/;

function same(a: string, b: string): boolean {
  if (!a || a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

const out = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

Deno.serve(async (req) => {
  if (req.method !== "POST") return out(405, { error: "POST only" });
  if (!TOKEN || !same(req.headers.get("x-ingest-token") ?? "", TOKEN)) return out(401, { error: "Wrong token" });
  let names: string[];
  try {
    names = (await req.json()).names;
    if (!Array.isArray(names) || !names.length || names.length > 300 || !names.every((n) => typeof n === "string" && NAME.test(n))) throw new Error();
  } catch {
    return out(400, { error: "Send names like federal.json.gz" });
  }
  const links: Record<string, string> = {};
  for (const name of names) {
    const res = await fetch(`${BASE}/storage/v1/object/upload/sign/data/${name}`, {
      method: "POST", headers: { Authorization: `Bearer ${SERVICE}`, apikey: SERVICE, "x-upsert": "true" },
    });
    if (!res.ok) return out(502, { error: `Couldn't make a link for ${name} (${res.status})` });
    const { url } = (await res.json()) as { url: string };
    links[name] = `${BASE}/storage/v1${url}`;
  }
  return out(200, { links });
});
