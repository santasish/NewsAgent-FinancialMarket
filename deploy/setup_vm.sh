#!/usr/bin/env bash
# One-shot bootstrap for the Oracle Always-Free VM (Ubuntu, ap-mumbai-1).
#
# Safe to re-run: every step checks before acting. It never overwrites .env, because
# that file holds the only copy of the secrets on the box.
#
#   ./setup_vm.sh                       # set up from files already in place
#   ./setup_vm.sh https://github.com/you/news-agent.git

set -euo pipefail

APP_DIR="${APP_DIR:-$HOME/news-agent}"
REPO_URL="${1:-}"
PYTHON_MIN="3.10"

info()  { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
warn()  { printf '\033[33m [!] %s\033[0m\n' "$*"; }
ok()    { printf '\033[32m [ok] %s\033[0m\n' "$*"; }

info "Setting the system clock to IST"
if [[ "$(timedatectl show -p Timezone --value)" != "Asia/Kolkata" ]]; then
    sudo timedatectl set-timezone Asia/Kolkata
fi
ok "timezone $(timedatectl show -p Timezone --value), now $(date -Is)"

info "Installing system packages"
sudo apt-get update -qq
sudo apt-get install -y -qq python3 python3-venv python3-pip git cron
sudo systemctl enable --now cron >/dev/null 2>&1 || true
ok "python $(python3 --version 2>&1 | cut -d' ' -f2), git, cron"

python3 - <<PY || { echo "Python ${PYTHON_MIN}+ is required" >&2; exit 1; }
import sys
raise SystemExit(0 if sys.version_info >= tuple(int(p) for p in "${PYTHON_MIN}".split(".")) else 1)
PY

info "Placing the application in $APP_DIR"
if [[ -n "$REPO_URL" ]]; then
    if [[ -d "$APP_DIR/.git" ]]; then
        git -C "$APP_DIR" pull --ff-only
        ok "updated existing checkout"
    else
        git clone "$REPO_URL" "$APP_DIR"
        ok "cloned $REPO_URL"
    fi
elif [[ -d "$APP_DIR/briefing" ]]; then
    ok "using files already in $APP_DIR"
else
    echo "No repo URL given and no application found in $APP_DIR." >&2
    echo "Either pass a git URL or copy the project there first (scp -r)." >&2
    exit 1
fi

cd "$APP_DIR"

info "Building the virtual environment"
[[ -d .venv ]] || python3 -m venv .venv
./.venv/bin/python -m pip install --quiet --upgrade pip
./.venv/bin/python -m pip install --quiet -r requirements.txt
ok "dependencies installed"

info "Checking secrets"
if [[ ! -f .env ]]; then
    cp .env.example .env
    warn ".env created from the example — it has no keys in it yet."
    warn "Fill in GEMINI_API_KEY and the Google settings before the first scheduled run:"
    warn "    nano $APP_DIR/.env"
else
    ok ".env present (left untouched)"
fi
chmod 600 .env

chmod +x deploy/run_edition.sh deploy/setup_vm.sh

info "Refreshing the NSE holiday calendar"
./.venv/bin/python -m briefing.cli refresh-holidays || warn "holiday refresh failed — will retry on Sunday's cron"

info "Installing the cron schedule"
MARKER_BEGIN="# >>> news-agent begin >>>"
MARKER_END="# <<< news-agent end <<<"
CRON_FILE="$(mktemp)"

# Replace only our own block, between the markers. Everything else in the user's
# crontab is carried through untouched — this script must never delete a job it did
# not create, and it must stay idempotent across re-runs.
crontab -l 2>/dev/null | sed "\|${MARKER_BEGIN}|,\|${MARKER_END}|d" >"$CRON_FILE" || true
{
    echo "$MARKER_BEGIN"
    sed "s|__APP_DIR__|$APP_DIR|g" deploy/crontab.template
    echo "$MARKER_END"
} >>"$CRON_FILE"

crontab "$CRON_FILE"
rm -f "$CRON_FILE"
ok "cron installed — 08:00, 18:00 and 20:30 IST"
crontab -l | grep -v '^#' | grep -v '^$' | sed 's/^/     /'

info "Verifying data sources"
./.venv/bin/python -m briefing.cli test-sources || warn "some sources failed — see above"

info "Done"
cat <<EOF

  Next steps
    1. Put your keys in       $APP_DIR/.env
    2. Check Google access    cd $APP_DIR && ./.venv/bin/python -m briefing.cli check-google --test-alert
    3. Try one run by hand    cd $APP_DIR && ./deploy/run_edition.sh evening; tail logs/\$(date +%F)_evening.log

  Logs live in $APP_DIR/logs and are pruned after 30 days.
EOF
