import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional, Sequence, Tuple

from cache import CacheResult, FETCH_ERRORS, cached_usage
from config import (
    DEFAULT_DISPLAY_CONFIG,
    LANGUAGES,
    METRIC_ROWS,
    RATE_FORMATS,
    TREND_PERIOD_PRESETS,
    DisplayConfig,
    load_display_config,
    save_display_config,
    trend_period_seconds,
)
from diagnostics import background_diagnostics
from output import rate_value
from otlp import export_metrics, quota_resource
from receiver import serve
from runcat_ai_usage import __version__
from services import services
import agent_setup


def run_once(home: Path, state_directory: Path, refresh_seconds: int, endpoint=None) -> int:
    """Collect plan quotas and send them through the Collector; never write snapshots."""
    now = time.time()
    resources = []
    for service in services(home):
        try:
            state_key = service.state_key()
            result = cached_usage(
                state_directory / "cache" / "{}.json".format(state_key),
                service.fetcher, refresh_seconds, now,
            )
        except FETCH_ERRORS as error:
            state_key = service.key
            result = CacheResult(None, None, error)
        if result.error is not None:
            print("[{}] {}".format(service.title, result.error), file=sys.stderr)
        resources.append(quota_resource(service, state_key, result, now))
    try:
        export_metrics({"resourceMetrics": resources}, endpoint)
    except FETCH_ERRORS as error:
        print("OTLP export failed: {}".format(type(error).__name__), file=sys.stderr)
        return 1
    return 0


def doctor(home: Path, output_directory: Optional[Path] = None) -> int:
    catalog = services(home)
    failures = background_diagnostics(home, catalog, output_directory)
    recovery = {
        "claude-code": "Sign in with Claude Code; allow its Keychain access if prompted.",
        "codex": "Sign in with Codex again (codex login).",
        "github-copilot": "Run gh auth status; sign in with gh auth login if needed and check your Copilot entitlement.",
    }
    print("\nProvider connections:")
    for service in catalog:
        try:
            usage = service.fetcher()
            print("OK   {:<15} {}".format(service.title, rate_value(usage)))
        except FETCH_ERRORS as error:
            failures += 1
            print("FAIL {:<15} {}".format(service.title, error))
            print("     {}".format(recovery.get(service.key, "Check provider credentials and retry.")))
    return 1 if failures else 0


def default_state_directory(home: Path) -> Path:
    configured = os.environ.get("RUNCAT_AI_USAGE_STATE_DIR")
    return Path(configured).expanduser() if configured else (
        home / "Library" / "Application Support" / "RunCat AI Usage" / "state"
    )


def default_output_directory(home: Path) -> Path:
    configured = os.environ.get("RUNCAT_AI_USAGE_OUTPUT_DIR")
    return Path(configured).expanduser() if configured else home / "RunCatMetrics"


def non_negative_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be an integer") from error
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be zero or greater")
    return parsed


def percentage_precision(value: str) -> int:
    parsed = non_negative_int(value)
    if parsed > 3:
        raise argparse.ArgumentTypeError("must be between 0 and 3")
    return parsed


def metric_rows(value: str) -> Tuple[str, ...]:
    rows = tuple(row.strip() for row in value.split(",") if row.strip())
    if not rows:
        raise argparse.ArgumentTypeError("must include at least one metric row")
    invalid = [row for row in rows if row not in METRIC_ROWS]
    if invalid:
        raise argparse.ArgumentTypeError(
            "unsupported metric row: {}".format(", ".join(invalid))
        )
    if len(set(rows)) != len(rows):
        raise argparse.ArgumentTypeError("metric rows must not contain duplicates")
    return rows


