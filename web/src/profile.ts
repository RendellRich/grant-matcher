import { BUDGET_BANDS, CATEGORY_NAMES } from "./score";

export const STATE_NAMES: Record<string, string> = {
  AL: "Alabama", AK: "Alaska", AZ: "Arizona", AR: "Arkansas", CA: "California", CO: "Colorado", CT: "Connecticut",
  DC: "District of Columbia", DE: "Delaware", FL: "Florida", GA: "Georgia", HI: "Hawaii", ID: "Idaho", IL: "Illinois",
  IN: "Indiana", IA: "Iowa", KS: "Kansas", KY: "Kentucky", LA: "Louisiana", ME: "Maine", MD: "Maryland",
  MA: "Massachusetts", MI: "Michigan", MN: "Minnesota", MS: "Mississippi", MO: "Missouri", MT: "Montana",
  NE: "Nebraska", NV: "Nevada", NH: "New Hampshire", NJ: "New Jersey", NM: "New Mexico", NY: "New York",
  NC: "North Carolina", ND: "North Dakota", OH: "Ohio", OK: "Oklahoma", OR: "Oregon", PA: "Pennsylvania",
  PR: "Puerto Rico", RI: "Rhode Island", SC: "South Carolina", SD: "South Dakota", TN: "Tennessee", TX: "Texas",
  UT: "Utah", VT: "Vermont", VA: "Virginia", WA: "Washington", WV: "West Virginia", WI: "Wisconsin", WY: "Wyoming",
};
export const STATES = Object.keys(STATE_NAMES).sort((a, b) => STATE_NAMES[a].localeCompare(STATE_NAMES[b]));

export type Status501 = "Yes" | "Pending" | "No";

/** What the person typed. Matches the JSON the Streamlit app saves, so old profile files still load. */
export interface ProfileForm {
  mission: string;
  keywords: string;
  categories: string[];
  state: string;
  cities: string;
  has_501c3: Status501;
  budget_band: string;
  can_cost_share: boolean;
  include_forecasted: boolean;
  min_days_left: number;
}

export const BLANK: ProfileForm = {
  mission: "", keywords: "", categories: [], state: "FL", cities: "", has_501c3: "Yes",
  budget_band: "$50k to $250k", can_cost_share: false, include_forecasted: true, min_days_left: 14,
};

export function sameForm(a: ProfileForm, b: ProfileForm): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

/** Reads a saved profile file; throws when it is not one. */
export function parseProfile(text: string): ProfileForm {
  const d = JSON.parse(text);
  if (!d || typeof d !== "object" || !("mission" in d || "keywords" in d)) throw new Error("not a profile");
  return {
    mission: String(d.mission ?? ""),
    keywords: String(d.keywords ?? ""),
    cities: String(d.cities ?? ""),
    state: d.state in STATE_NAMES ? d.state : "FL",
    has_501c3: ["Yes", "Pending", "No"].includes(d.has_501c3) ? d.has_501c3 : "Yes",
    budget_band: d.budget_band in BUDGET_BANDS ? d.budget_band : "$50k to $250k",
    can_cost_share: Boolean(d.can_cost_share),
    categories: Array.isArray(d.categories) ? d.categories.filter((c: string) => c in CATEGORY_NAMES) : [],
    include_forecasted: d.include_forecasted === undefined ? true : Boolean(d.include_forecasted),
    min_days_left: Number.isFinite(+d.min_days_left) ? Math.max(0, Math.min(60, Math.round(+d.min_days_left))) : 14,
  };
}

export const splitList = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean);
