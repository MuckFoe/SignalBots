#!/bin/bash
# Daily Ollama update (runs as moritz from /Library/LaunchDaemons/local.ollama-update.plist).
# Installs the latest official release into ~/ollama/versions/<tag>, points ~/ollama/current at it,
# restarts the service (launchd KeepAlive brings it back) and rolls back unless the new version
# answers a structured-output request. Usage: update.sh [--force-check]
set -u
ROOT=/Users/moritz/ollama
API=http://localhost:11434
MODEL=qwen3.6:35b
TEAM=3MU9H2V9Y9   # Ollama's Apple developer team id
log() { echo "$(date '+%F %T') $*"; }

current_tag=$(basename "$(readlink "$ROOT/current")")
latest_tag=$(curl -fsS -m 30 https://api.github.com/repos/ollama/ollama/releases/latest \
  | sed -n 's/^  "tag_name": "\(.*\)",$/\1/p')
if [ -z "$latest_tag" ]; then log "could not read latest release"; exit 1; fi
if [ "$latest_tag" = "$current_tag" ]; then log "up to date ($current_tag)"; exit 0; fi
log "updating $current_tag -> $latest_tag"

new="$ROOT/versions/$latest_tag"
tmp="$new.tmp"
rm -rf "$tmp" && mkdir -p "$tmp"
if ! curl -fsSL -m 900 -o "$tmp/ollama-darwin.tgz" \
     "https://github.com/ollama/ollama/releases/download/$latest_tag/ollama-darwin.tgz"; then
  log "download failed"; rm -rf "$tmp"; exit 1
fi
tar xzf "$tmp/ollama-darwin.tgz" -C "$tmp" && rm "$tmp/ollama-darwin.tgz"
if ! codesign -dv "$tmp/ollama" 2>&1 | grep -q "TeamIdentifier=$TEAM"; then
  log "signature check failed, not installing"; rm -rf "$tmp"; exit 1
fi
if ! ls "$tmp"/mlx_metal_*/libollama_xgrammar.dylib >/dev/null 2>&1; then
  log "release has no xgrammar library (no structured output on MLX), not installing"; rm -rf "$tmp"; exit 1
fi
rm -rf "$new" && mv "$tmp" "$new"

restart() {  # kill serve + runners; launchd restarts serve; wait until it reports version $1
  pkill -f "^$ROOT/(current|versions/[^/]+)/ollama "
  for _ in $(seq 1 60); do
    sleep 2
    v=$(curl -fsS -m 2 "$API/api/version" 2>/dev/null | sed -n 's/.*"version":"\([^"]*\)".*/\1/p')
    [ "v$v" = "$1" ] && return 0
  done
  return 1
}

smoke_test() {  # strict json_schema request must succeed and match the enum
  curl -fsS -m 300 "$API/v1/chat/completions" -d '{"model":"'"$MODEL"'","temperature":0,"reasoning_effort":"none",
    "messages":[{"role":"user","content":"Is the sky blue? Answer as JSON."}],
    "response_format":{"type":"json_schema","json_schema":{"name":"t","strict":true,"schema":{"type":"object",
    "properties":{"answer":{"type":"string","enum":["yes","no"]}},"required":["answer"],"additionalProperties":false}}}}' \
    | grep -Eq '\\"answer\\"[^"]*\\"(yes|no)\\"'
}

ln -sfn "versions/$latest_tag" "$ROOT/current"
if restart "$latest_tag" && smoke_test; then
  log "now running $latest_tag, structured output OK"
  # keep the new and the previous version
  ls -1t "$ROOT/versions" | grep -v -e "^$latest_tag\$" -e "^$current_tag\$" -e '\.tmp$' \
    | while read -r old; do rm -rf "$ROOT/versions/$old"; log "removed $old"; done
else
  log "$latest_tag failed start or structured-output check, rolling back to $current_tag"
  ln -sfn "versions/$current_tag" "$ROOT/current"
  restart "$current_tag" && log "rolled back to $current_tag" || log "ROLLBACK DID NOT COME UP, check the service"
  rm -rf "$new"
  exit 1
fi
