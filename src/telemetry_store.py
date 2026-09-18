"""Persistent quota state and deduplicated native OTel usage measurements."""

import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from config import MAX_TREND_PERIOD_SECONDS
from history import local_midnight
from models import MonthlyUsage, Usage, UsageWindow
from otlp import SCOPE, attribute_values, finite


PROVIDERS = ("claude-code", "codex", "github-copilot")
PLAN_METRICS = {"fetch.success", "fetched_at", "utilization", "remaining_percent",
                "used", "limit", "remaining", "enabled"}


def native_metric(name, resource, point_attributes):
    """Map only documented measurements, avoiding cached/reasoning token overlap."""
    service = str(resource.get("service.name", ""))
    if name == "claude_code.token.usage":
        return "claude-code", "tokens"
    if name == "claude_code.cost.usage":
        return "claude-code", "cost"
    if name in ("turn.token_usage", "codex.turn.token_usage") and "codex" in service.lower():
        if point_attributes.get("token_type") in ("input", "output"):
            return "codex", "tokens"
    if name == "gen_ai.client.token.usage" and service in ("copilot-chat", "github-copilot"):
        if point_attributes.get("gen_ai.token.type") in ("input", "output"):
            return "github-copilot", "tokens"
    return None


class TelemetryStore:
    def __init__(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(directory / "telemetry.db"), timeout=10)
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS quota (
                provider TEXT, profile TEXT, name TEXT, window TEXT,
                stamp INTEGER, value REAL, attributes TEXT,
                PRIMARY KEY(provider, profile, name, window));
            CREATE TABLE IF NOT EXISTS streams (
                id TEXT PRIMARY KEY, start INTEGER, end INTEGER, value REAL);
            CREATE TABLE IF NOT EXISTS increments (
                stream TEXT, stamp INTEGER, provider TEXT, kind TEXT, value REAL,
                PRIMARY KEY(stream, stamp));
            CREATE INDEX IF NOT EXISTS increments_time ON increments(stamp);
            CREATE INDEX IF NOT EXISTS increments_provider ON increments(provider, kind, stamp);
            CREATE TABLE IF NOT EXISTS health (key TEXT PRIMARY KEY, value REAL);
        """)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.db.commit()
        else:
            self.db.rollback()
        self.db.close()

    def ingest(self, payload, now):
        if not isinstance(payload, dict) or not isinstance(payload.get("resourceMetrics", []), list):
            raise ValueError("expected an OTLP metrics object")
        for resource_metric in payload.get("resourceMetrics", []):
            resource = attribute_values(resource_metric.get("resource", {}).get("attributes", []))
            for scope in resource_metric.get("scopeMetrics", []):
                for metric in scope.get("metrics", []):
                    name = metric.get("name", "")
                    kind = next((key for key in ("gauge", "sum", "histogram", "exponentialHistogram") if key in metric), None)
                    if kind is None:
                        continue
                    data = metric[kind]
                    for point in data.get("dataPoints", []):
                        if int(point.get("flags", 0)) & 1:
                            continue  # OTLP NO_RECORDED_VALUE
                        attrs = attribute_values(point.get("attributes", []))
                        stamp = int(point.get("timeUnixNano", 0))
                        if stamp <= 0 or stamp > int((now + 60) * 1e9):
                            raise ValueError("invalid or future metric timestamp")
                        if name.startswith(SCOPE + ".") and kind == "gauge":
                            short_name = name[len(SCOPE) + 1:]
                            window = attrs.get("window", "primary")
                            if short_name not in PLAN_METRICS or window not in ("primary", "five_hour", "seven_day", "monthly"):
                                continue
                            provider, profile = resource.get("ai.provider"), resource.get("runcat.profile")
                            if provider not in PROVIDERS or not isinstance(profile, str) or not profile:
                                continue
                            value = finite(point.get("asDouble", point.get("asInt")))
                            if value < 0 or (short_name in ("utilization", "remaining_percent") and value > 100):
                                raise ValueError("invalid plan value")
                            if short_name in ("fetch.success", "enabled") and value not in (0, 1):
                                raise ValueError("invalid plan status")
                            if not 0 <= int(attrs.get("decimal_places", 0)) <= 6:
                                raise ValueError("invalid amount precision")
                            self.db.execute("""
                                INSERT INTO quota VALUES (?, ?, ?, ?, ?, ?, ?)
                                ON CONFLICT(provider, profile, name, window) DO UPDATE SET
                                    stamp=excluded.stamp, value=excluded.value, attributes=excluded.attributes
                                WHERE excluded.stamp >= quota.stamp
                            """, (provider, profile, short_name, window,
                                  stamp, value, json.dumps(attrs)))
                        else:
                            mapped = native_metric(name, resource, attrs)
                            if mapped and kind in ("sum", "histogram", "exponentialHistogram"):
                                value = finite(point.get("sum") if kind != "sum" else point.get("asDouble", point.get("asInt")))
                                identity = json.dumps([resource, scope.get("scope", {}), name, kind,
                                                       data.get("aggregationTemporality"), attrs,
                                                       point.get("startTimeUnixNano", "0")
                                                       if int(data.get("aggregationTemporality", 0)) == 2 else None], sort_keys=True)
                                stream = hashlib.sha256(identity.encode()).hexdigest()
                                self.record_increment(stream, mapped, point, data, stamp, value)
        self.db.execute("INSERT OR REPLACE INTO health VALUES ('received_at', ?)", (now,))
        before = int((now - MAX_TREND_PERIOD_SECONDS - 86400) * 1e9)
        self.db.execute("DELETE FROM increments WHERE stamp < ?", (before,))
        self.db.execute("DELETE FROM streams WHERE end < ?", (before,))
        self.db.execute("DELETE FROM quota WHERE stamp < ?", (before,))

    def record_increment(self, stream, mapped, point, data, stamp, value):
        if value < 0:
            raise ValueError("usage totals must not be negative")
        temporality = int(data.get("aggregationTemporality", 0))
        if temporality not in (1, 2):
            raise ValueError("usage metrics require delta or cumulative temporality")
        start = int(point.get("startTimeUnixNano", 0))
        if start < 0 or start > stamp:
            raise ValueError("invalid metric start time")
        previous = self.db.execute("SELECT start, end, value FROM streams WHERE id=?", (stream,)).fetchone()
        if temporality == 2 and previous and stamp <= previous[1]:
            return
        delta = value
        if temporality == 2 and previous and start == previous[0] and value >= previous[2]:
            delta = value - previous[2]
        self.db.execute("INSERT OR IGNORE INTO increments VALUES (?, ?, ?, ?, ?)",
                        (stream, stamp, mapped[0], mapped[1], delta))
        if previous is None or stamp > previous[1]:
            self.db.execute("INSERT OR REPLACE INTO streams VALUES (?, ?, ?, ?)", (stream, start, stamp, value))

    def quota(self, provider):
        active = self.db.execute("""SELECT profile, value, stamp FROM quota
            WHERE provider=? AND name='fetch.success' ORDER BY stamp DESC LIMIT 1""", (provider,)).fetchone()
        if active is None:
            return provider, None, None, False
        profile, success, _ = active
        # A failed credential lookup has no account identity. Keep the previous
        # account's last known value, explicitly stale, rather than erasing it.
        # A resolved new account never inherits the previous account's quota.
        if profile == provider and not success:
            previous = self.db.execute("""SELECT profile FROM quota
                WHERE provider=? AND name='utilization' AND window='primary'
                ORDER BY stamp DESC LIMIT 1""", (provider,)).fetchone()
            if previous:
                profile = previous[0]
        rows = self.db.execute("SELECT name, window, stamp, value, attributes FROM quota WHERE provider=? AND profile=?",
                               (provider, profile)).fetchall()
        points = {(name, window): (stamp, value, json.loads(attrs)) for name, window, stamp, value, attrs in rows}
        primary = points.get(("utilization", "primary"))
        if primary is None:
            return profile, None, None, False
        stamp, percentage, metadata = primary

        def get(name, window="primary"):
            item = points.get((name, window))
            return item[1] if item and item[0] == stamp else None

        windows = tuple(UsageWindow(window, get("utilization", window))
                        for window in ("five_hour", "seven_day") if get("utilization", window) is not None)
        monthly = None
        if get("enabled", "monthly") is not None:
            item = points.get(("utilization", "monthly")) or points.get(("used", "monthly"))
            extra = item[2] if item and item[0] == stamp else {}
            monthly = MonthlyUsage(bool(get("enabled", "monthly")), get("utilization", "monthly"),
                get("used", "monthly"), get("limit", "monthly"), extra.get("currency", ""),
                int(extra.get("decimal_places", 0)))
        usage = Usage(percentage, get("used"), get("limit"), metadata.get("amount_kind"),
                      metadata.get("unit", ""), metadata.get("currency", ""),
                      int(metadata.get("decimal_places", 0)), windows, monthly)
        return profile, usage, stamp / 1e9, bool(success)

    def totals(self, provider, now):
        today = local_midnight(datetime.fromtimestamp(now).astimezone().date())
        result = {}
        for kind in ("tokens", "cost"):
            latest = self.db.execute("SELECT MAX(stamp) FROM increments WHERE provider=? AND kind=?", (provider, kind)).fetchone()[0]
            if latest is None:
                continue
            def total(since):
                return self.db.execute("SELECT COALESCE(SUM(value), 0) FROM increments WHERE provider=? AND kind=? AND stamp>? AND stamp<=?",
                    (provider, kind, int(since * 1e9), int(now * 1e9))).fetchone()[0]
            result[kind] = {"today": total(today), "hour": total(now - 3600), "last_received": latest / 1e9}
        return result

    def health(self):
        return dict(self.db.execute("SELECT key, value FROM health"))
