// What the Stripe webhook writes to an account (supabase/functions/_shared/billing-core.ts).
import { describe, expect, it } from "vitest";
import { accountPatch, HANDLED_EVENTS, isPaidPlan, planForLookupKey, type SubscriptionView } from "../../supabase/functions/_shared/billing-core";

const sub = (over: Partial<SubscriptionView> = {}): SubscriptionView => ({
  id: "sub_synthetic1", customer: "cus_synthetic1", status: "active",
  items: [{ price: { lookup_key: "gm_pro_monthly" } }], coupons: [], ...over,
});

describe("billing", () => {
  it("knows the two paid plans by their price lookup keys", () => {
    expect(planForLookupKey("gm_pro_monthly")).toBe("pro");
    expect(planForLookupKey("gm_consultant_monthly")).toBe("consultant");
    expect(planForLookupKey("something_else")).toBeNull();
    expect(planForLookupKey(null)).toBeNull();
    expect(isPaidPlan("pro")).toBe(true);
    expect(isPaidPlan("free")).toBe(false);
  });
  it("sets the plan and status from an active subscription", () => {
    expect(accountPatch(sub())).toEqual({ plan: "pro", status: "active", stripe_subscription_id: "sub_synthetic1", founding: false });
    expect(accountPatch(sub({ items: [{ price: { lookup_key: "gm_consultant_monthly" } }] })).plan).toBe("consultant");
  });
  it("marks a founding price from its coupon", () => {
    expect(accountPatch(sub({ coupons: ["FOUNDING_PRO"] })).founding).toBe(true);
    expect(accountPatch(sub({ coupons: ["SOMEOTHER"] })).founding).toBe(false);
  });
  it("keeps the plan while a renewal is being retried, and drops to free when it ends", () => {
    expect(accountPatch(sub({ status: "past_due" }))).toMatchObject({ plan: "pro", status: "past_due" });
    expect(accountPatch(sub({ status: "canceled" }))).toEqual({ plan: "free", status: "canceled", stripe_subscription_id: null, founding: false });
    expect(accountPatch(sub({ status: "incomplete_expired" })).plan).toBe("free");
  });
  it("never grants a plan for a price it doesn't know", () => {
    expect(accountPatch(sub({ items: [{ price: { lookup_key: "other_product" } }] })).plan).toBe("free");
  });
  it("handles the lifecycle and risk events, and nothing else", () => {
    for (const t of ["checkout.session.completed", "customer.subscription.updated", "customer.subscription.deleted", "invoice.paid",
      "invoice.payment_failed", "charge.dispute.created", "charge.refunded", "radar.early_fraud_warning.created"]) expect(HANDLED_EVENTS).toContain(t);
    expect(HANDLED_EVENTS).not.toContain("customer.created");
  });
});
