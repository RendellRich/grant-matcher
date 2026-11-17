// Embed mode: the Grant Matcher running inside Exceed the Odds' admin page (?embed=eto).
//
// The two pages talk with window.postMessage. Every message is checked both ways: this page only listens to
// its own parent window, only when that parent's origin is on the list below, and only ever posts to that
// origin. The profile ETO sends is cleaned by parseProfile like a loaded file. What goes back is the profile
// (to save in ETO) and public facts about a grant or funder (to add to ETO's funding pipeline). Nothing is
// sent anywhere else.

import type { Entry } from "./entries";
import { parseProfile, type ProfileForm } from "./profile";

export const PROTOCOL = 1;

/** Sites allowed to embed the matcher and send it a profile. Local addresses are for ETO's own development. */
export const ALLOWED_PARENTS = [
  "https://exceedtheodds.com",
  "https://www.exceedtheodds.com",
  "http://localhost:5173",
  "http://127.0.0.1:5173",
];

export const isAllowedParent = (origin: string) => ALLOWED_PARENTS.includes(origin);

/** The embedding site's origin when this page runs inside an allowed one with ?embed=eto, else null. */
export function embedParent(loc: { search: string; ancestorOrigins?: ArrayLike<string> }, referrer: string, framed: boolean): string | null {
  if (!framed || new URLSearchParams(loc.search).get("embed") !== "eto") return null;
  const ancestors = loc.ancestorOrigins ? Array.from(loc.ancestorOrigins) : [];
  let origin = ancestors[0] ?? "";
  if (!origin && referrer) {
    try { origin = new URL(referrer).origin; } catch { origin = ""; }
  }
  return isAllowedParent(origin) ? origin : null;
}

/** Where a grant sits in ETO's pipeline, as ETO reports it. */
export interface PipelineItem { key: string; stage: string; closed: boolean }

/** What "Send to funding pipeline" hands ETO: public facts only, in the shape ETO's save function takes. */
export interface SendPayload {
  key: string; // "fed:355824", "fdn:591234567", "fl:10.123"; ETO keeps it so nothing is sent twice
  source: "federal" | "foundation" | "florida";
  title: string; // the opportunity or the funder's name
  funder: string; // the agency or the foundation
  ein: string | null;
  website: string | null;
  url: string | null; // the notice or the page to apply from
  deadline: string | null; // yyyy-mm-dd
  amount_low: number | null;
  amount_high: number | null;
  catalog: string;
  summary: string;
  fits: string[];
  cautions: string[];
  website_note: string | null; // the sentence the weekly website check found
  score: number;
  tier: string;
}

const ymd = (t: number) => { const d = new Date(t); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };
const row = (e: Entry, label: string) => e.rows?.find((r) => r.label === label);

export function payloadFor(e: Entry): SendPayload {
  const site = row(e, "Website")?.href ?? null;
  const quote = row(e, "On its website")?.text ?? null;
  const applyLink = row(e, "Application link")?.href ?? row(e, "Page checked")?.href ?? null;
  const source = e.source === "fed" ? "federal" : e.source === "fdn" ? "foundation" : "florida";
  return {
    key: e.key, source, title: e.title,
    funder: e.source === "fdn" ? e.title : e.agency ?? "",
    ein: e.source === "fdn" ? e.key.slice(4) : null,
    website: site,
    url: (e.source === "fdn" ? applyLink ?? site : e.url) || null,
    deadline: e.sortClose ? ymd(e.sortClose) : null,
    amount_low: e.source === "fed" ? e.amountLow ?? null : e.source === "fdn" ? e.sortMedian ?? null : null,
    amount_high: e.source === "fed" ? e.amountHigh ?? null : e.source === "fdn" ? e.sortMedian ?? null : null,
    catalog: e.catalog,
    summary: (e.summary ?? "").slice(0, 1000),
    fits: e.fits.slice(0, 8), cautions: e.cautions.slice(0, 8),
    website_note: quote, score: e.score, tier: e.tier,
  };
}

// ---------------- messages ----------------

export type Incoming =
  | { type: "eto:profile"; profile: ProfileForm }
  | { type: "eto:in-pipeline"; items: PipelineItem[] }
  | { type: "eto:sent"; key: string; ok: boolean; status: "saved" | "exists" | "error"; stage: string; message: string }
  | { type: "eto:profile-saved"; ok: boolean; message: string };

const str = (v: unknown, max = 300) => (typeof v === "string" ? v.slice(0, max) : "");

/** Reads a message from ETO, or null when it isn't one this page understands. Never trusts its shape. */
export function readMessage(data: unknown): Incoming | null {
  if (!data || typeof data !== "object") return null;
  const d = data as Record<string, unknown>;
  switch (d.type) {
    case "eto:profile":
      try { return { type: "eto:profile", profile: parseProfile(JSON.stringify(d.profile ?? {})) }; } catch { return null; }
    case "eto:in-pipeline":
      return {
        type: "eto:in-pipeline",
        items: (Array.isArray(d.items) ? d.items : []).slice(0, 5000)
          .filter((x): x is Record<string, unknown> => !!x && typeof x === "object" && typeof (x as Record<string, unknown>).key === "string")
          .map((x) => ({ key: str(x.key, 80), stage: str(x.stage, 60), closed: x.closed === true })),
      };
    case "eto:sent": {
      const status = d.status === "saved" || d.status === "exists" ? d.status : "error";
      return { type: "eto:sent", key: str(d.key, 80), ok: d.ok === true && status !== "error", status, stage: str(d.stage, 60), message: str(d.message) };
    }
    case "eto:profile-saved":
      return { type: "eto:profile-saved", ok: d.ok === true, message: str(d.message) };
    default:
      return null;
  }
}

export type Outgoing =
  | { type: "gm:ready"; protocol: number }
  | { type: "gm:send"; item: SendPayload }
  | { type: "gm:save-profile"; profile: ProfileForm };

/** Listens to the parent window at `origin` only. Returns a function that stops listening. */
export function listen(origin: string, onMessage: (m: Incoming) => void): () => void {
  const handler = (ev: MessageEvent) => {
    if (ev.origin !== origin || ev.source !== window.parent) return;
    const m = readMessage(ev.data);
    if (m) onMessage(m);
  };
  window.addEventListener("message", handler);
  return () => window.removeEventListener("message", handler);
}

export function post(origin: string, m: Outgoing): void {
  window.parent.postMessage(m, origin);
}

/** Where a loaded profile came from, for the example menu's extra option. */
export type LoadedFrom = "file" | "eto";
export function loadedLabel(from: LoadedFrom): string {
  return from === "eto" ? "ETO's saved profile" : "Loaded from a file";
}
