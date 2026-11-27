// Words a source requires wherever its listings are shown (disclaimers.json, one entry per state code; Python reads
// the same file). Missouri: https://mo.gov/data-policy. Anything that lists state calls (cards, downloads, calendar
// files, emails, what is handed to ETO) adds them, read off the entry keys ("fl:mo-...").
import DISCLAIMERS from "./disclaimers.json";

export interface Notice { name: string; text: string }

export function noticesFor(keys: string[]): Notice[] {
  const codes = new Set(keys.map((k) => /^fl:([a-z]{2})-/.exec(k)?.[1].toUpperCase()));
  return Object.entries(DISCLAIMERS as Record<string, Notice>).filter(([c]) => codes.has(c)).map(([, n]) => n);
}

export const noticeLines = (keys: string[]): string[] => noticesFor(keys).map((n) => `Notice for ${n.name} listings: ${n.text}`);
