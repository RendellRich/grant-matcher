// The email box for paid accounts: the weekly email of new strong matches for this profile, and deadline
// reminders for the shortlist. Each is saved to the account only while it's on, and deleted when it's turned
// off (supabase/migrations/20261119220000_weekly_email.sql, 20261120000000_deadline_reminders.sql).
import { useEffect, useRef, useState } from "preact/hooks";
import { emailOff, myDigest, saveClientDigest, saveDigest, saveReminders, setDigestMode, type DigestInfo, type EmailKind } from "./access";
import { isBlank } from "./rank";
import { parseProfile, type ProfileForm } from "./profile";
import { searchSignature } from "./server/preview";
import type { ReminderItem } from "./shortlist";

function savedMatches(saved: unknown, form: ProfileForm): boolean {
  try { return searchSignature(parseProfile(JSON.stringify(saved))) === searchSignature(form); } catch { return false; }
}

const plural = (n: number, one: string) => `${n} ${one}${n === 1 ? "" : "s"}`;

export interface ClientEmailProps {
  /** The Consultant client that's open. */
  client: { id: string; label: string };
  /** Every client's open reminders, read from the account, for turning reminders on across all of them. */
  allReminders: () => Promise<{ id: string; items: ReminderItem[] }[]>;
}

export function WeeklyEmail(p: { email: string; form: ProfileForm; vector: number[] | null; reminders: ReminderItem[]; clients?: ClientEmailProps | null }) {
  const [info, setInfo] = useState<DigestInfo | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const synced = useRef<string | null>(null);
  const clientId = p.clients?.client.id ?? null;
  useEffect(() => { let live = true; void myDigest().then((d) => { if (live) setInfo(d); }); return () => { live = false; }; }, [p.email, clientId]);

  // While reminders are on, the server's copy follows the shortlist: a second after it changes, send it again.
  // On Consultant that is the open client's set; the other clients' sets stay as they are.
  const remindersJson = JSON.stringify([clientId, p.reminders]);
  useEffect(() => {
    if (!info?.reminders) { synced.current = null; return; }
    if (synced.current === remindersJson) return;
    const t = setTimeout(() => {
      void saveReminders(true, p.reminders, clientId).then((r) => { if (r.info) { synced.current = remindersJson; setInfo(r.info); } });
    }, 1000);
    return () => clearTimeout(t);
  }, [info?.reminders, remindersJson]);

  if (!info) return null;
  if (p.clients && info.plan === "consultant") return <ClientEmails {...p} clients={p.clients} info={info} setInfo={setInfo} synced={synced} remindersJson={remindersJson} />;
  async function run(job: () => Promise<{ info?: DigestInfo; error?: string }>, after?: () => void) {
    setBusy(true); setError(null);
    const r = await job();
    setBusy(false);
    if (r.error) setError(r.error); else if (r.info) { after?.(); setInfo(r.info); }
  }
  const blank = isBlank(p.form);
  const same = info.on && savedMatches(info.profile, p.form);
  const count = info.reminder_count ?? 0;
  return (
    <section class="note weekly" aria-label="Email">
      <h2 class="weekly-h">Weekly email</h2>
      {info.on ? (
        <p>On. Each week we email {p.email} the new strong matches for {same ? "this profile" : "the profile you saved"}.</p>
      ) : (
        <p>Get new strong matches for this profile by email each week.</p>
      )}
      <div class="weekly-actions">
        {!info.on ? (
          <button type="button" class="btn" disabled={busy || blank} onClick={() => void run(() => saveDigest(p.form, p.vector, true))}>{blank ? "Search first" : "Email me weekly"}</button>
        ) : (
          <>
            {!same && !blank ? <button type="button" class="btn" disabled={busy} onClick={() => void run(() => saveDigest(p.form, p.vector, true))}>Use this profile instead</button> : null}
            <button type="button" class="btn" disabled={busy} onClick={() => void run(() => saveDigest(p.form, p.vector, false))}>Turn off</button>
          </>
        )}
      </div>

      <h2 class="weekly-h weekly-h2">Deadline reminders</h2>
      {info.reminders ? (
        <p>On. We email {p.email} 14 days and 3 days before {count ? `each of the ${plural(count, "deadline")} on your shortlist` : "each deadline you add to your shortlist"}. Mark a grant Submitted and its reminders stop.</p>
      ) : (
        <p>Get an email 14 days and 3 days before each deadline on your shortlist.</p>
      )}
      <div class="weekly-actions">
        {!info.reminders ? (
          <button type="button" class="btn" disabled={busy} onClick={() => void run(() => saveReminders(true, p.reminders), () => { synced.current = remindersJson; })}>Remind me of deadlines</button>
        ) : (
          <button type="button" class="btn" disabled={busy} onClick={() => void run(() => saveReminders(false, []))}>Turn off</button>
        )}
      </div>
      {error ? <p class="warn-text" role="alert">{error}</p> : null}
    </section>
  );
}

