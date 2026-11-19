// What a visitor without a full search sees: how many strong and possible matches each source has, and the
// top three from the source with the most. Runs in the search function (supabase/functions/search), on the
// same scoring code as the page, so the counts and the three match what a signed-in search shows first.
import { federalEntry, floridaEntry, foundationEntry, profileNarrow, type Entry, type SourceKey } from "../entries";
import { expandCities, type ProfileForm } from "../profile";
import { isBlank, KINDS, simFor, toProfile, type RankSources } from "../rank";
import { scoreFederal, scoreFlorida, scoreFoundations } from "../score";

export const PREVIEW_SIZE = 3;

export interface Counts { strong: number; possible: number }
export interface Preview {
  /** Per source shown for this profile; a source without data for the state is left out. */
  counts: Partial<Record<SourceKey, Counts>>;
  /** The source the three come from (the most strong matches, then the most possible), or null when none match. */
  source: SourceKey | null;
  entries: Entry[];
}

const good = <T extends { tier: string }>(xs: T[]) => xs.filter((x) => x.tier !== "Long shot");

/** Which sources the profile's funder choices show, the same rule as the page's tabs. */
export function shownSources(f: ProfileForm, hasPrograms: boolean): SourceKey[] {
  const out: SourceKey[] = [];
  if (f.funder_types.includes("federal")) out.push("fed");
  if (f.funder_types.some((t) => !["federal", "florida"].includes(t))) out.push("fdn");
  if (hasPrograms && f.funder_types.includes("florida")) out.push("fl");
  return out;
}

export function preview(f: ProfileForm, src: RankSources, vector: number[] | null, now: Date = new Date(), take = PREVIEW_SIZE): Preview {
  if (isBlank(f)) return { counts: {}, source: null, entries: [] };
  const p = toProfile(f, now);
  const hasKw = p.keywords.length > 0;
  const cities = expandCities(f.cities, src.counties);
  const hasPrograms = Boolean(src.fl) && f.state === (src.flState ?? "FL");
  const lists: Partial<Record<SourceKey, Entry[]>> = {};
  for (const k of shownSources(f, hasPrograms)) {
    // Entries are built for strong and possible matches only: long shots are never part of a preview.
    if (k === "fed" && src.fed) {
      lists.fed = good(scoreFederal(src.fed.records, p, simFor(src.fed.vecs, vector))).map((s) => federalEntry(s, hasKw));
    } else if (k === "fdn" && src.fdn) {
      const recs = src.fdn.records.filter((r) => KINDS.includes(r.kind || "Private foundation"));
      lists.fdn = good(scoreFoundations(recs, p, f.state, cities, simFor(src.fdn.vecs, vector), false))
        .map((s) => foundationEntry(s, f.state, hasKw, cities));
    } else if (k === "fl" && src.fl) {
      lists.fl = good(scoreFlorida(src.fl.records, p, simFor(src.fl.vecs, vector), false, cities)).map((s) => floridaEntry(s, hasKw));
    }
  }
  const counts: Partial<Record<SourceKey, Counts>> = {};
  for (const [k, list] of Object.entries(lists) as [SourceKey, Entry[]][]) {
    const kept = profileNarrow(list, f, now).entries ?? [];
    lists[k] = kept;
    counts[k] = { strong: kept.filter((e) => e.tier === "Strong").length, possible: kept.filter((e) => e.tier === "Possible").length };
  }
  const ranked = (Object.keys(counts) as SourceKey[])
    .filter((k) => counts[k]!.strong + counts[k]!.possible > 0)
    .sort((a, b) => counts[b]!.strong - counts[a]!.strong || counts[b]!.possible - counts[a]!.possible);
  const source = ranked[0] ?? null;
  return { counts, source, entries: source ? lists[source]!.slice(0, take) : [] };
}

/** The fields that make a search new. Changing anything else (deadlines, sizes, the hide list) refines the
 *  same search and is never counted again. */
export function searchSignature(f: ProfileForm): string {
  const sorted = (xs: string[]) => [...xs].sort();
  return JSON.stringify([
    f.mission.trim(), f.keywords.trim(), f.state, f.cities.trim().toLowerCase(),
    sorted(f.categories), sorted(f.focus_areas), sorted(f.ages), sorted(f.populations),
  ]);
}
