import argparse
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List

from . import __version__
from .cache import FETCH_ERRORS, cached_usage
from .history import HistoryStore
from .models import Usage
from .output import rate_value, write_snapshot
from .providers import collect_claude, collect_codex, collect_copilot


@dataclass(frozen=True)
class Service:
    key: str
    filename: str
    title: str
    symbol: str
    fetcher: Callable[[], Usage]


def services(home: Path) -> List[Service]:
    return [
        Service(
            "claude-code",
            "claude-code.json",
            "Claude Code",
            "staroflife",
            lambda: collect_claude(home),
        ),
        Service(
            "codex",
            "codex.json",
            "Codex",
            "camera.aperture",
            lambda: collect_codex(home),
        ),
        Service(
            "github-copilot",
            "github-copilot.json",
            "GitHub Copilot",
            "chevron.left.forwardslash.chevron.right",
            lambda: collect_copilot(home),
        ),
    ]


def run_once(
    home: Path,
    output_directory: Path,
    state_directory: Path,
    refresh_seconds: int,
) -> None:
    now = time.time()
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
                if result.usage is not None and result.usage.used_amount is not None
                else None
            )
            write_snapshot(
                output_directory / service.filename,
                service.title,
                service.symbol,
                result.usage,
                result.fetched_at,
                history,
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


def parser(home: Path) -> argparse.ArgumentParser:
    argument_parser = argparse.ArgumentParser(
        prog="runcat-ai-usage",
        description="Write AI plan usage snapshots for RunCat Neo."
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
        type=int,
        default=int(os.environ.get("RUNCAT_AI_USAGE_REFRESH_SECONDS", "55")),
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
    return argument_parser


def main(argv=None) -> int:
    home = Path.home()
    arguments = parser(home).parse_args(argv)
    if arguments.refresh_seconds < 0:
        parser(home).error("--refresh-seconds must be zero or greater")
    if arguments.doctor:
        return doctor(home)
    run_once(
        home,
        arguments.output_dir.expanduser(),
        arguments.state_dir.expanduser(),
        arguments.refresh_seconds,
    )
    return 0
