import unittest

from runcat_ai_usage.providers import (
    ProviderError,
    parse_claude_usage,
    parse_codex_usage,
    parse_copilot_usage,
)


class ProviderParsingTests(unittest.TestCase):
    def test_claude_prefers_highest_rolling_window(self):
        usage = parse_claude_usage(
            {
                "five_hour": {"utilization": 12},
                "seven_day": {"utilization": 27.5},
            }
        )
        self.assertEqual(usage.percentage, 27.5)
        self.assertIsNone(usage.used_amount)

    def test_claude_parses_enterprise_extra_usage(self):
        usage = parse_claude_usage(
            {
                "five_hour": None,
                "seven_day": None,
                "extra_usage": {
                    "used_credits": 268,
                    "monthly_limit": 100000,
                    "decimal_places": 2,
                    "currency": "USD",
                },
            }
        )
        self.assertAlmostEqual(usage.percentage, 0.268)
        self.assertEqual(usage.used_amount, 2.68)
        self.assertEqual(usage.limit_amount, 1000)

    def test_codex_parses_spend_control(self):
        usage = parse_codex_usage(
            {
                "spend_control": {
                    "individual_limit": {
                        "used_percent": 44,
                        "used": 241.5,
                        "limit": 550,
                    }
                }
            }
        )
        self.assertEqual(usage.percentage, 44)
        self.assertEqual(usage.unit, "credits")
        self.assertEqual(usage.used_amount, 241.5)

    def test_codex_falls_back_to_rate_limits(self):
        usage = parse_codex_usage(
            {
                "rate_limit": {
                    "primary_window": {"used_percent": 10},
                    "secondary_window": {"used_percent": 30},
                }
            }
        )
        self.assertEqual(usage.percentage, 30)

    def test_copilot_parses_ai_credits(self):
        usage = parse_copilot_usage(
            {
                "quota_snapshots": {
                    "premium_interactions": {
                        "percent_remaining": 80,
                        "credits_used": 11000,
                        "entitlement": 50000,
                    }
                }
            }
        )
        self.assertEqual(usage.percentage, 22)
        self.assertEqual(usage.used_amount, 11000)
        self.assertEqual(usage.limit_amount, 50000)
        self.assertEqual(usage.unit, "AIC")

    def test_missing_usage_raises_clear_error(self):
        with self.assertRaisesRegex(ProviderError, "Claude plan usage is unavailable"):
            parse_claude_usage({})


if __name__ == "__main__":
    unittest.main()
