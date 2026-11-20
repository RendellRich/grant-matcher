// Keeps the profile and shortlist the same on every device a Pro account signs in on (sync.ts has the rules).
import { useEffect, useRef, useState } from "preact/hooks";
import { myWorkspace, saveProfileRemote, saveShortlistRemote, setSync } from "./access";
import { parseProfile, type ProfileForm } from "./profile";
import type { Item } from "./shortlist";
import { mergeShortlists, onLoad, parseWorkspace, readSync, writeSync, type Workspace } from "./sync";

export interface SyncProps {
  email: string | null;
  enabled: boolean; // a paid plan, outside ETO
  items: Item[];
  replace: (items: Item[]) => void;
  applied: ProfileForm;
  vector: number[] | null;
  /** True once the profile on screen is the person's own (searched with, or loaded from the account). */
  ownProfile: boolean;
  /** Puts the account's profile on screen, unless the person already searched with their own this visit. */
  loadProfile: (f: ProfileForm, vector: number[] | null) => boolean;
}

const json = (v: unknown) => JSON.stringify(v);
const RETRY_MS = 30_000;

/** What the last talk with the account came to, for the line under "On any device". */
export type SaveState = { kind: "idle" } | { kind: "saving" } | { kind: "saved"; at: Date } | { kind: "failed"; what: "save" | "load" };

export function useAccountSync(p: SyncProps) {
  const [ws, setWs] = useState<Workspace | null>(null);
  const [loaded, setLoaded] = useState(0); // bumps when the account's copy should be read again
  const [state, setState] = useState<SaveState>({ kind: "idle" });
  const [retry, setRetry] = useState(0); // bumps to try a failed save again
  const ready = useRef(false);
  const items = useRef(p.items);
  items.current = p.items;
  const lastItems = useRef<string | null>(null); // the shortlist as the account last saved it
  const lastProfile = useRef<string | null>(null);
  const account = p.email ?? "";

  async function push(list: Item[], base: number, tries = 0): Promise<void> {
    if (!tries) setState({ kind: "saving" });
    const r = await saveShortlistRemote(list, base);
    if (r.ok) {
      if (json(items.current) === json(list)) lastItems.current = json(list);
      writeSync({ account, version: r.version, dirty: json(items.current) !== json(list) });
      setState({ kind: "saved", at: new Date() });
      return;
    }
    if (r.off) { setState({ kind: "idle" }); setWs((w) => (w ? { ...w, on: false } : w)); return; }
    if (r.failed || r.version === undefined || tries >= 2) {
      // Still marked changed here, so it goes up with the next change, the retry below or the next visit.
      lastItems.current = null;
      setState({ kind: "failed", what: "save" });
      return;
    }
    // Another device saved first: merge both and save over its version.
    const theirs = parseWorkspace({ shortlist: r.shortlist }).shortlist ?? [];
    const merged = mergeShortlists(items.current, theirs);
    writeSync({ account, version: r.version, dirty: true });
    lastItems.current = json(merged); // already being saved here
    if (json(merged) !== json(items.current)) { items.current = merged; p.replace(merged); }
    await push(merged, r.version, tries + 1);
  }

  // Read the account's copy when a paid account signs in (and when saving is turned back on).
  useEffect(() => {
    ready.current = false;
    if (!p.enabled || !p.email) { setWs(null); return; }
    let live = true;
    void myWorkspace().then((raw) => {
      if (!live) return;
      if (raw === null) { setState({ kind: "failed", what: "load" }); return; }
      setState({ kind: "idle" });
      const w = parseWorkspace(raw);
      setWs(w);
      if (!w.paid || !w.on) return;
      const plan = onLoad(items.current, readSync(), account, w);
      if (json(plan.items) !== json(items.current)) p.replace(plan.items);
      items.current = plan.items;
      lastItems.current = json(plan.items);
      if (plan.push) void push(plan.items, w.version);
      else writeSync({ account, version: w.version, dirty: false });
      let took = false;
      if (w.profile) {
        try {
          const f = parseProfile(json(w.profile));
          took = p.loadProfile(f, w.vector);
          if (took) lastProfile.current = json(f);
        } catch { /* a profile this version can't read: keep the one on screen */ }
      }
      if (!took && p.ownProfile) {
        const f = json(p.applied);
        void saveProfileRemote(p.applied, p.vector).then((ok) => { if (ok) lastProfile.current = f; else setState({ kind: "failed", what: "save" }); });
      }
      ready.current = true;
    });
    return () => { live = false; };
  }, [p.enabled, p.email, loaded]);

  // Save the shortlist a moment after it changes.
  const itemsJson = json(p.items);
  useEffect(() => {
    if (!ready.current || !ws?.on || itemsJson === lastItems.current) return;
    const s = readSync();
    const base = s && s.account === account ? s.version : ws.version;
    writeSync({ account, version: base, dirty: true });
    const t = setTimeout(() => { void push(items.current, readSync()?.version ?? base); }, 1200);
    return () => clearTimeout(t);
  }, [itemsJson, ws?.on, retry]);

  // Save the profile a moment after the person searches with a new one.
  const profileJson = json(p.applied);
  useEffect(() => {
    if (!ready.current || !ws?.on || !p.ownProfile || profileJson === lastProfile.current) return;
    const t = setTimeout(() => {
      setState({ kind: "saving" });
      void saveProfileRemote(p.applied, p.vector).then((ok) => {
        if (ok) { lastProfile.current = profileJson; setState({ kind: "saved", at: new Date() }); }
        else setState({ kind: "failed", what: "save" });
      });
    }, 1500);
    return () => clearTimeout(t);
  }, [profileJson, p.ownProfile, p.vector, ws?.on, retry]);

  // After a failure, try again in half a minute, or as soon as the connection comes back.
  useEffect(() => {
    if (state.kind !== "failed") return;
    const again = () => { if (state.what === "load") setLoaded((n) => n + 1); else setRetry((n) => n + 1); };
    const t = setTimeout(again, RETRY_MS);
    window.addEventListener("online", again);
    return () => { clearTimeout(t); window.removeEventListener("online", again); };
  }, [state]);

  async function turn(on: boolean): Promise<boolean> {
    const raw = await setSync(on);
    if (raw === null) return false;
    if (!on) { writeSync(null); lastItems.current = null; lastProfile.current = null; setWs(parseWorkspace(raw)); return true; }
    setLoaded((n) => n + 1); // read again, which saves this browser's copy
    return true;
  }

  return { ws, turn, state };
}

