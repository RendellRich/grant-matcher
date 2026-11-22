import { useRef, useState } from "preact/hooks";
import type { Example } from "./data";
import { download } from "./exports";
import {
  AGES, BLANK, DELIVERY, FOCUS_AREAS, ORG_TYPES, FUNDER_TYPES, HIDE, HIDE_PIPELINE, parseProfile, POPULATIONS, REGISTRATIONS, STATE_NAMES, STATES, SUPPORT_TYPES, TIMING,
  type ProfileForm, type Status501, type Timing,
} from "./profile";
import { BUDGET_BANDS, CATEGORY_NAMES } from "./score";

export interface FormProps {
  idp: string; // "side" or "phone"; keeps ids unique if both copies exist
  draft: ProfileForm;
  setDraft: (f: ProfileForm | ((current: ProfileForm) => ProfileForm)) => void;
  examples: Record<string, Example>;
  exampleKey: string; // the example the profile started from, or "" once a profile was loaded
  loadedLabel: string; // the menu's option for a loaded profile: from a file, or ETO's saved one
  onExample: (key: string) => void;
  onLoad: (f: ProfileForm) => void;
  onUpdate: () => void;
  pending: boolean;
  busy: string; // progress text while updating
  status: string; // "Updated: 30 strong matches." etc.
  applied: ProfileForm;
  /** Inside ETO's admin page: the profile is kept by ETO instead of in a downloaded file. */
  parent?: { onSave: () => void; saving: boolean; result: { ok: boolean; text: string } | null };
}

export function exampleForm(ex: Example): ProfileForm {
  return { ...BLANK, org_type: ex.org_type ?? "", mission: ex.mission, keywords: ex.keywords, categories: [...ex.categories], state: ex.state, cities: ex.cities };
}

const count = (n: number) => (n ? `${n} chosen` : "none chosen");

