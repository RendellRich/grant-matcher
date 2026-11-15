import { useRef, useState } from "preact/hooks";
import type { Example } from "./data";
import { download } from "./exports";
import { BLANK, parseProfile, STATE_NAMES, STATES, type ProfileForm, type Status501 } from "./profile";
import { BUDGET_BANDS, CATEGORY_NAMES } from "./score";

export interface FormProps {
  idp: string; // "side" or "phone"; keeps ids unique if both copies exist
  draft: ProfileForm;
  setDraft: (f: ProfileForm) => void;
  examples: Record<string, Example>;
  exampleKey: string; // the example the profile started from, or "" once a file was loaded
  onExample: (key: string) => void;
  onLoad: (f: ProfileForm) => void;
  onUpdate: () => void;
  pending: boolean;
  busy: string; // progress text while updating
  status: string; // "Updated: 30 strong matches." etc.
  applied: ProfileForm;
}

export function exampleForm(ex: Example): ProfileForm {
  return { ...BLANK, mission: ex.mission, keywords: ex.keywords, categories: [...ex.categories], state: ex.state, cities: ex.cities };
}

export function ProfileFormView(p: FormProps) {
  const { draft, setDraft, idp } = p;
  const [guard, setGuard] = useState<string | null>(null);
  const [fileError, setFileError] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const set = <K extends keyof ProfileForm>(k: K, v: ProfileForm[K]) => setDraft({ ...draft, [k]: v });
  const id = (s: string) => `${idp}-${s}`;
  const ex = p.examples[p.exampleKey];
  const edited = () => {
    const base = ex ? exampleForm(ex) : BLANK;
    const typed = draft.mission.trim() || draft.keywords.trim() || draft.cities.trim();
    return Boolean(typed) && (draft.mission !== base.mission || draft.keywords !== base.keywords || draft.cities !== base.cities);
  };

  function pickExample(key: string) {
    if (key === p.exampleKey) return;
    if (edited()) setGuard(key);
    else p.onExample(key);
  }

  async function loadFile(ev: Event) {
    const input = ev.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;
    try {
      p.onLoad(parseProfile(await file.text()));
      setFileError("");
    } catch {
      setFileError("That file isn't a profile from Grant Matcher. Save one with Download this profile.");
    }
    input.value = "";
  }

  return (
    <form class="profile" onSubmit={(ev) => { ev.preventDefault(); p.onUpdate(); }} aria-labelledby={id("h")}>
      <h2 id={id("h")} class="form-title">Your organization</h2>

      <div class="field">
        <label for={id("ex")}>Start from an example</label>
        <select id={id("ex")} value={p.exampleKey} onChange={(e) => pickExample((e.target as HTMLSelectElement).value)}>
          {Object.entries(p.examples).map(([k, v]) => <option value={k} key={k}>{v.label}</option>)}
          <option value="blank">Start blank</option>
          {p.exampleKey === "" ? <option value="">Loaded from a file</option> : null}
        </select>
        <p class="hint" id={id("ex-hint")}>Pick the one closest to your work and edit it, or start blank.</p>
      </div>
      {guard !== null ? (
        <div class="guard" role="alert">
          <p>{guard === "blank" ? "Clear your mission, key words and cities to start blank?"
            : <>Replace your mission, key words and cities with the <i>{p.examples[guard]?.label}</i> example?</>}</p>
          <div class="guard-actions">
            <button type="button" class="btn" onClick={() => setGuard(null)}>Keep my text</button>
            <button type="button" class="btn" onClick={() => { p.onExample(guard); setGuard(null); }}>
              {guard === "blank" ? "Clear my text" : "Replace my text"}
            </button>
          </div>
        </div>
      ) : null}

      <fieldset class="group">
        <legend>About your work</legend>
        <div class="field">
          <label for={id("mission")}>Mission and programs</label>
          <p class="hint" id={id("mission-hint")}>Two or three sentences: who you serve, where, and what you do for them. This counts most.</p>
          <textarea id={id("mission")} rows={6} aria-describedby={id("mission-hint")} value={draft.mission}
                    onInput={(e) => set("mission", (e.target as HTMLTextAreaElement).value)} />
        </div>
        <div class="field">
          <label for={id("kw")}>Key words</label>
          <p class="hint" id={id("kw-hint")}>Separate with commas. Rare, specific words count more than common ones.</p>
          <textarea id={id("kw")} rows={3} aria-describedby={id("kw-hint")} value={draft.keywords}
                    placeholder="For example: dyslexia, tutoring, after school"
                    onInput={(e) => set("keywords", (e.target as HTMLTextAreaElement).value)} />
        </div>
        <details class="cats">
          <summary>Federal funding areas <span class="quiet">({draft.categories.length ? `${draft.categories.length} chosen` : "any"})</span></summary>
          <p class="hint">Federal grants in these areas score higher.</p>
          <div class="checks">
            {Object.entries(CATEGORY_NAMES).filter(([c]) => c !== "O").map(([c, name]) => (
              <label class="check" key={c}>
                <input type="checkbox" checked={draft.categories.includes(c)}
                       onChange={(e) => set("categories", (e.target as HTMLInputElement).checked
                         ? [...draft.categories, c] : draft.categories.filter((x) => x !== c))} />
                <span>{name}</span>
              </label>
            ))}
          </div>
        </details>
      </fieldset>

      <fieldset class="group">
        <legend>Where you work</legend>
        <div class="field">
          <label for={id("state")}>State you serve</label>
          <select id={id("state")} value={draft.state} onChange={(e) => set("state", (e.target as HTMLSelectElement).value)}>
            {STATES.map((s) => <option value={s} key={s}>{STATE_NAMES[s]}</option>)}
          </select>
        </div>
        <div class="field">
          <label for={id("cities")}>Cities or counties <span class="quiet">(optional)</span></label>
          <p class="hint" id={id("cities-hint")}>Separate with commas. Finds foundations that already fund groups near you.</p>
          <input id={id("cities")} type="text" aria-describedby={id("cities-hint")} value={draft.cities} placeholder="For example: Tampa, Hillsborough"
                 onInput={(e) => set("cities", (e.target as HTMLInputElement).value)} />
        </div>
      </fieldset>

      <fieldset class="group">
        <legend>Eligibility</legend>
        <fieldset class="field radios">
          <legend class="label">501(c)(3) status</legend>
          <div class="seg">
            {(["Yes", "Pending", "No"] as Status501[]).map((v) => (
              <label key={v}><input type="radio" name={id("501")} value={v} checked={draft.has_501c3 === v}
                                    onChange={() => set("has_501c3", v)} /><span>{v}</span></label>
            ))}
          </div>
        </fieldset>
        <div class="field">
          <label for={id("budget")}>Annual budget</label>
          <select id={id("budget")} value={draft.budget_band} onChange={(e) => set("budget_band", (e.target as HTMLSelectElement).value)}>
            {Object.keys(BUDGET_BANDS).map((b) => <option value={b} key={b}>{b}</option>)}
          </select>
        </div>
        <label class="check">
          <input type="checkbox" checked={draft.can_cost_share} onChange={(e) => set("can_cost_share", (e.target as HTMLInputElement).checked)} />
          <span>We can provide matching funds</span>
        </label>
      </fieldset>

      <div class="apply">
        <button type="submit" class="btn primary" aria-describedby={id("status")}>Update matches</button>
        <p class="form-status" id={id("status")} role="status">
          {p.busy ? p.busy : p.pending ? <span class="quiet">You have changes. Press Update matches to see them.</span> : p.status}
        </p>
      </div>

      <fieldset class="group keep">
        <legend>Keep this profile</legend>
        <p class="hint">Nothing is saved on a server. Download your profile, then load it here next time.</p>
        <div class="keep-actions">
          <button type="button" class="btn" onClick={() => download("grant-profile.json", JSON.stringify(p.applied, null, 2), "application/json")}>
            Download this profile
          </button>
          <button type="button" class="btn" onClick={() => fileRef.current?.click()}>Load a saved profile</button>
          <input ref={fileRef} type="file" accept=".json,application/json" class="sr-only" tabIndex={-1} aria-hidden="true" aria-label="Saved profile file" onChange={loadFile} />
        </div>
        {fileError ? <p class="error" role="alert">{fileError}</p> : null}
      </fieldset>
    </form>
  );
}
