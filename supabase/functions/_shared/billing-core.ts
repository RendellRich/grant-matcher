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
