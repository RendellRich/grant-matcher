# County and city coverage

What Grant Matcher holds for county and city grants, checked November 25, 2026.

**No free national or state catalog of county or city grants exists in what was searched.** The research looked for one (a web search, the 51-state audit in [state-coverage.md](state-coverage.md), the Socrata and ArcGIS open-data catalogs and the grant platforms local governments use) and found state-agency portals, commercial aggregators that can't be used, and a few regional lists, but no dataset of current county or city calls. "Not found" is not proof that none exists. So every county and city program here is entered by hand from the program's own page, and coverage is partial.

Separately, a [local funder directory](#local-funder-directory) lists local governments that get HUD money, from two federal files. It is a list of funders to ask, not of programs.

## How a program gets in

1. robots.txt is read first, with the user agent `grant-matcher (github.com/RendellRich/grant-matcher)`. A site that keeps out this crawler, ClaudeBot or another Anthropic agent is off limits, and so is a site whose robots.txt can't be read. The agent is never changed to get around it.
2. The site's terms are read. Terms that forbid automation or commercial reuse (Grant Matcher is a paid product) put the host on the blocklist.
3. The title, who may apply, the dates and the link must be supported by the live page. Matching funds and tax status rules are checked in the linked guidelines too. What they don't say is not filled in, and a guideline that couldn't be read is named in the entry's `source_note`.
4. A program whose deadline has passed is kept only when the page shows it comes round again. It then ranks as "Between rounds".

The weekly page watcher and website check apply rules 1 and 2 in code (`off_limits` in `grantmatch/cycles.py`): robots.txt is checked for this crawler and for `ClaudeBot`, `Claude-User`, `Claude-SearchBot`, `Claude-Web` and `anthropic-ai`, wildcard paths included; every redirect is checked before it is followed; and hosts in `BLOCKED_HOSTS` are never requested. Only two answers for robots.txt let a page be read: 200 (the rules are followed) and 404 or 410 (there are none). A 200 that is a web page instead of the file, a 401, 403, 429, a server error, a timeout, a refused connection, a bad certificate or anything else is "robots.txt could not be read", and the site is off limits. A page that is off limits is reported by the watcher as blocked. Its entry is not deleted, and a person decides what to do.

What this changes for the foundation website check (`grantmatch/cycles.py`, thousands of sites): a site whose robots.txt can't be read is now recorded as an error and not read, where before it was read. Its website note drops off the card until the file can be read again, and the try over plain http for a broken certificate no longer happens, since a certificate error also leaves https robots.txt unread. How many foundation sites this affects was not measured. Foundation scores don't use the website check.

Terms are only as good as the blocklist, which is kept by hand.

### Watched pages that are now off limits

These entries were already in the lists. Their pages can't be rechecked automatically. On November 25, 2026, of 145 watched pages, 7 were off limits by their rules or terms and 8 more because robots.txt could not be read (checked twice, with the same result). Six of those 8 unreadable ones already failed to load before this change (403 or timeout); the Citrus County file and the e-CImpact sign-in page did load.

| Entry (list) | Page | Why |
|---|---|---|
| `hillsborough-childrens-board-emerging-needs`, `childrens-board-aso-flexible-funds` (FL) | childrensboard.org | robots.txt keeps out Claude-Web |
| `bradenton-police-forfeiture` (FL) | www.bradentonpd.com | robots.txt keeps out ClaudeBot |
| `uws-summer-care-2027` (FL) | unitedwaysuncoast.org | robots.txt keeps out ClaudeBot |
| `pasco-opioid-fund` (FL) | cms1files.revize.com (a PDF) | robots.txt keeps automated visitors out |
| `ohio-history-fund` (OH) | www.ohiohistory.org (both pages) | robots.txt keeps out ClaudeBot |
| `humanities-iowa-mini-grants` (IA) | humanitiesiowa.submittable.com (its second page, humanitiesiowa.org, is still read) | terms can't be confirmed |
| `sarasota-contracted-human-services` (FL) | www.scgov.net | robots.txt answers 403 |
| `citrus-tourist-development-grants` (FL) | s3.us-east-1.amazonaws.com (a PDF) | robots.txt answers 403 |
| `fldoe-21st-cclc` (FL, two pages) | www.fldoe.org | robots.txt answers 403 |
| `oag-voca-victim-assistance` (FL) | www.myfloridalegal.com | robots.txt answers 403 |
| `isl-adult-volunteer-literacy` (IL, two pages) | www.ilsos.gov | robots.txt times out |
| `uws-summer-care-2027` (FL, its second page) | agency.e-cimpact.com | robots.txt answers with a web page |

Ren's decision, 2026-11-25: these entries stay. The weekly freshness report names each one under "Check by hand" so a person rechecks it in a browser ([freshness.md](freshness.md)).

The weekly website check also stops reading these, so a website status it recorded before (for example "applications are open") drops off at its next run. For a program with no dates, that can move it to "Between rounds".

## Entry format

One file per state, `data/local-<ST>.json`: `{"about": "...", "programs": [...]}`. `python -m grantmatch.local` checks every file; a bad entry stops the export. Florida's ids are `local-<slug>`; other states' are `local-<st>-<slug>`.

| Key | Required | Meaning |
|---|---|---|
| `slug` | yes | Lowercase letters, digits and hyphens, up to 51; unique in the file. Part of the key ETO stores, so don't change it |
| `title`, `agency` | yes | The program and who runs it |
| `level` | yes | `State`, `County`, `City`, `Children's services council`, `Community foundation` or `United Way` |
| `counties` | yes | County names as in `data/counties.json.gz`, or `["Statewide"]` |
| `objectives`, `who`, `application`, `award` | yes | In plain words, from the page. Say "Not stated on the page." when it isn't |
| `requires_501c3` | yes | `true` only when the program requires 501(c)(3) status and allows no fiscal sponsor or other route; `false` only when it says tax status isn't needed (individuals or unincorporated groups may apply); `null` for anything else (a sponsor or another 501(c) type will do, or the page doesn't say). With `null` no points come off, and "Can we apply?" (card and copied summary) asks a profile without 501(c)(3) status to "Check tax status" and read who can apply; it never reads as a clean yes |
| `match` | no | The required match, for example `25%` or `100% cash`. Takes 20 points off for a profile that can't cost share, and the card says so |
| `url`, `checked` | yes | The official page (https) and the date a person checked it |
| `opens`, `closes` | no | `yyyy-mm-dd` or `null` |
| `rolling` | no | `true` for a program that takes applications any time; no `closes` |
| `by_invitation` | no | `true` when only invited or earlier recipients may apply. "Can we apply?" shows it as something to check; no score change |
| `deadlines` | no | A sentence that replaces the one made from `opens` and `closes` |
| `contact`, `subjects`, `web` | no | `web` is a second page, usually an HTML page beside a PDF |
| `area` | with `places` or `exclude_places` | The words the card uses, for example "Houston" or "suburban Cook County" |
| `places` | no | The only places served, replacing the county-wide list: a city program, or part of a county. Each must be a county in `counties`, "<county> County", a Census place in them, or a New York City borough name |
| `exclude_places` | no | Places in those counties that are not served, for example Chicago in a suburban Cook County program. Not with `places` |
| `source_note` | no | Something the page gets wrong or leaves unclear; shown on the card as "Note" |

