import { useEffect, useMemo, useRef, useState } from "preact/hooks";
import {
  loadExamples, loadFederal, loadFlorida, loadFoundations, loadMeta,
  type Example, type Meta, type Source,
} from "./data";
import { embedMission } from "./embed";
import { federalEntry, floridaEntry, foundationEntry, isNarrowed, narrow, NO_NARROW, SIZE_BANDS, type Entry, type Narrow, type SourceKey } from "./entries";
import { download, toCsv, toIcs } from "./exports";
import { exampleForm, ProfileFormView } from "./form";
import { BLANK, sameForm, splitList, STATE_NAMES, type ProfileForm } from "./profile";
import {
  scoreFederal, scoreFlorida, scoreFoundations,
  type FederalRec, type FloridaRec, type FoundationRec, type Profile,
} from "./score";
import { EntryView, IconDownload, IconMark, ResultList } from "./ui";
import { markNew, newSince, type Fresh } from "./seen";
import { similarities } from "./vectors";

const NOTICE = "This product uses the Grants.gov API but is not endorsed or certified by the U.S. Department of Health and Human Services.";
const KINDS = ["Private foundation", "Community foundation", "Public foundation", "United Way or federated fund"];
const SHORT: Record<string, string> = { fl: "Florida", fdn: "Foundations", fed: "Federal", shortlist: "Shortlist" };
const NOUN: Record<SourceKey, [string, string, string]> = {
  fl: ["Florida programs", "Florida programs", "Florida program"],
  fdn: ["Foundations", "foundations", "foundation"],
  fed: ["Federal grants", "federal grants", "federal grant"],
};

type Loaded<T> = { state: "loading" } | { state: "ready"; data: T } | { state: "error" };

const n = (count: number, one: string, many: string) => `${count.toLocaleString("en-US")} ${count === 1 ? one : many}`;
const queryText = (f: ProfileForm) => f.mission + " " + f.keywords;

function useShortlist() {
  const [items, setItems] = useState<Entry[]>(() => {
    try { return JSON.parse(localStorage.getItem("gm-shortlist") ?? "[]"); } catch { return []; }
  });
  const keys = useMemo(() => new Set(items.map((e) => e.key)), [items]);
  const toggle = (e: Entry) => {
    const next = keys.has(e.key) ? items.filter((x) => x.key !== e.key) : [...items, e];
    setItems(next);
    try { localStorage.setItem("gm-shortlist", JSON.stringify(next)); } catch { /* private mode: keep it for this visit */ }
  };
  return { items, keys, toggle, clear: () => { setItems([]); try { localStorage.removeItem("gm-shortlist"); } catch { /* */ } } };
}

