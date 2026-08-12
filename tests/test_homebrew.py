import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
FORMULA = ROOT / "Formula" / "runcat-ai-usage.rb"
INSTALLER = ROOT / "scripts" / "install.sh"
TEST_WORKFLOW = ROOT / ".github" / "workflows" / "test.yml"
RELEASE_WORKFLOW = ROOT / ".github" / "workflows" / "release.yml"


class HomebrewInstallationTests(unittest.TestCase):
    def test_formula_runs_background_setup_in_post_install(self):
        content = FORMULA.read_text(encoding="utf-8")
        self.assertIn("def post_install", content)
        self.assertIn('system bin/"runcat-ai-usage-install", "--no-open"', content)

        installer = INSTALLER.read_text(encoding="utf-8")
        self.assertIn('if [ "$OPEN_OUTPUT" = true ]', installer)

    def test_workflows_skip_post_install_during_formula_tests(self):
        for workflow in (TEST_WORKFLOW, RELEASE_WORKFLOW):
            content = workflow.read_text(encoding="utf-8")
            self.assertIn("brew install --skip-post-install", content)

    @unittest.skipUnless(sys.platform == "darwin", "requires macOS")
    def test_no_open_installs_monitor_without_launching_real_agent(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            launchctl = home / "bin" / "launchctl"
            launchctl.parent.mkdir()
            launchctl.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            launchctl.chmod(0o755)

            cache_directory = (
                home / "Library/Application Support/RunCat AI Usage/state/cache"
            )
            cache_directory.mkdir(parents=True)
            now = time.time()
            cache = {
                "attempted_at": now,
                "fetched_at": now,
                "usage": {"percentage": 10},
            }
            for filename in (
                "claude-code.json",
                "codex.json",
                "github-copilot.json",
            ):
                (cache_directory / filename).write_text(
                    json.dumps(cache), encoding="utf-8"
                )

            environment = os.environ.copy()
            environment["HOME"] = str(home)
            environment["PATH"] = "{}:{}".format(
                launchctl.parent, environment["PATH"]
            )
            environment["RUNCAT_AI_USAGE_PYTHON"] = sys.executable
            result = subprocess.run(
                ["sh", str(INSTALLER), "--no-open"],
                env=environment,
                capture_output=True,
                text=True,
                check=False,
                timeout=60,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            app = (
                home / "Library/Application Support/RunCat AI Usage"
                / "RunCat AI Usage Monitor.app"
            )
            executable = app / "Contents/MacOS/RunCat AI Usage Monitor"
            self.assertTrue(executable.is_file())
            output_directory = home / "RunCatMetrics"
            self.assertEqual(
                sorted(path.name for path in output_directory.glob("*.json")),
                [
                    "claude-code.json",
                    "codex.json",
                    "github-copilot.json",
                ],
            )

    def test_installer_rejects_unknown_option_before_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            environment = os.environ.copy()
            environment["HOME"] = directory
            result = subprocess.run(
                ["sh", str(INSTALLER), "--unknown"],
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("Usage:", result.stderr)
            self.assertFalse((Path(directory) / "Library").exists())


if __name__ == "__main__":
    unittest.main()
