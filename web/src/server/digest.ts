// The weekly email's content: which strong matches are new for a saved profile, and the email that lists them.
// Used by supabase/functions/weekly-email. Scores exactly the way a search does (preview.ts), so the email never
// lists a grant the page wouldn't show as a strong match.
import { noticeLines } from "../disclaimers";
import type { Entry, SourceKey } from "../entries";
import type { ProfileForm } from "../profile";
import type { RankSources } from "../rank";
import { preview } from "./preview";

/** What public.take_digest() returns for an account that is due. */
export interface DigestAccount {
  id: string;
  email: string;
  profile: unknown;
  vector: number[] | null;
  seen: string[] | null; // null: the email was just turned on, so only remember what matches now
  token: string;
  /** Consultant: one email per client, or one combined. */
  mode?: "each" | "combined";
  /** Consultant: the clients the email is on for, each with its saved profile. Null on Pro. */
  clients?: DigestClient[] | null;
}

export interface DigestClient { id: string; label: string; profile: unknown; vector: number[] | null; seen: string[] | null }

/** Most matches one email lists; the rest are counted. */
export const DIGEST_LIMIT = 15;

/** Every strong match now (`all`, to remember), and those not in `seen` (`fresh`), best first. */
export function newStrong(f: ProfileForm, src: RankSources, vector: number[] | null, seen: string[] | null,
  now: Date): { fresh: Entry[]; all: string[] } {
  const pv = preview(f, src, vector, now, Number.MAX_SAFE_INTEGER, true);
  const strong = Object.values(pv.lists).flatMap((l) => (l ?? []).filter((e) => e.tier === "Strong"))
    .sort((a, b) => b.score - a.score);
  const old = new Set(seen ?? []);
  return { fresh: strong.filter((e) => !old.has(e.key)), all: strong.map((e) => e.key) };
}

const LABEL: Record<SourceKey, string> = { fed: "Federal grant", fdn: "Foundation", fl: "State program" };

const esc = (s: string) => s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);

const shorten = (s: string, n: number) => (s.length > n ? `${s.slice(0, n - 1).trimEnd()}…` : s);

const why = (e: Entry) => e.fits[0] ?? "";

/** One list of matches, as table rows and as plain-text lines. */
function block(fresh: Entry[], site: string, limit: number): { html: string; text: string[] } {
  const shown = fresh.slice(0, limit);
  const more = fresh.length - shown.length;
  const notes = noticeLines(shown.map((e) => e.key));
  const html = shown.map((e) => `
    <tr><td style="padding:14px 0;border-top:1px solid #e0e2d9">
      <div style="font-size:12px;color:#5a5e53;text-transform:uppercase;letter-spacing:.04em">${esc(LABEL[e.source] ?? "")}${e.side ? ` &middot; ${esc(e.side)}` : ""}</div>
      <a href="${esc(e.url || site)}" style="font-size:17px;font-weight:600;color:#355025">${esc(e.title)}</a>
      ${why(e) ? `<div style="margin-top:4px;color:#23261f">${esc(why(e))}</div>` : ""}
    </td></tr>`).join("") + (more > 0 ? `<tr><td style="padding:14px 0;border-top:1px solid #e0e2d9">And ${more} more.</td></tr>` : "")
    + notes.map((n) => `<tr><td style="padding:12px 0;border-top:1px solid #e0e2d9;font-size:13px;color:#23261f">${esc(n)}</td></tr>`).join("");
  const text = [
    ...shown.flatMap((e) => [`${e.title}`, `${LABEL[e.source] ?? ""}${e.side ? ` | ${e.side}` : ""}`, ...(why(e) ? [why(e)] : []), e.url || site, ""]),
    ...(more > 0 ? [`And ${more} more.`, ""] : []),
    ...notes.flatMap((n) => [n, ""]),
  ];
  return { html, text };
}

