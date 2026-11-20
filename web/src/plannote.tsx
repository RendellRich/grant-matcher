// "Your plan": how a paid plan is billed, what it costs and when it renews or ends (billing function, action
// "status"). Changes happen in Stripe's portal, behind Manage plan.
import { useEffect, useState } from "preact/hooks";
import { planStatus, type PlanStatus } from "./access";

const PLAN_NAME: Record<string, string> = { pro: "Pro", consultant: "Consultant" };
const day = (iso: string) => new Date(iso).toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" });
const money = (cents: number, currency: string) =>
  (cents / 100).toLocaleString("en-US", { style: "currency", currency: currency.toUpperCase(), minimumFractionDigits: cents % 100 ? 2 : 0 });

/** The plan line's sentences. */
export function planLines(s: PlanStatus): { text: string; warn?: boolean }[] {
  const name = PLAN_NAME[s.plan] ?? s.plan;
  const b = s.billing;
  if (!b) return [{ text: `${name} plan, at no charge.` }];
  const out: { text: string; warn?: boolean }[] = [];
  const per = b.interval === "year" ? "a year" : "a month";
  const how = b.interval ? `billed ${b.interval === "year" ? "yearly" : "monthly"}` : "";
  const cost = b.amount !== null ? `${money(b.amount, b.currency)} ${per}${b.founding ? " with your founding price" : ""}` : "";
  out.push({ text: `${name}${how ? `, ${how}` : ""}${cost ? `: ${cost}` : ""}.` });
  if (s.status === "past_due") out.push({ text: "Your last payment didn't go through. Update your card under Manage plan to keep your plan.", warn: true });
  if (b.endsAt) out.push({ text: `Ends on ${day(b.endsAt)}. You can turn it back on under Manage plan before then.` });
  else if (b.renewsAt) out.push({ text: `Renews on ${day(b.renewsAt)}.${b.changeBooked ? " A plan change you booked starts then." : ""}` });
  return out;
}

export function PlanNote({ email }: { email: string }) {
  const [s, setS] = useState<PlanStatus | null>(null);
  useEffect(() => { let live = true; void planStatus().then((r) => { if (live) setS(r); }); return () => { live = false; }; }, [email]);
  if (!s || !(s.plan in PLAN_NAME)) return null;
  return (
    <section class="note weekly" aria-label="Your plan">
      <h2 class="weekly-h">Your plan</h2>
      {planLines(s).map((l) => <p class={l.warn ? "warn-text" : undefined}>{l.text}</p>)}
    </section>
  );
}