const clock = (d: Date) => d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });

/** The one line that says whether the last change reached the account. */
export function saveLine(s: SaveState): { text: string; warn: boolean } | null {
  if (s.kind === "saving") return { text: "Saving to your account.", warn: false };
  if (s.kind === "saved") return { text: `Last saved at ${clock(s.at)}.`, warn: false };
  if (s.kind === "failed") {
    return s.what === "load"
      ? { text: "Couldn't reach your account, so this browser's copy is showing. Trying again shortly.", warn: true }
      : { text: "Couldn't save your last change to your account. It's kept in this browser, and we'll try again shortly.", warn: true };
  }
  return null;
}

export function SyncNote(p: { ws: Workspace | null; turn: (on: boolean) => Promise<boolean>; state: SaveState }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);
  const line = saveLine(p.state);
  if (!p.ws && line?.warn) {
    return (
      <section class="note weekly" aria-label="On any device">
        <h2 class="weekly-h">On any device</h2>
        <p class="warn-text" role="status">{line.text}</p>
      </section>
    );
  }
  if (!p.ws?.paid) return null;
  const run = async (on: boolean) => {
    setBusy(true); setError(false);
    const ok = await p.turn(on);
    setBusy(false); setError(!ok);
  };
  return (
    <section class="note weekly" aria-label="On any device">
      <h2 class="weekly-h">On any device</h2>
      {p.ws.on ? (
        <p>Your profile and shortlist are saved to your account, so they're the same wherever you sign in.</p>
      ) : (
        <p>Your profile and shortlist stay in this browser only. Save them to your account to have them wherever you sign in.</p>
      )}
      {p.ws.on && line ? <p class={line.warn ? "warn-text" : "quiet"} role="status">{line.text}</p> : null}
      <div class="weekly-actions">
        {p.ws.on
          ? <button type="button" class="btn" disabled={busy} onClick={() => void run(false)}>Stop saving and delete the account copy</button>
          : <button type="button" class="btn" disabled={busy} onClick={() => void run(true)}>Save to my account</button>}
      </div>
      {error ? <p class="warn-text" role="alert">Couldn't change that. Try again in a minute.</p> : null}
    </section>
  );
}