def trend_period(value: str) -> str:
    try:
        trend_period_seconds(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from error
    return value


def parser(home: Path) -> argparse.ArgumentParser:
    argument_parser = argparse.ArgumentParser(
        prog="runcat-ai-usage",
        description="Write AI plan usage snapshots for RunCat Neo.",
    )
    argument_parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="RunCat JSON output directory",
    )
    argument_parser.add_argument(
        "--state-dir",
        type=Path,
        default=default_state_directory(home),
        help="cache and history directory",
    )
    argument_parser.add_argument(
        "--refresh-seconds",
        type=non_negative_int,
        default=os.environ.get("RUNCAT_AI_USAGE_REFRESH_SECONDS", "55"),
        help="minimum provider API refresh interval",
    )
    argument_parser.add_argument(
        "--doctor",
        action="store_true",
        help="check automatic updates and provider connections; show recovery steps",
    )
    argument_parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s {}".format(__version__),
    )

    argument_parser.add_argument(
        "--otlp-endpoint", help="OTLP/HTTP metrics URL (default: localhost:4318/v1/metrics)",
    )
    commands = argument_parser.add_subparsers(dest="command")
    agent_setup.add_parser(commands)
    commands.add_parser("collect", help="send plan quotas to the OTel Collector (default)")
    receive_parser = commands.add_parser("serve", help="receive Collector OTLP/JSON and write RunCat snapshots")
    receive_parser.add_argument("--port", type=int, default=4319)

    config_parser = commands.add_parser(
        "config",
        help="show or change persistent display settings",
    )
    config_actions = config_parser.add_subparsers(dest="config_action", required=True)
    config_actions.add_parser("show", help="show the effective display settings")

    set_parser = config_actions.add_parser("set", help="change display settings")
    set_parser.add_argument(
        "--rows",
        type=metric_rows,
        help="comma-separated rows: " + ",".join(METRIC_ROWS),
    )
    set_parser.add_argument(
        "--rate-format",
        choices=RATE_FORMATS,
        help="show full used/limit details or percentage only",
    )
    set_parser.add_argument(
        "--percentage-precision",
        type=percentage_precision,
        help="maximum percentage decimal places (0-3)",
    )
    set_parser.add_argument(
        "--language",
        choices=LANGUAGES,
        help="metric label language",
    )
    set_parser.add_argument(
        "--trend-period",
        type=trend_period,
        metavar="PERIOD",
        help=(
            "trend window: {} or a custom duration such as 90m, 12h, or 14d"
        ).format(",".join(TREND_PERIOD_PRESETS)),
    )
    config_actions.add_parser("reset", help="restore default display settings")
    return argument_parser


def configure(arguments: argparse.Namespace, state_directory: Path) -> int:
    current = load_display_config(state_directory)
    if arguments.config_action == "set":
        current = DisplayConfig(
            rows=arguments.rows if arguments.rows is not None else current.rows,
            rate_format=(
                arguments.rate_format
                if arguments.rate_format is not None
                else current.rate_format
            ),
            percentage_precision=(
                arguments.percentage_precision
                if arguments.percentage_precision is not None
                else current.percentage_precision
            ),
            language=(
                arguments.language
                if arguments.language is not None
                else current.language
            ),
            trend_period=(
                arguments.trend_period
                if arguments.trend_period is not None
                else current.trend_period
            ),
        )
        save_display_config(state_directory, current)
    elif arguments.config_action == "reset":
        current = DEFAULT_DISPLAY_CONFIG
        save_display_config(state_directory, current)
    print(json.dumps(current.to_dict(), ensure_ascii=False, indent=2))
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    home = Path.home()
    arguments = parser(home).parse_args(argv)
    state_directory = arguments.state_dir.expanduser()
    if arguments.command == "agents":
        return agent_setup.execute(arguments, home)
    if arguments.command == "config":
        return configure(arguments, state_directory)
    if arguments.doctor:
        output_directory = arguments.output_dir
        if output_directory is None and os.environ.get("RUNCAT_AI_USAGE_OUTPUT_DIR"):
            output_directory = default_output_directory(home)
        return doctor(home, output_directory.expanduser() if output_directory else None)
    if arguments.command == "serve":
        return serve(home, (arguments.output_dir or default_output_directory(home)).expanduser(),
                     state_directory, arguments.port)
    return run_once(home, state_directory, arguments.refresh_seconds, arguments.otlp_endpoint)
