# Security

## Credential handling

The monitor reuses credentials already managed by Claude Code, Codex, and
GitHub CLI. It does not copy credentials into its state directory, output
files, or logs.

- Claude Code: macOS Keychain item `Claude Code-credentials`
- Codex: `~/.codex/auth.json`
- GitHub Copilot: the active `gh` authentication

The local cache and SQLite history contain usage amounts and opaque, truncated
SHA-256 credential fingerprints used only to keep each Claude sign-in's state
separate. They do not contain access tokens, refresh tokens, account names, or
email addresses. RunCat Neo reads only the generated JSON snapshots.

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting for this repository. Do
not include access tokens, credential files, or complete command output that
may contain secrets.
