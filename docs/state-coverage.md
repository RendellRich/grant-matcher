# State coverage

What Grant Matcher covers in each of the 50 states and the District of Columbia, checked November 25, 2026. The state-by-state research behind section (b) was done the same day with anonymous requests only (no accounts, keys, sign-ups or terms). The registry that the code reads is `grantmatch/states.py`; this page explains it.

**Short answer.** Federal grants, private foundations, community foundations and the county list cover all 50 states and DC. State grant catalogs cover 8 states (Florida, California, Illinois, Iowa, Ohio, Washington, and, new in this change, West Virginia and New Jersey). In the other 42 states and DC the site says plainly that there is no state catalog yet and that federal grants and foundations still cover the state. Of those 43: 3 have a machine-readable list that Ren decided on 2026-11-25 to leave out (Alaska, Hawaii, Pennsylvania), for 18 the grant pages checked are web pages or a dashboard, not a data file, 4 had no current list anywhere the research looked, and 18 are **unchecked**: the research couldn't establish the answer (blocked, a captcha, not tested, or a check that couldn't be completed), so the site claims nothing about them. County and city programs are hand-kept for 5 states.

## (a) Audit by data source

| Data source | All 50 states? | DC? | Evidence |
|---|---|---|---|
| Federal opportunities (Grants.gov) | Yes, national | Yes | One national pull (`grantmatch/fetch.py`, eligibility codes 12, 13, 25 and 99) into release asset `opportunities.json.gz`. Every profile reads the same `federal` file (`export_web.py`, `write(out, "federal", ...)`). A title that names another state loses points (`match.py` `other_places`, `score.ts` `otherPlaces`), so the list is national but ranked for the profile's state. |
| Private foundations (IRS 990-PF) | Yes | Yes | Release assets `foundations-<ST>.json.gz` exist for 62 codes: all 50 states and DC, plus AA, AE, AP, AS, FM, GU, MH, MP, PR, PW and VI (`gh release view data-latest --json assets`). The release's `states.json` lists 59 of them (all but AE, AS and MH). `export_web.foundation_states()` exports the union of that list and the snapshot in `data/`. |
| Community foundations, public foundations, United Ways (990 Schedule I) | Yes | Yes | Release assets `community-<ST>.json.gz` for all 50 states and DC, plus GU, PR, PW and VI. They join each state's foundation file in `export_web.main()`. `data/coverage.json` (made 2026-11-19) has 61 rows and 53 states with data. |
| Corporate foundations (`data/corporate.json`) | Partly, by design: Walmart's and Target's programs are listed in every state, the others where they give | Yes: Walmart and Target (every state and DC) and Bank of America | 35 company foundations, based in 16 states. Four have a program listed outside their home state: Walmart and Target serve every state and DC (`"serves": "*"`), Bank of America lists 41 markets including DC, Publix 8 states in the Southeast. County limits exist only for Florida (Duke Energy). The others show in the states where their IRS return says they give. This is a hand-kept overlay on the foundation files, not a separate source, so it doesn't need to reach every state. |
| State programs | No: 8 states | No | Florida (`florida.json.gz`), California, Illinois, Iowa, Ohio and Washington from release assets (`california.json.gz`, `illinois.json.gz`, `iowa.json.gz`, `ohio.json.gz`, `washington.json.gz`), and West Virginia and New Jersey from snapshots in `data/` (`westvirginia.json.gz`, `newjersey.json.gz`) until a refresh job is approved. Listed in `grantmatch/states.py` (`STATE_PROGRAMS`); every state's status goes into `meta.json` as `catalogs`. Section (b) gives the reason for each state without one. |
| County and city programs (`data/local-*.json`) | No: 5 states | No | `data/local-FL.json`, `local-IA.json`, `local-IL.json`, `local-OH.json`, `local-WA.json`, kept by hand (`grantmatch/local.py`). They join that state's tab. |
| Counties list (`data/counties.json.gz`) | Yes | Yes | 56 codes: all 50 states, DC (one county, the District itself), and AS, GU, MP, PR, VI. `export_web.main()` writes `counties-<ST>.json` for each. |
| State picker | Yes | Yes | `web/src/score.ts` line 32 (`STATE_NAMES`, used by `web/src/profile.ts` line 5 `STATES`) and `grantmatch/display.py` lines 8 and 12 list the 50 states, DC and Puerto Rico. Puerto Rico is the only territory in the picker; it has foundation files and gets the same "no catalog" note as a state without one. Other territories aren't in the picker and are out of scope. |

