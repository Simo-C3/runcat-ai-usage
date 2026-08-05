#!/bin/sh
set -eu

LABEL="dev.runcat.ai-usage"
APP_NAME="RunCat AI Usage Monitor"
SUPPORT_ROOT="$HOME/Library/Application Support/RunCat AI Usage"
APP="$SUPPORT_ROOT/$APP_NAME.app"
LAUNCH_AGENT="$HOME/Library/LaunchAgents/$LABEL.plist"
DOMAIN="gui/$(id -u)"

launchctl bootout "$DOMAIN" "$LAUNCH_AGENT" >/dev/null 2>&1 || true
rm -f "$LAUNCH_AGENT"
rm -rf "$APP"

if [ "${1:-}" = "--purge" ]; then
    rm -rf "$SUPPORT_ROOT/state"
    rm -rf "$HOME/Library/Logs/RunCat AI Usage"
    OUTPUT_DIR="${RUNCAT_AI_USAGE_OUTPUT_DIR:-$HOME/RunCatMetrics}"
    rm -f \
        "$OUTPUT_DIR/claude-code.json" \
        "$OUTPUT_DIR/codex.json" \
        "$OUTPUT_DIR/github-copilot.json"
fi

echo "Uninstalled $APP_NAME."
if [ "${1:-}" != "--purge" ]; then
    echo "Usage history and JSON snapshots were kept. Use --purge to remove them."
fi
