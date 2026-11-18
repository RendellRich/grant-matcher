// Turns scored records from each source into one shape the result list draws.
import {
  asks501c3, fmtDate, money, type CompanyGiving, type FederalExtra, type FederalRec, type FloridaRec, type FoundationOut, type Scored, type Tier, type WebsiteCycle,
} from "./score";
import { SUPPORT_TYPES, splitList, type ProfileForm } from "./profile";

export type SourceKey = "fl" | "fdn" | "fed";

export interface DetailRow { label: string; text?: string; href?: string; linkText?: string }

export interface GrantRow { to: string; place: string; amount: string; purpose: string }

export interface Entry {
  key: string; // "fed:355824"; also the shortlist key
  source: SourceKey;
  title: string;
  url: string;
  catalog: string; // the record's own number, shown first in the facts line
  facts: string[];
  side: string; // the right-aligned figure: a deadline, or a typical grant size
  sideQuiet?: boolean; // a size, not a date
  score: number;
  tier: Tier;
  fits: string[];
  cautions: string[];
  also: string[];
  status: string[];
  summary?: string;
  eligibility?: string;
  rows?: DetailRow[];
  noApplyInfo?: boolean;
  grants?: GrantRow[];
  grantsWhere?: string;
  sortClose?: number | null;
  sortAward?: number | null;
  sortInState?: number;
  sortMedian?: number | null;
  // for the filters, which narrow the list and never change a score
  agency?: string;
  amountLow?: number | null; // federal award floor (or ceiling when no floor)
  amountHigh?: number | null; // federal award ceiling (or floor when no ceiling)
  publishesApply?: boolean;
  closedToUnsolicited?: boolean;
  local?: boolean; // based in, or has funded groups in, one of the person's cities
  asks501c3?: boolean; // a foundation whose how-to-apply text asks for 501(c)(3) status
  isNew?: boolean; // in the data now but not at the person's last visit (set by the app, not the scorer)
  cycle?: WebsiteCycle["s"]; // what a foundation's website said at the last weekly check
  support?: string[]; // kinds of support its text describes (general operating, program...), from terms.json
  kind?: string; // a foundation's kind: private, community, public, United Way
  corp?: string; // the company behind a company foundation (data/corporate.json)
  reach?: "national" | "state" | ""; // a foundation that gives in 5 or more states, or mostly in the person's state
  forecast?: boolean; // a federal forecast, not open yet
}

const SUPPORT = SUPPORT_TYPES.map((t) => [t.id, new RegExp(t.pattern, "i")] as const);
/** The kinds of support a grant's or funder's own words describe. */
export function supportIn(text: string): string[] {
  return SUPPORT.filter(([, re]) => re.test(text)).map(([id]) => id);
}

const STATUS = ["Forecast, not open yet"];
const FIT = ["Mentions ", "Past grants mention ", "In your categories", "Funded ", "Based in "];
const WORDS = ["Mentions ", "Past grants mention "];

/** Reasons about the person's work first, then cautions, then plain facts, as the app's why(). */
function sortReasons(reasons: string[], cautionsIn: string[], wordsIn: string, hasKeywords: boolean) {
  const status = reasons.filter((x) => STATUS.some((p) => x.startsWith(p)));
  const fits = reasons.filter((x) => FIT.some((p) => x.startsWith(p)) || x.includes(" grants went to ") || x.startsWith("Its only grant"));
  const also = reasons.filter((x) => !fits.includes(x) && !status.includes(x));
  const cautions = [...cautionsIn];
  if (wordsIn && hasKeywords && !reasons.some((x) => WORDS.some((p) => x.startsWith(p)))) {
    cautions.unshift(`None of your key words appear in ${wordsIn}`);
  }
  return { fits, cautions, also, status };
}

const present = (v: unknown) => {
  const t = typeof v === "string" ? v.trim() : "";
  return ["", "NONE", "N/A", "NA", "NOT APPLICABLE", "0", "-", "NULL"].includes(t.toUpperCase()) ? "" : t;
};

