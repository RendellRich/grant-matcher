// Turns scored records from each source into one shape the result list draws.
import { fmtDate, money, type FederalExtra, type FederalRec, type FloridaRec, type FoundationOut, type Scored, type Tier } from "./score";

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
  };
}

export function foundationEntry(s: Scored<FoundationOut>, state: string, hasKw: boolean): Entry {
  const r = s.rec;
  const a = r._apply ?? {};
  const why = sortReasons(s.reasons, s.cautions, "its past grants", hasKw);
  const site = siteHref(r._site ?? "");
  const rows: DetailRow[] = [];
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
  if (safeUrl(r.url)) rows.push({ label: "Tax filings", href: r.url, linkText: "ProPublica Nonprofit Explorer" });
  const grants = (r.sample_grants || []).filter((g) => g && typeof g === "object").slice(0, 8);
  const local = grants.filter((g) => g.state === state).length;
  return {
    key: `fdn:${r.ein}`, source: "fdn", title: r._name || r.name, url: site || safeUrl(r.url),
    catalog: `EIN ${r.ein.length === 9 ? r.ein.slice(0, 2) + "-" + r.ein.slice(2) : r.ein}`,
    facts: [r.kind ?? "Private foundation", `${r._city || r.city}, ${r.state}`,
      `${plural(r.grant_count ?? 0, "grant")}, ${money(r.grants_total)} total`, `tax year ${r.tax_year}`],
    side: `Typical ${money(r.grant_median)}`, sideQuiet: true,
    score: s.score, tier: s.tier, ...why, rows,
    noApplyInfo: !(a.contact || a.materials || a.deadlines),
    grants: grants.map((g) => ({
      to: g._to || g.to, place: `${g._city || g.city}, ${g.state}`,
      amount: `$${Math.round(Number(g.amount) || 0).toLocaleString("en-US")}`, purpose: g._purpose || "",
    })),
    grantsWhere: grants.length ? (local === grants.length ? `all in ${state}` : `${local} of ${grants.length} in ${state}`) : "",
    sortInState: r.in_state, sortMedian: r.grant_median ?? null,
  };
}

export function floridaEntry(s: Scored<FloridaRec>, hasKw: boolean): Entry {
  const r = s.rec;
  const why = sortReasons(s.reasons, s.cautions, "its title or objectives", hasKw);
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
  return {
    key: `fl:${r.id}`, source: "fl", title: r._title || r.title, url: safeUrl(r.url), catalog: `CSFA ${r.csfa}`,
    facts: [r.agency, r._assist || ""].filter(Boolean),
    side: "",
    score: s.score, tier: s.tier, ...why, rows,
  };
}
