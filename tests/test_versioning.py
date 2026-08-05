import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "version.py"
SPEC = importlib.util.spec_from_file_location("release_version", SCRIPT)
versioning = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(versioning)


class VersioningTests(unittest.TestCase):
    def test_repository_versions_are_consistent(self):
        self.assertRegex(versioning.package_version(), r"^[0-9]+\.[0-9]+\.[0-9]+$")
        self.assertLessEqual(
            versioning.version_tuple(versioning.formula_version()),
            versioning.version_tuple(versioning.package_version()),
        )

    def test_tag_must_match_package_version(self):
        current = versioning.package_version()
        versioning.command_check_tag("v{}".format(current))
        with self.assertRaisesRegex(versioning.VersionError, "does not match"):
            versioning.command_check_tag("v999.999.999")

    def test_stable_semver_is_required(self):
        self.assertEqual(versioning.require_semver("1.2.3"), "1.2.3")
        for value in ("v1.2.3", "1.2", "1.2.3-beta.1"):
            with self.subTest(value=value):
                with self.assertRaises(versioning.VersionError):
                    versioning.require_semver(value)

    def test_formula_update_changes_release_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            formula = Path(directory) / "formula.rb"
            formula.write_text(
                '  url "old"\n'
                '  version "0.1.0"\n'
                '  sha256 "{}"\n'
                '    assert_match "runcat-ai-usage 0.1.0", output\n'.format("0" * 64),
                encoding="utf-8",
            )
            with mock.patch.object(versioning, "FORMULA_PATH", formula):
                versioning.update_formula("1.2.3", "https://example.test/release.tgz", "a" * 64)
            content = formula.read_text(encoding="utf-8")
            self.assertIn('version "1.2.3"', content)
            self.assertIn('sha256 "{}"'.format("a" * 64), content)
            self.assertIn("runcat-ai-usage 1.2.3", content)

    def test_formula_update_rejects_downgrade(self):
        with tempfile.TemporaryDirectory() as directory:
            formula = Path(directory) / "formula.rb"
            formula.write_text(
                '  url "new"\n'
                '  version "2.0.0"\n'
                '  sha256 "{}"\n'
                '    assert_match "runcat-ai-usage 2.0.0", output\n'.format("0" * 64),
                encoding="utf-8",
            )
            with mock.patch.object(versioning, "FORMULA_PATH", formula):
                with self.assertRaisesRegex(versioning.VersionError, "refusing to downgrade"):
                    versioning.update_formula(
                        "1.9.9", "https://example.test/old.tgz", "a" * 64
                    )
            self.assertIn('version "2.0.0"', formula.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
