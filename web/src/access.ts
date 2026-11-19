// Accounts and the search gate. A visitor sees a preview (the counts and three results), a free account the counts
// and the top ten in each source; a Pro or Consultant account gets short-lived links to its state's data files and
// ranks them here, as before. Sign-in
// is by a code sent to the person's email, so it works inside ETO's page too, where a link would open a tab
// that can't see the framed page's sign-in.
import { createClient, type Session } from "@supabase/supabase-js";
import type { Entry, SourceKey } from "./entries";
import type { ProfileForm } from "./profile";
import type { Counts } from "./server/preview";

// Both are public by design: the publishable key only lets the page call what row level security allows.
export const SUPABASE_URL: string = import.meta.env.VITE_SUPABASE_URL || "https://lthfecwgvpekrjjqszof.supabase.co";
export const SUPABASE_KEY: string = import.meta.env.VITE_SUPABASE_KEY || "sb_publishable_S2pcGw5_agbrzxP5u-JKvQ_8xcHBIqz";
/** Where the plans and the waitlist are. */
export const PLANS_URL = "https://solutionsbyrich.com/grant-matcher/";

export const supabase = SUPABASE_KEY
  ? createClient(SUPABASE_URL, SUPABASE_KEY, { auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: false, storageKey: "gm-auth" } })
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

export async function signOut(): Promise<void> {
  await supabase?.auth.signOut();
}

/** Fires with the signed-in email (or null) now and whenever it changes. */
export function watchSession(on: (email: string | null) => void): () => void {
  if (!supabase) { on(null); return () => undefined; }
  void currentSession().then((s) => on(s?.user.email ?? null));
  const { data } = supabase.auth.onAuthStateChange((_event, s) => on(s?.user.email ?? null));
  return () => data.subscription.unsubscribe();
}
