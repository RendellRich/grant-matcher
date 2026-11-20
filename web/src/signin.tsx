// Sign in or make an account with a code sent by email, or with Google. No passwords: the same steps for both.
import { useEffect, useRef, useState } from "preact/hooks";
import { googleEnabled, sendCode, signInWithGoogle, verifyCode } from "./access";

export function SignIn({ open, onClose }: { open: boolean; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const codeRef = useRef<HTMLInputElement>(null);
  const [step, setStep] = useState<"email" | "code">("email");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [google, setGoogle] = useState(false); // shown once the Google sign-in is switched on in Supabase
  useEffect(() => { if (open) void googleEnabled().then(setGoogle); }, [open]);

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) { setError(""); d.showModal?.(); }
    if (!open && d.open) d.close();
  }, [open]);
  useEffect(() => { if (step === "code") codeRef.current?.focus(); }, [step]);

  async function submitEmail(ev: Event) {
    ev.preventDefault();
    const e = email.trim();
    if (!/^\S+@\S+\.\S+$/.test(e)) { setError("Enter the email address you want to sign in with."); return; }
    setBusy(true); setError("");
    const problem = await sendCode(e);
    setBusy(false);
    if (problem) setError(problem);
    else { setStep("code"); setCode(""); }
  }

  async function submitCode(ev: Event) {
    ev.preventDefault();
    if (!/^\d{6,10}$/.test(code.replace(/\s+/g, ""))) { setError("Enter the code from the email, numbers only."); return; }
    setBusy(true); setError("");
    const problem = await verifyCode(email.trim(), code);
    setBusy(false);
    if (problem) { setError(problem); return; }
    setStep("email"); setCode("");
    onClose();
  }

  return (
    <dialog ref={ref} class="signin" aria-labelledby="signin-title" onClose={onClose} onCancel={onClose}>
      <div class="signin-head">
        <h2 id="signin-title">{step === "email" ? "Sign in or make a free account" : "Check your email"}</h2>
        <button type="button" class="link-btn" onClick={onClose}>Close</button>
      </div>
      {step === "email" ? (
        <form onSubmit={submitEmail} noValidate>
          {google ? (
            <>
              <button type="button" class="btn google-btn" disabled={busy}
                      onClick={async () => { setBusy(true); setError(""); const p = await signInWithGoogle(); if (p) { setBusy(false); setError(p); } }}>
                <svg width="18" height="18" viewBox="0 0 48 48" aria-hidden="true">
                  <path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3C33.7 32.7 29.2 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.3-.1-2.4-.4-3.5z"/>
                  <path fill="#FF3D00" d="M6.3 14.7l6.6 4.8C14.7 15.1 19 12 24 12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 16.3 4 9.7 8.3 6.3 14.7z"/>
                  <path fill="#4CAF50" d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.1 26.7 36 24 36c-5.2 0-9.6-3.3-11.3-7.9l-6.5 5C9.5 39.6 16.2 44 24 44z"/>
                  <path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.2 4.2-4.1 5.6l6.2 5.2C37 39.2 44 34 44 24c0-1.3-.1-2.4-.4-3.5z"/>
                </svg>
                Continue with Google
              </button>
              <p class="signin-or"><span>or</span></p>
            </>
          ) : null}
          <p class="quiet">We'll email you a sign-in code. There's no password. A new email address gets a free account, which shows the top 10 matches in each list.</p>
          <div class="field">
            <label for="signin-email">Email</label>
            <input id="signin-email" type="email" autoComplete="email" inputMode="email" value={email}
                   onInput={(e) => setEmail((e.target as HTMLInputElement).value)} aria-invalid={Boolean(error)} aria-describedby={error ? "signin-error" : undefined} />
          </div>
          {error ? <p id="signin-error" class="error" role="alert">{error}</p> : null}
          <button type="submit" class="btn primary" disabled={busy}>{busy ? "Sending" : "Email me a code"}</button>
        </form>
      ) : (
        <form onSubmit={submitCode} noValidate>
          <p class="quiet">We sent a code to <strong>{email.trim()}</strong>. It can take a minute to arrive; check spam if it doesn't.</p>
          <div class="field">
            <label for="signin-code">Code</label>
            <input id="signin-code" ref={codeRef} type="text" inputMode="numeric" autoComplete="one-time-code" value={code}
                   onInput={(e) => setCode((e.target as HTMLInputElement).value)} aria-invalid={Boolean(error)} aria-describedby={error ? "signin-error" : undefined} />
          </div>
          {error ? <p id="signin-error" class="error" role="alert">{error}</p> : null}
          <button type="submit" class="btn primary" disabled={busy}>{busy ? "Checking" : "Sign in"}</button>
          <p class="signin-alt">
            <button type="button" class="link-btn" onClick={() => { setStep("email"); setError(""); }}>Use a different email</button>
          </p>
        </form>
      )}
    </dialog>
  );
}
