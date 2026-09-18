# Source before launching Claude Code, or merge these env entries into its settings.
export CLAUDE_CODE_ENABLE_TELEMETRY=1
export OTEL_METRICS_EXPORTER=otlp
export OTEL_EXPORTER_OTLP_METRICS_ENDPOINT=http://127.0.0.1:4318/v1/metrics
export OTEL_EXPORTER_OTLP_METRICS_PROTOCOL=http/protobuf
export OTEL_METRIC_EXPORT_INTERVAL=60000
# This pipeline only needs metrics, not prompts, responses or tool logs.
export OTEL_LOGS_EXPORTER=none
export OTEL_TRACES_EXPORTER=none
