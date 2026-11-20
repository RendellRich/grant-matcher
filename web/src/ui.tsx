import { useEffect, useRef, useState } from "preact/hooks";
import type { Entry } from "./entries";
import { readySummary, type ReadyCheck } from "./ready";
import { download } from "./exports";
import { grantSummary, summaryFileName } from "./summary";

// ---------- icons: one stroke family, 1.75px at 20px ----------

const Svg = (p: { d: string; size?: number }) => (
  <svg class="icon" width={p.size ?? 18} height={p.size ?? 18} viewBox="0 0 24 24" fill="none" stroke="currentColor"
       stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">
    <path d={p.d} />
  </svg>
);
export const IconCheck = () => <Svg d="M5 12.5l4.5 4.5L19 7.5" />;
export const IconAlert = () => <Svg d="M12 3.5 2.5 20h19L12 3.5zM12 10v4.5M12 17.5v.01" />;
export const IconClock = () => <Svg d="M12 3.5a8.5 8.5 0 1 0 0 17 8.5 8.5 0 0 0 0-17zM12 7.5V12l3 2" />;
export const IconInfo = () => <Svg d="M12 3.5a8.5 8.5 0 1 0 0 17 8.5 8.5 0 0 0 0-17zM12 11v5M12 8v.01" />;
export const IconMark = (p: { on: boolean }) => (
  <svg class="icon" width="18" height="18" viewBox="0 0 24 24" fill={p.on ? "currentColor" : "none"} stroke="currentColor"
       stroke-width="2" stroke-linejoin="round" aria-hidden="true" focusable="false">
    <path d="M6.5 3.5h11v17l-5.5-4-5.5 4z" />
  </svg>
);
export const IconDownload = () => <Svg d="M12 4v11M7 10.5l5 5 5-5M5 19.5h14" />;
export const IconExternal = () => <Svg size={14} d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" />;

const TIER_LABEL = { Strong: "Strong match", Possible: "Possible match", "Long shot": "Long shot" } as const;

/** The signature: every entry on the same 0 to 100 scale, with the 35 and 60 marks. */
export function ScoreRule(p: { score: number; tier: Entry["tier"] }) {
  return (
    <span class={`score tier-${p.tier.split(" ")[0].toLowerCase()}`}>
      <span class="tier">{TIER_LABEL[p.tier]}</span>
      <span class="sr-only">, </span>
      <span class="rule" aria-hidden="true">
        <span class="fill" style={{ width: `${p.score}%` }} />
        <span class="mark m35" />
        <span class="mark m60" />
      </span>
      <span class="num"><span class="sr-only">Score </span>{p.score}<span class="sr-only"> of 100</span></span>
    </span>
  );
}

/** How the mark button reads when it does something other than the shortlist (in ETO: send to the pipeline). */
export interface MarkAction {
  label: (e: Entry, marked: boolean) => string;
  busy?: Set<string>; // keys waiting for an answer
}

