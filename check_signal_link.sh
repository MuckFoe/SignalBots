#!/bin/sh
# Runs on the remote host via cron (installed by install_signal_link_monitor.py).
# Logs only on state change (OK <-> BROKEN), so the log is a timeline of
# link-loss events instead of a line every 15 minutes.
set -eu

STATE_FILE=/home/signalbot/bots/.signal_link_state
LOG_FILE=/home/signalbot/bots/signal_link_status.log

ACCOUNTS=$(curl -s http://127.0.0.1:8080/v1/accounts || echo "CURL_FAILED")
if [ "$ACCOUNTS" = "[]" ] || [ "$ACCOUNTS" = "CURL_FAILED" ]; then
    NEW_STATE=BROKEN
else
    NEW_STATE=OK
fi

OLD_STATE=""
[ -f "$STATE_FILE" ] && OLD_STATE=$(cat "$STATE_FILE")

if [ "$NEW_STATE" != "$OLD_STATE" ]; then
    echo "$(date -Iseconds) $NEW_STATE accounts=$ACCOUNTS" >> "$LOG_FILE"
    echo "$NEW_STATE" > "$STATE_FILE"
fi
