import sqlite3
from datetime import date, datetime, time as datetime_time, timedelta
from pathlib import Path
from typing import Optional, Sequence

from models import HistoryData, Usage


class HistoryStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(path), timeout=10)
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS usage_samples (
                service TEXT NOT NULL,
                sampled_at INTEGER NOT NULL,
                used REAL NOT NULL,
                PRIMARY KEY (service, sampled_at)
            )
            """
        )
        self.connection.execute(
            "CREATE INDEX IF NOT EXISTS usage_samples_time ON usage_samples(sampled_at)"
        )

    def __enter__(self) -> "HistoryStore":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        if exc_type is None:
            self.connection.commit()
        self.connection.close()

    def record(
        self,
        service: str,
        usage: Optional[Usage],
        sampled_at: Optional[float],
    ) -> None:
        if usage is None or usage.used_amount is None or sampled_at is None:
            return
        minute = int(sampled_at // 60 * 60)
        self.connection.execute(
            """
            INSERT INTO usage_samples(service, sampled_at, used)
            VALUES (?, ?, ?)
            ON CONFLICT(service, sampled_at) DO UPDATE SET used = excluded.used
            """,
            (service, minute, usage.used_amount),
        )

    def period_delta(self, service: str, start_at: float, end_at: float) -> float:
        baseline = self.connection.execute(
            """
            SELECT used
            FROM usage_samples
            WHERE service = ? AND sampled_at <= ?
            ORDER BY sampled_at DESC
            LIMIT 1
            """,
            (service, int(start_at)),
        ).fetchone()
        rows = self.connection.execute(
            """
            SELECT used
            FROM usage_samples
            WHERE service = ? AND sampled_at > ? AND sampled_at <= ?
            ORDER BY sampled_at
            """,
            (service, int(start_at), int(end_at)),
        ).fetchall()
        values = ([baseline[0]] if baseline else []) + [row[0] for row in rows]
        return positive_delta(values)

    def summary(self, service: str, now: float) -> HistoryData:
        local_now = datetime.fromtimestamp(now).astimezone()
        today_start = local_midnight(local_now.date())
        today = self.period_delta(service, today_start, now)
        last_hour = self.period_delta(service, now - 3600, now)

        daily = []
        days_with_samples = []
        first_day = local_now.date() - timedelta(days=6)
        for offset in range(7):
            day = first_day + timedelta(days=offset)
            start = local_midnight(day)
            end = local_midnight(day + timedelta(days=1)) - 1
            present = (
                self.connection.execute(
                    """
                    SELECT 1
                    FROM usage_samples
                    WHERE service = ? AND sampled_at >= ? AND sampled_at <= ?
                    LIMIT 1
                    """,
                    (service, int(start), int(end)),
                ).fetchone()
                is not None
            )
            days_with_samples.append(present)
            daily.append(self.period_delta(service, start, end))
        return HistoryData(today, last_hour, daily, days_with_samples)

    def prune(self, before: float) -> None:
        self.connection.execute(
            "DELETE FROM usage_samples WHERE sampled_at < ?",
            (int(before),),
        )


def positive_delta(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0

    suffix_maximums = [float("-inf")] * len(values)
    suffix_maximums[-1] = values[-1]
    for index in range(len(values) - 2, -1, -1):
        suffix_maximums[index] = max(values[index], suffix_maximums[index + 1])

    total = 0.0
    previous = values[0]
    for index, current in enumerate(values[1:], start=1):
        if current >= previous:
            total += current - previous
            previous = current
            continue

        # Usage counters are monotonic within a billing period. Ignore a
        # temporary lower response when a later sample recovers to this level.
        if index + 1 < len(values) and suffix_maximums[index + 1] >= previous:
            continue
        total += current
        previous = current
    return max(0.0, total)


def local_midnight(day: date) -> float:
    return datetime.combine(day, datetime_time.min).astimezone().timestamp()
