import contextlib
import io
import json
import os
import plistlib
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from app import doctor, main
from diagnostics import LABEL, background_diagnostics
from models import Usage
from services import Service


NOW = 1800000000
STATUS = """state = not running
run interval = 60 seconds
runs = 7
last exit code = 0
"""


class DiagnosticsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name)
        self.output = self.home / "Custom Metrics"
        self.output.mkdir()
        self.agent = self.home / "Library/LaunchAgents" / (LABEL + ".plist")
        self.agent.parent.mkdir(parents=True)
        self.executable = self.home / "monitor"
        self.executable.write_text("#!/bin/sh\nexit 0\n")
        self.executable.chmod(0o755)
        self.agent.write_bytes(plistlib.dumps({
            "Label": LABEL,
            "Program": str(self.executable),
            "ProgramArguments": [str(self.executable), "collect"],
            "StartInterval": 60,
            "RunAtLoad": True,
            "EnvironmentVariables": {"RUNCAT_AI_USAGE_OUTPUT_DIR": str(self.output)},
        }))
        self.service = Service("codex", "codex.json", "Codex", "", lambda: Usage(10), lambda: "codex")
        self.snapshot = self.output / self.service.filename
        self.write_snapshot()
        self.status = STATUS
        self.disabled = '"dev.runcat.ai-usage" => enabled'
        self.launchctl = mock.patch("diagnostics.launchctl", side_effect=self.query).start()
        self.addCleanup(mock.patch.stopall)
        mock.patch("diagnostics.time.time", return_value=NOW).start()
        mock.patch("diagnostics.pipeline_diagnostics", return_value=0).start()

    def query(self, command, target):
        return self.disabled if command == "print-disabled" else self.status

    def write_snapshot(self, fetched=NOW - 30, modified=NOW - 30, available=True):
        self.snapshot.write_text(json.dumps({
            "lastUpdatedDate": datetime.fromtimestamp(fetched, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "metricsBarValue": "10%" if available else "N/A",
            "metrics": [],
        }))
        os.utime(self.snapshot, (modified, modified))

    def diagnose(self, output=None):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            failures = background_diagnostics(self.home, [self.service], output)
        return failures, stdout.getvalue()

    def test_healthy_waiting_agent_uses_installed_output_directory(self):
        before = self.snapshot.stat().st_mtime_ns
        failures, output = self.diagnose()
        self.assertEqual(failures, 0, output)
        self.assertIn("waiting between runs is normal", output)
        self.assertIn(str(self.output), output)
        self.assertNotIn("Recovery:", output)
        self.assertEqual(self.snapshot.stat().st_mtime_ns, before)
        self.assertEqual([call.args[0] for call in self.launchctl.call_args_list], ["print-disabled", "print"])

    def test_missing_installation_reports_reinstall_even_with_recent_json(self):
        self.agent.unlink()
        self.executable.unlink()
        self.launchctl.side_effect = subprocess.CalledProcessError(113, "launchctl")
        failures, output = self.diagnose(self.output)
        self.assertGreater(failures, 0)
        self.assertIn("runcat-ai-usage-install --no-open", output)
        self.assertIn("./scripts/install.sh --no-open", output)
        self.assertIn("RUNCAT_AI_USAGE_OUTPUT_DIR='", output)

    def test_missing_executable_is_installation_failure(self):
        self.executable.unlink()
        failures, output = self.diagnose()
        self.assertGreater(failures, 0)
        self.assertIn("executable is missing", output)

    def test_disabled_agent_is_unhealthy_even_if_registered(self):
        for value in ("disabled", "true"):
            with self.subTest(value=value):
                self.disabled = '"dev.runcat.ai-usage" => ' + value
                failures, output = self.diagnose()
                self.assertGreater(failures, 0)
                self.assertIn("disabled in launchd", output)

    def test_failed_or_never_completed_run_is_unhealthy(self):
        for status in (STATUS.replace("code = 0", "code = 1"), STATUS.replace("runs = 7", "runs = 0"), "state = running"):
            with self.subTest(status=status):
                self.status = status
                failures, output = self.diagnose()
                self.assertGreater(failures, 0)
                self.assertIn("no successful last exit", output)

    def test_schedule_must_be_loaded(self):
        self.status = STATUS.replace("60 seconds", "600 seconds")
        failures, output = self.diagnose()
        self.assertGreater(failures, 0)
        self.assertIn("runcat-ai-usage-install", output)

    def test_stale_json_reports_restart(self):
        self.write_snapshot(modified=NOW - 600)
        failures, output = self.diagnose()
        self.assertEqual(failures, 1, output)
        self.assertIn("launchctl kickstart -k", output)

    def test_freshly_written_stale_or_unavailable_data_is_unhealthy(self):
        for fetched, available in ((NOW - 600, True), (NOW, False), (NOW + 600, True)):
            with self.subTest(fetched=fetched, available=available):
                self.write_snapshot(fetched=fetched, available=available)
                failures, output = self.diagnose()
                self.assertEqual(failures, 1, output)
                self.assertIn("unavailable or stale", output)

    def test_missing_and_corrupt_snapshot_do_not_crash(self):
        self.snapshot.unlink()
        self.assertGreater(self.diagnose()[0], 0)
        for value in ("not json", "[]", '{"lastUpdatedDate": "invalid"}'):
            self.snapshot.write_text(value)
            self.assertGreater(self.diagnose()[0], 0)
        self.snapshot.write_bytes(b"\xff")
        self.assertGreater(self.diagnose()[0], 0)

    def test_invalid_plist_and_launchctl_timeout_do_not_crash(self):
        self.launchctl.side_effect = subprocess.TimeoutExpired("launchctl", 10)
        for value in (b"not plist", plistlib.dumps([]), b'<?xml version="1.0"?><plist><dict>'):
            self.agent.write_bytes(value)
            self.assertGreater(self.diagnose(self.output)[0], 0)

    def test_explicit_output_directory_overrides_installed_directory(self):
        failures, output = self.diagnose(self.home / "Other Metrics")
        self.assertGreater(failures, 0)
        self.assertIn(str(self.home / "Other Metrics"), output)

    def test_doctor_provider_success_cannot_hide_background_failure(self):
        with mock.patch("app.services", return_value=[self.service]), mock.patch("app.background_diagnostics", return_value=1), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(doctor(self.home), 1)

    def test_doctor_succeeds_when_background_and_provider_are_healthy(self):
        with mock.patch("app.services", return_value=[self.service]), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(doctor(self.home), 0)

    def test_doctor_provider_failure_includes_recovery(self):
        service = Service("codex", "codex.json", "Codex", "", mock.Mock(side_effect=ValueError("unauthorized")), lambda: "codex")
        output = io.StringIO()
        with mock.patch("app.services", return_value=[service]), mock.patch("app.background_diagnostics", return_value=0), contextlib.redirect_stdout(output):
            self.assertEqual(doctor(self.home), 1)
        self.assertIn("codex login", output.getvalue())

    def test_main_passes_only_explicit_or_environment_output_override(self):
        with mock.patch("app.doctor", return_value=0) as check, mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(main(["--doctor"]), 0)
            self.assertIsNone(check.call_args.args[1])
            main(["--doctor", "--output-dir", str(self.output)])
            self.assertEqual(check.call_args.args[1], self.output)
            with mock.patch.dict(os.environ, {"RUNCAT_AI_USAGE_OUTPUT_DIR": str(self.output)}):
                main(["--doctor"])
                self.assertEqual(check.call_args.args[1], self.output)


if __name__ == "__main__":
    unittest.main()
