// Deadline reminders. pg_cron calls this every ten minutes from 8 to 11 am Eastern with the job's token
// (private.job_tokens). Each call takes up to 25 accounts with reminders due today (public.due_reminders),
// sends each one email listing them (web/src/server/reminder-email.ts) and marks them sent, so a reminder
// goes out once. POST ?off=<token> turns reminders off (the page's confirm button, and one-click).
//
// Secrets: RESEND_API_KEY. Built into one file by `npm run build:reminders` in web/.
import { reminderEmail, type ReminderAccount } from "../../../web/src/server/reminder-email";

declare const Deno: {
  env: { get(name: string): string | undefined };
  serve(handler: (req: Request) => Response | Promise<Response>): void;
};

const BASE = (Deno.env.get("SUPABASE_URL") ?? "").replace(/\/$/, "");
const SERVICE = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "";
const RESEND = Deno.env.get("RESEND_API_KEY") ?? "";
const FROM = Deno.env.get("DIGEST_FROM") ?? "Grant Matcher <noreply@solutionsbyrich.com>";
const SITE = Deno.env.get("SITE_URL") ?? "https://rendellrich.github.io/grant-matcher/";
const service = { Authorization: `Bearer ${SERVICE}`, apikey: SERVICE, "Content-Type": "application/json" };

async function rpc<T>(name: string, args: Record<string, unknown> = {}): Promise<T> {
  const res = await fetch(`${BASE}/rest/v1/rpc/${name}`, { method: "POST", headers: service, body: JSON.stringify(args) });
  if (!res.ok) throw new Error(`${name} ${res.status}`);
  const text = await res.text();
  return (text ? JSON.parse(text) : null) as T;
}

const CORS = { "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "content-type", "Access-Control-Allow-Methods": "POST, OPTIONS" };
const say = (text: string, status = 200) => new Response(text, { status, headers: { ...CORS, "Content-Type": "text/plain; charset=utf-8" } });

export async function handle(req: Request): Promise<Response> {
  const off = new URL(req.url).searchParams.get("off");
  if (off !== null) {
    if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
    if (req.method !== "POST") return say("To turn off deadline reminders, use the link in the email and press the button.", 405);
    if (!/^[0-9a-f-]{36}$/i.test(off)) return say("That link isn't right.", 400);
    return say((await rpc<boolean>("reminders_off", { p_token: off })) ? "off" : "already off");
  }
  if (req.method !== "POST") return new Response("POST only", { status: 405 });
  const token = req.headers.get("x-job-token") ?? "";
  if (!token || !(await rpc<boolean>("check_job_token", { p_name: "deadline-reminders", p_token: token }))) {
    return new Response("not allowed", { status: 401 });
  }
  if (!RESEND) return new Response("not set up", { status: 503 });
  const due = (await rpc<ReminderAccount[]>("due_reminders", { p_limit: 25 })) ?? [];
  let sent = 0, failed = 0;
  for (const a of due) {
    try {
      const oneClick = `${BASE}/functions/v1/deadline-reminders?off=${a.token}`;
      const mail = reminderEmail(a, SITE, `${SITE}?reminders-off=${a.token}`);
      const res = await fetch("https://api.resend.com/emails", {
        method: "POST",
        headers: { Authorization: `Bearer ${RESEND}`, "Content-Type": "application/json" },
        body: JSON.stringify({
          from: FROM, to: [a.email], reply_to: "ren@solutionsbyrich.com", subject: mail.subject, html: mail.html, text: mail.text,
          headers: { "List-Unsubscribe": `<${oneClick}>`, "List-Unsubscribe-Post": "List-Unsubscribe=One-Click" },
        }),
      });
      if (!res.ok) throw new Error(`resend ${res.status} ${(await res.text()).slice(0, 200)}`);
      await rpc("mark_reminders", { p_account: a.account_id, p_keys: a.items.map((x) => x.key) });
      sent++;
    } catch (e) {
      failed++;
      console.error("deadline-reminders failed:", a.account_id, e instanceof Error ? e.message : String(e));
    }
  }
  return new Response(due.length ? `sent ${sent}${failed ? `, failed ${failed}` : ""}` : "none due", { status: failed && !sent ? 500 : 200 });
}

if (typeof Deno !== "undefined" && typeof Deno.serve === "function") Deno.serve(handle);
