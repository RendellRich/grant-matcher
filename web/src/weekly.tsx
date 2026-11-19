// The weekly email switch for paid accounts: email me new strong matches for this profile every week.
// The profile and its mission vector are saved to the account only when the email is turned on, and deleted
// when it's turned off (supabase/migrations/20261119220000_weekly_email.sql).
import { useEffect, useState } from "preact/hooks";
import { myDigest, saveDigest, weeklyOff, type DigestInfo } from "./access";
import { isBlank } from "./rank";
import { parseProfile, type ProfileForm } from "./profile";
import { searchSignature } from "./server/preview";

function savedMatches(saved: unknown, form: ProfileForm): boolean {
  try { return searchSignature(parseProfile(JSON.stringify(saved))) === searchSignature(form); } catch { return false; }
}

export function WeeklyEmail(p: { email: string; form: ProfileForm; vector: number[] | null }) {
  const [info, setInfo] = useState<DigestInfo | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { let live = true; void myDigest().then((d) => { if (live) setInfo(d); }); return () => { live = false; }; }, [p.email]);
  if (!info) return null;
  async function set(on: boolean) {
    setBusy(true); setError(null);
    const r = await saveDigest(p.form, p.vector, on);
    setBusy(false);
    if (r.error) setError(r.error); else if (r.info) setInfo(r.info);
  }
  const blank = isBlank(p.form);
  const same = info.on && savedMatches(info.profile, p.form);
  return (
    <section class="note weekly" aria-labelledby="weekly-h">
      <h2 id="weekly-h" class="weekly-h">Weekly email</h2>
      {info.on ? (
        <p>On. Each week we email {p.email} the new strong matches for {same ? "this profile" : "the profile you saved"}.</p>
      ) : (
        <p>Get new strong matches for this profile by email each week. Your profile is saved to your account only while this is on.</p>
      )}
      <div class="weekly-actions">
        {!info.on ? (
          <button type="button" class="btn" disabled={busy || blank} onClick={() => void set(true)}>{blank ? "Search first" : "Email me weekly"}</button>
        ) : (
          <>
            {!same && !blank ? <button type="button" class="btn" disabled={busy} onClick={() => void set(true)}>Use this profile instead</button> : null}
            <button type="button" class="btn" disabled={busy} onClick={() => void set(false)}>Turn off</button>
          </>
        )}
      </div>
      {error ? <p class="warn-text" role="alert">{error}</p> : null}
    </section>
  );
}

/** Opened from a weekly email's "Turn it off" link: one press turns the email off. */
export function WeeklyOff(p: { token: string }) {
  const [state, setState] = useState<"ask" | "busy" | "done" | "failed">("ask");
  if (state === "done") return <p class="note" role="status">The weekly email is off. You can turn it back on any time from Grant Matcher.</p>;
  return (
    <section class="note weekly" aria-labelledby="weekly-off-h">
      <h2 id="weekly-off-h" class="weekly-h">Turn off the weekly email?</h2>
      <p>You'll stop getting the weekly email of new matches, and the profile saved for it is deleted.</p>
      <div class="weekly-actions">
        <button type="button" class="btn" disabled={state === "busy"}
          onClick={async () => { setState("busy"); setState((await weeklyOff(p.token)) ? "done" : "failed"); }}>Turn it off</button>
      </div>
      {state === "failed" ? <p class="warn-text" role="alert">That didn't work. Try again, or email ren@solutionsbyrich.com.</p> : null}
    </section>
  );
}
