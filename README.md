# Daily Market Briefing Agent

Automated morning and evening briefings on Indian equity markets.
Design decisions and the build plan live in [SPEC.md](SPEC.md).

## Setup

```bash
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env      # then fill in GEMINI_API_KEY
```

## Commands

```bash
# Offline end-to-end run on the bundled sample payload (no API key needed)
.venv\Scripts\python.exe -m briefing.cli dry-run --edition evening --date 2026-09-03

# Generate from a real payload file
.venv\Scripts\python.exe -m briefing.cli run --edition morning --payload path\to\payload.json

# Check every data source (live network calls, ~60s)
.venv\Scripts\python.exe -m briefing.cli test-sources

# Computed levels: pivots, DMAs, PCR, OI walls, breadth, sector leaders
.venv\Scripts\python.exe -m briefing.cli analyse

# Fetch, rule-filter and score today's headlines ('stub' works without an API key)
.venv\Scripts\python.exe -m briefing.cli score-news --provider stub

# Verify Google delivery credentials and access
.venv\Scripts\python.exe -m briefing.cli check-google --test-alert

# Refresh the NSE trading-holiday calendar
.venv\Scripts\python.exe -m briefing.cli refresh-holidays

# Tests
.venv\Scripts\python.exe -m unittest discover -s tests
```

Editions: `morning` (08:00 IST) and `evening` (18:00 IST), every day. On weekends and NSE
holidays both switch automatically to their `weekend_*` templates.

Each issue is a plain-prose newsletter: a title line, capital-letter section headings,
ordinary paragraphs, no jargon and no acronyms. Every story is followed through its
consequences in flowing sentences; the layers are never labelled. The house rules and the
data-to-plain-phrase table live in `prompts/_core_rules.txt`.

## Status

Pipeline complete and verified on live data (2026-09-10): fetchers for yfinance, NSE
(indices, breadth, FII/DII, option chain, F&O ban, participant OI, announcements, block
deals, holidays), PIB and Google News; local pivots, moving averages, option-chain
analytics, breadth and sector ranking; keyword gate plus batched Gemini scorer; payload
builders for the four templates; generation; the zero-fabrication verifier; and delivery
over Telegram and/or Gmail with a Sheets archive row and a Calendar event.

BSE and GIFT Nifty are optional sources: they rarely work from outside India and their
absence never marks a run as degraded.

Deployed as a GitHub Actions scheduled workflow (`.github/workflows/briefing.yml`) rather
than the Oracle VM originally planned — Oracle sign-up did not go through. See
[deploy/GITHUB_ACTIONS.md](deploy/GITHUB_ACTIONS.md) for the secrets to add and how it
runs. The Oracle path (`deploy/DEPLOY.md`) is kept as a documented fallback.

Remaining: confirm a delivery channel is actually working end to end (run
`check-google --test-alert` above) and watch the archive Sheet for the first few
unattended days once the GitHub secrets are in place.
