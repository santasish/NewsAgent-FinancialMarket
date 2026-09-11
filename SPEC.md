# Daily Market Briefing Agent — Consolidated Spec & Build Plan

Status: decisions locked 2026-09-10; revised the same day to two editions in plain
newsletter prose (see §1a). Supersedes the raw notes pasted into chat.

---

## 1. Decision log (resolved contradictions)

| Topic | Decision |
|---|---|
| Runs per day | 2, every day: Morning 08:00 and Evening 06:00 PM (IST). The US-open addendum was dropped on 2026-09-10. |
| Weekends / NSE holidays | Same 2 runs, switched to the weekend templates: Morning (global/macro + weekend news) and Evening "Week-Ahead". |
| Morning layout | Merged: formal Morning prompt sections + PIB, Sector Snapshot, Earnings/Concall, Micro-cap Catalysts |
| Delivery | Telegram and/or email, whichever is configured, plus a Sheets archive row and a Calendar event. Channels are independent; the briefing counts as delivered if any route succeeds. Google Docs dropped — see the delivery note in §3. |
| NSE data risk | Free unofficial NSE JSON APIs only. On failure: omit section, log, alert. Paid/broker source deferred. |
| GIFT Nifty | Best-effort scrape of a public page; omit if unavailable; implied open inferred from US/Asia |
| News outlets | Official (PIB, RBI, SEBI, NSE, BSE) + tier-1 press (Moneycontrol, ET, Business Standard, Mint, Reuters India) |
| Pivots / DMA | Computed locally: classic pivot formula from previous session H/L/C; 20/50-DMA from OHLC history |
| LLM | Provider-agnostic adapter. Default: Google Gemini free tier (2.5 Flash-Lite = scoring, 2.5 Flash = generation). Anthropic / OpenAI adapters kept as paid upgrades. |
| Impact depth | Three layers (immediate effect, knock-on to related firms, wider economy and flows) for macro and index-level items; two for company-level items. Written as prose; the layers are never labelled. |
| Scoring gate | Category-aware: score 0–10 + label {macro, earnings, mna, microcap, pib, global}; keep score >= 6 |
| Budget | $0 / month. Everything on free tiers. |
| Hosting | GitHub Actions (revised 2026-09-10; Oracle Always-Free sign-up did not succeed). Trigger revised again 2026-09-11: an external free cron service fires `repository_dispatch`, not GitHub's native `schedule` — see below and deploy/GITHUB_ACTIONS.md. |
| Google auth | Service account; Drive folder, Sheet and Calendar shared to it |
| Repo shape | Single Python package, one CLI: `briefing run --edition morning|evening` |
| Alerting | Email on failure + `DEGRADED` banner at top of any briefing with missing sections |
| Fabrication check | Code-level: every number and ticker in output must exist in payload; else regenerate once, then flag |
| Review gate | Zero-touch from day one |

### Non-negotiables
1. Zero fabrication — omit rather than guess. Enforced in prompt AND in code.
2. Every story is followed through its consequences (immediate, knock-on, wider).
3. Plain English. No jargon, no acronyms, no trader shorthand.

### 1a. Writing style (decided 2026-09-10)

The first live outputs read like an institutional desk note: `1st Order (Direct Impact):`
labels, bracketed acronyms, emoji headers, BTST/PCR/OI/R1 shorthand. The user rejected
that. The issue is now a newsletter in plain prose:

- A title line, then sections with CAPITAL-LETTER headings and ordinary paragraphs. No
  markdown, no dashed rules, no emoji. The capital-letter heading is the only structural
  convention; `briefing/layout.py` uses it to split for Telegram and to bold for email.
- The impact chain is still mandatory but is written as flowing sentences. The words
  "first/second/third order", "direct impact", "ripple", "downstream" and "macro and
  flows" are banned from the output.
