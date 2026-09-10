# Deploying with GitHub Actions

Decided 2026-09-10 after signing up for Oracle Cloud's Always Free tier did not go
through. GitHub Actions needs no VM, no card, and no babysitting: `.github/workflows/briefing.yml`
runs the morning and evening editions on their own schedule, for free, on GitHub's
infrastructure. NSE has been reachable from this dev machine in every live run so far, so
the loss of an India-region IP has not been a problem in practice; BSE — which is already
blocked here — is an optional source and its absence never degrades an issue.

This assumes the code is already pushed to GitHub. It stays there as a normal repo; only
`.env`, the service account file, and everything under `out/` and `raw/` are excluded
(see `.gitignore`).

## 1. Add the secrets

**Repo → Settings → Secrets and variables → Actions → New repository secret.** Add:

| Secret | Value |
|---|---|
| `GEMINI_API_KEY` | your Gemini API key |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | the full contents of the service account JSON key file, pasted as-is (multi-line is fine — GitHub secrets are not single-line-only) |
| `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` | if using Telegram |
| `ALERT_EMAIL_FROM`, `ALERT_EMAIL_TO`, `GMAIL_APP_PASSWORD` | if using email |

At least one delivery channel (Telegram or email) is required, same as running locally.
`config.yaml`'s `google.sheet_id` and `google.calendar_id` are not secrets — they are
already committed, since a sheet or calendar ID does not grant access on its own; only
the service account's credentials do.

## 2. Confirm the schedule is enabled

Scheduled workflows are enabled automatically on push, but only on the repo's default
branch. Open the **Actions** tab once after pushing to confirm "Daily market briefing"
is listed and not shown as disabled.

## 3. Run it once by hand

**Actions → Daily market briefing → Run workflow**, pick an edition, and watch the log.
A run that fails prints the same `[FAILED]` / `[degraded]` / `[verify]` lines you'd see
locally. Every run also uploads the generated issue as a build artifact for 7 days —
open the run and download it from the **Artifacts** section — so a run can be checked
without waiting on Telegram or email.

## 4. Leave it running

- **08:00 and 18:00 IST, every day** — the morning and evening editions.
- **Sunday 02:00 IST** — refreshes `briefing/holidays.yaml` from the NSE holiday API and
  commits the change back to the repo directly from the workflow (using the
  automatically-provided `GITHUB_TOKEN`, not your own credentials). This also produces at
  least one commit a week, which keeps GitHub from disabling the schedule after 60 days
  of a quiet repo.

## Known limits of this approach

- GitHub's schedule is UTC-only and can run a few minutes late under heavy platform
  load; it is not a real-time guarantee. For a briefing that goes out once at 8 and once
  at 6, this has not mattered in testing.
- Runners are not India-based. If NSE ever starts blocking GitHub's IP ranges the way it
  currently blocks BSE, the fix is the same fallback the project always had: an
  India-region VM (Oracle, or otherwise) running `deploy/run_edition.sh` on cron — see
  [DEPLOY.md](DEPLOY.md). Nothing about the application code would need to change.
- The free minutes quota (2,000/month on a free personal account) is not a real
  constraint here: two runs a day at well under a minute each is roughly 60 minutes a
  month.
