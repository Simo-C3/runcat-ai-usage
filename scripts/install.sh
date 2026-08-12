#!/bin/sh
set -eu

LABEL="dev.runcat.ai-usage"
APP_NAME="RunCat AI Usage Monitor"
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
SUPPORT_ROOT="$HOME/Library/Application Support/RunCat AI Usage"
APP="$SUPPORT_ROOT/$APP_NAME.app"
STAGING_APP="$SUPPORT_ROOT/.$APP_NAME.installing.app"
CONTENTS="$STAGING_APP/Contents"
EXECUTABLE="$CONTENTS/MacOS/$APP_NAME"
RESOURCES="$CONTENTS/Resources"
STATE_DIR="$SUPPORT_ROOT/state"
LOG_DIR="$HOME/Library/Logs/RunCat AI Usage"
OUTPUT_DIR="${RUNCAT_AI_USAGE_OUTPUT_DIR:-$HOME/RunCatMetrics}"
PYTHON_BIN="${RUNCAT_AI_USAGE_PYTHON:-/usr/bin/python3}"
LAUNCH_AGENT="$HOME/Library/LaunchAgents/$LABEL.plist"
DOMAIN="gui/$(id -u)"
OPEN_OUTPUT=true

if [ "$#" -gt 1 ]; then
    echo "Usage: $0 [--no-open]" >&2
    exit 2
fi
if [ "${1:-}" = "--no-open" ]; then
    OPEN_OUTPUT=false
elif [ "$#" -eq 1 ]; then
    echo "Usage: $0 [--no-open]" >&2
    exit 2
fi

if [ "$(uname -s)" != "Darwin" ]; then
    echo "runcat-ai-usage supports macOS only." >&2
    exit 1
fi
if [ ! -x "$PYTHON_BIN" ]; then
    echo "$PYTHON_BIN is required." >&2
    exit 1
fi
PACKAGE_VERSION=$(
    PYTHONPATH="$ROOT/src" "$PYTHON_BIN" -c \
        "from runcat_ai_usage import __version__; print(__version__)"
)

mkdir -p "$SUPPORT_ROOT" "$LOG_DIR" "$OUTPUT_DIR" "$HOME/Library/LaunchAgents"
rm -rf "$STAGING_APP"
mkdir -p "$CONTENTS/MacOS" "$RESOURCES"
cp "$ROOT"/src/*.py "$RESOURCES/"
cp -R "$ROOT/src/providers" "$RESOURCES/"
find "$RESOURCES" -type d -name __pycache__ -prune -exec rm -rf {} \;

cat >"$EXECUTABLE" <<EOF
#!/bin/sh
set -eu
RESOURCES=\$(CDPATH= cd -- "\$(dirname -- "\$0")/../Resources" && pwd)
export PYTHONPATH="\$RESOURCES"
export PYTHONDONTWRITEBYTECODE=1
exec "$PYTHON_BIN" -m runcat_ai_usage "\$@"
EOF
chmod 755 "$EXECUTABLE"

"$PYTHON_BIN" - \
    "$CONTENTS/Info.plist" \
    "$LAUNCH_AGENT" \
    "$APP/Contents/MacOS/$APP_NAME" \
    "$LOG_DIR" \
    "$OUTPUT_DIR" \
    "$PACKAGE_VERSION" <<'PY'
import plistlib
import sys
from pathlib import Path

info_path, agent_path, executable, log_directory, output_directory = map(
    Path, sys.argv[1:6]
)
version = sys.argv[6]
info = {
    "CFBundleDisplayName": "RunCat AI Usage Monitor",
    "CFBundleExecutable": "RunCat AI Usage Monitor",
    "CFBundleIdentifier": "dev.runcat.ai-usage",
    "CFBundleInfoDictionaryVersion": "6.0",
    "CFBundleName": "RunCat AI Usage Monitor",
    "CFBundlePackageType": "APPL",
    "CFBundleShortVersionString": version,
    "CFBundleVersion": version,
    "LSMinimumSystemVersion": "13.0",
    "LSUIElement": True,
}
agent = {
    "Label": "dev.runcat.ai-usage",
    "AssociatedBundleIdentifiers": ["dev.runcat.ai-usage"],
    "Program": str(executable),
    "ProgramArguments": [str(executable)],
    "RunAtLoad": True,
    "StartInterval": 60,
    "ProcessType": "Background",
    "StandardOutPath": str(log_directory / "monitor.log"),
    "StandardErrorPath": str(log_directory / "monitor.error.log"),
    "EnvironmentVariables": {
        "RUNCAT_AI_USAGE_OUTPUT_DIR": str(output_directory),
    },
}
with info_path.open("wb") as output:
    plistlib.dump(info, output)
with agent_path.open("wb") as output:
    plistlib.dump(agent, output)
PY

rm -rf "$APP"
mv "$STAGING_APP" "$APP"
/usr/bin/codesign --force --deep --sign - "$APP" >/dev/null 2>&1

OLD_LABEL="dev.runcat.metrics-monitor"
OLD_AGENT="$HOME/Library/LaunchAgents/$OLD_LABEL.plist"
if [ -f "$OLD_AGENT" ]; then
    launchctl bootout "$DOMAIN" "$OLD_AGENT" >/dev/null 2>&1 || true
    rm -f "$OLD_AGENT"
fi
OLD_APP="$HOME/Library/Application Support/RunCat Metrics/RunCat Metrics Monitor.app"
if [ -d "$OLD_APP" ]; then
    rm -rf "$OLD_APP"
fi
OLD_HISTORY="$HOME/.copilot/runcat-usage-history.db"
if [ ! -f "$STATE_DIR/history.db" ] && [ -f "$OLD_HISTORY" ]; then
    mkdir -p "$STATE_DIR"
    cp "$OLD_HISTORY" "$STATE_DIR/history.db"
fi
"$PYTHON_BIN" - "$STATE_DIR/cache" "$HOME" <<'PY'
import json
import shutil
import sys
from pathlib import Path

cache_directory = Path(sys.argv[1])
home = Path(sys.argv[2])
cache_directory.mkdir(parents=True, exist_ok=True)
sources = {
    "claude-code.json": home / ".claude" / "runcat-plan-cache.json",
    "codex.json": home / ".codex" / "runcat-plan-cache.json",
    "github-copilot.json": home / ".copilot" / "runcat-plan-cache.json",
}
for filename, source in sources.items():
    destination = cache_directory / filename
    try:
        current = json.loads(destination.read_text(encoding="utf-8"))
        if isinstance(current.get("usage"), dict):
            continue
    except (OSError, json.JSONDecodeError, TypeError):
        pass
    if source.is_file():
        shutil.copy2(source, destination)
PY

launchctl bootout "$DOMAIN" "$LAUNCH_AGENT" >/dev/null 2>&1 || true
"$APP/Contents/MacOS/$APP_NAME"
launchctl bootstrap "$DOMAIN" "$LAUNCH_AGENT"
launchctl enable "$DOMAIN/$LABEL"
launchctl kickstart -k "$DOMAIN/$LABEL"

echo
echo "Installed $APP_NAME."
echo "Metrics: $OUTPUT_DIR"
echo "RunCat Neo: Settings > Metrics > Custom Metrics > Add Custom Metrics Source"
echo "Add claude-code.json, codex.json, and github-copilot.json."
if [ "$OPEN_OUTPUT" = true ]; then
    /usr/bin/open "$OUTPUT_DIR"
fi