const OFF_TEXT: Record<EmailKind, { ask: string; what: string; done: string }> = {
  weekly: {
    ask: "Turn off the weekly email?",
    what: "You'll stop getting the weekly email of new matches, and the profile saved for it is deleted.",
    done: "The weekly email is off. You can turn it back on any time from Grant Matcher.",
  },
  reminders: {
    ask: "Turn off deadline reminders?",
    what: "You'll stop getting deadline reminders, and the shortlist dates saved for them are deleted.",
    done: "Deadline reminders are off. You can turn them back on any time from Grant Matcher.",
  },
};

/** Opened from an email's "Turn it off" link: one press turns that email off. */
export function EmailOff(p: { kind: EmailKind; token: string }) {
  const [state, setState] = useState<"ask" | "busy" | "done" | "failed">("ask");
  const t = OFF_TEXT[p.kind];
  if (state === "done") return <p class="note" role="status">{t.done}</p>;
  return (
    <section class="note weekly" aria-labelledby="email-off-h">
      <h2 id="email-off-h" class="weekly-h">{t.ask}</h2>
      <p>{t.what}</p>
      <div class="weekly-actions">
        <button type="button" class="btn" disabled={state === "busy"}
          onClick={async () => { setState("busy"); setState((await emailOff(p.kind, p.token)) ? "done" : "failed"); }}>Turn it off</button>
      </div>
      {state === "failed" ? <p class="warn-text" role="alert">That didn't work. Try again, or email ren@solutionsbyrich.com.</p> : null}
    </section>
  );
}

/** Consultant: the weekly email for each client (one email each, or one combined), and reminders for every client. */
function ClientEmails(p: {
  email: string; form: ProfileForm; reminders: ReminderItem[]; clients: ClientEmailProps; info: DigestInfo;
  setInfo: (d: DigestInfo) => void; synced: { current: string | null }; remindersJson: string;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const all = p.info.clients ?? [];
  const me = all.find((c) => c.id === p.clients.client.id);
  const onCount = all.filter((c) => c.on).length;
  const ready = Boolean(me?.ready) || !isBlank(p.form);
  const name = p.clients.client.label;
  const [mode, setMode] = useState<"each" | "combined" | null>(null); // the choice just made, until the account answers
  const shownMode = mode ?? p.info.mode ?? "each";
  async function run(job: () => Promise<{ info?: DigestInfo; error?: string }>, after?: () => void) {
    setBusy(true); setError(null);
    const r = await job();
    setBusy(false);
    if (r.error) setError(r.error); else if (r.info) { after?.(); p.setInfo(r.info); }
  }
  async function remindAll(): Promise<{ info?: DigestInfo; error?: string }> {
    const sets = await p.clients.allReminders();
    let last: { info?: DigestInfo; error?: string } = { error: "Couldn't save that. Try again in a minute." };
    for (const s of sets) {
      last = await saveReminders(true, s.items, s.id);
      if (last.error) return last;
    }
    return last;
  }
  return (
    <section class="note weekly" aria-label="Email">
      <h2 class="weekly-h">Weekly email</h2>
      {me?.on ? (
        <p>On for <strong>{name}</strong>. Each week we email {p.email} the new strong matches for this client's saved profile.</p>
      ) : (
        <p>Get new strong matches for <strong>{name}</strong> by email each week, from this client's saved profile.</p>
      )}
      <div class="weekly-actions">
        {me?.on
          ? <button type="button" class="btn" disabled={busy} onClick={() => void run(() => saveClientDigest(p.clients.client.id, false))}>Turn off for this client</button>
          : <button type="button" class="btn" disabled={busy || !ready} onClick={() => void run(() => saveClientDigest(p.clients.client.id, true))}>{ready ? "Email me weekly for this client" : "Search first"}</button>}
      </div>
      {all.length > 1 ? (
        <fieldset class="field email-mode">
          <legend class="label">{onCount === 1 ? "1 client gets" : `${onCount} clients get`} the weekly email</legend>
          {(["each", "combined"] as const).map((m) => (
            <label class="check" key={m}>
              <input type="radio" name="digest-mode" checked={shownMode === m} disabled={busy}
                     onChange={() => { setMode(m); void run(() => setDigestMode(m), () => setMode(null)).then(() => setMode(null)); }} />
              <span>{m === "each" ? "One email per client" : "One combined email, with a section for each client"}</span>
            </label>
          ))}
        </fieldset>
      ) : null}

      <h2 class="weekly-h weekly-h2">Deadline reminders</h2>
      {p.info.reminders ? (
        <p>On for every client. We email {p.email} 14 days and 3 days before each deadline on a client's shortlist, and say which client it's for. Mark a grant Submitted and its reminders stop.</p>
      ) : (
        <p>Get an email 14 days and 3 days before each deadline on any client's shortlist.</p>
      )}
      <div class="weekly-actions">
        {!p.info.reminders
          ? <button type="button" class="btn" disabled={busy} onClick={() => void run(remindAll, () => { p.synced.current = p.remindersJson; })}>Remind me of deadlines</button>
          : <button type="button" class="btn" disabled={busy} onClick={() => void run(() => saveReminders(false, []))}>Turn off</button>}
      </div>
      {error ? <p class="warn-text" role="alert">{error}</p> : null}
    </section>
  );
}