export function App() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [examples, setExamples] = useState<Record<string, Example> | null>(null);
  const [fed, setFed] = useState<Loaded<Source<FederalRec>>>({ state: "loading" });
  const [fl, setFl] = useState<Loaded<Source<FloridaRec>>>({ state: "loading" });
  const [fdn, setFdn] = useState<Record<string, Loaded<Source<FoundationRec>>>>({});

  const [exampleKey, setExampleKey] = useState("literacy");
  const [draft, setDraft] = useState<ProfileForm>(BLANK);
  const [applied, setApplied] = useState<ProfileForm>(BLANK);
  const [vector, setVector] = useState<number[] | null>(null);
  const [busy, setBusy] = useState("");
  const [status, setStatus] = useState("");
  const [modelFailed, setModelFailed] = useState(false);

  const [fdnKinds, setFdnKinds] = useState<string[]>(KINDS);
  const [fdnPre, setFdnPre] = useState(false);
  const [flEar, setFlEar] = useState(false);
  // Filters narrow what is shown; they never change a score. The search words apply on every tab.
  const [q, setQ] = useState("");
  const [nar, setNar] = useState<Record<SourceKey, Narrow>>({ fed: NO_NARROW, fdn: NO_NARROW, fl: NO_NARROW });
  const [tab, setTab] = useState<string>("");
  const [order, setOrder] = useState<SourceKey[]>([]);
  const [phoneOpen, setPhoneOpen] = useState(false);
  const shortlist = useShortlist();
  const panelRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    // The profile column scrolls on its own and keeps Update matches in view: its height is the part of the
    // window below its top edge.
    const fit = () => {
      const el = panelRef.current;
      if (!el) return;
      const top = Math.max(0, el.getBoundingClientRect().top);
      el.style.setProperty("--panel-h", `${window.innerHeight - top}px`);
    };
    fit();
    const ro = new ResizeObserver(fit); // the band grows when the answer line changes
    ro.observe(document.body);
    window.addEventListener("scroll", fit, { passive: true });
    window.addEventListener("resize", fit);
    return () => { ro.disconnect(); window.removeEventListener("scroll", fit); window.removeEventListener("resize", fit); };
  }, []);

  // ---------- data ----------
  useEffect(() => {
    loadMeta().then(setMeta).catch(() => setMeta({ states: [] }));
    loadExamples().then((ex) => {
      setExamples(ex);
      const first = ex.literacy ?? Object.values(ex)[0];
      const f = exampleForm(first);
      setDraft(f); setApplied(f); setVector(first.vector);
    }).catch(() => setExamples({}));
    loadFederal().then((d) => setFed({ state: "ready", data: d })).catch(() => setFed({ state: "error" }));
    loadFlorida().then((d) => setFl({ state: "ready", data: d })).catch(() => setFl({ state: "error" }));
  }, []);

  const st = applied.state;
  useEffect(() => {
    if (!meta || fdn[st]) return;
    if (!meta.states.includes(st)) return;
    setFdn((m) => ({ ...m, [st]: { state: "loading" } }));
    loadFoundations(st).then((d) => setFdn((m) => ({ ...m, [st]: { state: "ready", data: d } })))
      .catch(() => setFdn((m) => ({ ...m, [st]: { state: "error" } })));
  }, [meta, st]);

  // ---------- scoring ----------
  const profile: Profile = useMemo(() => {
    const now = new Date();
    return {
      mission: applied.mission, keywords: splitList(applied.keywords), has501c3: applied.has_501c3,
      budgetBand: applied.budget_band, canCostShare: applied.can_cost_share, categories: applied.categories,
      includeForecasted: applied.include_forecasted, minDaysLeft: applied.min_days_left,
      today: new Date(now.getFullYear(), now.getMonth(), now.getDate()),
    };
  }, [applied]);
  const hasKw = profile.keywords.length > 0;
  const blank = !applied.mission.trim() && !applied.keywords.trim();
  const sim = (vecs: Source<unknown>["vecs"]) => (vector && !blank ? similarities(vecs, vector) : null);

  const fedScored = useMemo(() => fed.state === "ready" && !blank
    ? scoreFederal(fed.data.records, profile, sim(fed.data.vecs)) : null, [fed, profile, vector]);
  const fdnSrc = fdn[st];
  // What's new since the last visit is about the data, not the profile, so it is worked out once per source.
  const fedFresh = useMemo(() => (fed.state === "ready" ? newSince("fed", fed.data.records.map((r) => r.id)) : null), [fed]);
  const fdnFresh = useMemo(() => (fdnSrc?.state === "ready" ? newSince(`fdn-${st}`, fdnSrc.data.records.map((r) => r.ein)) : null), [fdnSrc]);
  const flFresh = useMemo(() => (fl.state === "ready" ? newSince("fl", fl.data.records.map((r) => r.id)) : null), [fl]);
  const fresh: Record<SourceKey, Fresh | null> = { fed: fedFresh, fdn: fdnFresh, fl: flFresh };
  const fedEntries = useMemo(() => markNew(fedScored?.map((s) => federalEntry(s, hasKw)) ?? null, fedFresh), [fedScored, fedFresh]);
  const fdnEntries = useMemo(() => markNew(fdnSrc?.state === "ready" && !blank
    ? scoreFoundations(fdnSrc.data.records.filter((r) => fdnKinds.includes(r.kind || "Private foundation")), profile, st,
      applied.cities.split(",").filter((c) => c.trim()), sim(fdnSrc.data.vecs), fdnPre).map((s) => foundationEntry(s, st, hasKw))
    : null, fdnFresh), [fdnSrc, profile, vector, fdnKinds, fdnPre, fdnFresh]);
  const flEntries = useMemo(() => markNew(fl.state === "ready" && st === "FL" && !blank
    ? scoreFlorida(fl.data.records, profile, sim(fl.data.vecs), flEar).map((s) => floridaEntry(s, hasKw)) : null, flFresh),
  [fl, profile, vector, flEar, st, flFresh]);

  const lists: Partial<Record<SourceKey, Entry[] | null>> = { fed: fedEntries, fdn: fdnEntries };
  if (st === "FL") lists.fl = flEntries;
  const keys = Object.keys(lists) as SourceKey[];
  const count = (k: SourceKey, tier: string) => (lists[k] ?? []).filter((e) => e.tier === tier).length;
  const strong = Object.fromEntries(keys.map((k) => [k, count(k, "Strong")])) as Record<SourceKey, number>;
  const possible = Object.fromEntries(keys.map((k) => [k, count(k, "Possible")])) as Record<SourceKey, number>;
  const ready = keys.every((k) => lists[k] !== null || (k === "fdn" && !meta?.states.includes(st)));

  // Most strong matches first; keep the order unless another source pulls ahead, so tabs don't shuffle under a reader.
  useEffect(() => {
    if (!ready) return;
    const ranked = [...keys].sort((a, b) => strong[b] - strong[a] || possible[b] - possible[a]);
    const same = order.length === keys.length && order.every((k) => keys.includes(k));
    if (!same || strong[ranked[0]] > strong[order[0]]) setOrder(ranked);
  }, [ready, JSON.stringify(strong), JSON.stringify(possible), keys.join()]);
  useEffect(() => { if (order.length && (!tab || (!order.includes(tab as SourceKey) && tab !== "shortlist"))) setTab(order[0]); }, [order]);

  const total = keys.reduce((s, k) => s + strong[k], 0);
  // The saved order can still name a source the new state doesn't have (Florida programs after a switch to
  // New York) until the effect above catches up, so keep only today's sources, in that order.
  const shownOrder = [...order.filter((k) => keys.includes(k)), ...keys.filter((k) => !order.includes(k))];
  const parts = shownOrder.map((k) => strong[k] || !possible[k]
    ? n(strong[k], NOUN[k][2], NOUN[k][1])
    : `no strong ${NOUN[k][1]} (${possible[k].toLocaleString("en-US")} possible)`);
  const listing = parts.length > 1 ? parts.slice(0, -1).join(", ") + " and " + parts[parts.length - 1] : parts[0];

  // ---------- profile actions ----------
  const pending = !sameForm(draft, applied);

  async function update() {
    if (!pending) { setStatus("Your matches are already up to date."); return; }
    const textChanged = queryText(draft) !== queryText(applied);
    let v = vector;
    if (textChanged && (draft.mission.trim() || draft.keywords.trim())) {
      const ex = Object.values(examples ?? {}).find((e) => e.mission === draft.mission && e.keywords === draft.keywords);
      if (ex) v = ex.vector;
      else {
        setBusy("Reading your mission");
        try {
          v = await embedMission(queryText(draft), ({ loaded, total }) => {
            if (total) setBusy(`Downloading the matching model, ${Math.round(loaded / 1e6)} of ${Math.round(total / 1e6)} MB. This happens once.`);
          });
          setModelFailed(false);
        } catch {
          v = null;
          setModelFailed(true);
        }
      }
    }
    setBusy("");
    setVector(v);
    setApplied(draft);
    setStatus("updated");
  }

  // The answer to pressing the button, said where it was pressed, once the new scores exist.
  const statusText = status === "updated" ? `Updated: ${n(total, "strong match", "strong matches")}.` : status;
  useEffect(() => { if (status === "updated" && ready) setStatus(statusText); }, [ready, status]);

  function chooseExample(key: string) {
    const ex = examples?.[key];
    const f = ex ? exampleForm(ex) : { ...BLANK, state: draft.state };
    setExampleKey(key);
    setDraft(f);
    // An example applies at once, and has its vector ready, so nothing needs downloading.
    setApplied(f);
    setVector(ex ? ex.vector : null);
    setStatus("");
  }

  function loadProfile(f: ProfileForm) {
    setExampleKey("");
    setDraft(f);
    setStatus("Loaded your profile. Press Update matches to see your matches.");
  }

  const isExample = exampleKey && exampleKey !== "blank" && examples?.[exampleKey]
    && sameForm({ ...applied }, { ...exampleForm(examples[exampleKey]), ...pickRest(applied) });

  const formProps = {
    draft, setDraft, examples: examples ?? {}, exampleKey, onExample: chooseExample, onLoad: loadProfile, onUpdate: update,
    pending, busy, status: statusText, applied,
  };

  // ---------- render ----------
  const tabs: [string, string, number | null][] = [
    ...shownOrder.map((k): [string, string, number | null] => [k, NOUN[k][0], lists[k] ? strong[k] + possible[k] : null]),
    ["shortlist", "Shortlist", shortlist.items.length],
  ];
  const tabRefs = useRef<Record<string, HTMLButtonElement | null>>({});
  function onTabKey(ev: KeyboardEvent, i: number) {
    const dir = ev.key === "ArrowRight" ? 1 : ev.key === "ArrowLeft" ? -1 : 0;
    const to = ev.key === "Home" ? 0 : ev.key === "End" ? tabs.length - 1 : dir ? (i + dir + tabs.length) % tabs.length : -1;
    if (to < 0) return;
    ev.preventDefault();
    setTab(tabs[to][0]);
    tabRefs.current[tabs[to][0]]?.focus();
  }

  return (
    <>
      <a class="skip-link" href="#results">Skip to results</a>
      <header class="band">
        <div class="band-inner">
          <div class="masthead">
            <p class="name">Grant Matcher</p>
            <a class="short-count" href="#results" onClick={() => setTab("shortlist")}>
              <IconMark on={shortlist.items.length > 0} />Shortlist <span class="num">{shortlist.items.length}</span>
            </a>
          </div>
          <h1 class="answer" aria-live="polite">
            {blank ? "Describe your work to see which grants fit."
              : !ready ? "Ranking grants for this profile."
              : total ? <><strong>{n(total, "strong match", "strong matches")}</strong> for this profile: {listing}.</>
              : <><strong>No strong matches yet.</strong> {shownOrder.map((k) => n(possible[k], `possible ${NOUN[k][2]}`, `possible ${NOUN[k][1]}`)).join(", ")}. More specific key words usually help.</>}
          </h1>
          <p class="lede">Federal grants, private and community foundations{st === "FL" ? " and Florida state programs" : ""}, ranked against your mission with the reasons spelled out.</p>
          <p class="notice">{NOTICE}</p>
        </div>
      </header>

      <div class="layout">
        <aside class="side" aria-label="Your organization">
          <div class="phone-bar">
            <button type="button" class="btn phone-toggle" aria-expanded={phoneOpen} aria-controls="profile-panel"
                    onClick={() => setPhoneOpen(!phoneOpen)}>
              Edit your organization
            </button>
          </div>
          <div id="profile-panel" ref={panelRef} class={`profile-panel${phoneOpen || blank ? " open" : ""}`}>
            <ProfileFormView idp="p" {...formProps} />
          </div>
        </aside>

        <main id="results" tabIndex={-1} class="main">
          {isExample ? (
            <p class="note"><strong>This is an example.</strong> These matches are for a sample organization,{" "}
              <i>{examples![exampleKey].label}</i>. Describe your own work under Your organization to see yours.</p>
          ) : null}
          {modelFailed ? (
            <p class="note warn-note" role="alert">The matching model could not load, so these results rank by your key words only. Check your connection and press Update matches to try again.</p>
          ) : null}

          {blank ? <BlankSteps /> : (
            <>
              <div class="tabs" role="tablist" aria-label="Results by source">
                {tabs.map(([k, label, c], i) => (
                  <button type="button" role="tab" key={k} id={`tab-${k}`} aria-label={c !== null ? `${label}, ${c}` : label} aria-selected={tab === k} aria-controls={`panel-${k}`}
                          tabIndex={tab === k ? 0 : -1} ref={(el) => { tabRefs.current[k] = el; }}
                          onClick={() => setTab(k)} onKeyDown={(ev) => onTabKey(ev as KeyboardEvent, i)}>
                    <span><span class="tab-long">{label}</span><span class="tab-short" aria-hidden="true">{SHORT[k]}</span></span>{c !== null ? <span class="tab-count">{c.toLocaleString("en-US")}</span> : null}
                  </button>
                ))}
              </div>
              {tabs.map(([k]) => (
                <section role="tabpanel" id={`panel-${k}`} aria-labelledby={`tab-${k}`} hidden={tab !== k} key={k} class="panel">
                  {tab === k ? panel(k) : null}
                </section>
              ))}
            </>
          )}
          {blank ? null : (
            <details class="ready">
              <summary><h2>Getting ready to apply</h2></summary>
              <Checklist />
            </details>
          )}
          <Footer />
        </main>
      </div>
    </>
  );

  function panel(k: string) {
    if (k === "shortlist") return <ShortlistPanel items={shortlist.items} keys={shortlist.keys} toggle={shortlist.toggle} clear={shortlist.clear} />;
    if (k === "fed") return federalPanel();
    if (k === "fdn") return foundationPanel();
    return floridaPanel();
  }

  function tally(k: SourceKey, caption: string) {
    return (
      <div class="tally">
        <h2>{strong[k] ? <strong>{strong[k].toLocaleString("en-US")}</strong> : "0"} strong,{" "}
          <strong>{possible[k].toLocaleString("en-US")}</strong> possible {NOUN[k][1]}</h2>
        <p class="quiet">{caption}</p>
        <div class="key">
          <span class="key-scale" aria-hidden="true">
            <span class="rule"><span class="mark m35" /><span class="mark m60" /></span>
            <span class="key-labels"><span style={{ left: "0%" }}>0</span><span style={{ left: "35%" }}>35</span><span style={{ left: "60%" }}>60</span><span style={{ left: "100%" }}>100</span></span>
          </span>
          <span>Strong is 60 or more out of 100; possible is 35 to 59.</span>
        </div>
      </div>
    );
  }

  function cur(k: SourceKey): Narrow {
    return { ...nar[k], q };
  }

  function narrowed(k: SourceKey, entries: Entry[]): Entry[] {
    return narrow(entries, cur(k));
  }

  function setN(k: SourceKey, patch: Partial<Narrow>) {
    setNar({ ...nar, [k]: { ...nar[k], ...patch } });
  }

  /** The visible filters for one source: search, then the source's own choices, then what they hide. */
  function narrowBar(k: SourceKey, all: Entry[], shown: Entry[], noun: string) {
    const n = nar[k];
    const agencies = k === "fdn" ? [] : [...new Set(all.map((e) => e.agency).filter(Boolean) as string[])].sort();
    const on = isNarrowed(cur(k));
    const id = (s: string) => `${k}-${s}`;
    const newCount = all.filter((e) => e.isNew).length;
    const since = fresh[k]?.since;
    return (
      <div class="narrow">
        <div class="narrow-row">
          <div class="field grow">
            <label for={id("q")}>Search these results</label>
            <input id={id("q")} type="search" value={q} placeholder="For example: after school, Hillsborough"
                   onInput={(e) => setQ((e.target as HTMLInputElement).value)} />
          </div>
          {k !== "fl" ? (
            <div class="field">
              <label for={id("size")}>{k === "fed" ? "Award size" : "Typical grant"}</label>
              <select id={id("size")} value={n.size} onChange={(e) => setN(k, { size: (e.target as HTMLSelectElement).value })}>
                <option value="">Any size</option>
                {Object.entries(SIZE_BANDS).map(([v, [label]]) => <option value={v} key={v}>{label}</option>)}
              </select>
            </div>
          ) : null}
          {k === "fed" ? (
            <div class="field">
              <label for={id("before")}>Closes by</label>
              <input id={id("before")} type="date" value={n.before} onInput={(e) => setN(k, { before: (e.target as HTMLInputElement).value })} />
            </div>
          ) : null}
          {agencies.length > 1 ? (
            <div class="field">
              <label for={id("agency")}>Agency</label>
              <select id={id("agency")} value={n.agency} onChange={(e) => setN(k, { agency: (e.target as HTMLSelectElement).value })}>
                <option value="">Any agency</option>
                {agencies.map((a) => <option value={a} key={a}>{a}</option>)}
              </select>
            </div>
          ) : null}
        </div>
        {k === "fdn" ? (
          <fieldset class="narrow-checks">
            <legend class="sr-only">Show only foundations that</legend>
            <label class="check"><input type="checkbox" checked={n.apply} onChange={(e) => setN(k, { apply: (e.target as HTMLInputElement).checked })} /><span>Publish how to apply</span></label>
            <label class="check"><input type="checkbox" checked={n.open} onChange={(e) => setN(k, { open: (e.target as HTMLInputElement).checked })} /><span>Don't refuse unsolicited requests</span></label>
            <label class="check"><input type="checkbox" checked={n.local} onChange={(e) => setN(k, { local: (e.target as HTMLInputElement).checked })} /><span>Based in or funding your cities</span></label>
            {applied.has_501c3 !== "Yes" ? (
              <label class="check"><input type="checkbox" checked={n.no501} onChange={(e) => setN(k, { no501: (e.target as HTMLInputElement).checked })} /><span>Don't ask for 501(c)(3) proof</span></label>
            ) : null}
          </fieldset>
        ) : null}
        {newCount && since ? (
          <div class="narrow-checks">
            <label class="check"><input type="checkbox" checked={n.fresh} onChange={(e) => setN(k, { fresh: (e.target as HTMLInputElement).checked })} />
              <span>Only new since your last visit on {fmtVisit(since)} ({newCount.toLocaleString("en-US")})</span></label>
          </div>
        ) : null}
        <p class="narrowed" role="status">
          {on ? <>Showing {shown.length.toLocaleString("en-US")} of {all.length.toLocaleString("en-US")} {noun}.{" "}
            <button type="button" class="link-btn" onClick={() => { setQ(""); setNar({ ...nar, [k]: NO_NARROW }); }}>Clear filters</button></> : null}
        </p>
      </div>
    );
  }

  function fmtVisit(iso: string): string {
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? "your last visit" : d.toLocaleDateString("en-US", { month: "long", day: "numeric" });
  }

  function loading(what: string) {
    return <p class="loading" role="status">Loading {what}.</p>;
  }

  function federalPanel() {
    if (fed.state === "error") return <p class="error">The federal grant list could not be loaded right now. Try again in a few minutes.</p>;
    if (!fedEntries || fed.state !== "ready") return loading("federal grants");
    const updated = fed.data.fetchedAt ? fmtStamp(fed.data.fetchedAt) : "";
    const shown = narrowed("fed", fedEntries);
    const shownKeys = new Set(shown.map((e) => e.key));
    const picks = (fedScored ?? []).filter((s) => s.tier !== "Long shot" && shownKeys.has(`fed:${s.rec.id}`));
    return (
      <>
        {tally("fed", `${fed.data.records.length.toLocaleString("en-US")} open and forecasted federal opportunities that list nonprofits as eligible${updated ? `, updated ${updated}` : ""}.`
          + (strong.fed ? "" : " No strong federal matches is common for small direct-service groups: much federal money for local programs passes through state agencies first."))}
        {narrowBar("fed", fedEntries, shown, "grants")}
        <details class="filters">
          <summary>More filters and how the score works</summary>
          <div class="filters-body">
            <label class="check">
              <input type="checkbox" checked={applied.include_forecasted}
                     onChange={(e) => { const v = (e.target as HTMLInputElement).checked; setApplied({ ...applied, include_forecasted: v }); setDraft({ ...draft, include_forecasted: v }); }} />
              <span>Include forecasts (not open yet)</span>
            </label>
            <div class="field">
              <label for="min-days">Hide deadlines sooner than <span class="num">{applied.min_days_left}</span> days</label>
              <input id="min-days" type="range" min={0} max={60} value={applied.min_days_left}
                     onChange={(e) => { const v = +(e.target as HTMLInputElement).value; setApplied({ ...applied, min_days_left: v }); setDraft({ ...draft, min_days_left: v }); }} />
            </div>
            <ul class="how">
              <li>Up to 70 points for how closely the grant's description matches your mission, compared with how your mission matches grants in general</li>
              <li>Up to 30 points for your key words, with rare words like <i>dyslexia</i> worth more than common ones like <i>children</i></li>
              <li>Points off for research grants, cost sharing you can't provide, award sizes far above your budget, a 501(c)(3) requirement you don't meet, and programs aimed at tribes, states, or embassies abroad</li>
              <li>Strong is 60 and up, possible is 35 to 59</li>
            </ul>
          </div>
        </details>
        <ResultList name="fed" noun="grants" entries={shown} narrowed={isNarrowed(cur("fed"))} marked={shortlist.keys} onMark={shortlist.toggle}
          sorts={[["Best fit", null],
            ["Closing soonest", (a, b) => (a.sortClose ?? Infinity) - (b.sortClose ?? Infinity)],
            ["Largest award", (a, b) => (b.sortAward ?? -Infinity) - (a.sortAward ?? -Infinity)]]}
          exports={picks.length ? (
            <div class="exports">
              <button type="button" class="btn" onClick={() => download("federal-matches.csv", toCsv(
                ["score", "tier", "title", "agency", "number", "status", "close_date", "award_floor", "award_ceiling", "cost_sharing", "reasons", "cautions", "url"],
                picks.map(({ rec: r, ...s }) => [s.score, s.tier, r.title, r.agency, r.number, r.status, r.close_date, r.award_floor, r.award_ceiling, r.cost_sharing, s.reasons.join("; "), s.cautions.join("; "), r.url])), "text/csv")}>
                <IconDownload />Download matches (CSV)
              </button>
              <button type="button" class="btn" onClick={() => download("grant-deadlines.ics", toIcs(picks), "text/calendar")}>
                <IconDownload />Add deadlines to your calendar (.ics)
              </button>
            </div>
          ) : null} />
      </>
    );
  }

  function foundationPanel() {
    if (!meta?.states.includes(st)) return <p class="note">Foundation data for {STATE_NAMES[st] ?? st} isn't available yet. Florida is covered today.</p>;
    if (fdnSrc?.state === "error") return <p class="error">The foundation list could not be loaded right now. Try again in a few minutes.</p>;
    if (!fdnEntries || fdnSrc?.state !== "ready") return loading("foundations");
    const recs = fdnSrc.data.records;
    const kindCount = (k: string) => recs.filter((r) => (r.kind || "Private foundation") === k).length;
    const shown = narrowed("fdn", fdnEntries);
    const picks = shown.filter((e) => e.tier !== "Long shot");
    return (
      <>
        {tally("fdn", `${recs.length.toLocaleString("en-US")} grantmakers based in ${st} or giving there, from their latest IRS returns. Most funders back groups they already know, so start with an introduction.`)}
        {narrowBar("fdn", fdnEntries, shown, "foundations")}
        <details class="filters">
          <summary>More filters and how the score works</summary>
          <div class="filters-body">
            <fieldset class="field">
              <legend class="label">Types</legend>
              {KINDS.map((k) => (
                <label class="check" key={k}>
                  <input type="checkbox" checked={fdnKinds.includes(k)}
                         onChange={(e) => setFdnKinds((e.target as HTMLInputElement).checked ? [...fdnKinds, k] : fdnKinds.filter((x) => x !== k))} />
                  <span>{k} <span class="quiet num">({kindCount(k).toLocaleString("en-US")})</span></span>
                </label>
              ))}
            </fieldset>
            <label class="check">
              <input type="checkbox" checked={fdnPre} onChange={(e) => setFdnPre((e.target as HTMLInputElement).checked)} />
              <span>Include foundations that say they fund preselected groups only</span>
            </label>
            <ul class="how">
              <li>Up to 75 points for fit: 60 for how closely its past grant purposes match your mission, 15 for your key words</li>
              <li>Up to 20 points for how much it gives in {st}, and more if it funds groups in your cities or is a community foundation serving your area</li>
              <li>Points off when its typical grant is large for your budget, when it says it doesn't take unsolicited requests, or when it mostly gives scholarships</li>
              <li>Scores stop at 100. Strong is 60 and up, possible is 35 to 59</li>
              <li>Data comes from the foundation's own tax return, usually one to two years old</li>
            </ul>
          </div>
        </details>
        <ResultList name="fdn" noun="foundations" entries={shown} narrowed={isNarrowed(cur("fdn"))} marked={shortlist.keys} onMark={shortlist.toggle}
          sorts={[["Best fit", null],
            [`Most grants in ${st}`, (a, b) => (b.sortInState ?? 0) - (a.sortInState ?? 0)],
            ["Largest typical grant", (a, b) => (b.sortMedian ?? -Infinity) - (a.sortMedian ?? -Infinity)]]}
          exports={picks.length ? (
            <div class="exports">
              <button type="button" class="btn" onClick={() => download("foundation-matches.csv", entriesCsv(picks), "text/csv")}>
                <IconDownload />Download foundation matches (CSV)
              </button>
            </div>
          ) : null} />
      </>
    );
  }

  function floridaPanel() {
    if (fl.state === "error") return <p class="error">Florida program data could not be loaded right now. Try again in a few minutes.</p>;
    if (!flEntries || fl.state !== "ready") return loading("Florida programs");
    const all = fl.data.records;
    const open = all.filter((r) => r.nonprofit_eligible && !r.earmark).length;
    const shown = narrowed("fl", flEntries);
    const picks = shown.filter((e) => e.tier !== "Long shot");
    return (
      <>
        {tally("fl", `${open.toLocaleString("en-US")} of ${all.length.toLocaleString("en-US")} Florida programs (fiscal year ${fl.data.fiscalYear}) are open to nonprofits. These are programs, not open calls: check each agency's site for the next window.`)}
        {narrowBar("fl", flEntries, shown, "programs")}
        <details class="filters">
          <summary>More filters and how the score works</summary>
          <div class="filters-body">
            <label class="check">
              <input type="checkbox" checked={flEar} onChange={(e) => setFlEar((e.target as HTMLInputElement).checked)} />
              <span>Include programs the Legislature set aside for named organizations</span>
            </label>
            <ul class="how">
              <li>Up to 75 points for how closely the program's objectives match your mission</li>
              <li>Up to 25 points for your key words in its title and objectives, with rare words worth more</li>
              <li>Points off for student aid paid to individuals or schools, and for programs the Legislature set aside for a named organization</li>
              <li>Strong is 60 and up, possible is 35 to 59</li>
            </ul>
          </div>
        </details>
        <ResultList name="fl" noun="programs" entries={shown} narrowed={isNarrowed(cur("fl"))} marked={shortlist.keys} onMark={shortlist.toggle}
          exports={picks.length ? (
            <div class="exports">
              <button type="button" class="btn" onClick={() => download("florida-matches.csv", entriesCsv(picks), "text/csv")}>
                <IconDownload />Download Florida matches (CSV)
              </button>
            </div>
          ) : null} />
      </>
    );
  }
}