`places`, `exclude_places`, `area`, `match`, `source_note` and a `null` `requires_501c3` came with this batch. In Florida's file only the seven Miami-Dade and Broward programs added later use any of them (`match`, `source_note`, a `null` `requires_501c3`); its earlier entries are unchanged. New entries carry no email addresses. FIPS codes are not stored, because nothing reads them; counties are matched by name against `data/counties.json.gz`.

How a place is matched: the card says "Funds work in <area>" when one of the profile's cities or counties is in the program's list, and "Only for work in <area>" (40 points off) when not. A county typed into the profile counts as every place in it, so someone who types a county also matches a city program inside it. In a program for towns and unincorporated areas (Maricopa County CDBG), an organization that types only an unincorporated place's name should add the county.

## First batch: what was kept

48 researched entries: 36 loaded (29 at first, then the 7 held Florida ones) and 12 dropped. The Cook County CDBG and ESG page became two entries, since ESG requires a match and CDBG doesn't, so the files hold 37 of this batch.

| Loaded into | Programs |
|---|---|
| `local-FL.json` (+7) | Miami-Dade County Cultural Affairs: Community, Cultural Advancement, Cultural Development, Developing Arts in Neighborhoods, Festivals and Special Events and Hannibal Cox, Jr. grants; Children's Services Council of Broward County sponsorships |
| `local-AZ.json` (3) | Maricopa County: ESG and CDBG public services, CDBG, HOME CHDO |
| `local-CA.json` (6) | Los Angeles County arts (2) and Care First grants; San Bernardino County CDBG; Alameda County ARTSFUND; Sacramento County TOT grants |
| `local-IL.json` (+3) | Cook County violence intervention; Cook County CDBG; Cook County ESG |
| `local-NV.json` (1) | Clark County Outside Agency Grant |
| `local-NY.json` (3) | New York City Council discretionary funding; Queens and Brooklyn Borough Presidents |
| `local-PA.json` (2) | Philadelphia Cultural Fund |
| `local-TX.json` (8) | Houston Arts Alliance (4); Dallas ArtsActivate; Tarrant County CDBG and ESG; San Antonio arts operating grants |
| `local-WA.json` (+4) | 4Culture (King County) |

