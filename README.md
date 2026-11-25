# Grant Matcher for small nonprofits

Finding grants you can actually win is hard when you are a small nonprofit. Grants.gov lists over a thousand open and upcoming federal opportunities at any time, and most of them are research programs, multimillion-dollar awards, or grants that require matching funds a young organization does not have. Foundation money is spread across tens of thousands of private funders whose interests are buried in tax returns.

Grant Matcher reads your mission and ranks three kinds of funding against it, telling you in plain words why each one is or is not a fit:

- **Federal grants:** every open and forecasted opportunity on Grants.gov that nonprofits can apply for
- **Foundations:** private foundations (IRS Form 990-PF) plus community foundations, public foundations, and United Ways (Form 990 Schedule I) that give in your state, with who they funded, typical grant size, and how to apply
- **Florida state programs:** state programs open to nonprofits from Florida's Catalog of State Financial Assistance, with legislative earmarks filtered out
- **Other states' grants:** open calls from the state's own list in California, Illinois, Iowa, Ohio, Washington, West Virginia and New Jersey. For every other state, and DC, the page says there is no state catalog yet; [docs/state-coverage.md](docs/state-coverage.md) says why for each
- **County programs:** county grant programs for nonprofits, such as Manatee County's children's services funding, entered by hand from each program's own page