## (b) Each state

Status (the registry's value in brackets):

- **built** (`built`): an adapter reads the state's own list. **built this PR** marks West Virginia and New Jersey.
- **left out by decision** (`decide`): a machine-readable list works but isn't built, because Ren decided on 2026-11-25 to leave it out; section (c) gives the reasons.
- **HTML only** (`html`): the grant pages checked are web pages, a dashboard or a bid system, not a data file.
- **none found** (`none`): nowhere the research looked has a current public list of state grant calls: past awards only, a login wall, or a list that is empty or abandoned. If any page it looked at posts current state calls (a bid board, an agency calendar), the state is HTML only instead; if the notes don't say either way, it is unchecked.
- **unchecked** (`unchecked`): the research couldn't establish the answer. The site was blocked to scripts, showed a captcha, or wasn't tested, or a check couldn't be completed (for Texas, the research session's own permission check blocked the probe of its data endpoint). Nothing is claimed; the notes say only what was seen. The page's note for these says only that the state's grants aren't read in yet.
- `next` (an adapter worth building next) is in the registry but no state has it now.

| State | Status | Source | Format | Data URL | Notes |
|---|---|---|---|---|---|
| Alabama | HTML only | ADECA Funding Opportunities and Grant Calendar | HTML (WordPress) | https://adeca.alabama.gov/about/funding-opportunities/ | One agency, not statewide. The site's RSS is news posts. |
| Alaska | left out by decision | State of Alaska Online Public Notices | RSS 2.0 | https://aws.state.ak.us/OnlinePublicNotices/Feeds/RSS.aspx | Machine-readable, not built. The feed holds the 100 newest notices of every kind, about 9 days' worth; 1 of the 100 was a grant. No agency, deadline or eligibility fields. A bot check guarded the help page. Left out by decision on 2026-11-25; section (c) gives the reasons. |
| Arizona | none found | grants.az.gov, which points to Euna Grants (eCivis) | n/a | https://grants.az.gov/funding-opportunities-0 | The listings are behind a subscriber login. |
| Arkansas | unchecked | DFA Intergovernmental Services grant program pages | HTML | https://www.dfa.arkansas.gov/office/intergovernmental-services/grant-programs/ (not tested) | Found by search only. The search showed program pages spread across agencies; no central portal turned up, but none was tested. |
| California | built | California Grants Portal | CSV | https://data.ca.gov/dataset/california-grants-portal | Daily refresh (`grantmatch/california.py`). |
| Colorado | unchecked | OEDIT Programs and Funding; SIPA govgrants | HTML | https://oedit.colorado.gov/programs-and-funding (403 CloudFront); https://sipa.colorado.gov/govgrants (403) | Blocked to scripts, so what these pages hold is unknown. data.colorado.gov's catalog search for "grant" found only charity financials, no opportunities. |
| Connecticut | HTML only | CTsource Bid Board; data.ct.gov (awards) | HTML bid board; Socrata, awards only | https://portal.ct.gov/das/ctsource/bidboard (page); https://api.us.socrata.com/api/catalog/v1?domains=data.ct.gov&q=grant | Nonprofit Grant Program rounds are posted on the CTsource bid board, a public page, and no export was found there. data.ct.gov has past awards only (for example qcgq-9p42, 2014 OPM Nonprofit Grant Program Awards). |
| Delaware | none found | data.delaware.gov | Socrata, awards only | https://api.us.socrata.com/api/catalog/v1?domains=data.delaware.gov&q=grant | Grant-in-Aid is a legislative application system, not a list of calls. |
| District of Columbia | HTML only | District Grants Clearinghouse (Serve DC) | HTML; weekly Funding Alert PDFs | https://communityaffairs.dc.gov/node/26 | No feed found; whether the Drupal topic page has RSS is unverified. |
| Florida | built | Catalog of State Financial Assistance | HTML catalog | https://apps.fldfs.com/fsaa/catalog.aspx | Weekly refresh (`grantmatch/florida.py`), plus county programs by hand. |
| Georgia | HTML only | Georgia Grants Portal (OPB) | HTML (Power Pages) | https://cares.georgia.gov/grantopportunities/ | One office, not statewide, and empty when checked. |
| Hawaii | left out by decision | HANDS (Hawaii Awards and Notices Data System) | JSON (POST) | https://hands.ehawaii.gov/hands/api/bidding-opportunities | Machine-readable, not built. An undocumented API behind the public page, mostly procurement: 6 of 185 posted items had "grant" in the title. No description or eligibility field. Left out by decision on 2026-11-25; section (c) gives the reasons. |
| Idaho | unchecked | Idaho Commerce grants page | HTML | https://commerce.idaho.gov/incentives-and-financing/grants (403 Cloudflare challenge) | Blocked to scripts. The research note names separate agency pages (Commerce, Arts, Parks, State Board of Education); none was read. |
| Illinois | built | CSFA list of open funding notices (GATA) | HTML | https://omb.illinois.gov/PUBLIC/GATA/CSFA/OpportunityList.aspx | Daily refresh (`grantmatch/illinois.py`). |
| Indiana | HTML only | State Agency Grant Opportunities (Euna Grants list) | HTML iframe; PDF | https://gn.ecivis.com/GO/gn_redir/T/mk3lzl56q0ht/iframe/true | 1 open when checked. Public, no login, but no feed. |
| Iowa | built | IowaGrants.gov | HTML | https://www.iowagrants.gov/storefrontFOList.do | Daily refresh (`grantmatch/iowa.py`). |
| Kansas | unchecked | grants.ks.gov; KS Infrastructure Hub; Commerce grants calendar | HTML / PDF | https://www.grants.ks.gov/ (403 Akamai); https://www.kshub.gov/iija/open-grant-opportunities (403); https://www.kansas.gov/grants/index.do (404) | Blocked to scripts, so the pages weren't read. The research note also says applications need a login; how that was learned isn't recorded. Commerce publishes a yearly PDF grants guide (https://kansascommerce.gov/grantscalendar/, not opened). |
| Kentucky | unchecked | CHFS Grant Opportunities, KDE Competitive Grants, eMARS public access | HTML | https://chfs.ky.gov/agencies/os/oas/Pages/grants.aspx (not tested) | Found by search only. The search suggests solicitations go through eMARS Vendor Self Service; nothing was opened. |
| Louisiana | unchecked | LaPAC (procurement); LED monthly Opportunity Roadmap (PDF) | HTML / PDF | https://wwwcfprd.doa.louisiana.gov/osp/lapac/pubmain.cfm | LaPAC answered (200) and is procurement bids, not a grant list. LED publishes a monthly Opportunity Roadmap PDF that mixes federal, state and private items; the research note records no link and the PDF wasn't opened, so whether it lists current state grant calls is unknown. LDOE eGMS covers education allocations only. |
| Maine | HTML only | Maine Community Funding Finder | HTML (Drupal view) | https://www.maine.gov/moca/funding | 62 items, aimed at communities; no nonprofit applicant type. |
| Maryland | none found | grants.maryland.gov SharePoint list | JSON (SharePoint REST) | https://grants.maryland.gov/_api/web/lists/getbytitle('Maryland%20State%20and%20Foundation%20Grants')/items?$filter=Approved%20eq%201&$top=5000 | Machine-readable but abandoned: nothing added after September 2023, nothing open. Not worth an adapter. |
| Massachusetts | HTML only | COMMBUYS public bid search | HTML (JSF app) | https://www.commbuys.com/bso/view/search/external/advancedSearchBid.xhtml | Grants posted as bids; results need form postbacks. |
| Michigan | HTML only | MI Funding Hub | JS app | https://mifundinghub.org/find-funding/ | Undocumented admin-ajax call with a page nonce; aimed at local governments. |
| Minnesota | unchecked | Office of Grants Management, Find a Grant | HTML | https://mn.gov/grants/find-a-grant/ (200, but a Radware bot captcha) | The captcha wasn't passed, so the list wasn't seen. https://mn.gov/grants/search/json.jsp returns JSON, but it is the site's page search, not opportunities. |
| Mississippi | unchecked | Agency pages (for example MDHS Grant Opportunities) | HTML | https://www.mdhs.ms.gov/ (not tested) | Not tested; the research note names no statewide portal. |
| Missouri | unchecked | Agency pages; data.mo.gov | n/a | https://moarpa.mo.gov/grant-programs/ (not tested) | Only data.mo.gov was checked: its catalog search found ARRA and federal expenditure data from 2012 to 2017, no opportunities. Agency pages weren't opened. |
| Montana | HTML only | WebGrants storefront | HTML | https://funding.mt.gov/outsideStorefrontList.jsp | 4 listed, mostly expired. |
| Nebraska | unchecked | Agency pages; DED uses AmpliFund (an application system) | n/a | https://opportunity.nebraska.gov/ (not tested) | Not tested. |
| Nevada | HTML only | Office of Federal Assistance, Grant Opportunities | Airtable view | https://airtable.com/appnYtlggE8fe6n3H/shrev4GTlV51q2EJD | The Airtable API needs a key. |
| New Hampshire | unchecked | none named | n/a | none: the research notes give no URL | Nothing was tested; no source is named. |
| New Jersey | built this PR | Treasury Grants Office, State Grant Opportunities | CSV (no header) | https://www.nj.gov/treasury/grants-management/opportunities/state/state-data.csv | 37 rows, 31 open on November 25. Columns category, title, url, agency, deadline. No eligibility field, so every call says to read the notice, except 2 whose titles say municipal or county grants, marked not open to nonprofits. The page says the list isn't complete. |
| New Mexico | unchecked | SHARE NM (PeopleSoft) | n/a | none: the research notes give no URL | Not tested. SHARE NM is reportedly login-based (unverified); data.nm.gov's catalog query failed. |
| New York | HTML only | Statewide Financial System, Search for Grant Opportunities | HTML (PeopleSoft grid) | https://esupplier.sfs.ny.gov/psc/fscm/SUPPLIER/ERP/c/NY_SUPPUB_FL.AUC_RESP_INQ_AUC.GBL | Has a Not-For-Profit eligibility value and due dates; the only export needs a postback. Best scraper candidate. |
| North Carolina | HTML only | NC.gov Grant Opportunities | HTML table | https://www.nc.gov/your-government/all-nc-state-services/grant-opportunities | About 74 programs, no deadlines. |
| North Dakota | HTML only | WebGrants storefront | HTML | https://grants.nd.gov/storefrontFOList.do | 2 rows. |
| Ohio | built | Ohio Grants Partnership current opportunities | JSON | https://api.obm.ohio.gov/grants/getfundingopportunities/0/0/1 | Daily refresh. This is the list `grantmatch/ohio.py` reads (`LIST`). The public page the adapter links when an opportunity has no detail page, https://grants.ohio.gov/funding-opportunities/find-current-opportunities, returned 404 to a script on 2026-11-25 (as did https://grants.ohio.gov/). |
| Oklahoma | unchecked | OK Grants; agency pages | login portal; HTML | https://grants.ok.gov/ | OK Grants redirects to a login page, and its opportunity search needs registration. data.ok.gov has only old funding summaries and OTAG awards. The research note says agency pages (Arts Council, OSDE, Homeland Security) are HTML only, but not whether they list current calls. |
| Oregon | none found | OHCS and ODHS/OHA Housing Grant Opportunities | Socrata JSON | https://data.oregon.gov/resource/8e87-r9yi.json | Machine-readable but housing only and empty ("No opportunities at this time"), as is https://data.oregon.gov/resource/qqzc-277f.json. Not worth an adapter unless Oregon fills them. |
| Pennsylvania | left out by decision | pa.gov Discover State Grants | JSON (POST) | https://www.pa.gov/cv-pxy/rest/search/v2 | Machine-readable, not built. 380 grants, 80 accepting applications, an applicant type field with Nonprofit (125). But it is the site's own search proxy, not a published feed. Left out by decision on 2026-11-25; section (c) gives the reasons. |
| Rhode Island | HTML only | Grants Management Office funding opportunities (Euna Grants list) | HTML table | https://gn.ecivis.com/GO/gn_redir/T/vijhe5b15ds1/iframe/true | About 9 open; clean HTML. |
| South Carolina | unchecked | Agency pages (SCDE, SC Energy, SCORF, BHDD) | HTML | https://ed.sc.gov/finance/grants/scde-grant-opportunities/ (one agency; not tested) | Not tested; data.sc.gov didn't respond. |
| South Dakota | unchecked | Agency pages and news posts on sd.gov | HTML | https://www.sd.gov/sdac?id=cs_kb_article_view&sysparm_article=KB0045433 (not tested) | Not tested; data.sd.gov didn't respond. |
| Tennessee | unchecked | Central Procurement Office grant page; Rural Development printable list | HTML / DOCX | https://www.tn.gov/generalservices/procurement/central-procurement-office--cpo-/library-/grant-funding-information.html (403 to scripts) | Blocked to scripts and WebFetch; the printable DOCX list wasn't opened. |
| Texas | unchecked | Electronic State Business Daily, Grants | JS app (NetSuite backend) | https://www.txsmartbuy.gov/esbd | The statewide grant list since November 2024 (per the research note). The site's script has a CSV export routine, but no public data endpoint could be verified: the research session's own permission check blocked the probe. An earlier survey in this repo (November 2026) found that its robots.txt disallows crawling. |
| Utah | HTML only | Utah Funding Opportunities Portal | Looker Studio report | https://gopb.utah.gov/funding-resources/ (links the report) | No export without a Google login. |
| Vermont | HTML only | Agency grant pages (for example the Agency of Agriculture grants calendar); data.vermont.gov Grants Issued | HTML; Socrata, awards only | agriculture.vermont.gov/grants/calendar (as given in the research note); https://data.vermont.gov/resource/xifk-zskz.json (awards) | The research note says opportunities are on agency pages, HTML only, for example the Agriculture grants calendar. data.vermont.gov lists grants issued (77,050 awards), not open calls. |
| Virginia | HTML only | Governor's Office Grants directory | HTML table | https://www.governor.virginia.gov/constituent-services/grants/ | About 58 rows, free-text application periods, some stale. |
| Washington | built | FundHubWA | JSON (WordPress) | https://fundhub.wa.gov/funding/ | Daily refresh (`grantmatch/washington.py`, through the site's WordPress JSON API). |
| West Virginia | built this PR | grants.wv.gov AvailableGrants list | JSON (SharePoint REST) | https://grants.wv.gov/_api/web/lists/getbytitle('AvailableGrants')/items?$top=500 | 124 rows, never pruned: 7 kept on November 25 (83 past due, 34 with no due date and not rolling). Who may apply is the state's EntityEligible text; 4 of the 7 are open to nonprofits. The REST API is the site's own, not a published open-data feed. |
| Wisconsin | unchecked | Agency pages (DHS solicitations, DOJ, DNR, DATCP, DOA) | HTML | https://www.dhs.wisconsin.gov/business/solicitations-list.htm (one agency; not tested) | Not tested; data.wi.gov didn't respond. |
| Wyoming | HTML only | Wyoming Grants Connect Hub | Power BI report | https://sbd.wyo.gov/grants | No documented export. |

