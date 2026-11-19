import { useEffect, useMemo, useRef, useState } from "preact/hooks";
import {
  loadCounties, loadExamples, loadFederal, loadFlorida, loadFoundations, loadMeta,
  type Example, type Meta, type Source,
} from "./data";
import { embedMission } from "./embed";
import {
  isNarrowed, narrow, NO_NARROW, profileNarrow, SIZE_BANDS, type Entry, type Narrow, type SourceKey,
} from "./entries";
import { download, toCsv, toIcs } from "./exports";
import { exampleForm, ProfileFormView } from "./form";
import { CoverageNote } from "./coverage";
import { BLANK, expandCities, sameForm, STATE_NAMES, type ProfileForm } from "./profile";
import { federalEntries, isBlank, KINDS, queryText, rankFlorida, rankFoundations, toProfile } from "./rank";
import {
  closeDate, fmtDate, scoreFederal,
  type FederalRec, type FloridaRec, type FoundationRec, type Profile,
} from "./score";
import { EntryView, IconAlert, IconDownload, IconMark, ResultList, type MarkAction } from "./ui";
import { embedParent, listen, loadedLabel, payloadFor, post, PROTOCOL, type Incoming, type LoadedFrom, type PipelineItem } from "./parent";
import { markNew, markOrgNew, newSince, strongKeys, type Fresh, type OrgSeen } from "./seen";
import {
  byDeadline, comingUp, deadline, dropSubmitted, dueText, daysUntil, listedNow, parseShortlist, setDue, setStage, shortlistIcs,
  STAGE_LABEL, STAGES, submittedKeys, toggle as toggleItem, type Item, type Listed, type Stage,
} from "./shortlist";
import { similarities } from "./vectors";

const NOTICE = "This product uses the Grants.gov API but is not endorsed or certified by the U.S. Department of Health and Human Services.";
const SHORT: Record<string, string> = { fl: "Florida", fdn: "Foundations", fed: "Federal", shortlist: "Shortlist" };
const NOUN: Record<SourceKey, [string, string, string]> = {
  fl: ["Florida programs", "Florida programs", "Florida program"],
  fdn: ["Foundations", "foundations", "foundation"],
  fed: ["Federal grants", "federal grants", "federal grant"],
};

type Loaded<T> = { state: "loading" } | { state: "ready"; data: T } | { state: "error" };

const n = (count: number, one: string, many: string) => `${count.toLocaleString("en-US")} ${count === 1 ? one : many}`;

const NO_KEYS = new Set<string>();
const ANSWER_WAIT = 15_000; // how long to wait for ETO before saying it didn't answer

function useShortlist() {
  const [items, setItems] = useState<Item[]>(() => {
    try { return parseShortlist(localStorage.getItem("gm-shortlist")); } catch { return []; }
  });
  const keys = useMemo(() => new Set(items.map((e) => e.key)), [items]);
  const done = useMemo(() => submittedKeys(items), [items]);
  const save = (next: Item[]) => {
    setItems(next);
    try { localStorage.setItem("gm-shortlist", JSON.stringify(next)); } catch { /* private mode: keep it for this visit */ }
  };
  return {
    items, keys, done,
    toggle: (e: Entry) => save(toggleItem(items, e)),
    stage: (key: string, s: Stage) => save(setStage(items, key, s)),
    due: (key: string, d: string) => save(setDue(items, key, d)),
    clear: () => { setItems([]); try { localStorage.removeItem("gm-shortlist"); } catch { /* */ } },
  };
}
type Shortlist = ReturnType<typeof useShortlist>;

