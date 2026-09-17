"""Read-only checks for the installed, once-per-minute monitor."""

import os
import plistlib
import re
import shlex
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Sequence
from xml.parsers.expat import ExpatError

from services import Service
from storage import read_object


LABEL = "dev.runcat.ai-usage"
MAX_AGE_SECONDS = 180


def report(ok: bool, title: str, detail: str) -> int:
    print("{} {:<22} {}".format("OK  " if ok else "FAIL", title, detail))
    return 0 if ok else 1


def launchctl(*arguments: str) -> str:
    result = subprocess.run(
        ["/bin/launchctl", *arguments],
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    )
    return result.stdout


def background_diagnostics(
    home: Path,
    catalog: Sequence[Service],
    output_directory: Optional[Path] = None,
) -> int:
    failures = 0
    installation_failed = False
    agent_path = home / "Library/LaunchAgents" / (LABEL + ".plist")
    agent = {}
    try:
        with agent_path.open("rb") as source:
            agent = plistlib.load(source)
        if not isinstance(agent, dict):
            raise ValueError("expected a LaunchAgent dictionary")
        if agent.get("Label") != LABEL or agent.get("StartInterval") != 60:
            raise ValueError("expected the monitor label and a 60-second interval")
        if agent.get("RunAtLoad") is not True:
            raise ValueError("RunAtLoad is not enabled")
        program = agent.get("Program")
        if not isinstance(program, str) or not program:
            raise ValueError("monitor executable is not configured")
        executable = Path(program)
        if not executable.is_file() or not os.access(executable, os.X_OK):
            raise ValueError("monitor executable is missing or not executable")
        failures += report(True, "Monitor installation", "installed; interval 60s")
    except (OSError, ValueError, plistlib.InvalidFileException, ExpatError) as error:
        installation_failed = True
        failures += report(False, "Monitor installation", str(error))

    domain = "gui/{}".format(os.getuid())
    target = domain + "/" + LABEL
    try:
        disabled = launchctl("print-disabled", domain)
        is_disabled = re.search(
            r'"' + re.escape(LABEL) + r'"\s*=>\s*(?:disabled|true)\b', disabled
        ) is not None
        failures += report(
            not is_disabled, "Monitor enabled",
            "disabled in launchd" if is_disabled else "enabled",
        )
        installation_failed = installation_failed or is_disabled
    except (OSError, subprocess.SubprocessError):
        failures += report(False, "Monitor enabled", "could not query launchd")

    try:
        status = launchctl("print", target)
    except (OSError, subprocess.SubprocessError):
        installation_failed = True
        failures += report(
            False, "Monitor registration", "not loaded or launchd is inaccessible"
        )
    else:
        failures += report(True, "Monitor registration", "loaded")
        runs = re.search(r"^\s*runs = (\d+)\s*$", status, re.MULTILINE)
        exit_code = re.search(r"^\s*last exit code = (\d+)\s*$", status, re.MULTILINE)
        interval = re.search(r"^\s*run interval = (\d+) seconds\s*$", status, re.MULTILINE)
        scheduled = interval is not None and int(interval.group(1)) == 60
        failures += report(
            scheduled, "Monitor schedule",
            "every 60s" if scheduled else "60-second schedule is not loaded",
        )
        installation_failed = installation_failed or not scheduled
        succeeded = (
            runs is not None and int(runs.group(1)) > 0
            and exit_code is not None and int(exit_code.group(1)) == 0
        )
        failures += report(
            succeeded, "Monitor last run",
            "exit 0; waiting between runs is normal" if succeeded
            else "no successful last exit; check the monitor error log",
        )

    # Use the installed destination unless the caller explicitly overrides it.
    environment = agent.get("EnvironmentVariables", {}) if isinstance(agent, dict) else {}
    configured_output = (
        environment.get("RUNCAT_AI_USAGE_OUTPUT_DIR")
        if isinstance(environment, dict) else None
    )
    if output_directory is None:
        output_directory = (
            Path(configured_output).expanduser()
            if isinstance(configured_output, str) and configured_output
            else home / "RunCatMetrics"
        )
    print("Metrics directory: {}".format(output_directory))
    now = time.time()
    for service in catalog:
        path = output_directory / service.filename
        try:
            age = now - path.stat().st_mtime
            recent = -60 <= age <= MAX_AGE_SECONDS
            failures += report(
                recent, service.title + " JSON", "written {:.0f}s ago".format(age)
            )
        except OSError:
            failures += report(False, service.title + " JSON", "missing or unreadable")
        try:
            value = read_object(path) or {}
            timestamp = value.get("lastUpdatedDate")
            if not isinstance(timestamp, str):
                raise ValueError("missing lastUpdatedDate")
            fetched = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            if fetched.tzinfo is None:
                raise ValueError("lastUpdatedDate has no timezone")
            age = now - fetched.timestamp()
            recent = (
                -60 <= age <= MAX_AGE_SECONDS
                and isinstance(value.get("metrics"), list)
                and isinstance(value.get("metricsBarValue"), str)
                and value["metricsBarValue"] not in ("", "N/A")
            )
            failures += report(
                recent, service.title + " data",
                "last successful fetch {:.0f}s ago".format(age)
                if recent else "unavailable or stale usage data",
            )
        except (ValueError, OverflowError, OSError):
            failures += report(
                False, service.title + " data", "missing or invalid snapshot timestamp"
            )

    if failures:
        print("\nRecovery:")
        if not installation_failed:
            print("  Retry the background update:")
            print("    launchctl kickstart -k {}".format(shlex.quote(target)))
            print("  If restarting does not help, rerun setup:")
        print("  Reinstall/start the monitor (Homebrew):")
        print(
            "    RUNCAT_AI_USAGE_OUTPUT_DIR={} runcat-ai-usage-install --no-open"
            .format(shlex.quote(str(output_directory)))
        )
        print("  Manual installation: run from the source checkout:")
        print(
            "    RUNCAT_AI_USAGE_OUTPUT_DIR={} ./scripts/install.sh --no-open"
            .format(shlex.quote(str(output_directory)))
        )
        log_path = home / "Library/Logs/RunCat AI Usage/monitor.error.log"
        print("  Inspect errors: tail -n 50 {}".format(shlex.quote(str(log_path))))
        print(
            "  If macOS disabled the monitor, allow RunCat AI Usage Monitor in "
            "System Settings > General > Login Items."
        )
        print("  After recovery, wait 1-2 minutes and run --doctor again.")
    return failures
