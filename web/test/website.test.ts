import { describe, expect, it } from "vitest";
import { narrow, NO_NARROW, websiteFindings, type Entry } from "../src/entries";

const today = new Date(2026, 10, 15);
const at = "2026-11-11";

describe("website findings", () => {
  it("says applications are open, with the deadline and the check date", () => {
    const w = websiteFindings({ s: "open", d: "2027-02-01", q: "We are currently accepting applications.", u: "https://example.org/apply", at }, today);
    expect(w.line).toBe("Its website says applications are open, deadline Feb 01, 2027 (website checked Nov 11)");
    expect(w.due).toBe(new Date(2027, 1, 1).getTime());
    expect(w.rows.map((r) => r.label)).toEqual(["On its website", "Page checked"]);
    expect(w.rows[0].text).toBe("“We are currently accepting applications.”");
  });
  it("gives a deadline only while it is still ahead", () => {
    expect(websiteFindings({ s: "deadline", d: "2027-01-08", at }, today).line).toBe("Its website gives a deadline of Jan 08, 2027 (website checked Nov 11)");
    expect(websiteFindings({ s: "deadline", d: "2026-11-01", at }, today)).toEqual({ rows: [], due: null });
    expect(websiteFindings({ s: "open", d: "2026-11-01", at }, today).due).toBeNull();
  });
  it("turns a closed note into a caution and an apply link into a plain line", () => {
    expect(websiteFindings({ s: "closed", q: "By invitation only.", at }, today).caution).toBe("Its website says it isn't taking new requests now (website checked Nov 11)");
    const a = websiteFindings({ s: "apply", u: "https://x.submittable.com/submit", at }, today);
    expect(a.line).toBe("Its website has an application link (website checked Nov 11)");
    expect(a.rows).toEqual([{ label: "Application link", href: "https://x.submittable.com/submit", linkText: "x.submittable.com/submit" }]);
  });
  it("ignores missing data and unsafe links", () => {
    expect(websiteFindings(undefined, today)).toEqual({ rows: [], due: null });
    expect(websiteFindings({ s: "apply", u: "javascript:alert(1)", at }, today).rows).toEqual([]);
  });
});

describe("open cycle filter", () => {
  const e = (key: string, cycle?: Entry["cycle"]): Entry => ({
    key, source: "fdn", title: key, url: "", catalog: "", facts: [], side: "", score: 50, tier: "Possible",
    fits: [], cautions: [], also: [], status: [], cycle,
  });
  it("keeps foundations whose website is open or gives a deadline", () => {
    const list = [e("a", "open"), e("b", "deadline"), e("c", "closed"), e("d", "apply"), e("f")];
    expect(narrow(list, { ...NO_NARROW, cycle: true }).map((x) => x.key)).toEqual(["a", "b"]);
  });
});
