---
name: Grant Matcher
description: A calm, plain search tool that shows small nonprofits which grants fit and why.
colors:
  evergreen: "#2f6f5e"
  evergreen-night: "#6cc0a5"
  on-evergreen-night: "#121715"
  paper: "#ffffff"
  mist: "#f4f6f5"
  ink: "#1c2421"
  slate: "#4b5753"
  rule: "#d5ddd9"
  control-edge: "#7d8984"
  caution-amber: "#8a5a00"
  strong-tint: "#e2f1e9"
  strong-ink: "#17543f"
  long-tint: "#edf0ef"
  long-ink: "#3b4744"
  night: "#121715"
  night-surface: "#1b2220"
  night-ink: "#e6ebe9"
  night-slate: "#a7b2ae"
  night-rule: "#34403b"
  control-edge-night: "#6a7a75"
  caution-amber-night: "#e0b45a"
  strong-tint-night: "#173a2d"
  strong-ink-night: "#a9e3c6"
  long-tint-night: "#252d2a"
  long-ink-night: "#c6cfcb"
typography:
  display:
    fontFamily: "Source Sans, sans-serif"
    fontSize: "clamp(1.75rem, 1.3rem + 1.6vw, 2.25rem)"
    fontWeight: 650
    lineHeight: 1.2
    letterSpacing: "-0.01em"
  headline:
    fontFamily: "Source Sans, sans-serif"
    fontSize: "1.5625rem"
    fontWeight: 400
    lineHeight: 1.25
  title:
    fontFamily: "Source Sans, sans-serif"
    fontSize: "1.25rem"
    fontWeight: 600
    lineHeight: 1.35
  lead:
    fontFamily: "Source Sans, sans-serif"
    fontSize: "1.0625rem"
    fontWeight: 400
    lineHeight: 1.55
  body:
    fontFamily: "Source Sans, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.5
  detail:
    fontFamily: "Source Sans, sans-serif"
    fontSize: "0.9375rem"
    fontWeight: 400
    lineHeight: 1.5
  meta:
    fontFamily: "Source Sans, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "Source Sans, sans-serif"
    fontSize: "0.8125rem"
    fontWeight: 600
    lineHeight: 1.5
rounded:
  md: "8px"
  pill: "999px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "20px"
  section: "24px"
components:
  button:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    height: "44px"
  button-night:
    backgroundColor: "{colors.night}"
    textColor: "{colors.night-ink}"
    rounded: "{rounded.md}"
    height: "44px"
  input:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    borderColor: "{colors.control-edge}"
    rounded: "{rounded.md}"
    height: "44px"
  button-primary:
    backgroundColor: "{colors.evergreen}"
    textColor: "{colors.paper}"
    rounded: "{rounded.md}"
    height: "44px"
  button-primary-night:
    backgroundColor: "{colors.evergreen-night}"
    textColor: "{colors.on-evergreen-night}"
    rounded: "{rounded.md}"
    height: "44px"
  result-card:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    padding: "18px 20px 8px"
  badge-strong:
    backgroundColor: "{colors.strong-tint}"
    textColor: "{colors.strong-ink}"
    typography: "{typography.label}"
    rounded: "{rounded.pill}"
    padding: "2px 10px"
  badge-possible:
    textColor: "{colors.evergreen}"
    typography: "{typography.label}"
    rounded: "{rounded.pill}"
    padding: "2px 10px"
  badge-long:
    backgroundColor: "{colors.long-tint}"
    textColor: "{colors.long-ink}"
    typography: "{typography.label}"
    rounded: "{rounded.pill}"
    padding: "2px 10px"
  note:
    backgroundColor: "{colors.mist}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    padding: "10px 14px"
  tab:
    textColor: "{colors.ink}"
    height: "44px"
  tab-selected:
    textColor: "{colors.evergreen}"
    height: "44px"
---

# Design System: Grant Matcher

## Overview

**Creative North Star: "The Honest Ledger"**

Grant Matcher shows its working. Every result carries its reasons and its cautions side by side, a plain score, and the source it came from, the way a careful bookkeeper writes notes next to each line. The visitor is a small-nonprofit staffer, often without grant-writing experience. They should finish a visit knowing which funders to approach first and why, without being sold anything.

The surface is a task tool, so the look is quiet and dense in information rather than in decoration. Flat paper and mist surfaces, thin rules, one evergreen accent, and the stock Source Sans face. Expression lives in precise details: the drawn check, caution and clock icons; the dot-separated meta line; the outlined "Possible match" badge; a focus ring that always shows. Light and dark follow the visitor's system setting and are tuned separately, never inverted.

The page leads with the answer. An overview line counts strong matches across all sources, tabs are ordered by where those matches are, and each tab opens with its own tally before any filters.

**Key Characteristics:**
- Plain and sturdy: flat surfaces, 1px rules, 44px targets, nothing decorative.
- One accent, used for action and fit; amber only for cautions.
- Every claim on a card is a sentence a person can check.
- The same order on every tab: tally, source, one expander for filters and scoring, then cards.
- Raw source data is tidied for reading, never rewritten.

## Colors

