import { BUDGET_BANDS, CATEGORY_NAMES, currentBand, STATE_NAMES } from "./score";
export { STATE_NAMES };
import TERMS from "./terms.json";

export const STATES = Object.keys(STATE_NAMES).sort((a, b) => STATE_NAMES[a].localeCompare(STATE_NAMES[b]));

export type Status501 = "Yes" | "Pending" | "No";
export type Delivery = "in_person" | "online_state" | "online_national";
export type Timing = "" | "open" | "30" | "60" | "90";

export interface Term { id: string; label: string; words: string[] }
export interface SupportType { id: string; label: string; pattern: string }
/** A kind of nonprofit: which focus areas to show first and which federal funding areas to start from. */
export interface OrgType { id: string; label: string; focus: string[]; categories: string[] }
export const FOCUS_AREAS: Term[] = TERMS.focus_areas;
export const AGES: Term[] = TERMS.ages;
export const POPULATIONS: Term[] = TERMS.populations;
export const SUPPORT_TYPES: SupportType[] = TERMS.support_types;
export const ORG_TYPES: OrgType[] = TERMS.org_types;

export const DELIVERY: [Delivery, string][] = [
  ["in_person", "In person"], ["online_state", "Online in our state"], ["online_national", "Online nationwide"],
];
export const REGISTRATIONS: [string, string][] = [["sam", "SAM.gov and a UEI"], ["grantsgov", "A Grants.gov account"], ["audit", "Audited financials"]];
export const FUNDER_TYPES: [string, string][] = [
  ["federal", "Federal"], ["florida", "State programs"], ["Private foundation", "Private foundations"],
  ["Community foundation", "Community foundations"], ["Public foundation", "Public foundations"], ["United Way or federated fund", "United Ways"],
];
export const TIMING: [Timing, string][] = [
  ["", "Any time"], ["open", "Open now (website says so)"], ["30", "Due within 30 days"], ["60", "Due within 60 days"], ["90", "Due within 90 days"],
];
/** Results a person can hide in one click; each reads a caution the scorer already writes. */
export const HIDE: [string, string][] = [
  ["scholarship", "Scholarship funds"], ["invitation", "Invitation only or preselected groups"], ["unsolicited", "Doesn't take unsolicited requests"],
  ["asks501", "Asks for 501(c)(3) proof"], ["research", "Research grants"], ["costshare", "Requires matching funds"],
];
/** Offered only inside ETO's admin page, where the funding pipeline says what was already sent. */
export const HIDE_PIPELINE: [string, string][] = [["inpipeline", "Already in our pipeline"], ["declined", "Declined or closed before"]];

/** What the person entered. Matches the JSON the Streamlit app saves, so old profile files still load:
 *  every field added later has a default. */
export interface ProfileForm {
  org_type: string; // "" or an ORG_TYPES id; it arranges the form and never changes a score
  mission: string;
  keywords: string;
  categories: string[];
  state: string;
  cities: string;
  has_501c3: Status501;
  budget_band: string;
  can_cost_share: boolean;
  include_forecasted: boolean;
  min_days_left: number;
  // what you do and who you serve: each choice adds its words to the key word match
  focus_areas: string[];
  ages: string[];
  populations: string[];
  exclude_words: string;
  // your organization
  delivery: Delivery;
  fiscal_sponsor: boolean;
  year_founded: string; // "" or a four-digit year
  registrations: string[];
  // what you are asking for, and which funders: these narrow the list and never change a score
  support_types: string[];
  ask_min: string; // "" or whole dollars
  ask_max: string;
  funder_types: string[];
  timing: Timing;
  include_rolling: boolean; // with a timing choice, keep results with no deadline
  hide: string[];
}

export const BLANK: ProfileForm = {
  org_type: "", mission: "", keywords: "", categories: [], state: "FL", cities: "", has_501c3: "Yes",
  budget_band: "$50k to $250k", can_cost_share: false, include_forecasted: true, min_days_left: 14,
  focus_areas: [], ages: [], populations: [], exclude_words: "",
  delivery: "in_person", fiscal_sponsor: false, year_founded: "", registrations: [],
  support_types: [], ask_min: "", ask_max: "", funder_types: FUNDER_TYPES.map(([v]) => v), timing: "", include_rolling: true, hide: [],
};

/** The typed key words first, then each chosen group's words, without repeats (ignoring case). Same as terms.py. */
export function expandKeywords(keywords: string[], focus: string[] = [], ages: string[] = [], populations: string[] = []): string[] {
  const out: string[] = [];
  const seen = new Set<string>();
  const add = (w: string) => { const t = w.trim(); if (t && !seen.has(t.toLowerCase())) { seen.add(t.toLowerCase()); out.push(t); } };
  keywords.forEach(add);
  for (const [group, chosen] of [[FOCUS_AREAS, focus], [AGES, ages], [POPULATIONS, populations]] as const) {
    for (const item of group) if (chosen.includes(item.id)) item.words.forEach(add);
  }
  return out;
}

