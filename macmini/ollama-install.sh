#!/bin/sh
# One-time, run with sudo: point the Ollama service at ~/ollama/current (official build) and
# install the daily updater. Rolls back to the Homebrew config if the new service does not come up.
set -e
[ "$(id -u)" = 0 ] || { echo "run with sudo"; exit 1; }
P=/Library/LaunchDaemons/local.ollama.plist
U=/Library/LaunchDaemons/local.ollama-update.plist
NEW=/Users/moritz/ollama/current/ollama

[ -f "$P.homebrew-backup" ] || cp -p "$P" "$P.homebrew-backup"
/usr/libexec/PlistBuddy -c "Set :ProgramArguments:0 $NEW" "$P"
launchctl bootout system/local.ollama 2>/dev/null || true
sleep 2
launchctl bootstrap system "$P"
ok=0
for _ in $(seq 1 15); do
  sleep 1
  if curl -s -m 2 localhost:11434/api/version >/dev/null && ps -axo command | grep -q "^$NEW serve"; then ok=1; break; fi
done
if [ "$ok" != 1 ]; then
  echo "FAILED: new service did not come up, restoring Homebrew config"
  cp -p "$P.homebrew-backup" "$P"
  launchctl bootout system/local.ollama 2>/dev/null || true; sleep 2
  launchctl bootstrap system "$P"
  exit 1
fi
echo "OK: service runs $NEW ($(curl -s localhost:11434/api/version))"

cat > "$U" <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>Label</key>
	<string>local.ollama-update</string>
	<key>ProgramArguments</key>
	<array>
		<string>/bin/bash</string>
		<string>/Users/moritz/ollama/update.sh</string>
	</array>
	<key>UserName</key>
	<string>moritz</string>
	<key>StartCalendarInterval</key>
	<dict>
		<key>Hour</key>
		<integer>4</integer>
		<key>Minute</key>
		<integer>30</integer>
	</dict>
	<key>StandardOutPath</key>
	<string>/Users/moritz/Library/Logs/ollama-update.log</string>
	<key>StandardErrorPath</key>
	<string>/Users/moritz/Library/Logs/ollama-update.log</string>
</dict>
</plist>
EOF
chown root:wheel "$U"; chmod 644 "$U"
launchctl bootout system/local.ollama-update 2>/dev/null || true
launchctl bootstrap system "$U"
echo "OK: daily update at 04:30 installed (log: ~/Library/Logs/ollama-update.log)"
