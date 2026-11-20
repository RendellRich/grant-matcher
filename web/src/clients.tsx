// Consultant: the client menu above the profile. Pick a client to open its profile and shortlist, add one
// (up to 10), rename or delete the one that's open. accountsync.tsx does the saving and loading.
import { useState } from "preact/hooks";
import type { Client } from "./sync";

export interface ClientBarProps {
  clients: Client[];
  current: string | null;
  onSwitch: (id: string) => Promise<string | null>;
  onAdd: (label: string) => Promise<string | null>;
  onRename: (id: string, label: string) => Promise<string | null>;
  onDelete: (id: string) => Promise<string | null>;
}

export const MAX_CLIENTS = 10;

export function ClientBar(p: ClientBarProps) {
  const [mode, setMode] = useState<"" | "add" | "rename" | "delete">("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const current = p.clients.find((c) => c.id === p.current) ?? p.clients[0];
  const run = async (job: () => Promise<string | null>) => {
    setBusy(true); setError(null);
    const err = await job();
    setBusy(false);
    if (err) setError(err); else { setMode(""); setName(""); }
  };
  const open = (m: "add" | "rename" | "delete") => { setMode(m); setError(null); setName(m === "rename" ? current?.label ?? "" : ""); };
  const full = p.clients.length >= MAX_CLIENTS;

  return (
    <section class="clients" aria-label="Clients">
      <div class="field">
        <label for="client-pick">Client</label>
        <select id="client-pick" value={current?.id ?? ""} disabled={busy}
                onChange={(e) => { const id = (e.target as HTMLSelectElement).value; void run(() => p.onSwitch(id)); }}>
          {p.clients.map((c) => <option value={c.id} key={c.id}>{c.label}</option>)}
        </select>
        <p class="hint">{p.clients.length} of {MAX_CLIENTS} clients. Each keeps its own profile and shortlist.</p>
      </div>
      {mode === "" ? (
        <div class="client-actions">
          <button type="button" class="link-btn" disabled={busy || full} onClick={() => open("add")}>{full ? "10 clients, the most" : "Add a client"}</button>
          <button type="button" class="link-btn" disabled={busy} onClick={() => open("rename")}>Rename</button>
          {p.clients.length > 1 ? <button type="button" class="link-btn" disabled={busy} onClick={() => open("delete")}>Delete</button> : null}
        </div>
      ) : mode === "delete" ? (
        <div class="guard" role="alert">
          <p>Delete <strong>{current?.label}</strong>, with its profile and shortlist? This can't be undone.</p>
          <div class="guard-actions">
            <button type="button" class="btn" onClick={() => setMode("")}>Keep it</button>
            <button type="button" class="btn" disabled={busy} onClick={() => current && void run(() => p.onDelete(current.id))}>Delete client</button>
          </div>
        </div>
      ) : (
        <form class="client-name" onSubmit={(e) => {
          e.preventDefault();
          if (!name.trim()) { setError("Name the client."); return; }
          void run(() => (mode === "add" ? p.onAdd(name) : current ? p.onRename(current.id, name) : Promise.resolve(null)));
        }}>
          <label for="client-name">{mode === "add" ? "New client's name" : "Client's name"}</label>
          <input id="client-name" type="text" maxLength={120} value={name} autoFocus
                 onInput={(e) => setName((e.target as HTMLInputElement).value)} />
          <div class="guard-actions">
            <button type="button" class="btn" onClick={() => { setMode(""); setError(null); }}>Cancel</button>
            <button type="submit" class="btn" disabled={busy}>{mode === "add" ? "Add client" : "Save name"}</button>
          </div>
        </form>
      )}
      {error ? <p class="warn-text" role="alert">{error}</p> : null}
    </section>
  );
}