Counts: 6 built before this change, 2 built this PR, 3 left out by decision, 18 HTML only (DC included), 4 none found, 18 unchecked. Total 51.

## (c) Left out by decision, and what's left

Three states have a machine-readable list that isn't built. Each went to Ren for a decision; the recommendation for all three was to leave them out for now, and the table keeps the reasons.

**Ren's decisions, 2026-11-25:**

- **Weekly refresh for West Virginia and New Jersey: approved.** The job is not on this branch yet: writing `.github/workflows/refresh-states.yml` wasn't permitted in the session that made this change, so the job in section (d) is still a proposal, and the committed snapshots in `data/` are what ship until the workflow is added.
- **Pennsylvania: left out.**
- **Hawaii and Alaska: left out for now.**

| State | What works | Recommended | Why |
|---|---|---|---|
| Alaska | Online Public Notices RSS (`https://aws.state.ak.us/OnlinePublicNotices/Feeds/RSS.aspx`), filtered to `<category>Grants</category>` | Leave out for now | It is a feed of every public notice, not a grant list: 1 of its 100 newest notices was a grant, and the 100 cover about 9 days, so roughly one grant a week. That rate rests on a single snapshot of the feed. Items age out in about 9 days, so a weekly refresh could miss some in a busy week, and deadline and eligibility would have to be read from the notice text. |
| Hawaii | HANDS JSON (`POST https://hands.ehawaii.gov/hands/api/bidding-opportunities?size=200&page=0&sort=publish_date_dt,desc` with `{"statuses":["POSTED"], ...}`) | Leave out for now | An undocumented API behind the procurement page: 6 of 185 posted items had "grant" in the title, with no description and no eligibility field, so every card would only say "read the notice". It could change without notice. |
| Pennsylvania | pa.gov grant search (`POST https://www.pa.gov/cv-pxy/rest/search/v2`): 380 grants, 80 accepting applications, an applicant type with Nonprofit (125) | Leave out | The best data of any state not built, but it is the site's internal search proxy, not a published feed. It could be locked down or close at any time. |

