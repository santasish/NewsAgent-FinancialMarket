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

## 4. Set up the external trigger (required — read this)

**GitHub's native `schedule` trigger turned out not to work for this.** Two real runs on
2026-09-10/11 landed 4-5 hours late (a schedule for 08:00 IST fired at ~12:51 IST) —
GitHub's own docs say `schedule` is deprioritised under load with no timing guarantee at
all, and it isn't just "a few minutes" in practice.

The fix (as of 2026-09-11): the morning and evening runs are triggered by
`repository_dispatch`, an API call, instead. That event type goes through the normal
runner queue rather than the deprioritised schedule one. An external free cron service
plays the role GitHub's own scheduler used to:

1. **Create a GitHub personal access token** scoped to just this repo:
   [github.com/settings/tokens?type=beta](https://github.com/settings/tokens?type=beta)
   (fine-grained) → select only this repository → under "Repository permissions" set
   **Contents: Read and write**. (A classic token with the `public_repo` scope also
   works, since this repo is public.) Copy the token — you won't see it again.
2. **Sign up for a free external cron service** — [cron-job.org](https://cron-job.org)
   works well and lets you pick a timezone directly (Asia/Kolkata), so there's no UTC
   conversion to get wrong.
3. **Create two cron jobs**, one per edition:

   | Field | Morning | Evening |
   |---|---|---|
   | URL | `https://api.github.com/repos/<owner>/<repo>/dispatches` | same |
   | Method | POST | POST |
   | Schedule | 6:30 AM, Asia/Kolkata, daily | 6:30 PM, Asia/Kolkata, daily |
   | Header | `Authorization: Bearer <your PAT>` | same |
   | Header | `Accept: application/vnd.github+json` | same |
   | Header | `Content-Type: application/json` | same |
   | Body | `{"event_type": "run-morning"}` | `{"event_type": "run-evening"}` |

   Replace `<owner>/<repo>` with this repo's actual path. The PAT is entered directly
   into cron-job.org's own header field — it is never stored in this repo or anywhere
   Claude has access to.
4. **Test each job manually** from cron-job.org's dashboard once, then check the
   **Actions** tab here for a run that started from a `repository_dispatch` event.

Native `schedule` is kept only for the Sunday holiday-calendar refresh below, where a
multi-hour delay genuinely doesn't matter.

## 5. Leave it running

- **6:30am and 6:30pm IST, every day** — the morning and evening editions, fired by the
  external cron jobs set up above.
- **Sunday ~02:00 IST** — refreshes `briefing/holidays.yaml` from the NSE holiday API and
  commits the change back to the repo directly from the workflow (using the
  automatically-provided `GITHUB_TOKEN`, not your own credentials). Still on GitHub's
  native `schedule`, since timing doesn't matter here; this also produces at least one
  commit a week, which keeps GitHub from disabling the workflow after 60 days of a quiet
  repo.

## Known limits of this approach

- The external cron service is now a dependency: if cron-job.org (or whichever service
  you use) has an outage, no `repository_dispatch` fires and that edition is silently
  skipped for the day. There's no automatic fallback — check the Actions tab or the
  archive Sheet occasionally, especially in the first couple of weeks.
- `repository_dispatch` avoids GitHub's `schedule`-specific deprioritisation, but GitHub
  Actions as a whole still has no hard real-time SLA. This is a real improvement over the
  4-5 hour delays observed on `schedule`, not a guarantee of exact timing.
- Runners are not India-based. If NSE ever starts blocking GitHub's IP ranges the way it
  currently blocks BSE, the fix is the same fallback the project always had: an
  India-region VM (Oracle, or otherwise) running `deploy/run_edition.sh` on cron — see
  [DEPLOY.md](DEPLOY.md). Nothing about the application code would need to change.
- The free minutes quota (2,000/month on a free personal account) is not a real
  constraint here: two runs a day at well under a minute each is roughly 60 minutes a
  month.
