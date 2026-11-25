---
name: Grant Matcher
description: The funding directory on the reference shelf, ranked against your own mission.
colors:
  ground: "#ffffff"
  paper: "#f3f6fa"
  cloth: "#0f2747"
  on-cloth: "#ffffff"
  on-cloth-muted: "#c7d4e6"
  ink: "#0f1b2d"
  muted: "#4a5568"
  rule: "#dbe2ea"
  edge: "#7a8699"
  accent: "#1d4ed8"
  on-accent: "#ffffff"
  strong-bg: "#dbeafe"
  strong-fg: "#1e3a8a"
  long-bg: "#eef1f5"
  long-fg: "#374151"
  caution: "#8a5a00"
  error: "#b3261e"
  ground-dark: "#0b1220"
  paper-dark: "#111a2b"
  cloth-dark: "#132c50"
  on-cloth-dark: "#f1f5fb"
  on-cloth-muted-dark: "#b9c7da"
  ink-dark: "#e6ebf2"
  muted-dark: "#a3b0c2"
  rule-dark: "#243049"
  edge-dark: "#6b7a92"
  accent-dark: "#8ab4ff"
  on-accent-dark: "#0b1220"
  strong-bg-dark: "#1e3a8a"
  strong-fg-dark: "#dbeafe"
  long-bg-dark: "#1c2537"
  long-fg-dark: "#cbd5e1"
  caution-dark: "#e3b65c"
  error-dark: "#ff8f86"
typography:
  headline:
    fontFamily: "Public Sans Variable, Public Sans, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "clamp(1.5rem, 1.1rem + 1.4vw, 2.125rem)"
    fontWeight: 400
    lineHeight: 1.2
    letterSpacing: "-0.012em"
  title:
    fontFamily: "Public Sans Variable, Public Sans, system-ui, sans-serif"
    fontSize: "1.5rem"
    fontWeight: 400
    lineHeight: 1.25
    letterSpacing: "-0.01em"
  wordmark:
    fontFamily: "Public Sans Variable, Public Sans, system-ui, sans-serif"
    fontSize: "1.3125rem"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "-0.01em"
  entry-name:
    fontFamily: "Source Serif 4 Variable, Source Serif 4, Georgia, serif"
    fontSize: "1.25rem"
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: "-0.003em"
  group-title:
    fontFamily: "Public Sans Variable, Public Sans, system-ui, sans-serif"
    fontSize: "1.125rem"
    fontWeight: 650
    lineHeight: 1.3
  body:
    fontFamily: "Public Sans Variable, Public Sans, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.5
    fontFeature: "lnum"
  label:
    fontFamily: "Public Sans Variable, Public Sans, system-ui, sans-serif"
    fontSize: "0.9375rem"
    fontWeight: 600
    lineHeight: 1.2
  meta:
    fontFamily: "Public Sans Variable, Public Sans, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.5
  caption:
    fontFamily: "Public Sans Variable, Public Sans, system-ui, sans-serif"
    fontSize: "0.8125rem"
    fontWeight: 700
    lineHeight: 1.3
    fontFeature: "tnum"
rounded:
  focus: "2px"
  md: "6px"
  pill: "999px"
spacing:
  2xs: "4px"
  xs: "6px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "20px"
  2xl: "24px"
  3xl: "32px"
  gutter: "48px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.on-accent}"
    typography: "{typography.label}"
    rounded: "{rounded.md}"
    padding: "0 16px"
    height: "44px"
    width: "100%"
  button-secondary:
    backgroundColor: "{colors.ground}"
    textColor: "{colors.ink}"
    typography: "{typography.label}"
    rounded: "{rounded.md}"
    padding: "0 16px"
    height: "44px"
  button-secondary-hover:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
  input:
    backgroundColor: "{colors.ground}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.md}"
    padding: "9px 12px"
    height: "44px"
  index-tab:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    typography: "{typography.label}"
    rounded: "{rounded.md}"
    padding: "0 14px"
    height: "44px"
  index-tab-hover:
    backgroundColor: "{colors.strong-bg}"
  index-tab-selected:
    backgroundColor: "{colors.cloth}"
    textColor: "{colors.on-cloth}"
  tier-strong:
    backgroundColor: "{colors.strong-bg}"
    textColor: "{colors.strong-fg}"
    typography: "{typography.caption}"
    rounded: "{rounded.pill}"
    padding: "2px 9px"
  tier-possible:
    backgroundColor: "{colors.ground}"
    textColor: "{colors.accent}"
    typography: "{typography.caption}"
    rounded: "{rounded.pill}"
    padding: "2px 9px"
  tier-long:
    backgroundColor: "{colors.long-bg}"
    textColor: "{colors.long-fg}"
    typography: "{typography.caption}"
    rounded: "{rounded.pill}"
    padding: "2px 9px"
  score-rule:
    backgroundColor: "{colors.rule}"
    rounded: "{rounded.pill}"
    width: "120px"
    height: "6px"
  note:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    padding: "12px 16px"