**HTML only, worth a scraper later** (each would be the state's first catalog): New York (SFS grid, with a Not-For-Profit eligibility value), Rhode Island and Indiana (public Euna Grants lists), Virginia (Governor's directory), North Carolina (program table). Check each site's terms and robots.txt first.

**Not worth it now:** Maryland (abandoned since 2023), Oregon (housing only, empty), Montana and North Dakota (2 to 4 rows).

**Unchecked, needs a look in a browser:** Arkansas, Colorado, Idaho, Kansas, Kentucky, Louisiana (open the Opportunity Roadmap PDF), Minnesota, Mississippi, Missouri, Nebraska, New Hampshire, New Mexico, Oklahoma (read the agency pages), South Carolina, South Dakota, Tennessee, Texas and Wisconsin. Texas's list is known to exist, but an earlier survey in this repo (November 2026) found that its robots.txt disallows crawling, so it would need the Comptroller's permission or a published export.

## (d) Proposed refresh job

Not made: workflows are Ren's call. Until one is approved, West Virginia and New Jersey ship from the snapshots `data/westvirginia.json.gz` and `data/newjersey.json.gz`, made on November 25, 2026. `export_web.fetch()` asks the release for `westvirginia.json.gz`, gets a 404, and reads the file in `data/` instead (tested in `tests/test_states.py`). There is no vectors file in either place, so `program_vectors()` embeds the records during the export, as it already does for the hand-kept lists. A snapshot ages. `export_web` leaves out any call whose closing date is before the day of the export (`still_open()`, for every open-call state; Florida's catalog and the hand-kept lists keep their own rules), so expired calls stop showing, and the state tab says when its data was last updated. Calls the state adds after the snapshot don't appear until it is remade (`python -m grantmatch.westvirginia --out data/westvirginia.json.gz` and `python -m grantmatch.newjersey --out data/newjersey.json.gz`) or the refresh job runs. On November 25 the New Jersey snapshot had 9 dated calls (the first closing December 4) and 22 rolling ones; West Virginia's 7 close between December 15, 2026 and June 30, 2027, except one ongoing. The deploy workflow's push paths don't include these two files, so a new snapshot reaches the site on the next deploy that runs for another reason (several a day).