/** A group of checkboxes with a visible legend; `items` are [value, label]. */
function CheckGroup(p: { legend: string; hint?: string; idp: string; items: [string, string][]; chosen: string[]; onToggle: (v: string, on: boolean) => void }) {
  return (
    <fieldset class="field check-group" aria-describedby={p.hint ? `${p.idp}-hint` : undefined}>
      <legend class="label">{p.legend}</legend>
      {p.hint ? <p class="hint" id={`${p.idp}-hint`}>{p.hint}</p> : null}
      <div class="checks">
        {p.items.map(([v, label]) => (
          <label class="check" key={v}>
            <input type="checkbox" checked={p.chosen.includes(v)}
                   onChange={(e) => p.onToggle(v, (e.target as HTMLInputElement).checked)} />
            <span>{label}</span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}

export function ProfileFormView(p: FormProps) {
  const { draft, setDraft, idp } = p;
  const [guard, setGuard] = useState<string | null>(null);
  const [allFocus, setAllFocus] = useState(false);
  const [fileError, setFileError] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  // Every change builds on the latest form, so quick changes in a row (or a profile filled in by ETO) never undo each other.
  const set = <K extends keyof ProfileForm>(k: K, v: ProfileForm[K]) => setDraft((d) => ({ ...d, [k]: v }));
  type ListKey = { [K in keyof ProfileForm]: ProfileForm[K] extends string[] ? K : never }[keyof ProfileForm];
  const toggle = (k: ListKey) => (v: string, on: boolean) => setDraft((d) => ({
    ...d, [k]: on ? (d[k].includes(v) ? d[k] : [...d[k], v]) : d[k].filter((x) => x !== v),
  }));
  const id = (s: string) => `${idp}-${s}`;
  const ex = p.examples[p.exampleKey];
  const edited = () => {
    const base = ex ? exampleForm(ex) : BLANK;
    const typed = draft.mission.trim() || draft.keywords.trim() || draft.cities.trim();
    return Boolean(typed) && (draft.mission !== base.mission || draft.keywords !== base.keywords || draft.cities !== base.cities);
  };

  const orgType = ORG_TYPES.find((t) => t.id === draft.org_type);
  // With a type chosen, its focus areas come first in its own order; anything already checked stays visible.
  const focusItems = !orgType || allFocus ? FOCUS_AREAS
    : [...orgType.focus.map((f) => FOCUS_AREAS.find((t) => t.id === f)!).filter(Boolean),
       ...FOCUS_AREAS.filter((t) => !orgType.focus.includes(t.id) && draft.focus_areas.includes(t.id))];

  // Picking a type fills in its federal funding areas only when none are chosen, so nothing typed is undone.
  function pickType(v: string) {
    const t = ORG_TYPES.find((o) => o.id === v);
    setDraft((d) => ({ ...d, org_type: v, categories: d.categories.length || !t ? d.categories : [...t.categories] }));
    setAllFocus(false);
  }

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
      {ex && draft.mission === ex.mission ? (
        <div class="sample-note" role="note">
          <p><strong>This is a sample, not your saved profile.</strong> It describes a made-up organization so you can see how
            matching works. Replace it with your own work, or clear it and start blank.</p>
          <button type="button" class="link-btn" onClick={() => p.onExample("blank")}>Clear the sample</button>
        </div>
      ) : null}

      <div class="field">
        <label for={id("ex")}>Start from an example</label>
        <select id={id("ex")} value={p.exampleKey} onChange={(e) => pickExample((e.target as HTMLSelectElement).value)}>
          {Object.entries(p.examples).map(([k, v]) => <option value={k} key={k}>{v.label}</option>)}
          <option value="blank">Start blank</option>
          {p.exampleKey === "" ? <option value="">{p.loadedLabel}</option> : null}
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
          <label for={id("orgtype")}>Type of organization</label>
          <p class="hint" id={id("orgtype-hint")}>Shows the focus areas and federal funding areas that fit your work.</p>
          <select id={id("orgtype")} aria-describedby={id("orgtype-hint")} value={draft.org_type} onChange={(e) => pickType((e.target as HTMLSelectElement).value)}>
            <option value="">Choose one</option>
            {ORG_TYPES.map((t) => <option value={t.id} key={t.id}>{t.label}</option>)}
          </select>
        </div>
        <div class="field">
          <label for={id("mission")}>Mission and programs</label>
          <p class="hint" id={id("mission-hint")}>Two or three sentences: who you serve, where, and what you do for them. This counts most.</p>
          <textarea id={id("mission")} rows={6} aria-describedby={id("mission-hint")} value={draft.mission}
                    onInput={(e) => set("mission", (e.target as HTMLTextAreaElement).value)} />
        </div>
        <CheckGroup legend="Focus areas" hint={orgType && !allFocus ? "The ones that fit your type of organization. Each adds its own key words." : "Each one adds its own key words, so you don't have to type them."}
                    idp={id("focus")} items={focusItems.map((t) => [t.id, t.label])} chosen={draft.focus_areas} onToggle={toggle("focus_areas")} />
        {orgType ? (
          <button type="button" class="link-btn focus-more" aria-expanded={allFocus} onClick={() => setAllFocus(!allFocus)}>
            {allFocus ? "Show only the focus areas for my type" : `Show all focus areas (${FOCUS_AREAS.length - focusItems.length} more)`}
          </button>
        ) : null}
        <div class="field">
          <label for={id("kw")}>More key words <span class="quiet">(optional)</span></label>
          <p class="hint" id={id("kw-hint")}>Separate with commas. Rare, specific words count more than common ones.</p>
          <textarea id={id("kw")} rows={3} aria-describedby={id("kw-hint")} value={draft.keywords}
                    placeholder="For example: tutoring, summer camp"
                    onInput={(e) => set("keywords", (e.target as HTMLTextAreaElement).value)} />
        </div>
        <details class="cats">
          <summary>Federal funding areas <span class="quiet">({draft.categories.length ? `${draft.categories.length} chosen` : "any"})</span></summary>
          <p class="hint">Federal grants in these areas score higher.</p>
          <div class="checks">
            {Object.entries(CATEGORY_NAMES).filter(([c]) => c !== "O").map(([c, name]) => (
              <label class="check" key={c}>
                <input type="checkbox" checked={draft.categories.includes(c)}
                       onChange={(e) => toggle("categories")(c, (e.target as HTMLInputElement).checked)} />
                <span>{name}</span>
              </label>
            ))}
          </div>
        </details>
      </fieldset>

      <details class="group-more">
        <summary>Who you serve <span class="quiet">({count(draft.ages.length + draft.populations.length)})</span></summary>
        <div class="group-body">
          <CheckGroup legend="Ages and grades" idp={id("ages")} items={AGES.map((t) => [t.id, t.label])}
                      chosen={draft.ages} onToggle={toggle("ages")} />
          <CheckGroup legend="Populations" hint="Funders word these many ways, so they raise a match and never rule one out." idp={id("pops")}
                      items={POPULATIONS.map((t) => [t.id, t.label])} chosen={draft.populations} onToggle={toggle("populations")} />
        </div>
      </details>

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
          <p class="hint" id={id("cities-hint")}>Separate with commas. A county includes its cities and towns. Finds foundations that already fund groups near you.</p>
          <input id={id("cities")} type="text" aria-describedby={id("cities-hint")} value={draft.cities} placeholder="For example: Manatee, Sarasota"
                 onInput={(e) => set("cities", (e.target as HTMLInputElement).value)} />
        </div>
        <fieldset class="field radios">
          <legend class="label">How you deliver services</legend>
          <p class="hint">Online nationwide also counts funders that give in many states.</p>
          <div class="stack">
            {DELIVERY.map(([v, label]) => (
              <label class="check" key={v}><input type="radio" name={id("delivery")} value={v} checked={draft.delivery === v}
                                                  onChange={() => set("delivery", v)} /><span>{label}</span></label>
            ))}
          </div>
        </fieldset>
      </fieldset>

      <fieldset class="group">
        <legend>Your organization</legend>
        <fieldset class="field radios">
          <legend class="label">501(c)(3) status</legend>
          <div class="seg">
            {(["Yes", "Pending", "No"] as Status501[]).map((v) => (
              <label key={v}><input type="radio" name={id("501")} value={v} checked={draft.has_501c3 === v}
                                    onChange={() => set("has_501c3", v)} /><span>{v}</span></label>
            ))}
          </div>
        </fieldset>
        {draft.has_501c3 !== "Yes" ? (
          <label class="check">
            <input type="checkbox" checked={draft.fiscal_sponsor} onChange={(e) => set("fiscal_sponsor", (e.target as HTMLInputElement).checked)} />
            <span>We can apply through a fiscal sponsor</span>
          </label>
        ) : null}
        <div class="field">
          <label for={id("budget")}>Annual budget</label>
          <select id={id("budget")} value={draft.budget_band} onChange={(e) => set("budget_band", (e.target as HTMLSelectElement).value)}>
            {Object.keys(BUDGET_BANDS).map((b) => <option value={b} key={b}>{b}</option>)}
          </select>
        </div>
        <div class="field">
          <label for={id("founded")}>Year founded <span class="quiet">(optional)</span></label>
          <input id={id("founded")} type="text" inputMode="numeric" maxLength={4} pattern="[0-9]{4}" value={draft.year_founded} placeholder="For example: 2026"
                 onInput={(e) => set("year_founded", (e.target as HTMLInputElement).value.replace(/\D/g, "").slice(0, 4))} />
        </div>
        <label class="check">
          <input type="checkbox" checked={draft.can_cost_share} onChange={(e) => set("can_cost_share", (e.target as HTMLInputElement).checked)} />
          <span>We can provide matching funds</span>
        </label>
        <CheckGroup legend="We already have" idp={id("reg")} items={REGISTRATIONS} chosen={draft.registrations}
                    onToggle={toggle("registrations")} />
      </fieldset>

      <details class="group-more">
        <summary>What you're asking for <span class="quiet">({count(draft.support_types.length + (draft.ask_min || draft.ask_max ? 1 : 0))})</span></summary>
        <div class="group-body">
          <CheckGroup legend="Type of support" hint="Keeps results whose words describe one of these. Results that don't say stay in." idp={id("support")}
                      items={SUPPORT_TYPES.map((t) => [t.id, t.label])} chosen={draft.support_types} onToggle={toggle("support_types")} />
          <fieldset class="field">
            <legend class="label">Amount you want to ask for</legend>
            <p class="hint">Keeps federal awards whose range overlaps it and foundations whose typical grant falls in it.</p>
            <div class="range-pair">
              <label for={id("ask-min")}>From</label>
              <input id={id("ask-min")} type="text" inputMode="numeric" value={draft.ask_min} placeholder="$1,000"
                     onInput={(e) => set("ask_min", (e.target as HTMLInputElement).value.replace(/\D/g, ""))} />
              <label for={id("ask-max")}>to</label>
              <input id={id("ask-max")} type="text" inputMode="numeric" value={draft.ask_max} placeholder="$25,000"
                     onInput={(e) => set("ask_max", (e.target as HTMLInputElement).value.replace(/\D/g, ""))} />
            </div>
          </fieldset>
        </div>
      </details>

      <details class="group-more">
        <summary>Funders and timing <span class="quiet">({count(draft.hide.length + (draft.timing ? 1 : 0) + (draft.funder_types.length < FUNDER_TYPES.length ? 1 : 0) + (draft.exclude_words.trim() ? 1 : 0))})</span></summary>
        <div class="group-body">
          <CheckGroup legend="Funder types" idp={id("ftypes")} items={FUNDER_TYPES} chosen={draft.funder_types}
                      onToggle={toggle("funder_types")} />
          <div class="field">
            <label for={id("timing")}>When</label>
            <select id={id("timing")} value={draft.timing} onChange={(e) => set("timing", (e.target as HTMLSelectElement).value as Timing)}>
              {TIMING.map(([v, label]) => <option value={v} key={v}>{label}</option>)}
            </select>
          </div>
          {draft.timing ? (
            <label class="check">
              <input type="checkbox" checked={draft.include_rolling} onChange={(e) => set("include_rolling", (e.target as HTMLInputElement).checked)} />
              <span>Also show funders with no deadline listed</span>
            </label>
          ) : null}
          <CheckGroup legend="Hide" idp={id("hide")} items={p.parent ? [...HIDE_PIPELINE, ...HIDE] : HIDE} chosen={draft.hide} onToggle={toggle("hide")} />
          <div class="field">
            <label for={id("exclude")}>Hide results that mention <span class="quiet">(optional)</span></label>
            <input id={id("exclude")} type="text" value={draft.exclude_words} placeholder="For example: capital campaign, religious instruction"
                   onInput={(e) => set("exclude_words", (e.target as HTMLInputElement).value)} />
          </div>
        </div>
      </details>

      <div class="apply">
        <button type="submit" class="btn primary" aria-describedby={id("status")}>Update matches</button>
        <p class="form-status" id={id("status")} role="status">
          {p.busy ? p.busy : p.pending ? <span class="quiet">You have changes. Press Update matches to see them.</span> : p.status}
        </p>
      </div>

      {p.parent ? (
        <fieldset class="group keep">
          <legend>Keep this profile</legend>
          <p class="hint">Saves the profile above to Exceed the Odds, so it loads here next time for every admin.</p>
          <div class="keep-actions">
            <button type="button" class="btn" disabled={p.parent.saving} onClick={p.parent.onSave}>
              {p.parent.saving ? "Saving" : "Save profile to ETO"}
            </button>
          </div>
          {p.parent.result ? (
            <p class={p.parent.result.ok ? "form-status" : "error"} role={p.parent.result.ok ? "status" : "alert"}>{p.parent.result.text}</p>
          ) : null}
        </fieldset>
      ) : <fieldset class="group keep">
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
      </fieldset>}
    </form>
  );
}
