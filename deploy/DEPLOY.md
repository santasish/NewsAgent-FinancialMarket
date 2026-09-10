# Deploying to the Oracle Always-Free VM

The agent runs twice a day on a small always-on Linux box in Mumbai. An Indian IP
matters: NSE's endpoints are noticeably friendlier to one, and BSE — which blocks the
development machine outright — is expected to work from there.

---

## 1. Create the VM

At [cloud.oracle.com](https://cloud.oracle.com), sign up for the Always Free tier and set
the **home region to India West (Mumbai)** — `ap-mumbai-1`. The home region is chosen once
at signup and cannot be changed afterwards, so get this right first.

Then **Compute → Instances → Create Instance**:

| Setting | Value |
|---|---|
| Image | Canonical Ubuntu 24.04 (or 22.04) |
| Shape | `VM.Standard.A1.Flex` (Ampere, 1 OCPU / 6 GB) — or `VM.Standard.E2.1.Micro` |
| Networking | default VCN, assign a public IPv4 address |
| SSH keys | generate a key pair and **download the private key** |

Both shapes are Always Free. Ampere is the better machine but is frequently out of
capacity in popular regions; if creation fails with "out of host capacity", take the
E2.1.Micro — this workload is tiny and runs fine on it.

No inbound ports are needed beyond SSH. The agent only makes outbound calls.

Connect:

```bash
chmod 400 ~/Downloads/ssh-key.key
ssh -i ~/Downloads/ssh-key.key ubuntu@<public-ip>
```

---

## 2. Get the code onto the box

**Option A — via GitHub** (easier to update later). Push the project to a private repo,
then on the VM:

```bash
git clone https://github.com/<you>/news-agent.git ~/news-agent
```

**Option B — copy directly** from the Windows machine, no repo needed:

```powershell
scp -i C:\path\to\ssh-key.key -r "C:\Users\SANTASISH\OneDrive\Desktop\News Agent" ubuntu@<public-ip>:~/news-agent
```

Never copy `.env` into a git repo. If you use Option A, transfer it separately with `scp`.

---

## 3. Run the bootstrap

```bash
cd ~/news-agent
chmod +x deploy/setup_vm.sh
./deploy/setup_vm.sh
```

It sets the clock to IST, installs Python and cron, builds the virtualenv, refreshes the
NSE holiday calendar, installs the schedule, and finishes by testing every data source.
It is safe to re-run, and it will never overwrite an existing `.env`.

If you see `bad interpreter: /usr/bin/env bash^M`, the files picked up Windows line
endings in transit:

```bash
sudo apt-get install -y dos2unix && dos2unix deploy/*.sh
```

---

## 4. Secrets

```bash
nano ~/news-agent/.env
chmod 600 ~/news-agent/.env
```

Needs `GEMINI_API_KEY`, the Google service-account credentials, and the alert email
settings. For the service account, either copy the JSON key file across and point
`GOOGLE_SERVICE_ACCOUNT_FILE` at it, or inline it as base64:

```bash
base64 -w0 news-agent-key.json    # paste the output as GOOGLE_SERVICE_ACCOUNT_JSON
```

Then confirm delivery works end to end:

```bash
cd ~/news-agent
./.venv/bin/python -m briefing.cli check-google --test-alert
```

---

## 5. Verify

```bash
# One real run, exactly as cron will invoke it
./deploy/run_edition.sh evening
tail -40 logs/$(date +%F)_evening.log

# What the schedule looks like
crontab -l
```

BSE is worth re-checking here — it fails from a non-Indian IP but should come back:

```bash
./.venv/bin/python -m briefing.cli test-sources
```

---

## The schedule

| Time (IST) | Job | Notes |
|---|---|---|
| 08:00 daily | morning | Weekend/holiday variant selected automatically |
| 18:00 daily | evening | Weekend/holiday variant selected automatically |
| 02:00 Sunday | refresh-holidays | Keeps the NSE calendar current |

Cron is pinned to `Asia/Kolkata` via `CRON_TZ`, and the application independently checks
IST, so a wrong system clock cannot shift an edition.

Logs are written to `~/news-agent/logs/YYYY-MM-DD_<edition>.log` and pruned after 30 days.

---

## Operating notes

**Oracle reclaims idle Always-Free instances.** The daily cron keeps this one active, but
if the VM is ever stopped for a long stretch it can be reclaimed. Check occasionally.

**Watch the first week.** The archive Sheet is the fastest health check: one row per run
with an `OK` / `DEGRADED` / `VERIFY FAILED` status. Any run that is degraded or fails
verification also sends an email.

**Updating the code** (Option A):

```bash
cd ~/news-agent && git pull && ./.venv/bin/python -m pip install -q -r requirements.txt
```

Re-run `./deploy/setup_vm.sh` after a pull if dependencies or the cron schedule changed.
