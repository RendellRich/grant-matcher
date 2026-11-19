// Starts a Pro or Consultant subscription (Stripe Checkout) or opens Stripe's billing portal for a signed-in
// account. The page calls it with the account's own sign-in token:
//
//   POST { "action": "checkout", "plan": "pro" | "consultant" }  ->  { "url": "https://checkout.stripe.com/..." }
//   POST { "action": "portal" }                                   ->  { "url": "https://billing.stripe.com/..." }
//
// The plan itself only changes when Stripe tells stripe-webhook that a subscription started or changed.
// Secrets: STRIPE_SECRET_KEY (a restricted key). Prices are found by lookup key (_shared/billing-core.ts).
import Stripe from "npm:stripe@23";
import { CHECKOUT_LABEL, isPaidPlan, LOOKUP_KEYS } from "../_shared/billing-core.ts";

const BASE = (Deno.env.get("SUPABASE_URL") ?? "").replace(/\/$/, "");
const SERVICE = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "";
const PUBLIC_KEY = (() => {
  try { return JSON.parse(Deno.env.get("SUPABASE_PUBLISHABLE_KEYS") ?? "{}").default ?? Deno.env.get("SUPABASE_ANON_KEY") ?? ""; } catch { return Deno.env.get("SUPABASE_ANON_KEY") ?? ""; }
})();
const ORIGINS = (Deno.env.get("ALLOWED_ORIGINS") ?? "https://rendellrich.github.io,http://localhost:5173,http://localhost:4173").split(",").map((s) => s.trim());
const KEY = Deno.env.get("STRIPE_SECRET_KEY") ?? "";
// Stripe's library won't start without a key, so the function still answers before the key is set.
const stripe = KEY ? new Stripe(KEY, { apiVersion: "2026-10-28.endive" as Stripe.LatestApiVersion, httpClient: Stripe.createFetchHttpClient() }) : (null as unknown as Stripe);

const service = { Authorization: `Bearer ${SERVICE}`, apikey: SERVICE, "Content-Type": "application/json" };

function cors(origin: string | null): Record<string, string> {
  return {
    "Access-Control-Allow-Origin": origin && ORIGINS.includes(origin) ? origin : ORIGINS[0],
    "Access-Control-Allow-Headers": "authorization, apikey, content-type, x-client-info",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    Vary: "Origin",
  };
}
const reply = (origin: string | null, status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { ...cors(origin), "Content-Type": "application/json" } });

/** Where Stripe sends people back: the page they came from (the live site, or a local copy while testing). */
const siteFor = (origin: string | null) => `${origin && ORIGINS.includes(origin) ? origin : ORIGINS[0]}/grant-matcher/`;

interface Account { id: string; plan: string; status: string; stripe_customer_id: string | null }

async function currentUser(token: string | null): Promise<{ id: string; email: string } | null> {
  if (!token || token.split(".").length !== 3) return null;
  const res = await fetch(`${BASE}/auth/v1/user`, { headers: { apikey: PUBLIC_KEY, Authorization: `Bearer ${token}` } });
  if (!res.ok) return null;
  const u = await res.json();
  return u?.id ? { id: u.id, email: u.email ?? "" } : null;
}

async function accountOf(userId: string): Promise<Account | null> {
  const res = await fetch(`${BASE}/rest/v1/accounts?owner=eq.${userId}&select=id,plan,status,stripe_customer_id`, { headers: service });
  if (!res.ok) throw new Error(`accounts ${res.status}`);
  return ((await res.json()) as Account[])[0] ?? null;
}

/** The account's Stripe customer, made the first time. Only set when empty, so two clicks can't make two. */
async function customerFor(acct: Account, userId: string, email: string): Promise<string> {
  if (acct.stripe_customer_id) return acct.stripe_customer_id;
  const customer = await stripe.customers.create({ email, metadata: { account_id: acct.id } }, { idempotencyKey: `gm-customer-${acct.id}` });
  const res = await fetch(`${BASE}/rest/v1/accounts?id=eq.${acct.id}&stripe_customer_id=is.null`, {
    method: "PATCH", headers: { ...service, Prefer: "return=representation" }, body: JSON.stringify({ stripe_customer_id: customer.id }),
  });
  if (!res.ok) throw new Error(`save customer ${res.status}`);
  const saved = (await res.json()) as Account[];
  if (saved[0]?.stripe_customer_id) return saved[0].stripe_customer_id;
  const again = await accountOf(userId); // another request saved one first
  if (!again?.stripe_customer_id) throw new Error("customer not saved");
  return again.stripe_customer_id;
}

const paidAndActive = (a: Account) => isPaidPlan(a.plan) && ["active", "trialing", "past_due"].includes(a.status);

Deno.serve(async (req) => {
  const origin = req.headers.get("origin");
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors(origin) });
  if (req.method !== "POST") return reply(origin, 405, { error: "POST only" });
  if (!KEY) return reply(origin, 503, { error: "Paid plans aren't open yet." });
  let body: { action?: string; plan?: string };
  try { body = await req.json(); } catch { return reply(origin, 400, { error: "Send an action" }); }
  try {
    const user = await currentUser(req.headers.get("authorization")?.replace(/^Bearer\s+/i, "") ?? null);
    if (!user) return reply(origin, 401, { error: "Sign in first." });
    const acct = await accountOf(user.id);
    if (!acct) return reply(origin, 404, { error: "Your account isn't set up yet. Sign out and back in, then try again." });
    const site = siteFor(origin);

    // Changing or cancelling a plan happens in Stripe's portal, and so does a second checkout for a paying account.
    if (body.action === "portal" || (body.action === "checkout" && paidAndActive(acct))) {
      if (!acct.stripe_customer_id) return reply(origin, 400, { error: "There's no billing on this account yet." });
      const portal = await stripe.billingPortal.sessions.create({ customer: acct.stripe_customer_id, return_url: site });
      return reply(origin, 200, { url: portal.url });
    }
    if (body.action !== "checkout" || !isPaidPlan(body.plan)) return reply(origin, 400, { error: "Choose Pro or Consultant." });

    const prices = await stripe.prices.list({ lookup_keys: [LOOKUP_KEYS[body.plan]], active: true, limit: 1 });
    const price = prices.data[0];
    if (!price) return reply(origin, 503, { error: "That plan isn't for sale yet." });
    const customer = await customerFor(acct, user.id, user.email);
    const session = await stripe.checkout.sessions.create({
      mode: "subscription",
      customer,
      client_reference_id: acct.id,
      line_items: [{ price: price.id, quantity: 1 }],
      allow_promotion_codes: true,
      subscription_data: { metadata: { account_id: acct.id } },
      success_url: `${site}?upgraded=1`,
      cancel_url: site,
      integration_identifier: CHECKOUT_LABEL,
    } as Stripe.Checkout.SessionCreateParams);
    return reply(origin, 200, { url: session.url });
  } catch (e) {
    console.error("billing failed:", e instanceof Error ? e.message : String(e));
    return reply(origin, 500, { error: "Billing is unavailable right now. Try again in a minute." });
  }
});