/** The rest of the profile (the federal filters) that doesn't decide whether it is still the example. */
function pickRest(f: ProfileForm): Partial<ProfileForm> {
  return { include_forecasted: f.include_forecasted, min_days_left: f.min_days_left, has_501c3: f.has_501c3,
    budget_band: f.budget_band, can_cost_share: f.can_cost_share };
}

function entriesCsv(items: Entry[]): string {
  const src = { fed: "Federal grant", fdn: "Foundation", fl: "Florida program" } as const;
  return toCsv(["source", "score", "tier", "name", "catalog", "details", "deadline_or_size", "reasons", "cautions", "url"],
    items.map((e) => [src[e.source], e.score, e.tier, e.title, e.catalog, e.facts.join("; "), e.side,
      [...e.fits, ...e.also, ...e.status].join("; "), e.cautions.join("; "), e.url]));
}

function fmtStamp(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleDateString("en-US", { month: "short", day: "2-digit", year: "numeric" });
}

function ShortlistPanel(p: { items: Entry[]; keys: Set<string>; toggle: (e: Entry) => void; clear: () => void }) {
  const [confirm, setConfirm] = useState(false);
  if (!p.items.length) {
    return (
      <div class="tally">
        <h2>Your shortlist is empty</h2>
        <p class="quiet">Press Add to shortlist on any result to keep it here. The shortlist stays in this browser on this device, and nothing is sent anywhere.</p>
      </div>
    );
  }
  return (
    <>
      <div class="tally">
        <h2><strong>{p.items.length}</strong> on your shortlist</h2>
        <p class="quiet">Kept in this browser on this device. Scores are from when you added each one.</p>
      </div>
      <ol class="entries">
        {p.items.map((e) => <li key={e.key}><EntryView e={e} marked={p.keys.has(e.key)} onMark={p.toggle} /></li>)}
      </ol>
      <div class="exports">
        <button type="button" class="btn" onClick={() => download("shortlist.csv", entriesCsv(p.items), "text/csv")}>
          <IconDownload />Download your shortlist (CSV)
        </button>
        {confirm ? (
          <span class="confirm" role="alert">Remove all {p.items.length}?
            <button type="button" class="btn" onClick={() => { p.clear(); setConfirm(false); }}>Clear the shortlist</button>
            <button type="button" class="btn" onClick={() => setConfirm(false)}>Keep it</button>
          </span>
        ) : <button type="button" class="btn quiet-btn" onClick={() => setConfirm(true)}>Clear the shortlist</button>}
      </div>
    </>
  );
}

