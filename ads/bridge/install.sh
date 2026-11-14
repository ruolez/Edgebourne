#!/usr/bin/env bash
# ads-desk: connect this Mac to the Ads console Desk.
#
#   bash ~/Desktop/Dev/edgebourne/ads/bridge/install.sh          install or update
#   bash ~/Desktop/Dev/edgebourne/ads/bridge/install.sh remove   stop and remove
#
# Installs the /ads-desk skill and the desk helper into ~/.claude/skills/ads-desk,
# keeps the Mac key in the login Keychain (never in a file), and starts the
# bridge as a LaunchAgent that runs while you're logged in.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$HOME/.claude/skills/ads-desk"
CONF_DIR="$HOME/.config/ads-desk"
LABEL="com.edgebourne.ads-desk"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG_DIR="$HOME/Library/Logs/ads-desk"
SERVICE="ads-desk"
DEFAULT_URL="https://ads.edgebourne.com"
DEFAULT_WORKDIR="$HOME/Desktop/Dev/meta-ads"

ok()   { printf '\033[0;32m[ok]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[warn]\033[0m %s\n' "$*"; }
die()  { printf '\033[0;31m[error]\033[0m %s\n' "$*" >&2; exit 1; }

stop_agent() { launchctl bootout "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || true; }

if [ "${1:-}" = "remove" ]; then
  stop_agent
  rm -f "$PLIST"
  url="$(python3 -c "import json;print(json.load(open('$CONF_DIR/config.json'))['base_url'])" 2>/dev/null || echo "$DEFAULT_URL")"
  security delete-generic-password -s "$SERVICE" -a "$url" >/dev/null 2>&1 || true
  security delete-generic-password -s "ads-desk-claude" >/dev/null 2>&1 || true
  security delete-generic-password -s "ads-manager-link" -a "$url" >/dev/null 2>&1 || true
  rm -rf "$SKILL_DIR" "$CONF_DIR"
  ok "Removed. Also click \"Disconnect the Mac\" on the Desk page so the old key stops working."
  exit 0
fi

[ "$(uname)" = "Darwin" ] || die "This is for macOS."
PY="$(command -v python3 || true)"; [ -n "$PY" ] || die "python3 not found."
CLAUDE="$(command -v claude || true)"
[ -n "$CLAUDE" ] || [ ! -x "$HOME/.local/bin/claude" ] || CLAUDE="$HOME/.local/bin/claude"
[ -n "$CLAUDE" ] || die "Claude Code (claude) not found."

read -r -p "Dashboard address [$DEFAULT_URL]: " URL; URL="${URL:-$DEFAULT_URL}"; URL="${URL%/}"
read -r -p "meta-ads workspace folder [$DEFAULT_WORKDIR]: " WORKDIR; WORKDIR="${WORKDIR:-$DEFAULT_WORKDIR}"
[ -d "$WORKDIR" ] || die "No folder at $WORKDIR"

existing=""
security find-generic-password -s "$SERVICE" -a "$URL" -w >/dev/null 2>&1 && existing=1
if [ -n "$existing" ]; then
  read -r -p "A Mac key is already saved. Replace it? (y/N): " yn
  [[ "$yn" =~ ^[Yy] ]] && existing=""
fi
if [ -z "$existing" ]; then
  read -r -s -p "Paste the Mac key from the Desk page (hidden): " KEY; echo
  [[ "$KEY" == ebdesk_* ]] || die "That doesn't look like a Mac key (it starts with ebdesk_)."
  status="$(KEY="$KEY" URL="$URL" "$PY" - <<'PYEOF'
import os, urllib.request, urllib.error
req = urllib.request.Request(os.environ["URL"] + "/api/agent/queue", headers={"Authorization": "Bearer " + os.environ["KEY"], "User-Agent": "ads-desk-install"})
try:
    print(urllib.request.urlopen(req, timeout=20).status)
except urllib.error.HTTPError as e:
    print(e.code)
except Exception as e:
    print("unreachable")
PYEOF
)"
  case "$status" in
    200) ok "The dashboard accepted the key." ;;
    401) die "The dashboard rejected that key. Create a new one on the Desk page and try again." ;;
    *)   die "Couldn't reach $URL ($status)." ;;
  esac
  security add-generic-password -U -s "$SERVICE" -a "$URL" -l "Ads console Desk key" -w "$KEY"
  unset KEY
  ok "Key saved in your login Keychain."
fi

# Unattended runs need a sign-in that doesn't expire: `claude setup-token` makes one.
if security find-generic-password -s "ads-desk-claude" -w >/dev/null 2>&1; then
  ok "Claude token for unattended runs already saved."
else
  echo
  echo "Recommended: a long-lived Claude Code token so Desk runs keep working when your"
  echo "normal sign-in expires. In another Terminal window run:  claude setup-token"
  read -r -s -p "Paste the token here (hidden), or press Enter to skip: " CTOKEN; echo
  if [ -n "$CTOKEN" ]; then
    security add-generic-password -U -s "ads-desk-claude" -a "claude" -l "Ads console Desk: Claude Code token" -w "$CTOKEN"
    unset CTOKEN
    ok "Claude token saved in your login Keychain."
  else
    warn "Skipped. Desk runs use your normal Claude sign-in until it expires; run this installer again to add the token."
  fi
fi

mkdir -p "$SKILL_DIR" "$CONF_DIR" "$LOG_DIR" "$HOME/Library/LaunchAgents"
cp "$HERE/desk" "$HERE/bridge.py" "$HERE/amlink.py" "$SKILL_DIR/"
cp "$HERE/skill/SKILL.md" "$SKILL_DIR/SKILL.md"
chmod 755 "$SKILL_DIR/desk"
sed -i '' "1s|.*|#!$PY|" "$SKILL_DIR/desk"
cat > "$CONF_DIR/config.json" <<JSON
{"base_url": "$URL", "workdir": "$WORKDIR", "claude": "$CLAUDE", "python": "$PY"}
JSON
ok "Skill /ads-desk and the desk helper installed in $SKILL_DIR"

stop_agent
cat > "$PLIST" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array><string>$PY</string><string>$SKILL_DIR/bridge.py</string></array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>30</integer>
  <key>ProcessType</key><string>Background</string>
  <key>StandardOutPath</key><string>$LOG_DIR/bridge.log</string>
  <key>StandardErrorPath</key><string>$LOG_DIR/bridge.log</string>
</dict>
</plist>
PLISTEOF
launchctl bootstrap "gui/$(id -u)" "$PLIST"
sleep 3
if launchctl print "gui/$(id -u)/$LABEL" 2>/dev/null | grep -q "state = running"; then
  ok "Bridge running. The Desk page should say \"Mac connected\" within a few seconds."
else
  warn "The bridge didn't start. Log: $LOG_DIR/bridge.log"
fi
echo "   Logs: $LOG_DIR   ·   Remove: bash $HERE/install.sh remove"
