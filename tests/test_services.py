import unittest
from pathlib import Path

from services import services


class ServiceCatalogTests(unittest.TestCase):
    def test_catalog_has_unique_keys_and_output_files(self):
        catalog = services(Path("/tmp/example-home"))

        self.assertEqual(len({service.key for service in catalog}), len(catalog))
        self.assertEqual(
            len({service.filename for service in catalog}),
            len(catalog),
        )
        self.assertTrue(all(callable(service.fetcher) for service in catalog))
        self.assertTrue(all(callable(service.state_key) for service in catalog))


if __name__ == "__main__":
    unittest.main()