export function EntryView(p: {
  e: Entry; marked: boolean; onMark: (e: Entry) => void; id?: string; stage?: preact.ComponentChildren; action?: MarkAction;
}) {
  const { e } = p;
  // Lines the "Can we apply?" checks already say stay off the card (the filters still read them).
  const covered = new Set(e.covered ?? []);
  const cautions = e.cautions.filter((x) => !covered.has(x));
  const statusAll = e.status.filter((x) => !covered.has(x));
  // Fits and cautions always show. The other lines fill up to MAX_WHY rows, dated and history lines first; the rest wait in the details.
  const room = Math.max(0, MAX_WHY - e.fits.length - cautions.length - (e.ready?.length ? 1 : 0));
  const status = statusAll.slice(0, room);
  const also = e.also.slice(0, room - status.length);
  const rest = [...e.also.slice(also.length), ...statusAll.slice(status.length)];
  return (
    <article class="entry" aria-labelledby={`t-${e.key}`}>
      <div class="entry-top">
        {/* The title comes first in reading order so heading navigation lands on it; CSS shows the score above it. */}
        <h3 class="entry-title" id={`t-${e.key}`}>
          {e.url ? (
            <a id={p.id} href={e.url} target="_blank" rel="noopener">{e.title}<span class="sr-only"> (opens in a new tab)</span></a>
          ) : <span id={p.id} tabIndex={-1}>{e.title}</span>}
        </h3>
        <div class="entry-head">
          <span class="head-score">
            <ScoreRule score={e.score} tier={e.tier} />
            {e.isNew ? <span class="tag-new">New<span class="sr-only"> since your last visit</span></span> : null}
          </span>
          {e.side ? <span class={`side${e.sideQuiet ? " quiet" : ""}`}>{e.side}</span> : null}
        </div>
      </div>
      <p class="facts">
        <span class="catalog">{e.catalog}</span>
        {e.facts.map((f) => <span class="fact" key={f}><span class="sep" aria-hidden="true"> · </span><span class="sr-only">, </span>{f}</span>)}
      </p>
      <ul class="why">
        {e.fits.map((x) => <li class="good" key={x}><IconCheck /><span><span class="sr-only">Fits: </span>{x}</span></li>)}
        {cautions.map((x) => <li class="warn" key={x}><IconAlert /><span><span class="sr-only">Caution: </span>{x}</span></li>)}
        {also.map((x) => <li class="also" key={x}><IconInfo /><span><span class="sr-only">Also: </span>{x}</span></li>)}
        {status.map((x) => <li class="also" key={x}><IconClock /><span><span class="sr-only">Status: </span>{x}</span></li>)}
      </ul>
      {e.ready?.length ? <ReadyLine checks={e.ready} id={`r-${e.key}`} /> : null}
      {p.stage}
      <div class="entry-actions">
        {p.action ? (
          // Sending can't be undone from here, so this is a plain button that stops once the grant is in the pipeline.
          <button type="button" class={`mark-btn${p.marked ? " on" : ""}`} disabled={p.marked || p.action.busy?.has(e.key)}
                  onClick={() => p.onMark(e)}>
            <IconMark on={p.marked} />{p.action.busy?.has(e.key) ? "Sending" : p.action.label(e, p.marked)}
            <span class="sr-only">: {e.title}</span>
          </button>
        ) : (
          <button type="button" class={`mark-btn${p.marked ? " on" : ""}`} aria-pressed={p.marked} onClick={() => p.onMark(e)}>
            <IconMark on={p.marked} />{p.marked ? "On shortlist" : "Add to shortlist"}
            <span class="sr-only">: {e.title}</span>
          </button>
        )}
        <Details e={e} rest={rest} />
      </div>
    </article>
  );
}

const MAX_WHY = 6;

const SR: Record<ReadyCheck["state"], string> = { ok: "Fine: ", check: "Check: ", no: "Stops you: " };

/** "Can we apply?" on the card: a few words per check on one wrapping line; the details give the sentences. */
function ReadyLine({ checks, id }: { checks: ReadyCheck[]; id: string }) {
  return (
    <div class="can-apply">
      <span class="can-apply-head" id={id}>Can we apply?<span class="sr-only"> {readySummary(checks)}.</span></span>
      <ul aria-labelledby={id}>
        {checks.map((c) => (
          <li class={`ca-${c.state}`} key={c.key}>{c.state === "ok" ? <IconCheck /> : <IconAlert />}
            <span><span class="sr-only">{SR[c.state]}</span>{c.label}</span></li>
        ))}
      </ul>
    </div>
  );
}

