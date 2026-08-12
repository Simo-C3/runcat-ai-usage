import argparse
import os
import unittest
from pathlib import Path
from unittest import mock

from runcat_ai_usage.app import non_negative_int, parser


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


if __name__ == "__main__":
    unittest.main()