function BlankSteps() {
  return (
    <div class="note blank">
      <p><strong>Tell us about your work to see matches.</strong></p>
      <ol>
        <li>Describe your mission and programs under Your organization.</li>
        <li>Add a few key words a matching grant would use.</li>
        <li>Set your state and, if you like, your cities or counties.</li>
      </ol>
      <p>Then press Update matches. The first search downloads the matching model (about 67 MB) once; after that it runs right here in your browser, and your mission never leaves this device.</p>
    </div>
  );
}

function Checklist() {
  return (
    <div class="checklist">
      <h2>Getting ready to apply</h2>
      <h3>For any funder</h3>
      <ol>
        <li><strong>Your IRS determination letter</strong> showing 501(c)(3) status.</li>
        <li><strong>A one-page organization summary:</strong> mission, programs, who you serve, and the results you track.</li>
        <li><strong>A simple annual budget</strong> and, for larger requests, your most recent financial statements.</li>
        <li><strong>Your board list</strong> and a short bio for your director.</li>
      </ol>
      <h3>For federal grants</h3>
      <p>These registrations take weeks, so start early.</p>
      <ol>
        <li><strong>SAM.gov registration and a Unique Entity ID (UEI).</strong> Free, required for every federal applicant, and renewed every year. Start at <a href="https://sam.gov" target="_blank" rel="noopener">sam.gov</a>.</li>
        <li><strong>A Grants.gov applicant account</strong> linked to your organization. See <a href="https://www.grants.gov/applicants/applicant-registration" target="_blank" rel="noopener">Grants.gov applicant registration</a>.</li>
      </ol>
      <h3>For foundations</h3>
      <ul>
        <li>Read the "How to apply" notes. Many want a short letter of inquiry first, not a full proposal.</li>
        <li>Look at who they funded last year. If they fund groups like yours near you, mention that connection.</li>
        <li>Community foundations in your county are often the best first call, and many run small grant cycles for new nonprofits.</li>
      </ul>
      <h3>For Florida state programs</h3>
      <ul>
        <li>The state pays grants and contracts to registered vendors. Register at <a href="https://www.myfloridamarketplace.com" target="_blank" rel="noopener">MyFloridaMarketPlace</a> and keep a Florida Substitute W-9 on file with the Department of Financial Services.</li>
        <li>Each agency posts its own application windows. Use the agency link on each program to find the next one.</li>
      </ul>
    </div>
  );
}

function Footer() {
  return (
    <footer class="footer">
      <p>{NOTICE}</p>
      <p>Federal data from the Grants.gov API, refreshed nightly. Foundation data from IRS Form 990-PF and Form 990 Schedule I e-file returns. Florida data from the Department of Financial Services Catalog of State Financial Assistance.</p>
      <p>Scores are a starting point for your own review, not a guarantee of eligibility. Matching runs in your browser; your mission and profile are never sent to a server.</p>
      <p>Source code: <a href="https://github.com/RendellRich/grant-matcher">github.com/RendellRich/grant-matcher</a></p>
    </footer>
  );
}
