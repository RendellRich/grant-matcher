// "What the data covers": how many of each state's registered foundations the site holds
// (grantmatch/coverage.py writes data/coverage.json). Opened from the footer, loaded only when asked for.
import { useState } from "preact/hooks";
import { loadCoverage, type Coverage } from "./data";
import { STATE_NAMES } from "./profile";

export interface CoverageRow {
  state: string;
  name: string;
  registered: number;
  efiled: number;
  listed: number;
  share: string;
  giving: number;
  community: number;
}

const num = (v: number) => v.toLocaleString("en-US");
const pct = (v: number | null | undefined) => (v == null ? "" : `${Math.round(v * 100)}%`);

/** One row per state, by name. Places the profile form doesn't offer (territories and military
 * addresses) share one last row. */
export function coverageRows(c: Coverage): CoverageRow[] {
  const rows: CoverageRow[] = [];
  const blank = (state: string, name: string): CoverageRow => ({ state, name, registered: 0, efiled: 0, listed: 0, share: "", giving: 0, community: 0 });
  const other = blank("other", "Territories and military addresses");
  for (const s of c.states) {
    if (!(s.private.registered || s.private.listed || s.community.listed)) continue;
    const named = s.state in STATE_NAMES;
    const row = named ? blank(s.state, STATE_NAMES[s.state]) : other;
    row.registered += s.private.registered;
    row.efiled += s.private.efiled;
    row.listed += s.private.listed;
    row.giving += s.private.giving_here + s.community.giving_here;
    row.community += s.community.listed;
    if (named) rows.push(row);
  }
  rows.sort((a, b) => a.name.localeCompare(b.name));
  if (other.registered || other.listed || other.community) rows.push(other);
  for (const r of rows) r.share = r.efiled ? pct(r.listed / r.efiled) : "";
  return rows;
}

/** The sentence above the table: the national totals in words. */
export function coverageSummary(c: Coverage): string {
  const p = c.national.private;
  const years = c.filing_years.length ? `${c.filing_years[0]} to ${c.filing_years[c.filing_years.length - 1]}` : "the last two years";
  return `${num(p.registered)} private foundations are registered with the IRS, and ${num(p.efiled)} of them filed a return electronically in ${years}. `
    + `${num(p.listed)} are listed here (${pct(p.listed_share)}), with ${num(c.national.community.listed)} community foundations, public foundations and United Ways, `
    + `across ${c.national.states_with_data} states and territories.`;
}

export function CoverageNote() {
  const [data, setData] = useState<Coverage | "loading" | "error" | null>(null);
  function open(ev: Event) {
    if (!(ev.currentTarget as HTMLDetailsElement).open || data) return;
    setData("loading");
    loadCoverage().then(setData).catch(() => setData("error"));
  }
  return (
    <details class="filters coverage" onToggle={open}>
      <summary>What the data covers</summary>
      <div class="coverage-body" aria-live="polite">
        <p>Federal grants cover the whole country. Foundations cover every state. State grants cover Florida, California, Illinois, Iowa, Ohio, Washington (mostly climate and energy), West Virginia, New Jersey, New York, the District of Columbia, Minnesota (two agencies only), Arkansas (arts council only), Maryland (a short list), North Dakota (arts council only) and Wyoming (arts council only); county, city and community foundation programs cover Florida, with a partial hand-kept list for some counties and cities in Arizona, California, Illinois, Nevada, New York, Pennsylvania, Texas and Washington.</p>
        {data === "loading" ? <p>Loading the state-by-state counts.</p> : null}
        {data === "error" ? <p class="error">The state-by-state counts could not be loaded right now.</p> : null}
        {data && typeof data === "object" ? (
          <>
            <p>{coverageSummary(data)}</p>
            <p>A foundation is listed only when its latest return shows grants to organizations and it doesn't say it only funds charities it picks itself, so the listed share is never meant to reach 100%.</p>
            <div class="table-wrap" role="region" aria-label="Foundation coverage by state" tabIndex={0}>
              <table class="coverage-table">
                <thead>
                  <tr>
                    <th scope="col">State</th>
                    <th scope="col" class="n">Registered</th>
                    <th scope="col" class="n">E-filed</th>
                    <th scope="col" class="n">Listed</th>
                    <th scope="col" class="n">Share</th>
                    <th scope="col" class="n">Community</th>
                    <th scope="col" class="n">Giving here</th>
                  </tr>
                </thead>
                <tbody>
                  {coverageRows(data).map((r) => (
                    <tr key={r.state}>
                      <th scope="row">{r.name}</th>
                      <td class="n">{num(r.registered)}</td>
                      <td class="n">{num(r.efiled)}</td>
                      <td class="n">{num(r.listed)}</td>
                      <td class="n">{r.share}</td>
                      <td class="n">{num(r.community)}</td>
                      <td class="n">{num(r.giving)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p>Registered and E-filed count private foundations based in the state, from the IRS Exempt Organizations Business Master File and e-file index. Share is Listed out of E-filed. Community counts listed community foundations, public foundations and United Ways. Giving here counts every listed funder based in the state or with grants there. Counted {data.made_at.slice(0, 10)}.</p>
          </>
        ) : null}
      </div>
    </details>
  );
}
