# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Delegated: a static site in `web/` (Vite, TypeScript, Preact) hosted on GitHub Pages. Matching runs in the visitor's browser: the mission is embedded with BAAI/bge-small-en-v1.5 (fp16 ONNX through transformers.js, which matches the Python fastembed vectors) and scored by a TypeScript port of `grantmatch/match.py` and `grantmatch/rank_more.py`, kept in step by a parity test. The data pipelines stay in Python; `grantmatch/export_web.py` turns their output into the files the site reads. The signed-in Workspace stays in the Streamlit app.

## Users

- **Primary:** people at small nonprofits, often a one-person development team or a founder, checking which grants are worth their limited time. They work late, on a phone as often as a laptop, and some use a screen reader.
- **Also:** advisors, consultants and volunteers who search on behalf of several nonprofits, so they switch profiles and compare results often.

## Product Purpose

Grant Matcher ranks federal grants (Grants.gov), private and community foundations (IRS 990-PF and 990 Schedule I) and Florida state programs (Catalog of State Financial Assistance) against a nonprofit's own mission, and says in plain words why each one is or is not a fit. Success is a short, ranked list worth applying to, found in minutes, with reasons the person believes.

## Positioning

It reads the funders' own records (tax returns, the federal and state catalogs) rather than a curated database, ranks by meaning and rare key words rather than keyword search alone, and checks the things that sink small applicants: 501(c)(3) status, cost sharing, award size against budget, research-only programs, programs aimed at tribes or state agencies, and deadlines. Every score comes with its reasons and cautions. It is free, and the mission never leaves the visitor's device.

## Operating Context

- The visitor describes their work (mission, key words, funding areas, state, cities, 501(c)(3) status, budget, matching funds), then reads results grouped by source.
- Results are ranked Strong (60 and up), Possible (35 to 59) and Long shot. Each result shows a score out of 100, reasons it fits, cautions, facts, and details such as how to apply and past grants.
- Exports: CSV of matches and a calendar file (.ics) of federal deadlines. A profile can be downloaded as JSON and loaded later; nothing is stored on a server.
- Data refreshes: Grants.gov nightly, Florida weekly, foundations monthly (GitHub Actions).
- Foundation data exists for Florida only at present; other states say so.

## Capabilities and Constraints

- The Grants.gov notice must appear with exactly this wording: "This product uses the Grants.gov API but is not endorsed or certified by the U.S. Department of Health and Human Services."
- Ranking logic is not changed as part of design work. The TypeScript scorer must match the Python scorer.
- Known issue kept for parity: the "No close date listed" caution in `match.py` never shows when any grant has a date (pandas NaN check).
- The first visit downloads the matching model (about 67 MB) once; the built-in examples are scored without it.

## Brand Commitments

- Name: Grant Matcher.
- Writing: plain words, sentence case, buttons are verbs, no em dashes.
- One accent color; status colors only for meaning; no decoration for its own sake.
- Must not feel like a slick startup or marketing site: no hype, no gradients, nothing that reads as selling.

## Evidence on Hand

- Real data from Grants.gov, IRS e-file returns and the Florida catalog (`data/`, and the `data-latest` release).
- Three example organizations (youth literacy, food pantry, youth arts) used as demonstrations; they are examples, not clients.
- No testimonials, user counts or outcome claims exist. Do not invent them.

## Product Principles

1. The answer comes first: how many strong matches, and where, before anything else.
2. Every score explains itself, cautions included; the ranking is a starting point for judgment.
3. Nothing changes until the person asks; edits stay a draft until they update.
4. Fast to use and fast to trust, on a phone as well as a laptop.
5. Free and private: no account, no server-side storage, the mission stays on the device.

## Accessibility & Inclusion

WCAG 2.2 AA in light and dark: AA contrast, visible focus, 44px targets, works at 320px wide, usable with NVDA and VoiceOver. Light and dark follow the system setting.
