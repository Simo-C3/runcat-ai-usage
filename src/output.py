from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from config import DEFAULT_DISPLAY_CONFIG, DisplayConfig
from models import HistoryData, MonthlyUsage, Usage
from storage import atomic_write_json


LABELS = {
    "en": {
        "rate": "Rate",
        "change": "Today / 1h",
        "trend": "{} Trend",
        "unavailable": "Unavailable",
        "monthly": "Monthly",
        "disabled": "Disabled",
        "enabled": "Enabled",
    },
    "ja": {
        "rate": "使用率",
        "change": "今日 / 1時間",
        "trend": "{}推移",
        "unavailable": "取得不可",
        "monthly": "月次",
        "disabled": "無効",
        "enabled": "有効",
    },
}

WINDOW_LABELS = {
    "en": {
        "five_hour": "5h",
        "seven_day": "7d",
    },
    "ja": {
        "five_hour": "5時間",
        "seven_day": "7日",
    },
}


def trend_period_label(period: str, language: str) -> str:
    amount = int(period[:-2] if period.endswith("mo") else period[:-1])
    unit = "mo" if period.endswith("mo") else period[-1]
    if language == "en":
        return "7d" if period == "1w" else period
    if period == "1w":
        return "7日"
    return "{}{}".format(
        amount,
        {
            "m": "分",
            "h": "時間",
            "d": "日",
            "w": "週間",
            "mo": "ヶ月",
        }[unit],
    )


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


def monthly_value(
    monthly: MonthlyUsage,
    config: DisplayConfig = DEFAULT_DISPLAY_CONFIG,
) -> str:
    labels = LABELS[config.language]
    if not monthly.enabled:
        return labels["disabled"]
    if monthly.percentage is None:
        return labels["enabled"]
    return rate_value(
        Usage(
            percentage=monthly.percentage,
            used_amount=monthly.used_amount,
            limit_amount=monthly.limit_amount,
            amount_kind="currency",
            currency=monthly.currency,
            decimal_places=monthly.decimal_places,
        ),
        config,
    )


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
            if usage.windows:
                metrics.extend(
                    {
                        "title": WINDOW_LABELS[config.language].get(
                            window.key, window.key
                        ),
                        "formattedValue": percentage_value(
                            window.percentage, config.percentage_precision
                        ),
                    }
                    for window in usage.windows
                )
                if usage.monthly is not None:
                    metrics.append(
                        {
                            "title": labels["monthly"],
                            "formattedValue": monthly_value(usage.monthly, config),
                        }
                    )
            elif usage.monthly is not None:
                metrics.append(
                    {
                        "title": labels["monthly"],
                        "formattedValue": monthly_value(usage.monthly, config),
                    }
                )
            else:
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
                    "title": labels["trend"].format(
                        trend_period_label(config.trend_period, config.language)
                    ),
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
