import tempfile
import unittest
from pathlib import Path

from config import (
    DEFAULT_DISPLAY_CONFIG,
    DisplayConfig,
    load_display_config,
    save_display_config,
)


class DisplayConfigTests(unittest.TestCase):
    def test_round_trip(self):
        configured = DisplayConfig(
            rows=("trend", "rate"),
            rate_format="percentage",
            percentage_precision=2,
            language="ja",
        )
        with tempfile.TemporaryDirectory() as directory:
            state_directory = Path(directory)
            save_display_config(state_directory, configured)
            self.assertEqual(load_display_config(state_directory), configured)

    def test_missing_or_invalid_config_uses_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            state_directory = Path(directory)
            self.assertEqual(
                load_display_config(state_directory),
                DEFAULT_DISPLAY_CONFIG,
            )
            (state_directory / "display.json").write_text(
                '{"rows":["unsupported"]}',
                encoding="utf-8",
            )
            self.assertEqual(
                load_display_config(state_directory),
                DEFAULT_DISPLAY_CONFIG,
            )


if __name__ == "__main__":
    unittest.main()