const frame = (intro: string, rows: string, site: string, unsubscribe: string) => `<!DOCTYPE html><html><body style="margin:0;background:#fcfcfa">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:24px 16px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;font:16px/1.5 Arial,Helvetica,sans-serif;color:#23261f">
<tr><td style="font-weight:700;font-size:20px;padding-bottom:4px">Grant Matcher</td></tr>
<tr><td style="padding-bottom:12px">${intro}</td></tr>
${rows}
<tr><td style="padding:18px 0;border-top:1px solid #e0e2d9"><a href="${esc(site)}" style="display:inline-block;background:#55642a;color:#fff;padding:10px 16px;border-radius:6px;text-decoration:none;font-weight:600">See every match</a></td></tr>
<tr><td style="font-size:13px;color:#5a5e53">Always check each funder's own guidelines and deadlines before you apply.<br>
You get this because you turned on the weekly email in Grant Matcher. <a href="${esc(unsubscribe)}" style="color:#5a5e53">Turn it off</a>.<br>
Grant Matcher by Solutions by Rich LLC &middot; ren@solutionsbyrich.com</td></tr>
</table></td></tr></table></body></html>`;

const matches = (n: number) => (n === 1 ? "One new strong match" : `${n} new strong matches`);

/** One profile's email. On Consultant, `client` names the client it is for. */
export function digestEmail(f: ProfileForm, fresh: Entry[], site: string, unsubscribe: string, client?: string):
  { subject: string; html: string; text: string } {
  const n = fresh.length;
  const subject = `${n} new strong grant match${n === 1 ? "" : "es"} this week${client ? ` for ${shorten(client, 60)}` : ""}`;
  const about = f.mission.trim() ? shorten(f.mission.trim(), 120) : "your saved profile";
  const b = block(fresh, site, DIGEST_LIMIT);
  const html = frame(`${matches(n)} since last week for${client ? ` <strong>${esc(client)}</strong>` : ""}: <em>${esc(about)}</em>`, b.html, site, unsubscribe);
  const text = [
    `Grant Matcher: ${matches(n).toLowerCase()} since last week for${client ? ` ${client}` : ""}: ${about}`,
    "",
    ...b.text,
    `See every match: ${site}`,
    "",
    "Always check each funder's own guidelines and deadlines before you apply.",
    `Turn off this email: ${unsubscribe}`,
  ].join("\n");
  return { subject, html, text };
}

/** Consultant's combined email: a section for each client with new matches. */
export const COMBINED_LIMIT = 8;
export function combinedEmail(sections: { client: string; fresh: Entry[] }[], site: string, unsubscribe: string):
  { subject: string; html: string; text: string } {
  const withNew = sections.filter((s) => s.fresh.length);
  const n = withNew.reduce((t, s) => t + s.fresh.length, 0);
  const k = withNew.length;
  const subject = `${n} new strong grant match${n === 1 ? "" : "es"} this week across ${k} client${k === 1 ? "" : "s"}`;
  const rows = withNew.map((s) => {
    const b = block(s.fresh, site, COMBINED_LIMIT);
    return `<tr><td style="padding:22px 0 4px;font-size:18px;font-weight:700">${esc(s.client)} <span style="font-weight:400;color:#5a5e53;font-size:14px">${matches(s.fresh.length).toLowerCase()}</span></td></tr>${b.html}`;
  }).join("");
  const html = frame(`${matches(n)} since last week across your clients.`, rows, site, unsubscribe);
  const text = [
    `Grant Matcher: ${matches(n).toLowerCase()} since last week across your clients.`,
    "",
    ...withNew.flatMap((s) => [`== ${s.client}: ${matches(s.fresh.length).toLowerCase()} ==`, "", ...block(s.fresh, site, COMBINED_LIMIT).text]),
    `See every match: ${site}`,
    "",
    "Always check each funder's own guidelines and deadlines before you apply.",
    `Turn off this email: ${unsubscribe}`,
  ].join("\n");
  return { subject, html, text };
}
