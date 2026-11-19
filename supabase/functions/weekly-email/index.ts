// The weekly email of new strong matches. pg_cron calls this every ten minutes with the job's token
// (private.job_tokens). Each call takes one account that is due (public.take_digest), scores its saved profile
// with the page's own code (web/src/server/digest.ts), and emails the strong matches it hasn't sent before.
// The first run after someone turns the email on only remembers what already matches, so the first email holds
// what is new since then. POST ?off=<token> turns the email off (the page's confirm button, and one-click).
//
// Secrets: RESEND_API_KEY (sending). Built into one file by `npm run build:digest` in web/.
import { newStrong, digestEmail, type DigestAccount } from "../../../web/src/server/digest";
import { parseProfile } from "../../../web/src/profile";
import type { RankSources } from "../../../web/src/rank";
import { decodeF16 } from "../../../web/src/vectors";

declare const Deno: {
  env: { get(name: string): string | undefined };
  serve(handler: (req: Request) => Response | Promise<Response>): void;
};

const BASE = (Deno.env.get("SUPABASE_URL") ?? "").replace(/\/$/, "");
const SERVICE = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "";
const RESEND = Deno.env.get("RESEND_API_KEY") ?? "";
const FROM = Deno.env.get("DIGEST_FROM") ?? "Grant Matcher <noreply@solutionsbyrich.com>";
const SITE = Deno.env.get("SITE_URL") ?? "https://rendellrich.github.io/grant-matcher/";
const BUCKET = "data";
const service = { Authorization: `Bearer ${SERVICE}`, apikey: SERVICE };

async function rpc<T>(name: string, args: Record<string, unknown> = {}): Promise<T> {
  const res = await fetch(`${BASE}/rest/v1/rpc/${name}`, {
    method: "POST", headers: { ...service, "Content-Type": "application/json" }, body: JSON.stringify(args),
  });
  if (!res.ok) throw new Error(`${name} ${res.status}`);
  return (await res.json()) as T;
}

// ---------- data, the same files the search function reads ----------
async function names(): Promise<Set<string>> {
  const res = await fetch(`${BASE}/storage/v1/object/list/${BUCKET}`, {
    method: "POST", headers: { ...service, "Content-Type": "application/json" },
    body: JSON.stringify({ prefix: "", limit: 1000, offset: 0 }),
  });
  if (!res.ok) throw new Error(`list ${res.status}`);
  return new Set(((await res.json()) as { name: string }[]).map((r) => r.name));
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

async function source<T>(have: Set<string>, name: string) {
  if (!have.has(`${name}.f16`)) return null;
  const file = have.has(`${name}.slim.json.gz`) ? `${name}.slim.json.gz` : `${name}.json.gz`;
  const [payload, raw] = await Promise.all([
    parseJson<{ records: T[]; vec_ids: string[]; dim: number }>(await download(file)),
    download(`${name}.f16`),
  ]);
  const buf = raw.buffer.slice(raw.byteOffset, raw.byteOffset + raw.byteLength) as ArrayBuffer;
  return { records: payload.records, vecs: decodeF16(buf, payload.vec_ids, payload.dim) };
}

interface Meta { states: string[]; programs?: Record<string, { file: string }> }

async function sourcesFor(state: string): Promise<RankSources> {
  const have = await names();
  const meta = await parseJson<Meta>(await download("meta.json"));
  const fdn = meta.states.includes(state) ? `foundations-${state}` : null;
  const fl = state === "FL" ? "florida" : meta.programs?.[state]?.file ?? null;
  const counties = have.has(`counties-${state}.json`) ? await parseJson<Record<string, string[]>>(await download(`counties-${state}.json`)) : {};
  const [fed, fdnSrc, flSrc] = await Promise.all([
    source<never>(have, "federal"), fdn ? source<never>(have, fdn) : null, fl ? source<never>(have, fl) : null,
  ]);
  return { fed, fdn: fdnSrc, fl: flSrc, flState: state, counties };
}

async function send(to: string, mail: { subject: string; html: string; text: string }, unsubscribe: string) {
  const res = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: { Authorization: `Bearer ${RESEND}`, "Content-Type": "application/json" },
    body: JSON.stringify({
      from: FROM, to: [to], reply_to: "ren@solutionsbyrich.com", subject: mail.subject, html: mail.html, text: mail.text,
      headers: { "List-Unsubscribe": `<${unsubscribe}>`, "List-Unsubscribe-Post": "List-Unsubscribe=One-Click" },
    }),
  });
  if (!res.ok) throw new Error(`resend ${res.status} ${(await res.text()).slice(0, 200)}`);
}

const CORS = { "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "content-type", "Access-Control-Allow-Methods": "POST, OPTIONS" };
const say = (text: string, status = 200) => new Response(text, { status, headers: { ...CORS, "Content-Type": "text/plain; charset=utf-8" } });

export async function handle(req: Request): Promise<Response> {
  const off = new URL(req.url).searchParams.get("off");
  if (off !== null) {
    // Unsubscribe: the page's confirm button and mail apps' one-click both POST here. A plain visit changes
    // nothing, so a mail scanner opening links can't turn anyone's email off.
    if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
    if (req.method !== "POST") return say("To turn off the weekly email, use the link in the email and press the button.", 405);
    if (!/^[0-9a-f-]{36}$/i.test(off)) return say("That link isn't right.", 400);
    return say((await rpc<boolean>("digest_off", { p_token: off })) ? "off" : "already off");
  }
  if (req.method !== "POST") return new Response("POST only", { status: 405 });
  const token = req.headers.get("x-job-token") ?? "";
  if (!token || !(await rpc<boolean>("check_job_token", { p_name: "weekly-email", p_token: token }))) {
    return new Response("not allowed", { status: 401 });
  }
  if (!RESEND) return new Response("not set up", { status: 503 });
  const acct = await rpc<DigestAccount | null>("take_digest");
  if (!acct) return new Response("none due", { status: 200 });
  try {
    const form = parseProfile(JSON.stringify(acct.profile));
    const src = await sourcesFor(form.state);
    const { fresh, all } = newStrong(form, src, acct.vector, acct.seen, new Date());
    if (acct.seen !== null && fresh.length) {
      const oneClick = `${BASE}/functions/v1/weekly-email?off=${acct.token}`;
      const turnOff = `${SITE}?weekly-off=${acct.token}`;
      await send(acct.email, digestEmail(form, fresh, SITE, turnOff), oneClick);
    }
    await rpc("finish_digest", { p_id: acct.id, p_seen: all });
    return new Response(acct.seen === null ? "seeded" : `sent ${fresh.length}`, { status: 200 });
  } catch (e) {
    console.error("weekly-email failed:", acct.id, e instanceof Error ? e.message : String(e));
    return new Response("failed", { status: 500 });
  }
}

if (typeof Deno !== "undefined" && typeof Deno.serve === "function") Deno.serve(handle);