---

# Design System: Grant Matcher

## Overview

**Creative North Star: "The reference shelf directory"**

Grant Matcher looks like the printed funding directory a librarian keeps behind the desk, rebuilt to read your mission back to you. A navy band holds the name, the one-line answer and the Grants.gov notice. Below it, results are dense listings set on hairline rules on plain ground, not floating cards: a ranked score on one fixed scale, the funder's name in a text serif, a catalog number in tabular figures, then run-in facts and the reasons that a grant fits or could sink you.

The system is calm, sturdy and plain. Type does the ranking quietly because a fixed visual scale carries the rank. There is one accent color, and status colors appear only when they mean something. It refuses the category default of a grey filter sidebar beside interchangeable soft cards, and it must never read as a slick startup: no gradients, no hype, no decoration for its own sake.

The public static site in `web/` is the source of this system. The Streamlit workspace (`app.py`) predates it and is not the reference for new public surfaces.

**Key Characteristics:**
- Navy band and selected index tab; plain white ground in light, deep blue-black in dark, never cream.
- Public Sans for every working word; Source Serif 4 for funder and entry names only.
- Ruled directory listings, not cards.
- One score rule, one fixed 0 to 100 scale, the same on every entry.
- Light and dark follow the system setting; AA in both.

## Colors

A narrow blue world: one navy for the shell, one civic blue accent for action and rank, cool blue-grey neutrals, and two status colors held back for meaning.

### Primary
- **Binding navy** (cloth): the header band and the selected index tab, plus the 2px rule under the tab row and above "Getting ready to apply". It is the binding of the book, never a button fill.
- **Civic blue** (accent): the primary button, links, focus rings, the score rule fill, the selected segment, checkbox and range controls, fit icons and the "On shortlist" state. In dark mode it lifts to a pale sky blue (accent-dark) and its text partner turns dark (on-accent-dark).

### Neutral
- **Plain ground** (ground): page background. White in light, deep blue-black in dark.
- **Shelf paper** (paper): quiet fills: unselected tabs, notes, button hover in light.
- **Ink** (ink): body text, entry names, deadlines, catalog numbers.
- **Muted ink** (muted): hints, run-in facts, award sizes, the printed key, the long shot rule fill.
- **Hairline** (rule): entry rules, column divider, the empty track of the score rule.
- **Control edge** (edge): borders on inputs, buttons, the segmented control, and the select chevron.
- **Tier tints** (strong-bg / strong-fg, long-bg / long-fg): the Strong and Long shot chips. strong-bg also serves as the tab hover.

### Status
- **Caution amber** (caution): caution icons, the confirm guard outline, the warning note outline. Nothing else.
- **Error red** (error): error text. Nothing else.

### Named Rules
**The One Blue Voice Rule.** There is one accent. Navy is structure, civic blue is action and rank; no third hue joins them.

**The Meaning-Only Status Rule.** Amber appears only for cautions and red only for errors. Never use either to decorate, highlight or brand.

**The No Cream Rule.** Ground is plain white in light and deep blue-black in dark. Warm paper tints are not part of this world.

## Typography

**Body Font:** Public Sans Variable (with system-ui, Segoe UI, sans-serif)
**Name Font:** Source Serif 4 Variable (with Georgia, serif)

**Character:** A sturdy civic sans does all the work; the text serif appears only where a directory would set a proper name, so funder names read like entries in a printed catalog.

### Hierarchy
- **Headline** (400, clamp 1.5rem to 2.125rem, 1.2): the one-line answer in the band. The counts inside it are set in 700. Max 36ch.
- **Title** (400, 1.5rem, 1.25): the tally above each list ("18 strong, 30 possible") with counts in 700; also checklist headings. Section heads like "Long shots" use 400 at 1.375rem.
- **Wordmark** (700, 1.3125rem, 1.2): the product name in the band.
- **Entry name** (Source Serif 4, 600, 1.25rem, 1.3; 1.125rem at 560px and below): funder, program and grant names only.
- **Group title** (650, 1.125rem, 1.3): the form title and the "Getting ready to apply" summary (1.25rem there); fieldset legends at 1rem.
- **Body** (400, 1rem, 1.5): running text; long text held to 62 to 70ch.
- **Label** (600, 0.9375rem): field labels, buttons, tabs, deadlines.
- **Meta** (400, 0.875rem): hints, run-in facts, form status.
- **Caption** (700, 0.8125rem): tier chips and tab counts; the printed key uses 400 at the same size.

