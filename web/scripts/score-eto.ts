// Background scoring for Exceed the Odds (Phase 3E). Runs in the deploy workflow after the data is exported:
// reads ETO's saved grant profile with the Grant Matcher key, ranks it with the page's own code (src/rank.ts) on
// the files in public/data, and records the strong grants in ETO's CRM. Nothing about ETO is written to disk or
// to the site, and the log shows counts only.
//
//   ETO_SUPABASE_URL, ETO_PUBLISHABLE_KEY, ETO_GRANT_MATCHER_KEY   the three repository secrets
//   --data <dir>        where the exported data is (default public/data)
//   --profile <file>    score a profile from a local file instead of ETO's, and record nothing (for checks)
import { existsSync, readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { gunzipSync } from "node:zlib";
import { env as modelEnv, pipeline } from "@huggingface/transformers";
import { parseProfile, type ProfileForm } from "../src/profile";
import { isBlank, queryText, rankAll, strongItems, type RankSources } from "../src/rank";
import { decodeF16, type VectorSet } from "../src/vectors";

const MODEL = "Xenova/bge-small-en-v1.5";
const arg = (name: string) => { const i = process.argv.indexOf(name); return i > 0 ? process.argv[i + 1] : undefined; };
const say = (text: string) => console.log(`Background scoring: ${text}`);

function source<T>(dir: string, name: string): { records: T[]; vecs: VectorSet } | null {
  const file = join(dir, `${name}.json.gz`);
  if (!existsSync(file)) return null;
  const payload = JSON.parse(gunzipSync(readFileSync(file)).toString("utf8"));
  const raw = readFileSync(join(dir, `${name}.f16`));
  const buf = raw.buffer.slice(raw.byteOffset, raw.byteOffset + raw.byteLength) as ArrayBuffer;
  return { records: payload.records, vecs: decodeF16(buf, payload.vec_ids, payload.dim) };
}

export function loadSources(dir: string, state: string): RankSources {
  const meta = JSON.parse(readFileSync(join(dir, "meta.json"), "utf8")) as { states: string[]; programs?: Record<string, { file: string }> };
  const programs = state === "FL" ? "florida" : meta.programs?.[state]?.file;
  const counties = join(dir, `counties-${state}.json`);
  return {
    fed: source(dir, "federal"),
    fdn: meta.states.includes(state) ? source(dir, `foundations-${state}`) : null,
    fl: programs ? source(dir, programs) : null,
    flState: state,
    counties: existsSync(counties) ? JSON.parse(readFileSync(counties, "utf8")) : null,
  };
}

async function embed(text: string, modelDir: string): Promise<number[]> {
  modelEnv.localModelPath = modelDir;
  modelEnv.allowLocalModels = true;
  modelEnv.allowRemoteModels = false;
  const extract = await pipeline("feature-extraction", MODEL, { dtype: "fp16", device: "cpu" });
  const out = await extract(text, { pooling: "cls", normalize: true });
  return Array.from(out.data as Float32Array);
}

async function rpc(name: string, body: Record<string, unknown>): Promise<unknown> {
  const url = `${process.env.ETO_SUPABASE_URL!.replace(/\/$/, "")}/rest/v1/rpc/${name}`;
  const res = await fetch(url, {
    method: "POST",
    headers: { apikey: process.env.ETO_PUBLISHABLE_KEY!, "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const text = await res.text();
  if (!res.ok) {
    // ETO's errors carry no profile or grant data; keep only the reason the database gave, if it is ours.
    const known = /Unknown or revoked key|Unsupported Grant Matcher matches/.exec(text)?.[0];
    throw new Error(`ETO refused ${name} (HTTP ${res.status})${known ? `: ${known}` : ""}`);
  }
  return text ? JSON.parse(text) : null;
}

async function main() {
  const dir = resolve(arg("--data") ?? "public/data");
  const modelDir = resolve("public/models") + "/";
  const local = arg("--profile");
  let form: ProfileForm;
  if (local) {
    form = parseProfile(readFileSync(local, "utf8"));
  } else {
    if (!process.env.ETO_SUPABASE_URL || !process.env.ETO_PUBLISHABLE_KEY || !process.env.ETO_GRANT_MATCHER_KEY) {
      say("not set up (no ETO secrets), so nothing was scored.");
      return;
    }
    const got = (await rpc("grant_match_background_profile", { p_key: process.env.ETO_GRANT_MATCHER_KEY })) as { profile: unknown };
    if (!got?.profile) { say("ETO has no saved profile, so nothing was scored."); return; }
    form = parseProfile(JSON.stringify(got.profile));
  }
  if (isBlank(form)) { say("the saved profile is empty, so nothing was scored."); return; }
  const vector = queryText(form).trim() ? await embed(queryText(form), modelDir) : null;
  const lists = rankAll(form, loadSources(dir, form.state), vector);
  const items = strongItems([lists.fed, lists.fdn, lists.fl]);
  if (local) { say(`${items.length} strong (local profile; nothing recorded).`); return; }
  const done = (await rpc("record_grant_match_background", { p_key: process.env.ETO_GRANT_MATCHER_KEY, p_items: items })) as { strong: number; new: number };
  say(`recorded ${done.strong} strong, ${done.new} new.`);
}

main().catch((err) => {
  say(err instanceof Error ? err.message : "failed.");
  process.exitCode = 1;
});
