// The "Your plan" line: billing-core's planView reads the Stripe subscription, plannote's planLines words it.
import { describe, expect, it } from "vitest";
import { planView, type PlanSource } from "../../supabase/functions/_shared/billing-core";
import { planLines } from "../src/plannote";

const end = Date.UTC(2027, 10, 20, 15) / 1000;
const sub = (over: Partial<PlanSource> = {}): PlanSource => ({
  status: "active", cancel_at_period_end: false, cancel_at: null, schedule: null, coupons: [],
  items: [{ current_period_end: end, price: { lookup_key: "gm_pro_yearly", unit_amount: 39000, currency: "usd", recurring: { interval: "year" } } }],
  ...over,
});
const monthly = { current_period_end: end, price: { lookup_key: "gm_pro_monthly", unit_amount: 3900, currency: "usd", recurring: { interval: "month" } } };

describe("plan line", () => {
  it("reads the interval, price and renewal date", () => {
    expect(planView(sub())).toMatchObject({ plan: "pro", interval: "year", amount: 39000, founding: false, endsAt: null, changeBooked: false });
    expect(planView(sub()).renewsAt?.slice(0, 10)).toBe("2027-11-20");
  });
  it("takes discounts off, including a founding coupon known only by its id", () => {
    expect(planView(sub({ items: [monthly], coupons: ["FOUNDING_PRO"] }))).toMatchObject({ amount: 2900, founding: true });
    expect(planView(sub({ coupons: [{ id: "FOUNDING_PRO", amount_off: 1000 }] })).amount).toBe(38000);
    expect(planView(sub({ coupons: [{ id: "HALF", percent_off: 50 }] })).amount).toBe(19500);
  });
  it("says when a plan ends instead of renewing, and notes a booked change", () => {
    expect(planView(sub({ cancel_at_period_end: true }))).toMatchObject({ renewsAt: null, changeBooked: false });
    expect(planView(sub({ cancel_at_period_end: true })).endsAt?.slice(0, 10)).toBe("2027-11-20");
    expect(planView(sub({ schedule: "sub_sched_1" })).changeBooked).toBe(true);
  });
  it("words it plainly", () => {
    const view = planView(sub({ items: [monthly], coupons: ["FOUNDING_PRO"] }));
    expect(planLines({ plan: "pro", status: "active", billing: view }).map((l) => l.text)).toEqual([
      "Pro, billed monthly: $29 a month with your founding price.", "Renews on November 20, 2027.",
    ]);
    expect(planLines({ plan: "pro", status: "active", billing: planView(sub()) })[0].text).toBe("Pro, billed yearly: $390 a year.");
    const ending = planLines({ plan: "pro", status: "active", billing: planView(sub({ cancel_at_period_end: true })) });
    expect(ending[1].text).toMatch(/^Ends on November 20, 2027\./);
    const late = planLines({ plan: "pro", status: "past_due", billing: planView(sub()) });
    expect(late[1]).toMatchObject({ warn: true });
    expect(planLines({ plan: "consultant", status: "active", billing: null })[0].text).toBe("Consultant plan, at no charge.");
  });
});