### Named Rules
**The Names Only Serif Rule.** Source Serif 4 is for funder and entry names only. Headings, numbers, labels and buttons stay in Public Sans.

**The Column Figures Rule.** Every number that is scanned down a column (scores, catalog numbers, deadlines, counts) uses tabular figures; running text uses lining figures.

## Layout

A two-column work area at desktop, max 77.5rem wide with 1.5rem side padding: the profile column (18rem to 21rem) on the left, then a 3rem gap and the results column (max 50rem). The profile column is separated by a single hairline, is sticky to the top, scrolls on its own inside the viewport, and keeps the Update matches button pinned at its foot on ground.

The profile reads top to bottom in the order a person thinks about their work: About your work (mission, focus area checkboxes, more key words, federal funding areas), Who you serve, Where you work (state, cities or counties, how services are delivered), Your organization (501(c)(3) status, fiscal sponsor when not Yes, budget, year founded, matching funds, registrations), What you're asking for, and Funders and timing. The three optional groups (Who you serve, What you're asking for, Funders and timing) fold away behind a disclosure in the group-heading style, with "N chosen" beside the name so a closed group still shows it is doing something. Checkbox groups are a fieldset with a visible legend and one 44px row per choice.

Inside the results column, the order is fixed: example or warning note, the index tab row with a count on each tab, the tally with its printed key, filters, then the ruled entries.

Inside each entry the columns are fixed: the tier chip and score rule at left with the deadline right-aligned on the same line; the entry name; the catalog number and run-in facts; the reasons list; then the shortlist mark at the right and the details disclosure at the left. On the Shortlist tab, entries are grouped under Applying, Saved and Submitted headings, and each one has a Stage select with the date it moved, above the details row; changing it keeps focus on that select in its new group and announces the move. Below it, a Your deadline date field with the days left (caution color within a week). A Coming up list (next 30 days) sits above the groups, Applying and Saved sort by deadline, and a changed or withdrawn federal deadline shows as a caution line under the date. When something is due within a week, a note at the top of the results links to the shortlist.

A profile in a state with no state catalog gets no state tab. A plain note above the tabs says what is missing and what still covers the state, and gives only a reason the research established: the pages are web pages and not a data file, a machine-readable list isn't read in, no current list was found, or the key sites can't be used because their rules or terms don't allow it or they turn automated readers away. The note never says a state has no grants. The line above a state's open calls names the source, says when coverage is partial, and never says a list names nonprofits when it doesn't say who may apply. Calls with no stated eligibility are counted apart from the ones that list nonprofits ("3 of 7 ... list nonprofits as eligible; 1 more doesn't say who may apply"). A call with no stated eligibility says "Who may apply isn't listed; read the notice" as a plain note, never "Open to nonprofits".

Spacing runs on a quarter-rem rhythm (4, 6, 8, 12, 16, 20, 24, 32, 48px). Entries are dense: 20px above, 12px below, 8px between parts.

**Responsive behavior.**
- At 860px and below the layout becomes one column with 1rem padding, the band lede hides, and the profile collapses behind a single full-width "Edit your organization" bar above the tabs.
- At 560px and below the tabs become a 2x2 grid with short labels (Florida, Foundations, Federal, Shortlist; DC for the District of Columbia), the score rule shortens to 5.5rem, details rows stack, and the shortlist mark moves below the details.
- Every layout works at 320px wide with no horizontal scroll.

## Elevation & Depth

Flat. There are no drop shadows. Depth comes from tonal blocks (the cloth band, the paper fills) and from hairline rules. The only box-shadows are 1px inset outlines that act as borders: the Possible chip and the warning note.

### Named Rules
**The Rules Not Cards Rule.** Entries sit on hairline rules on plain ground. They never get a card fill, a border box, or a shadow.

## Shapes

Gently squared corners (6px) on every control, note, tab top and the segmented control. Pills (999px) only for the tier chips, tab counts, the shortlist count and the score rule track. Focus outlines take a 2px corner. Disclosure chevrons are drawn from two 2px borders rotated, not glyphs.

## Components

### Buttons
Plain and firm.
- **Shape:** gently squared (6px), 44px minimum height, 16px side padding.
- **Primary:** accent fill with on-accent text, full width of its column, 1rem label. Used for Update matches. Hover brightens slightly (brightness 1.08).
- **Secondary:** ground fill, ink text, 1px control-edge border. Hover takes the paper fill and an ink border. Press nudges down 1px.
- **Quiet:** the shortlist mark is a borderless muted text button with a bookmark icon; it turns accent when on.

