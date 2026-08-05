import json
import tempfile
import unittest
from pathlib import Path

from runcat_ai_usage.models import HistoryData, Usage
from runcat_ai_usage.output import rate_value, snapshot, write_snapshot


class OutputTests(unittest.TestCase):
    def test_compact_count_rate(self):
        usage = Usage(
            percentage=14.1,
            used_amount=6972,
            limit_amount=50000,
            amount_kind="count",
            unit="AIC",
        )
        self.assertEqual(rate_value(usage), "14.1% · 6,972 / 50,000 AIC")

    def test_compact_currency_rate(self):
        usage = Usage(
            percentage=0.268,
            used_amount=2.68,
            limit_amount=1000,
            amount_kind="currency",
            currency="USD",
            decimal_places=2,
        )
        self.assertEqual(rate_value(usage), "0.3% · $2.68 / $1,000.00")

    def test_snapshot_has_three_compact_rows(self):
        usage = Usage(
            percentage=20,
            used_amount=10,
            limit_amount=50,
            amount_kind="count",
            unit="credits",
        )
        history = HistoryData(
            today=3,
            last_hour=1,
            daily=[0, 0, 0, 0, 0, 2, 3],
            days_with_samples=[False, False, False, False, False, True, True],
        )
        value = snapshot("Codex", "camera.aperture", usage, 0, history)
        self.assertEqual(
            [metric["title"] for metric in value["metrics"]],
            ["Rate", "Today / 1h", "7d Trend"],
        )
        self.assertEqual(value["metricsBarValue"], "20%")
        self.assertEqual(value["metrics"][2]["formattedValue"], "·····▆█")

    def test_writer_produces_valid_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "metric.json"
            write_snapshot(path, "Codex", "camera.aperture", None, None, None)
            with path.open(encoding="utf-8") as source:
                value = json.load(source)
            self.assertEqual(value["metricsBarValue"], "N/A")


if __name__ == "__main__":
    unittest.main()
