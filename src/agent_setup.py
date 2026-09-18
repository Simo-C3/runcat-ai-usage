"""Opt-in native telemetry setup. Never inspect credentials or start an agent on setup."""
import argparse
import json
import os
import re
import shlex
import shutil
import stat
import sys
import tempfile
from pathlib import Path

AGENTS = ("claude", "codex", "copilot", "vscode")
BASE = "http://127.0.0.1:4318"
METRICS = BASE + "/v1/metrics"
CLAUDE_ENV = {
    "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
    "OTEL_METRICS_EXPORTER": "otlp",
    "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT": METRICS,
    "OTEL_EXPORTER_OTLP_METRICS_PROTOCOL": "http/protobuf",
    "OTEL_METRIC_EXPORT_INTERVAL": "60000",
    "OTEL_LOGS_EXPORTER": "none",
    "OTEL_TRACES_EXPORTER": "none",
}
COPILOT_ENV = {
    "COPILOT_OTEL_ENABLED": "true",
    "OTEL_EXPORTER_OTLP_ENDPOINT": BASE,
    "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT": METRICS,
    "OTEL_EXPORTER_OTLP_PROTOCOL": "http/protobuf",
    "OTEL_EXPORTER_OTLP_METRICS_PROTOCOL": "http/protobuf",
    "COPILOT_OTEL_CAPTURE_CONTENT": "false",
    "OTEL_LOGS_EXPORTER": "none",
    "OTEL_TRACES_EXPORTER": "none",
}
VSCODE_SETTINGS = {
    "github.copilot.chat.otel.enabled": True,
    "github.copilot.chat.otel.exporterType": "otlp-http",
    "github.copilot.chat.otel.otlpEndpoint": BASE,
    "github.copilot.chat.otel.captureContent": False,
}
CODEX_OVERRIDE = 'otel.metrics_exporter={otlp-http={endpoint="' + METRICS + '",protocol="binary"}}'
CODEX_TABLE = ('[otel.metrics_exporter.otlp-http]\n'
               'endpoint = "' + METRICS + '"\nprotocol = "binary"\n')


class SetupError(ValueError):
    pass


def add_parser(commands):
    parser = commands.add_parser("agents", help="configure native agent OpenTelemetry")
    actions = parser.add_subparsers(dest="agent_action", required=True)
    for action in ("setup", "status"):
        command = actions.add_parser(action, help=("apply settings with backups" if action == "setup"
                                                   else "check local settings (not delivery)"))
        command.add_argument("agent", choices=("all",) + AGENTS, nargs="?", default="all")
        command.add_argument("--config-path", type=Path, help="custom settings path (one agent only; not Copilot CLI)")
        if action == "setup":
            command.add_argument("--dry-run", action="store_true", help="report changes without writing")
    run = actions.add_parser("run", help="launch a CLI with telemetry enabled, without changing settings")
    run.add_argument("agent", choices=AGENTS[:3])
    run.add_argument("agent_args", nargs=argparse.REMAINDER, help="arguments after -- are passed to the agent")


def config_path(home, agent):
    if agent == "claude":
        return Path(os.environ.get("CLAUDE_CONFIG_DIR", str(home / ".claude"))).expanduser() / "settings.json"
    if agent == "codex":
        return Path(os.environ.get("CODEX_HOME", str(home / ".codex"))).expanduser() / "config.toml"
    if agent == "copilot":
        return home / ".local" / "bin" / "runcat-copilot"
    return home / "Library" / "Application Support" / "Code" / "User" / "settings.json"


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise SetupError("Duplicate JSON keys; resolve them before setup.")
        result[key] = value
    return result


def json_document(text, comments=False):
    """Mask JSONC comments/commas without changing offsets used for surgical edits."""
    masked = text
    if comments:
        pattern = r'"(?:\\.|[^"\\])*"|//[^\r\n]*|/\*[\s\S]*?\*/'
        masked = re.sub(pattern, lambda m: (m[0] if m[0].startswith('"') else
                                            re.sub(r'[^\r\n]', ' ', m[0])), text)
        masked = re.sub(r'"(?:\\.|[^"\\])*"|,(?=\s*[}\]])',
                        lambda m: ' ' if m[0] == ',' else m[0], masked)
    try:
        data = json.loads(masked, object_pairs_hook=unique_object)
    except (ValueError, RecursionError):
        raise SetupError("Invalid or duplicate-key JSON settings; no changes made.") from None
    if not isinstance(data, dict):
        raise SetupError("Settings must be a JSON object.")
    return data, masked


