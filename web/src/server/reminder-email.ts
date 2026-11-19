// The deadline reminder email: the shortlisted grants due in about two weeks or three days, in one message.
// Used by supabase/functions/deadline-reminders.

/** One account's reminders that are due to go out, from public.due_reminders(). */
export interface ReminderAccount {
  account_id: string;
  email: string;
  token: string;
  items: { key: string; title: string; url: string; source: string; stage: string; due: string; days: number }[];
}

const LABEL: Record<string, string> = { fed: "Federal grant", fdn: "Foundation", fl: "State program" };
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const esc = (s: string) => s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);
const day = (ymd: string) => { const [y, m, d] = ymd.split("-").map(Number); return `${MONTHS[m - 1]} ${d}, ${y}`; };
const when = (days: number) => (days === 0 ? "due today" : days === 1 ? "due tomorrow" : `due in ${days} days`);

export function reminderEmail(a: ReminderAccount, site: string, turnOff: string): { subject: string; html: string; text: string } {
  const items = [...a.items].sort((x, y) => x.days - y.days);
  const first = items[0];
  const subject = items.length === 1
    ? `Grant deadline ${when(first.days)}: ${first.title.length > 70 ? `${first.title.slice(0, 69).trimEnd()}…` : first.title}`
    : `${items.length} grant deadlines coming up, the first ${when(first.days)}`;
  const rows = items.map((x) => `
    <tr><td style="padding:14px 0;border-top:1px solid #e0e2d9">
      <div style="font-size:12px;color:#5a5e53;text-transform:uppercase;letter-spacing:.04em">${esc(LABEL[x.source] ?? "Grant")} &middot; ${esc(x.stage === "applying" ? "Applying" : "Saved")}</div>
      <a href="${esc(x.url || site)}" style="font-size:17px;font-weight:600;color:#355025">${esc(x.title)}</a>
      <div style="margin-top:4px;color:#23261f"><strong>${esc(day(x.due))}</strong>, ${esc(when(x.days))}</div>
    </td></tr>`).join("");
  const html = `<!DOCTYPE html><html><body style="margin:0;background:#fcfcfa">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:24px 16px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;font:16px/1.5 Arial,Helvetica,sans-serif;color:#23261f">
<tr><td style="font-weight:700;font-size:20px;padding-bottom:4px">Grant Matcher</td></tr>
<tr><td style="padding-bottom:12px">${items.length === 1 ? "A deadline on your shortlist is coming up." : "Deadlines on your shortlist are coming up."}</td></tr>
${rows}
<tr><td style="padding:18px 0;border-top:1px solid #e0e2d9"><a href="${esc(site)}" style="display:inline-block;background:#55642a;color:#fff;padding:10px 16px;border-radius:6px;text-decoration:none;font-weight:600">Open your shortlist</a></td></tr>
<tr><td style="font-size:13px;color:#5a5e53">Dates are the ones you set, or the listed deadline. Always confirm with the funder.<br>
Mark a grant Submitted on your shortlist and its reminders stop. You get these because you turned on deadline reminders in Grant Matcher. <a href="${esc(turnOff)}" style="color:#5a5e53">Turn them off</a>.<br>
Grant Matcher by Solutions by Rich LLC &middot; ren@solutionsbyrich.com</td></tr>
</table></td></tr></table></body></html>`;
  const text = [
    items.length === 1 ? "Grant Matcher: a deadline on your shortlist is coming up." : "Grant Matcher: deadlines on your shortlist are coming up.",
    "",
    ...items.flatMap((x) => [x.title, `${day(x.due)}, ${when(x.days)}`, x.url || site, ""]),
    `Open your shortlist: ${site}`,
    "",
    "Mark a grant Submitted on your shortlist and its reminders stop.",
    `Turn off deadline reminders: ${turnOff}`,
  ].join("\n");
  return { subject, html, text };
}
