import unittest

from models import MonthlyUsage, Usage, UsageWindow


class UsageModelTests(unittest.TestCase):
    def test_usage_windows_round_trip_through_cache_data(self):
        usage = Usage(
            percentage=27.5,
            windows=(
                UsageWindow("five_hour", 12),
                UsageWindow("seven_day", 27.5),
            ),
            monthly=MonthlyUsage(
                enabled=True,
                percentage=45.44,
                used_amount=45.44,
                limit_amount=100,
                currency="USD",
                decimal_places=2,
            ),
        )

        restored = Usage.from_dict(usage.to_dict())

        self.assertEqual(restored, usage)


if __name__ == "__main__":
    unittest.main()
