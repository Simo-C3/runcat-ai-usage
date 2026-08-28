from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class UsageWindow:
    """A named usage window reported by a provider."""

    key: str
    percentage: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "key", str(self.key))
        object.__setattr__(
            self,
            "percentage",
            max(0.0, min(float(self.percentage), 100.0)),
        )


@dataclass(frozen=True)
class MonthlyUsage:
    """Optional monthly usage budget reported alongside rolling windows."""

    enabled: bool
    percentage: Optional[float] = None
    used_amount: Optional[float] = None
    limit_amount: Optional[float] = None
    currency: str = ""
    decimal_places: int = 0

    def __post_init__(self) -> None:
        if self.percentage is not None:
            object.__setattr__(
                self,
                "percentage",
                max(0.0, min(float(self.percentage), 100.0)),
            )


@dataclass(frozen=True)
class Usage:
    percentage: float
    used_amount: Optional[float] = None
    limit_amount: Optional[float] = None
    amount_kind: Optional[str] = None
    unit: str = ""
    currency: str = ""
    decimal_places: int = 0
    windows: Tuple[UsageWindow, ...] = ()
    monthly: Optional[MonthlyUsage] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "percentage", max(0.0, min(float(self.percentage), 100.0)))

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Dict[str, Any]) -> "Usage":
        return cls(
            percentage=float(value["percentage"]),
            used_amount=_optional_float(value.get("used_amount")),
            limit_amount=_optional_float(value.get("limit_amount")),
            amount_kind=value.get("amount_kind"),
            unit=str(value.get("unit") or ""),
            currency=str(value.get("currency") or ""),
            decimal_places=int(value.get("decimal_places") or 0),
            windows=_usage_windows(value.get("windows")),
            monthly=_monthly_usage(value.get("monthly")),
        )


@dataclass(frozen=True)
class HistoryData:
    today: float
    last_hour: float
    daily: List[float]
    days_with_samples: List[bool]


def number(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_float(value: Any) -> Optional[float]:
    return None if value is None else float(value)


def _usage_windows(value: Any) -> Tuple[UsageWindow, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    windows = []
    for item in value:
        if not isinstance(item, dict):
            continue
        key = item.get("key")
        percentage = number(item.get("percentage"))
        if not isinstance(key, str) or not key or percentage is None:
            continue
        windows.append(UsageWindow(key=key, percentage=percentage))
    return tuple(windows)


def _monthly_usage(value: Any) -> Optional[MonthlyUsage]:
    if not isinstance(value, dict) or not isinstance(value.get("enabled"), bool):
        return None
    return MonthlyUsage(
        enabled=value["enabled"],
        percentage=number(value.get("percentage")),
        used_amount=number(value.get("used_amount")),
        limit_amount=number(value.get("limit_amount")),
        currency=str(value.get("currency") or ""),
        decimal_places=int(number(value.get("decimal_places")) or 0),
    )