function Details({ e, rest }: { e: Entry; rest: string[] }) {
  const label = e.source === "fdn" ? "How to apply and past grants" : e.source === "fed" ? "Summary" : "Details";
  return (
    <details class="more">
      <summary>{label}<span class="sr-only"> for {e.title}</span></summary>
      <div class="more-body">
        {e.ready?.length ? (
          <>
            <p class="sub">Can we apply? {readySummary(e.ready)}</p>
            <ul class="why">
              {e.ready.map((c) => (
                <li class={c.state === "ok" ? "good" : "warn"} key={c.key}>{c.state === "ok" ? <IconCheck /> : <IconAlert />}
                  <span><span class="sr-only">{SR[c.state]}</span>{c.note}</span></li>
              ))}
            </ul>
          </>
        ) : null}
        {rest.length ? (
          <ul class="why">
            {rest.map((x) => <li class="also" key={x}><IconInfo /><span><span class="sr-only">Also: </span>{x}</span></li>)}
          </ul>
        ) : null}
        {e.summary ? <p class="summary">{e.summary}</p> : null}
        {e.eligibility ? <p class="summary"><strong>Eligibility notes:</strong> {e.eligibility}</p> : null}
        {e.noApplyInfo ? <p class="quiet">No application details listed on the return.</p> : null}
        {e.rows?.length ? (
          <dl class="rows">
            {e.rows.map((r) => [
              <dt key={r.label + "t"}>{r.label}</dt>,
              <dd key={r.label + "d"}>{r.href
                ? <a href={r.href} target={r.href.startsWith("http") ? "_blank" : undefined} rel="noopener">{r.linkText}</a>
                : r.text}</dd>,
            ])}
          </dl>
        ) : null}
        {e.grants?.length ? (
          <>
            <p class="sub">Largest grants ({e.grantsWhere})</p>
            <ul class="grants">
              {e.grants.map((g, i) => (
                <li key={i}><strong>{g.to}</strong><span class="sep" aria-hidden="true"> · </span><span class="sr-only">, </span>
                  <span class="nowrap">{g.place}</span><span class="sep" aria-hidden="true"> · </span><span class="sr-only">, </span>
                  <span class="num">{g.amount}</span>
                  {g.purpose ? <><span class="sep" aria-hidden="true"> · </span><span class="sr-only">, </span>{g.purpose}</> : null}
                </li>
              ))}
            </ul>
          </>
        ) : null}
        {e.source === "fed" && e.url ? (
          <p><a href={e.url} target="_blank" rel="noopener">Read the full notice on Grants.gov<span class="sr-only"> (opens in a new tab)</span></a></p>
        ) : null}
        <SummaryActions e={e} />
      </div>
    </details>
  );
}

/** A one-page summary for a grant writer: copy it to paste anywhere, or download it as a text file. */
function SummaryActions({ e }: { e: Entry }) {
  const [said, setSaid] = useState("");
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(grantSummary(e));
      setSaid("Copied. Paste it into your document.");
    } catch {
      setSaid("Your browser blocked copying; download it instead.");
    }
  };
  return (
    <div class="summary-actions">
      <button type="button" class="btn" onClick={copy}>Copy one-page summary<span class="sr-only"> of {e.title}</span></button>
      <button type="button" class="btn quiet-btn" onClick={() => download(summaryFileName(e), grantSummary(e), "text/plain")}>
        <IconDownload />Download as text<span class="sr-only">: {e.title}</span>
      </button>
      <span class="quiet" role="status">{said}</span>
    </div>
  );
}

const PAGE = 40;
const FIRST_POSSIBLE = 10;

