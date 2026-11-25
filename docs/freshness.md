# Freshness check

One weekly check of how old the data behind the master list is, and whether the links it can check still open (see [what isn't link-checked](#not-link-checked)). It runs at the end of the page watch (`.github/workflows/watch-pages.yml`, Thursdays at 11:41 UTC), through the command that job already runs (`python -m grantmatch.watch`), so there is no new job and no workflow change. The code is `grantmatch/freshness.py`.

The page watch writes its own report and readings first. If the freshness check then fails, those are kept, the report says the check did not finish, and last week's freshness results stay as they were.

## What is checked

**How old the data is.**

| Source | Date read from | Refreshed by | Old after |
|---|---|---|---|
| Federal grants | `opportunities.json.gz` `fetched_at` | `refresh-data.yml`, twice a day | 3 days |
| California, Illinois, Iowa, Ohio, Washington | each state file's `fetched_at` | its own daily job | 3 days |
| Florida catalog | `florida.json.gz` `fetched_at` | `refresh-florida.yml`, weekly | 10 days |
| West Virginia, New Jersey | each state file's `fetched_at` | `refresh-states.yml`, weekly | 10 days |
| New York, District of Columbia, Minnesota | the snapshot's `fetched_at` | no job yet | 14 days |
| Funder website check | `cycles.json.gz` `checked_at` | `refresh-websites.yml`, weekly | 10 days |
| Private and community foundations | the oldest state file's `fetched_at` | `refresh-foundations.yml`, monthly | 45 days |
| Foundation coverage numbers | `coverage.json` `made_at` | `refresh-foundations.yml`, monthly | 45 days |
| Hand-kept files and company programs | the oldest `checked` date | a person | 90 days |
| County and place names | the 2020 census file | a person, once a census | 4,018 days (about 11 years) |

A source with no readable date counts as old. A release file whose read failed, or was skipped because the 90 seconds for reading the release ran out, is reported as "could not read": it is not counted as old, and the older copy in `data/` is not read in its place. The built states and their limits come from the registry (`grantmatch/states.py`), so a new state joins with no change here.

**Whether links open.** The public pages the sources are read from (each built state's `pages` in the registry; Grants.gov, the two IRS pages and the Census file for the others), the links on state calls, and the pages behind the hand-kept and company programs. The hand-kept pages are the ones the page watch has just read, so they aren't asked for twice.

| Result | When | Counted as dead |
|---|---|---|
| ok | the page answers 2xx | no |
| dead | 404 or 410, or unreachable (a timeout, a refused connection, a 5xx) on two checks in a row, on separate days. It stays dead until it answers 2xx | yes |
| unreachable | unreachable once | not yet; it is asked for first next week |
| blocked | robots.txt keeps this crawler or an Anthropic agent out, robots.txt couldn't be read, or the host's terms forbid automation | never; not asked for |
| refused | any other answer that isn't 2xx, 404, 410 or 5xx (400, 401, 403, 405, 406, 429, 451 and so on) | never, unless it was already dead |

Every request goes through the project's crawling rule (`off_limits` in `grantmatch/cycles.py`), redirects included, with the project's own user agent. Only the status is read, not the page. Requests to one host are 2 seconds apart, 10 for communityaffairs.dc.gov, and longer when robots.txt asks. One run asks for at most 150 pages, 20 from one host, and starts no request after 150 seconds of link checking. What doesn't fit waits for a later week, longest unchecked first. With the links in `data/` and the release on November 25, the links it may open come round about every two to three weeks (estimate).

**Stale records.** A hand-kept program whose closing date has passed, with no later window entered, not rolling, and whose page didn't say applications are open at the last website check. Old `checked` dates are listed entry by entry in the page watch's own part of the report. State calls past their deadline are counted in the source table; the export already leaves them out. When the website check's file (`cycles.json.gz`) can't be read, no new past closing date is listed that run, and the ones already reported are kept.

### Not link-checked

- **Federal grant links.** No job opens them: the Grants.gov refresh reads the API, not the grant pages.
- **Florida catalog links.** The weekly Florida refresh reads the catalog pages, but no link result is recorded.
- **Foundation websites.** The weekly website check reads them, but no link result is recorded.
- **Off-limits hosts**, and pages that turn scripts away.

## "Last checked" on the cards

The export stamps each record with when its source was read: a hand-kept entry's `checked` date, otherwise its data file's `fetched_at` (see below for foundations). Where the published watch state has a result for the record's link, the record carries `ok` or `dead` and that date. Cards show "Last checked <date>", and "Link didn't open when last checked" when the link is dead.

A foundation's "Last checked" is the date the IRS data was read, not a look at the foundation's website, so its card says "IRS data last checked <date>".

A company program's page that didn't open is noted in the card's details. The fields start with `_`, are display only and never change a score, and Florida's catalog data and scores are as before. In a local export of the data in `data/` (8,187 records), the stamps added 11 KB of gzipped JSON (0.12%).

## What to do with the report

The report is the second part of the weekly `page-watch` issue. A finding is listed in full the first time it appears; after that it is only counted under "Still open from earlier reports" (old sources are also named there), and of the freshness findings only new ones count toward posting a comment. So work from the report that first listed it. The keys of what has been reported are in `watch-state.json.gz` under `_freshness`. The source table shows only sources that are new or changed.

1. **Data that is old or missing:** open that source's refresh job and see why it didn't run or publish. For New York, DC and Minnesota, remake the snapshot (`python -m grantmatch.newyork --out data/newyork.json.gz`, and the same for the others) or add the proposed job below.
2. **Dead links:** open the page in a browser. If it moved, update the entry's `url` in `data/local-<ST>.json` or `data/corporate.json`, or the adapter and the registry's `pages` for a state. If a program is gone, remove its entry. A state call with a dead link is the state's list to fix; `hide` it in `data/skip-review.csv` if it shouldn't show.
3. **Closing date passed, no next round entered:** read the program's page. Enter the next window, mark it `rolling`, leave it (it ranks as "Between rounds" when it comes round each year), or remove it. It is listed once, then counted until its dates change.
4. **Didn't open once:** nothing yet.
5. **Off limits or turned away:** these need a person with a browser, or permission. They are not errors in the data.

The check never edits an entry.

## Proposed: one weekly job for the five states

`grantmatch/refresh_states.py` runs every built state but Florida that has no daily job (West Virginia, New Jersey, New York, DC, Minnesota). Each state's addresses are checked against the crawling rule first. A state that fails, or comes back with no open calls, keeps its previous file, the others are still written, the written states are listed in `build/refreshed.txt`, and the exit code is 1.

Nothing runs it yet. Two text files hold the proposed workflows:

- [proposed-workflows/refresh-states.yml.txt](proposed-workflows/refresh-states.yml.txt) replaces `.github/workflows/refresh-states.yml`.
- [proposed-workflows/skipped-report.yml.txt](proposed-workflows/skipped-report.yml.txt) replaces `.github/workflows/skipped-report.yml`, adding the five states' skipped lists and data files.

To use them:

1. Copy each over its workflow file and commit.
2. After the first successful "Refresh state lists" run, set `"refresh": "weekly"` for NY, DC and MN in `grantmatch/states.py`.
3. With the new skipped report in place and the files on the release, remove `"in_skip_report": False` from the five states.
4. Update the rows in this page, the README and [state-coverage.md](state-coverage.md) that say New York, DC and Minnesota have no job.

Until step 2, the registry says those three have no refresh job, which stays true.

## Actions minutes

Billed per job, rounded up to the minute. A month has 4 or 5 weekly runs.

| Job | Now, a run | Now, a month | After, a run | After, a month | New a month |
|---|---|---|---|---|---|
| `watch-pages.yml` | 1 min (measured once: job 41 s on November 20) | 4 to 5 | 4 min (estimate, range 3 to 5) | 16 to 20 (estimate) | about 12 to 15 (estimate) |
| `refresh-states.yml`, if the proposed file is copied in | 1 to 2 min (estimate; it has not run yet) | 4 to 10 (estimate) | 2 to 3 min (estimate) | 8 to 15 (estimate) | about 4 to 5 (estimate) |
| `skipped-report.yml`, if the proposed file is copied in | 1 min (measured twice: 46 and 50 s on November 22) | 4 to 5 | 1 min (estimate) | 4 to 5 | 0 (estimate) |
| **Total new** | | | | | **about 16 to 20 (estimate)** |

How the watch estimate was made:

- The one measured run predates the county and city entries, so the page watch itself will take somewhat longer once they are on main, with or without this change.
- One local run of the freshness check on November 25 took 150 s in all: 133 s of link checks (29 sources, 451 links, 150 planned) and the rest reading the release. It has not run on a GitHub runner. After that run, off-limits pages stopped being waited for, so the time should be a little lower; this was not measured.
- At its caps the check adds at most about 4 to 5 minutes (90 s of release reading, 150 s of link checks, and a request already started). If every run hit that, the watch would add up to about 25 minutes a month and the total about 30.

No other job changes. `deploy-site.yml` is not triggered by the check.

## Limits

- A page that answers 200 with a "not found" message reads as ok.
- A whole host that disappears shows as "robots.txt could not be read", not as dead; the report counts how many checks in a row that has happened (for the pages the page watch doesn't read).
- On November 25, robots.txt on omb.illinois.gov and il.amplifund.com answered with a web page, and www.grants.gov's couldn't be read, so under the crawling rule those pages are not opened. The daily Illinois refresh still reads omb.illinois.gov and does not check robots.txt as it runs.
- A card's link result is as old as the last weekly check, and the export picks it up at the next site build.
