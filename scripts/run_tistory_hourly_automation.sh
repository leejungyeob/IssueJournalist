#!/bin/zsh
set -euo pipefail

ROOT="/Users/goods99j/Desktop/IssueJournalist"
LOG_DIR="$ROOT/logs"
LOCK_DIR="$LOG_DIR/tistory-hourly.lock"
RUN_LOG="$LOG_DIR/tistory-hourly-run.log"

mkdir -p "$LOG_DIR"

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  echo "[$(date '+%Y-%m-%d %H:%M:%S %z')] SKIP: previous hourly run is still active" >> "$RUN_LOG"
  exit 0
fi

cleanup() {
  rmdir "$LOCK_DIR" 2>/dev/null || true
}
trap cleanup EXIT

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

cd "$ROOT"
echo "[$(date '+%Y-%m-%d %H:%M:%S %z')] START: hourly Tistory publish batch" >> "$RUN_LOG"
python3 scripts/run_tistory_hourly_batch.py >> "$RUN_LOG" 2>&1
echo "[$(date '+%Y-%m-%d %H:%M:%S %z')] END: hourly Tistory publish batch" >> "$RUN_LOG"
