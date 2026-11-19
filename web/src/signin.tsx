// Sign in or make an account with a code sent by email. No passwords: the same two steps for both.
import { useEffect, useRef, useState } from "preact/hooks";
import { sendCode, verifyCode } from "./access";

export function SignIn({ open, onClose }: { open: boolean; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const codeRef = useRef<HTMLInputElement>(null);
  const [step, setStep] = useState<"email" | "code">("email");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

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
          <p class="quiet">We'll email you a sign-in code. There's no password. A new email address gets a free account with 3 full searches a month.</p>
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
