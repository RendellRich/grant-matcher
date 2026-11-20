// The parts of billing that don't talk to Stripe or the database, so they can be tested on their own
// (web/test/billing.test.ts). Used by supabase/functions/billing and supabase/functions/stripe-webhook.

/** Each plan's monthly and yearly prices, found in Stripe by lookup key so test and live mode need no settings. */
export const LOOKUP_KEYS = {
  pro: { month: "gm_pro_monthly", year: "gm_pro_yearly" },
  consultant: { month: "gm_consultant_monthly", year: "gm_consultant_yearly" },
} as const;
export type PaidPlan = keyof typeof LOOKUP_KEYS;
export type Interval = "month" | "year";

export const isPaidPlan = (p: unknown): p is PaidPlan => p === "pro" || p === "consultant";
/** Monthly unless the page asked for yearly. */
export const intervalOf = (i: unknown): Interval => (i === "year" ? "year" : "month");

export const lookupKeyFor = (plan: PaidPlan, interval: Interval): string => LOOKUP_KEYS[plan][interval];

export function planForLookupKey(key: string | null | undefined): PaidPlan | null {
  for (const [plan, keys] of Object.entries(LOOKUP_KEYS)) if (Object.values(keys).includes(key as never)) return plan as PaidPlan;
  return null;
}

/**
 * Promotion codes only on monthly checkouts. The founding coupon is $10 off every invoice, which is the
 * $29 founding price on monthly but would only take $10 off a whole year.
 */
export const promoCodesAllowed = (interval: Interval): boolean => interval === "month";

/** The part of a Stripe Subscription the account needs. */
export interface SubscriptionView {
  id: string;
  customer: string;
  status: string;
  items: { price: { lookup_key: string | null } }[];
  /** Coupon ids of the discounts on the subscription. */
  coupons: string[];
}

/** Coupons whose ids start with this are founding prices (FOUNDING_PRO, FOUNDING_CONSULTANT). */
export const FOUNDING_PREFIX = "FOUNDING";

/** What the account row should say for this subscription. A plan that has ended goes back to free. */
export function accountPatch(sub: SubscriptionView): { plan: string; status: string; stripe_subscription_id: string | null; founding: boolean } {
  const ended = ["canceled", "incomplete_expired"].includes(sub.status);
  const plan = sub.items.map((i) => planForLookupKey(i.price.lookup_key)).find(Boolean) ?? null;
  if (ended || !plan) return { plan: "free", status: sub.status, stripe_subscription_id: ended ? null : sub.id, founding: false };
  return {
    plan, status: sub.status, stripe_subscription_id: sub.id,
    founding: sub.coupons.some((c) => c.toUpperCase().startsWith(FOUNDING_PREFIX)),
  };
}

/** Events the webhook acts on. Anything else is acknowledged and ignored. */
export const SUBSCRIPTION_EVENTS = ["customer.subscription.created", "customer.subscription.updated", "customer.subscription.deleted"];
export const INVOICE_EVENTS = ["invoice.paid", "invoice.payment_failed"];
export const RISK_EVENTS = ["charge.dispute.created", "charge.refunded", "radar.early_fraud_warning.created"];
export const HANDLED_EVENTS = ["checkout.session.completed", ...SUBSCRIPTION_EVENTS, ...INVOICE_EVENTS, ...RISK_EVENTS];

/** A label for Checkout sessions, so this flow can be told apart in the Stripe dashboard. */
export const CHECKOUT_LABEL = "grant-matcher-upgrade-qvmrtkse";

// ---------- what the page shows about a paid plan ("Your plan") ----------

/** The founding coupons' discount, for when Stripe sends only the coupon's id (the restricted key can't read coupons). */
export const FOUNDING_OFF: Record<PaidPlan, number> = { pro: 1000, consultant: 2000 };

/** The part of a Stripe Subscription the plan line needs. Times are Unix seconds. */
export interface PlanSource {
  status: string;
  cancel_at_period_end: boolean;
  cancel_at: number | null;
  schedule: string | null; // set when a change is booked for the end of the period (yearly to monthly)
  items: { current_period_end?: number | null; price: { lookup_key: string | null; unit_amount: number | null; currency: string; recurring?: { interval: string } | null } }[];
  /** Each discount's coupon, as an id or with its amounts. */
  coupons: ({ id: string; amount_off?: number | null; percent_off?: number | null } | string)[];
}

export interface PlanView {
  plan: PaidPlan | null;
  status: string;
  interval: Interval | null;
  /** What each payment costs after discounts, in cents. */
  amount: number | null;
  currency: string;
  founding: boolean;
  /** ISO date of the next payment, unless the plan is set to end. */
  renewsAt: string | null;
  /** ISO date the plan ends, when it was cancelled at the end of the period. */
  endsAt: string | null;
  changeBooked: boolean;
}

const iso = (s: number | null | undefined) => (s ? new Date(s * 1000).toISOString() : null);

export function planView(sub: PlanSource): PlanView {
  const item = sub.items.find((i) => planForLookupKey(i.price.lookup_key)) ?? sub.items[0];
  const plan = item ? planForLookupKey(item.price.lookup_key) : null;
  const iv = item?.price.recurring?.interval;
  let amount = item?.price.unit_amount ?? null;
  let founding = false;
  for (const c of sub.coupons) {
    const id = typeof c === "string" ? c : c.id;
    const isFounding = id.toUpperCase().startsWith(FOUNDING_PREFIX);
    founding ||= isFounding;
    if (amount === null) continue;
    if (typeof c !== "string" && c.amount_off) amount -= c.amount_off;
    else if (typeof c !== "string" && c.percent_off) amount = Math.round(amount * (1 - c.percent_off / 100));
    else if (isFounding && plan) amount -= FOUNDING_OFF[plan];
  }
  const periodEnd = iso(item?.current_period_end);
  const ending = sub.cancel_at_period_end || sub.cancel_at !== null;
  return {
    plan, status: sub.status, interval: iv === "year" ? "year" : iv === "month" ? "month" : null,
    amount: amount === null ? null : Math.max(0, amount), currency: item?.price.currency ?? "usd", founding,
    renewsAt: ending ? null : periodEnd,
    endsAt: ending ? (iso(sub.cancel_at) ?? periodEnd) : null,
    changeBooked: Boolean(sub.schedule) && !ending,
  };
}
