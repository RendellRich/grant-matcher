import { describe, expect, it } from "vitest";
import { parseProfile } from "../src/profile";

describe("parseProfile budget bands", () => {
  const load = (band: string) => parseProfile(JSON.stringify({ mission: "x", budget_band: band })).budget_band;
  it("keeps the new small bands", () => {
    expect(load("Under $10k")).toBe("Under $10k");
    expect(load("$10k to $50k")).toBe("$10k to $50k");
  });
  it("reads a band saved before the split as $10k to $50k", () => {
    expect(load("Under $50k")).toBe("$10k to $50k");
  });
  it("falls back for an unknown band", () => {
    expect(load("Lots")).toBe("$50k to $250k");
  });
});