/** The cities to look for: each typed name, and for a county name ("Manatee" or "Manatee County") every
 *  city, town and Census place in it. Names are matched without regard to case. */
export function expandCities(typed: string, counties: Record<string, string[]> | null): string[] {
  const byName = new Map(Object.entries(counties ?? {}).map(([c, places]) => [c.toLowerCase(), places]));
  const out: string[] = [];
  const seen = new Set<string>();
  const add = (s: string) => { const k = s.trim().toLowerCase(); if (k && !seen.has(k)) { seen.add(k); out.push(s.trim()); } };
  for (const name of splitList(typed)) {
    add(name);
    const county = byName.get(name.toLowerCase().replace(/\s+(county|parish)$/, ""));
    if (county) county.forEach(add);
  }
  return out;
}

/** The words only the ages and populations choices added: the scorers count these at half weight. Same as terms.py. */
export function minorKeywords(keywords: string[], focus: string[] = [], ages: string[] = [], populations: string[] = []): string[] {
  const major = new Set(expandKeywords(keywords, focus).map((w) => w.toLowerCase()));
  return expandKeywords(keywords, focus, ages, populations).filter((w) => !major.has(w.toLowerCase()));
}

/** Every key word the scorer will use for this profile. */
export const profileKeywords = (f: ProfileForm) => expandKeywords(splitList(f.keywords), f.focus_areas, f.ages, f.populations);
export const profileMinorKeywords = (f: ProfileForm) => minorKeywords(splitList(f.keywords), f.focus_areas, f.ages, f.populations);

export function sameForm(a: ProfileForm, b: ProfileForm): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

/** Reads a saved profile file; throws when it is not one. */
export function parseProfile(text: string): ProfileForm {
  const d = JSON.parse(text);
  if (!d || typeof d !== "object" || !("mission" in d || "keywords" in d)) throw new Error("not a profile");
  return {
    org_type: ORG_TYPES.some((t) => t.id === d.org_type) ? d.org_type : "",
    mission: String(d.mission ?? ""),
    keywords: String(d.keywords ?? ""),
    cities: String(d.cities ?? ""),
    state: d.state in STATE_NAMES ? d.state : "FL",
    has_501c3: ["Yes", "Pending", "No"].includes(d.has_501c3) ? d.has_501c3 : "Yes",
    budget_band: currentBand(d.budget_band) in BUDGET_BANDS ? currentBand(d.budget_band) : "$50k to $250k",
    can_cost_share: Boolean(d.can_cost_share),
    categories: Array.isArray(d.categories) ? d.categories.filter((c: string) => c in CATEGORY_NAMES) : [],
    include_forecasted: d.include_forecasted === undefined ? true : Boolean(d.include_forecasted),
    min_days_left: Number.isFinite(+d.min_days_left) ? Math.max(0, Math.min(60, Math.round(+d.min_days_left))) : 14,
    focus_areas: ids(d.focus_areas, FOCUS_AREAS.map((t) => t.id)),
    ages: ids(d.ages, AGES.map((t) => t.id)),
    populations: ids(d.populations, POPULATIONS.map((t) => t.id)),
    exclude_words: String(d.exclude_words ?? ""),
    delivery: DELIVERY.some(([v]) => v === d.delivery) ? d.delivery : "in_person",
    fiscal_sponsor: Boolean(d.fiscal_sponsor),
    year_founded: /^\d{4}$/.test(String(d.year_founded ?? "")) ? String(d.year_founded) : "",
    registrations: ids(d.registrations, REGISTRATIONS.map(([v]) => v)),
    support_types: ids(d.support_types, SUPPORT_TYPES.map((t) => t.id)),
    ask_min: dollars(d.ask_min),
    ask_max: dollars(d.ask_max),
    funder_types: Array.isArray(d.funder_types) ? ids(d.funder_types, FUNDER_TYPES.map(([v]) => v)) : BLANK.funder_types,
    timing: TIMING.some(([v]) => v === d.timing) ? d.timing : "",
    include_rolling: d.include_rolling === undefined ? true : Boolean(d.include_rolling),
    hide: ids(d.hide, [...HIDE, ...HIDE_PIPELINE].map(([v]) => v)),
  };
}

const ids = (v: unknown, allowed: string[]) => (Array.isArray(v) ? v.filter((x) => allowed.includes(x)) : []);
const dollars = (v: unknown) => {
  const n = Math.round(Number(String(v ?? "").replace(/[$,\s]/g, "")));
  return v !== "" && v != null && Number.isFinite(n) && n > 0 ? String(n) : "";
};

export const splitList = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean);
