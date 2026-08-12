from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Callable, List

from models import Usage
from providers import collect_claude, collect_codex, collect_copilot


UsageFetcher = Callable[[], Usage]


@dataclass(frozen=True)
class Service:
    key: str
    filename: str
    title: str
    symbol: str
    fetcher: UsageFetcher


def services(home: Path) -> List[Service]:
    """Build the provider catalog for a user's home directory."""
    return [
        Service(
            "claude-code",
            "claude-code.json",
            "Claude Code",
            "staroflife",
            partial(collect_claude, home),
        ),
        Service(
            "codex",
            "codex.json",
            "Codex",
            "camera.aperture",
            partial(collect_codex, home),
        ),
        Service(
            "github-copilot",
            "github-copilot.json",
            "GitHub Copilot",
            "chevron.left.forwardslash.chevron.right",
            partial(collect_copilot, home),
        ),
    ]