const safeUrl = (u: unknown) => {
  const s = present(u);
  return /^https?:\/\//i.test(s) ? s : "";
};

export function siteHref(site: string): string {
  if (!site) return "";
  return /^https?:\/\//i.test(site) ? site : `https://${site}`;
}

function phone(v: string): DetailRow | null {
  let d = v.replace(/\D/g, "");
  if (d.length === 11 && d.startsWith("1")) d = d.slice(1);
  if (!v) return null;
  if (d.length !== 10) return { label: "Phone", text: v };
  return { label: "Phone", linkText: `${d.slice(0, 3)}-${d.slice(3, 6)}-${d.slice(6)}`, href: `tel:+1${d}` };
}

const plural = (n: number, noun: string) => `${n.toLocaleString("en-US")} ${n === 1 ? noun : noun + "s"}`;

export function federalEntry(s: Scored<FederalRec & FederalExtra>, hasKw: boolean): Entry {
  const r = s.rec;
  const label = r.status === "forecasted" ? "Est. due" : "Due";
  const why = sortReasons(s.reasons, s.cautions, "its description", hasKw);
  const desc = r.description || "";
  return {
    key: `fed:${r.id}`, source: "fed", title: r._title || r.title, url: safeUrl(r.url), catalog: r.number,
    facts: [r.agency, `Award ${r.award_range}`],
    side: r.close ? `${label} ${fmtDate(r.close)}` : "No close date",
    score: s.score, tier: s.tier, ...why,
    // the date is already in the right-hand column; the CSV keeps the scorer's full wording
    status: why.status.map((x) => (r.close ? x.replace(/ \(estimated due [^)]*\)/, "") : x)),
    summary: desc.slice(0, 1500) + (desc.length > 1500 ? "..." : ""),
    eligibility: r.eligibility_text ? r.eligibility_text.slice(0, 800) : "",
    sortClose: r.close ? r.close.getTime() : null,
    sortAward: r.award_ceiling ?? null,
    agency: r.agency,
    amountLow: (r.award_floor && r.award_floor > 0 ? r.award_floor : null) ?? (r.award_ceiling || null),
    amountHigh: (r.award_ceiling && r.award_ceiling > 0 ? r.award_ceiling : null) ?? (r.award_floor || null),
    support: supportIn(`${r.title} ${desc}`),
    forecast: r.status === "forecasted",
  };
}

const ymdDate = (d: string) => new Date(+d.slice(0, 4), +d.slice(5, 7) - 1, +d.slice(8, 10));
const shortDay = (d: string) => ymdDate(d).toLocaleDateString("en-US", { month: "short", day: "numeric" });

/** What a foundation's website said at the last weekly check, as a line for the card and rows for its details.
 *  Its words are quoted with the date, since a page can change after it was read. */
export function websiteFindings(c: WebsiteCycle | undefined, today: Date = new Date()): {
  line?: string; caution?: string; rows: DetailRow[]; due: number | null;
} {
  if (!c || !/^\d{4}-\d{2}-\d{2}/.test(c.at ?? "")) return { rows: [], due: null };
  const checked = ` (website checked ${shortDay(c.at)})`;
  const t0 = new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime();
  const due = c.d && /^\d{4}-\d{2}-\d{2}$/.test(c.d) && ymdDate(c.d).getTime() >= t0 ? ymdDate(c.d) : null;
  const rows: DetailRow[] = [];
  if (c.q) rows.push({ label: "On its website", text: `“${c.q}”` });
  const href = c.u ? safeUrl(c.u) : "";
  if (href) rows.push({ label: c.s === "apply" ? "Application link" : "Page checked", href, linkText: href.split("://")[1].replace(/\/$/, "").slice(0, 70) });
  const out = { rows, due: due ? due.getTime() : null };
  if (c.s === "open") return { ...out, line: `Its website says applications are open${due ? `, deadline ${fmtDate(due)}` : ""}${checked}` };
  if (c.s === "deadline") return due ? { ...out, line: `Its website gives a deadline of ${fmtDate(due)}${checked}` } : { rows: [], due: null };
  if (c.s === "apply") return { ...out, line: `Its website has an application link${checked}` };
  return { ...out, caution: `Its website says it isn't taking new requests now${checked}` };
}