def merge_jsonc(text, desired):
    data, masked = json_document(text, comments=True)
    decoder = json.JSONDecoder()
    pos = masked.index('{') + 1
    edits = []
    present = set()
    last_value_end = None
    while True:
        while masked[pos].isspace() or masked[pos] == ',':
            pos += 1
        if masked[pos] == '}':
            closing = pos
            break
        key, pos = decoder.raw_decode(masked, pos)
        while masked[pos].isspace() or masked[pos] == ':':
            pos += 1
        start = pos
        value, pos = decoder.raw_decode(masked, pos)
        last_value_end = pos
        present.add(key)
        if key in desired and (value != desired[key] or type(value) is not type(desired[key])):
            edits.append((start, pos, json.dumps(desired[key])))
    missing = {k: v for k, v in desired.items() if k not in present}
    if missing:
        # Insert after the last value, before comments and an existing trailing comma.
        if data:
            insertion = last_value_end
            prefix = ','
        else:
            insertion = closing
            prefix = ''
        added = ',\n'.join('  {}: {}'.format(json.dumps(k), json.dumps(v)) for k, v in missing.items())
        edits.append((insertion, insertion, prefix + '\n' + added + '\n'))
    for start, end, value in sorted(edits, reverse=True):
        text = text[:start] + value + text[end:]
    json_document(text, comments=True)
    return text


# Strings (including multiline strings) are atomic; brackets and comments inside them
# cannot accidentally look like a table boundary. Unsupported structures fail closed.
TOML_TOKEN = re.compile(r'"""[\s\S]*?(?<!\\)"""|\'\'\'[\s\S]*?\'\'\'|"(?:\\.|[^"\\\n])*"|\'[^\'\n]*\'|#[^\n]*|[^"\'#]', re.MULTILINE)
KEY = re.compile(r'\s*([A-Za-z0-9_-]+|"(?:\\.|[^"\\])*"|\'[^\']*\')\s*(\.|$)')


def key_parts(value):
    if not value.strip():
        raise SetupError("Empty TOML key.")
    parts = []
    pos = 0
    while pos < len(value):
        match = KEY.match(value, pos)
        if not match:
            raise SetupError("Unsupported TOML key syntax; use agents run codex instead.")
        key = match[1]
        if key.startswith('"'):
            try:
                key = json.loads(key)
            except ValueError:
                raise SetupError("Unsupported TOML key escape; use agents run codex instead.") from None
        elif key.startswith("'"):
            key = key[1:-1]
        parts.append(key)
        pos = match.end()
        if match[2] == '.' and pos == len(value):
            raise SetupError("Invalid TOML key.")
    return tuple(parts)


def toml_statements(text):
    start, end = 0, 0
    brackets = []
    clean = []
    for match in TOML_TOKEN.finditer(text):
        if match.start() != end:
            raise SetupError("Unsupported TOML string; use agents run codex instead.")
        token = match[0]
        end = match.end()
        if token.startswith('#'):
            continue
        clean.append(token)
        if token in ('[', '{'):
            brackets.append(token)
        elif token in (']', '}'):
            if not brackets or brackets.pop() != {']': '[', '}': '{'}[token]:
                raise SetupError("Unbalanced TOML settings.")
        if token == '\n' and not brackets:
            yield text[start:end], ''.join(clean).strip()
            start, clean = end, []
    if end != len(text) or brackets:
        raise SetupError("Incomplete TOML settings.")
    if start < len(text):
        yield text[start:], ''.join(clean).strip()


def merge_codex(text):
    """Replace only the metrics exporter; leave logs, traces and all other tables intact."""
    section = ()
    kept = []
    target = ('otel', 'metrics_exporter')
    for original, statement in toml_statements(text):
        if not statement:
            kept.append(original)
            continue
        if statement.startswith('['):
            array = statement.startswith('[[')
            trim = 2 if array else 1
            if not statement.endswith(']' * trim):
                raise SetupError("Invalid TOML table header.")
            section = key_parts(statement[trim:-trim])
            if array and section == ('otel',):
                raise SetupError("otel must be a table, not an array of tables.")
            if section[:2] == target:
                if array:
                    raise SetupError("Invalid metrics exporter table; use agents run codex instead.")
                continue
        else:
            # '=' inside quoted keys is legal: locate only unquoted assignment delimiters.
            tokens = list(TOML_TOKEN.finditer(statement))
            delimiter = next((m.start() for m in tokens if m[0] == '='), None)
            if delimiter is None:
                raise SetupError("Unsupported TOML statement; use agents run codex instead.")
            path = section + key_parts(statement[:delimiter].strip())
            if path == ('otel',):
                raise SetupError("Inline otel tables are preserved; use agents run codex instead.")
            if path[:2] == target:
                continue
        kept.append(original)
    prefix = ''.join(kept).rstrip()
    result = (prefix + '\n\n' if prefix else '') + CODEX_TABLE
    # Python 3.9 has no TOML library. On newer versions also validate the whole document.
    try:
        import tomllib
    except ImportError:
        pass
    else:
        try:
            tomllib.loads(text)
            tomllib.loads(result)
        except ValueError:
            raise SetupError("Invalid or unsupported TOML settings; use agents run codex instead.") from None
    return result


