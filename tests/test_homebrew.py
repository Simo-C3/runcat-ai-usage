import json
import os
import plistlib
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
            collector = home / "bin/otelcol-contrib"
            collector.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            collector.chmod(0o755)

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
            environment["RUNCAT_AI_USAGE_COLLECTOR"] = str(collector)
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
            agents = home / "Library/LaunchAgents"
            for suffix in ("", ".collector", ".receiver"):
                agent = plistlib.loads((agents / ("dev.runcat.ai-usage" + suffix + ".plist")).read_bytes())
                if suffix:
                    self.assertTrue(agent["KeepAlive"])
                    self.assertNotIn("StartInterval", agent)
                else:
                    self.assertEqual(agent["StartInterval"], 60)
                    self.assertEqual(agent["ProgramArguments"][-1], "collect")
            self.assertTrue((home / "Library/Application Support/RunCat AI Usage/otel/collector.yaml").exists())
            # Mocked launchd does not run the pipeline; setup must not bypass OTLP.
            self.assertFalse(list((home / "RunCatMetrics").glob("*.json")))

            # Reinstalling preserves operator routing, credentials and the selected paths.
            config = home / "Library/Application Support/RunCat AI Usage/otel/collector.yaml"
            config.write_text(config.read_text() + "\n# operator routing\n")
            monitor_path = agents / "dev.runcat.ai-usage.plist"
            monitor = plistlib.loads(monitor_path.read_bytes())
            monitor["EnvironmentVariables"]["RUNCAT_AI_USAGE_OUTPUT_DIR"] = str(home / "Custom Metrics")
            monitor_path.write_bytes(plistlib.dumps(monitor))
            collector_path = agents / "dev.runcat.ai-usage.collector.plist"
            collector_agent = plistlib.loads(collector_path.read_bytes())
            collector_agent["EnvironmentVariables"]["RUNCAT_REMOTE_OTLP_ENDPOINT"] = "https://example.invalid"
            collector_path.write_bytes(plistlib.dumps(collector_agent))
            again = subprocess.run(["sh", str(INSTALLER), "--no-open"], env=environment,
                                   capture_output=True, text=True, timeout=60)
            self.assertEqual(again.returncode, 0, again.stderr)
            self.assertIn("# operator routing", config.read_text())
            monitor = plistlib.loads(monitor_path.read_bytes())
            self.assertEqual(monitor["EnvironmentVariables"]["RUNCAT_AI_USAGE_OUTPUT_DIR"], str(home / "Custom Metrics"))
            collector_agent = plistlib.loads(collector_path.read_bytes())
            self.assertEqual(collector_agent["EnvironmentVariables"]["RUNCAT_REMOTE_OTLP_ENDPOINT"], "https://example.invalid")

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
