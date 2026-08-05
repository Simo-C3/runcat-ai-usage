from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class Usage:
    percentage: float
    used_amount: Optional[float] = None
    limit_amount: Optional[float] = None
    amount_kind: Optional[str] = None
    unit: str = ""
    currency: str = ""
    decimal_places: int = 0

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
        )


@dataclass(frozen=True)
class HistoryData:
    today: float
    last_hour: float
    daily: list
    days_with_samples: list


def number(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_float(value: Any) -> Optional[float]:
    return None if value is None else float(value)
