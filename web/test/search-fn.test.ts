// The search gate (supabase/functions/search), run here against a fake Supabase: storage serves the test data,
// one token is a signed-in account, and record_search() answers as the test says.
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { BLANK } from "../src/profile";

const DIR = new URL("../test-data/", import.meta.url);
const have = ["federal.json.gz", "foundations-FL.json.gz", "florida.json.gz", "meta.json", "examples.json"].every((f) => existsSync(new URL(f, DIR)));
const BASE = "https://gm.test";
const USER = "aaa.bbb.ccc";
let searches: { sig: string }[] = [];
let answer: (sig: string) => Record<string, unknown> = () => ({ allowed: true, used: 1, limit: 3, plan: "free" });

function fakeFetch(input: string | URL | Request, init?: RequestInit): Promise<Response> {
  const url = String(input instanceof Request ? input.url : input);
  const path = url.replace(BASE, "");
  const ok = (body: unknown) => Promise.resolve(new Response(typeof body === "string" || body instanceof Uint8Array ? body as BodyInit : JSON.stringify(body)));
  if (path === "/storage/v1/object/list/data") {
    return ok(readdirSync(DIR).map((name) => ({ name, metadata: { eTag: `"${name}-1"` } })));
  }
  if (path.startsWith("/storage/v1/object/authenticated/data/")) {
    const name = path.split("/").pop()!;
    return existsSync(new URL(name, DIR)) ? ok(new Uint8Array(readFileSync(new URL(name, DIR)))) : Promise.resolve(new Response("", { status: 404 }));
  }
  if (path === "/storage/v1/object/sign/data") {
    const { paths } = JSON.parse(String(init?.body));
    return ok(paths.map((p: string) => ({ path: p, signedURL: `/object/sign/data/${p}?token=t` })));
  }
  if (path === "/auth/v1/user") {
    const auth = new Headers(init?.headers).get("authorization");
    return Promise.resolve(new Response("{}", { status: auth === `Bearer ${USER}` ? 200 : 401 }));
  }
  if (path === "/rest/v1/rpc/record_search") {
    const { p_sig } = JSON.parse(String(init?.body));
    searches.push({ sig: p_sig });
    return ok(answer(p_sig));
  }
  return Promise.resolve(new Response("not faked", { status: 500 }));
}

let handle: (req: Request) => Promise<Response>;
beforeAll(async () => {
  const env: Record<string, string> = { SUPABASE_URL: BASE, SUPABASE_SERVICE_ROLE_KEY: "service", SUPABASE_ANON_KEY: "anon" };
  (globalThis as Record<string, unknown>).Deno = { env: { get: (k: string) => env[k] } };
  vi.stubGlobal("fetch", fakeFetch);
  handle = (await import("../../supabase/functions/search/index")).handle;
});

const examples = have ? JSON.parse(readFileSync(new URL("examples.json", DIR), "utf8")) : {};
const [exKey, ex] = (Object.entries(examples)[0] ?? ["", null]) as [string, { mission: string; keywords: string; categories: string[]; state: string; cities: string; vector: number[] } | null];
const form = ex ? { ...BLANK, mission: ex.mission, keywords: ex.keywords, categories: ex.categories, state: ex.state, cities: ex.cities } : BLANK;

async function call(body: unknown, token = "anon", origin = "https://rendellrich.github.io") {
  const res = await handle(new Request(`${BASE}/functions/v1/search`, {
    method: "POST", headers: { Authorization: `Bearer ${token}`, Origin: origin, "Content-Type": "application/json" }, body: JSON.stringify(body),
  }));
  return { status: res.status, cors: res.headers.get("access-control-allow-origin"), body: await res.json() };
}

describe("the search gate", () => {
  it("refuses what isn't a profile", async () => {
    expect((await call({ form: { nope: 1 } })).status).toBe(400);
  });
});

describe.skipIf(!have)("with the test data", () => {
  it("shows a visitor three results and the counts, and no links", async () => {
    const r = await call({ form, vector: ex!.vector, example: exKey });
    expect(r.status).toBe(200);
    expect(r.cors).toBe("https://rendellrich.github.io");
    expect(r.body.access).toBe("preview");
    expect(r.body.reason).toBe("visitor");
    expect(r.body.entries).toHaveLength(3);
    expect(r.body.files).toBeUndefined();
    expect(r.body.counts.fed.strong + r.body.counts.fed.possible).toBeGreaterThan(0);
    expect(searches).toHaveLength(0);
  });
  it("doesn't count an example for a signed-in account, and sends links for its state's files", async () => {
    searches = [];
    const r = await call({ form, vector: ex!.vector, example: exKey }, USER);
    expect(r.body.access).toBe("full");
    expect(searches).toHaveLength(0);
    expect(r.body.files.fed.json).toBe(`${BASE}/storage/v1/object/sign/data/federal.json.gz?token=t`);
    expect(r.body.files.fdn.name).toBe("foundations-FL");
    expect(r.body.files.fl.name).toBe("florida");
    expect(r.body.entries).toBeUndefined();
  });
  it("counts a new search by its hash, and a refinement hashes the same", async () => {
    searches = [];
    const mine = { ...form, mission: `${form.mission} Synthetic change.` };
    await call({ form: mine, vector: ex!.vector }, USER);
    await call({ form: { ...mine, min_days_left: 45, hide: ["declined"] }, vector: ex!.vector }, USER);
    expect(searches).toHaveLength(2);
    expect(searches[0].sig).toBe(searches[1].sig);
    expect(searches[0].sig).toMatch(/^[0-9a-f]{64}$/);
    expect(searches[0].sig).not.toBe(createHash("sha256").update(JSON.stringify(form)).digest("hex"));
  });
  it("gives an account past its free searches the preview, saying why", async () => {
    answer = () => ({ allowed: false, reason: "limit", used: 3, limit: 3, plan: "free" });
    const r = await call({ form: { ...form, mission: "Synthetic other mission" }, vector: ex!.vector }, USER);
    expect(r.body.access).toBe("preview");
    expect(r.body.reason).toBe("limit");
    expect(r.body.used).toBe(3);
    expect(r.body.entries.length).toBeLessThanOrEqual(3);
  });
  it("treats a forged token as a visitor", async () => {
    const r = await call({ form, vector: ex!.vector }, "xxx.yyy.zzz", "https://evil.test");
    expect(r.body.access).toBe("preview");
    expect(r.cors).toBe("https://rendellrich.github.io");
  });
});
