import tempfile
import unittest
from pathlib import Path

from runcat_ai_usage.cache import cached_usage
from runcat_ai_usage.models import Usage


class CacheTests(unittest.TestCase):
    def test_fresh_cache_avoids_provider_request(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cache.json"
            first = cached_usage(path, lambda: Usage(percentage=10), 55, now=100)

            def unexpected_request():
                raise AssertionError("provider should not be called")

            second = cached_usage(path, unexpected_request, 55, now=120)
            self.assertEqual(first.usage, second.usage)
            self.assertIsNone(second.error)

    def test_failed_refresh_keeps_stale_value(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cache.json"
            cached_usage(path, lambda: Usage(percentage=10), 55, now=100)

            def failed_request():
                raise ValueError("temporary failure")

            result = cached_usage(path, failed_request, 55, now=200)
            self.assertEqual(result.usage, Usage(percentage=10))
            self.assertEqual(str(result.error), "temporary failure")


if __name__ == "__main__":
    unittest.main()
