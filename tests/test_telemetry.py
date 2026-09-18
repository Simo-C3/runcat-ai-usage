import contextlib
import io
import json
import os
import socket
import subprocess
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

from app import run_once
from cache import CacheResult
from config import DisplayConfig, save_display_config
from diagnostics import pipeline_diagnostics
from models import MonthlyUsage, Usage, UsageWindow
from otlp import attributes, export_metrics, quota_resource
from receiver import make_server, render
from services import services
from telemetry_store import TelemetryStore


ROOT = Path(__file__).resolve().parent.parent


def native_payload(name, value, end, start=0, temporality=2, service="claude-code", tags=None, histogram=False):
    point = {"timeUnixNano": str(int(end * 1e9)), "startTimeUnixNano": str(int(start * 1e9)),
             "attributes": attributes(tags or {})}
    if histogram:
        point.update(sum=value, count="1", bucketCounts=["1"], explicitBounds=[])
    else:
        point["asDouble"] = value
    metric = {"name": name, "histogram" if histogram else "sum": {
        "dataPoints": [point], "aggregationTemporality": temporality}}
    if not histogram:
        metric["sum"]["isMonotonic"] = True
    return {"resourceMetrics": [{"resource": {"attributes": attributes({"service.name": service})},
            "scopeMetrics": [{"scope": {"name": "test"}, "metrics": [metric]}]}]}


class TelemetryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.state = self.root / "state"
        self.output = self.root / "output"
        self.now = time.time()

    def ingest(self, payload):
        with TelemetryStore(self.state) as store:
            store.ingest(payload, self.now)

    def quota(self, usage, fetched=None, error=None, profile="claude-code-a"):
        return {"resourceMetrics": [quota_resource(services(self.root)[0], profile,
                CacheResult(usage, fetched if fetched is not None else self.now - 1, error), self.now)]}

    def test_plan_round_trip_preserves_windows_monthly_amounts_and_timestamp(self):
        usage = Usage(60, windows=(UsageWindow("five_hour", 60), UsageWindow("seven_day", 25)),
                      monthly=MonthlyUsage(True, 20, 2, 10, "USD", 2))
        self.ingest(self.quota(usage))
        with TelemetryStore(self.state) as store:
            profile, actual, fetched, ok = store.quota("claude-code")
        self.assertEqual(actual, usage)
        self.assertTrue(ok)
        self.assertEqual(profile, "claude-code-a")
        self.assertAlmostEqual(fetched, self.now - 1, places=5)
        names = [m["name"] for m in self.quota(usage)["resourceMetrics"][0]["scopeMetrics"][0]["metrics"]]
        self.assertIn("runcat.ai.plan.remaining_percent", names)
        self.assertIn("runcat.ai.plan.remaining", names)

    def test_failed_fetch_keeps_last_value_and_stale_timestamp(self):
        fetched = self.now - 600
        self.ingest(self.quota(Usage(40), fetched, ValueError("offline")))
        render(self.root, self.output, self.state, self.now)
        before = json.loads((self.output / "claude-code.json").read_text())
        self.ingest(native_payload("claude_code.token.usage", 123, self.now))
        render(self.root, self.output, self.state, self.now)
        after = json.loads((self.output / "claude-code.json").read_text())
        self.assertEqual(after["lastUpdatedDate"], before["lastUpdatedDate"])
        self.assertEqual(after["metricsBarValue"], "40%")
        self.assertTrue(any("Stale" in row["formattedValue"] for row in after["metrics"]))
        self.assertTrue(any("Tokens" in row["title"] for row in after["metrics"]))

    def test_profile_switch_and_old_replay_do_not_restore_previous_account(self):
        old = self.quota(Usage(80), profile="claude-code-old")
        self.ingest(old)
        self.now += 1
        self.ingest(self.quota(Usage(10), profile="claude-code-new"))
        self.ingest(old)
        with TelemetryStore(self.state) as store:
            profile, usage, _, _ = store.quota("claude-code")
        self.assertEqual(profile, "claude-code-new")
        self.assertEqual(usage.percentage, 10)

    def test_missing_credentials_preserve_stale_value_but_new_account_does_not(self):
        self.ingest(self.quota(Usage(80)))
        self.now += 1
        self.ingest(self.quota(None, error=ValueError("no credentials"), profile="claude-code"))
        with TelemetryStore(self.state) as store:
            _, usage, _, success = store.quota("claude-code")
            self.assertEqual(usage.percentage, 80)
            self.assertFalse(success)
        self.now += 1
        self.ingest(self.quota(None, error=ValueError("API failure"), profile="claude-code-new"))
        with TelemetryStore(self.state) as store:
            self.assertIsNone(store.quota("claude-code")[1])

    def test_cumulative_duplicates_resets_and_out_of_order_across_restarts(self):
        for value, offset, start in ((100, -30, -60), (100, -30, -60), (160, -20, -60),
                                     (120, -25, -60), (10, -10, -15)):
            self.ingest(native_payload("claude_code.token.usage", value, self.now + offset, self.now + start))
        with TelemetryStore(self.state) as store:
            self.assertEqual(store.totals("claude-code", self.now)["tokens"]["hour"], 170)

    def test_delta_histograms_deduplicate_and_sum_out_of_order(self):
        for value, offset in ((25, -10), (30, -20), (25, -10)):
            self.ingest(native_payload("gen_ai.client.token.usage", value, self.now + offset,
                temporality=1, service="copilot-chat", tags={"gen_ai.token.type": "input"}, histogram=True))
        with TelemetryStore(self.state) as store:
            self.assertEqual(store.totals("github-copilot", self.now)["tokens"]["hour"], 55)

    def test_concurrent_cumulative_streams_are_separated_by_start_time(self):
        for value, end, start in ((100, -30, -60), (200, -25, -50), (110, -20, -60), (220, -10, -50)):
            self.ingest(native_payload("claude_code.token.usage", value, self.now + end, self.now + start))
        with TelemetryStore(self.state) as store:
            self.assertEqual(store.totals("claude-code", self.now)["tokens"]["hour"], 330)

    def test_native_only_output_honors_row_order_without_inventing_quota(self):
        save_display_config(self.state, DisplayConfig(rows=("cost", "tokens", "rate")))
        self.ingest(native_payload("claude_code.token.usage", 90, self.now))
        self.ingest(native_payload("claude_code.cost.usage", .25, self.now))
        render(self.root, self.output, self.state, self.now)
        value = json.loads((self.output / "claude-code.json").read_text())
        self.assertEqual(value["metricsBarValue"], "N/A")
        self.assertEqual([row["title"] for row in value["metrics"]],
                         ["Est. cost today / 1h", "Tokens today / 1h", "Rate"])

    def test_export_rejects_partial_success(self):
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.status = 200
        response.read.return_value = b'{"partialSuccess":{"rejectedDataPoints":"1"}}'
        with mock.patch("otlp.urllib.request.urlopen", return_value=response), mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "rejected"):
                export_metrics({"resourceMetrics": []})

    def test_unsupported_temporality_and_no_recorded_value(self):
        payload = native_payload("claude_code.token.usage", 90, self.now, temporality=0)
        with self.assertRaises(ValueError):
            self.ingest(payload)
        payload["resourceMetrics"][0]["scopeMetrics"][0]["metrics"][0]["sum"]["dataPoints"][0]["flags"] = 1
        self.ingest(payload)
        with TelemetryStore(self.state) as store:
            self.assertEqual(store.totals("claude-code", self.now), {})

    def test_codex_does_not_double_count_total_cache_or_reasoning(self):
        for token_type, value in (("input", 100), ("output", 20), ("total", 120),
                                  ("cached_input", 80), ("reasoning_output", 10)):
            self.ingest(native_payload("turn.token_usage", value, self.now, service="codex_cli_rs",
                        tags={"token_type": token_type}, histogram=True))
        with TelemetryStore(self.state) as store:
            self.assertEqual(store.totals("codex", self.now)["tokens"]["hour"], 120)

    def test_invalid_payload_rolls_back_and_unknown_metrics_are_ignored(self):
        payload = native_payload("claude_code.token.usage", float("nan"), self.now)
        with self.assertRaises(ValueError):
            self.ingest(payload)
        self.ingest(native_payload("unknown.metric", 9000, self.now))
        with TelemetryStore(self.state) as store:
            self.assertEqual(store.totals("claude-code", self.now), {})

    def test_producer_only_exports_otlp_and_failure_is_nonzero(self):
        catalog = services(self.root)
        catalog[0] = type(catalog[0])("claude-code", "claude-code.json", "Claude Code", "star", lambda: Usage(5), lambda: "claude-code")
        with mock.patch("app.services", return_value=catalog[:1]), mock.patch("app.export_metrics") as export:
            self.assertEqual(run_once(self.root, self.state, 55), 0)
            self.assertIn("resourceMetrics", export.call_args.args[0])
            export.side_effect = OSError("unreachable")
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(run_once(self.root, self.state, 55), 1)
        self.assertFalse(self.output.exists())

    def test_receiver_http_contract_and_success_response(self):
        server = make_server(self.root, self.output, self.state, 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            endpoint = "http://127.0.0.1:{}/v1/metrics".format(server.server_port)
            with mock.patch.dict(os.environ, {}, clear=True):
                export_metrics(self.quota(Usage(42)), endpoint)
            self.assertEqual(json.loads((self.output / "claude-code.json").read_text())["metricsBarValue"], "42%")
            request = urllib.request.Request(endpoint, data=b"protobuf", headers={"Content-Type": "application/x-protobuf"})
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(request)
            self.assertEqual(error.exception.code, 415)
            error.exception.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_doctor_distinguishes_delivery_from_native_idle(self):
        def response(url, timeout):
            return mock.MagicMock(__enter__=lambda _self: mock.Mock(status=200,
                read=lambda: json.dumps({"received_at": self.now, "status": "ok"}).encode()))
        with mock.patch("diagnostics.launchctl", return_value="state = running"), mock.patch("diagnostics.urllib.request.urlopen", side_effect=response), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(pipeline_diagnostics("gui/123"), 0)


@unittest.skipUnless(os.environ.get("RUNCAT_TEST_COLLECTOR"), "set RUNCAT_TEST_COLLECTOR for real Collector integration")
class CollectorIntegrationTests(unittest.TestCase):
    def test_collector_fans_out_quota_and_native_metrics_to_two_sinks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            servers = [make_server(root, root / str(i) / "output", root / str(i) / "state", 0) for i in range(2)]
            threads = [threading.Thread(target=s.serve_forever, daemon=True) for s in servers]
            for thread in threads:
                thread.start()
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            config = {
                "receivers": {"otlp": {"protocols": {"http": {"endpoint": "127.0.0.1:{}".format(port)}}}},
                "processors": {"batch": {"timeout": "100ms"}},
                "exporters": {"otlp_http/sink{}".format(i): {"endpoint": "http://127.0.0.1:{}".format(s.server_port), "encoding": "json", "compression": "none"} for i, s in enumerate(servers)},
                "service": {"pipelines": {"metrics": {"receivers": ["otlp"], "processors": ["batch"], "exporters": ["otlp_http/sink0", "otlp_http/sink1"]}}},
            }
            path = root / "collector.json"
            path.write_text(json.dumps(config))
            with (root / "collector.log").open("w+") as log:
                process = subprocess.Popen([os.environ["RUNCAT_TEST_COLLECTOR"], "--config", str(path)], stdout=log, stderr=log)
                try:
                    deadline = time.monotonic() + 15
                    while True:
                        try:
                            with socket.create_connection(("127.0.0.1", port), timeout=.2):
                                break
                        except OSError:
                            if time.monotonic() >= deadline or process.poll() is not None:
                                log.seek(0)
                                self.fail(log.read())
                            time.sleep(.05)
                    now = time.time()
                    resource = quota_resource(services(root)[0], "claude-code", CacheResult(Usage(37), now, None), now)
                    payload = native_payload("claude_code.token.usage", 321, now)
                    payload["resourceMetrics"].append(resource)
                    with mock.patch.dict(os.environ, {}, clear=True):
                        export_metrics(payload, "http://127.0.0.1:{}/v1/metrics".format(port))
                    for i in range(2):
                        output = root / str(i) / "output/claude-code.json"
                        while not output.exists():
                            if time.monotonic() >= deadline:
                                log.seek(0)
                                self.fail(log.read())
                            time.sleep(.05)
                        value = json.loads(output.read_text())
                        self.assertEqual(value["metricsBarValue"], "37%")
                        self.assertTrue(any("321" in row["formattedValue"] for row in value["metrics"]))
                finally:
                    process.terminate()
                    process.wait(timeout=10)
                    for server, thread in zip(servers, threads):
                        server.shutdown()
                        server.server_close()
                        thread.join()