def copilot_launcher():
    lines = ['#!/bin/sh', '# Managed by runcat-ai-usage agents setup copilot.']
    lines.extend('export {}={}'.format(key, shlex.quote(value)) for key, value in COPILOT_ENV.items())
    lines.append('exec copilot "$@"')
    return '\n'.join(lines) + '\n'


def desired_text(agent, original):
    if agent == 'claude':
        data, _ = json_document(original or '{}')
        env = data.setdefault('env', {})
        if not isinstance(env, dict):
            raise SetupError("Claude settings.env must be an object.")
        if all(env.get(k) == v for k, v in CLAUDE_ENV.items()):
            return original
        env.update(CLAUDE_ENV)
        return json.dumps(data, ensure_ascii=False, indent=2) + '\n'
    if agent == 'codex':
        return merge_codex(original)
    if agent == 'vscode':
        return merge_jsonc(original or '{}\n', VSCODE_SETTINGS)
    return copilot_launcher()


def write_settings(path, original, updated, executable=False):
    """Back up original bytes, then replace atomically; don't follow symlinks."""
    if path.is_symlink():
        raise SetupError("Symlink settings are not replaced; pass --config-path with the real file.")
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = None
    if path.exists():
        if path.read_bytes() != original.encode('utf-8'):
            raise SetupError("Settings changed during setup; retry.")
        descriptor, backup_name = tempfile.mkstemp(prefix=path.name + '.runcat-backup-', dir=str(path.parent))
        backup = Path(backup_name)
        with os.fdopen(descriptor, 'wb') as output:
            output.write(original.encode('utf-8'))
    descriptor, temp_name = tempfile.mkstemp(prefix='.runcat-', dir=str(path.parent))
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8', newline='') as output:
            output.write(updated)
        mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o600
        os.chmod(temp_name, (mode | 0o700) if executable else mode)
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    return backup


def run_agent(agent, arguments):
    executable = shutil.which(agent)
    if executable is None:
        raise SetupError("{} is not installed or is not on PATH.".format(agent))
    env = os.environ.copy()
    if agent == 'claude':
        env.update(CLAUDE_ENV)
    elif agent == 'copilot':
        env.update(COPILOT_ENV)
    arguments = list(arguments)
    if arguments[:1] == ['--']:
        arguments = arguments[1:]
    if agent == 'codex':
        arguments = ['-c', CODEX_OVERRIDE] + arguments
    os.execve(executable, [executable] + arguments, env)
    return 0


def execute(arguments, home):
    try:
        if arguments.agent_action == 'run':
            return run_agent(arguments.agent, arguments.agent_args)
        custom = arguments.config_path
        if custom and arguments.agent in ('all', 'copilot'):
            raise SetupError("--config-path requires one of claude, codex, vscode.")
        agents = AGENTS if arguments.agent == 'all' else (arguments.agent,)
        failures = 0
        for agent in agents:
            path = custom.expanduser() if custom else config_path(home, agent)
            try:
                original = path.read_bytes().decode('utf-8') if path.exists() else ''
                updated = desired_text(agent, original)
                ready = path.is_file() and original == updated
                if agent == 'copilot':
                    ready = ready and os.access(path, os.X_OK)
                if arguments.agent_action == 'status':
                    print('{} {}: {}'.format('OK' if ready else 'NEEDS SETUP', agent, path))
                    failures += int(not ready)
                elif ready:
                    print('UNCHANGED {}: {}'.format(agent, path))
                elif path.is_symlink():
                    raise SetupError("Symlink settings are not replaced; pass --config-path with the real file.")
                elif arguments.dry_run:
                    print('WOULD SET UP {}: {}'.format(agent, path))
                else:
                    backup = write_settings(path, original, updated, executable=agent == 'copilot')
                    print('CONFIGURED {}: {}'.format(agent, path))
                    if backup:
                        print('  Backup: {}'.format(backup))
                if agent == 'copilot':
                    print('  Launch with {} (plain copilot is unchanged).'.format(shlex.quote(str(path))))
            except SetupError as error:
                print('ERROR {}: {}: {}'.format(agent, path, error), file=sys.stderr)
                failures += 1
            except (OSError, UnicodeError):
                # No source text or secret values in diagnostics.
                print('ERROR {}: could not read or write {}; check encoding and permissions.'.format(agent, path), file=sys.stderr)
                failures += 1
        if arguments.agent_action == 'setup':
            print('Restart configured agents / reload VS Code. Verify delivery with --doctor after use.')
        else:
            print('Local settings only; project settings and policies may override them. Use --doctor to check delivery.')
        return int(bool(failures))
    except (OSError, SetupError) as error:
        print('Agent setup: {}'.format(error), file=sys.stderr)
        return 1
