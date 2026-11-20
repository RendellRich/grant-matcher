// Accounts and the search gate. A visitor sees a preview (the counts and three results), a free account the counts
// and the top ten in each source; a Pro or Consultant account gets short-lived links to its state's data files and
// ranks them here, as before. Sign-in
// is by a code sent to the person's email, so it works inside ETO's page too, where a link would open a tab
// that can't see the framed page's sign-in.
import { createClient, type Session } from "@supabase/supabase-js";
import type { Entry, SourceKey } from "./entries";
import type { ProfileForm } from "./profile";
import type { Counts } from "./server/preview";
import type { PlanView } from "../../supabase/functions/_shared/billing-core";

// Both are public by design: the publishable key only lets the page call what row level security allows.
export const SUPABASE_URL: string = import.meta.env.VITE_SUPABASE_URL || "https://lthfecwgvpekrjjqszof.supabase.co";
export const SUPABASE_KEY: string = import.meta.env.VITE_SUPABASE_KEY || "sb_publishable_S2pcGw5_agbrzxP5u-JKvQ_8xcHBIqz";
/** Where the plans and the waitlist are. */
export const PLANS_URL = "https://solutionsbyrich.com/grant-matcher/";

export const supabase = SUPABASE_KEY
  // PKCE, and reading the session from the address bar, so Sign in with Google can come back to the page.
  ? createClient(SUPABASE_URL, SUPABASE_KEY, { auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true, flowType: "pkce", storageKey: "gm-auth" } })
  : null;

export interface FileLink { name: string; json: string; f16: string; version: string }
export type Gate =
  | { state: "idle" }
  | { state: "checking" }
  | { state: "full"; files: Partial<Record<SourceKey, FileLink | null>>; plan: string | null }
  | { state: "preview"; reason: "visitor" | "free"; counts: Partial<Record<SourceKey, Counts>>; source: SourceKey | null;
      lists: Partial<Record<SourceKey, Entry[]>>; plan: string | null }
  | { state: "error"; message: string };

export async function currentSession(): Promise<Session | null> {
  if (!supabase) return null;
  try { return (await supabase.auth.getSession()).data.session; } catch { return null; }
}