The proposed change is one new workflow that runs **weekly**. Weekly means a call a state opens mid-week can show up to a week late. Closed calls still drop out at every site export, which runs several times a day, because `still_open()` checks each record's closing date against the export day, not the refresh day.

```yaml
# .github/workflows/refresh-states.yml (proposed, not added)
name: Refresh state lists
on:
  schedule:
    - cron: "17 13 * * 1"   # weekly, Mondays at 13:17 UTC
  workflow_dispatch:
permissions:
  contents: write
  actions: write
jobs:
  refresh:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -r requirements.txt
      - name: Read the West Virginia and New Jersey lists
        run: |
          python -m grantmatch.westvirginia --out build/westvirginia.json.gz --skipped build/skipped-westvirginia.json.gz
          python -m grantmatch.newjersey --out build/newjersey.json.gz --skipped build/skipped-newjersey.json.gz
      - name: Build semantic embeddings
        run: |
          python -m grantmatch.embed programs build/westvirginia.json.gz build/westvirginia.npz
          python -m grantmatch.embed programs build/newjersey.json.gz build/newjersey.npz
      - name: Publish as data-latest release assets
        env:
          GH_TOKEN: ${{ github.token }}
        run: gh release upload data-latest build/westvirginia.* build/newjersey.* build/skipped-westvirginia.json.gz build/skipped-newjersey.json.gz --clobber
      - name: Keep this schedule from expiring
        if: always()
        env:
          GH_TOKEN: ${{ github.token }}
        run: gh api -X PUT "repos/${{ github.repository }}/actions/workflows/refresh-states.yml/enable"
```