A cool, near-neutral paper palette with one evergreen accent and a single amber reserved for warnings.

### Primary
- **Evergreen** (light `evergreen`, dark `evergreen-night`): the one accent. Selected tab underline, the check icon on reasons that fit, the "Possible match" badge outline, focus rings, link hover, radio and toggle fills. Never a large fill behind text.

### Neutral
- **Paper** and **Night** (`paper`, `night`): page backgrounds.
- **Mist** and **Night surface** (`mist`, `night-surface`): the sidebar, notes and info boxes. Tonal layering instead of shadow.
- **Ink** and **Night ink** (`ink`, `night-ink`): body text, titles, and links (links are ink with an underline, not a second colour).
- **Slate** and **Night slate** (`slate`, `night-slate`): meta lines, captions, notices, the score, details labels and placeholders. Passes AA on every surface it sits on.
- **Rule** and **Night rule** (`rule`, `night-rule`): card borders, dividers between card body and expander, tab baseline, footer rule. Decorative only, so it may sit below 3:1.
- **Control edge** (`control-edge`, `control-edge-night`): the edge of anything you type into or toggle: text fields, selects, the file drop zone, unchecked boxes and radios, the off track of a toggle. At least 3:1 against both paper and mist (WCAG 1.4.11).

### Status
- **Caution amber** (`caution-amber`, `caution-amber-night`): the caution icon on card reasons only. Not used for badges, buttons or decoration.
- **Strong tint and ink** (`strong-tint`, `strong-ink` and night pair): the filled "Strong match" badge.
- **Long tint and ink** (`long-tint`, `long-ink` and night pair): the "Long shot" badge and the neutral multiselect chips.

### Named Rules
**The Ten Possible Rule.** Possible matches (35 to 59) are a long tail. Show ten after the strong ones and let the visitor ask for more; never open with hundreds.

**The One Voice Rule.** Evergreen is the only hue that signals fit or action. If a second colour starts carrying meaning, it is wrong.

**The Amber Means Caution Rule.** Amber appears only next to a reason to hesitate. A badge, chip or button is never amber.

**The Ink Link Rule.** Links are ink with an underline and turn evergreen on hover. A blue link is a bug.

## Typography

**Display Font:** Source Sans (with sans-serif)
**Body Font:** Source Sans (with sans-serif)

**Character:** One humanist sans at every level. Hierarchy comes from size and weight steps of about 1.25, not from a second face.

### Hierarchy
- **Display** (650, `clamp(1.75rem, 1.3rem + 1.6vw, 2.25rem)`, 1.2): the page title only.
- **Headline** (400 with 650 numerals, 1.5625rem, 1.25): each tab's tally ("17 strong, 30 possible, 160 long-shot programs") and section headings such as "Long shots (160)".
- **Title** (600, 1.25rem, 1.35): result card titles, which are also the card's link.
- **Lead** (400, 1.0625rem, 1.55, max 65ch; 1rem under 640px): the intro and the overview line.
- **Body** (400, 1rem, 1.5): reasons, details values, checklist text. Notes and captions cap at 72ch.
- **Detail** (400, 0.9375rem, 1.5): dense reading inside a card or note: details lists, past grants, notes.
- **Meta** (400, 0.875rem, 1.5): the dot-separated meta line, notices, captions, the score, the edit guard.
- **Label** (600, 0.8125rem): badges.

### Named Rules
**The Step Rule.** Adjacent heading roles differ by at least 1.25 in size: 16, 20, 25px. A 17px heading over 16px body is a missing step. Detail (15px) is a reading size inside cards, never a heading.

**The No Shouting Rule.** All-caps text from tax returns is converted for display (title case for names, cities and addresses; sentence case for missions and instructions). The interface itself never uses all caps.

## Layout

A single reading column, at most 1080px wide, beside Streamlit's sidebar. The sidebar holds only the profile, grouped under small headings (About your work, Where you work, Eligibility, Keep this profile) separated by 1px rules.

The profile form exists twice: in the sidebar from 768px up, and as an "Edit your organization" expander above the results under 768px, where a sidebar would cover the results it changes. CSS shows one copy; both write to the same values, so they never disagree.

The main column follows a fixed rhythm: title, lead, the Grants.gov notice, an optional note, the phone profile row (under 768px), the overview line, tabs, then per tab the tally, a source caption, one "Filters and how the score works" expander, and the cards. Cards stack with 12px between their parts. Every strong result (up to 40) shows, then the first 10 possible ones, then "Show 40 more". A "Sort by" select above the cards offers best fit plus one or two orders that matter for that source (closing soonest and largest award for federal; most grants in the state and largest typical grant for foundations). The tally counts strong and possible only; long shots are counted in their own section behind a toggle.

Under 768px the sidebar and its button are hidden, the profile moves into the main column, the lead drops its list of sources, the example note shortens to one line and the overview keeps only its count. Under 640px tabs wrap with tighter gaps, card padding tightens to 16px and details lists stack label over value. Nothing scrolls sideways at 320px.

## Elevation & Depth

