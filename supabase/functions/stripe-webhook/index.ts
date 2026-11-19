// Stripe calls this when a subscription starts, changes, renews, fails to renew or ends, and when a charge is
// refunded or disputed. It checks Stripe's signature, then sets the account's plan and status from the
// subscription itself (fetched fresh, so events arriving out of order can't leave a stale plan). Each event is
// recorded once in public.billing_events, so a retried event is not applied twice.
// Secrets: STRIPE_SECRET_KEY (a restricted key), STRIPE_WEBHOOK_SECRET (this endpoint's signing secret).
import Stripe from "npm:stripe@23";
import { accountPatch, HANDLED_EVENTS, INVOICE_EVENTS, RISK_EVENTS, SUBSCRIPTION_EVENTS, type SubscriptionView } from "../_shared/billing-core.ts";

const BASE = (Deno.env.get("SUPABASE_URL") ?? "").replace(/\/$/, "");
const SERVICE = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "";
const SIGNING = Deno.env.get("STRIPE_WEBHOOK_SECRET") ?? "";
const KEY = Deno.env.get("STRIPE_SECRET_KEY") ?? "";
// Stripe's library won't start without a key, so the endpoint still answers before the secrets are set.
const stripe = KEY ? new Stripe(KEY, { apiVersion: "2026-10-28.endive" as Stripe.LatestApiVersion, httpClient: Stripe.createFetchHttpClient() }) : (null as unknown as Stripe);
const cryptoProvider = Stripe.createSubtleCryptoProvider();
const service = { Authorization: `Bearer ${SERVICE}`, apikey: SERVICE, "Content-Type": "application/json" };

const idOf = (x: string | { id: string } | null | undefined) => (typeof x === "string" ? x : x?.id ?? null);

async function seen(eventId: string): Promise<boolean> {
  const res = await fetch(`${BASE}/rest/v1/billing_events?id=eq.${encodeURIComponent(eventId)}&select=id`, { headers: service });
  if (!res.ok) throw new Error(`billing_events ${res.status}`);
  return ((await res.json()) as unknown[]).length > 0;
}

async function record(event: Stripe.Event, objectId: string | null, note: string): Promise<void> {
  await fetch(`${BASE}/rest/v1/billing_events`, {
    method: "POST", headers: { ...service, Prefer: "resolution=ignore-duplicates" },
    body: JSON.stringify({ id: event.id, type: event.type, object_id: objectId, note, livemode: event.livemode }),
  });
}

function view(sub: Stripe.Subscription): SubscriptionView {
  const coupons: string[] = [];
  for (const d of (sub.discounts ?? []) as unknown[]) {
    if (!d || typeof d === "string") continue;
    const disc = d as { coupon?: { id: string } | string; source?: { coupon?: { id: string } | string } };
    const c = idOf(disc.source?.coupon ?? disc.coupon ?? null);
    if (c) coupons.push(c);
  }
  return {
    id: sub.id, customer: idOf(sub.customer as string | { id: string })!, status: sub.status, coupons,
    items: sub.items.data.map((i) => ({ price: { lookup_key: i.price.lookup_key ?? null } })),
  };
}

/** Sets the account from the subscription as Stripe has it now. Finds the account by its Stripe customer,
 *  or (the first time) by the account id the checkout carried. */
async function sync(subscriptionId: string): Promise<string> {
  const sub = await stripe.subscriptions.retrieve(subscriptionId, { expand: ["discounts"] });
  const v = view(sub);
  const patch = accountPatch(v);
  let res = await fetch(`${BASE}/rest/v1/accounts?stripe_customer_id=eq.${encodeURIComponent(v.customer)}`, {
    method: "PATCH", headers: { ...service, Prefer: "return=representation" }, body: JSON.stringify(patch),
  });
  if (!res.ok) throw new Error(`update account ${res.status}`);
  let rows = (await res.json()) as unknown[];
  const accountId = sub.metadata?.account_id;
  if (!rows.length && accountId) {
    res = await fetch(`${BASE}/rest/v1/accounts?id=eq.${encodeURIComponent(accountId)}`, {
      method: "PATCH", headers: { ...service, Prefer: "return=representation" }, body: JSON.stringify({ ...patch, stripe_customer_id: v.customer }),
    });
    if (!res.ok) throw new Error(`update account by id ${res.status}`);
    rows = (await res.json()) as unknown[];
  }
  if (!rows.length) throw new Error(`no account for customer ${v.customer}`);
  return `${patch.plan} ${patch.status}${patch.founding ? " founding" : ""}`;
}

function invoiceSubscription(inv: Stripe.Invoice): string | null {
  const parent = (inv as unknown as { parent?: { subscription_details?: { subscription?: string | { id: string } } } }).parent;
  return idOf(parent?.subscription_details?.subscription ?? (inv as unknown as { subscription?: string | { id: string } }).subscription ?? null);
}

Deno.serve(async (req) => {
  if (req.method !== "POST") return new Response("POST only", { status: 405 });
  if (!KEY || !SIGNING) return new Response("not set up", { status: 503 });
  const signature = req.headers.get("stripe-signature");
  const body = await req.text();
  let event: Stripe.Event;
  try {
    event = await stripe.webhooks.constructEventAsync(body, signature ?? "", SIGNING, undefined, cryptoProvider);
  } catch {
    return new Response("Bad signature", { status: 400 });
  }
  if (!HANDLED_EVENTS.includes(event.type)) return new Response("ignored", { status: 200 });
  try {
    if (await seen(event.id)) return new Response("already done", { status: 200 });
    const obj = event.data.object as unknown as Record<string, unknown>;
    let note = "";
    if (event.type === "checkout.session.completed") {
      const s = event.data.object as Stripe.Checkout.Session;
      const subId = idOf(s.subscription as string | { id: string } | null);
      note = s.mode === "subscription" && subId ? await sync(subId) : "not a subscription";
    } else if (SUBSCRIPTION_EVENTS.includes(event.type)) {
      note = await sync((event.data.object as Stripe.Subscription).id);
    } else if (INVOICE_EVENTS.includes(event.type)) {
      const subId = invoiceSubscription(event.data.object as Stripe.Invoice);
      note = subId ? await sync(subId) : "no subscription";
    } else if (RISK_EVENTS.includes(event.type)) {
      // Refunds, disputes and fraud warnings need a person: they are logged for review, and Stripe emails the owner.
      note = "needs review";
      console.warn(`billing: ${event.type} ${String(obj.id)}`);
    }
    await record(event, typeof obj.id === "string" ? obj.id : null, note);
    return new Response("ok", { status: 200 });
  } catch (e) {
    // A 500 makes Stripe retry later; the event isn't recorded, so the retry is applied.
    console.error("stripe-webhook failed:", event.type, e instanceof Error ? e.message : String(e));
    return new Response("retry", { status: 500 });
  }
});
