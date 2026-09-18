# Source in the shell that launches a current Copilot CLI.
export COPILOT_OTEL_ENABLED=true
export OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4318
export OTEL_EXPORTER_OTLP_METRICS_ENDPOINT=http://127.0.0.1:4318/v1/metrics
export OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
export OTEL_EXPORTER_OTLP_METRICS_PROTOCOL=http/protobuf
export COPILOT_OTEL_CAPTURE_CONTENT=false
export OTEL_LOGS_EXPORTER=none
export OTEL_TRACES_EXPORTER=none
