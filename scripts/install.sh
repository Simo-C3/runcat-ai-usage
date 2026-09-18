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
STATE_DIR="${RUNCAT_AI_USAGE_STATE_DIR:-}"
COLLECTOR_BIN="${RUNCAT_AI_USAGE_COLLECTOR:-$SUPPORT_ROOT/bin/otelcol-contrib}"
COLLECTOR_CONFIG="$SUPPORT_ROOT/otel/collector.yaml"
LOG_DIR="$HOME/Library/Logs/RunCat AI Usage"
OUTPUT_DIR="${RUNCAT_AI_USAGE_OUTPUT_DIR:-}"
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

if [ -z "$OUTPUT_DIR" ]; then
    OUTPUT_DIR=$("$PYTHON_BIN" - "$LAUNCH_AGENT" "$HOME/RunCatMetrics" <<'PYTHON'
import plistlib
from xml.parsers.expat import ExpatError
import sys
try:
    with open(sys.argv[1], "rb") as source:
        value = plistlib.load(source)["EnvironmentVariables"]["RUNCAT_AI_USAGE_OUTPUT_DIR"]
    print(value)
except (OSError, ValueError, KeyError, TypeError, AttributeError, ExpatError):
    print(sys.argv[2])
PYTHON
    )
fi
if [ -z "$STATE_DIR" ]; then
    STATE_DIR=$("$PYTHON_BIN" - "$LAUNCH_AGENT" "$SUPPORT_ROOT/state" <<'PYTHON'
import plistlib
from xml.parsers.expat import ExpatError
import sys
try:
    with open(sys.argv[1], "rb") as source:
        value = plistlib.load(source)["EnvironmentVariables"]["RUNCAT_AI_USAGE_STATE_DIR"]
    print(value)
except (OSError, ValueError, KeyError, TypeError, AttributeError, ExpatError):
    print(sys.argv[2])
PYTHON
    )
fi
if [ -z "${RUNCAT_AI_USAGE_COLLECTOR:-}" ]; then
    sh "$ROOT/scripts/install-collector.sh" "$COLLECTOR_BIN"
fi
[ -x "$COLLECTOR_BIN" ] || { echo "Collector executable not found: $COLLECTOR_BIN" >&2; exit 1; }
mkdir -p "$SUPPORT_ROOT/otel" "$STATE_DIR" "$LOG_DIR" "$OUTPUT_DIR" "$HOME/Library/LaunchAgents"
cp "$ROOT/otel/collector.yaml" "$SUPPORT_ROOT/otel/collector.example.yaml"
cp "$ROOT/otel/remote.example.yaml" "$SUPPORT_ROOT/otel/remote.example.yaml"
cp -R "$ROOT/otel/agents" "$SUPPORT_ROOT/otel/"
if [ ! -f "$COLLECTOR_CONFIG" ]; then
    cp "$ROOT/otel/collector.yaml" "$COLLECTOR_CONFIG"
fi
"$PYTHON_BIN" - "$COLLECTOR_BIN" "$COLLECTOR_CONFIG" "$STATE_DIR" "$HOME/Library/LaunchAgents/$LABEL.collector.plist" <<'PYTHON'
import os
import plistlib
from xml.parsers.expat import ExpatError
import subprocess
import sys

environment = {}
try:
    with open(sys.argv[4], "rb") as source:
        environment.update(plistlib.load(source).get("EnvironmentVariables", {}))
except (OSError, ValueError, TypeError, AttributeError, ExpatError):
    pass
environment.update(os.environ)
environment["RUNCAT_AI_USAGE_STATE_DIR"] = sys.argv[3]
subprocess.run([sys.argv[1], "validate", "--config", sys.argv[2]], env=environment, check=True)
PYTHON

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
    "$PACKAGE_VERSION" "$COLLECTOR_BIN" "$COLLECTOR_CONFIG" "$STATE_DIR" <<'PY'
import plistlib
from xml.parsers.expat import ExpatError
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
    "ProgramArguments": [str(executable), "collect"],
    "RunAtLoad": True,
    "StartInterval": 60,
    "ProcessType": "Background",
    "StandardOutPath": str(log_directory / "monitor.log"),
    "StandardErrorPath": str(log_directory / "monitor.error.log"),
    "EnvironmentVariables": {
        "RUNCAT_AI_USAGE_OUTPUT_DIR": str(output_directory),
        "RUNCAT_AI_USAGE_STATE_DIR": sys.argv[9],
        "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT": "http://127.0.0.1:4318/v1/metrics",
    },
}
with info_path.open("wb") as output:
    plistlib.dump(info, output)
with agent_path.open("wb") as output:
    plistlib.dump(agent, output)
for suffix, program, args in (
    ("receiver", str(executable), [str(executable), "serve"]),
    ("collector", sys.argv[7], [sys.argv[7], "--config", sys.argv[8]]),
):
    worker = dict(agent)
    worker["Label"] = agent["Label"] + "." + suffix
    worker["Program"] = program
    worker["ProgramArguments"] = args
    worker.pop("StartInterval")
    worker["KeepAlive"] = True
    worker["EnvironmentVariables"] = dict(agent["EnvironmentVariables"])
    worker["EnvironmentVariables"].pop("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT", None)
    worker["StandardOutPath"] = str(log_directory / (suffix + ".log"))
    worker["StandardErrorPath"] = str(log_directory / (suffix + ".error.log"))
    # Operators can supply remote-export credentials here without embedding them in YAML.
    worker_path = agent_path.with_name(worker["Label"] + ".plist")
    if suffix == "collector" and worker_path.exists():
        try:
            with worker_path.open("rb") as source:
                old_environment = plistlib.load(source).get("EnvironmentVariables", {})
            worker["EnvironmentVariables"] = dict(old_environment, **worker["EnvironmentVariables"])
        except (OSError, ValueError, TypeError, AttributeError, ExpatError):
            pass
    with worker_path.open("wb") as output:
        plistlib.dump(worker, output)
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

for JOB in "$LABEL" "$LABEL.collector" "$LABEL.receiver"; do
    launchctl bootout "$DOMAIN/$JOB" >/dev/null 2>&1 || true
done
for JOB in "$LABEL.receiver" "$LABEL.collector" "$LABEL"; do
    launchctl enable "$DOMAIN/$JOB"
    launchctl bootstrap "$DOMAIN" "$HOME/Library/LaunchAgents/$JOB.plist"
    launchctl kickstart "$DOMAIN/$JOB"
done

echo
echo "Installed $APP_NAME."
echo "Metrics: $OUTPUT_DIR"
echo "Collector config: $COLLECTOR_CONFIG"
echo "Native agent telemetry is opt-in. Configure with:"
echo "  runcat-ai-usage agents setup all --dry-run"
echo "  runcat-ai-usage agents setup all"
echo "Source installs: use \"$APP/Contents/MacOS/$APP_NAME\" agents setup all"
echo "Agent settings templates: $SUPPORT_ROOT/otel/agents"
echo "Allow 1-2 minutes for the first OTLP update."
echo "RunCat Neo: Settings > Metrics > Custom Metrics > Add Custom Metrics Source"
echo "Add claude-code.json, codex.json, and github-copilot.json."
if [ "$OPEN_OUTPUT" = true ]; then
    /usr/bin/open "$OUTPUT_DIR"
fi
