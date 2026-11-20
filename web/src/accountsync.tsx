// Keeps the profile and shortlist the same on every device a paid account signs in on (sync.ts has the rules),
// and on Consultant switches between client profiles, each with its own shortlist.
import { useEffect, useRef, useState } from "preact/hooks";
import { addClient, deleteClient, myWorkspace, renameClient, saveProfileRemote, saveShortlistRemote, setSync } from "./access";
import { parseProfile, type ProfileForm } from "./profile";
import type { Item } from "./shortlist";
import { mergeShortlists, onLoad, parseWorkspace, readClient, readSync, writeClient, writeSync, type Workspace } from "./sync";

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
  /** Puts another client's profile on screen (null: that client has none yet). */
  showProfile: (f: ProfileForm | null, vector: number[] | null) => void;
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
  const client = useRef<string | null>(null); // the profile (client) on screen
  const switching = useRef(false);
  const account = p.email ?? "";
  const mark = (version: number, dirty: boolean) => writeSync({ account, version, dirty, ...(client.current ? { profile: client.current } : {}) });

  async function push(list: Item[], base: number, tries = 0): Promise<boolean> {
    if (!tries) setState({ kind: "saving" });
    const id = client.current;
    const r = await saveShortlistRemote(list, base, id);
    if (id !== client.current) return false; // switched clients meanwhile; that list was saved to its own client
    if (r.ok) {
      if (json(items.current) === json(list)) lastItems.current = json(list);
      mark(r.version, json(items.current) !== json(list));
      setState({ kind: "saved", at: new Date() });
      return true;
    }
    if (r.off) { setState({ kind: "idle" }); setWs((w) => (w ? { ...w, on: false } : w)); return false; }
    if (r.failed || r.version === undefined || tries >= 2) {
      // Still marked changed here, so it goes up with the next change, the retry below or the next visit.
      lastItems.current = null;
      setState({ kind: "failed", what: "save" });
      return false;
    }
    // Another device saved first: merge both and save over its version.
    const theirs = parseWorkspace({ shortlist: r.shortlist }).shortlist ?? [];
    const merged = mergeShortlists(items.current, theirs);
    mark(r.version, true);
    lastItems.current = json(merged); // already being saved here
    if (json(merged) !== json(items.current)) { items.current = merged; p.replace(merged); }
    return push(merged, r.version, tries + 1);
  }

  // Read the account's copy when a paid account signs in (and when saving is turned back on).
  useEffect(() => {
    ready.current = false;
    if (!p.enabled || !p.email) { setWs(null); return; }
    let live = true;
    void myWorkspace(readClient(account)).then((raw) => {
      if (!live) return;
      if (raw === null) { setState({ kind: "failed", what: "load" }); return; }
      setState({ kind: "idle" });
      const w = parseWorkspace(raw);
      setWs(w);
      if (!w.paid || !w.on) return;
      client.current = w.id;
      if (w.clients.length > 1) writeClient(account, w.id);
      const plan = onLoad(items.current, readSync(), account, w);
      if (json(plan.items) !== json(items.current)) p.replace(plan.items);
      items.current = plan.items;
      lastItems.current = json(plan.items);
      if (plan.push) void push(plan.items, w.version);
      else mark(w.version, false);
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
        void saveProfileRemote(p.applied, p.vector, client.current).then((ok) => { if (ok) lastProfile.current = f; else setState({ kind: "failed", what: "save" }); });
      }
      ready.current = true;
    });
    return () => { live = false; };
  }, [p.enabled, p.email, loaded]);

  // Save the shortlist a moment after it changes.
  const itemsJson = json(p.items);
  useEffect(() => {
    if (!ready.current || switching.current || !ws?.on || itemsJson === lastItems.current) return;
    const s = readSync();
    const base = s && s.account === account ? s.version : ws.version;
    mark(base, true);
    const t = setTimeout(() => { void push(items.current, readSync()?.version ?? base); }, 1200);
    return () => clearTimeout(t);
  }, [itemsJson, ws?.on, retry]);

  // Save the profile a moment after the person searches with a new one.
  const profileJson = json(p.applied);
  useEffect(() => {
    if (!ready.current || switching.current || !ws?.on || !p.ownProfile || profileJson === lastProfile.current) return;
    const t = setTimeout(() => {
      setState({ kind: "saving" });
      void saveProfileRemote(p.applied, p.vector, client.current).then((ok) => {
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
    if (!on) { writeSync(null); writeClient(account, null); client.current = null; lastItems.current = null; lastProfile.current = null; setWs(parseWorkspace(raw)); return true; }
    setLoaded((n) => n + 1); // read again, which saves this browser's copy
    return true;
  }

  /** Saves anything not yet saved for the client on screen. */
  async function flush(): Promise<boolean> {
    if (!ws?.on) return true;
    if (json(items.current) !== lastItems.current) {
      const s = readSync();
      if (!(await push(items.current, s && s.account === account ? s.version : ws.version))) return false;
    }
    if (p.ownProfile && json(p.applied) !== lastProfile.current) {
      if (!(await saveProfileRemote(p.applied, p.vector, client.current))) return false;
      lastProfile.current = json(p.applied);
    }
    return true;
  }

  /** Opens another client: saves this one first, then loads that one's profile and shortlist. */
  async function switchTo(id: string): Promise<string | null> {
    if (switching.current) return null;
    switching.current = true;
    try {
      if (!(await flush())) return "Couldn't save this client's last change, so it's still open. Try again in a minute.";
      const raw = await myWorkspace(id);
      if (raw === null) return "Couldn't open that client. Try again in a minute.";
      const w = parseWorkspace(raw);
      client.current = w.id;
      writeClient(account, w.id);
      const saved = w.shortlist ?? [];
      lastItems.current = json(saved);
      items.current = saved;
      p.replace(saved);
      mark(w.version, false);
      let f: ProfileForm | null = null;
      try { f = w.profile ? parseProfile(json(w.profile)) : null; } catch { f = null; }
      lastProfile.current = f ? json(f) : null;
      p.showProfile(f, w.vector);
      setWs(w);
      setState({ kind: "idle" });
      return null;
    } finally {
      switching.current = false;
    }
  }

  async function add(label: string): Promise<string | null> {
    const r = await addClient(label);
    if (r.error || !r.id) return r.error ?? "Couldn't add that client. Try again in a minute.";
    return switchTo(r.id);
  }

  async function rename(id: string, label: string): Promise<string | null> {
    const err = await renameClient(id, label);
    if (!err) setWs((w) => (w ? { ...w, clients: w.clients.map((c) => (c.id === id ? { ...c, label: label.trim() } : c)) } : w));
    return err;
  }

  async function remove(id: string): Promise<string | null> {
    if (!ws) return null;
    if (id === client.current) {
      const other = ws.clients.find((c) => c.id !== id);
      if (!other) return "Keep at least one client.";
      const err = await switchTo(other.id);
      if (err) return err;
    }
    const err = await deleteClient(id);
    if (!err) setWs((w) => (w ? { ...w, clients: w.clients.filter((c) => c.id !== id) } : w));
    return err;
  }

  return { ws, turn, state, switchTo, add, rename, remove };
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
  const [confirm, setConfirm] = useState(false);
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
    setBusy(true); setError(false); setConfirm(false);
    const ok = await p.turn(on);
    setBusy(false); setError(!ok);
  };
  const many = p.ws.clients.length > 1;
  return (
    <section class="note weekly" aria-label="On any device">
      <h2 class="weekly-h">On any device</h2>
      {p.ws.on ? (
        <p>{many ? "Each client's profile and shortlist are" : "Your profile and shortlist are"} saved to your account, so they're the same wherever you sign in.</p>
      ) : (
        <p>Your profile and shortlist stay in this browser only. Save them to your account to have them wherever you sign in.</p>
      )}
      {p.ws.on && line ? <p class={line.warn ? "warn-text" : "quiet"} role="status">{line.text}</p> : null}
      <div class="weekly-actions">
        {!p.ws.on
          ? <button type="button" class="btn" disabled={busy} onClick={() => void run(true)}>Save to my account</button>
          : !many
            ? <button type="button" class="btn" disabled={busy} onClick={() => void run(false)}>Stop saving and delete the account copy</button>
            : !confirm
              ? <button type="button" class="btn" disabled={busy} onClick={() => setConfirm(true)}>Stop saving and delete the account copy</button>
              : null}
      </div>
      {confirm ? (
        <div class="guard" role="alert">
          <p>This deletes all {p.ws.clients.length} clients' saved profiles and shortlists from your account. This browser keeps only the client open now.</p>
          <div class="guard-actions">
            <button type="button" class="btn" onClick={() => setConfirm(false)}>Keep them</button>
            <button type="button" class="btn" disabled={busy} onClick={() => void run(false)}>Delete them</button>
          </div>
        </div>
      ) : null}
      {error ? <p class="warn-text" role="alert">Couldn't change that. Try again in a minute.</p> : null}
    </section>
  );
}
