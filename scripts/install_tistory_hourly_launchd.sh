#!/bin/zsh
set -euo pipefail

ROOT="/Users/goods99j/Desktop/IssueJournalist"
LABEL="com.issuejournalist.tistory-hourly-publish"
SOURCE_PLIST="$ROOT/ops/launchd/$LABEL.plist"
TARGET_PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

mkdir -p "$HOME/Library/LaunchAgents" "$ROOT/logs"
cp "$SOURCE_PLIST" "$TARGET_PLIST"
chmod 644 "$TARGET_PLIST"
chmod +x "$ROOT/scripts/run_tistory_hourly_automation.sh"

launchctl bootout "gui/$(id -u)" "$TARGET_PLIST" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$TARGET_PLIST"
launchctl enable "gui/$(id -u)/$LABEL"

echo "Installed $LABEL"
echo "Schedule: 00, 01, 02, 07-23 KST/macOS local time, minute 00"
echo "Run log: $ROOT/logs/tistory-hourly-run.log"