/** A company foundation's program, as detail rows and a short amount for the right-hand column. */
export function companyRows(c: CompanyGiving | undefined): { rows: DetailRow[]; side?: string; line?: string } {
  const p = c?.program;
  if (!c || !p) return { rows: [] };
  const rows: DetailRow[] = [{ label: "Company program", text: p.name }];
  const add = (label: string, text?: string) => { if (text) rows.push({ label, text }); };
  add("Who can apply", p.who);
  add("Amount", p.amount);
  add("When to apply", p.when);
  add("How to apply", p.how);
  add("Focus", p.focus);
  const href = safeUrl(p.url);
  if (href) rows.push({ label: "Program page", href, linkText: href.split("://")[1].replace(/\/$/, "").slice(0, 70) });
  if (/^\d{4}-\d{2}-\d{2}$/.test(p.checked)) {
    rows.push({ label: "Source", text: `Entered by hand from ${c.company}'s giving page, checked ${fmtDate(ymdDate(p.checked))}` });
  }
  const range = /^\$[\d,]+ to \$[\d,]+$/.test(p.amount) ? p.amount : "";
  return { rows, side: range ? `Grants ${range}` : undefined, line: `Runs ${p.name}${range ? `, ${range}` : ""}` };
}

export function foundationEntry(s: Scored<FoundationOut>, state: string, hasKw: boolean): Entry {
  const r = s.rec;
  const company = companyRows(r._corp);
  const a = r._apply ?? {};
  const why = sortReasons(s.reasons, s.cautions, "its past grants", hasKw);
  const web = websiteFindings(r._cycle);
  if (web.line || web.caution) why.also = why.also.filter((x) => x !== "Check its website for open grant cycles"); // already checked
  if (web.line) why.status.unshift(web.line);
  if (company.line) why.status.unshift(company.line);
  if (web.caution) why.cautions.push(web.caution);
  const site = siteHref(r._site ?? "");
  const rows: DetailRow[] = [...company.rows];
  const add = (label: string, text?: string) => { if (text) rows.push({ label, text }); };
  add("Mission", r._mission);
  add("Contact", a.contact);
  const ph = phone(a.phone ?? "");
  if (ph) rows.push(ph);
  if (a.email) rows.push(a.email.includes("@") && !a.email.includes(" ")
    ? { label: "Email", linkText: a.email, href: `mailto:${a.email}` } : { label: "Email", text: a.email });
  add("Address", a.address);
  add("What to send", a.materials);
  add("Deadlines", a.deadlines);
  add("Restrictions", a.restrictions);
  if (site) rows.push({ label: "Website", href: site, linkText: site.split("://")[1].replace(/\/$/, "").toLowerCase() });
  rows.push(...web.rows);
  if (safeUrl(r.url)) rows.push({ label: "Tax filings", href: r.url, linkText: "ProPublica Nonprofit Explorer" });
  const grants = (r.sample_grants || []).filter((g) => g && typeof g === "object").slice(0, 8);
  const local = grants.filter((g) => g.state === state).length;
  return {
    key: `fdn:${r.ein}`, source: "fdn", title: r._name || r.name, url: site || safeUrl(r.url),
    catalog: `EIN ${r.ein.length === 9 ? r.ein.slice(0, 2) + "-" + r.ein.slice(2) : r.ein}`,
    facts: [r._corp ? `Company foundation (${r._corp.company})` : r.kind ?? "Private foundation", `${r._city || r.city}, ${r.state}`,
      `${plural(r.grant_count ?? 0, "grant")}, ${money(r.grants_total)} total`, `tax year ${r.tax_year}`],
    side: company.side ?? `Typical ${money(r.grant_median)}`, sideQuiet: true,
    score: s.score, tier: s.tier, ...why, rows,
    noApplyInfo: !(a.contact || a.materials || a.deadlines),
    grants: grants.map((g) => ({
      to: g._to || g.to, place: `${g._city || g.city}, ${g.state}`,
      amount: `$${Math.round(Number(g.amount) || 0).toLocaleString("en-US")}`, purpose: g._purpose || "",
    })),
    grantsWhere: grants.length ? (local === grants.length ? `all in ${state}` : `${local} of ${grants.length} in ${state}`) : "",
    sortInState: r.in_state, sortMedian: r.grant_median ?? null,
    sortClose: web.due, // a deadline from its website, which the shortlist counts down to
    cycle: web.line || web.caution ? r._cycle!.s : undefined,
    support: supportIn([...r.top_purposes, ...(r.sample_grants || []).map((g) => g?.purpose ?? ""), r._mission ?? ""].join(" ")),
    kind: r.kind ?? "Private foundation",
    corp: r._corp?.company,
    reach: Object.values(r.recipient_states ?? {}).filter(Boolean).length >= 5 ? "national"
      : (r.grant_count ? r.in_state / r.grant_count >= 0.5 : false) ? "state" : "",
    publishesApply: s.reasons.includes("Publishes how to apply"),
    closedToUnsolicited: s.cautions.includes("Says it does not accept unsolicited requests"),
    local: s.reasons.some((x) => x.startsWith("Funded ") || x.startsWith("Based in ")),
    asks501c3: asks501c3(s.rec),
  };
}

