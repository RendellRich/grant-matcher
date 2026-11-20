// "Can we apply?": the handful of facts that stop a small nonprofit from applying, checked against its profile.
// Each source says different things, so each gets its own reader; a check is left out when the record doesn't say.
// It never changes a score: the scorer's cautions already do that. The card shows these instead of the cautions
// they repeat (see `covered`), and the cautions stay on the entry for the filters and the CSV.
import type { FederalExtra, FederalRec, FloridaRec, FoundationOut, Profile } from "./score";

export type ReadyState = "ok" | "check" | "no";
export interface ReadyCheck {
  key: "501c3" | "sam" | "match" | "pay" | "loan" | "open";
  state: ReadyState;
  label: string; // a few words for the card
  note: string; // one sentence for the details
}
export interface Readiness { checks: ReadyCheck[]; covered: string[] }

/** Profile facts the checks need; anything missing reads as "don't know", which never says you're set. */
export type ReadyProfile = Pick<Profile, "has501c3" | "canCostShare"> & Partial<Pick<Profile, "fiscalSponsor" | "registrations" | "today">>;

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const shortDate = (d: Date) => `${MONTHS[d.getMonth()]} ${d.getDate()}, ${d.getFullYear()}`;
const ymd = (s?: string | null) => (s && /^\d{4}-\d{2}-\d{2}$/.test(s) ? new Date(+s.slice(0, 4), +s.slice(5, 7) - 1, +s.slice(8, 10)) : null);
const dayStart = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();

// Words in a program's own text. A "no match required" line wins over the word "match" elsewhere.
const NO_MATCH = /\bno (?:cash |local )?match(?:ing)?(?: funds?)?(?: is| are)? required\b|\bno match(?:ing)?(?: fund)? requirements?\b|\bno match required\b/i;
const MATCH = /\b(?:cash|in-kind|local|dollar-for-dollar|\d{1,3} ?%)\s+match\b|\bmatching (?:funds?|requirement|contribution)s?\b|\bmatch (?:is |are )?required\b|\brequires? (?:a )?(?:cash )?match\b|\bcost[- ]shar(?:e|ing)\b/i;
const REIMBURSE = /\breimburs(?:e|ed|es|ing|ement|ements|able)\b/i;
const ADVANCE = /\b(?:paid|payment|funds?) (?:in )?advance\b|\badvance payments?\b/i;
const SAM = /\bSAM\.gov\b|\bUnique Entity (?:ID|Identifier)\b|\bUEI\b/;
const MUST_501 = /must (?:be|have) (?:a )?(?:registered )?501\s*\(?c\)?\s*\(?3\)?|501\s*\(?c\)?\s*\(?3\)?\s*(?:status )?(?:is )?required|only (?:to )?501\s*\(?c\)?\s*\(?3\)?/i;

function need501(required: boolean | null, p: ReadyProfile, where: string): ReadyCheck | null {
  if (required === null) return null;
  if (!required) {
    return { key: "501c3", state: "ok", label: "No 501(c)(3) needed", note: `${where} doesn't require 501(c)(3) status.` };
  }
  if (p.has501c3 === "Yes") return { key: "501c3", state: "ok", label: "501(c)(3): you have it", note: `${where} requires 501(c)(3) status, and your profile says you have it.` };
  if (p.fiscalSponsor) {
    return { key: "501c3", state: "check", label: "501(c)(3) via sponsor", note: `${where} requires 501(c)(3) status; ask whether you can apply through your fiscal sponsor.` };
  }
  return p.has501c3 === "Pending"
    ? { key: "501c3", state: "check", label: "501(c)(3) pending", note: `${where} requires 501(c)(3) status; apply once your IRS letter arrives.` }
    : { key: "501c3", state: "no", label: "Needs 501(c)(3)", note: `${where} requires 501(c)(3) status, which your profile says you don't have.` };
}

function samCheck(p: ReadyProfile, why: string): ReadyCheck {
  return p.registrations?.includes("sam")
    ? { key: "sam", state: "ok", label: "SAM.gov: registered", note: `${why} Your profile says you're registered; make sure it hasn't lapsed (it renews yearly).` }
    : { key: "sam", state: "check", label: "Needs SAM.gov", note: `${why} A new registration can take several weeks, so start early.` };
}

/** A required match against the profile; `none` is the sentence for when nothing is required. */
function matchCheck(required: boolean, p: ReadyProfile, none: string, detail = ""): ReadyCheck {
  if (!required) return { key: "match", state: "ok", label: "No match required", note: none };
  const what = detail ? ` (${detail})` : "";
  return p.canCostShare
    ? { key: "match", state: "ok", label: "Match: you can", note: `Matching funds are required${what}, and your profile says you can provide them.` }
    : { key: "match", state: "no", label: "Match required", note: `Matching funds are required${what}; your profile says you can't provide them.` };
}

