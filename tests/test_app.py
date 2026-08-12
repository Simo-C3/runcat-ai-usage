import argparse
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app import main, metric_rows, non_negative_int, parser, trend_period
from config import load_display_config


class AppTests(unittest.TestCase):
    def test_refresh_interval_must_be_non_negative(self):
        self.assertEqual(non_negative_int("0"), 0)
        with self.assertRaises(argparse.ArgumentTypeError):
            non_negative_int("-1")
        with self.assertRaises(argparse.ArgumentTypeError):
            non_negative_int("invalid")

    def test_environment_refresh_interval_is_converted_to_integer(self):
        with mock.patch.dict(
            os.environ,
            {"RUNCAT_AI_USAGE_REFRESH_SECONDS": "42"},
        ):
            arguments = parser(Path("/tmp/example-home")).parse_args([])
        self.assertEqual(arguments.refresh_seconds, 42)

    def test_metric_rows_are_validated_and_keep_order(self):
        self.assertEqual(metric_rows("trend,rate"), ("trend", "rate"))
        with self.assertRaises(argparse.ArgumentTypeError):
            metric_rows("rate,unknown")
        with self.assertRaises(argparse.ArgumentTypeError):
            metric_rows("rate,rate")

    def test_trend_period_rejects_invalid_custom_duration(self):
        self.assertEqual(trend_period("14d"), "14d")
        with self.assertRaises(argparse.ArgumentTypeError):
            trend_period("forever")

    def test_config_command_persists_display_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            state_directory = Path(directory)
            with mock.patch("sys.stdout"):
                result = main(
                    [
                        "--state-dir",
                        str(state_directory),
                        "config",
                        "set",
                        "--rows",
                        "trend,rate",
                        "--rate-format",
                        "percentage",
                        "--percentage-precision",
                        "2",
                        "--language",
                        "ja",
                        "--trend-period",
                        "12h",
                    ]
                )
            self.assertEqual(result, 0)
            configured = load_display_config(state_directory)
            self.assertEqual(configured.rows, ("trend", "rate"))
            self.assertEqual(configured.rate_format, "percentage")
            self.assertEqual(configured.percentage_precision, 2)
            self.assertEqual(configured.language, "ja")
            self.assertEqual(configured.trend_period, "12h")


if __name__ == "__main__":
    unittest.main()