/** A county or city program's window (grantmatch/local.py): its due date, and a line while it isn't open yet. */
export function localWindow(r: FloridaRec, today: Date = new Date()): { due: number | null; line?: string } {
  const t0 = new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime();
  const day = (d?: string | null) => (d && /^\d{4}-\d{2}-\d{2}$/.test(d) ? ymdDate(d) : null);
  const opens = day(r.opens), closes = day(r.closes);
  const due = closes && closes.getTime() >= t0 ? closes.getTime() : null;
  if (opens && opens.getTime() > t0) return { due, line: `Applications open ${fmtDate(opens)}` };
  return { due, line: due ? "Taking applications now" : undefined };
}

export function floridaEntry(s: Scored<FloridaRec>, hasKw: boolean): Entry {
  const r = s.rec;
  const why = sortReasons(s.reasons, s.cautions, "its title or objectives", hasKw);
  const local = Boolean(r.level);
  const win = local ? localWindow(r) : { due: null };
  const site = local ? websiteFindings(r._cycle) : { rows: [] as DetailRow[], due: null, line: undefined, caution: undefined };
  if (win.line) why.status.unshift(win.line);
  if (site.line) why.status.push(site.line);
  if (site.caution) why.cautions.push(site.caution);
  const due = win.due ?? site.due;
  const rows: DetailRow[] = [];
  for (const [label, key] of [["Objectives", "objectives"], ["Who can apply", "applicant_types"], ["How to apply", "application"],
    ["How awards are made", "award"], ["Deadlines", "deadlines"], ["Restrictions", "restrictions"], ["Contact", "contact"]] as const) {
    const t = present(r[key]).slice(0, 900);
    if (t) rows.push({ label, text: t });
  }
  const web = present(r.web);
  if (web && !web.includes(" ") && web.includes(".")) {
    const href = siteHref(web);
    rows.push({ label: "Agency site", href, linkText: href.split("://")[1].replace(/\/$/, "").toLowerCase() });
  }
  if (local) {
    rows.push(...site.rows);
    if (r.checked && /^\d{4}-\d{2}-\d{2}$/.test(r.checked)) {
      rows.push({ label: "Source", text: `Entered by hand from the program's own page, checked ${fmtDate(ymdDate(r.checked))}` });
    }
  }
  return {
    key: `fl:${r.id}`, source: "fl", title: r._title || r.title, url: safeUrl(r.url),
    catalog: local ? `${r.level} program` : `CSFA ${r.csfa}`,
    facts: [r.agency, local ? r.area || "" : r._assist || ""].filter(Boolean),
    side: due ? `Due ${fmtDate(new Date(due))}` : "", agency: r.agency,
    sortClose: due,
    score: s.score, tier: s.tier, ...why, rows,
    support: supportIn(`${r.title} ${r.objectives}`),
  };
}

