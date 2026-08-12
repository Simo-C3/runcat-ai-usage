from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Tuple

from storage import atomic_write_json, read_object


METRIC_ROWS = ("rate", "change", "trend")
RATE_FORMATS = ("full", "percentage")
LANGUAGES = ("en", "ja")


@dataclass(frozen=True)
class DisplayConfig:
    rows: Tuple[str, ...] = METRIC_ROWS
    rate_format: str = "full"
    percentage_precision: int = 1
    language: str = "en"

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

        return cls(rows, rate_format, precision, language)


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