/** Strong matches (up to 40) and the first 10 possible ones, then 40 more at a time; long shots behind a switch. */
export function ResultList(p: {
  name: string; noun: string; entries: Entry[]; marked: Set<string>; onMark: (e: Entry) => void; action?: MarkAction;
  sorts?: [string, ((a: Entry, b: Entry) => number) | null][]; exports?: preact.ComponentChildren; narrowed?: boolean;
  /** A preview's few results: the lock below says what else there is, so the list doesn't count itself. */
  preview?: boolean;
}) {
  const [sortIdx, setSortIdx] = useState(0);
  const good0 = p.entries.filter((e) => e.tier !== "Long shot");
  const longs = p.entries.filter((e) => e.tier === "Long shot").slice(0, 20);
  const cmp = p.sorts?.[sortIdx]?.[1];
  const good = cmp ? [...good0].sort(cmp) : good0;
  const nStrong = good.filter((e) => e.tier === "Strong").length;
  const first = Math.min(nStrong, PAGE) + FIRST_POSSIBLE;
  const [shown, setShown] = useState(first);
  const [jump, setJump] = useState(0);
  const [announce, setAnnounce] = useState(false);
  const [showLongs, setShowLongs] = useState(false);
  const listKey = good.map((e) => e.key).join("|");
  const prevKey = useRef(listKey);
  useEffect(() => {
    if (prevKey.current !== listKey) { setShown(first); setJump(0); setAnnounce(false); prevKey.current = listKey; }
  }, [listKey, first]);
  useEffect(() => {
    if (jump) document.getElementById(`${p.name}-r${jump}`)?.focus();
  }, [jump, p.name]);
  const n = Math.min(shown, good.length);
  const more = Math.min(PAGE, good.length - n);

  return (
    <div class="results">
      {good.length === 0 ? (
        <p class="empty">{p.narrowed
          ? `No strong or possible ${p.noun} match your search and filters. Clear filters to see more.`
          : `No strong or possible ${p.noun} for this profile yet. Try more specific key words, or look through the long shots below.`}</p>
      ) : (
        <>
          <div class="list-tools">
            <a class="skip" href={`#${p.name}-end`}>Skip past these {p.noun}</a>
            {p.sorts ? (
              <label class="sort">Sort by
                <select value={sortIdx} onChange={(ev) => setSortIdx(+(ev.target as HTMLSelectElement).value)}>
                  {p.sorts.map(([label], i) => <option value={i} key={label}>{label}</option>)}
                </select>
              </label>
            ) : null}
          </div>
          <ol class="entries">
            {good.slice(0, n).map((e, i) => (
              <li key={e.key}><EntryView e={e} marked={p.marked.has(e.key)} onMark={p.onMark} action={p.action} id={`${p.name}-r${i + 1}`} /></li>
            ))}
          </ol>
          {p.preview ? null : <div class="list-end">
            <p id={`${p.name}-end`} tabIndex={-1} class="count" role={announce ? "status" : undefined}>
              {n < good.length
                ? `Showing the top ${n.toLocaleString("en-US")} of ${good.length.toLocaleString("en-US")} strong and possible ${p.noun}.`
                : `Showing all ${good.length.toLocaleString("en-US")} strong and possible ${p.noun}.`}
            </p>
            {n < good.length ? (
              <button type="button" class="btn" onClick={() => { setShown(n + more); setJump(n + 1); setAnnounce(true); }}>
                Show {more} more
              </button>
            ) : good.length > first ? (
              <button type="button" class="btn" onClick={() => { setShown(first); setJump(0); setAnnounce(true); }}>
                Show the first {first} again
              </button>
            ) : null}
          </div>}
          {p.exports}
        </>
      )}
      {longs.length ? (
        <section class="longs" aria-labelledby={`${p.name}-longs`}>
          <h3 id={`${p.name}-longs`} class="section-head">Long shots <span class="quiet">({p.entries.filter((e) => e.tier === "Long shot").length.toLocaleString("en-US")})</span></h3>
          <p class="quiet">These fit on a few points and miss on others. Read the cautions before spending time on one.</p>
          <button type="button" class="btn" aria-expanded={showLongs} onClick={() => setShowLongs(!showLongs)}>
            {showLongs ? "Hide the long shots" : `Show the top ${longs.length} long shots`}
          </button>
          {showLongs ? (
            <ol class="entries">
              {longs.map((e) => <li key={e.key}><EntryView e={e} marked={p.marked.has(e.key)} onMark={p.onMark} action={p.action} /></li>)}
            </ol>
          ) : null}
        </section>
      ) : null}
    </div>
  );
}
