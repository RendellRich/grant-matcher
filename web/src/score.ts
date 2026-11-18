// Scoring for federal grants, foundations and Florida programs. A line-by-line port of
// grantmatch/match.py and grantmatch/rank_more.py; tests/parity.test.ts checks it against Python.
// Python rounds halves to even and formats with its own rules, so those are copied too.

export const BUDGET_BANDS: Record<string, number> = {
  "Under $10k": 10_000,
  "$10k to $50k": 50_000,
  "$50k to $250k": 250_000,
  "$250k to $1M": 1_000_000,
  "Over $1M": 5_000_000,
};

/** Band names saved in profiles before the small bands were split, mapped to the band that took their place. */
const OLD_BUDGET_BANDS: Record<string, string> = { "Under $50k": "$10k to $50k" };

/** The band a saved name means today, so profiles saved before a rename still load. */
export function currentBand(name: string): string {
  return OLD_BUDGET_BANDS[name] ?? name;
}

export const CATEGORY_NAMES: Record<string, string> = {
  AG: "Agriculture", AR: "Arts", BC: "Business and commerce", CD: "Community development",
  CP: "Consumer protection", DPR: "Disaster prevention and relief", ED: "Education",
  ELT: "Employment, labor and training", EN: "Energy", ENV: "Environment",
  FN: "Food and nutrition", HL: "Health", HO: "Housing", HU: "Humanities",
  ISS: "Income security and social services", IS: "Information and statistics",
  LJL: "Law, justice and legal services", NR: "Natural resources", O: "Other",
  RD: "Regional development", RT: "Recreation and tourism",
  ST: "Science, technology and research", T: "Transportation",
};

const RESEARCH_NUMBER = /^(RFA|PAR|PA|NOT)-/i;
const TARGETED: [RegExp, string, number][] = [
  [/\b(tribal|tribes|native american|indian health|alaska native)\b/i,
    "Appears limited to tribal organizations or tribal communities", 25],
  [/\b(state awards|state agencies|state arts agencies|states and territories|state and local governments)\b/i,
    "Appears aimed at state agencies", 20],
  [/\b(embassy|consulate|public diplomacy|mission \w+ public affairs)\b/i,
    "Run by a U.S. embassy for programs abroad", 25],
  [/\bindemnity\b/i, "Insurance for museum exhibitions, not a cash grant", 35],
];
const RESEARCH_TITLE = /\b(research|investigators?|scientists?|fellowships?|clinical trials?)\b/i;
export const SEMANTIC_SPREAD = 0.14;

const NO_UNSOLICITED = new RegExp(
  "(no|not accept\\w*|does not (accept|consider)|do not (accept|consider)) unsolicited|unsolicited (requests|applications|proposals) (are )?not"
  + "|by invitation only|invitation only|only to pre-?selected|preselected", "i");
