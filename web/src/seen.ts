// Remembers which grants, foundations and programs were in the data at the person's last visit, so the
// ones added since can be marked New. Kept in this browser only; nothing leaves the device.
//
// localStorage holds what was seen, per source ("fed", "fl", "fdn-FL"). sessionStorage holds the
// snapshot this tab started from, so reloading the page keeps the same New marks until the next visit.

const SAVED = "gm-seen";
const BASE = "gm-seen-base";

interface Snapshot { at: string; ids: string[] }
type Store = Record<string, Snapshot | null>;

export interface Fresh {
  ids: Set<string>; // new since the last visit
  since: string | null; // when that visit was; null on a first visit, when nothing is marked
}

function read(storage: Storage | undefined, key: string): Store {
  try {
    const raw = storage?.getItem(key);
    const v = raw ? JSON.parse(raw) : {};
    return v && typeof v === "object" ? v : {};
  } catch {
    return {};
  }
}

function write(storage: Storage | undefined, key: string, value: Store): void {
  try {
    storage?.setItem(key, JSON.stringify(value));
  } catch {
    // Storage full or blocked (a private window): the New marks just won't carry over.
  }
}

const local = () => (typeof localStorage === "undefined" ? undefined : localStorage);
const session = () => (typeof sessionStorage === "undefined" ? undefined : sessionStorage);

/** The ids in `ids` that weren't there at the last visit, and records this visit for next time. */
export function newSince(scope: string, ids: string[], now: Date = new Date()): Fresh {
  const base = read(session(), BASE);
  if (!(scope in base)) {
    const saved = read(local(), SAVED);
    base[scope] = saved[scope] ?? null;
    write(session(), BASE, base);
    saved[scope] = { at: now.toISOString(), ids };
    write(local(), SAVED, saved);
  }
  const prev = base[scope];
  if (!prev || !Array.isArray(prev.ids)) return { ids: new Set(), since: null };
  const old = new Set(prev.ids);
  return { ids: new Set(ids.filter((i) => !old.has(i))), since: prev.at };
}

/** Copies of the entries with isNew set from their record id (the part of the key after "fed:"). */
export function markNew<T extends { key: string; isNew?: boolean }>(entries: T[] | null, fresh: Fresh | null): T[] | null {
  if (!entries || !fresh || !fresh.ids.size) return entries;
  return entries.map((e) => (fresh.ids.has(e.key.slice(e.key.indexOf(":") + 1)) ? { ...e, isNew: true } : e));
}

/** Inside ETO: the strong matches ETO's organization has already seen, kept by ETO for everyone who signs in.
 *  `since` is when they were last counted; null before the first count, when nothing is marked. */
export interface OrgSeen { keys: Set<string>; since: string | null }

/** Copies of the entries with isNew set on strong matches ETO hasn't seen yet. Used instead of markNew inside
 *  ETO, so Owners and Admins see the same marks on any device. */
export function markOrgNew<T extends { key: string; tier: string; isNew?: boolean }>(entries: T[] | null, seen: OrgSeen): T[] | null {
  if (!entries) return entries;
  return entries.map((e) => {
    const isNew = seen.since !== null && e.tier === "Strong" && !seen.keys.has(e.key);
    return e.isNew === isNew ? e : { ...e, isNew };
  });
}

/** The strong matches across the given lists, for ETO's count. Each key once, at most `max`. */
export function strongKeys(lists: ({ key: string; tier: string }[] | null)[], max = 2000): string[] {
  const keys = new Set<string>();
  for (const list of lists) for (const e of list ?? []) if (e.tier === "Strong") keys.add(e.key);
  return [...keys].sort().slice(0, max);
}
