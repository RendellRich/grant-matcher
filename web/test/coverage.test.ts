import { describe, expect, it } from "vitest";
import { coverageRows, coverageSummary } from "../src/coverage";
import type { Coverage } from "../src/data";

const state = (code: string, registered: number, listed: number, community = 0) => ({
  state: code,
  private: { registered, efiled: Math.round(registered * 0.9), listed, listed_share: registered ? listed / Math.round(registered * 0.9) : null, giving_here: listed * 2 },
  community: { registered: community * 3, efiled: community * 2, listed: community, giving_here: community },
});

const sample: Coverage = {
  made_at: "2026-11-19T09:00+00:00",
  filing_years: [2025, 2026],
  national: {
    private: { registered: 1300, efiled: 1170, listed: 250, listed_share: 0.214 },
    community: { registered: 60, efiled: 40, listed: 20 },
    states_with_data: 2,
  },
  states: [state("AA", 0, 0), state("GU", 10, 0), state("WY", 300, 50, 5), state("FL", 1000, 200, 15), state("VI", 20, 3)],
};

describe("coverage table", () => {
  it("lists states by name, with territories and military addresses in one last row", () => {
    const rows = coverageRows(sample);
    expect(rows.map((r) => r.name)).toEqual(["Florida", "Wyoming", "Territories and military addresses"]);
    expect(rows[2]).toMatchObject({ registered: 30, efiled: 27, listed: 3, share: "11%" });
    expect(rows[1]).toMatchObject({ registered: 300, listed: 50 });  // the shared row's counts never leak into a state's
    expect(rows[0]).toMatchObject({ registered: 1000, efiled: 900, listed: 200, share: "22%", community: 15, giving: 415 });
  });

  it("says the national totals in one sentence", () => {
    expect(coverageSummary(sample)).toBe(
      "1,300 private foundations are registered with the IRS, and 1,170 of them filed a return electronically in 2025 to 2026. "
      + "250 are listed here (21%), with 20 community foundations, public foundations and United Ways, across 2 states and territories.");
  });
});