### Chips
- **Tier chips:** Strong is a strong-tint fill; Possible is an accent 1px inset outline on ground; Long shot is a grey tint. 0.8125rem, 700, pill.
- **Tab count:** ground pill inside the tab; translucent white on the selected cloth tab.

### Inputs / Fields
- **Style:** ground fill, 1px control-edge border, 6px corners, 44px minimum height, 1rem text.
- **Focus:** the border turns accent and the 2px accent ring sits flush (offset 0).
- **Segmented control:** three equal cells in one 6px frame divided by edge lines; the checked cell fills accent.
- **Checks:** native boxes tinted accent, each row 44px tall.
- **Confirm guard:** a 1px caution outline box with two buttons, used before replacing typed text.

### Navigation
- **Index tabs:** paper tabs with 6px top corners sitting on a 2px cloth rule; hover takes the strong tint; selected fills cloth with on-cloth text. Arrow keys, Home and End move between them.
- **Band:** cloth fill, wordmark left, shortlist count right, focus ring switches to on-cloth inside the band.

### Score rule (signature)
Every entry carries the same rule: a 7.5rem by 6px pill track on the hairline color, filled in accent to the score's percent (muted for long shots), with thin ink marks at 35 and 60 that stand slightly proud of the track. The score number follows in 700 tabular figures. The scale never rescales per list. Under each tally a printed key repeats the empty rule with its marks labelled 0, 35, 60 and 100 and the sentence "Strong is 60 or more out of 100; possible is 35 to 59."

### Entry facts
The deadline sits right-aligned on the score line in ink, 600, tabular figures. Award sizes ("Typical $N") take the same place in muted 400. The catalog number leads the run-in facts in ink 600; the rest of the facts are muted, separated by a middle dot.

### Reasons list
Each reason is one line with an 18px stroke icon: an accent check for fits, an amber triangle for cautions, a muted info or clock icon for other notes. Screen readers hear "Fits", "Caution", "Also" or "Status" before each.

### Can we apply?
Under the reasons, one wrapping line: "Can we apply?" in ink 650, then each check as a 16px icon and a few words (an accent check when it's fine, an amber triangle when it needs a look or stops you; one that stops you is set in 650). No fills, no pills. The details open with the same checks as full sentences. Screen readers hear "Fine", "Check" or "Stops you" before each, and the heading carries the count. A caution or status line the checks repeat stays off the card.

### Notes
Paper fill, 6px corners, 12px by 16px padding, max 66ch. A warning note adds a 1px caution inset outline.

### Filter bar
Sits under each tally, above "More filters and how the score works", on a top rule. One row of standard 44px fields that wraps: "Search these results" (grows; its words carry across tabs and must all appear somewhere in an entry, details included), then the source's own choices (award size, closes by and agency for federal grants; typical grant and three checkboxes for foundations; agency for Florida programs). Filters narrow what is shown and never change a score. When any is on, a muted status line reads "Showing N of M" with an accent "Clear filters" text button. When the profile's 501(c)(3) status isn't Yes, foundations get a fourth checkbox, "Don't ask for 501(c)(3) proof". After a return visit with new records, every source gets "Only new since your last visit on {date} (N)".

### New tag
A small word, "New", in the accent with a 1px accent border and the standard radius, beside the score rule. Screen readers hear "New since your last visit". Never colour alone.

## Do's and Don'ts

### Do:
- **Do** keep every target at least 44px tall, including entry name links and summary rows.
- **Do** show the 2px accent focus ring with a 2px offset on every focusable element (on-cloth inside the band).
- **Do** hold AA contrast in light and dark; the built system measures its lowest text contrast at 6.7:1 in light and 7.27:1 in dark.
- **Do** put the score rule on every entry, on the one fixed 0 to 100 scale with marks at 35 and 60, and print its key under each tally.
- **Do** right-align deadlines in ink 600 tabular figures and keep award sizes muted.
- **Do** set funder and entry names in Source Serif 4 and everything else in Public Sans.
- **Do** keep the profile column sticky and self-scrolling with Update matches pinned at its foot.
- **Do** switch the tabs to a 2x2 grid with short labels at 560px and below, and test every surface at 320px.
- **Do** write in plain words and sentence case, with verb buttons and no em dashes.

### Don't:
- **Don't** add a second accent hue, or use amber or red for anything but cautions and errors.
- **Don't** put entries in cards, fills, borders or shadows; they live on rules.
- **Don't** use the serif for headings, numbers, labels or buttons.
- **Don't** rescale the score rule per list or drop the 35 and 60 marks.
- **Don't** use cream or warm paper grounds, gradients, or decorative imagery.
- **Don't** use navy as a button fill; it is the band and the selected tab only.
