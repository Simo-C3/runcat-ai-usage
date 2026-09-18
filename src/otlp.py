"""OTLP/HTTP JSON quota export. Native agents send OTLP to the same Collector."""

import json
import math
import os
import urllib.request
from urllib.parse import unquote

from cache import CacheResult
from services import Service


SCOPE = "runcat.ai.plan"
DEFAULT_ENDPOINT = "http://127.0.0.1:4318/v1/metrics"


def attributes(values):
    return [{"key": key, "value": {"stringValue": str(value)}}
            for key, value in values.items() if value is not None]


def attribute_values(items):
    return {item["key"]: next(iter(item.get("value", {}).values()), "")
            for item in items if isinstance(item, dict) and "key" in item}


def finite(value):
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("metric values must be finite")
    return result


def quota_resource(service: Service, profile: str, result: CacheResult, now: float):
    metrics = []

    def gauge(name, value, window="primary", unit="1", metadata=None, stamp=None):
        if value is None:
            return
        metrics.append({
            "name": SCOPE + "." + name,
            "unit": unit,
            "gauge": {"dataPoints": [{
                "attributes": attributes(dict(metadata or {}, window=window)),
                "timeUnixNano": str(round((stamp if stamp is not None else result.fetched_at) * 1e9)),
                "asDouble": finite(value),
            }]},
        })

    gauge("fetch.success", int(result.error is None and result.usage is not None
                              and result.fetched_at is not None
                              and now - result.fetched_at <= 180), stamp=now)
    if result.usage is not None and result.fetched_at is not None:
        usage = result.usage
        gauge("fetched_at", result.fetched_at, unit="s", stamp=now)

        def window_values(window, percentage, used, limit, metadata):
            gauge("utilization", percentage, window, "%", metadata)
            if percentage is not None:
                gauge("remaining_percent", max(0, 100 - percentage), window, "%", metadata)
            amount_unit = metadata.get("currency") or metadata.get("unit") or "1"
            gauge("used", used, window, amount_unit, metadata)
            gauge("limit", limit, window, amount_unit, metadata)
            if used is not None and limit is not None:
                gauge("remaining", max(0, limit - used), window, amount_unit, metadata)

        metadata = {"amount_kind": usage.amount_kind, "unit": usage.unit,
                    "currency": usage.currency, "decimal_places": usage.decimal_places}
        window_values("primary", usage.percentage, usage.used_amount, usage.limit_amount, metadata)
        for window in usage.windows:
            window_values(window.key, window.percentage, None, None, {})
        if usage.monthly is not None:
            monthly = usage.monthly
            gauge("enabled", int(monthly.enabled), "monthly")
            window_values("monthly", monthly.percentage, monthly.used_amount, monthly.limit_amount,
                          {"currency": monthly.currency, "decimal_places": monthly.decimal_places,
                           "amount_kind": "currency"})
    return {
        "resource": {"attributes": attributes({"service.name": "runcat-ai-usage-quota",
                     "ai.provider": service.key, "runcat.profile": profile})},
        "scopeMetrics": [{"scope": {"name": SCOPE}, "metrics": metrics}],
    }


def metrics_endpoint():
    explicit = os.environ.get("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT")
    base = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    return explicit or (base.rstrip("/") + "/v1/metrics" if base else DEFAULT_ENDPOINT)


def export_metrics(payload, endpoint=None):
    headers = {"Content-Type": "application/json"}
    raw_headers = os.environ.get("OTEL_EXPORTER_OTLP_METRICS_HEADERS",
                                 os.environ.get("OTEL_EXPORTER_OTLP_HEADERS", ""))
    for item in raw_headers.split(","):
        if item.strip():
            key, value = item.split("=", 1)
            headers[key.strip()] = unquote(value.strip())
    request = urllib.request.Request(endpoint or metrics_endpoint(),
        data=json.dumps(payload, allow_nan=False).encode(), headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=10) as response:
        body = response.read()
        if response.status != 200:
            raise ValueError("OTLP export did not return HTTP 200")
        result = json.loads(body) if body else {}
        if not isinstance(result, dict) or not isinstance(result.get("partialSuccess", {}), dict):
            raise ValueError("Invalid OTLP export response")
        if int(result.get("partialSuccess", {}).get("rejectedDataPoints", 0)):
            raise ValueError("Collector rejected metric data points")