export function App() {
  // Inside ETO's admin page (?embed=eto, framed by an allowed site), ETO keeps the profile and the pipeline,
  // and "Send to funding pipeline" takes the place of the shortlist.
  const parentOrigin = useMemo(() => embedParent(window.location, document.referrer, window.parent !== window), []);
  const embedded = parentOrigin !== null;
  const [pipeline, setPipeline] = useState<Map<string, PipelineItem>>(new Map());
  const [sending, setSending] = useState<Set<string>>(new Set());
  const sendingRef = useRef(sending);
  sendingRef.current = sending;
  const [sentNote, setSentNote] = useState<{ ok: boolean; text: string } | null>(null);
  const [saving, setSaving] = useState(false);
  const savingRef = useRef(saving);
  savingRef.current = saving;
  const [saveResult, setSaveResult] = useState<{ ok: boolean; text: string } | null>(null);
  const sentTitles = useRef(new Map<string, string>());
  const fromParent = useRef(false); // set once ETO has sent its profile
  const etoProfile = useRef<ProfileForm | null>(null); // the profile ETO saved, to count matches for it only
  const [etoSeen, setEtoSeen] = useState<OrgSeen | null>(null); // ETO's shared New marks, when ETO sends them
  const countedRef = useRef(""); // the last strong keys sent to ETO, so each set is sent once
  const savedDraft = useRef<ProfileForm | null>(null); // the profile last sent to ETO to save
  const [sentNow, setSentNow] = useState<Set<string>>(new Set()); // sent during this visit: stay in view, marked
  // "Already in our pipeline" hides what ETO reported, not what was just sent, so a sent grant doesn't vanish.
  const pipelineToHide = useMemo(() => new Map([...pipeline].filter(([k]) => !sentNow.has(k))), [pipeline, sentNow]);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [examples, setExamples] = useState<Record<string, Example> | null>(null);
  const [fed, setFed] = useState<Loaded<Source<FederalRec>>>({ state: "loading" });
  const [fl, setFl] = useState<Loaded<Source<FloridaRec>>>({ state: "loading" });
  const [fdn, setFdn] = useState<Record<string, Loaded<Source<FoundationRec>>>>({});

  const [exampleKey, setExampleKey] = useState("literacy");
  const [loadedFrom, setLoadedFrom] = useState<LoadedFrom>("file");
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
  const [filtersOpen, setFiltersOpen] = useState(false); // phones fold the filters under one button
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
      if (fromParent.current) return; // ETO's own profile arrived first; the example must not replace it
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

  const [counties, setCounties] = useState<Record<string, Record<string, string[]> | null>>({});
  useEffect(() => {
    if (st in counties) return;
    setCounties((m) => ({ ...m, [st]: null }));
    loadCounties(st).then((c) => setCounties((m) => ({ ...m, [st]: c }))).catch(() => undefined);
  }, [st]);
  const cityList = useMemo(() => expandCities(applied.cities, counties[st] ?? null), [applied.cities, counties, st]);

  // ---------- scoring ----------
  // The same ranking as the background scorer (rank.ts), so ETO's count is the same wherever it is made.
  const profile: Profile = useMemo(() => toProfile(applied), [applied]);
  const blank = isBlank(applied);
  const sim = (vecs: Source<unknown>["vecs"]) => (vector && !blank ? similarities(vecs, vector) : null);

  const fedScored = useMemo(() => fed.state === "ready" && !blank
    ? scoreFederal(fed.data.records, profile, sim(fed.data.vecs)) : null, [fed, profile, vector]);
  const fdnSrc = fdn[st];
  // What's new since the last visit is about the data, not the profile, so it is worked out once per source.
  const fedFresh = useMemo(() => (fed.state === "ready" ? newSince("fed", fed.data.records.map((r) => r.id)) : null), [fed]);
  const fdnFresh = useMemo(() => (fdnSrc?.state === "ready" ? newSince(`fdn-${st}`, fdnSrc.data.records.map((r) => r.ein)) : null), [fdnSrc]);
  const flFresh = useMemo(() => (fl.state === "ready" ? newSince("fl", fl.data.records.map((r) => r.id)) : null), [fl]);
  const fresh: Record<SourceKey, Fresh | null> = { fed: fedFresh, fdn: fdnFresh, fl: flFresh };
  // Inside ETO, New means a strong match ETO hasn't seen, shared by everyone who signs in; elsewhere it is this browser's.
  const mark = <T extends Entry>(list: T[] | null, f: Fresh | null) => (etoSeen ? markOrgNew(list, etoSeen) : markNew(list, f));
  const fedAll = useMemo(() => mark(fedScored ? federalEntries(fedScored, profile) : null, fedFresh), [fedScored, fedFresh, etoSeen]);
  const fdnAll = useMemo(() => mark(fdnSrc?.state === "ready" && !blank
    ? rankFoundations(fdnSrc.data.records, profile, st, cityList, sim(fdnSrc.data.vecs), fdnKinds, fdnPre)
    : null, fdnFresh), [fdnSrc, profile, vector, fdnKinds, fdnPre, fdnFresh, cityList, etoSeen]);
  const flAll = useMemo(() => mark(fl.state === "ready" && st === "FL" && !blank
    ? rankFlorida(fl.data.records, profile, sim(fl.data.vecs), flEar, cityList) : null, flFresh),
  [fl, profile, vector, flEar, st, flFresh, cityList, etoSeen]);
  // Anything marked submitted on the shortlist stops showing in the results and their counts.
  const done = embedded ? NO_KEYS : shortlist.done;
  const fedOut = useMemo(() => dropSubmitted(fedAll, done), [fedAll, done]);
  const fdnOut = useMemo(() => dropSubmitted(fdnAll, done), [fdnAll, done]);
  const flOut = useMemo(() => dropSubmitted(flAll, done), [flAll, done]);
  // The profile's filters (what you ask for, which funders, timing, the hide list) apply on every tab.
  const fedP = useMemo(() => profileNarrow(fedOut.entries, applied, undefined, pipelineToHide), [fedOut, applied, pipelineToHide]);
  const fdnP = useMemo(() => profileNarrow(fdnOut.entries, applied, undefined, pipelineToHide), [fdnOut, applied, pipelineToHide]);
  const flP = useMemo(() => profileNarrow(flOut.entries, applied, undefined, pipelineToHide), [flOut, applied, pipelineToHide]);
  const fedEntries = fedP.entries, fdnEntries = fdnP.entries, flEntries = flP.entries;
  const hiddenByProfile: Record<SourceKey, number> = { fed: fedP.hidden, fdn: fdnP.hidden, fl: flP.hidden };
  const hiddenDone: Record<SourceKey, number> = { fed: fedOut.hidden, fdn: fdnOut.hidden, fl: flOut.hidden };
  // Today's Grants.gov dates for shortlisted federal grants, so a moved or withdrawn deadline shows.
  const listed = useMemo(() => listedNow(shortlist.items, fed.state === "ready"
    ? fed.data.records.map((r) => ({ id: String(r.id), close: closeDate(r.close_date, profile.today ?? new Date()) })) : null),
  [shortlist.items, fed, profile.today]);
  const dueSoon = useMemo(() => comingUp(shortlist.items, listed, new Date(), 7), [shortlist.items, listed]);

  const lists: Partial<Record<SourceKey, Entry[] | null>> = {};
  if (applied.funder_types.includes("federal")) lists.fed = fedEntries;
  if (applied.funder_types.some((t) => !["federal", "florida"].includes(t))) lists.fdn = fdnEntries;
  if (st === "FL" && applied.funder_types.includes("florida")) lists.fl = flEntries;
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

  async function update(f: ProfileForm = draft, force = false) {
    if (!force && sameForm(f, applied)) { setStatus("Your matches are already up to date."); return; }
    const textChanged = queryText(f) !== queryText(applied);
    let v = vector;
    if (textChanged && (f.mission.trim() || f.keywords.trim())) {
      const ex = Object.values(examples ?? {}).find((e) => e.mission === f.mission && e.keywords === f.keywords);
      if (ex) v = ex.vector;
      else {
        setBusy("Reading your mission");
        try {
          v = await embedMission(queryText(f), ({ loaded, total }) => {
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
    setApplied(f);
    setStatus("updated");
  }

  // ---------- inside ETO ----------
  const onParent = useRef<(m: Incoming) => void>(() => undefined);
  onParent.current = (m) => {
    if (m.type === "eto:profile") {
      fromParent.current = true;
      etoProfile.current = m.profile;
      setLoadedFrom("eto");
      setExampleKey("");
      setDraft(m.profile);
      void update(m.profile, true);
    } else if (m.type === "eto:in-pipeline") {
      setPipeline(new Map(m.items.map((i) => [i.key, i])));
    } else if (m.type === "eto:sent") {
      setSending((s) => { const next = new Set(s); next.delete(m.key); return next; });
      const title = sentTitles.current.get(m.key) ?? "This grant";
      const at = m.stage ? ` at ${m.stage}` : "";
      if (m.ok) {
        setSentNow((s) => new Set(s).add(m.key));
        setPipeline((p) => new Map(p).set(m.key, { key: m.key, stage: m.stage || "Prospect", closed: false }));
        setSentNote({ ok: true, text: m.status === "exists" ? `${title} is already in the funding pipeline${at}.` : `Sent ${title} to the funding pipeline${at}.` });
      } else {
        setSentNote({ ok: false, text: m.message || `${title} wasn't saved. Try again, or add it in Funding.` });
      }
    } else if (m.type === "eto:seen") {
      setEtoSeen({ keys: new Set(m.keys), since: m.since });
    } else if (m.type === "eto:profile-saved") {
      setSaving(false);
      if (m.ok && savedDraft.current) etoProfile.current = savedDraft.current;
      setSaveResult(m.ok ? { ok: true, text: "Saved to ETO." } : { ok: false, text: m.message || "The profile wasn't saved. Try again." });
    }
  };
  useEffect(() => {
    if (!parentOrigin) return;
    const stop = listen(parentOrigin, (m) => onParent.current(m));
    post(parentOrigin, { type: "gm:ready", protocol: PROTOCOL });
    return stop;
  }, [parentOrigin]);

  function sendToPipeline(e: Entry) {
    if (!parentOrigin || pipeline.has(e.key) || sending.has(e.key)) return;
    sentTitles.current.set(e.key, e.title);
    setSending((s) => new Set(s).add(e.key));
    setSentNote(null);
    post(parentOrigin, { type: "gm:send", item: payloadFor(e) });
    window.setTimeout(() => {
      if (!sendingRef.current.has(e.key)) return;
      setSending((s) => { const next = new Set(s); next.delete(e.key); return next; });
      setSentNote({ ok: false, text: `ETO didn't answer, so ${e.title} may not have been saved. Check Funding before sending it again.` });
    }, ANSWER_WAIT);
  }

  function saveToParent() {
    if (!parentOrigin) return;
    setSaving(true);
    setSaveResult(null);
    savedDraft.current = draft;
    post(parentOrigin, { type: "gm:save-profile", profile: draft });
    window.setTimeout(() => {
      if (!savingRef.current) return;
      setSaving(false);
      setSaveResult({ ok: false, text: "ETO didn't answer, so the profile may not have been saved. Try again." });
    }, ANSWER_WAIT);
  }

  const pipelineKeys = useMemo(() => new Set(pipeline.keys()), [pipeline]);
  const markAction: MarkAction = {
    label: (e, on) => (on ? `In pipeline: ${pipeline.get(e.key)?.stage || "Prospect"}` : "Send to funding pipeline"),
    busy: sending,
  };
  const markProps = embedded
    ? { marked: pipelineKeys, onMark: sendToPipeline, action: markAction }
    : { marked: shortlist.keys, onMark: shortlist.toggle };

  // The answer to pressing the button, said where it was pressed, once the new scores exist.
  const statusText = status === "updated" ? `Updated: ${n(total, "strong match", "strong matches")}.` : status;
  useEffect(() => { if (status === "updated" && ready) setStatus(statusText); }, [ready, status]);
  // Inside ETO: once the matches for ETO's own saved profile are ready, tell ETO which are strong. ETO counts the
  // new ones for its sidebar and remembers them as seen. Matches for an unsaved edit are never sent.
  useEffect(() => {
    if (!parentOrigin || !etoSeen || !ready || busy || modelFailed || !vector) return;
    if (!etoProfile.current || !sameForm(applied, etoProfile.current)) return;
    const keys = strongKeys([fedAll, fdnAll, flAll]);
    const sig = `${st}|${keys.join(",")}`;
    if (sig === countedRef.current) return;
    countedRef.current = sig;
    post(parentOrigin, { type: "gm:matches", keys, counted_at: new Date().toISOString() });
  }, [parentOrigin, etoSeen, ready, busy, modelFailed, vector, applied, fedAll, fdnAll, flAll, st]);

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
    setLoadedFrom("file");
    setExampleKey("");
    setDraft(f);
    setStatus("Loaded your profile. Press Update matches to see your matches.");
  }

  const isExample = exampleKey && exampleKey !== "blank" && examples?.[exampleKey]
    && sameForm({ ...applied }, { ...exampleForm(examples[exampleKey]), ...pickRest(applied) });

  const formProps = {
    draft, setDraft, examples: examples ?? {}, exampleKey, loadedLabel: loadedLabel(loadedFrom), onExample: chooseExample, onLoad: loadProfile, onUpdate: update,
    pending, busy, status: statusText, applied,
    parent: embedded ? { onSave: saveToParent, saving, result: saveResult } : undefined,
  };

  // ---------- render ----------
  const tabs: [string, string, number | null][] = [
    ...shownOrder.map((k): [string, string, number | null] => [k, NOUN[k][0], lists[k] ? strong[k] + possible[k] : null]),
    ...(embedded ? [] : [["shortlist", "Shortlist", shortlist.items.length] as [string, string, number | null]]),
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
            {embedded ? null : (
              <a class="short-count" href="#results" onClick={() => setTab("shortlist")}>
                <IconMark on={shortlist.items.length > 0} />Shortlist <span class="num">{shortlist.items.length}</span>
              </a>
            )}
          </div>
          <h1 class="answer" aria-live="polite">
            {blank ? "Describe your work to see which grants fit."
              : !ready ? "Ranking grants for this profile."
              : total ? <><strong>{n(total, "strong match", "strong matches")}</strong> for this profile: {listing}.</>
              : <><strong>No strong matches yet.</strong> {shownOrder.map((k) => n(possible[k], `possible ${NOUN[k][2]}`, `possible ${NOUN[k][1]}`)).join(", ")}. More specific key words usually help.</>}
          </h1>
          <p class="lede">Federal grants, private and community foundations{st === "FL" ? " and Florida state and county programs" : ""}, ranked against your mission with the reasons spelled out.</p>
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
          {embedded ? (
            <div class="toast-wrap" role="status">
              {sentNote?.ok ? <p class="toast">{sentNote.text}</p> : null}
            </div>
          ) : null}
          {embedded && sentNote && !sentNote.ok ? <p class="toast warn" role="alert">{sentNote.text}</p> : null}
          {!embedded && dueSoon.length && tab !== "shortlist" ? (
            <p class="note due-soon">
              <strong>{dueSoon.length === 1 ? "1 grant on your shortlist is" : `${dueSoon.length} grants on your shortlist are`} due within a week</strong>
              {dueSoon[0].days < 0 ? ", and one is past due" : ""}.{" "}
              <button type="button" class="link-btn" onClick={() => setTab("shortlist")}>Open your shortlist</button>
            </p>
          ) : null}
          {isExample ? (
            <p class="note"><strong>Example results</strong> for a sample organization,{" "}
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
          <Footer coverage={!!meta?.coverage} />
        </main>
      </div>
    </>
  );

  function panel(k: string) {
    if (k === "shortlist") return <ShortlistPanel list={shortlist} listed={listed} />;
    if (k === "fed") return federalPanel();
    if (k === "fdn") return foundationPanel();
    return floridaPanel();
  }

  /** The count line for one source. With filters on it counts what they leave, so it agrees with the list below. */
  function tally(k: SourceKey, caption: string, shown?: Entry[]) {
    const on = Boolean(shown) && isNarrowed(cur(k));
    const s = on ? shown!.filter((e) => e.tier === "Strong").length : strong[k];
    const p = on ? shown!.filter((e) => e.tier === "Possible").length : possible[k];
    return (
      <div class="tally">
        <h2>{s ? <strong>{s.toLocaleString("en-US")}</strong> : "0"} strong,{" "}
          <strong>{p.toLocaleString("en-US")}</strong> possible {NOUN[k][1]}{on ? " with your filters" : ""}</h2>
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
    // Every count here is of strong and possible matches, the same pool the tab and the line under the filters count.
    const pool = all.filter((e) => e.tier !== "Long shot");
    const count = (f: (e: Entry) => unknown) => pool.filter(f).length.toLocaleString("en-US");
    const newCount = pool.filter((e) => e.isNew).length;
    const since = etoSeen ? etoSeen.since : fresh[k]?.since;
    const onCount = Object.entries(n).filter(([key, v]) => key !== "q" && Boolean(v)).length;
    const hasMore = k !== "fl" || agencies.length > 1 || Boolean(newCount && since);
    const check = (key: "apply" | "open" | "local" | "no501" | "cycle" | "corp" | "steady" | "firstTime" | "newHere", label: string) => (
      <label class="check"><input type="checkbox" checked={Boolean(n[key])} onChange={(e) => setN(k, { [key]: (e.target as HTMLInputElement).checked })} /><span>{label}</span></label>
    );
    return (
      <div class={`narrow${filtersOpen ? " open" : ""}`}>
        <div class="narrow-row">
          <div class="field grow">
            <label for={id("q")}>Search these results</label>
            <input id={id("q")} type="search" value={q} placeholder="For example: after school, Hillsborough"
                   onInput={(e) => setQ((e.target as HTMLInputElement).value)} />
          </div>
          {hasMore ? (
            <button type="button" class="btn narrow-toggle" aria-expanded={filtersOpen} onClick={() => setFiltersOpen(!filtersOpen)}>
              {filtersOpen ? "Hide filters" : "Filters"}{onCount ? ` (${onCount} on)` : ""}
            </button>
          ) : null}
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
          {k === "fdn" ? (
            <div class="field">
              <label for={id("reach")}>Where it gives</label>
              <select id={id("reach")} value={n.reach} onChange={(e) => setN(k, { reach: (e.target as HTMLSelectElement).value as Narrow["reach"] })}>
                <option value="">Anywhere</option>
                <option value="state">Mostly in {STATE_NAMES[st] ?? st}</option>
                <option value="national">Nationally (5 or more states)</option>
              </select>
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
          <div class="narrow-groups" role="group" aria-label="Show only foundations that">
            <fieldset class="narrow-group">
              <legend>Open to requests</legend>
              {check("apply", "Publish how to apply")}
              {check("open", "Haven't said no to unsolicited requests")}
              {pool.some((e) => e.cycle === "open" || e.cycle === "deadline")
                ? check("cycle", `Say online that applications are open or a deadline is ahead (${count((e) => e.cycle === "open" || e.cycle === "deadline")})`) : null}
              {applied.has_501c3 !== "Yes" ? check("no501", "Don't ask for 501(c)(3) proof") : null}
            </fieldset>
            {pool.some((e) => e.steady || e.firstTime || e.newHere) ? (
              <fieldset class="narrow-group">
                <legend>Giving history</legend>
                {pool.some((e) => e.steady) ? check("steady", `Gave every year for four years (${count((e) => e.steady)})`) : null}
                {pool.some((e) => e.firstTime) ? check("firstTime", `Often fund groups new to them (${count((e) => e.firstTime)})`) : null}
                {pool.some((e) => e.newHere) ? check("newHere", `Started giving in your cities in their latest year (${count((e) => e.newHere)})`) : null}
              </fieldset>
            ) : null}
            <fieldset class="narrow-group">
              <legend>Place and type</legend>
              {check("local", "Based in or funding your cities")}
              {pool.some((e) => e.corp) ? check("corp", `Company foundations (${count((e) => e.corp)})`) : null}
            </fieldset>
          </div>
        ) : null}
        {newCount && since ? (
          <div class="narrow-checks">
            <label class="check"><input type="checkbox" checked={n.fresh} onChange={(e) => setN(k, { fresh: (e.target as HTMLInputElement).checked })} />
              <span>Only new since {etoSeen ? "ETO last looked" : "your last visit"} on {fmtVisit(since)} ({newCount.toLocaleString("en-US")})</span></label>
          </div>
        ) : null}
        {hiddenByProfile[k] ? (
          <p class="quiet">Your profile's filters hide {hiddenByProfile[k].toLocaleString("en-US")} {hiddenByProfile[k] === 1 ? NOUN[k][2] : NOUN[k][1]}.
            Change them under Your organization.</p>
        ) : null}
        {hiddenDone[k] ? (
          <p class="quiet">{hiddenDone[k] === 1 ? `1 ${NOUN[k][2]} you submitted is` : `${hiddenDone[k].toLocaleString("en-US")} ${NOUN[k][1]} you submitted are`} hidden here.{" "}
            <button type="button" class="link-btn" onClick={() => setTab("shortlist")}>Open your shortlist</button></p>
        ) : null}
        <p class="narrowed" role="status">
          {on ? <>Showing {shown.filter((e) => e.tier !== "Long shot").length.toLocaleString("en-US")} of {pool.length.toLocaleString("en-US")} strong and possible {noun}.{" "}
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
          + (strong.fed ? "" : " No strong federal matches is common for small direct-service groups: much federal money for local programs passes through state agencies first."), shown)}
        {!applied.registrations.includes("sam") ? (
          <p class="note">Federal applications need a free SAM.gov registration and a Unique Entity ID first, and approval can take several weeks. Start at <a href="https://sam.gov" target="_blank" rel="noopener">sam.gov<span class="sr-only"> (opens in a new tab)</span></a>.</p>
        ) : null}
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
        <ResultList name="fed" noun="grants" entries={shown} narrowed={isNarrowed(cur("fed"))} {...markProps}
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
        {tally("fdn", `Scored from ${recs.length.toLocaleString("en-US")} grantmakers based in ${st} or giving there, using their latest IRS returns. Most funders back groups they already know, so start with an introduction.`, shown)}
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
        <ResultList name="fdn" noun="foundations" entries={shown} narrowed={isNarrowed(cur("fdn"))} {...markProps}
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
    const stateAll = all.filter((r) => !r.level);
    const open = stateAll.filter((r) => r.nonprofit_eligible && !r.earmark).length;
    const county = all.length - stateAll.length;
    const shown = narrowed("fl", flEntries);
    const picks = shown.filter((e) => e.tier !== "Long shot");
    return (
      <>
        {tally("fl", `${open.toLocaleString("en-US")} of ${stateAll.length.toLocaleString("en-US")} Florida state programs (fiscal year ${fl.data.fiscalYear}) are open to nonprofits${county ? `, plus ${county} county program${county === 1 ? "" : "s"} with their own windows` : ""}. State programs are not open calls: check each agency's site for the next window.`, shown)}
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
              <li>County programs lose points when your cities are outside the county they serve, or when they require 501(c)(3) status you don't have yet</li>
              <li>Strong is 60 and up, possible is 35 to 59</li>
            </ul>
          </div>
        </details>
        <ResultList name="fl" noun="programs" entries={shown} narrowed={isNarrowed(cur("fl"))} {...markProps}
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

function entriesCsv(items: (Entry & Partial<Pick<Item, "stage" | "stageAt">>)[], withStage = false): string {
  const src = { fed: "Federal grant", fdn: "Foundation", fl: "Florida program" } as const;
  const head = ["source", "score", "tier", "name", "catalog", "details", "deadline_or_size", "reasons", "cautions", "url"];
  return toCsv(withStage ? ["stage", "stage_date", ...head] : head,
    items.map((e) => {
      const row = [src[e.source], e.score, e.tier, e.title, e.catalog, e.facts.join("; "), e.side,
        [...e.fits, ...e.also, ...e.status].join("; "), e.cautions.join("; "), e.url];
      return withStage ? [e.stage ? STAGE_LABEL[e.stage] : "", e.stageAt ? e.stageAt.slice(0, 10) : "", ...row] : row;
    }));
}

function fmtStamp(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleDateString("en-US", { month: "short", day: "2-digit", year: "numeric" });
}

const fmtYmd = (d: string) => fmtDate(new Date(+d.slice(0, 4), +d.slice(5, 7) - 1, +d.slice(8, 10)));
const fmtIso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

function ShortlistPanel({ list, listed }: { list: Shortlist; listed: Listed }) {
  const [confirm, setConfirm] = useState(false);
  const [moved, setMoved] = useState<{ key: string; text: string } | null>(null);
  // Changing a stage moves the entry to another group; keep focus on its stage control there.
  useEffect(() => { if (moved) document.getElementById(`stage-${moved.key}`)?.focus(); }, [moved]);
  if (!list.items.length) {
    return (
      <div class="tally">
        <h2>Your shortlist is empty</h2>
        <p class="quiet">Press Add to shortlist on any result to save it here. Move it to Applying when you start the application, and to Submitted once it is sent, so it stops showing in your results. The shortlist stays in this browser on this device, and nothing is sent anywhere.</p>
      </div>
    );
  }
  const today = new Date();
  const groups = STAGES.map((s) => {
    const items = list.items.filter((e) => e.stage === s.id);
    return { ...s, items: s.id === "submitted" ? [...items].reverse() : byDeadline(items, listed) };
  }).filter((g) => g.items.length);
  const soon = comingUp(list.items, listed, today, 30);
  const ahead = list.items.some((x) => x.stage !== "submitted" && (deadline(x, listed)?.date ?? "") >= fmtIso(today));
  function move(e: Item, s: Stage) {
    list.stage(e.key, s);
    setMoved({ key: e.key, text: s === "submitted" ? "Moved to Submitted. It no longer shows in your results." : `Moved to ${STAGE_LABEL[s]}.` });
  }
  return (
    <>
      <div class="tally">
        <h2><strong>{list.items.length}</strong> on your shortlist</h2>
        <p class="quiet">{groups.map((g) => `${g.items.length} ${g.label.toLowerCase()}`).join(", ")}. Kept in this browser on this device. Scores are from when you added each one.</p>
        <p class="sr-only" role="status">{moved?.text ?? ""}</p>
      </div>
      {soon.length ? (
        <section class="coming-up" aria-labelledby="coming-up-h">
          <h3 id="coming-up-h" class="section-head">Coming up <span class="quiet">(next 30 days)</span></h3>
          <ul>
            {soon.map(({ item, days, d }) => (
              <li key={item.key} class={days < 0 ? "past" : days <= 7 ? "near" : ""}>
                <span class="when">{dueText(days)}</span>
                <a href={`#sl-${item.key}`}>{item.title}</a>
                <span class="quiet">{STAGE_LABEL[item.stage]}{d.own ? ", your deadline" : ""}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      {groups.map((g) => (
        <section class="stage-group" aria-labelledby={`stage-h-${g.id}`} key={g.id}>
          <h3 id={`stage-h-${g.id}`} class="section-head">{g.label} <span class="quiet">({g.items.length})</span></h3>
          {g.id === "submitted" ? <p class="quiet">These no longer show in your results. Set one back to Applying to see it there again.</p> : null}
          <ol class="entries">
            {g.items.map((e) => (
              <li key={e.key}><EntryView e={e} marked onMark={list.toggle} id={`sl-${e.key}`}
                stage={<StagePicker e={e} listed={listed} today={today} onChange={(s) => move(e, s)} onDue={(d) => list.due(e.key, d)} />} /></li>
            ))}
          </ol>
        </section>
      ))}
      <div class="exports">
        {ahead ? (
          <button type="button" class="btn" onClick={() => download("shortlist-deadlines.ics", shortlistIcs(list.items, listed, today), "text/calendar")}>
            <IconDownload />Add shortlist deadlines to your calendar (.ics)
          </button>
        ) : null}
        <button type="button" class="btn" onClick={() => download("shortlist.csv", entriesCsv(list.items, true), "text/csv")}>
          <IconDownload />Download your shortlist (CSV)
        </button>
        {confirm ? (
          <span class="confirm" role="alert">Remove all {list.items.length}?
            <button type="button" class="btn" onClick={() => { list.clear(); setConfirm(false); }}>Clear the shortlist</button>
            <button type="button" class="btn" onClick={() => setConfirm(false)}>Keep it</button>
          </span>
        ) : <button type="button" class="btn quiet-btn" onClick={() => setConfirm(true)}>Clear the shortlist</button>}
      </div>
      {ahead ? <p class="quiet">The calendar file reminds you two weeks and three days before each deadline. Download it again after you change a date.</p> : null}
    </>
  );
}

function StagePicker({ e, listed, today, onChange, onDue }: {
  e: Item; listed: Listed; today: Date; onChange: (s: Stage) => void; onDue: (d: string) => void;
}) {
  const since = STAGES.find((s) => s.id === e.stage)?.since;
  const d = deadline(e, listed);
  const open = e.stage !== "submitted";
  const now = listed.get(e.key);
  return (
    <div class="stage-box">
      <div class="stage-row">
        <label class="stage">Stage<span class="sr-only"> for {e.title}</span>
          <select id={`stage-${e.key}`} value={e.stage} onChange={(ev) => onChange((ev.target as HTMLSelectElement).value as Stage)}>
            {STAGES.map((s) => <option value={s.id} key={s.id}>{s.label}</option>)}
          </select>
        </label>
        {e.stageAt ? <span class="quiet">{since} {fmtStamp(e.stageAt)}</span> : null}
      </div>
      {open ? (
        <div class="stage-row">
          <label class="stage">Your deadline<span class="sr-only"> for {e.title}</span>
            <input type="date" value={e.due ?? ""} onChange={(ev) => onDue((ev.target as HTMLInputElement).value)} />
          </label>
          {d?.date ? (
            <span class={`due${daysUntil(d.date, today) <= 7 ? " near" : ""}`}>{dueText(daysUntil(d.date, today))}{d.own ? "" : ` (${fmtYmd(d.date)})`}</span>
          ) : <span class="quiet">Set a date to see it under Coming up.</span>}
        </div>
      ) : null}
      {open && d?.gone ? (
        <p class="due-note"><IconAlert /><span>No longer listed on Grants.gov. It may have closed or been withdrawn; check the notice.</span></p>
      ) : open && d?.changedFrom && typeof now === "string" ? (
        <p class="due-note"><IconAlert /><span>Grants.gov moved the deadline from {fmtYmd(d.changedFrom)} to {fmtYmd(now)}.</span></p>
      ) : null}
    </div>
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
        <li>County programs are entered by hand from each county's own page, with the date they were checked. Confirm the dates and rules there before you apply.</li>
      </ul>
    </div>
  );
}

function Footer({ coverage }: { coverage: boolean }) {
  return (
    <footer class="footer">
      {coverage ? <CoverageNote /> : null}
      <p>{NOTICE}</p>
      <p>Federal data from the Grants.gov API, refreshed twice a day. Foundation data from IRS Form 990-PF and Form 990 Schedule I e-file returns. Florida data from the Department of Financial Services Catalog of State Financial Assistance, and county programs entered by hand from each program's own page.</p>
      <p>Scores are a starting point for your own review, not a guarantee of eligibility. Matching runs in your browser; your mission and profile are never sent to a server.</p>
      <p>Source code: <a href="https://github.com/RendellRich/grant-matcher">github.com/RendellRich/grant-matcher</a></p>
    </footer>
  );
}
