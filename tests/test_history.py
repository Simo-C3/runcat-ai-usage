from datetime import date, timedelta
from pathlib import Path
import tempfile
import unittest

from history import HistoryStore, local_midnight, positive_delta
from models import Usage


class HistoryTests(unittest.TestCase):
    def test_positive_delta_handles_counter_reset(self):
        self.assertEqual(positive_delta([90, 100, 3, 8]), 18)

    def test_positive_delta_ignores_temporary_zero(self):
        self.assertEqual(positive_delta([241.5, 0, 241.5]), 0)

    def test_period_delta_uses_sample_at_period_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.db"
            usage = Usage(percentage=10, used_amount=100)
            with HistoryStore(path) as store:
                store.record("codex", usage, 600)
                store.record(
                    "codex",
                    Usage(percentage=11, used_amount=112),
                    660,
                )
                self.assertEqual(store.period_delta("codex", 600, 660), 12)

    def test_summary_splits_custom_period_into_seven_buckets(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.db"
            with HistoryStore(path) as store:
                for index in range(8):
                    store.record(
                        "codex",
                        Usage(percentage=10, used_amount=index),
                        600 + index * 600,
                    )
                summary = store.summary("codex", 4800, 4200)
                self.assertEqual(summary.daily, [1] * 7)
                self.assertEqual(summary.days_with_samples, [True] * 7)

    def test_summary_aligns_day_based_trends_to_local_dates(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.db"
            today = date(2026, 1, 15)
            now = local_midnight(today) + 12 * 3600
            first_day = today - timedelta(days=6)
            used = 100
            with HistoryStore(path) as store:
                for offset in range(7):
                    day = first_day + timedelta(days=offset)
                    start = local_midnight(day)
                    store.record(
                        "codex",
                        Usage(percentage=10, used_amount=used),
                        start,
                    )
                    used += offset + 1
                    event_time = start + (9 if offset == 6 else 18) * 3600
                    store.record(
                        "codex",
                        Usage(percentage=10, used_amount=used),
                        event_time,
                    )

                summary = store.summary("codex", now, 7 * 86400)

            self.assertEqual(summary.daily, [1, 2, 3, 4, 5, 6, 7])
            self.assertEqual(summary.days_with_samples, [True] * 7)

    def test_record_skips_usage_without_absolute_amount(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.db"
            with HistoryStore(path) as store:
                store.record("claude", Usage(percentage=10), 600)
                count = store.connection.execute(
                    "SELECT COUNT(*) FROM usage_samples"
                ).fetchone()[0]
                self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