Later states join the same job as more lines in the two steps, so the job count doesn't grow with each state. One small edit to `deploy-site.yml` is also worth making with it: its push paths list `grantmatch/export_web.py` but not `grantmatch/states.py`, which the export now reads, so a change to the registry alone wouldn't rebuild the site until the next refresh-triggered deploy. `skipped-report.yml` also needs a change, or West Virginia and New Jersey stay out of the Friday skipped grants report: today it neither downloads their skipped lists nor passes their data files. Proposed (not made): add `-p 'skipped-westvirginia.json.gz' -p 'skipped-newjersey.json.gz'` to the first `gh release download`, `-p westvirginia.json.gz -p newjersey.json.gz` to the second, and `--westvirginia build/westvirginia.json.gz --newjersey build/newjersey.json.gz` to the `python -m grantmatch.skipped` line. `grantmatch/skipped.py` already takes those arguments and reads the two skipped lists when they are there (both come from `grantmatch/states.py`); once their `refresh` is set in the registry, the report also says when a refresh failed to publish one. The report job's minutes don't change measurably (a few more seconds of download).

**Billed minutes.** Job times from `gh run view` for the recent successful runs of each existing state refresh, on ubuntu-latest (billed per job, rounded up to the minute):

| Refresh | Job time | Billed a run |
|---|---|---|
| Ohio | 50 to 58 s | 1 |
| Washington | 52 to 60 s | 1 |
| Iowa | 59 to 67 s | 1 to 2 |
| California | 64 to 81 s | 2 |
| Illinois | 142 to 158 s | 3 |