// ---------- filters ----------

export interface Narrow {
  q: string; // words to find anywhere in an entry
  size: string; // "" or a band key from SIZE_BANDS
  before: string; // "" or yyyy-mm-dd: federal deadlines on or before this day
  agency: string; // "" or an agency name
  apply: boolean; // foundations that publish how to apply
  open: boolean; // foundations that don't say no to unsolicited requests
  local: boolean; // foundations based in or funding groups in the person's cities
  no501: boolean; // hide foundations that ask for 501(c)(3) status
  fresh: boolean; // only entries that are new since the last visit
  cycle: boolean; // foundations whose website says applications are open or gives a deadline ahead
  reach: "" | "state" | "national"; // foundations by where they give
  corp?: boolean; // only company foundations (data/corporate.json)
}

export const NO_NARROW: Narrow = {
  q: "", size: "", before: "", agency: "", apply: false, open: false, local: false, no501: false, fresh: false, cycle: false, reach: "",
};

export const SIZE_BANDS: Record<string, [string, number, number]> = {
  s: ["Up to $50k", 0, 50_000],
  m: ["$50k to $250k", 50_000, 250_000],
  l: ["$250k to $1M", 250_000, 1_000_000],
  xl: ["Over $1M", 1_000_000, Infinity],
};

const haystacks = new WeakMap<Entry, string>();

function haystack(e: Entry): string {
  let h = haystacks.get(e);
  if (h === undefined) {
    h = [e.title, e.catalog, ...e.facts, e.side, ...e.fits, ...e.cautions, ...e.also, ...e.status, e.summary ?? "", e.eligibility ?? "",
      ...(e.rows ?? []).map((r) => `${r.text ?? ""} ${r.linkText ?? ""}`),
      ...(e.grants ?? []).map((g) => `${g.to} ${g.place} ${g.purpose}`)].join(" \n ").toLowerCase();
    haystacks.set(e, h);
  }
  return h;
}

export function isNarrowed(n: Narrow): boolean {
  return Boolean(n.q.trim() || n.size || n.before || n.agency || n.apply || n.open || n.local || n.no501 || n.fresh || n.cycle || n.reach || n.corp);
}

/** Entries that pass every filter that applies to their source. Every word typed must appear. */
export function narrow(entries: Entry[], n: Narrow): Entry[] {
  if (!isNarrowed(n)) return entries;
  const words = n.q.toLowerCase().split(/\s+/).filter(Boolean);
  const band = SIZE_BANDS[n.size];
  const before = n.before ? new Date(`${n.before}T23:59:59`).getTime() : null;
  return entries.filter((e) => {
    if (n.fresh && !e.isNew) return false;
    if (words.length && !words.every((w) => haystack(e).includes(w))) return false;
    if (n.agency && e.agency !== n.agency) return false;
    if (band) {
      const [, lo, hi] = band;
      if (e.source === "fed") {
        // the award range overlaps the band
        if (e.amountLow == null && e.amountHigh == null) return false;
        const a = e.amountLow ?? e.amountHigh!, b = e.amountHigh ?? e.amountLow!;
        if (b < lo || a > hi) return false;
      } else if (e.source === "fdn") {
        const m = e.sortMedian;
        if (m == null || m < lo || m > hi) return false;
      }
    }
    if (before !== null && e.source === "fed" && (e.sortClose == null || e.sortClose > before)) return false;
    if (e.source === "fdn") {
      if (n.apply && !e.publishesApply) return false;
      if (n.open && e.closedToUnsolicited) return false;
      if (n.local && !e.local) return false;
      if (n.no501 && e.asks501c3) return false;
      if (n.cycle && e.cycle !== "open" && e.cycle !== "deadline") return false;
      if (n.reach && e.reach !== n.reach) return false;
      if (n.corp && !e.corp) return false;
    }
    return true;
  });
}

