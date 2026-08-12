import tempfile
import unittest
from pathlib import Path

from history import HistoryStore, positive_delta
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
