"""Loopback OTLP/HTTP JSON sink for the Collector's otlp_http exporter."""

import json
import sys
import time
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from config import MAX_TREND_PERIOD_SECONDS, load_display_config, trend_period_seconds
from history import HistoryStore
from output import iso_timestamp, snapshot
from services import services
from storage import atomic_write_json
from telemetry_store import TelemetryStore


MAX_REQUEST_BYTES = 8 * 1024 * 1024


def render(home, output_directory, state_directory, now=None):
    now = time.time() if now is None else now
    config = load_display_config(state_directory)
    with TelemetryStore(state_directory) as store, HistoryStore(state_directory / "history.db") as history:
        for service in services(home):
            profile, usage, fetched_at, success = store.quota(service.key)
            history.record(profile, usage, fetched_at)
            summary = (history.summary(profile, now, trend_period_seconds(config.trend_period))
                       if usage is not None and usage.used_amount is not None else None)
            value = snapshot(service.title, service.symbol, usage, fetched_at, summary, config)
            ja = config.language == "ja"
            value["metrics"] = []
            totals = store.totals(service.key, now)
            for kind in config.rows:
                if kind in ("rate", "change", "trend"):
                    value["metrics"].extend(snapshot(service.title, service.symbol, usage,
                        fetched_at, summary, replace(config, rows=(kind,)))["metrics"])
                    continue
                if kind == "remaining" and usage is not None:
                    value["metrics"].append({"title": "残量" if ja else "Remaining",
                        "formattedValue": "{:g}%".format(max(0, 100 - usage.percentage))})
                    continue
                if kind not in totals:
                    continue
                item = totals[kind]
                title = ("トークン 今日 / 1h" if ja else "Tokens today / 1h") if kind == "tokens" else ("推定費用 今日 / 1h" if ja else "Est. cost today / 1h")
                formatted = "{:,.0f} / {:,.0f}" if kind == "tokens" else "${:,.4f} / ${:,.4f}"
                value["metrics"].append({"title": title, "formattedValue": formatted.format(item["today"], item["hour"])})
            if usage is not None and (not success or now - fetched_at > 180):
                value["metrics"].append({"title": "状態" if ja else "Status",
                    "formattedValue": "取得失敗・前回値" if ja else "Stale / last known value"})
            # Native activity must never refresh the quota's timestamp.
            if fetched_at is None:
                value["lastUpdatedDate"] = iso_timestamp(0)
            atomic_write_json(output_directory / service.filename, value)
        history.prune(now - MAX_TREND_PERIOD_SECONDS - 86400)


def make_server(home: Path, output_directory: Path, state_directory: Path, port=4319):
    class Handler(BaseHTTPRequestHandler):
        def reply(self, code, body):
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path != "/health":
                self.reply(404, {})
                return
            with TelemetryStore(state_directory) as store:
                native = {}
                for service in services(home):
                    values = store.totals(service.key, time.time())
                    native[service.key] = max((item["last_received"] for item in values.values()), default=None)
                self.reply(200, dict(store.health(), status="ok", native_last_received=native))

        def do_POST(self):
            if self.path != "/v1/metrics":
                self.reply(404, {})
                return
            if self.headers.get("Content-Type", "").split(";", 1)[0] != "application/json":
                self.reply(415, {"message": "Configure Collector encoding: json"})
                return
            if self.headers.get("Content-Encoding", "identity") != "identity":
                self.reply(415, {"message": "Configure Collector compression: none"})
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= MAX_REQUEST_BYTES:
                    self.reply(413, {})
                    return
                payload = json.loads(self.rfile.read(size))
                with TelemetryStore(state_directory) as store:
                    store.ingest(payload, time.time())
            except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
                self.reply(400, {"message": "Invalid OTLP metrics payload"})
                return
            except Exception as error:
                print("Telemetry storage failed: {}".format(type(error).__name__), file=sys.stderr)
                self.reply(503, {})
                return
            try:
                render(home, output_directory, state_directory)
            except Exception as error:
                print("Snapshot update failed: {}".format(type(error).__name__), file=sys.stderr)
                self.reply(503, {})
                return
            self.reply(200, {})

        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def log_message(self, *_args):
            pass

    return HTTPServer(("127.0.0.1", port), Handler)


def serve(home, output_directory, state_directory, port=4319):
    with make_server(home, output_directory, state_directory, port) as server:
        server.timeout = 1
        last_render = float("-inf")
        try:
            while True:
                if time.monotonic() - last_render >= 60:
                    render(home, output_directory, state_directory)
                    last_render = time.monotonic()
                server.handle_request()
        except KeyboardInterrupt:
            return 0
