#!/usr/bin/env bash
# Cron entry point for one briefing run.
#
# Cron gives a near-empty environment and no terminal, so everything is made explicit:
# absolute app directory, the venv interpreter by path, and all output captured to a
# dated log. Never `set -e` here — a non-zero exit from the run is information we want
# to record and pass on, not a reason to abandon the log.

set -uo pipefail

APP_DIR="${APP_DIR:-$HOME/news-agent}"
LOG_RETENTION_DAYS="${LOG_RETENTION_DAYS:-30}"

EDITION="${1:-}"
if [[ -z "$EDITION" ]]; then
    echo "usage: run_edition.sh morning|evening" >&2
    exit 2
fi

cd "$APP_DIR" || { echo "cannot cd to $APP_DIR" >&2; exit 2; }
mkdir -p logs

LOG="logs/$(date +%F)_${EDITION}.log"
status=0

{
    echo "=== $(date -Is) starting ${EDITION} ==="
    ./.venv/bin/python -m briefing.cli run --edition "$EDITION"
    status=$?
    echo "=== $(date -Is) finished ${EDITION} exit=${status} ==="
} >>"$LOG" 2>&1

find logs -name '*.log' -type f -mtime "+${LOG_RETENTION_DAYS}" -delete 2>/dev/null

exit "$status"
