// A one-page plain-text summary of a grant, for a grant writer to paste into a document or another tool.
// Built only from what the card already shows, so it never says more than the data does.
import { callState, type Entry } from "./entries";
import { readySummary } from "./ready";

const SOURCE: Record<Entry["source"], string> = { fed: "Federal grant", fdn: "Foundation", fl: "State or local program" };
const STATE_WORD = { ok: "OK", check: "Check", no: "Stops you" } as const;
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const day = (d: Date) => `${MONTHS[d.getMonth()]} ${d.getDate()}, ${d.getFullYear()}`;

/** Text cut at a word near `n` characters, with an ellipsis when cut. */
function clip(s: string, n: number): string {
  const t = s.replace(/\s+/g, " ").trim();
  if (t.length <= n) return t;
  const cut = t.slice(0, n);
  const at = cut.lastIndexOf(" ");
  return `${(at > n * 0.6 ? cut.slice(0, at) : cut).replace(/[,;:.]$/, "")}...`;
}

function section(title: string, lines: string[]): string[] {
  return lines.length ? ["", title.toUpperCase(), ...lines] : [];
}

function sourceLabel(e: Entry): string {
  if (e.source === "fl" && / program$/.test(e.catalog)) return ""; // "County program" is already the catalog
  const call = e.source === "fl" ? callState(e.key) : null;
  if (call) return call.code === "DC" ? `${call.name} grant` : `${call.name} state grant`;
  return SOURCE[e.source];
}

/** One grant on one page. */
export function grantSummary(e: Entry, today: Date = new Date()): string {
  const covered = new Set(e.covered ?? []);
  const cautions = e.cautions.filter((x) => !covered.has(x));
  const notes = [...e.status, ...e.also].filter((x) => !covered.has(x));
  const out: string[] = [e.title, [sourceLabel(e), e.catalog, ...e.facts].filter(Boolean).join(" · ")];
  if (e.url) out.push(e.url);
  out.push("");
  if (e.side) out.push(e.sideQuiet ? `Size: ${e.side}` : e.side.startsWith("Due") || e.side.startsWith("Est.") ? `Deadline: ${e.side.replace(/^Due /, "")}` : e.side);
  out.push(`Grant Matcher score: ${e.score} of 100 (${e.tier === "Long shot" ? "long shot" : `${e.tier.toLowerCase()} match`})`);
  if (e.ready?.length) {
    out.push(...section(`Can we apply? ${readySummary(e.ready)}`, e.ready.map((c) => `- ${STATE_WORD[c.state]}: ${c.note}`)));
  }
  out.push(...section("Why it fits", e.fits.map((x) => `- ${x}`)));
  out.push(...section("Cautions", cautions.map((x) => `- ${x}`)));
  out.push(...section("Also", notes.map((x) => `- ${x}`)));
  const rows = (e.rows ?? []).map((r) => `${r.label}: ${r.href ? (r.linkText && !r.href.endsWith(r.linkText) ? `${r.linkText} (${r.href.replace(/^mailto:|^tel:/, "")})` : r.href.replace(/^mailto:|^tel:/, "")) : clip(r.text ?? "", 400)}`);
  out.push(...section(e.source === "fdn" ? "How to apply" : "Details", rows));
  if (e.summary) out.push(...section("Summary", [clip(e.summary, 900)]));
  if (e.eligibility) out.push(...section("Eligibility notes", [clip(e.eligibility, 500)]));
  if (e.grants?.length) {
    out.push(...section(`Largest grants (${e.grantsWhere || "latest return"})`,
      e.grants.slice(0, 5).map((g) => `- ${g.to}, ${g.place}, ${g.amount}${g.purpose ? `: ${clip(g.purpose, 120)}` : ""}`)));
  }
  out.push("", "---", `From Grant Matcher on ${day(today)}. Check the funder's own page before you apply; deadlines and rules change.`);
  return out.join("\n") + "\n";
}

/** Several summaries in one file, one after another. */
export function summariesFile(entries: Entry[], today: Date = new Date()): string {
  return entries.map((e) => grantSummary(e, today)).join("\n\n==========\n\n");
}

/** A file name from a grant's title. */
export function summaryFileName(e: Entry): string {
  const slug = e.title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 60) || "grant";
  return `${slug}-summary.txt`;
}
