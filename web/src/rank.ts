// The ranking that turns a saved profile and the data into each source's list of entries. The page and the
// background scorer (scripts/score-eto.ts) both use it, so ETO's strong-match count is the same wherever it is made.
import { federalEntry, floridaEntry, foundationEntry, type Entry } from "./entries";
import { expandCities, profileKeywords, profileMinorKeywords, type ProfileForm } from "./profile";
import { scoreFederal, scoreFlorida, scoreFoundations, type FederalRec, type FloridaRec, type FoundationRec, type Profile } from "./score";
import { strongKeys } from "./seen";
import { similarities, type VectorSet } from "./vectors";

/** The kinds of foundation shown until someone narrows them. */
export const KINDS = ["Private foundation", "Community foundation", "Public foundation", "United Way or federated fund"];

/** The text the meaning model reads for a profile. */
export const queryText = (f: ProfileForm) => f.mission + " " + f.keywords;

/** True when there's nothing to match on. */
export const isBlank = (f: ProfileForm) => !f.mission.trim() && !f.keywords.trim() && !f.focus_areas.length;

/** The scorer's view of a saved profile, as of today. */
export function toProfile(f: ProfileForm, now: Date = new Date()): Profile {
  return {
    mission: f.mission, keywords: profileKeywords(f), has501c3: f.has_501c3,
    budgetBand: f.budget_band, canCostShare: f.can_cost_share, categories: f.categories,
    includeForecasted: f.include_forecasted, minDaysLeft: f.min_days_left,
    today: new Date(now.getFullYear(), now.getMonth(), now.getDate()),
    fiscalSponsor: f.fiscal_sponsor, delivery: f.delivery, minorKeywords: profileMinorKeywords(f),
    yearFounded: f.year_founded ? +f.year_founded : null,
  };
}

type Sim = Map<string, number> | null;
export const simFor = (vecs: VectorSet, vector: number[] | null) => (vector ? similarities(vecs, vector) : null);

/** Federal entries from scored rows; the page keeps the scored rows too, for its exports. */
export const federalEntries = (scored: ReturnType<typeof scoreFederal>, p: Profile): Entry[] =>
  scored.map((s) => federalEntry(s, p.keywords.length > 0));

export const rankFederal = (records: FederalRec[], p: Profile, sim: Sim): Entry[] => federalEntries(scoreFederal(records, p, sim), p);

export const rankFoundations = (records: FoundationRec[], p: Profile, state: string, cities: string[], sim: Sim,
  kinds: string[] = KINDS, preselected = false): Entry[] =>
  scoreFoundations(records.filter((r) => kinds.includes(r.kind || "Private foundation")), p, state, cities, sim, preselected)
    .map((s) => foundationEntry(s, state, p.keywords.length > 0, cities));

export const rankFlorida = (records: FloridaRec[], p: Profile, sim: Sim, earmarks = false, cities: string[] = []): Entry[] =>
  scoreFlorida(records, p, sim, earmarks, cities).map((s) => floridaEntry(s, p.keywords.length > 0));

interface Loaded<T> { records: T[]; vecs: VectorSet }
export interface RankSources {
  fed: Loaded<FederalRec> | null;
  fdn: Loaded<FoundationRec> | null;
  /** The state's programs, and the state they are for (Florida unless said). */
  fl: Loaded<FloridaRec> | null;
  flState?: string;
  counties: Record<string, string[]> | null;
}

/** Every source's entries for a saved profile, with the page's starting settings. */
export function rankAll(f: ProfileForm, src: RankSources, vector: number[] | null, now: Date = new Date()) {
  if (isBlank(f)) return { fed: null, fdn: null, fl: null };
  const p = toProfile(f, now);
  const cities = expandCities(f.cities, src.counties);
  return {
    fed: src.fed ? rankFederal(src.fed.records, p, simFor(src.fed.vecs, vector)) : null,
    fdn: src.fdn ? rankFoundations(src.fdn.records, p, f.state, cities, simFor(src.fdn.vecs, vector)) : null,
    fl: src.fl && f.state === (src.flState ?? "FL") ? rankFlorida(src.fl.records, p, simFor(src.fl.vecs, vector), false, cities) : null,
  };
}

const day = (ms: number | null | undefined) => {
  if (ms == null || !Number.isFinite(ms)) return null;
  const d = new Date(ms);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

/** The strong entries, once each, in key order: what ETO counts, with a name, funder and deadline for each. */
export function strongItems(lists: (Entry[] | null)[], max = 2000): { k: string; title: string; funder: string | null; deadline: string | null }[] {
  const keys = new Set(strongKeys(lists, max));
  const byKey = new Map<string, Entry>();
  for (const list of lists) for (const e of list ?? []) if (keys.has(e.key) && !byKey.has(e.key)) byKey.set(e.key, e);
  return [...keys].map((k) => {
    const e = byKey.get(k)!;
    const funder = e.source === "fed" ? e.agency ?? null : e.source === "fdn" ? e.title : null;
    return { k, title: e.title.slice(0, 200), funder: funder ? funder.slice(0, 200) : null, deadline: day(e.sortClose) };
  });
}