const SCHOLARSHIP = /\bscholarships?\b|\btuition\b|\bstudent aid\b/i;
const SCHOLARSHIP_G = /\bscholarships?\b|\btuition\b|\bstudent aid\b/gi;
// A foundation's own words, in its how-to-apply section, asking for 501(c)(3) status or the IRS letter that proves it.
const ASKS_501C3 = /501\s*\(?\s*c\s*\)?\s*\(?\s*3|tax[- ]exempt|determination letter|public charit|509\s*\(?\s*a/i;
const ASKS_501C3_PENALTY = { Pending: 10, No: 20 } as const;
const ASKS_501C3_CAUTION = {
  Pending: "Asks for proof of 501(c)(3) status; apply once your IRS letter arrives, or through a fiscal sponsor",
  No: "Asks for proof of 501(c)(3) status; you would need a fiscal sponsor",
} as const;

/** Whether a foundation's how-to-apply text asks for 501(c)(3) status. Also drives the filter. */
export function asks501c3(r: { apply?: unknown }): boolean {
  const apply = r.apply && typeof r.apply === "object" ? (r.apply as Record<string, unknown>) : {};
  return ASKS_501C3.test(Object.values(apply).filter((v): v is string => typeof v === "string").join(" "));
}

const SCHOLARSHIP_SHARE = 0.6; // share of a foundation's listed grants that are scholarships before it counts as a scholarship fund
const SCHOLARSHIP_PENALTY = 40; // enough to take a scholarship fund out of the strong tier
const COMPETITIVE = /\b(competitive|request for (applications|proposals)|rfa|rfp|solicitation|notice of funding|scored|review panel)\b/i;
const STUDENT_GRANT = /\bstudent (assistance|aid) grant|tuition/i;

export type Tier = "Strong" | "Possible" | "Long shot";

export interface Profile {
  mission: string;
  keywords: string[];
  has501c3: "Yes" | "Pending" | "No";
  budgetBand: string;
  canCostShare: boolean;
  categories: string[];
  includeForecasted: boolean;
  minDaysLeft: number;
  today: Date; // a local calendar date; only the year, month and day are used
  fiscalSponsor?: boolean; // can apply through a fiscal sponsor while 501(c)(3) status is pending or absent
  delivery?: "in_person" | "online_state" | "online_national";
  yearFounded?: number | null;
  minorKeywords?: string[]; // words from the ages and populations choices, counted at half weight
}

const MINOR_WEIGHT = 0.5;

// match.py and rank_more.py: the fiscal sponsor, young organization and national giver rules.
const SPONSOR_PENALTY = 10;
const YOUNG_YEARS = 3;
const YOUNG_AWARD = 100_000;
const YOUNG_CAUTION = "A large federal award for a new organization; most go to groups with a few years of results";
const ASKS_501C3_SPONSOR = "Asks for proof of 501(c)(3) status; apply through your fiscal sponsor";
const NATIONAL_STATES = 5;

export interface Scored<T> {
  rec: T;
  score: number;
  tier: Tier;
  reasons: string[];
  cautions: string[];
  matched: string[];
}

// ---------- Python behaviour ----------

/** Python's round(): halves go to the even neighbour. */
export function pyRound(x: number): number {
  const f = Math.floor(x);
  const diff = x - f;
  if (diff > 0.5) return f + 1;
  if (diff < 0.5) return f;
  return f % 2 === 0 ? f : f + 1;
}

/** Python's f"{x:.{d}f}": exact ties (only possible for values a double holds exactly) go to even. */
function pyFixed(x: number, d: number): string {
  // toFixed already rounds the exact binary value; it differs from Python only on an exact tie, where
  // it rounds up and Python rounds to even. Test for a tie exactly: x = m * 2^e, so x * 10^d is a tie
  // when m * 10^d leaves exactly half of 2^-e as remainder.
  const view = new DataView(new ArrayBuffer(8));
  view.setFloat64(0, Math.abs(x));
  const bits = view.getBigUint64(0);
  const exp = Number((bits >> 52n) & 0x7ffn);
  const frac = bits & ((1n << 52n) - 1n);
  if (exp === 0 || exp === 0x7ff) return x.toFixed(d);
  const m = frac | (1n << 52n);
  const e = exp - 1075; // x = m * 2^e
  if (e < 0 && -e < 120) {
    const scale = 1n << BigInt(-e);
    if ((m * 10n ** BigInt(d)) % scale === scale >> 1n) {
      const down = (m * 10n ** BigInt(d)) / scale; // the even neighbour wins
      const n = down % 2n === 0n ? down : down + 1n;
      const s = n.toString().padStart(d + 1, "0");
      const out = d ? s.slice(0, -d) + "." + s.slice(-d) : s;
      return (x < 0 ? "-" : "") + out;
    }
  }
  return x.toFixed(d);
}

function grouped(n: number): string {
  // f"{n:,.0f}"
  const [i] = pyFixed(n, 0).split(".");
  const neg = i.startsWith("-");
  const digits = neg ? i.slice(1) : i;
  return (neg ? "-" : "") + digits.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

function median(values: number[]): number {
  const s = [...values].sort((a, b) => a - b);
  const m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

const WORD = /[\p{L}\p{N}\p{M}_]/u;

function escapeRe(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"); // a "u" regex rejects needless escapes such as \-
}

const hitCache = new Map<string, RegExp | null>();

/** re.search(r"\b" + re.escape(stem), text) with Python's Unicode word boundary. */
function stemPattern(kw: string): RegExp | null {
  let re = hitCache.get(kw);
  if (re !== undefined) return re;
  const k = kw.trim().toLowerCase();
  if (!k) re = null;
  else {
    const stem = k.endsWith("s") && k.length > 4 ? k.slice(0, -1) : k;
    // \b before the stem: a word start if the stem starts with a word character, else right after one.
    const guard = WORD.test(stem[0]) ? "(?<![\\p{L}\\p{N}\\p{M}_])" : "(?<=[\\p{L}\\p{N}\\p{M}_])";
    re = new RegExp(guard + escapeRe(stem), "u");
  }
  hitCache.set(kw, re);
  return re;
}

export function keywordHits(keywords: string[], text: string): string[] {
  const lower = text.toLowerCase();
  const hits: string[] = [];
  for (const kw of keywords) {
    const re = stemPattern(kw);
    if (re && re.test(lower)) hits.push(kw.trim());
  }
  return hits;
}

function missing(n: unknown): boolean {
  return n === null || n === undefined || (typeof n === "number" && Number.isNaN(n));
}

export function money(n: number | null | undefined): string {
  if (missing(n) || !n) return "not listed";
  const v = n as number;
  if (v >= 1_000_000) return `$${pyFixed(v / 1_000_000, 1)}M`.replace(".0M", "M");
  if (v >= 1_000) return `$${pyFixed(v / 1_000, 0)}k`;
  return `$${grouped(v)}`;
}

function awardRange(floor: number | null, ceiling: number | null): string {
  const hasCeiling = !missing(ceiling) && (ceiling as number) > 0;
  if (floor && hasCeiling && Math.abs(floor - (ceiling as number)) < 1) return money(ceiling);
  if (floor && hasCeiling) return `${money(floor)} to ${money(ceiling)}`;
  if (hasCeiling) return `up to ${money(ceiling)}`;
  if (floor) return `from ${money(floor)}`;
  return "amount not listed";
}

function keywordWeights(keywords: string[], texts: string[], minor: string[] = []): [Map<string, number>, number] {
  const weights = new Map<string, number>();
  for (const kw of keywords) {
    const share = texts.length ? texts.filter((t) => keywordHits([kw], t).length > 0).length / texts.length : 0;
    const w = 1.0 - Math.min(0.85, share * 8); // a word in 10%+ of records keeps only 15% weight
    weights.set(kw, minor.includes(kw) ? w * MINOR_WEIGHT : w);
  }
  const best3 = [...weights.values()].sort((a, b) => b - a).slice(0, 3).reduce((a, b) => a + b, 0) || 1.0;
  return [weights, best3];
}

function coverageOf(matched: string[], weights: Map<string, number>, best3: number): number {
  return Math.min(1.0, matched.reduce((s, m) => s + (weights.get(m) ?? 0.15), 0) / best3);
}

function tierOf(shown: number): Tier {
  return shown >= 60 ? "Strong" : shown >= 35 ? "Possible" : "Long shot";
}

const clip01 = (x: number) => Math.min(1, Math.max(0, x));

/** Embedding similarity above the source's median, scaled to 0..1 (rank_more._scale). */
function scaler(semantic: Map<string, number> | null, yardstick?: Map<string, number> | null): (id: string) => number {
  if (!semantic || semantic.size === 0) return () => 0.5;
  const base = median([...(yardstick && yardstick.size ? yardstick : semantic).values()]);
  return (id) => clip01(((semantic.get(id) ?? base) - base) / SEMANTIC_SPREAD);
}

// ---------- federal ----------

export interface FederalRec {
  id: string; number: string; title: string; agency_code: string; agency: string; status: string;
  close_date: string | null; award_ceiling: number | null; award_floor: number | null;
  cost_sharing: boolean; applicant_types: string[]; categories: string[]; category_labels: string[];
  description: string; eligibility_text: string; url: string; _title?: string;
}

export interface FederalExtra {
  close: Date | null; days_left: number | null; award_range: string; size_ref: number | null;
}

const DAY = 86_400_000;
const utcDay = (d: Date) => Date.UTC(d.getFullYear(), d.getMonth(), d.getDate());

/** load_frame: close dates, with far-future placeholders ("2099-01-01") read as no date. */
export function closeDate(raw: string | null, now: Date): Date | null {
  if (!raw) return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(raw);
  if (!m) return null;
  const d = new Date(+m[1], +m[2] - 1, +m[3]);
  const limit = new Date(now.getFullYear() + 4, now.getMonth(), now.getDate(), now.getHours(), now.getMinutes());
  return d < limit ? d : null;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
export const fmtDate = (d: Date) => `${MONTHS[d.getMonth()]} ${String(d.getDate()).padStart(2, "0")}, ${d.getFullYear()}`;

export function scoreFederal(records: FederalRec[], p: Profile, semantic: Map<string, number> | null,
                             now: Date = new Date()): Scored<FederalRec & FederalExtra>[] {
  const today = utcDay(p.today);
  let work = records.map((r) => ({ ...r, close: closeDate(r.close_date, now) } as FederalRec & FederalExtra));
  if (!p.includeForecasted) work = work.filter((r) => r.status === "posted");
  if (p.categories.length) work = work.filter((r) => r.categories.some((c) => p.categories.includes(c)));
  for (const r of work) r.days_left = r.close ? Math.round((utcDay(r.close) - today) / DAY) : null;
  work = work.filter((r) => r.days_left === null || r.days_left >= p.minDaysLeft);
  if (!work.length) return [];

  let sims: number[];
  if (semantic && semantic.size) {
    const baseline = median([...semantic.values()]);
    sims = work.map((r) => clip01(((semantic.get(r.id) ?? baseline) - baseline) / SEMANTIC_SPREAD));
  } else {
    sims = work.map(() => 0.5); // the model could not load: key words carry the ranking
  }

  const texts = work.map((r) => (r.title + " " + r.description).toLowerCase());
  const [weights, best3] = keywordWeights(p.keywords, texts, p.minorKeywords);
  const budget = BUDGET_BANDS[currentBand(p.budgetBand)] ?? 250_000;
  const allUndated = work.every((r) => r.days_left === null);
  const out: Scored<FederalRec & FederalExtra>[] = [];

  work.forEach((r, idx) => {
    const matched = keywordHits(p.keywords, r.title + " " + r.description);
    let points = 100 * (0.70 * sims[idx] + 0.30 * coverageOf(matched, weights, best3));
    const reasons: string[] = [];
    const cautions: string[] = [];
    if (matched.length) reasons.push("Mentions " + matched.slice(0, 5).join(", "));
    const cats = r.categories.map((c) => CATEGORY_NAMES[c] ?? c);
    if (p.categories.length && r.categories.some((c) => p.categories.includes(c))) {
      reasons.push("In your categories: " + cats.join(", "));
    }

    const types = new Set(r.applicant_types);
    if (p.has501c3 === "Yes") {
      if (types.has("12") || types.has("99")) reasons.push("Open to 501(c)(3) nonprofits");
      else { points -= 5; cautions.push('Eligibility is "other"; read the eligibility notes'); }
    } else if (types.has("13") || types.has("99")) {
      reasons.push("Open to nonprofits without 501(c)(3) status");
    } else if (types.has("12") && !["13", "25", "99"].some((t) => types.has(t))) {
      if (p.fiscalSponsor) {
        points -= SPONSOR_PENALTY;
        cautions.push("Requires 501(c)(3) status; apply through your fiscal sponsor");
      } else {
        points -= 40;
        cautions.push(p.has501c3 === "Pending"
          ? "Requires 501(c)(3) status; apply once your IRS letter arrives, or through a fiscal sponsor"
          : "Requires 501(c)(3) status; you would need a fiscal sponsor");
      }
    } else {
      points -= 5; cautions.push('Eligibility is "other"; read the eligibility notes');
    }

    if (r.cost_sharing && !p.canCostShare) {
      points -= 20; cautions.push("Requires cost sharing or matching funds");
    }

    const floor = r.award_floor && r.award_floor > 1_000 ? r.award_floor : null;
    const ceiling = missing(r.award_ceiling) ? null : r.award_ceiling;
    const sizeRef = floor || ceiling;
    if (floor && floor > 3 * budget) {
      points -= 15;
      cautions.push(`Smallest award (${money(floor)}) is large for your budget; funders usually want a track record at that size`);
    } else if (ceiling && ceiling > 10 * budget && !floor) {
      points -= 5;
      cautions.push(`Awards go up to ${money(ceiling)}; ask for an amount that fits your budget`);
    }

    const biggest = Math.max(floor ?? 0, ceiling && ceiling > 0 ? ceiling : 0);
    if (p.yearFounded && p.today.getFullYear() - p.yearFounded < YOUNG_YEARS && biggest >= YOUNG_AWARD) {
      points -= 5; cautions.push(YOUNG_CAUTION);
    }

    const nih = RESEARCH_NUMBER.test(r.number || "") && String(r.agency_code).startsWith("HHS-NIH");
    if (nih || RESEARCH_TITLE.test(r.title) || String(r.agency_code) === "NSF") {
      points -= 35; cautions.push("Research grant; usually needs a research team and institution");
    } else if (r.categories.includes("ST") && r.categories.length === 1) {
      points -= 8; cautions.push("Research and development funding");
    }

    for (const [pattern, note, penalty] of TARGETED) {
      if (pattern.test(r.title)) { points -= penalty; cautions.push(note); break; }
    }

    if (r.status === "forecasted") {
      const due = r.close ? `estimated due ${fmtDate(r.close)}` : "dates not set yet";
      reasons.push(`Forecast, not open yet (${due}); time to prepare`);
    } else if (r.days_left !== null && r.days_left < 30) {
      cautions.push(`Closes in ${r.days_left} days`);
    } else if (r.days_left === null && allUndated) {
      // match.py checks `is None`, but pandas stores a missing day count as NaN once any grant has one,
      // so this caution only appears when no grant in the list has a date. Kept as is to match the app.
      cautions.push("No close date listed; check the notice");
    }

    const final = Math.max(0, Math.min(100, points));
    const shown = pyRound(final);
    out.push({
      rec: { ...r, award_range: awardRange(floor, ceiling), size_ref: sizeRef ?? null },
      score: shown, tier: tierOf(shown), reasons, cautions, matched,
    });
  });
  // score high to low, then the soonest deadline; no deadline last
  return out.sort((a, b) => b.score - a.score
    || (a.rec.days_left ?? Infinity) - (b.rec.days_left ?? Infinity));
}

// ---------- foundations ----------

export interface SampleGrant {
  to: string; city: string; state: string; purpose: string; amount: number | null;
  _to?: string; _city?: string; _city_title?: string; _purpose?: string;
}

export interface FoundationRec {
  ein: string; name: string; city: string; state: string; tax_year: string; kind?: string;
  website?: string | null; preselected_only: boolean; apply?: Record<string, string> | null;
  grant_count: number | null; grant_median: number | null; grants_total: number | null;
  recipient_states: Record<string, number>; top_purposes: string[]; top_recipients?: string[];
  sample_grants: SampleGrant[]; url: string;
  _name?: string; _city?: string; _city_title?: string; _mission?: string; _site?: string;
  _apply?: Record<string, string>;
  /** What its website said at the last weekly check (grantmatch.cycles); display only, never scored. */
  _cycle?: WebsiteCycle;
  /** A company foundation and its local program (grantmatch/corporate.py); display only, never scored. */
  _corp?: CompanyGiving;
  /** Its giving over several years (grantmatch/history.py); display only, never scored. */
  hist?: GivingHistory;
}

export interface GivingHistory {
  y: number[]; // tax years with grants, oldest first
  n: number[]; // grants in each of those years
  steady?: boolean; // grants in each of the last four years
  new?: number | null; // share of the latest year's grantees it hadn't funded before
  pl?: Record<string, number>; // places in this state (lowercase), with the first year it funded there
}

export interface CompanyGiving {
  company: string;
  program?: { name: string; who: string; amount: string; when: string; how: string; focus?: string; url: string; checked: string };
}

export interface WebsiteCycle {
  s: "open" | "deadline" | "closed" | "apply"; // applications open, a deadline ahead, not taking requests, an apply link
  d?: string; // yyyy-mm-dd, the next deadline it gave
  q?: string; // the words found
  u?: string; // the page they were on
  at: string; // yyyy-mm-dd, when it was checked
}

export type FoundationOut = FoundationRec & { in_state: number };

const pyTitle = (s: string) => s.toLowerCase().replace(/(^|[^\p{L}])(\p{L})/gu, (_, a, b) => a + b.toUpperCase());

export function scoreFoundations(records: FoundationRec[], p: Profile, state: string, cities: string[],
                                 semantic: Map<string, number> | null, showPreselected = false): Scored<FoundationOut>[] {
  if (!records.length) return [];
  const recs = records.map((r) => ({
    ...r, kind: r.kind || "Private foundation", top_recipients: Array.isArray(r.top_recipients) ? r.top_recipients : [],
  }));
  const purposeText = recs.map((r) => r.top_purposes.join(" ") + " " + r.sample_grants.map((g) => g.purpose).join(" ")
    + " " + r.top_recipients.join(" "));
  const [weights, best3] = keywordWeights(p.keywords, purposeText.map((t) => t.toLowerCase()), p.minorKeywords);
  const fit = scaler(semantic);
  const budget = BUDGET_BANDS[currentBand(p.budgetBand)] ?? 250_000;
  const citySet = new Set(cities.map((c) => c.trim().toLowerCase()).filter(Boolean));
  const out: Scored<FoundationOut>[] = [];

  recs.forEach((r, i) => {
    const apply = r.apply && typeof r.apply === "object" ? r.apply : {};
    const restrictions = apply.restrictions ?? "";
    const reasons: string[] = [];
    const cautions: string[] = [];
    const matched = keywordHits(p.keywords, purposeText[i]);
    let points = 60 * fit(r.ein) + 15 * coverageOf(matched, weights, best3);
    if (matched.length) reasons.push("Past grants mention " + matched.slice(0, 5).join(", "));

    const n = r.grant_count || 0;
    const inState = r.recipient_states?.[state] ?? 0;
    const share = n ? inState / n : 0;
    // A group serving people online across the country can reach a funder that gives in many states.
    const reach = Object.values(r.recipient_states ?? {}).filter(Boolean).length;
    const national = p.delivery === "online_national" && reach >= NATIONAL_STATES;
    const wentTo = n === 1 ? `Its only grant went to a ${state} organization` : `${inState} of its ${n} grants went to ${state} organizations`;
    if (share >= 0.5) { points += 20; reasons.push(wentTo); }
    else if (share >= 0.2) { points += 12; reasons.push(wentTo); }
    else if (inState) {
      points -= national ? 0 : share < 0.1 && r.state !== state ? 15 : 5;
      cautions.push(`Only ${inState} of its ${n} grants went to ${state}`);
    } else if (r.state === state) points += 6;
    else if (national) { points -= 5; cautions.push(`No grants to ${state} in its latest return, but it gives in ${reach} states`); }
    else { points -= 20; cautions.push(`No grants to ${state} in its latest return`); }

    const isPublic = r.kind !== "Private foundation";
    if (r.kind === "Community foundation" && r.state !== state) {
      points -= 25;
      cautions.push(`Serves a community outside ${state}; its grants here are usually from donors' own funds`);
    }
    const cityLower = String(r.city).toLowerCase();
    if (citySet.has(cityLower) && r.state === state) {
      points += 5;
      reasons.push(`Based in ${r._city_title ?? pyTitle(String(r.city))}, one of your cities`);
    }
    if (n < 3) {
      points -= 20;
      cautions.push(`Made only ${n} grant${n !== 1 ? "s" : ""} last year, so its interests are hard to read`);
    }
    const local = r.sample_grants.filter((g) => citySet.has(g.city.toLowerCase()) && g.state === state);
    if (local.length) {
      points += local.length >= 3 ? 10 : 5;
      const names = [...new Set(local.map((g) => g._city_title ?? pyTitle(g.city)))].sort();
      reasons.push(`Funded ${local.length} group${local.length > 1 ? "s" : ""} in ${names.join(", ")}`);
    }
    const servesYou = r.state === state && (citySet.has(cityLower) || local.length >= 3);
    if (r.kind === "Community foundation" && servesYou) {
      points += 15;
      reasons.unshift("A community foundation serving your area; these often run grant cycles for local nonprofits");
    }

    const med = r.grant_median;
    if (missing(med)) reasons.push(`Typical grant ${money(null)}`); // pandas reads a missing median as NaN, which is truthy
    else if (med && med > budget) { points -= 10; cautions.push(`Typical grant (${money(med)}) is large next to your budget`); }
    else if (med && med < 1000) cautions.push(`Mostly small gifts (typical ${money(med)})`);
    else if (med) reasons.push(`Typical grant ${money(med)}`);

    if (isPublic && typeof r.website === "string" && r.website) reasons.push("Check its website for open grant cycles");
    if (r.preselected_only) {
      if (!showPreselected) return;
      points -= 25;
      cautions.push("Says it only funds preselected organizations; an introduction letter may still be read");
    }
    if (NO_UNSOLICITED.test(restrictions)) {
      points -= 30; cautions.push("Says it does not accept unsolicited requests");
    }
    if (Object.keys(apply).length && (apply.materials || apply.contact)) reasons.push("Publishes how to apply");
    if (p.has501c3 !== "Yes" && asks501c3(r)) {
      if (p.fiscalSponsor) cautions.push(ASKS_501C3_SPONSOR);
      else { points -= ASKS_501C3_PENALTY[p.has501c3]; cautions.push(ASKS_501C3_CAUTION[p.has501c3]); }
    }
    // Scholarship funds pay students (or a college on a student's behalf), so a nonprofit cannot apply.
    // Judge by what its grants were for: most of the listed grants, or a purpose list made of scholarships.
    const samples = r.sample_grants;
    const scholar = samples.filter((g) => SCHOLARSHIP.test(g.purpose)).length;
    const purposes = r.top_purposes.slice(0, 10).join(" ");
    if ((samples.length && scholar / samples.length >= SCHOLARSHIP_SHARE) || (purposes.match(SCHOLARSHIP_G)?.length ?? 0) >= 3) {
      points -= SCHOLARSHIP_PENALTY; cautions.push("Mostly scholarships paid to students, not grants to organizations");
    }

    if (n < 3) points = Math.min(points, 55); // too little history to call it a strong match
    const shown = pyRound(Math.max(0, Math.min(100, points)));
    out.push({ rec: { ...r, in_state: inState }, score: shown, tier: tierOf(shown), reasons, cautions, matched });
  });
  return out.sort((a, b) => b.score - a.score || (b.rec.grant_count ?? 0) - (a.rec.grant_count ?? 0));
}

// ---------- Florida programs ----------

export interface FloridaRec {
  id: string; csfa: string; title: string; agency: string; objectives: string; assistance: string;
  applicant_types: string; nonprofit_eligible: boolean; earmark: boolean; restrictions: string;
  application: string; award: string; deadlines: string; contact: string; web: string; subjects: string;
  url: string; _title?: string; _assist?: string;
  // County and city programs only (grantmatch/local.py)
  level?: string; area?: string; places?: string[]; requires_501c3?: boolean;
  opens?: string | null; closes?: string | null; checked?: string; _cycle?: WebsiteCycle;
}

// County and city programs serve named counties and may need 501(c)(3) status. Same as rank_more.py.
const REQUIRES_501C3_CAUTION = {
  Pending: "Requires 501(c)(3) status; apply once your IRS letter arrives",
  No: "Requires 501(c)(3) status",
} as const;
const REQUIRES_501C3_SPONSOR = "Requires 501(c)(3) status; ask whether you can apply through your fiscal sponsor";

export function localChecks(r: FloridaRec, p: Profile, citySet: Set<string>): [number, string[], string[]] {
  if (!Array.isArray(r.places) || !r.places.length) return [0, [], []];
  let points = 0;
  const reasons: string[] = [];
  const cautions: string[] = [];
  const area = r.area || "its county";
  if (r.places.some((x) => citySet.has(x))) reasons.push(`Funds work in ${area}, where you work`);
  else if (citySet.size) { points -= 40; cautions.push(`Only for work in ${area}`); }
  else { points -= 10; cautions.push(`Only for work in ${area}; add your cities to check`); }
  if (r.requires_501c3 === true && (p.has501c3 === "Pending" || p.has501c3 === "No")) {
    if (p.fiscalSponsor) cautions.push(REQUIRES_501C3_SPONSOR);
    else { points -= ASKS_501C3_PENALTY[p.has501c3]; cautions.push(REQUIRES_501C3_CAUTION[p.has501c3]); }
  }
  return [points, reasons, cautions];
}

export function scoreFlorida(records: FloridaRec[], p: Profile, semantic: Map<string, number> | null,
                             showEarmarks = false, cities: string[] = []): Scored<FloridaRec>[] {
  let recs = records.filter((r) => r.nonprofit_eligible);
  if (!showEarmarks) recs = recs.filter((r) => !r.earmark);
  if (!recs.length) return [];
  const text = recs.map((r) => r.title + " " + r.objectives + " " + r.subjects);
  // Measured on the state programs only, as in rank_more.py, so county programs never move a state program's score.
  const isLocal = (id: string) => id.startsWith("local-");
  const stateText = text.filter((_, i) => !isLocal(recs[i].id));
  const [weights, best3] = keywordWeights(p.keywords, (stateText.length ? stateText : text).map((t) => t.toLowerCase()), p.minorKeywords);
  const fit = scaler(semantic, semantic ? new Map([...semantic].filter(([k]) => !isLocal(k))) : null);
  const citySet = new Set(cities.map((c) => c.trim().toLowerCase()).filter(Boolean));
  const out = recs.map((r, i): Scored<FloridaRec> => {
    const matched = keywordHits(p.keywords, text[i]);
    let points = 75 * fit(r.id) + 25 * coverageOf(matched, weights, best3);
    const reasons = ["Open to nonprofits"];
    const cautions: string[] = [];
    if (matched.length) reasons.unshift("Mentions " + matched.slice(0, 5).join(", "));
    if (COMPETITIVE.test(r.award + " " + r.application)) reasons.push("Awarded through a competitive application");
    if (SCHOLARSHIP.test(r.title) || STUDENT_GRANT.test(r.title)) {
      points -= 25; cautions.push("Student aid paid to individuals or schools, not to nonprofits");
    }
    if (r.earmark) { points -= 40; cautions.push("Set aside by the Legislature for a named organization"); }
    const [extra, moreReasons, moreCautions] = localChecks(r, p, citySet);
    points += extra; reasons.push(...moreReasons); cautions.push(...moreCautions);
    const shown = pyRound(Math.max(0, Math.min(100, points)));
    return { rec: r, score: shown, tier: tierOf(shown), reasons, cautions, matched };
  });
  return out.sort((a, b) => b.score - a.score);
}
