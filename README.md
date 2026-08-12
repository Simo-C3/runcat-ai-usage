# RunCat AI Usage

[![Test](https://github.com/Simo-C3/runcat-ai-usage/actions/workflows/test.yml/badge.svg)](https://github.com/Simo-C3/runcat-ai-usage/actions/workflows/test.yml)
[![Release](https://img.shields.io/github/v/release/Simo-C3/runcat-ai-usage)](https://github.com/Simo-C3/runcat-ai-usage/releases)

Display Claude Code, Codex, and GitHub Copilot plan usage in
[RunCat Neo](https://github.com/runcat-dev/RunCatNeo).

```text
Claude Code
Rate:       0.3% · $2.68 / $1,000.00
Today / 1h: $0.14 / $0.03
7d Trend:   ···▁▂▅█

GitHub Copilot
Rate:       14.1% · 6,972 / 50,000 AIC
Today / 1h: 145 / 12 AIC
7d Trend:   ▁▂▃▅▆▇█
```

The monitor refreshes every minute, writes
[Custom Metrics JSON](https://github.com/runcat-dev/RunCatNeo/blob/main/docs/CustomMetricsSchema.md),
and keeps 40 days of local usage history. No Python packages are required.

[日本語](README.ja.md)

## Requirements

- macOS 13 or later
- RunCat Neo with Custom Metrics support
- The provider CLIs you want to monitor:
  - Claude Code, signed in
  - Codex, signed in
  - [GitHub CLI](https://cli.github.com/) with an account that has GitHub Copilot

Providers can be used independently. A missing login appears as `Unavailable`
and does not prevent the other cards from updating.

The Homebrew installation manages Python automatically. A manual installation
additionally requires `/usr/bin/python3`.

## Install with Homebrew (recommended)

```sh
brew tap Simo-C3/runcat-ai-usage https://github.com/Simo-C3/runcat-ai-usage
brew trust --formula Simo-C3/runcat-ai-usage/runcat-ai-usage
brew install runcat-ai-usage
runcat-ai-usage-install
```

The `brew trust` command grants trust to this Formula only, not to every
current or future Formula in the tap.

To upgrade:

```sh
brew update
brew upgrade runcat-ai-usage
runcat-ai-usage-install
```

The final command installs or updates the named background app, starts its
one-minute LaunchAgent, generates the initial snapshots, and opens
`~/RunCatMetrics`. Existing history is preserved.

## Install manually

```sh
git clone https://github.com/Simo-C3/runcat-ai-usage.git
cd runcat-ai-usage
./scripts/install.sh
```

The installer:

1. Creates a self-contained **RunCat AI Usage Monitor** app under
   `~/Library/Application Support/RunCat AI Usage/`.
2. Registers a one-minute LaunchAgent named `dev.runcat.ai-usage`.
3. Generates snapshots in `~/RunCatMetrics` and opens that directory.
4. Migrates history from the earlier `~/.copilot/runcat-usage-history.db`
   installation when present.

In RunCat Neo, open **Settings → Metrics → Custom Metrics**, select
**Add Custom Metrics Source**, and add:

- `~/RunCatMetrics/claude-code.json`
- `~/RunCatMetrics/codex.json`
- `~/RunCatMetrics/github-copilot.json`

This file selection is the only required RunCat GUI setup. Optionally enable
each source in the Metrics Bar to show its current rate in the menu bar.

Re-run `./scripts/install.sh` to update a manual installation.

## What each value means

| Row | Meaning |
| --- | --- |
| **Rate** | Current plan utilization and, when available, used / limit |
| **Today / 1h** | Counter increase since local midnight / over the last 60 minutes |
| **7d Trend** | One character per local calendar day, oldest to newest; `·` means no recorded sample |

History starts when the monitor is installed; earlier usage cannot be
reconstructed. Today and trend rows require an absolute usage counter from the
provider.

Provider plans expose different values:

| Provider | Value used |
| --- | --- |
| Claude Code | Higher of the 5-hour and 7-day utilization windows; Enterprise accounts without those windows use the monthly extra-usage budget |
| Codex | Workspace individual spend control; if absent, the higher available rolling utilization |
| GitHub Copilot | Monthly premium request (AI Credit) quota |

## Commands

Show the persistent display settings:

```sh
runcat-ai-usage config show
```

Change the visible rows, their order, Rate format, percentage precision, and
label language:

```sh
runcat-ai-usage config set \
  --rows rate,change,trend \
  --rate-format full \
  --percentage-precision 1 \
  --language en
```

- `--rows` accepts `rate`, `change`, and `trend` in any order.
- `--rate-format percentage` hides the absolute used / limit values.
- `--percentage-precision` accepts `0` through `3`.
- `--language` accepts `en` or `ja` for metric row labels.

Settings are saved in the state directory and take effect on the next monitor
update. Restore the original display with:

```sh
runcat-ai-usage config reset
```

For a manual installation, replace `runcat-ai-usage` in these examples with
the full monitor app executable path shown below.

Check credentials and provider responses without printing secrets:

```sh
runcat-ai-usage --doctor
```

For a manual installation:

```sh
"$HOME/Library/Application Support/RunCat AI Usage/RunCat AI Usage Monitor.app/Contents/MacOS/RunCat AI Usage Monitor" --doctor
```

Run an immediate update:

```sh
launchctl kickstart -k "gui/$(id -u)/dev.runcat.ai-usage"
```

Use a different snapshot directory during installation:

```sh
RUNCAT_AI_USAGE_OUTPUT_DIR="$HOME/MyMetrics" runcat-ai-usage-install
```

## Troubleshooting

Inspect the monitor without exposing credentials:

```sh
tail -n 50 "$HOME/Library/Logs/RunCat AI Usage/monitor.error.log"
launchctl print "gui/$(id -u)/dev.runcat.ai-usage"
```

- **Claude Code unavailable:** sign in with Claude Code once. The first
  background Keychain access may require macOS approval.
- **Codex unavailable:** sign in with Codex and confirm `~/.codex/auth.json`
  exists.
- **GitHub Copilot unavailable:** install `gh`, run `gh auth login`, and
  confirm the active account has a Copilot entitlement.
- **Old values:** provider APIs may cache or delay usage. The monitor polls
  once per minute and keeps the last successful value during temporary errors.
- **No Today or trend row:** the account endpoint exposed only a percentage,
  not an absolute counter.

## Uninstall

Homebrew:

```sh
runcat-ai-usage-uninstall
brew uninstall runcat-ai-usage
brew untrust --formula Simo-C3/runcat-ai-usage/runcat-ai-usage
brew untap Simo-C3/runcat-ai-usage
```

Manual installation:

```sh
./scripts/uninstall.sh
```

Both methods keep history and snapshots by default. To remove them as well,
pass `--purge` to the uninstall command before uninstalling the Formula:

```sh
runcat-ai-usage-uninstall --purge
# or: ./scripts/uninstall.sh --purge
```

Remove the three Custom Metrics sources from RunCat Neo separately.

## Privacy and API stability

All processing and history storage are local. Credentials are read only at
request time and are never written by this project. See [SECURITY.md](SECURITY.md).

Claude and Codex usage endpoints and GitHub's Copilot endpoint are not stable
public APIs. Provider updates may require changes to this project.

This project is not affiliated with RunCat Neo, Anthropic, OpenAI, or GitHub.

## Development

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -v
sh -n scripts/install.sh
sh -n scripts/uninstall.sh
brew style Formula/runcat-ai-usage.rb
```

The project intentionally uses only the Python standard library.
Releases are automated from SemVer tags; see [RELEASING.md](RELEASING.md).

## License

[MIT](LICENSE)