So the existing jobs take 50 to 158 seconds, 1 to 3 billed minutes a run. Illinois and Iowa are slower because they read a page per notice; California downloads a 6.6 MB file. The West Virginia and New Jersey adapters each make one small request (a 700 KB JSON list and a 7 KB CSV), like Ohio and Washington, but the job runs two of them and two embedding steps, so expect it near California's: about 60 to 90 seconds, **1 to 2 billed minutes a run**.

- **Proposed, weekly:** about 4.3 runs a month, so **about 4 to 9 billed minutes a month**.
- **Rejected alternative, daily:** 30 to 62 billed minutes a month (2 minutes every day of a 31-day month is the top), for calls showing up within a day instead of within a week.

A deploy triggered by a refresh (`deploy-site.yml` build and deploy jobs) took 6 to 8 minutes on November 24, about 7 to 9 billed minutes. Adding "Refresh state lists" to deploy-site's `workflow_run` list would add about 30 to 40 billed minutes a month even run weekly (210 to 270 if daily). That isn't needed: the export reads the release at every deploy, and the federal refresh alone triggers a deploy twice a day, so new West Virginia and New Jersey data reaches the site within about 12 hours of the weekly refresh without it. The recommendation is the weekly refresh job alone, at about 4 to 9 minutes a month.
