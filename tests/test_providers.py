import unittest

from providers import (
    ProviderError,
    claude_profile_key,
    parse_claude_usage,
    parse_codex_usage,
    parse_copilot_usage,
)


class ProviderParsingTests(unittest.TestCase):
    def test_claude_profile_key_uses_account_identifier_when_available(self):
        first = claude_profile_key(
            {
                "claudeAiOauth": {
                    "accessToken": "first-access-token",
                    "refreshToken": "first-refresh-token",
                    "accountUuid": "account-a",
                }
            }
        )
        refreshed = claude_profile_key(
            {
                "claudeAiOauth": {
                    "accessToken": "second-access-token",
                    "refreshToken": "second-refresh-token",
                    "accountUuid": "account-a",
                }
            }
        )
        other_account = claude_profile_key(
            {
                "claudeAiOauth": {
                    "accessToken": "third-access-token",
                    "refreshToken": "third-refresh-token",
                    "accountUuid": "account-b",
                }
            }
        )
        other_organization = claude_profile_key(
            {
                "claudeAiOauth": {
                    "accessToken": "fourth-access-token",
                    "refreshToken": "fourth-refresh-token",
                    "accountUuid": "account-a",
                    "organizationUuid": "organization-b",
                }
            }
        )

        self.assertEqual(first, refreshed)
        self.assertNotEqual(first, other_account)
        self.assertNotEqual(first, other_organization)
        self.assertEqual(len(first), 16)
        self.assertNotIn("account-a", first)

    def test_claude_profile_key_falls_back_to_a_credential_fingerprint(self):
        first = claude_profile_key({"accessToken": "license-one"})
        second = claude_profile_key({"accessToken": "license-two"})

        self.assertNotEqual(first, second)

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

    def test_codex_ignores_malformed_optional_sections(self):
        usage = parse_codex_usage(
            {
                "spend_control": [],
                "rate_limit": {"primary": {"used_percent": 18}},
            }
        )
        self.assertEqual(usage.percentage, 18)

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

    def test_malformed_copilot_quota_raises_provider_error(self):
        with self.assertRaisesRegex(
            ProviderError,
            "GitHub Copilot plan usage is unavailable",
        ):
            parse_copilot_usage({"quota_snapshots": []})


if __name__ == "__main__":
    unittest.main()
