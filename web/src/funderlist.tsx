// "Local funders to ask": the funder directory (funders.ts), below the ranked results and never part of them.
// A disclosure that loads the state's file when first opened.
import { useEffect, useState } from "preact/hooks";
import { loadFunders } from "./data";
import { funderFacts, fundersStatus, nearFunders, type Funder, type FundersMeta } from "./funders";

export const FUNDERS_TITLE = "Local funders to ask";
export const FUNDERS_WARNING = "These are funders to ask, not open grant calls.";
const LONG = 10; // past this, a link skips the list

const longDay = (iso: string) => {
  const d = new Date(`${iso}T12:00:00`);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" });
};
const Sep = () => <><span class="sep" aria-hidden="true"> · </span><span class="sr-only">, </span></>;
const NewTab = () => <span class="sr-only"> (opens in a new tab)</span>;

export interface FundersViewProps {
  rows: Funder[]; // every funder in the state
  near: Funder[] | null; // those near the profile's places; null when it names none
  all: boolean;
  onAll: (all: boolean) => void;
  state: string;
  stateName: string;
  info: FundersMeta;
}

/** The open section's content. No hooks, so it can be read straight in tests. */
export function FundersView(p: FundersViewProps) {
  const shown = p.all ? p.rows : p.near ?? [];
  // Nothing to switch to when the near ones are the whole list.
  const canSwitch = !(p.near && p.near.length === p.rows.length);
  return (
    <>
      <p class="note">
        <strong>{FUNDERS_WARNING}</strong>{" "}
        Each of these local governments gets money from HUD for community development (CDBG) or affordable
        housing (HOME). That doesn't mean it funds nonprofits now: CDBG money for public services is limited and varies
        from place to place. Ask whether, when and how it takes applications. They aren't scored, ranked or counted in
        your matches.
      </p>
      <p class="quiet" role="status">{fundersStatus(p.rows.length, p.near, p.all, p.stateName)}</p>
      {canSwitch ? (
        <p>
          <button type="button" class="btn" onClick={() => p.onAll(!p.all)}>
            {!p.all ? `Show all ${p.rows.length.toLocaleString("en-US")} in ${p.stateName}`
              : p.near?.length ? "Show only the ones near your places" : "Hide the full list"}
          </button>
        </p>
      ) : null}
      {shown.length > LONG ? <a class="skip" href="#funders-source">Skip past the funder list</a> : null}
      {shown.length ? (
        <ul class="entries">
          {shown.map((f) => (
            <li key={f.id}>
              <div class="funder">
                <h3>{f.name}</h3>
                <p class="facts">{funderFacts(f, p.info.fiscal_year).map((fact, i) => <span key={fact}>{i ? <Sep /> : null}{fact}</span>)}</p>
                {f.website ? (
                  <p><a class="funder-site" href={f.website} target="_blank" rel="noopener noreferrer">
                    Website<span class="sr-only"> for {f.name}</span><NewTab />
                  </a></p>
                ) : <p class="quiet funder-none">No website listed.</p>}
              </div>
            </li>
          ))}
        </ul>
      ) : null}
      <p class="quiet" id="funders-source" tabIndex={-1}>
        Sources: <a href={p.info.hud_page} target="_blank" rel="noopener">HUD's FY {p.info.fiscal_year} formula
        allocations<NewTab /></a> (as of {longDay(p.info.hud_as_of)}) and the <a href={p.info.census_page} target="_blank"
        rel="noopener">Census Bureau's {p.info.census_year} Government Units listing<NewTab /></a> (as of{" "}
        {longDay(p.info.census_as_of)}). A website is the one the government reported to the Census Bureau. It isn't
        checked here, so make sure it is the government's own before you rely on it.
        {p.state === "DC" || p.state === "PR" ? ""
          : ` Places not listed may get CDBG money through ${p.stateName}'s own program, which isn't listed here.`}
      </p>
    </>
  );
}

export function Funders(p: { state: string; stateName: string; cities: string; counties: Record<string, string[]> | null; info: FundersMeta }) {
  const [open, setOpen] = useState(false);
  const [rows, setRows] = useState<Funder[] | "error" | null>(null);
  const [all, setAll] = useState(false);
  useEffect(() => {
    if (!open || Array.isArray(rows)) return;
    let live = true;
    setRows(null);
    loadFunders(p.state).then((r) => { if (live) setRows(r); }).catch(() => { if (live) setRows("error"); });
    return () => { live = false; };
  }, [open]);
  return (
    <details class="ready funders" onToggle={(ev) => setOpen((ev.currentTarget as HTMLDetailsElement).open)}>
      <summary><h2>{FUNDERS_TITLE}</h2></summary>
      <div class="funders-body">
        {!open ? null
          : rows === "error" ? <p class="error" role="alert">The funder list could not be loaded. Close this section and open it to try again.</p>
          : !rows ? <p class="loading" role="status">Loading local funders.</p>
          : <FundersView rows={rows} near={nearFunders(rows, p.cities, p.counties)} all={all} onAll={setAll}
              state={p.state} stateName={p.stateName} info={p.info} />}
      </div>
    </details>
  );
}
