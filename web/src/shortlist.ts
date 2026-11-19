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

export type Item = Entry & { stage: Stage; stageAt: string; due?: string }; // due: the person's own date, "YYYY-MM-DD"

const isStage = (v: unknown): v is Stage => v === "saved" || v === "applying" || v === "submitted";

/** Reads what was stored; items saved before stages existed count as saved, with no date. */
export function parseShortlist(raw: string | null): Item[] {
  try {
    const v = raw ? JSON.parse(raw) : [];
    if (!Array.isArray(v)) return [];
    return v.filter((e) => e && typeof e.key === "string")
      .map((e) => ({
        ...e, stage: isStage(e.stage) ? e.stage : "saved", stageAt: typeof e.stageAt === "string" ? e.stageAt : "",
        due: typeof e.due === "string" && YMD.test(e.due) ? e.due : undefined,
      }));
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

// ---------------- deadlines ----------------

const YMD = /^\d{4}-\d{2}-\d{2}$/;
export const ymd = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const parseYmd = (s: string) => { const [y, m, d] = s.split("-").map(Number); return new Date(y, m - 1, d); };

/** The person's own deadline for one entry; an empty value clears it. */
export function setDue(items: Item[], key: string, due: string): Item[] {
  const v = YMD.test(due) ? due : undefined;
  return items.map((x) => (x.key === key ? { ...x, due: v } : x));
}

/** What Grants.gov lists today for each shortlisted federal grant: its close date, null for none, or
 *  "gone" when it is no longer in the list (closed or withdrawn). Other sources have no listed dates. */
export type Listed = Map<string, string | null | "gone">;
export function listedNow(items: Item[], records: { id: string; close: Date | null }[] | null): Listed {
  const out: Listed = new Map();
  if (!records) return out;
  const byId = new Map(records.map((r) => [String(r.id), r.close]));
  for (const x of items) {
    if (x.source !== "fed") continue;
    const id = x.key.slice(x.key.indexOf(":") + 1);
    out.set(x.key, byId.has(id) ? (byId.get(id) ? ymd(byId.get(id)!) : null) : "gone");
  }
  return out;
}

/** The close date as it was when the entry was added. */
export const savedClose = (x: Item) => (x.sortClose ? ymd(new Date(x.sortClose)) : null);

export interface Deadline { date: string; own: boolean; changedFrom?: string; gone?: boolean }

/** The date to work toward: the person's own, else the listed one (today's listing when known). */
export function deadline(x: Item, listed: Listed): Deadline | null {
  const now = listed.get(x.key);
  const was = savedClose(x);
  const gone = now === "gone";
  const listedDate = now === undefined || gone ? was : now;
  const changedFrom = !gone && now !== undefined && was && now !== was ? was : undefined;
  if (x.due) return { date: x.due, own: true, changedFrom, gone };
  if (listedDate) return { date: listedDate, own: false, changedFrom, gone };
  return gone ? { date: "", own: false, gone } : null;
}

export function daysUntil(date: string, today: Date): number {
  const t = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  return Math.round((parseYmd(date).getTime() - t.getTime()) / 86_400_000);
}

export function dueText(days: number): string {
  if (days < 0) return days === -1 ? "Past due by 1 day" : `Past due by ${-days} days`;
  if (days === 0) return "Due today";
  if (days === 1) return "Due tomorrow";
  return `Due in ${days} days`;
}

/** Not yet submitted, with a deadline inside the window (or already past), soonest first. */
export function comingUp(items: Item[], listed: Listed, today: Date, within = 30): { item: Item; days: number; d: Deadline }[] {
  const out = [];
  for (const item of items) {
    if (item.stage === "submitted") continue;
    const d = deadline(item, listed);
    if (!d?.date) continue;
    const days = daysUntil(d.date, today);
    if (days <= within) out.push({ item, days, d });
  }
  return out.sort((a, b) => a.days - b.days);
}

/** Soonest deadline first; entries with no date after, in the order they were added. */
export function byDeadline(items: Item[], listed: Listed): Item[] {
  const date = (x: Item) => deadline(x, listed)?.date || "9999";
  return items.map((x, i) => [x, i] as const).sort((a, b) => date(a[0]).localeCompare(date(b[0])) || a[1] - b[1]).map(([x]) => x);
}

const icsText = (s: string) => s.replace(/\\/g, "\\\\").replace(/[,;]/g, (c) => "\\" + c).replace(/\r?\n/g, " ");

/** One all-day event per deadline still ahead, each with reminders 14 days and 3 days before. */
export function shortlistIcs(items: Item[], listed: Listed, today: Date, stamp: Date = new Date()): string {
  const st = stamp.toISOString().replace(/[-:]/g, "").slice(0, 15) + "Z";
  const lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//grant-matcher//shortlist//EN", "CALSCALE:GREGORIAN"];
  for (const x of items) {
    if (x.stage === "submitted") continue;
    const d = deadline(x, listed);
    if (!d?.date || daysUntil(d.date, today) < 0) continue;
    const label = d.own ? "Your deadline" : "Due";
    const day = d.date.replace(/-/g, "");
    const next = ymd(new Date(parseYmd(d.date).getTime() + 36 * 3_600_000)).replace(/-/g, "");
    lines.push("BEGIN:VEVENT", `UID:shortlist-${x.key.replace(":", "-")}@grant-matcher`, `DTSTAMP:${st}`,
      `DTSTART;VALUE=DATE:${day}`, `DTEND;VALUE=DATE:${next}`, `SUMMARY:${icsText(`${label}: ${x.title}`).slice(0, 150)}`,
      `DESCRIPTION:${icsText([x.catalog, x.url].filter(Boolean).join(" "))}`);
    if (x.url) lines.push(`URL:${x.url}`);
    for (const [n, word] of [[14, "Two weeks"], [3, "Three days"]] as const) {
      lines.push("BEGIN:VALARM", "ACTION:DISPLAY", `TRIGGER:-P${n}D`, `DESCRIPTION:${icsText(`${word} until ${label.toLowerCase()}: ${x.title}`)}`, "END:VALARM");
    }
    lines.push("END:VEVENT");
  }
  lines.push("END:VCALENDAR");
  return lines.join("\r\n") + "\r\n";
}

/** What deadline reminders need for each shortlisted grant not yet submitted whose deadline is today or later. */
export interface ReminderItem { key: string; title: string; url: string; source: string; stage: Stage; due: string }
export function reminderItems(items: Item[], listed: Listed, today: Date, max = 200): ReminderItem[] {
  const out: ReminderItem[] = [];
  for (const x of byDeadline(items, listed)) {
    if (x.stage === "submitted") continue;
    const d = deadline(x, listed);
    if (!d?.date || d.gone || daysUntil(d.date, today) < 0) continue;
    out.push({ key: x.key, title: x.title, url: x.url || "", source: x.source, stage: x.stage, due: d.date });
    if (out.length >= max) break;
  }
  return out;
}
