import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Tuple

from storage import atomic_write_json, read_object


METRIC_ROWS = ("rate", "change", "trend")
RATE_FORMATS = ("full", "percentage")
LANGUAGES = ("en", "ja")
TREND_PERIOD_PRESETS = ("1h", "1d", "1w", "1mo")
TREND_BUCKETS = 7
MIN_TREND_PERIOD_SECONDS = TREND_BUCKETS * 60
MAX_TREND_PERIOD_SECONDS = 365 * 86400


def trend_period_seconds(value: str) -> int:
    match = re.fullmatch(r"([1-9][0-9]*)(mo|m|h|d|w)", value)
    if match is None:
        raise ValueError("trend_period must use m, h, d, w, or mo")
    amount = int(match.group(1))
    unit = match.group(2)
    seconds = amount * {
        "m": 60,
        "h": 3600,
        "d": 86400,
        "w": 7 * 86400,
        "mo": 30 * 86400,
    }[unit]
    if not MIN_TREND_PERIOD_SECONDS <= seconds <= MAX_TREND_PERIOD_SECONDS:
        raise ValueError("trend_period must be between 7 minutes and 365 days")
    return seconds


@dataclass(frozen=True)
class DisplayConfig:
    rows: Tuple[str, ...] = METRIC_ROWS
    rate_format: str = "full"
    percentage_precision: int = 1
    language: str = "en"
    trend_period: str = "1w"

    def to_dict(self) -> Dict[str, Any]:
        value = asdict(self)
        value["rows"] = list(self.rows)
        return value

    @classmethod
    def from_dict(cls, value: Dict[str, Any]) -> "DisplayConfig":
        rows_value = value.get("rows", list(METRIC_ROWS))
        if not isinstance(rows_value, list):
            raise ValueError("rows must be a list")
        rows = tuple(str(row) for row in rows_value)
        if not rows or len(set(rows)) != len(rows) or any(row not in METRIC_ROWS for row in rows):
            raise ValueError("rows contains an unsupported or duplicate value")

        rate_format = str(value.get("rate_format", "full"))
        if rate_format not in RATE_FORMATS:
            raise ValueError("rate_format is unsupported")

        precision = value.get("percentage_precision", 1)
        if (
            isinstance(precision, bool)
            or not isinstance(precision, int)
            or not 0 <= precision <= 3
        ):
            raise ValueError("percentage_precision must be between 0 and 3")

        language = str(value.get("language", "en"))
        if language not in LANGUAGES:
            raise ValueError("language is unsupported")

        trend_period = str(value.get("trend_period", "1w"))
        trend_period_seconds(trend_period)

        return cls(rows, rate_format, precision, language, trend_period)


DEFAULT_DISPLAY_CONFIG = DisplayConfig()


def display_config_path(state_directory: Path) -> Path:
    return state_directory / "display.json"


def load_display_config(state_directory: Path) -> DisplayConfig:
    value = read_object(display_config_path(state_directory))
    if value is None:
        return DEFAULT_DISPLAY_CONFIG
    try:
        return DisplayConfig.from_dict(value)
    except (TypeError, ValueError):
        return DEFAULT_DISPLAY_CONFIG


def save_display_config(state_directory: Path, config: DisplayConfig) -> None:
    atomic_write_json(display_config_path(state_directory), config.to_dict())