/** Asks the gate for this profile. */
export async function search(form: ProfileForm, vector: number[] | null, signal?: AbortSignal): Promise<Gate> {
  if (!SUPABASE_KEY) return { state: "error", message: "Search isn't set up on this copy of the site." };
  const session = await currentSession();
  const res = await fetch(`${SUPABASE_URL}/functions/v1/search`, {
    method: "POST", signal,
    headers: { Authorization: `Bearer ${session?.access_token ?? SUPABASE_KEY}`, apikey: SUPABASE_KEY, "Content-Type": "application/json" },
    body: JSON.stringify({ form, vector }),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) return { state: "error", message: body.error ?? "Search is unavailable right now. Try again in a minute." };
  if (body.access === "full") return { state: "full", files: body.files ?? {}, plan: body.plan ?? null };
  const lists = body.lists && typeof body.lists === "object" ? body.lists : {};
  return {
    state: "preview", reason: body.reason === "free" ? "free" : "visitor", counts: body.counts ?? {}, source: body.source ?? null,
    lists: Object.fromEntries(Object.entries(lists).filter(([, v]) => Array.isArray(v))), plan: body.plan ?? null,
  };
}

/** Sends a sign-in code. New emails get an account. */
export async function sendCode(email: string): Promise<string | null> {
  if (!supabase) return "Sign-in isn't set up on this copy of the site.";
  const { error } = await supabase.auth.signInWithOtp({ email, options: { shouldCreateUser: true } });
  if (!error) return null;
  return /rate|too many|seconds/i.test(error.message) ? "Too many codes were asked for. Wait a minute, then try again." : "That code couldn't be sent. Check the email address and try again.";
}

export async function verifyCode(email: string, code: string): Promise<string | null> {
  if (!supabase) return "Sign-in isn't set up on this copy of the site.";
  const { error } = await supabase.auth.verifyOtp({ email, token: code.replace(/\s+/g, ""), type: "email" });
  return error ? "That code didn't work. Codes expire after an hour; ask for a new one if it's old." : null;
}

/** True when Sign in with Google is switched on for the project (Supabase's public auth settings). */
export async function googleEnabled(): Promise<boolean> {
  if (!SUPABASE_KEY) return false;
  try {
    const res = await fetch(`${SUPABASE_URL}/auth/v1/settings`, { headers: { apikey: SUPABASE_KEY } });
    return res.ok && (await res.json())?.external?.google === true;
  } catch { return false; }
}

/** Goes to Google to sign in, and comes back to this page. An account that signed in by email code before is the
 *  same account when the Google email matches. Returns an error to show, or nothing while the page leaves. */
export async function signInWithGoogle(): Promise<string | null> {
  if (!supabase) return "Sign-in isn't set up on this copy of the site.";
  const back = `${window.location.origin}${window.location.pathname}`;
  const { error } = await supabase.auth.signInWithOAuth({ provider: "google", options: { redirectTo: back } });
  return error ? "Google sign-in isn't available right now. Use the email code instead." : null;
}

/** What Google or Supabase said when a sign-in came back with an error (?error_description=), taken out of the
 *  address bar. A successful return's ?code= is left for the sign-in library, and cleared once signed in. */
export function takeSignInReturn(): string | null {
  try {
    const url = new URL(window.location.href);
    const problem = url.searchParams.get("error_description") ?? url.searchParams.get("error");
    let changed = false;
    for (const k of ["error", "error_code", "error_description"]) if (url.searchParams.has(k)) { url.searchParams.delete(k); changed = true; }
    if (changed) history.replaceState(null, "", url.toString());
    return problem ? "Google sign-in didn't finish. Try again, or use the email code." : null;
  } catch { return null; }
}

/** Takes a used ?code= (from Sign in with Google) out of the address bar. */
function clearCodeParam(): void {
  try {
    const url = new URL(window.location.href);
    if (!url.searchParams.has("code")) return;
    url.searchParams.delete("code");
    history.replaceState(null, "", url.toString());
  } catch { /* */ }
}

export async function signOut(): Promise<void> {
  await supabase?.auth.signOut();
}

/** Fires with the signed-in email (or null) now and whenever it changes. */
export function watchSession(on: (email: string | null) => void): () => void {
  if (!supabase) { on(null); return () => undefined; }
  void currentSession().then((s) => on(s?.user.email ?? null));
  const { data } = supabase.auth.onAuthStateChange((_event, s) => {
    if (s) clearCodeParam();
    on(s?.user.email ?? null);
  });
  return () => data.subscription.unsubscribe();
}

/** Starts a Pro or Consultant checkout, or opens the billing portal, and goes there. Returns an error to show. */
export async function billing(action: "checkout" | "portal", plan?: "pro" | "consultant", interval: Interval = "month"): Promise<string | null> {
  const session = await currentSession();
  if (!session) return "Sign in first.";
  try {
    const res = await fetch(`${SUPABASE_URL}/functions/v1/billing`, {
      method: "POST",
      headers: { Authorization: `Bearer ${session.access_token}`, apikey: SUPABASE_KEY, "Content-Type": "application/json" },
      body: JSON.stringify({ action, plan, interval }),
    });
    const body = await res.json().catch(() => ({}));
    if (!res.ok || !body.url) return body.error ?? "Billing is unavailable right now. Try again in a minute.";
    window.location.assign(body.url);
    return null;
  } catch {
    return "Billing is unavailable right now. Check your connection and try again.";
  }
}

export const isPaid = (plan: string | null | undefined) => plan === "pro" || plan === "consultant";

export type Interval = "month" | "year";
export interface Upgrade { plan: "pro" | "consultant"; interval: Interval }

/** "pro" or "pro:year", as kept in sessionStorage. */
export function parseUpgrade(v: string | null): Upgrade | null {
  const [plan, interval] = (v ?? "").split(":");
  if (plan !== "pro" && plan !== "consultant") return null;
  return { plan, interval: interval === "year" ? "year" : "month" };
}
export const saveUpgrade = (u: Upgrade): void => {
  try { sessionStorage.setItem("gm-upgrade", u.interval === "year" ? `${u.plan}:year` : u.plan); } catch { /* */ }
};

/** A plan the person picked on the pricing page (?upgrade=pro, &interval=year for yearly), kept through sign-in. */
export function takeUpgradeParam(): Upgrade | null {
  try {
    const url = new URL(window.location.href);
    const picked = parseUpgrade(url.searchParams.get("upgrade"));
    if (picked) {
      if (url.searchParams.get("interval") === "year") picked.interval = "year";
      saveUpgrade(picked);
      url.searchParams.delete("upgrade");
      url.searchParams.delete("interval");
      history.replaceState(null, "", url.toString());
    }
    return parseUpgrade(sessionStorage.getItem("gm-upgrade"));
  } catch { return null; }
}
export function clearUpgrade(): void { try { sessionStorage.removeItem("gm-upgrade"); } catch { /* */ } }

/** True once, right after Stripe sends someone back from a finished checkout (?upgraded=1). */
export function takeUpgradedParam(): boolean {
  try {
    const url = new URL(window.location.href);
    if (url.searchParams.get("upgraded") !== "1") return false;
    url.searchParams.delete("upgraded");
    history.replaceState(null, "", url.toString());
    return true;
  } catch { return false; }
}

/** The account's weekly email of new strong matches (paid plans). */
export interface DigestInfo {
  on: boolean; sent_at?: string | null; profile?: unknown; reminders?: boolean; reminder_count?: number;
  /** Consultant: one email per client or one combined, and each client's weekly email. */
  plan?: string; mode?: "each" | "combined"; clients?: { id: string; label: string; on: boolean; ready: boolean }[];
}

export async function myDigest(): Promise<DigestInfo | null> {
  if (!supabase) return null;
  const { data, error } = await supabase.rpc("my_digest");
  return error ? null : (data as DigestInfo);
}

/** Turns the weekly email on for this profile, or off (which deletes the saved profile). */
export async function saveDigest(form: unknown, vector: number[] | null, on: boolean): Promise<{ info?: DigestInfo; error?: string }> {
  if (!supabase) return { error: "Sign in first." };
  const { data, error } = await supabase.rpc("save_digest", { p_profile: on ? form : null, p_vector: on ? vector : null, p_on: on });
  if (error) return { error: error.message.includes("Pro") ? "The weekly email comes with Pro." : "Couldn't save that. Try again in a minute." };
  return { info: data as DigestInfo };
}

/** Which email a "Turn it off" link was for, and its token (?weekly-off= or ?reminders-off=), taken out of the
 *  address bar. */
export type EmailKind = "weekly" | "reminders";
export function takeEmailOffParam(): { kind: EmailKind; token: string } | null {
  try {
    const url = new URL(window.location.href);
    for (const kind of ["weekly", "reminders"] as const) {
      const t = url.searchParams.get(`${kind}-off`);
      if (!t) continue;
      url.searchParams.delete(`${kind}-off`);
      history.replaceState(null, "", url.toString());
      return /^[0-9a-f-]{36}$/i.test(t) ? { kind, token: t } : null;
    }
    return null;
  } catch { return null; }
}

/** Turns one email off for the address the link was sent to. */
export async function emailOff(kind: EmailKind, token: string): Promise<boolean> {
  const fn = kind === "weekly" ? "weekly-email" : "deadline-reminders";
  try {
    const res = await fetch(`${SUPABASE_URL}/functions/v1/${fn}?off=${encodeURIComponent(token)}`, { method: "POST" });
    return res.ok;
  } catch { return false; }
}

/** Turns deadline reminders on with these shortlisted grants (replacing the last set), or off. */
/** Reminders for the shortlist; on Consultant, `client` says whose shortlist it is (that client's set is replaced). */
export async function saveReminders(on: boolean, items: unknown[], client: string | null = null): Promise<{ info?: DigestInfo; error?: string }> {
  if (!supabase) return { error: "Sign in first." };
  const { data, error } = await supabase.rpc("set_reminders", { p_on: on, p_items: on ? items : [], p_id: client });
  if (error) return { error: error.message.includes("Pro") ? "Deadline reminders come with Pro." : "Couldn't save that. Try again in a minute." };
  return { info: data as DigestInfo };
}

// ---------- profile and shortlist on any device (sync.ts) ----------

/** The account's saved profile and shortlist (for client `id` on Consultant), or null when signed out or unreachable. */
export async function myWorkspace(id: string | null = null): Promise<unknown | null> {
  if (!supabase) return null;
  const { data, error } = await supabase.rpc("my_workspace", { p_id: id });
  return error ? null : data;
}

export async function saveProfileRemote(form: ProfileForm, vector: number[] | null, id: string | null = null): Promise<boolean> {
  if (!supabase) return false;
  const { data, error } = await supabase.rpc("save_profile", { p_profile: form, p_vector: vector, p_id: id });
  return !error && (data as { ok?: boolean })?.ok === true;
}

/** Saves the shortlist over version `base`. A conflict brings back the account's newer copy. */
export type ShortlistSave = { ok: true; version: number } | { ok: false; version?: number; shortlist?: unknown; off?: boolean; failed?: boolean };
export async function saveShortlistRemote(items: unknown[], base: number, id: string | null = null): Promise<ShortlistSave> {
  if (!supabase) return { ok: false, failed: true };
  const { data, error } = await supabase.rpc("save_shortlist", { p_items: items, p_base: base, p_id: id });
  if (error || !data) return { ok: false, failed: true };
  return data as ShortlistSave;
}

/** Consultant client profiles: add, rename, delete. Each returns an error to show, or the new id. */
export async function addClient(label: string): Promise<{ id?: string; error?: string }> {
  if (!supabase) return { error: "Sign in first." };
  const { data, error } = await supabase.rpc("add_client", { p_label: label });
  if (error) return { error: /keeps 10/.test(error.message) ? "You have 10 clients, the most this plan keeps." : /Name the client|Consultant|Turn on saving/.test(error.message) ? error.message : "Couldn't add that client. Try again in a minute." };
  return { id: (data as { id?: string })?.id };
}
export async function renameClient(id: string, label: string): Promise<string | null> {
  if (!supabase) return "Sign in first.";
  const { error } = await supabase.rpc("rename_client", { p_id: id, p_label: label });
  return error ? (/Name the client/.test(error.message) ? error.message : "Couldn't rename that client. Try again in a minute.") : null;
}
export async function deleteClient(id: string): Promise<string | null> {
  if (!supabase) return "Sign in first.";
  const { error } = await supabase.rpc("delete_client", { p_id: id });
  return error ? (/at least one/.test(error.message) ? error.message : "Couldn't delete that client. Try again in a minute.") : null;
}

/** Turns saving to the account on, or off (which deletes the saved copies). Returns the new workspace. */
export async function setSync(on: boolean): Promise<unknown | null> {
  if (!supabase) return null;
  const { data, error } = await supabase.rpc("set_sync", { p_on: on });
  return error ? null : data;
}

// ---------- the plan line ----------
export type { PlanView };
export interface PlanStatus { plan: string; status: string; billing: PlanView | null }

/** How a paid plan is billed and when it renews, or null when it can't be read right now. */
export async function planStatus(): Promise<PlanStatus | null> {
  const session = await currentSession();
  if (!session) return null;
  try {
    const res = await fetch(`${SUPABASE_URL}/functions/v1/billing`, {
      method: "POST",
      headers: { Authorization: `Bearer ${session.access_token}`, apikey: SUPABASE_KEY, "Content-Type": "application/json" },
      body: JSON.stringify({ action: "status" }),
    });
    if (!res.ok) return null;
    const body = await res.json();
    return body && typeof body.plan === "string" ? (body as PlanStatus) : null;
  } catch { return null; }
}

/** Consultant: turns the weekly email on or off for one client, and picks one email per client or one combined. */
export async function saveClientDigest(id: string, on: boolean): Promise<{ info?: DigestInfo; error?: string }> {
  if (!supabase) return { error: "Sign in first." };
  const { data, error } = await supabase.rpc("save_client_digest", { p_id: id, p_on: on });
  if (error) return { error: /Search with this client/.test(error.message) ? "Search with this client's profile first, then turn the email on." : "Couldn't save that. Try again in a minute." };
  return { info: data as DigestInfo };
}
export async function setDigestMode(mode: "each" | "combined"): Promise<{ info?: DigestInfo; error?: string }> {
  if (!supabase) return { error: "Sign in first." };
  const { data, error } = await supabase.rpc("set_digest_mode", { p_mode: mode });
  return error ? { error: "Couldn't save that. Try again in a minute." } : { info: data as DigestInfo };
}