**The seven held Florida entries** were loaded on 2026-11-25, on Ren's approval, after each was rechecked against its live page and guidelines with the crawling rule. All seven were still supported; none was dropped. What the recheck changed:

- **Tax status.** All seven had said no 501(c)(3) was needed, which was wrong. Cultural Advancement, Cultural Development and the Broward sponsorships require it (`true`). Community Grants, Developing Arts in Neighborhoods, Festivals and Hannibal Cox allow a fiscal agent or another 501(c) type, or ask only for a Florida not-for-profit (`null`).
- **Match.** All six Miami-Dade programs require one: 100% for five (Community Grants allows part in kind; the others ask for cash), and 100% to 300% from private sources for Festivals. Broward's pages state none; its policy says the Council will not be an event's only funder.
- **Dates.** Community Grants' fourth quarter opens January 22, 2027 (the entry had no opening date, so it would have read as open now). Opening dates were added to the five closed programs.
- **Who may apply** now carries the guidelines' limits, among them budget floors and ceilings, and that arts programs for or with children can't use Cultural Advancement, Developing Arts or Hannibal Cox. Cultural Advancement is by invitation or prior recommendation, which "Can we apply?" shows (`by_invitation`).
- **Broward** gives up to $2,000 for events only, and takes requests any time, 60 to 180 days before the event.

Existing Florida entries, ids and scores are unchanged (`tests/test_florida_unchanged.py`).

**Dropped:**

| Researched entry | Why |
|---|---|
| Cook County diabetes education request | Run by a state institute with CDC money; the county page lists it among outside funders' opportunities |
| Harris County Public Health capacity grant | Closed with no dates; the page says future cohorts depend on funding |
| Houston public services notice | The page doesn't say who may apply |
| The Children's Trust outreach grants (Miami-Dade) | The Trust's terms of use prohibit copying or reselling its resources |
| Dallas County community garden mini-grant | Past deadline and nothing shows it comes round again; the researched award amounts aren't in the document |
| South Dallas/Fair Park Opportunity Fund | A govdelivery bulletin that links no terms; the only publisher terms found (granicus.com) limit use to individual use |
| New York City Cultural Development Fund | www.nyc.gov answers 403 to robots.txt, so what it allows can't be confirmed |
| King County Alan M. Painter grants | kingcounty.gov terms bar commercially exploiting its content |
| Tarrant County Community Outreach Fund | Past deadline and nothing shows it comes round again |
| Philadelphia public safety grants | phila.gov terms prohibit commercial use |
| Detroit Neighborhood Opportunity Fund | detroitmi.gov terms prohibit commercial use |
| Cambridge community benefits grants | cambridgema.gov prohibits commercial use |

**Match and tax status rules** (checked in the linked guidelines, November 25, 2026):