// ---------------- the profile's own filters ----------------

const HIDE_TEST: Record<string, (e: Entry) => boolean> = {
  scholarship: (e) => e.cautions.some((c) => c.startsWith("Mostly scholarships") || c.startsWith("Student aid paid")),
  invitation: (e) => e.cautions.some((c) => c.startsWith("Says it only funds preselected") || c.startsWith("Its website says it isn't taking")),
  unsolicited: (e) => e.cautions.includes("Says it does not accept unsolicited requests"),
  asks501: (e) => Boolean(e.asks501c3),
  research: (e) => e.cautions.some((c) => c.startsWith("Research")),
  costshare: (e) => e.cautions.includes("Requires cost sharing or matching funds"),
};

/** How many of each source the profile's filters take out, and why, so the page can say so. */
export interface ProfileNarrowed { entries: Entry[] | null; hidden: number }

/** The filters saved with the profile (what you ask for, which funders, timing, words to avoid, the hide list).
 *  They apply on every tab and never change a score. Results with no information on a choice stay in,
 *  except for timing, where "Rolling or no deadline" decides. */
export function profileNarrow(entries: Entry[] | null, f: ProfileForm, today: Date = new Date(),
                              pipeline: Map<string, { closed: boolean }> = new Map()): ProfileNarrowed {
  if (!entries) return { entries, hidden: 0 };
  const inPipeline = f.hide.includes("inpipeline");
  const declined = f.hide.includes("declined");
  const avoid = splitList(f.exclude_words).map((w) => w.toLowerCase());
  const lo = f.ask_min ? +f.ask_min : null;
  const hi = f.ask_max ? +f.ask_max : null;
  const t0 = new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime();
  const days = f.timing && f.timing !== "open" ? +f.timing : null;
  const hides = f.hide.map((h) => HIDE_TEST[h]).filter(Boolean);
  const kept = entries.filter((e) => {
    if (avoid.length && avoid.some((w) => haystack(e).includes(w))) return false;
    if (f.support_types.length && e.support?.length && !e.support.some((s) => f.support_types.includes(s))) return false;
    if (lo !== null || hi !== null) {
      const a = e.source === "fed" ? e.amountLow : e.source === "fdn" ? e.sortMedian : null;
      const b = e.source === "fed" ? e.amountHigh : a;
      if (a != null && b != null && ((hi !== null && Math.min(a, b) > hi) || (lo !== null && Math.max(a, b) < lo))) return false;
    }
    if (e.source === "fdn" && e.kind && !f.funder_types.includes(e.kind)) return false;
    if (f.timing === "open") {
      const open = e.source === "fed" ? !e.forecast : e.cycle === "open" || e.cycle === "deadline";
      if (!open && !(f.include_rolling && e.sortClose == null && e.source !== "fed")) return false;
    } else if (days !== null) {
      if (e.sortClose == null) { if (!f.include_rolling) return false; }
      else if (e.sortClose - t0 > days * 86_400_000) return false;
    }
    if (hides.some((h) => h(e))) return false;
    const p = pipeline.get(e.key);
    if (p && ((inPipeline && !p.closed) || (declined && p.closed))) return false;
    return true;
  });
  return { entries: kept, hidden: entries.length - kept.length };
}
