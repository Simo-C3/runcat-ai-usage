#!/bin/sh
set -eu

LABEL="dev.runcat.ai-usage"
APP_NAME="RunCat AI Usage Monitor"
SUPPORT_ROOT="$HOME/Library/Application Support/RunCat AI Usage"
APP="$SUPPORT_ROOT/$APP_NAME.app"
LAUNCH_AGENT="$HOME/Library/LaunchAgents/$LABEL.plist"
DOMAIN="gui/$(id -u)"

for JOB in "$LABEL" "$LABEL.collector" "$LABEL.receiver"; do
    launchctl bootout "$DOMAIN/$JOB" >/dev/null 2>&1 || true
    rm -f "$HOME/Library/LaunchAgents/$JOB.plist"
done
rm -f "$SUPPORT_ROOT/bin/otelcol-contrib"
rm -rf "$APP"

if [ "${1:-}" = "--purge" ]; then
    rm -rf "$SUPPORT_ROOT/state" "$SUPPORT_ROOT/otel"
    rm -rf "$HOME/Library/Logs/RunCat AI Usage"
    OUTPUT_DIR="${RUNCAT_AI_USAGE_OUTPUT_DIR:-$HOME/RunCatMetrics}"
    rm -f \
        "$OUTPUT_DIR/claude-code.json" \
        "$OUTPUT_DIR/codex.json" \
        "$OUTPUT_DIR/github-copilot.json"
fi

echo "Uninstalled $APP_NAME."
echo "Native agent OTel settings and ~/.local/bin/runcat-copilot were kept."
echo "Restore agent settings from their .runcat-backup-* files (preserve any later edits),"
echo "remove the runcat-copilot launcher if no longer needed, and restart the agents."
if [ "${1:-}" != "--purge" ]; then
    echo "Usage history and JSON snapshots were kept. Use --purge to remove them."
fi
