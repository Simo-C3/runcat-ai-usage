import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional, Sequence, Tuple

from cache import FETCH_ERRORS, cached_usage
from config import (
    DEFAULT_DISPLAY_CONFIG,
    LANGUAGES,
    METRIC_ROWS,
    RATE_FORMATS,
    DisplayConfig,
    load_display_config,
    save_display_config,
)
from history import HistoryStore
from output import rate_value, write_snapshot
from runcat_ai_usage import __version__
from services import services


def run_once(
    home: Path,
    output_directory: Path,
    state_directory: Path,
    refresh_seconds: int,
    display_config: DisplayConfig = DEFAULT_DISPLAY_CONFIG,
) -> None:
    now = time.time()
    history_requested = any(
        row in display_config.rows for row in ("change", "trend")
    )
    with HistoryStore(state_directory / "history.db") as history_store:
        for service in services(home):
            result = cached_usage(
                state_directory / "cache" / "{}.json".format(service.key),
                service.fetcher,
                refresh_seconds,
                now,
            )
            if result.error is not None:
                print("[{}] {}".format(service.title, result.error), file=sys.stderr)
            history_store.record(service.key, result.usage, result.fetched_at)
            history = (
                history_store.summary(service.key, now)
                if (
                    history_requested
                    and result.usage is not None
                    and result.usage.used_amount is not None
                )
                else None
            )
            write_snapshot(
                output_directory / service.filename,
                service.title,
                service.symbol,
                result.usage,
                result.fetched_at,
                history,
                display_config,
            )
        history_store.prune(now - 40 * 86400)


def doctor(home: Path) -> int:
    failures = 0
    for service in services(home):
        try:
            usage = service.fetcher()
            print("OK   {:<15} {}".format(service.title, rate_value(usage)))
        except FETCH_ERRORS as error:
            failures += 1
            print("FAIL {:<15} {}".format(service.title, error))
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


def parser(home: Path) -> argparse.ArgumentParser:
    argument_parser = argparse.ArgumentParser(
        prog="runcat-ai-usage",
        description="Write AI plan usage snapshots for RunCat Neo.",
    )
    argument_parser.add_argument(
        "--output-dir",
        type=Path,
        default=default_output_directory(home),
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
        help="check all provider credentials and APIs",
    )
    argument_parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s {}".format(__version__),
    )

    commands = argument_parser.add_subparsers(dest="command")
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
        help="comma-separated rows in display order: rate,change,trend",
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
    if arguments.command == "config":
        return configure(arguments, state_directory)
    if arguments.doctor:
        return doctor(home)
    run_once(
        home,
        arguments.output_dir.expanduser(),
        state_directory,
        arguments.refresh_seconds,
        load_display_config(state_directory),
    )
    return 0
