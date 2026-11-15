// The shortlist, with where each grant stands: saved for later, being applied for, or submitted.
// Submitted ones leave the results so they stop coming up, and stay on the shortlist with their date.
// Kept in this browser only, under the same key as before stages existed.

import type { Entry } from "./entries";

export type Stage = "saved" | "applying" | "submitted";
/** In the order the shortlist shows them: the work in hand first. */
export const STAGES: { id: Stage; label: string; since: string }[] = [
  { id: "applying", label: "Applying", since: "Started" },
  { id: "saved", label: "Saved", since: "Saved" },
  { id: "submitted", label: "Submitted", since: "Submitted" },
];
export const STAGE_LABEL: Record<Stage, string> = { saved: "Saved", applying: "Applying", submitted: "Submitted" };

export type Item = Entry & { stage: Stage; stageAt: string };

const isStage = (v: unknown): v is Stage => v === "saved" || v === "applying" || v === "submitted";

/** Reads what was stored; items saved before stages existed count as saved, with no date. */
export function parseShortlist(raw: string | null): Item[] {
  try {
    const v = raw ? JSON.parse(raw) : [];
    if (!Array.isArray(v)) return [];
    return v.filter((e) => e && typeof e.key === "string")
      .map((e) => ({ ...e, stage: isStage(e.stage) ? e.stage : "saved", stageAt: typeof e.stageAt === "string" ? e.stageAt : "" }));
  } catch {
    return [];
  }
}

/** Adds an entry as saved, or takes it off the shortlist if it is already there. */
export function toggle(items: Item[], e: Entry, now: Date = new Date()): Item[] {
  if (items.some((x) => x.key === e.key)) return items.filter((x) => x.key !== e.key);
  const { isNew: _drop, ...rest } = e; // "new" is about one visit, not worth keeping
  return [...items, { ...rest, stage: "saved", stageAt: now.toISOString() }];
}

export function setStage(items: Item[], key: string, stage: Stage, now: Date = new Date()): Item[] {
  return items.map((x) => (x.key === key && x.stage !== stage ? { ...x, stage, stageAt: now.toISOString() } : x));
}

export function submittedKeys(items: Item[]): Set<string> {
  return new Set(items.filter((x) => x.stage === "submitted").map((x) => x.key));
}

/** The entries without the ones already submitted, and how many that took out. */
export function dropSubmitted<T extends { key: string }>(entries: T[] | null, done: Set<string>): { entries: T[] | null; hidden: number } {
  if (!entries || !done.size) return { entries, hidden: 0 };
  const kept = entries.filter((e) => !done.has(e.key));
  return { entries: kept, hidden: entries.length - kept.length };
}