- `prompts/_core_rules.txt` carries a translation table from every data key to its plain
  phrase (put-call ratio -> "bets on a rise outnumber bets on a fall", call wall -> "the
  level most traders have bet the index will not climb past", and so on) and a banned-word
  list (headwinds, robust, bullish, oversold, catalyst ...).
- The payload's own assessment strings (`pcr_assessment`, FII stance, trend) are written
  in the same plain language, because the model echoes them.
- Figures are quoted exactly as given, never rounded, so the verifier stays strict.

---

## 2. Editions

### 2.1 Morning Edition — 08:00 IST (daily)
Purpose: preparation & execution. Window: previous NSE close -> now (US/Europe close, Asia open, overnight filings).

Sections, in order (headings as printed):
1. Title line
2. THE WORLD OVERNIGHT — Wall Street, Asia, Europe, the four macro readings, the opening call (direction only when GIFT Nifty is absent)
3. WHAT IS MOVING THIS MORNING — the scored stories, each followed through its consequences
4. WHERE THE BIG MONEY IS LEANING — foreign futures stance, where option bets sit, frozen-derivative list
5. DEALS AND ANNOUNCEMENTS — M&A, buybacks, demergers, stake sales
6. RESULTS AND WHAT MANAGEMENT SAID
7. SMALLER COMPANIES WORTH A LOOK — orders, block deals, capacity
8. FROM THE GOVERNMENT — PIB, RBI, SEBI releases
9. YESTERDAY'S WINNERS AND LOSERS — sector leaders and laggards
10. THE PLAN FOR TODAY — Nifty and Bank Nifty levels in plain words, watchlists
11. SOURCES AND LINKS

Weekend variant (`weekend_morning.txt`): THE WORLD WHILE INDIA WAS CLOSED · NEWS THAT LANDED · DEALS AND ANNOUNCEMENTS · FROM THE GOVERNMENT · CARRY THIS INTO [next session] · SOURCES AND LINKS.

### 2.2 Evening Edition — 06:00 PM IST (daily)
Purpose: post-mortem & position adjustment. Window: 09:15 – 17:45 IST.

Sections (headings as printed): HOW THE DAY WENT · WHAT HAPPENED TODAY · WHERE THE MONEY WENT · THE MOOD IN THE OPTIONS MARKET · FILED AFTER THE BELL · OVERNIGHT: WHAT COULD MOVE THINGS BEFORE TOMORROW · TOMORROW'S LEVELS · SOURCES AND LINKS.

Weekend variant (`weekend_evening.txt`): WHERE THE WORLD STANDS · WHAT CAME IN OVER THE BREAK · THEMES FOR THE WEEK FROM [next session] · SOURCES AND LINKS.

---

## 3. Data source map

Verified against live endpoints on 2026-09-10. ✅ = working, ⚠ = degraded.

| Data | Source | Endpoint / method | Status |
|---|---|---|---|
| Brent, US10Y, DXY, USD/INR, S&P, Nasdaq, Dow, Nikkei, HSI, FTSE, DAX, Nifty, Bank Nifty | yfinance | one batched 6-month download | ✅ |
| Benchmarks, 12 sector indices, market breadth | NSE | `/api/allIndices` (carries advances/declines) | ✅ |
| India VIX | NSE | same call | ✅ |
| Option chain OI → PCR, call/put walls | NSE | `/api/option-chain-contract-info` → `/api/option-chain-v3?expiry=` | ✅ |
| FII/DII provisional cash | NSE | `/api/fiidiiTradeReact` | ✅ |
| FII index-futures positioning | NSE archives | `fao_participant_oi_DDMMYYYY.csv` (T-1, walks back 5 days) | ✅ |
| F&O ban list | NSE archives | `fo_secban.csv` | ✅ |
| Corporate announcements | NSE | `/api/corporate-announcements?index=equities` | ✅ |
| Block deals | NSE | `/api/block-deal` | ✅ |
| NSE holiday calendar | NSE | `/api/holiday-master?type=trading` → `briefing/holidays.yaml` | ✅ |
| Press headlines | Google News RSS | 6 site-scoped queries over the approved domains | ✅ (~100/run) |
| PIB releases | PIB | scrape `Allrel.aspx?reg=3&lang=1` for English titles + PRID | ⚠ thin (~3/run) |
| BSE announcements | BSE | `api.bseindia.com/.../AnnSubCategoryData/w` | ⚠ blocked from this IP |
| GIFT Nifty | — | no free source found | ⚠ omitted by design |
| Pivots, 20/50-DMA | computed locally | classic pivots over the yfinance history | ✅ |
| PCR, call/put walls, max pain | computed locally | from the fetched option chains | ✅ |
| Breadth ratio, sector leaders/laggards | computed locally | from `allIndices` | ✅ |
| FII index-futures long ratio | computed locally | from participant OI | ✅ |

**Delivery decision, revised 2026-09-10 — Google Docs dropped, email is the channel.**

A service account has **no Drive storage quota** on a personal Google account. It can edit
files you already own — the archive Sheet and the Calendar both work — but `files.create`
always fails with `storageQuotaExceeded`, so it can never create the daily Doc. The only
ways round that are OAuth (browser consent, token refreshed headless thereafter) or a paid
Workspace Shared Drive. OAuth was attempted and abandoned: Google's consent screen would
not publish without domain/privacy-policy configuration, and an app left in **Testing**
status gets refresh tokens that expire after **7 days** — the agent would have died quietly
a week after setup.

Email needs none of that, and suits a daily newsletter better anyway. The Docs and OAuth
code has been deleted rather than left dormant; Google scopes are now only `spreadsheets`
and `calendar.events`. Revisit only if a Workspace account appears.

**Telegram added 2026-09-10** as the lowest-friction channel: a bot token and chat id, no
Google involvement at all. A briefing runs to ~7000 characters against Telegram's 4096
limit, so it is split on its own section dividers (never mid-sentence) and each part is
sent inside `<pre>` to preserve the fixed-width layout.

**Note on the user's existing stock-screener system.** It has its own EC2 host, a
multi-channel `NotificationRouter` (Telegram/Discord/Email), LiteLLM with several
providers, and a Dhan market-data provider — any of which this agent could have reused.
Decision (2026-09-10): **keep this agent fully standalone**; do not modify that repo. Only
the Telegram approach was adopted, reimplemented here rather than imported. Its
`src/briefing.py` is a different report (screener regime, SQI focus list, basket
transitions) and does not overlap with these editions.

**Screener technical engine: ported, then reverted (2026-09-10).** The screener's
`indicators.py` / `exhaustion.py` maths (Fibonacci pivots, MA alignment, ATR, velocity
percentile, exhaustion layers, beta) was ported and run over the index series, then removed
at the user's request. The briefing is back to classic pivots and 20/50-DMA. Do not
reintroduce without asking.

**Access notes**
- NSE `/api/` paths return 403 to a bare request. A session must first load
  `/market-data/live-equity-market` and `/option-chain` to collect cookies, then send the
  API call with XHR headers and a matching Referer. `NSESession` re-warms once on 401/403.
- NSE responds with Brotli-compressed JSON; the `Brotli` package is required or every
  payload decodes to garbage.
- **GIFT Nifty absent → implied open is inferred, never invented.** The morning prompt
  replaces the missing indicator with a direction-only call ("Gap-Down bias, reasoned
  from…") that cites payload figures, states that GIFT Nifty was unavailable, and is
  forbidden from quoting a level or point value for the open.
- **GIFT Nifty: fails closed.** NSE IX gates its quote API, and Moneycontrol's
  `gift-nifty-50-9.html` actually renders NIFTY 50 spot — a plausible number that is the
  wrong instrument. The fetcher verifies the page's own instrument label and refuses to
  return anything unless it says GIFT Nifty. Implied open is inferred from US/Asia instead.
- **BSE** redirects to `error_Bse.html` from this network; likely IP-based, so it may work
  from the Mumbai VM. NSE announcements plus the news feed cover most of the same ground.
- **PIB** RSS ignores its own `Lang` parameter and serves Hindi only, hence the scrape.
  Google News also covers `pib.gov.in` in English as a second path.

All fetchers: up to 3 retries with jittered backoff, 25s timeout, and a `FetchResult` that
carries the failure rather than raising. Raw snapshot saved per run for audit.

---

## 4. Pipeline

```
FETCH ──> PARSE/NORMALISE ──> FILTER+SCORE ──> BUILD PAYLOAD ──> GENERATE ──> VERIFY ──> DELIVER
                                                                     ^            |
                                                                     └─ retry x1 ─┘ (on verify fail)
```

1. **Fetch** — every source in §3 runs concurrently; each returns `{ok, data, error}`.
2. **Parse** — normalise to typed dataclasses; strip HTML; dedupe headlines by URL + fuzzy title.
3. **Filter + Score**
   - Rule gate: keyword allowlist (buyback, demerger, order win, Q1–Q4, margin, guidance, repo, block deal, bulk deal, ...), drop obvious noise (opinion, listicles).
   - LLM scorer (cheap model), batched 20 headlines/call, strict JSON out: `{score: 0-10, category, one_line_reason}`.
   - Keep score >= 6 (lowered from 7 on 2026-09-10: real policy stories were landing at 6). Per-category caps from config (macro 4, global 3, earnings 3, mna 4, microcap 3, pib 3).
   - Each headline is tagged `[press]`, `[NSE filing]` or `[PIB]` for the scorer, which applies a different bar to each. The scorer's subject rule: a listed company, a regulator, the government or a macro release; stories about individuals or personal finance score 0 (a "man earns ₹12,000 a day growing roses" story once reached the briefing as "earnings").
   - Every scored headline is written to `out/<date>_<edition>_scored.json` so the threshold can be tuned against real days.
4. **Build payload** — edition-specific JSON exactly matching the schemas in the system prompts; include `degraded` flag and `missing_sections` list.
   - **Design rule: the payload pre-computes every derived value** (point changes, basis-point moves, percentages, ratios, pivot levels). The model formats numbers; it never does arithmetic. This is what lets the verifier be strict without false positives.
5. **Generate** — edition system prompt (`prompts/morning.txt`, `evening.txt`, `weekend_morning.txt`, `weekend_evening.txt`) with `_core_rules.txt` (the house rules and the plain-phrase translation table) injected. Temperature 0.2.
6. **Verify** — extract numbers (levels, %, ₹ amounts, prices) and tickers/company names from output; each must appear in payload (numeric tolerance for formatting only). Fail -> regenerate once with the violations listed -> if still failing, deliver with `⚠ VERIFICATION FLAG` banner and alert.
7. **Deliver** — Telegram (split at section headings, headings in bold) and/or email (headings bold, serif body), then a Sheets archive row `[date, time IST, edition, channels, status, notes]` and a Calendar event. Failure alert if a non-optional fetch failed, verification flagged, or a channel errored. BSE and GIFT Nifty are *optional* sources: their absence never marks a run degraded or puts a note on the issue.

---

## 5. Repo layout

```
news-agent/
  briefing/
    __init__.py
    cli.py                 # `briefing run --edition ...`, `briefing dry-run`, `briefing test-sources`
    config.py              # loads config.yaml + .env
    schedule.py            # IST time, trading-day / weekend routing
    fetch/
      macro.py             # yfinance
      nse.py               # cookie session + all NSE endpoints
      bse.py
      pib.py
      news.py              # Google News RSS by allowed domains
      gift_nifty.py
    compute/
      pivots.py            # classic pivots, DMAs
      derivatives.py       # PCR, walls, max pain from option chain
    filter/
      rules.py
      scorer.py            # LLM scoring, batched
    payload/
      morning.py  evening.py  weekend.py
    llm/
      base.py              # Provider interface: complete(system, user, model_tier)
      gemini.py  anthropic.py  openai.py
    generate.py
    layout.py              # heading convention shared by Telegram and email
    verify.py
    deliver/
      gdocs.py  gsheets.py  gcal.py  email.py
    alerts.py
  prompts/
    _core_rules.txt        # house rules + plain-phrase translation table, injected into every edition prompt
    morning.txt  evening.txt  weekend_morning.txt  weekend_evening.txt
    scorer.txt
  config.yaml              # sources, thresholds, caps, allowed domains, model tiers
  .env.example
  tests/
    fixtures/              # saved raw responses + the two sample payloads from the spec
  deploy/
    setup_vm.sh            # idempotent Oracle VM bootstrap: TZ, python, venv, cron, checks
    run_edition.sh         # cron entry point: absolute paths, dated logs, 30-day pruning
    crontab.template       # IST entries for 08:00 / 18:00 + Sunday holiday refresh
    DEPLOY.md              # step-by-step Oracle setup
  requirements.txt
  README.md
```

---

## 6. Config (config.yaml sketch)

```yaml
timezone: Asia/Kolkata
editions:
  morning:  {time: "08:00", days: all}
  evening:  {time: "18:00", days: all}
llm:
  provider: gemini             # gemini | anthropic | openai
  tiers:
    score:    {gemini: gemini-2.5-flash-lite, anthropic: claude-haiku-4-5-20251001, openai: gpt-4o-mini}
    generate: {gemini: gemini-2.5-flash,      anthropic: claude-sonnet-5,            openai: gpt-4o}
  rate_limit: {requests_per_minute: 10}   # stay under Gemini free-tier RPM
scoring: {threshold: 6, batch_size: 20}
caps: {macro: 4, global: 3, earnings: 3, mna: 4, microcap: 3, pib: 3}   # keyed by scorer category
news_domains: [pib.gov.in, rbi.org.in, sebi.gov.in, nseindia.com, bseindia.com,
               moneycontrol.com, economictimes.indiatimes.com, business-standard.com,
               livemint.com, reuters.com]
google: {drive_folder_id: "", sheet_id: "", calendar_id: ""}
alerts: {email_to: ""}
```

Secrets (.env on the VM): `GEMINI_API_KEY`, `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` (optional), `GOOGLE_SERVICE_ACCOUNT_JSON` (base64), `GMAIL_APP_PASSWORD` (alerts via Gmail SMTP).

---

## 7. Cost

**Measured on 2026-09-10** (one evening run, end to end): 4 API calls — 3 scoring batches
plus 1 generation — totalling **10,638 input / 4,360 output tokens**. The plain-prose
prompts measured 12,311 in / 3,994 out (morning) and 6,839 in / 2,181 out (evening). Two runs
a day is roughly 19k in / 6k out daily, or about **0.6M in / 0.2M out per month**.

Billing is enabled on the account, so this bills at Flash rates rather than the free tier.
At Flash-class pricing that lands in the region of **$0.30–1.50/month** — well inside the
original $10 ceiling. Enabling billing also means prompts are not used for model training,
which resolves the privacy trade-off noted below.

Models are pinned to `gemini-3.8-flash` (generation) and `gemini-3.5-flash-lite` (scoring).
`gemini-2.5-flash-lite` is retired for new keys. Deliberately not using `-latest` aliases:
a template-strict pipeline should not have its model change without a decision.

**Pro evaluated and deferred (2026-09-10).** Flash meets all three non-negotiables on live
data and self-corrected when one figure failed verification, so the extra cost and latency
of a Pro model is not justified for an unattended 08:00 job. The A/B was blocked anyway by
a project spending cap (429 RESOURCE_EXHAUSTED, raise at https://ai.studio/spend). Revisit
only if output quality degrades; `briefing run --model <id>` runs an A/B on a saved payload.

### Original free-tier plan (superseded by billing)

| Component | Free tier used | Daily usage | Headroom |
|---|---|---|---|
| Gemini 2.5 Flash-Lite (scoring) | ~1,000 req/day | ~30 batched calls | large |
| Gemini 2.5 Flash (generation) | ~250 req/day | 3–6 calls incl. retries | large |
| Oracle Always-Free VM (1 OCPU / 1 GB or Ampere 4 OCPU / 24 GB) | forever | ~15 min CPU/day | large |
| Google Docs / Sheets / Calendar / Drive APIs | free quota | ~10 calls/run | large |
| Gmail SMTP (alerts) | 500 mails/day | 0–3 | large |

Trade-offs accepted: Gemini free-tier prompts may be used by Google for model improvement; Flash reasoning is a notch below Sonnet/Opus. Paid upgrade path = flip `llm.provider` in config.

**Claude cloud routines: evaluated and rejected (2026-09-10).** Tested directly with a
throwaway probe routine. Anthropic's cloud sandbox routes all traffic through an egress
proxy with a strict **allowlist** — only `api.anthropic.com`, npm, PyPI and JSR are
reachable. Every market-data host was refused at the CONNECT stage with
`connect_rejected (organization policy)`: ipinfo.io, Yahoo Finance, NSE, BSE and PIB alike.
This is not NSE's anti-bot layer; it is the sandbox refusing to open the connection at all.

A routine therefore cannot fetch any of the data this system needs, regardless of how the
code is arranged. The agent must run somewhere with unrestricted outbound internet — the
Oracle VM, or the user's own machine. Do not revisit unless the egress policy changes.

**Local Ollama: evaluated and rejected.** A 4GB-VRAM machine can run a 3–8B model, which is adequate for headline scoring but not for a long strict template with zero-fabrication requirements. Decisive factor: the PC is not reliably powered on at 08:00 / 18:00 IST, and the Oracle free VM has no GPU. Do not revisit unless an always-on GPU host appears.

---

## 8. Build phases

| Phase | Deliverable | Done when |
|---|---|---|
| 0. Setup ✅ | Repo skeleton, config, all 5 edition prompts + scorer, provider adapters, numeric verifier, CLI | `briefing dry-run --edition evening` runs generate -> verify -> write with the stub provider; 7 verifier tests pass; edition routing correct for weekday/weekend |
| 1. Fetchers ✅ | yfinance, NSE session + 8 endpoints, BSE, PIB, Google News, holiday calendar | `briefing test-sources` reports 11/13 OK on live data; `briefing refresh-holidays` populated 20 NSE holidays for 2026 |
| 2. Compute + Filter ✅ | pivots, DMAs, PCR/OI walls/max pain, breadth, sector ranking, FII futures stance, rule gate, batched LLM scorer | `briefing analyse` prints levels and derivatives from live data; `briefing score-news` runs the full gate; 33 tests pass |
| 3. Generation ✅ | 4 payload builders, pipeline orchestration, `run` wired to live data, Gemini adapter with token accounting | Morning and evening both generate from live data and verify clean (75 and 71 numbers traceable in the plain-prose versions); 56 tests pass |
| 3a. Rewrite ✅ | Addendum removed; plain-newsletter prompts; scorer subject rule and source tags; optional sources; heading-based Telegram/email layout; fixtures refreshed from live output | Both editions read as prose with no order labels or acronyms, and verify clean |
| 4. Verify + Deliver ◐ | verifier ✅, missing-data note ✅, Telegram + email + Sheets + Calendar + alerts built; Sheets and Calendar verified | **Remaining: no delivery channel is configured in `.env` — fill in Telegram or Gmail.** |
| 5. Schedule ◐ | Oracle VM path built (bootstrap, cron wrapper, DEPLOY.md) but sign-up did not go through; pivoted to a GitHub Actions workflow instead — see `deploy/GITHUB_ACTIONS.md` and `.github/workflows/briefing.yml`. GitHub's native `schedule` trigger was then confirmed (2026-09-10/11) to run 4-5 hours late, so morning/evening are now fired by `repository_dispatch` from an external free cron service instead; native `schedule` is kept only for the non-time-sensitive weekly holiday refresh. | Workflow updated and pushed. Oracle scripts kept as a documented fallback, not deleted. **Remaining: the user needs to do the one-time external-cron setup in `deploy/GITHUB_ACTIONS.md` §4 (create a GitHub PAT, create the cron-job.org jobs) — this cannot be done on their behalf.** |
| 6. Hardening | retries, raw snapshot archiving, cost logging, prompt tuning from real outputs | you sign off on output quality |

---

## 9. Items only you can do (before Phase 3–5)

1. Get a free Gemini API key from Google AI Studio — needed at Phase 2.
2. Google Cloud: create project, enable Docs + Drive + Sheets + Calendar APIs, create a service account, download JSON key.
3. Create a Drive folder, a Google Sheet (archive), and a Calendar; share all three with the service-account email (Editor).
4. Oracle Cloud: sign up for the Always-Free tier, pick the Mumbai (ap-mumbai-1) home region, create one Always-Free VM (Ubuntu), download the SSH key — needed at Phase 5.
5. Create a Gmail app password for alert emails, and decide the recipient address.

---

## 10. Known risks

- NSE anti-bot behaviour may block cloud IPs; an Indian-region VM reduces this. Mitigations: realistic headers, cookie bootstrap, jittered retries; fallback is graceful omission. If persistent, revisit the broker-API option.
- Gemini free-tier limits or model names can change without notice; the adapter reads model ids from config and the verifier catches quality regressions.
- Oracle Always-Free VMs are reclaimed if idle for long periods on some accounts; the daily cron keeps it active.
- yfinance is unofficial; index tickers occasionally change.
- Google News RSS may throttle; keep query count small (≤ 6 per run).
- LLM template drift; verifier + fixed section-header checks catch structural drift.
- VM cron runs in IST (system TZ set to Asia/Kolkata **and** `CRON_TZ` pinned); the app also
  checks IST itself, so a wrong system clock cannot shift an edition.
- `setup_vm.sh` replaces only the cron block between its own markers, so a re-run never
  deletes jobs it did not create.
- Shell scripts must keep LF endings (`.gitattributes` enforces it). CRLF produces
  `bad interpreter: /usr/bin/env bash^M` on Linux.
- **After-hours classification needs the date, not just the clock.** An item published at
  21:00 yesterday is not tonight's post-close disclosure; `is_after_hours` checks both.
- **Feed bytes must be handed to feedparser directly.** Letting it fetch a URL itself
  produces mojibake on non-ASCII punctuation (`Jewellers’` → `Jewellersâ€™`) and, for PIB,
  no entries at all.
- **Pivots must never be computed from a live session.** Daily feeds publish a partial bar
  for the running session, and pivots from a half-formed high/low are wrong. The scheduled
  run times all fall outside market hours, but `compute_levels` drops a trailing same-day
  bar before 15:30 IST regardless, so an off-schedule run cannot produce bad levels.
