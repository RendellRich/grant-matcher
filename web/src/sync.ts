// Profile and shortlist on any device (Pro and Consultant). The browser keeps its own copy as before; while
// saving is on, the account keeps one too (supabase/migrations/20261120140000_saved_workspace.sql).
//
// The shortlist is saved whole, with a version number. This browser remembers which account and version its
// copy came from, and whether it has changed since. On load it takes the account's copy unless it has changes
// of its own; a save that finds a newer version on the account merges the two and saves again. The profile
// is simpler: the last one searched with wins.
import { parseShortlist, type Item } from "./shortlist";

/** What this browser knows about its shortlist's link to an account. */
export interface SyncState { account: string; version: number; dirty: boolean }

const KEY = "gm-sync";
export function readSync(): SyncState | null {
  try {
    const v = JSON.parse(localStorage.getItem(KEY) ?? "null");
    return v && typeof v.account === "string" && typeof v.version === "number" ? { account: v.account, version: v.version, dirty: Boolean(v.dirty) } : null;
  } catch { return null; }
}
export function writeSync(s: SyncState | null): void {
  try { if (s) localStorage.setItem(KEY, JSON.stringify(s)); else localStorage.removeItem(KEY); } catch { /* private mode */ }
}

const when = (x: Item) => x.at || x.stageAt || "";

/**
 * Both copies, item by item: anything on either list is kept, and an item on both keeps the copy that changed
 * last. Order follows `mine`, then what only `theirs` has. A grant removed on one device while the other
 * changed the list can come back; removing it again sticks.
 */
export function mergeShortlists(mine: Item[], theirs: Item[]): Item[] {
  const other = new Map(theirs.map((x) => [x.key, x]));
  const out = mine.map((x) => {
    const t = other.get(x.key);
    return t && when(t) > when(x) ? t : x;
  });
  const have = new Set(mine.map((x) => x.key));
  for (const t of theirs) if (!have.has(t.key)) out.push(t);
  return out;
}

export interface Workspace {
  paid: boolean;
  on: boolean;
  profile: unknown | null;
  vector: number[] | null;
  version: number;
  shortlist: Item[] | null;
}

export function parseWorkspace(v: unknown): Workspace {
  const o = (v && typeof v === "object" ? v : {}) as Record<string, unknown>;
  return {
    paid: o.paid === true,
    on: o.on === true,
    profile: o.profile && typeof o.profile === "object" ? o.profile : null,
    vector: Array.isArray(o.vector) && o.vector.length === 384 ? (o.vector as number[]) : null,
    version: typeof o.version === "number" ? o.version : 0,
    shortlist: Array.isArray(o.shortlist) ? parseShortlist(JSON.stringify(o.shortlist)) : null,
  };
}

/**
 * What to do with the shortlist when an account's copy arrives.
 * - This browser's copy is clean and from this account: take the account's.
 * - It has changes, or was never linked to an account: merge, and save the result.
 * - It was linked to a different account: that list isn't this account's, so take the account's.
 */
export function onLoad(local: Item[], state: SyncState | null, account: string, ws: Workspace): { items: Item[]; push: boolean } {
  const saved = ws.shortlist ?? [];
  if (state && state.account !== account) return { items: saved, push: false };
  if (state && !state.dirty) return { items: saved, push: false };
  if (!state && !local.length) return { items: saved, push: false };
  const items = state && state.version === ws.version ? local : mergeShortlists(local, saved);
  return { items, push: true };
}
