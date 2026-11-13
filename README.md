# Grant Matcher for small nonprofits

Finding a federal grant you can actually win is hard when you are a small nonprofit. Grants.gov lists over a thousand open and upcoming opportunities that nonprofits can apply for at any time, and most of them are research programs, multimillion-dollar awards, or grants that require matching funds a young organization does not have.

Grant Matcher reads your mission, ranks every open and forecasted federal opportunity against it, and tells you in plain words why each one is or is not a fit.

**Try it:** [grant-matcher.streamlit.app](https://grant-matcher.streamlit.app)

> This product uses the Grants.gov API but is not endorsed or certified by the U.S. Department of Health and Human Services.

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
- **Exports** your strong and possible matches to CSV and the deadlines to a calendar file (.ics).
- **Saves your profile** as a small JSON file you can load next time. Nothing is stored on a server.

## How the score works

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

## Data

A GitHub Action runs every night and pulls every posted and forecasted opportunity open to nonprofits (eligibility codes 12, 13, 25 and 99) from the public [Grants.gov API](https://www.grants.gov/api/api-guide) using `search2` and `fetchOpportunity`. No API key is needed. The cleaned file and the opportunity embeddings are published as `data-latest` release assets, and the app reads them from there. A snapshot in `data/` is the fallback. If the embedding model cannot load, the app falls back to TF-IDF similarity.

## Run it yourself

```bash
pip install -r requirements.txt
python -m grantmatch.fetch --out data/opportunities.json.gz   # about 20 minutes; add --limit 50 for a quick test
python -m grantmatch.embed data/opportunities.json.gz data/embeddings.npz
streamlit run app.py
python -m pytest -q
```

## Project layout

```
app.py                  Streamlit app
grantmatch/fetch.py     Grants.gov pull and cleanup
grantmatch/embed.py     semantic embeddings (nightly for grants, on demand for a mission)
grantmatch/match.py     scoring, reasons, calendar export
tests/                  unit tests for scoring and parsing
.github/workflows/      nightly data refresh and tests
```

## Roadmap

- Private and community foundation grants from IRS Form 990-PF data
- State grant portals (starting with Florida)
- Email digest of new matches each week

## Why I built it

I'm a data scientist and the CTO of Exceed the Odds, a founding-stage nonprofit that provides literacy, speech, and tutoring support to children at no cost or on a sliding scale. We fund that work with grants, and I wanted a faster way to find the ones worth our time.

Built by [Rendell Rich](https://rendellrich.github.io). MIT License.