const REIMBURSE_CHECK: ReadyCheck = {
  key: "pay", state: "check", label: "Paid by reimbursement",
  note: "It pays by reimbursement: you spend your own money first and are paid back, so plan your cash before you apply.",
};

/** A program's own words, for sources that only have text. */
function fromText(text: string, p: ReadyProfile): ReadyCheck[] {
  const out: ReadyCheck[] = [];
  if (SAM.test(text)) out.push(samCheck(p, "Its text mentions SAM.gov registration."));
  if (NO_MATCH.test(text)) out.push(matchCheck(false, p, "Its text says no matching funds are required."));
  else if (MATCH.test(text)) out.push(matchCheck(true, p, "", "its text mentions a match"));
  if (REIMBURSE.test(text)) out.push(REIMBURSE_CHECK);
  else if (ADVANCE.test(text)) out.push({ key: "pay", state: "ok", label: "Paid in advance", note: "Its text says funds are paid in advance." });
  return out;
}

const startsAny = (x: string, prefixes: string[]) => prefixes.some((pre) => x.startsWith(pre));
const covers = (lines: string[], prefixes: string[]) => lines.filter((x) => startsAny(x, prefixes));

const C501 = ["Requires 501(c)(3) status", "Asks for proof of 501(c)(3) status"];
const CMATCH = ["Requires cost sharing", "Requires matching funds"];
const CPAY = ["Pays by reimbursement"];
const CLOAN = ["A loan, not a grant"];

/** The lines a check already says, so the card doesn't say them twice. */
function coveredBy(checks: ReadyCheck[], lines: string[]): string[] {
  const keys = new Set(checks.map((c) => c.key));
  return [
    ...(keys.has("501c3") ? covers(lines, C501) : []),
    ...(keys.has("match") ? covers(lines, CMATCH) : []),
    ...(keys.has("pay") ? covers(lines, CPAY) : []),
    ...(keys.has("loan") ? covers(lines, CLOAN) : []),
  ];
}

// ---------- federal ----------

export function federalReadiness(r: FederalRec & Partial<FederalExtra>, p: ReadyProfile, lines: string[] = []): Readiness {
  const types = new Set(r.applicant_types ?? []);
  const checks: ReadyCheck[] = [];
  // Grants.gov codes: 12 is 501(c)(3) nonprofits, 13 nonprofits without it, 25 "other", 99 anyone.
  const only501 = types.has("12") && !["13", "25", "99"].some((t) => types.has(t));
  const open = types.has("13") || types.has("99");
  const c501 = need501(only501 ? true : open ? false : null, p, "This opportunity");
  if (c501) checks.push(c501);
  checks.push(samCheck(p, "Every federal grant needs an active SAM.gov registration and a UEI."));
  checks.push(matchCheck(Boolean(r.cost_sharing), p, "Grants.gov lists no cost sharing or matching requirement.", "cost sharing"));
  const close = r.close ?? null;
  if (r.status === "forecasted") {
    checks.push({ key: "open", state: "check", label: "Not open yet", note: "This is a forecast: the agency expects to post it, but you can't apply until it does." });
  } else {
    checks.push({ key: "open", state: "ok", label: "Open now", note: close ? `Open on Grants.gov; due ${shortDate(close)}.` : "Open on Grants.gov with no close date listed." });
  }
  return { checks, covered: [...coveredBy(checks, lines), ...lines.filter((x) => x.startsWith("Forecast, not open yet"))] };
}

// ---------- state, county and city programs ----------

export function floridaReadiness(r: FloridaRec, p: ReadyProfile, lines: string[] = []): Readiness {
  const local = Boolean(r.level);
  const call = Boolean(r.status);
  const text = [r.applicant_types, r.application, r.award, r.restrictions, r.deadlines].filter((x) => typeof x === "string").join(" \n ");
  const checks: ReadyCheck[] = [];
  const where = local ? "This program" : call ? "This call" : "This program";
  const c501 = need501(local ? r.requires_501c3 === true : MUST_501.test(r.applicant_types ?? "") ? true : null, p, where);
  if (c501) checks.push(c501);
  if (call) {
    // California's portal says these outright: a required match, a loan, and how the money is paid.
    if (SAM.test(text)) checks.push(samCheck(p, "Its text mentions SAM.gov registration."));
    const match = typeof r.match === "string" ? r.match : "";
    checks.push(matchCheck(Boolean(match), p, "The state portal lists no matching funds requirement.", match));
    if (r.loan === true) checks.push({ key: "loan", state: "no", label: "A loan, not a grant", note: "This is a loan you repay, not a grant." });
    const how = typeof r.funding_method === "string" ? r.funding_method : "";
    if (how.startsWith("Reimbursement")) checks.push(REIMBURSE_CHECK);
    else if (/^Advance/i.test(how) && /Reimburse/i.test(how)) {
      checks.push({ key: "pay", state: "ok", label: "Advance or reimbursement", note: "The state portal says it pays by advance or reimbursement; ask which applies to you." });
    } else if (/^Advance/i.test(how)) checks.push({ key: "pay", state: "ok", label: "Paid in advance", note: "The state portal says it pays in advance." });
  } else {
    checks.push(...fromText(text, p));
  }
  checks.push(windowCheck(r, local, call, p.today ?? new Date()));
  const status = ["Taking applications now", "Taking applications with no set deadline", "Applications open "];
  return { checks, covered: [...coveredBy(checks, lines), ...lines.filter((x) => startsAny(x, status))] };
}