**Try it:** [rendellrich.github.io/grant-matcher](https://rendellrich.github.io/grant-matcher/). Visitors see the top 3 matches, free accounts the top 10 in each list, and Pro every match.

> This product uses the Grants.gov API but is not endorsed or certified by the U.S. Department of Health and Human Services.

![Grant Matcher on a desktop in light mode. A navy band at the top gives the answer, 30 strong matches for this profile: 18 Florida programs, 12 foundations and no strong federal grants, above the Grants.gov notice. Below, the profile form sits in a column on the left with Update matches pinned at its foot, and on the right are index tabs with counts and the first ranked Florida program.](docs/images/desktop-light.png)

![One federal grant entry in dark mode: a Possible match label, a score rule filled to 52 with marks at 35 and 60, the estimated due date set to the right, the program name, its opportunity number and agency, reasons it fits, and a Summary section to expand beside Add to shortlist.](docs/images/card-dark.png)

<table>
  <tr>
    <td width="50%" valign="top"><img src="docs/images/phone-light.png" alt="Grant Matcher on a phone in light mode with Edit your organization open: the example picker, the mission text, and Update matches pinned at the bottom of the screen."></td>
    <td width="50%" valign="top"><img src="docs/images/phone-dark.png" alt="Grant Matcher on a phone in dark mode: the result tabs as a two by two grid, the Florida tally with its 0 to 100 score key, and the first ranked program."></td>
  </tr>
</table>

## What it does

- **Ranks by meaning, not just key words.** Your mission is compared with each opportunity's title, summary, and categories using a small semantic embedding model (BAAI/bge-small-en-v1.5 through fastembed, no GPU needed), plus coverage of your key words. Rare, specific words like "dyslexia" count for more than common ones like "children".
- **Checks the things that sink small applicants:**
  - eligibility for 501(c)(3) nonprofits, or for groups still waiting on status
  - cost sharing or matching requirements
  - minimum award sizes far larger than your budget
  - research grants that need a research institution
  - programs that list nonprofits but are really for tribes, state agencies, or embassy programs abroad
  - deadlines too close to meet
- **Explains every score** with reasons and cautions, so the ranking is a starting point for your judgment, not a black box.
- **Shows forecasts**, grants that are announced but not open yet, which give you the most time to prepare.
- **Builds the search from checkboxes.** Pick focus areas (literacy, dyslexia, speech, tutoring and 12 more), ages and grades, and populations, and each adds a tested list of words to the match, so you don't have to guess key words. Words from ages and populations count half, so they lift a good match without making a weak one strong. The lists live in `web/src/terms.json`, read by both scorers.
- **Understands counties.** Type "Manatee" and grants to Bradenton, Palmetto, Ellenton and the county's other places count as local, from the Census Bureau's 2020 places-by-county file (`grantmatch/counties.py`).
- **Knows your situation:** a fiscal sponsor softens 501(c)(3) requirements, serving people online nationwide counts funders that give in five or more states, and a young organization gets a caution on large federal awards.
- **Saves your filters with your profile:** type of support (general operating, start-up, capacity building and more), the amount you want to ask for, funder types, timing (open now, or due within 30, 60 or 90 days), words to avoid, and a hide list (scholarship funds, invitation only, no unsolicited requests, research grants, matching funds required). They never change a score, and each tab says how many they hide.
- **Exports** your strong and possible matches to CSV and the deadlines to a calendar file (.ics).
- **Narrows the list** without changing any score: search words across every result and its details, award size, deadline and agency for federal grants, agency for Florida programs, and for foundations their typical grant, whether they publish how to apply, whether they refuse unsolicited requests, and whether they're based in or fund your cities.
- **Marks what's new.** Grants, foundations and programs that weren't in the data at your last visit carry a New tag, and "Only new since your last visit" shows just those. The record of what you've seen stays in your browser.
- **Flags eligibility while your 501(c)(3) is pending.** Foundations whose own filing asks for 501(c)(3) status or an IRS determination letter get a caution and a lower score, with a note about a fiscal sponsor, and one checkbox hides them. Federal grants that require 501(c)(3) status say the same.
- **Keeps a shortlist** of the results you mark, saved in your browser and, on Pro, to your account so it is the same on every device, with its own CSV. Each one has a stage: Saved, Applying or Submitted, with the date it moved. Submitted ones stop showing in the results and stay on the shortlist.
- **Tracks deadlines** for what is on the shortlist: set your own date for any grant (federal ones start from the Grants.gov date), see what is due in the next 30 days under Coming up, get a note on each visit when something is due within a week, and download a calendar file with reminders two weeks and three days before each deadline. If Grants.gov moves a deadline or drops a grant you saved, the shortlist says so.
- **Saves your profile** as a small JSON file you can load next time. Nothing is stored on a server, so the profile clears when you close the page.

## How it runs

The public site is a static site in `web/` (Vite, TypeScript, Preact) on GitHub Pages. Accounts, the search gate and the data live in a Supabase project.

- **Matching happens in the browser.** The first time you search with your own mission, the page downloads the same embedding model the data pipeline uses (BAAI/bge-small-en-v1.5, about 67 MB, once) and runs it on your device with [transformers.js](https://github.com/huggingface/transformers.js). The profile and that vector then go to the search function (`supabase/functions/search`), which ranks visitors and free accounts on the server with the same code and returns the top matches; Pro accounts get short-lived links to the data and rank in the browser. Search profiles are not stored; a signed-in search is logged only as a hash. The three examples are scored without the download.
- **The scoring is the Python scoring, ported.** `web/src/score.ts` is a line-by-line TypeScript port of `grantmatch/match.py` and `grantmatch/rank_more.py`. A parity test scores 18 example profiles in both, including the checkbox groups, fiscal sponsor, online nationwide and young organization cases, and requires the same results, reasons and cautions.
- **The data lives in a private bucket.** After each refresh, `grantmatch/export_web.py` writes the records and their embeddings (as float16), the deploy workflow uploads them to the Supabase bucket `data` through the ingest function (`grantmatch/server_data.py`), and only the small public files (meta, examples, coverage, changes, counties) ship with the site. The site rebuilds after every successful refresh (federal, Florida, California, Illinois, foundations, funder websites) and whenever the site code or a hand-kept list (`data/corporate.json`, `data/local-*.json`, `data/skip-review.csv`) changes on main.
- **Functions deploy themselves.** The search gate, the weekly email and the deadline reminders each run from one bundled file built in `web/`. When the code they bundle changes on main, the Deploy functions workflow tests it, rebuilds the three bundles, deploys them with the Supabase command-line tool (settings in `supabase/config.toml`) and checks that search answers a visitor. The billing and Stripe webhook functions deploy from source in the same run, with a check that each refuses a caller with no sign-in or signature. It needs the repository secret `SUPABASE_ACCESS_TOKEN`. The ingest function is deployed by hand.
- **Paid plans and the weekly email** run through Stripe Checkout, a signed Stripe webhook and a scheduled email job. Profiles are saved only for an account that turns the weekly email on. See [docs/billing.md](docs/billing.md) for how it fits together and the go-live steps.

## Design and accessibility

The people using this are often one-person development teams at small nonprofits, working late, on a phone as often as a laptop, and some use a screen reader. The design follows from that.

- **It reads like a funding directory.** The look is modelled on the printed grant catalogs nonprofits used to find at the library: a navy band, Public Sans (the typeface of U.S. government sites) for working text, a serif for funder names, and ruled entries that each lead with their catalog number, EIN or opportunity number.
- **The answer comes first.** The first line on the page says how many strong matches there are and where. Each tab carries its count, and each entry leads with a Strong, Possible or Long shot label and its score on the same 0 to 100 scale, with the 35 and 60 marks drawn in, so entries compare at a glance. Deadlines sit right-aligned.
- **Every entry explains itself** in the same order: what fits your work, then cautions, then plain facts such as typical grant size, in a quieter color. If none of your key words appear in a funder's past grants, that is the first caution.
- **Nothing changes until you ask.** Edits to the profile stay a draft until you press Update matches. The button stays pinned at the bottom of the form, and a line under it confirms the update or says your changes are not applied yet.
- **One accent color.** Blue is the only accent. Amber marks cautions and red marks errors; neither is used for decoration. Light and dark follow the visitor's system setting, and text meets WCAG AA contrast in both.
- **Works by keyboard and on small screens.** Focus is always visible, controls have 44 pixel targets, each long list has a link to skip past it, and the layout works down to 320 pixels wide with no sideways scrolling.
- **Tested with a screen reader.** I ran the main tasks with NVDA 2026.3 in Microsoft Edge and fixed what it found. Pressing Update matches is now announced. Show more keeps focus in place instead of sending NVDA back to the top. Each card's title is read before its score, and the button that opens a card's details names that card.

The colors, type, components and rules are written down in [DESIGN.md](DESIGN.md).

## Inside Exceed the Odds' admin page

With `?embed=eto`, and only when framed by an allowed site (`ALLOWED_PARENTS` in `web/src/parent.ts`), the matcher runs inside ETO's admin page:

- ETO sends its saved profile, and the matcher applies it. "Keep this profile" becomes "Save profile to ETO".
- "Add to shortlist" becomes "Send to funding pipeline". ETO adds the funder and the opportunity at Prospect and answers; the card then reads "In pipeline: Prospect". If ETO doesn't answer within 15 seconds, the page says so.
- The browser shortlist is off, and the hide list gains "Already in our pipeline" and "Declined or closed before", from what ETO reports.
- Opened any other way, `?embed=eto` changes nothing.

The two pages talk with `postMessage`. The matcher listens only to its parent window at an allowed origin, posts only to that origin, cleans every incoming message, and sends back only the profile and public facts about a grant. The messages:

| Message | From | Carries |
|---|---|---|
| `gm:ready` | Matcher | `protocol` version |
| `eto:profile` | ETO | the saved profile |
| `eto:in-pipeline` | ETO | `items`: match `key`, `stage`, `closed` |
| `gm:send` | Matcher | `item`: key, source, title, funder, EIN, website, link, deadline, amounts, catalog number, summary, reasons, cautions, website quote, score, tier |
| `eto:sent` | ETO | `key`, `ok`, `status` (saved, exists, error), `stage`, `message` |
| `gm:save-profile` | Matcher | the profile |
| `eto:profile-saved` | ETO | `ok`, `message` |

[`docs/embed-harness.html`](docs/embed-harness.html) stands in for ETO to try it by hand; the steps are at the top of the file.

### Background scoring for ETO

After each data refresh, the deploy workflow scores ETO's saved profile so ETO's count of new strong matches stays current without anyone opening the matcher.

- **How it ranks:** `web/scripts/score-eto.ts` uses the page's own ranking (`web/src/rank.ts`) and the same meaning model, on the data just exported.
- **What it sends:** it reads the saved profile from ETO with a key made in ETO's CRM, and sends back only the strong grants (key, name, funder, deadline).
- **What it keeps:** nothing about ETO is written to disk or to the site, and the log shows counts only.
- **When it runs:** only on `main` in this repository, and only when these repository secrets are set: `ETO_SUPABASE_URL`, `ETO_PUBLISHABLE_KEY` and `ETO_GRANT_MATCHER_KEY`. A failure never stops the deploy.

To check a profile locally without ETO, run `npm run score-eto -- --profile <file>` in `web/`. It prints the number of strong grants and records nothing.

## Private workspace (optional)

The Streamlit app (`app.py`, at [grant-matcher.streamlit.app](https://grant-matcher.streamlit.app)) still runs and has a signed-in workspace for an organization's own team. It is off unless the deployment has the secrets in `.streamlit/secrets.toml.example`. With them, people on the allowed list can sign in with Google and get:

- **Pipeline:** save any grant, foundation, or state program, then track status, deadlines, next steps, and notes
- **Organization:** the facts every draft draws on (mission, programs, budget, outcomes, board)
- **Write:** a letter of inquiry drafted for a saved funder from what it funded last year, or an uploaded application form with every question drafted, editable, and exported to Word (for a Word form, the answers are placed into a copy of the funder's own file)
- **Answer library:** every answer you approve is saved and reused in the next draft, so drafts sound more like you over time

Saved work lives in a separate private GitHub repository, not in this public one. Drafting uses the Claude API; drafts use only saved facts and approved answers, and missing facts become [bracketed placeholders] rather than guesses.

## How the federal score works

| Part | Effect |
|---|---|
| Mission similarity | Up to 70 points, by how far a grant sits above your mission's typical similarity to all grants |
| Key word coverage | Up to 30 points, weighted toward your rarest key words |
| "Other" eligibility only | minus 5, with a note to read the eligibility text |
| Requires 501(c)(3) and you do not have it | minus 40 |
| Requires cost sharing you cannot provide | minus 20 |
| Smallest award over 3 times your annual budget | minus 15 |
| Research grant (NIH or NSF announcement, or "research" in the title) | minus 35 |
| Aimed at tribes, state agencies, or overseas embassy programs | minus 20 to 25 |
| Research and development only | minus 8 |

Scores of 60 and up are labeled Strong, 35 to 59 Possible, and below 35 Long shot.

## How foundations are scored

| Part | Effect |
|---|---|
| Past grant purposes match your mission | Up to 60 points |
| Your key words in its past grants | Up to 15 points |
| Share of its grants that went to your state | Up to 20 points |
| Funded groups in the cities you list | plus 5, or plus 10 for three or more |
| Based in one of your cities | plus 5 |
| Community foundation serving your area | plus 15 |
| Community foundation in another state | minus 25 |
| Gives mostly outside your state (under 10% of grants) or not at all | minus 15 to 20 |
| Fewer than three grants last year | minus 20, and never rated Strong |
| Typical grant larger than your annual budget | minus 10 |
| Says it does not accept unsolicited requests | minus 30 |
| Mostly scholarships for individuals | minus 15 |

Foundations that check the box saying they only fund preselected organizations are hidden unless you ask to see them.

## Florida state programs

Florida's Department of Financial Services keeps the Catalog of State Financial Assistance, a list of every state program that pays money to local governments, nonprofits, and businesses. Many entries are money the Legislature set aside for a named organization; those are flagged and hidden by default. An entry counts as set aside when its award or application steps say so: a proviso or line item, a named recipient, "direct appropriation" or "sole source award", and similar wording. The catalog lists programs rather than open calls, so each result links to the agency for its next application window.

## California state grants

California's agencies post every grant and loan opportunity to the [California Grants Portal](https://www.grants.ca.gov/), which the State Library publishes as public-domain open data, updated daily. `grantmatch/california.py` reads that file and keeps the open and forecasted calls, in the same fields as Florida's programs so the same scorer reads them. Unlike Florida's catalog these are open calls, so each record also carries its open date, deadline, required match, whether it is a loan, and how the money is paid (most pay by reimbursement).

The data is refreshed daily and published with the release. On the site, the state tab follows the profile's state: a Florida profile sees Florida programs, a California, Illinois, Iowa, Ohio, Washington, West Virginia or New Jersey profile sees that state's grants, and a profile in any other state (or DC) sees a plain note above the tabs instead of a state tab: "No Kansas state catalog yet," the reason when the research established one, and that federal grants and foundations still cover the state.

When the portal's applicant categories leave nonprofits out but the agency's own notes name them ("non-profit corporations", "all public and private entities"), the call is shown with a note to check the notice first.

## Illinois state grants

Under Illinois' Grant Accountability and Transparency Act, every state agency posts its Notices of Funding Opportunity to one public list kept by the Governor's Office of Management and Budget ([CSFA opportunity list](https://omb.illinois.gov/PUBLIC/GATA/CSFA/OpportunityList.aspx)): the title, agency, application window and award range. Notices run in the state's grants system link to a public AmpliFund page with the description, who may apply, award size and match; the rest link to the catalog's own notice and program pages. `grantmatch/illinois.py` reads the list and each page, daily, into the same record fields as California's. Who may apply comes from the state's own applicant categories ("Nonprofit Organizations"); only when a notice says "Others" or gives no categories does it read the eligibility text. A notice that says nothing either way (blank, "N/A" or "SEE NOFO") is kept, and its card says so. A notice whose funding restrictions or eligibility say "by invitation only" is left out (listed in the skipped grants review), since nobody can apply to it on their own; most are Natural Resources pass-through money for wildlife and fisheries. Community action agencies count as nonprofits. Programs that don't post a notice to the list are kept by hand in `data/local-IL.json`: the Illinois Arts Council's General Operating Support and Creative Projects grants (the Council posts only its public radio and TV grant as a notice), Illinois Humanities' Project, Collaborative Project, General Operating and Envisioning Justice grants, the Illinois State Library's Adult Volunteer Literacy grants, and the Attorney General's Violent Crime Victims Assistance, Domestic Violence Fund and Violence Prevention Special Project grants (crime victim money from ICJIA, such as VOCA, is posted to the list and isn't kept by hand).

Open calls are scored like Florida's programs, with three checks of their own:

| Part | Effect |
|---|---|
| Requires matching funds you cannot provide | minus 20 |
| A loan, not a grant | minus 25 |
| Pays by reimbursement only | a caution, no points off |

## Ohio state grants

Ohio's grants policy (Office of Budget and Management, under ORC 126.22) requires every state agency that offers a state or federal funding opportunity to post it on the Ohio Grants Partnership site. Its [current opportunities](https://grants.ohio.gov/funding-opportunities/find-current-opportunities) table is filled from a public JSON list (`api.obm.ohio.gov/grants/getfundingopportunities`), and `grantmatch/ohio.py` reads that list daily: title, number, agency, application window, award floor and ceiling, total funding, match, the description, and the state's own eligible applicant types. Who may apply comes from those types: "Non-Profit" and "Faith-based Associations/Organizations" count; "Houses of Worship" alone does not. A listing with no types is kept with a note on its card. Each record links to the opportunity's public page on the Ohio Grants Portal. The list is short (about 15 open at a time), since many Ohio agencies also run calls on their own sites. Programs that don't post to the list are kept by hand in `data/local-OH.json`: the Commission on Minority Health's Minority Health Month and supplemental grants, the Attorney General's VOCA/SVAA and Rape Crisis Trust Fund cycles, the Ohio History Fund, and the OneOhio Recovery Foundation's regional opioid settlement grants. The Ohio Arts Council and Children's Trust Fund post their calls to the state list, so they aren't kept by hand.

## Iowa state grants

Iowa agencies post their funding opportunities on [IowaGrants.gov](https://www.iowagrants.gov/storefrontFOList.do), the state grants system. `grantmatch/iowa.py` reads its public list daily (ID, agency, program, title, posted date, final deadline) and each opportunity's page (award range, project dates, whether it recurs, program officer, description). Iowa's listing has no field for who may apply, so it is read from the description: one that names nonprofits as applicants keeps the grant; one that limits it to cities, counties, school districts or employers, or says nonprofits can't apply, leaves nonprofits out (the skipped report quotes the sentence); and one that says neither is kept with a note to read the notice. Department of Education grants that don't name nonprofits are taken as school and district grants. A nonprofit named only as a vendor ("can outsource the website to a non-profit") doesn't count. The program officer's email is left out: the site hides addresses from scripts, and the name and phone are kept. Use `show` in `data/skip-review.csv` when the description reads wrong. About 18 are posted at a time, about 8 of them open to nonprofits. A list that starts "Eligible borrowers: businesses" isn't read as a limit (it often goes on to name nonprofits), and neither is "only an eligible taxpayer" (a nonprofit that owns the building is one). Programs that apply outside IowaGrants are kept by hand in `data/local-IA.json`: Humanities Iowa's Mini Grants, the Iowa Arts Council's Art Project and Cultural Capacity Building grants (applied for in SlideRoom), the State Historical Society's Historical Resource Development Program, and the Attorney General's opioid settlement grants and victim services rounds (applied for in the Department of Justice's own grants system). Iowa's youth grants (Workforce Development internships, Volunteer Iowa's AmeriCorps) go through IowaGrants, so they aren't kept by hand.

## Washington state grants

[FundHubWA](https://fundhub.wa.gov/funding/), run by the Washington Department of Commerce, lists state and federal grants, loans, rebates and incentives, mostly for climate, clean energy, resilience and land and water work. Each listing has structured fields in the site's public WordPress JSON API (`/wp-json/wp/v2/funding`), and `grantmatch/washington.py` reads them daily. Only state money is kept; the federal listings are federal notices Grants.gov already carries. Closed and expired listings are history, not skips. Who may apply comes from the portal's audience tags ("Nonprofits"); only an untagged listing has its eligibility text read. About a dozen state listings are open at a time, so this is a narrow source: other Washington agencies post their calls on their own pages. Calls it leaves out are kept by hand in `data/local-WA.json`, the same way as Florida's local list: Commerce's social service and capital grants (Building Communities Fund, Youth Recreational Facilities, Building for the Arts, WorkFirst providers, behavioral health facilities), Office of Crime Victims Advocacy funding, and ArtsWA grants.

## West Virginia state grants

[grants.wv.gov](https://grants.wv.gov/) is a SharePoint site whose AvailableGrants list holds each agency's grant listings, and the site's own public REST API returns the list as JSON with no login. `grantmatch/westvirginia.py` reads it: title, agency, type of grant, who may apply (the state's EntityEligible text), posted and due dates, a forecast note, the details, guidelines and how to apply, links and the first contact's name and phone. Email addresses are taken out of every field: an address in the text ("respond by email to ...") reads "the contact on the state's page" instead. The list is never pruned (124 rows, most past due or last touched in 2023), so a row whose due date has passed is dropped, and so is one with no due date unless its forecast says it is ongoing or rolling; both are listed in the skipped grants review. Who may apply is the state's own wording: one that names nonprofits, 501(c)(3) groups, community action agencies or "any legal entity" keeps the grant; one that names only governments, districts or businesses leaves nonprofits out; nonprofits named only as reviewers don't count; and a blank one is kept with a note to read the notice. Only a plain exclusion ("nonprofits are not eligible", "not open to nonprofits") closes a grant; unclear wording, a limit ("may not receive more than") or a partner route ("cannot apply directly") keeps it open with the state's words on the card. About 7 listings are current at a time.

## New Jersey state grants

The Treasury Grants Office's [State Grant Opportunities](https://www.nj.gov/treasury/grants-management/opportunities/state) page is read from a plain CSV beside it, one row per call: category, title, a link to the notice, the agency and the deadline (a date, or "Rolling"). `grantmatch/newjersey.py` reads it. The file has no description and no field for who may apply, so every call is kept with a note to read the notice, as Iowa's are when the description says neither way, except one whose title plainly says it is for municipalities or counties ("... Municipal Grants", "County Environmental Health Act Grants"), which is marked as not open to nonprofits unless the title also names nonprofits or a county college. Each call is keyed by its whole title, so "Round 1" and "Round 2" stay apart. A call whose deadline has passed is dropped. About 30 are open at a time, most of them Environmental Protection programs, and the page says the list isn't complete.

West Virginia and New Jersey have no refresh workflow yet: they ship from snapshots in `data/` (`westvirginia.json.gz`, `newjersey.json.gz`), which the export reads when the release has no copy. The export leaves out any call whose deadline has passed since the snapshot was made (for every open-call state, not Florida's catalog or the hand-kept lists), and the state tab says when its data was updated. Until the job is approved, nothing publishes their skipped lists and `skipped-report.yml` doesn't pass their data files, so they aren't in the Friday skipped grants report. The proposed job runs weekly (about 4 to 9 billed minutes a month): a call a state opens mid-week would show up to a week late, while closed calls still drop out at every site export. The job, the report change and their billed minutes are in [docs/state-coverage.md](docs/state-coverage.md).

## Adding a state

Every state and DC has one entry in `grantmatch/states.py`: its status (built, next, decide, html, none or unchecked) and its source. `unchecked` is for a state the research couldn't check (blocked, a captcha, not tested, or a check that couldn't be completed); the site's note for it claims nothing beyond "not read in yet". `STATE_PROGRAMS`, which the export reads, comes from the built entries, and the export publishes every state's status in `meta.json` so the site can say when a state has no catalog. To add a state, write an adapter that produces the same record fields as `ohio.py` (with `--out`, `--skipped` and past-deadline rows dropped), set its entry to `built` with its file, source, catalog label, module, `report` (its heading in the skipped grants review) and `refresh` (`None` until a refresh job is approved), and propose a refresh job. The site and `grantmatch/skipped.py` need no change: the report's sources, headings, arguments (`--<file>`) and expected files come from the registry, though `skipped-report.yml` still has to download the state's skipped file and pass its data file. Florida is in the registry too but keeps its own export, and `tests/test_florida_unchanged.py` checks that its records and scores stay the same.

## County and city programs

No public catalog lists county and city grants, community foundation and United Way grant cycles, children's services council calls, or the state agency calls Florida's catalog leaves out (federal money the state passes through, such as 21st Century Community Learning Centers, AmeriCorps and VOCA victim assistance, and statewide councils such as Florida Humanities), so they are kept by hand in `data/local-FL.json`, one entry per program, from the program's own page: the counties it serves, who can apply, whether it requires 501(c)(3) status, the application window when there is one, and the date the page was checked. `grantmatch/local.py` checks every entry (a bad date, an unknown county or a repeated name stops the export) and adds them to the Florida tab, keyed `fl:local-<slug>`. Each entry's `level` is `State`, `County`, `City`, `Children's services council` (the property-tax children's boards such as Pinellas' Juvenile Welfare Board), `Community foundation` or `United Way`; a statewide entry lists its counties as `["Statewide"]` and gets no place rule. They score like state programs, with two more rules: points off when your cities are outside the county, and when the program requires 501(c)(3) status you don't have yet. Word rarity and the similarity median are still measured on the state programs alone, so adding or editing an entry never changes a state program's score. The weekly website check reads each program's page, and its closing date goes into `changes.json` like a federal deadline.

Other states can have the same kind of list: `data/local-<ST>.json` (Illinois, Iowa, Ohio and Washington have one) joins that state's tab, keyed `local-<st>-<slug>` so keys never clash with Florida's. Deploys, the website check and the page watch pick up every state's file.

A program that takes applications any time gets `"rolling": true` (and no `closes`). One that is between rounds (no window open or announced, not rolling, and its website not saying applications are open at the last weekly check) loses 15 points and gets a "Between rounds" caution, so programs a nonprofit can apply to now or soon rank first; `score.ts` and `rank_more.py` apply the same rule.

To add or change one, edit the file from the official page, update `checked`, and run `python -m grantmatch.local` to check every state's file.

## Skipped grants review

Every refresh leaves some grants and funders out on purpose, and each one now says who and why, so the reasons can be checked rather than trusted:

| Source | Left out or hidden | Written by |
|---|---|---|
| Grants.gov | Open and forecasted opportunities nonprofits can't apply for, with who can (flagged when the eligibility notes mention nonprofits after all), and any whose details couldn't be read | `grantmatch/fetch.py --skipped` |
| California portal, Illinois notices, IowaGrants, Ohio list, FundHubWA, grants.wv.gov, New Jersey list | Rows dropped (deadline passed, no title, no due date and not rolling, listed twice), and calls the state says nonprofits can't apply for. West Virginia and New Jersey join the weekly report only once their refresh job is approved | `california.py`, `illinois.py`, `iowa.py`, `ohio.py`, `washington.py`, `westvirginia.py`, `newjersey.py` |
| Florida catalog | Programs not open to nonprofits, and money set aside for a named organization | read from `florida.json.gz` |
| Private foundations, community foundations | Every return read but not listed: no grants to organizations, funds only charities it picks with no way to apply, or no return in the two newest filing years | `foundations.py`, `community.py` (`skipped.jsonl.gz`) |

Each Friday `grantmatch/skipped.py` (workflow `skipped-report.yml`) joins them into `skipped-grants.csv` on the data-latest release, one row per grant or funder with a plain reason and the date it was first seen, and replaces the body of the open `skip-review` issue with counts by source and reason, what is new since last week, every federal and state row, and the largest foundations left out. A comment marks weeks with new entries. To record a decision, add a row to `data/skip-review.csv` (source, id, decision, note); every later report shows it. Decisions use `justified` (the skip is right), `check` (it may be wrong; read the notice), `fixed` (a filter rule was wrong and has been changed, so the grant now shows) `show` (a one-off the filter can't tell apart: the site build puts that state program back, with the note at the front of who can apply) and `hide` (the opposite: a state program listed as open to nonprofits that they can't really use, such as a student scholarship with no application; the site build takes it off and the report lists it as hidden after review). A shown state program whose eligibility was a guess ("read the notice") can be marked `confirmed`: the note, from the notice itself, replaces the guess on the card. Federal grants and foundations aren't affected by `show`, `hide` or `confirmed`.

## Sources researched and not added yet

- **New York.** The Grants Gateway and the SFS Vendor Portal list state opportunities but offer no public export. A third-party site (OpenGrants) publishes a daily CSV of New York state programs, but states no license for reuse, so it isn't used.
- **Other states, surveyed November 2026.** The states and DC that had no adapter before this change were surveyed again on November 25, 2026, and California, Illinois and Iowa were rechecked; [docs/state-coverage.md](docs/state-coverage.md) has what was recorded for each. West Virginia and New Jersey turned out to publish their lists as JSON and CSV and are now read. **Alaska**, **Hawaii** and **Pennsylvania** have machine-readable lists that aren't built: on 2026-11-25 Ren decided to leave them out (Pennsylvania left out; Hawaii and Alaska left out for now). Alaska's is an all-notices RSS feed with about one grant a week in the one snapshot taken, Hawaii's an undocumented procurement API where 6 posted titles contained "grant", with no eligibility field, Pennsylvania's the site's own search proxy. For 17 states and DC the grant pages checked are web pages, a bid board or a dashboard, not a data file (New York's SFS grid is the best scraper candidate), 4 had no current list anywhere the research looked (Arizona's is behind a login, Delaware has past awards only, and Maryland's and Oregon's lists are abandoned or empty), and 18 are unchecked: the research couldn't establish the answer, because the site turned scripts away (Colorado, Idaho, Kansas, Tennessee), showed a captcha (Minnesota), its data endpoint couldn't be verified (Texas), the notes don't say whether the pages seen list current calls (Louisiana, Oklahoma), or it wasn't tested.
- **Florida's state ad portal (MyFloridaMarketPlace).** Since March 2022 state agencies post solicitations in the Vendor Information Portal, which has a public search and an Excel export button but no published data feed. Its "Grant Opportunities" ad type had 71 ads from 2022 to November 2026 (mostly Children and Families and Health). The portal stopped answering scripted requests after a few searches, and an ad marked OPEN can be past its application deadline (the deadline is inside the RFA), so it isn't read automatically. Agencies' own funding pages are better sources: the Department of Health posts every RFA with its deadline on its Grant Funding Opportunities page.
- **Company programs.** `data/corporate.json` names 35 company foundations; 10 have a program written up from the company's own page (Walmart, Publix, Truist, TD Bank, Albertsons, Kroger, Mosaic, Duke Energy, Target, Bank of America). The rest are labels only until someone reads each company's giving page. Bank of America's pages build their text with scripts, so a plain fetch sees only the page shell; read them in a browser.

## Profile and shortlist on any device

On a paid plan the page saves the profile you last searched with (and the mission vector your browser made, so another device doesn't download the model) and the whole shortlist to the account, in the `profiles` and `shortlist_items` tables (`supabase/migrations/20261120140000_saved_workspace.sql`, `web/src/sync.ts`, `web/src/accountsync.tsx`). Another device that signs in loads them: the saved profile replaces the example unless you already searched this visit, and the shortlist follows the rules below.

- The browser keeps its own copy as before, and remembers which account and version it came from and whether it changed since.
- On sign-in a clean copy takes the account's; a changed one, or one never linked to an account, is merged with the account's and saved. A copy from a different account is replaced, never mixed in.
- A save names the version it started from. If another device saved in between, the server returns its copy, the page merges the two (every item on either list, the newer copy of each) and saves again. A grant removed on one device while another changed the list can come back; removing it again sticks.
- The "On any device" box shows the last save time, or says when a save or load failed. A failed save stays marked as changed in the browser and is tried again after 30 seconds, when the connection comes back, or on the next visit.
- "Stop saving and delete the account copy" turns it off and deletes the saved profile and shortlist. Free accounts keep everything in the browser only.

## Consultant client profiles

A Consultant account keeps up to 10 client profiles (`supabase/migrations/20261120180000_client_profiles.sql`, `web/src/clients.tsx`). A Client menu above the profile opens a client: the page saves anything not yet saved for the one on screen, then loads the other's profile and shortlist. A new client starts blank. Rename and Delete act on the client that's open; the last one can't be deleted. Each device remembers the client it last had open. Pro keeps a single profile and sees no menu.

**Emails** (`supabase/migrations/20261120200000_client_emails.sql`). The weekly email is turned on per client and uses that client's saved profile; each client remembers which matches it was already sent. The account picks one email per client or one combined email with a section for each client. Deadline reminders cover every client's shortlist: turning them on sends each client's open deadlines, and after that the open client's set follows its shortlist. Each reminder says which client the grant is for. A Consultant account that had the weekly email before clients keeps it for its first client.

## Signing in

People sign in with a code sent by email, or with Google; there are no passwords (`web/src/signin.tsx`). The Google button shows only once the Google provider is switched on in Supabase (the page reads Supabase's public auth settings). Google sends people back to the page, which finishes the sign-in itself (PKCE). Someone who used the email code before and then picks Google with the same address gets the same account.

Google setup (done Nov 2026): the Google Cloud project "Grant Matcher" (`grant-matcher-515400`) belongs to ren@solutionsbyrich.com, a free Cloud Identity account on the verified solutionsbyrich.com domain. Its web OAuth client "Grant Matcher web" has one redirect URI, `https://lthfecwgvpekrjjqszof.supabase.co/auth/v1/callback`, and no JavaScript origins, since sign-in goes through Supabase. The client ID and secret live only in Supabase (Authentication, Sign In / Providers, Google). Supabase's Site URL is `https://rendellrich.github.io/grant-matcher/` and `https://rendellrich.github.io/grant-matcher/**` is its only redirect URL.

Google's sign-in screen shows "Grant Matcher" because the branding is verified. That depends on the branding page listing only domains we own: solutionsbyrich.com is the one authorized domain, and the home page, privacy policy and terms links all point to solutionsbyrich.com/grant-matcher. Google adds a domain to that list whenever a client URI uses it, so after editing the client, check that the Supabase and github.io domains have not come back. If they have, remove them and save, or the screen falls back to showing the Supabase address.

Rotating the secret: Google shows a new secret only once. Add a secret on the client, paste it into Supabase's Google provider and save, check that Google sign-in still works, then disable the old secret.

## When a paid plan ends

When Stripe ends a subscription, the webhook moves the account to Free and the database dates it (`plan_ended_at`, `supabase/migrations/20261120220000_lapsed_cleanup.sql`). What the account saved (profiles and shortlists, Consultant clients, the weekly email's profile, deadline reminders) is kept for a year in case the person comes back, then a daily job deletes it. The account itself stays, so the person can still sign in on Free. Paying again clears the date.

## Can we apply?

Every card ends with a short checklist of what usually stops a small nonprofit, checked against the profile (`web/src/ready.ts`): whether 501(c)(3) status is required, whether SAM.gov registration is needed (every federal grant; others when their text says so), whether a match is required, whether it pays by reimbursement or is a loan, and whether it is taking applications now (open, not open yet, between rounds, invitation only, not taking requests). Each source says different things, so each gets its own reader, and a check is left out when the record doesn't say. The profile's registrations ("SAM.gov and a UEI") turn the SAM.gov check green. It never changes a score; the caution and status lines it repeats stay off the card but still drive the filters and the CSV.

## One-page summaries

Every card's details end with "Copy one-page summary" and "Download as text", and the shortlist downloads them all in one file (`web/src/summary.ts`). A summary is plain text a grant writer can paste into a document or another tool: the name, the funder and link, the deadline or typical size, the "Can we apply?" checks as sentences, why it fits, the cautions, how to apply and the contact, the summary and largest grants, and the date it was made. It is built only from what the card shows.

## Company foundations

The IRS data can't tell a company's foundation from a family's. `data/corporate.json` names company foundations by EIN, the company behind each, and, where the company's own giving page says so, the local program a small nonprofit can apply to: who can apply, the amount, when and how. `grantmatch/corporate.py` checks the file, and the foundation cards show the company and its program, with a filter for company foundations. Only one part changes a score: when the company's page limits its grants to named counties (`"counties": {"FL": [...]}`, as Duke Energy's Florida page does), the foundation is scored like a county program. Work in those counties gets a reason, work elsewhere loses 40 points with a caution, and a profile with no cities gets a smaller penalty and a prompt to add them. County names are checked against `data/counties.json.gz`. Markets the company names only loosely (Bank of America's "Tampa Bay") stay as text, since the counties they cover aren't stated.

Both hand-kept lists go stale when a program changes after it was entered. Every Thursday `grantmatch/watch.py` (workflow `watch-pages.yml`) reads each page the two files point to, HTML, PDF or Word, and compares it with last week's reading, kept as `watch-state.json.gz` on the data-latest release. It opens or adds to a `page-watch` issue listing new status wording ("on hold", "now accepting", "applications are closed"), sentences added or removed, blank pages, pages it could not reach and entries checked more than 90 days ago. It never edits an entry: a person reads the page, updates the entry and sets its `checked` date. Some government sites turn away automated readers; those show as "could not reach" and need a look in a browser.

A national program run through local stores, such as Walmart's Spark Good grants, is listed in every state it serves, even when the foundation's IRS return names other states among the top 12 it gave to. Without that, the Walmart Foundation was missing from Florida's list.

## Giving over several years

The foundation refresh reads six IRS filing years, enough for five tax years per foundation, and `grantmatch/history.py` keeps a short summary of each foundation's giving across them: grants per year, whether it gave in each of the last four years, the share of its latest year's grantees it hadn't funded before (grantee names are matched loosely, so "Reading Club, Inc." and "The Reading Club" are the same), and, for each state's file, the cities there it has funded with the first year it did. The foundation cards show "Gave every year from 2021 to 2024", "39% of its 2024 grantees were new to it" and "Its first grants to Palmetto came in 2024", a grants-by-year row, and a filter for each. None of this changes a score.

## Coverage

Federal grants cover the whole country, and foundations cover every state and DC. State grant catalogs cover 8 states and hand-kept county and city programs 5; [docs/state-coverage.md](docs/state-coverage.md) audits every source and every state. "What the data covers" in the site's footer shows the foundation numbers state by state.

`grantmatch/coverage.py` compares the IRS Exempt Organizations Business Master File with the state files after each foundation refresh:

- **Registered:** private foundations based in the state (those required to file Form 990-PF).
- **E-filed:** of those, a return in the IRS e-file index for the two newest filing years, which is what the refresh can read.
- **Listed:** foundations in the state's file. A foundation is listed only when its latest return shows grants to organizations and it doesn't say it only funds preselected charities, so this is never meant to reach 100%.
- **Giving here:** every listed funder based in the state or with grants there.

Each refresh also writes `parsed.json` beside the state files: per state, how many returns it read and how many were listed, paid no grants, or fund only preselected charities. The report carries those counts once a refresh has run with them. `data/coverage.json` is the snapshot the site falls back to.

## Data

A GitHub Action runs twice a day and pulls every posted and forecasted opportunity open to nonprofits (eligibility codes 12, 13, 25 and 99) from the public [Grants.gov API](https://www.grants.gov/api/api-guide) using `search2` and `fetchOpportunity`. No API key is needed. The cleaned file and the opportunity embeddings are published as `data-latest` release assets, and the app reads them from there. A snapshot in `data/` is the fallback. If the embedding model cannot load, the app falls back to TF-IDF similarity.

| Source | Refresh | Job |
|---|---|---|
| Grants.gov (`search2`, `fetchOpportunity`) | twice a day | `refresh-data.yml` |
| IRS Form 990-PF e-file XML ([Form 990 series downloads](https://www.irs.gov/charities-non-profits/form-990-series-downloads)), latest return per foundation, split by state, every state | monthly | `refresh-foundations.yml` |
| IRS Form 990 Schedule I for organizations the [Exempt Organizations Business Master File](https://www.irs.gov/charities-non-profits/exempt-organizations-business-master-file-extract-eo-bmf) codes T31 (community foundations), T30 (public foundations), and T70 (United Ways and federated funds) | monthly | `refresh-foundations.yml` |
| [California Grants Portal](https://data.ca.gov/dataset/california-grants-portal) open data, open and forecasted calls | daily | `refresh-california.yml` |
| Illinois [CSFA list of open funding notices](https://omb.illinois.gov/PUBLIC/GATA/CSFA/OpportunityList.aspx) and each notice's page | daily | `refresh-illinois.yml` |
| [IowaGrants.gov](https://www.iowagrants.gov/storefrontFOList.do) posted opportunities and each one's page | daily | `refresh-iowa.yml` |
| [Ohio Grants Partnership](https://grants.ohio.gov/funding-opportunities/find-current-opportunities) current opportunities (JSON) | daily | `refresh-ohio.yml` |
| [FundHubWA](https://fundhub.wa.gov/funding/) state-funded listings (WordPress JSON API) | daily | `refresh-washington.yml` |
| [grants.wv.gov](https://grants.wv.gov/) AvailableGrants list (SharePoint REST, JSON) | snapshot in `data/`, made November 25, 2026 | none yet (a weekly job is proposed in docs/state-coverage.md) |
| New Jersey Treasury [State Grant Opportunities](https://www.nj.gov/treasury/grants-management/opportunities/state) (CSV) | snapshot in `data/`, made November 25, 2026 | none yet (a weekly job is proposed in docs/state-coverage.md) |
| Pages behind the hand-kept lists (`local-FL.json`, `corporate.json`) | weekly | `watch-pages.yml` |
| Skipped grants review (`skipped-grants.csv` and the `skip-review` issue) | weekly | `skipped-report.yml` |
| Florida [Catalog of State Financial Assistance](https://apps.fldfs.com/fsaa/catalog.aspx), current fiscal year | weekly | `refresh-florida.yml` |
| Each foundation's own website (the home page and the grants or apply page it links to), for an open cycle, a deadline ahead, an application link, or a note that it isn't taking requests | weekly | `refresh-websites.yml` |

The website check (`grantmatch/cycles.py`) honors robots.txt, identifies itself, reads at most two pages per site, and visits a site shared by several funders once. The site quotes the sentence it found, with the page and the date checked, since a page can change after it was read. It never changes a score.

## Run it yourself

```bash
pip install -r requirements.txt
python -m grantmatch.fetch --out data/opportunities.json.gz   # about 20 minutes; add --limit 50 for a quick test
python -m grantmatch.embed federal data/opportunities.json.gz data/embeddings.npz
pip install -r requirements-data.txt
python -m grantmatch.foundations --years 2025,2026 --out data/foundations      # about 15 minutes, 7 GB of downloads
python -m grantmatch.embed foundations data/foundations/FL.json.gz data/foundations/FL.npz
python -m grantmatch.community --years 2025,2026 --out data/community          # about 5 minutes
python -m grantmatch.embed foundations data/community/FL.json.gz data/community/FL.npz
python -m grantmatch.florida --out data/florida.json.gz                        # about 25 minutes
python -m grantmatch.embed florida data/florida.json.gz data/florida.npz
python -m pytest -q

# the public site
python -m grantmatch.export_web web/public/data   # add --local to use only the snapshot in data/
cd web
npm ci
npm run model    # puts the matching model beside the site
npm run dev

# the parity test: Python's scores for the examples, then the same profiles in TypeScript
python -m grantmatch.export_web web/test-data --local --golden web/test-data/golden.json
cd web && npm test

# the Streamlit app and workspace
streamlit run app.py
```

## Project layout

```
web/                    the public site: Preact app, TypeScript scoring, parity test
grantmatch/export_web.py  data and embeddings for the site, and Python's scores for the parity test
app.py                  Streamlit app (public search and the signed-in workspace)
grantmatch/fetch.py     Grants.gov pull and cleanup
grantmatch/embed.py     semantic embeddings (twice a day for grants, on demand for a mission)
grantmatch/embed_states.py  foundation embeddings for every state: each foundation once, reused between runs
grantmatch/match.py     federal scoring, reasons, calendar export
grantmatch/foundations.py  IRS 990-PF parsing, split by state
grantmatch/community.py IRS 990 Schedule I for community foundations and United Ways
grantmatch/florida.py   Florida Catalog of State Financial Assistance
grantmatch/california.py  California Grants Portal open calls
grantmatch/illinois.py  Illinois open funding notices (GATA/CSFA)
grantmatch/iowa.py     IowaGrants.gov posted opportunities
grantmatch/ohio.py     Ohio Grants Partnership current opportunities
grantmatch/washington.py  FundHubWA open state-funded listings
grantmatch/westvirginia.py  grants.wv.gov available grants
grantmatch/newjersey.py  New Jersey Treasury state grant opportunities
grantmatch/states.py   every state's catalog status and source; STATE_PROGRAMS comes from it
grantmatch/local.py     Florida programs entered by hand: state calls, county and city grants, community foundation cycles
grantmatch/skipped.py   the weekly list of grants left out, and why
grantmatch/corporate.py company foundations and their local programs (data/corporate.json)
grantmatch/watch.py     weekly check of the pages behind both hand-kept lists
grantmatch/history.py   each foundation's giving across five tax years
grantmatch/coverage.py  registered foundations per state against what the state files hold
grantmatch/rank_more.py foundation and Florida scoring
grantmatch/store.py     private workspace storage (GitHub repo or local folder)
grantmatch/workspace.py pipeline, organization facts, answer library, documents
grantmatch/writer.py    Claude drafting, Word export, and form filling
grantmatch/ui_workspace.py  workspace screens
tests/                  unit tests for scoring and parsing
PRODUCT.md              who it's for and the product's rules
DESIGN.md               design system: colors, type, components, and accessibility rules
docs/images/            README screenshots
docs/state-coverage.md  what each source covers, state by state, and the next states to add
.github/workflows/      data refreshes, tests, and the site deploy
```

## Roadmap

- More states' grant catalogs: 18 unchecked states need a look in a browser, and for 17 states and DC the grant pages checked are web pages, a bid board or a dashboard rather than a data file (docs/state-coverage.md). Alaska, Hawaii and Pennsylvania were left out by decision on 2026-11-25

## Why I built it

I'm a data scientist and the CTO of Exceed the Odds, a founding-stage nonprofit that provides literacy, speech, and tutoring support to children at no cost or on a sliding scale. We fund that work with grants, and I wanted a faster way to find the ones worth our time.

Built by [Rendell Rich](https://rendellrich.github.io). MIT License.
