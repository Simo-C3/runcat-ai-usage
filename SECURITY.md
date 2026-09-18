# Security

## Credential handling

The monitor reuses credentials already managed by Claude Code, Codex, and
GitHub CLI. It does not copy credentials into its state directory, output
files, or logs.

- Claude Code: macOS Keychain item `Claude Code-credentials`
- Codex: `~/.codex/auth.json`
- GitHub Copilot: the active `gh` authentication

The local cache and SQLite history contain usage amounts and opaque, truncated
SHA-256 credential fingerprints used to keep each Claude sign-in's state
separate, including the OTLP `runcat.profile` resource attribute. They do not contain access tokens, refresh tokens, account names, or
email addresses. RunCat Neo reads only the generated JSON snapshots.

## OpenTelemetry

Listeners bind to loopback. Quota payloads contain utilization, limits, amounts,
fetch status/timestamps and an opaque profile identifier, never provider tokens.
Native agent telemetry can include identifying resource attributes; the Collector
forwards these to configured destinations. Its persistent queues also contain the
forwarded telemetry. The RunCat adapter stores only recognized usage measurements
and hashed native stream identities, not prompts or raw native resource attributes.
Remote export is opt-in through Collector configuration. Use the Collector's
attribute processors when a destination should not receive particular attributes.
Collector exporter credentials are operator-managed, separate from provider tokens.

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting for this repository. Do
not include access tokens, credential files, or complete command output that
may contain secrets.