- A match is required by: both Los Angeles County arts grants (dollar for dollar, cash), Cook County ESG (100%), Tarrant County ESG (100%) and Maricopa County HOME CHDO (25% non-federal).
- 501(c)(3) with no other route: Maricopa County CDBG and its homeless services notice (the application offers no other tax status), Cook County CDBG and ESG, and San Antonio arts operating grants. Cook County CDBG capital money also goes to suburban municipalities.
- Guidelines not read, so match or tax status rules may be missing: Alameda ARTSFUND (constantcontact.com robots.txt can't be read), Dallas ArtsActivate (the file host's robots.txt can't be read), Queens Borough President (a document that needs a browser app), Brooklyn Borough President (a Microsoft form), both Philadelphia Cultural Fund grants (canva.com keeps automated visitors out). Each of these cards says so in its note, except the checklist can't show a match it doesn't know about.

- Florida additions: matches and tax status as above, from the six FY 2026-2027 Miami-Dade guidelines and the Broward sponsorship policy (revised January 2024).

Judgment calls a person may want to change:

- "All rights reserved" or a copyright line with no ban on commercial use was not treated as a ban.
- No terms page was found linked from houstonartsalliance.com, miamidadearts.org, dallascityhall.com, www.clarkcountynv.gov, arts.alamedacountyca.gov, www.philaculturalfund.org, council.nyc.gov, www.queensbp.nyc.gov or www.brooklynbp.nyc.gov, among others that link only a privacy policy. None was found linked from the www.cscbroward.org pages read for its sponsorships either. The three New York City hosts are subdomains of nyc.gov, whose own site couldn't be read.
- The check of terms was a search for automation and reuse wording on the pages linked from each site, then a reading of what it found. It is not legal advice.

## The 25 largest counties

The list of counties is the research's; the population order was not rechecked. Counts are programs loaded that serve the county, including city programs inside it. A New York City program counts under each of its counties.

| County | Loaded | Notes |
|---|---|---|
| Los Angeles, CA | 3 | County arts and justice grants |
| Cook, IL | 3 | County programs |
| Harris, TX | 4 | City of Houston arts only; no county program |
| Maricopa, AZ | 3 | County programs |
| San Diego, CA | 0 | Not read: sandiegocounty.gov timed out, robots.txt included |
| Orange, CA | 0 | None found on the county pages looked at |
| Miami-Dade, FL | 6 | County Cultural Affairs grants |
| Dallas, TX | 1 | City of Dallas arts only |
| Kings, NY | 2 | City Council and Borough President |
| Riverside, CA | 0 | Blocked: rivco.gov robots.txt keeps out ClaudeBot |
| Clark, NV | 1 | County program |
| Queens, NY | 2 | City Council and Borough President |
| King, WA | 4 | 4Culture; kingcounty.gov is blocked by its terms |
| San Bernardino, CA | 1 | County CDBG |
| Tarrant, TX | 2 | County programs |
| Bexar, TX | 1 | City of San Antonio only; bexar.org answered with a bot check |
| Broward, FL | 1 | Children's Services Council sponsorships; broward.org robots.txt keeps out ClaudeBot |
| Santa Clara, CA | 0 | Blocked: the county's sites answer with a bot check |
| Wayne, MI | 0 | Blocked for Detroit by its terms; no county nonprofit grant found |
| Alameda, CA | 1 | County arts |
| New York, NY | 1 | City Council |
| Middlesex, MA | 0 | Blocked for Cambridge by its terms; no county program page found |
| Sacramento, CA | 1 | County program |
| Hillsborough, FL | 11 | Already in `local-FL.json`; 2 of them can no longer be rechecked automatically |
| Philadelphia, PA | 2 | Philadelphia Cultural Fund; phila.gov is blocked by its terms |

San Diego, Orange, Riverside, Santa Clara, Bexar and the other "not read" notes come from the research and were not tried again. This is what one pass found, not a full inventory of any county: library, parks, tourism, opioid settlement, senior services and city CDBG rounds are mostly unswept.

## Every state's hand-kept list

| State | Entries | Statewide calls | County, city and other local | Counties named |
|---|---|---|---|---|
| Arizona | 3 | 0 | 3 | Maricopa 3 |
| California | 6 | 0 | 6 | Los Angeles 3, San Bernardino 1, Alameda 1, Sacramento 1 |
| Connecticut | 2 | 2 | 0 | none |
| Florida | 63 | 7 | 56 | Pinellas 15, Hillsborough 11, Miami-Dade 6, Manatee 5, Sarasota 5, Polk 5, Orange 4, Hernando 4, Pasco 3, DeSoto 3, Lee 2, Citrus 2, Charlotte 2, Osceola 1, Seminole 1, Broward 1 |
| Illinois | 13 | 10 | 3 | Cook 3 |
| Iowa | 6 | 6 | 0 | none |
| Kansas | 1 | 1 | 0 | none |
| Massachusetts | 2 | 2 | 0 | none |
| Mississippi | 3 | 3 | 0 | none |
| Nevada | 1 | 0 | 1 | Clark 1 |
| New York | 3 | 0 | 3 | Kings 2, Queens 2, Bronx 1, New York 1, Richmond 1 |
| Ohio | 6 | 6 | 0 | none |
| Pennsylvania | 2 | 0 | 2 | Philadelphia 2 |
| Texas | 8 | 0 | 8 | Harris 4, Tarrant 2, Dallas 1, Bexar 1 |
| Washington | 14 | 10 | 4 | King 4 |

Every other state and the District of Columbia has no county or city list (the Connecticut, Kansas, Massachusetts and Mississippi lists are state calls only).

On the site, a list in a state with a state catalog (Florida, California, Illinois, New York, Washington and the others) joins that state's tab. In Arizona, Nevada, Pennsylvania and Texas, which have no state catalog, the tab is "<state> local programs", and the note above the tabs says it holds county and city programs only, entered by hand, as a partial list. Connecticut, Kansas, Massachusetts and Mississippi have no state catalog either: their tab is "<state> programs" and the note says it holds state programs only, entered by hand, not a statewide list. Iowa, Illinois, Ohio and Washington lists join their tab only when that state's data file is in the release, as before.

## Local funder directory

Built November 25, 2026. "Local funders to ask" on the site lists the local governments that get HUD formula money. **They are funders, not open grant calls.** HUD money going to a government doesn't mean it funds nonprofits now, and CDBG money for public services is limited and varies. The directory is never ranked or scored, carries no deadline and no "open to nonprofits", stays out of results, the shortlist and the downloads, and neither scorer reads it. It is not the hand-kept programs above: those are calls read from each program's own page.

### Sources and license

| Source | File read | As of | License evidence |
|---|---|---|---|
| HUD [FY 2026 formula program allocations](https://www.hud.gov/hud-partners/community-budget-26) | [FY2026-Formula-Allocations-All-Grantees.xlsx](https://www.hud.gov/sites/dfiles/CPD/documents/FY2026-Formula-Allocations-All-Grantees.xlsx), 117,390 bytes | 2026-08-03 (the page's "content current as of") | A work of the U.S. government. [USAGov](https://www.usa.gov/government-copyright) points to 17 U.S.C. 105 for what that means for copyright. No license or terms statement is in the page's text or linked for the file, and HUD's privacy and web management pages, as read, state no limit on reuse or automated reading (the policy documents the web management page links as PDFs were not read) |
| Census Bureau [Government Units listing](https://www2.census.gov/programs-surveys/gus/datasets/), 2026 | [gov_units_2026.zip](https://www2.census.gov/programs-surveys/gus/datasets/2026/gov_units_2026.zip), 10,795,638 bytes (a workbook and its documentation) | 2026-08-13 (extraction date in the documentation) | A work of the U.S. government. The Bureau's [open data page](https://www.census.gov/topics/research/research-transparency-public-access/open-data.html) says it shares its public data as open data and names commercial activity among its uses. It asks for [citation](https://www.census.gov/about/policies/citation.html); the site and this page name it as the source. The Census API terms don't apply: no API is used |

- Both are free public downloads with no key or account. robots.txt of www.hud.gov, www2.census.gov, www.census.gov and www.usa.gov was read first with the project's agent; none keeps this crawler or an Anthropic agent off these addresses.
- USAGov also says federal agency logos and trademarks need permission and that nothing may imply endorsement. The site uses neither agency's logo and doesn't say either endorses it.
- This is a reading of public pages, not legal advice.
- HUD's FY 2026 file and the Census 2026 file were the newest found on November 25, 2026 (HUD's address for a FY 2027 page answered 404).

### What is kept

- **Kept:** HUD's cities (principal and metro), urban counties, Hawaii's three counties, HOME consortia and the District of Columbia, each with its CDBG and HOME dollars for FY 2026. **Left out:** the non-entitlement rows of the 50 states and Puerto Rico, the 4 insular areas, one urban county with neither program (Jefferson County, Kentucky), and HUD's other programs (ESG, HOPWA, RHP, Housing Trust Fund). States and territories aren't local governments.
- **One entry per government.** HUD lists two governments twice (Burlington, North Carolina and Davis County, Utah: their own CDBG row and a HOME consortium row); each is one entry.
- **HOME consortia.** 148 entries carry a consortium code, and their HOME amount is shown as a consortium's, not that government's alone. That reading comes from the file's layout (each code is on one row); HUD's file doesn't say it in words.
- **From the Census file** only the unit's name, Census id, kind, population, county and website are read. No street address, job title, person's name or email address is read or stored.
- **Websites** are the ones governments reported to the Census Bureau, which says it does only limited quality control. None is guessed or searched for, and none was opened or checked. A government's listed website may be a department's or a library's site, or another page, as the Census file gives it (Waterloo, Iowa's is under a library domain); it is shown as it stands. Left blank: cells that aren't a web address (including email addresses), directory sites, and eighteen addresses that look misspelled or malformed (`MISTYPED` in `grantmatch/funders.py`), since such a domain can belong to anyone. No other address is put in their place. They belong to Arvada, Pompano Beach, Pembroke Pines, Lower Merion, Eau Claire, Neenah, Mobile County, Roanoke, Bristol (Virginia), Hopewell, Austin, Thousand Oaks, Grants Pass, Harlingen, Killeen, Taylorsville, Meriden and Bridgeton (New Jersey). This was judged by eye from the address beside the government's name; a good address may be among them and a bad one may have been missed.
- **Names** are HUD's, with "Ft", "Hts" and "Twp" spelled out and county names spelled as `data/counties.json.gz` has them.

### How a government is matched

- An urban county by HUD's code (state code, 9, county FIPS code), and only when the names agree too.
- A city, town or township by name within its state. When several share a name, the kind in HUD's name decides, then municipalities before townships, then Census "city" units, then population of 50,000 or more. If more than one is still left, none is picked. Twelve names HUD words differently are joined by hand (`ALIASES`).
- State comes from the FIPS code, not the file's mailing address (Texarkana, Arkansas has a Texas address).
- Counties: the one county the Census file puts the government in (the one it says is most served), spelled as in `data/counties.json.gz`. **A city that spans several counties lists only that one** (Houston shows under Harris, not Fort Bend). The other counties aren't guessed from place names, since a different place of the same name would add a county the city isn't in. New York City is set to its five counties by hand. Connecticut towns are placed by a name found in exactly one county. A government with no reliable county is left at state level and shows under "Show all". Listing every county of a multi-county city would take the Census places-by-county file joined by FIPS code (the file `grantmatch/counties.py` already reads); not done.
- **Typing a name on the site** finds a government by the name the list uses (without "City", "Township", "Municipio" and the like, and without accents), with "Ft" read as "Fort" and "Saint" as "St". Short names are also read for Nashville, Lexington, Macon, Houma, New York City and its five boroughs. Other spellings, short forms and parts of a joined name may not find it by name (for example "Macon-Bibb" without "County"); it can still show through its county, and it is always under "Show all".
- **Not matched to a Census record (28):** Puerto Rico's 27 municipios (the Census listing has none) and Washington Township, New Jersey (several share the name). They have no website.
- **No county (8):** Fairfield, Hamden and Stratford, Connecticut (the Census file now uses planning regions); Houma-Terrebonne, Louisiana (the file misspells the parish); Baltimore, St. Louis, Richmond and Roanoke (each shares its name with a county that is a different government).

### Directory coverage by state

"County matched" counts entries with at least one county. By level: 201 county governments, 920 cities and 143 others (towns, townships, villages, boroughs, municipios, HOME consortia and the District). 1,249 have CDBG money, 626 HOME, 611 both.

| State | Entries | With website | No website | County matched |
|---|---|---|---|---|
| AK | 1 | 1 | 0 | 1 |
| AL | 16 | 15 | 1 | 16 |
| AR | 14 | 13 | 1 | 14 |
| AZ | 23 | 23 | 0 | 23 |
| CA | 186 | 184 | 2 | 186 |
| CO | 23 | 22 | 1 | 23 |
| CT | 23 | 22 | 1 | 20 |
| DC | 1 | 1 | 0 | 1 |
| DE | 3 | 3 | 0 | 3 |
| FL | 88 | 85 | 3 | 88 |
| GA | 28 | 28 | 0 | 28 |
| HI | 4 | 4 | 0 | 4 |
| IA | 12 | 12 | 0 | 12 |
| ID | 9 | 9 | 0 | 9 |
| IL | 50 | 49 | 1 | 50 |
| IN | 26 | 25 | 1 | 26 |
| KS | 9 | 9 | 0 | 9 |
| KY | 10 | 10 | 0 | 10 |
| LA | 15 | 15 | 0 | 14 |
| MA | 39 | 39 | 0 | 39 |
| MD | 15 | 15 | 0 | 14 |
| ME | 6 | 6 | 0 | 6 |
| MI | 47 | 46 | 1 | 47 |
| MN | 17 | 17 | 0 | 17 |
| MO | 16 | 16 | 0 | 15 |
| MS | 6 | 6 | 0 | 6 |
| MT | 4 | 4 | 0 | 4 |
| NC | 34 | 34 | 0 | 34 |
| ND | 4 | 4 | 0 | 4 |
| NE | 4 | 4 | 0 | 4 |
| NH | 5 | 5 | 0 | 5 |
| NJ | 60 | 56 | 4 | 60 |
| NM | 5 | 5 | 0 | 5 |
| NV | 7 | 7 | 0 | 7 |
| NY | 52 | 49 | 3 | 52 |
| OH | 46 | 44 | 2 | 46 |
| OK | 10 | 10 | 0 | 10 |
| OR | 19 | 17 | 2 | 19 |
| PA | 50 | 46 | 4 | 50 |
| PR | 27 | 0 | 27 | 27 |
| RI | 6 | 6 | 0 | 6 |
| SC | 22 | 22 | 0 | 22 |
| SD | 2 | 2 | 0 | 2 |
| TN | 19 | 19 | 0 | 19 |
| TX | 80 | 77 | 3 | 80 |
| UT | 19 | 18 | 1 | 19 |
| VA | 31 | 28 | 3 | 29 |
| VT | 1 | 1 | 0 | 1 |
| WA | 38 | 38 | 0 | 38 |
| WI | 22 | 20 | 2 | 22 |
| WV | 9 | 8 | 1 | 9 |
| WY | 1 | 1 | 0 | 1 |
| All | 1,264 | 1,200 | 64 | 1,256 |

### Upkeep

Once a year, when HUD publishes new allocations: update the addresses and dates at the top of `grantmatch/funders.py`, run `python -m grantmatch.funders --out data/funders.json.gz`, read the new `MISTYPED` and unmatched lists, and update this section. The weekly freshness report flags the file after 400 days and link-checks only the two source pages. The governments' websites are **not link-checked**: opening about 1,200 sites every week would lengthen the paid weekly job. The site rebuilds when `data/funders.json.gz` reaches main only if something else in the deploy's path list changes too; otherwise the next scheduled data refresh picks it up.

## Plan

Effort figures are estimates, not measurements.

**Phase 2: a nationwide directory of local funders. Built** (see [Local funder directory](#local-funder-directory)). A CDBG allocation does not prove that a government funds outside nonprofits in a given year, so the page says it doesn't. The research's counts (about 1,047 CDBG cities and 198 urban counties) matched the file: 607 principal and 440 metro cities, and 198 urban counties with money.

**Phase 3: more counties.** The next 75 counties by population, then CDBG entitlement cities, looking first at public services, arts and human services pages.

- This batch: 48 drafted, 36 loaded (7 of them after a second check). Plan on losing about a quarter to robots.txt, terms or pages that don't support the entry. Read each program's guidelines, not only its page: in this batch they held match and tax status rules the pages left out.
- About 1 to 2 hours a county for finding, checking and entering, so 75 counties is roughly 2 to 4 weeks of work. A script can draft from permitted pages; a person approves each entry.
- The directory can help pick them: it names every government with CDBG money and, where reported, its website.

**Upkeep for what is loaded now.** The weekly watcher reads every new page (28 more, all read by its reader on November 25, 2026), and the weekly website check reads each program's page. Both runs get a little longer; no workflow or schedule changes. Past programs need a person to look before their usual window each year.