function windowCheck(r: FloridaRec, local: boolean, call: boolean, today: Date): ReadyCheck {
  const t0 = dayStart(today);
  const opens = ymd(r.opens), closes = ymd(r.closes);
  if (opens && opens.getTime() > t0) {
    return { key: "open", state: "check", label: `Opens ${shortDate(opens)}`, note: `Applications open ${shortDate(opens)}${closes ? ` and close ${shortDate(closes)}` : ""}.` };
  }
  if (closes && closes.getTime() >= t0) return { key: "open", state: "ok", label: "Open now", note: `Taking applications now; due ${shortDate(closes)}.` };
  if (call && r.deadlines === "Ongoing") return { key: "open", state: "ok", label: "Open, no deadline", note: "Taking applications with no set deadline." };
  if (local) {
    return { key: "open", state: "check", label: "Between rounds", note: "No application window is open now; the Deadlines line says when the next round is expected." };
  }
  if (call) return { key: "open", state: "check", label: "Check the dates", note: "The portal lists no open window; read the Deadlines line." };
  return { key: "open", state: "check", label: "Ask when it funds", note: "The state catalog lists programs, not open calls: ask the agency when it next takes applications." };
}

// ---------- foundations ----------

const PRESELECTED = "Says it only funds preselected organizations";
const UNSOLICITED = "Says it does not accept unsolicited requests";
const SITE_CLOSED = "Its website says it isn't taking new requests";

export function foundationReadiness(r: FoundationOut, p: ReadyProfile, asks501: boolean, publishesApply: boolean, lines: string[] = []): Readiness {
  const checks: ReadyCheck[] = [];
  // Private foundations give almost entirely to 501(c)(3) public charities, whatever their return says.
  if (asks501) {
    const c = need501(true, p, "This foundation");
    if (c) checks.push({ ...c, note: c.note.replace("requires 501(c)(3) status", "asks for proof of 501(c)(3) status") });
  } else if (p.has501c3 !== "Yes") {
    checks.push({
      key: "501c3", state: "check", label: p.fiscalSponsor ? "501(c)(3) via sponsor" : "501(c)(3) usually expected",
      note: "Most foundations give only to 501(c)(3) charities, even when their return doesn't say so; ask before you apply.",
    });
  }
  const cycle = r._cycle?.s;
  if (lines.some((x) => x.startsWith(PRESELECTED))) {
    checks.push({ key: "open", state: "no", label: "Invitation only", note: "Its return says it only funds preselected organizations; a short introduction letter is the most you can send." });
  } else if (lines.some((x) => x.startsWith(UNSOLICITED))) {
    checks.push({ key: "open", state: "no", label: "No unsolicited requests", note: "Its return says it doesn't accept unsolicited requests." });
  } else if (cycle === "closed") {
    checks.push({ key: "open", state: "no", label: "Not taking requests", note: "Its website said it isn't taking new requests at the last weekly check." });
  } else if (cycle === "open" || cycle === "deadline") {
    checks.push({ key: "open", state: "ok", label: "Taking applications", note: "Its website said applications are open at the last weekly check." });
  } else if (publishesApply) {
    checks.push({ key: "open", state: "ok", label: "Says how to apply", note: "Its return lists how to apply." });
  } else {
    checks.push({ key: "open", state: "check", label: "No process listed", note: "Its return lists no way to apply; look for a website or call before writing." });
  }
  const covered = [...coveredBy(checks, lines), ...lines.filter((x) => startsAny(x, [PRESELECTED, UNSOLICITED, SITE_CLOSED]))];
  return { checks, covered };
}

/** One line for screen readers and the details: how many checks need a look. */
export function readySummary(checks: ReadyCheck[]): string {
  const no = checks.filter((c) => c.state === "no").length;
  const check = checks.filter((c) => c.state === "check").length;
  if (no) return `${no} ${no === 1 ? "thing stops" : "things stop"} you${check ? `, ${check} to check` : ""}`;
  if (check) return `${check} ${check === 1 ? "thing" : "things"} to check`;
  return "Nothing in the way that we can see";
}
