import json
import subprocess
import time
import urllib.error
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from .models import Usage, number
from .storage import atomic_write_json, read_object


FETCH_ERRORS = (
    OSError,
    subprocess.SubprocessError,
    urllib.error.URLError,
    json.JSONDecodeError,
    ValueError,
)


@dataclass(frozen=True)
class CacheResult:
    usage: Optional[Usage]
    fetched_at: Optional[float]
    error: Optional[Exception]


def cached_usage(
    path: Path,
    fetcher: Callable[[], Usage],
    refresh_seconds: int,
    now: Optional[float] = None,
) -> CacheResult:
    current_time = time.time() if now is None else now
    cache = read_object(path) or {}
    attempted_at = number(cache.get("attempted_at")) or 0
    fetched_at = number(cache.get("fetched_at"))
    stale_usage = _cached_value(cache)

    if current_time - attempted_at < refresh_seconds:
        return CacheResult(stale_usage, fetched_at, None)

    try:
        usage = fetcher()
        atomic_write_json(
            path,
            {
                "attempted_at": current_time,
                "fetched_at": current_time,
                "usage": usage.to_dict(),
            },
        )
        return CacheResult(usage, current_time, None)
    except FETCH_ERRORS as error:
        cache["attempted_at"] = current_time
        atomic_write_json(path, cache)
        return CacheResult(stale_usage, fetched_at, error)


def _cached_value(cache: dict) -> Optional[Usage]:
    value = cache.get("usage")
    if not isinstance(value, dict):
        return None
    try:
        return Usage.from_dict(value)
    except (KeyError, TypeError, ValueError):
        return None
