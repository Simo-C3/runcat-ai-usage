from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from config import DEFAULT_DISPLAY_CONFIG, DisplayConfig
from models import HistoryData, Usage
from storage import atomic_write_json


LABELS = {
    "en": {
        "rate": "Rate",
        "change": "Today / 1h",
        "trend": "7d Trend",
        "unavailable": "Unavailable",
    },
    "ja": {
        "rate": "使用率",
        "change": "今日 / 1時間",
        "trend": "7日推移",
        "unavailable": "取得不可",
    },
}


def percentage_value(percentage: float, precision: int = 1) -> str:
    formatted = "{:.{}f}".format(percentage, precision)
    if precision > 0:
        formatted = formatted.rstrip("0").rstrip(".")
    return formatted + "%"


def currency_value(amount: float, currency: str, decimal_places: int) -> str:
    symbol = {"USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥"}.get(currency)
    formatted = "{:,.{}f}".format(amount, max(0, decimal_places))
    return (
        "{}{}".format(symbol, formatted)
        if symbol
        else "{} {}".format(formatted, currency).strip()
    )


def count_value(value: float) -> str:
    rounded = round(value)
    return "{:,}".format(rounded) if abs(value - rounded) < 0.05 else "{:,.1f}".format(value)


def rate_value(
    usage: Usage,
    config: DisplayConfig = DEFAULT_DISPLAY_CONFIG,
) -> str:
    formatted = percentage_value(usage.percentage, config.percentage_precision)
    if (
        config.rate_format == "percentage"
        or usage.used_amount is None
        or usage.limit_amount is None
    ):
        return formatted
    if usage.amount_kind == "currency":
        used = currency_value(usage.used_amount, usage.currency, usage.decimal_places)
        limit = currency_value(usage.limit_amount, usage.currency, usage.decimal_places)
        return "{} · {} / {}".format(formatted, used, limit)
    used = count_value(usage.used_amount)
    limit = count_value(usage.limit_amount)
    return "{} · {} / {} {}".format(formatted, used, limit, usage.unit).strip()


def change_value(history: HistoryData, usage: Usage) -> str:
    if usage.amount_kind == "currency":
        today = currency_value(history.today, usage.currency, usage.decimal_places)
        hour = currency_value(history.last_hour, usage.currency, usage.decimal_places)
        return "{} / {}".format(today, hour)
    today = count_value(history.today)
    hour = count_value(history.last_hour)
    return "{} / {} {}".format(today, hour, usage.unit).strip()


def trend_value(history: HistoryData) -> str:
    blocks = "▁▂▃▄▅▆▇█"
    peak = max(
        (
            value
            for value, present in zip(history.daily, history.days_with_samples)
            if present
        ),
        default=0.0,
    )
    if peak <= 0:
        return "".join(blocks[0] if present else "·" for present in history.days_with_samples)
    return "".join(
        (
            blocks[min(len(blocks) - 1, round(value / peak * (len(blocks) - 1)))]
            if present
            else "·"
        )
        for value, present in zip(history.daily, history.days_with_samples)
    )


def snapshot(
    title: str,
    symbol: str,
    usage: Optional[Usage],
    fetched_at: Optional[float],
    history: Optional[HistoryData],
    config: DisplayConfig = DEFAULT_DISPLAY_CONFIG,
) -> Dict[str, Any]:
    metrics = []
    labels = LABELS[config.language]
    value: Dict[str, Any] = {
        "title": title,
        "symbol": symbol,
        "metrics": metrics,
        "lastUpdatedDate": iso_timestamp(fetched_at),
    }
    if usage is None:
        if "rate" in config.rows:
            metrics.append(
                {
                    "title": labels["rate"],
                    "formattedValue": labels["unavailable"],
                }
            )
        value["metricsBarValue"] = "N/A"
        return value

    for row in config.rows:
        if row == "rate":
            metrics.append(
                {
                    "title": labels["rate"],
                    "formattedValue": rate_value(usage, config),
                }
            )
        elif row == "change" and history is not None:
            metrics.append(
                {
                    "title": labels["change"],
                    "formattedValue": change_value(history, usage),
                }
            )
        elif row == "trend" and history is not None:
            metrics.append(
                {
                    "title": labels["trend"],
                    "formattedValue": trend_value(history),
                }
            )
    value["metricsBarValue"] = percentage_value(
        usage.percentage,
        config.percentage_precision,
    )
    return value


def write_snapshot(
    path: Path,
    title: str,
    symbol: str,
    usage: Optional[Usage],
    fetched_at: Optional[float],
    history: Optional[HistoryData],
    config: DisplayConfig = DEFAULT_DISPLAY_CONFIG,
) -> None:
    atomic_write_json(path, snapshot(title, symbol, usage, fetched_at, history, config))


def iso_timestamp(epoch_seconds: Optional[float]) -> str:
    timestamp = epoch_seconds if epoch_seconds is not None else datetime.now().timestamp()
    return datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