Flat. No shadows anywhere. Depth comes from tonal layering (paper, then mist for the sidebar and notes) and from 1px rules. Streamlit's rerun fade is kept short by running "Show more" and the long-shot toggle as their own fragments.

### Named Rules
**The Flat Ledger Rule.** If something needs to stand out, give it a rule, a tint or a heavier weight. Never a shadow.

## Shapes

Gently rounded (8px) on cards, buttons, inputs, notes and info boxes. Badges are full pills. Inside a card, the Summary or Details expander loses its own border and radius and becomes a full-width row under a single top rule, so there is never a box inside a box.

## Components

### Buttons
- **Character:** plain and sturdy.
- **Shape:** gently rounded (8px), at least 44px tall.
- **Default:** paper background, 1px rule border, ink text. Labels start with a verb ("Save to pipeline", "Download matches (CSV)", "Show 40 more", "Keep my text").
- **Hover / Focus:** Streamlit's border shift on hover; a 2px evergreen outline with 2px offset on keyboard focus.
- **Primary:** one only, "Update matches" under the key words: evergreen fill with paper text in light, evergreen-night fill with night text in dark (white on the light green fails AA). It commits typed text, so the form never needs a keyboard shortcut hint. A bold line under it answers the press where it happened: "Updated: 31 strong matches." or "No changes to your profile."
- **Safe first:** when a choice protects the visitor's work, the safe option comes first ("Keep my text" before "Replace my text" or "Clear my text").

### Chips
- **Style:** the multiselect's selected values use the neutral long tint and long ink, never the accent.

### Cards / Containers
- **Corner Style:** 8px.
- **Background:** paper (night in dark mode).
- **Shadow Strategy:** none; see Elevation & Depth.
- **Border:** 1px rule.
- **Internal Padding:** 18px top, 20px sides (16px under 640px), 8px bottom where the expander row sits flush.

### Inputs / Fields
- **Style:** paper background, 1px control-edge border, 8px radius, at least 44px tall. Placeholders in slate, written as examples ("For example: dyslexia, tutoring, after school").
- **Focus:** a 2px evergreen outline on the field wrapper.
- **Help:** each "?" icon has a 44px hit area centred on it.

### Navigation
- **Tabs:** sentence-case labels at 1rem and 500 weight, at least 44px tall, wrapping onto a second row instead of scrolling. The selected tab is evergreen with a 2px evergreen underline. Tabs are ordered by strong matches; "Before you apply" is always last.

### Result card (signature)
Badge row (tier badge plus "Score N of 100" in slate), the title link (title type, ink, underlined, at least 44px tall, announces that it opens a new tab; for a foundation it goes to the funder's own site when the return lists one, with the tax filing linked in the details), the meta line (meta type, slate, items separated by a dot; short facts never break), then the reasons list:
- **Fits:** drawn check in evergreen.
- **Cautions:** drawn triangle in caution amber.
- **Status** (timing facts such as forecasts): drawn clock in slate, slate text.

Each item carries hidden "Fits:", "Caution:" or "Status:" text for screen readers. Then "Save to pipeline" when signed in, and the Summary or Details row.

### Details list
Label and value pairs in a two-column definition list (slate labels, ink values), stacking under 640px. Empty values and return placeholders (NONE, N/A) are dropped. Phones become `tel:` links, emails `mailto:` links, websites lowercase links. Past grants are a short ruled list of up to eight: recipient in bold, then city, amount and purpose separated by dots.

### Notes
Mist background, 8px radius, 72ch maximum, detail type. One sentence where possible. Used for the example-profile notice ("This is an example." first, so nobody mistakes a sample's matches for their own) and the blank-start steps.

### Status and guard
- **Overview line:** a live region (`role="status"`). After any profile change it starts with a bold "Updated." so the change is seen and heard. The strong-match threshold sits here once, so no tab has to be remembered.
- **Edit guard:** switching examples over typed text asks first, as a caution-icon line with `role="alert"`, then "Keep my text" and "Replace my text".
- **Show more:** the count under the list is a live region; after a batch loads, "Go to result N" moves keyboard focus to the first new card.
- **Skip link:** each result list starts with a link that appears on focus and jumps past the list to its count.

## Do's and Don'ts

### Do:
- **Do** lead every screen with the answer: the overview line, then the tally.
- **Do** put reasons and cautions on the card itself, with drawn icons and screen-reader prefixes.
- **Do** keep every target at least 44px, every focus ring visible (2px evergreen), and every text pair at AA in both themes.
- **Do** escape every value that comes from an API or a tax return before it reaches HTML.
- **Do** tidy raw data for display (casing, empty placeholders, links) without changing what it says.
- **Do** write in sentence case, with buttons that start with a verb and no em dashes.

### Don't:
- **Don't** add a second accent colour or a blue link.
- **Don't** use amber anywhere except cautions.
- **Don't** use shadows, gradients or decorative imagery.
- **Don't** nest a bordered box inside a card.
- **Don't** change the wording or placement of the Grants.gov notice: "This product uses the Grants.gov API but is not endorsed or certified by the U.S. Department of Health and Human Services."
- **Don't** show more than 40 results at once without saying how many there are.
