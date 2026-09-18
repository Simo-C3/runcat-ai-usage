import contextlib
import io
import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import agent_setup as setup
from app import main


class AgentSetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.environment = mock.patch.dict(os.environ, {}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def call(self, *args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch('app.Path.home', return_value=self.home), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = main(['agents', *args])
        return result, stdout.getvalue() + stderr.getvalue()

    def write(self, agent, value):
        path = setup.config_path(self.home, agent)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding='utf-8')
        return path

    def test_dry_run_changes_nothing_then_setup_all_is_idempotent(self):
        self.assertEqual(self.call('status')[0], 1)
        self.assertEqual(self.call('setup', 'all', '--dry-run')[0], 0)
        self.assertEqual(list(self.home.iterdir()), [])
        self.assertEqual(self.call('setup')[0], 0)
        self.assertEqual(self.call('status')[0], 0)
        before = {p: p.read_bytes() for p in self.home.rglob('*') if p.is_file()}
        self.assertEqual(self.call('setup')[0], 0)
        self.assertEqual(before, {p: p.read_bytes() for p in self.home.rglob('*') if p.is_file()})
        self.assertEqual(list(self.home.rglob('*.runcat-backup-*')), [])

    def test_claude_preserves_other_settings_and_private_backup(self):
        original = '{"permissions":{"deny":["secret"]},"env":{"KEEP":"value","OTEL_METRICS_EXPORTER":"none"}}\n'
        path = self.write('claude', original)
        path.chmod(0o640)
        result, output = self.call('setup', 'claude')
        self.assertEqual(result, 0)
        data = json.loads(path.read_text())
        self.assertEqual(data['permissions'], {'deny': ['secret']})
        self.assertEqual(data['env']['KEEP'], 'value')
        self.assertEqual(data['env']['OTEL_METRICS_EXPORTER'], 'otlp')
        self.assertNotIn('secret', output)
        backups = list(path.parent.glob('*.runcat-backup-*'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), original)
        self.assertEqual(stat.S_IMODE(backups[0].stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o640)

    def test_custom_config_paths_and_environment_overrides(self):
        for name, env in [('claude', 'CLAUDE_CONFIG_DIR'), ('codex', 'CODEX_HOME')]:
            with self.subTest(name=name), mock.patch.dict(os.environ, {env: str(self.home / name)}):
                self.assertEqual(self.call('setup', name)[0], 0)
                self.assertTrue(setup.config_path(self.home, name).exists())
        custom = self.home / 'Code - Insiders' / 'User' / 'settings.json'
        self.assertEqual(self.call('setup', 'vscode', '--config-path', str(custom))[0], 0)
        self.assertTrue(custom.exists())
        self.assertEqual(self.call('setup', 'all', '--config-path', str(custom))[0], 1)
        self.assertEqual(self.call('setup', 'copilot', '--config-path', str(custom))[0], 1)

    def test_invalid_json_is_not_overwritten_or_printed(self):
        for original in ('{"env": "secret"}', '{"key": "secret",}', '["secret"]', '{"env":{},"env":{}}'):
            with self.subTest(original=original):
                path = self.write('claude', original)
                result, output = self.call('setup', 'claude')
                self.assertEqual(result, 1)
                self.assertEqual(path.read_text(), original)
                self.assertNotIn('secret', output)
                self.assertEqual(list(path.parent.glob('*.runcat-backup-*')), [])

    def test_jsonc_preserves_comments_nested_settings_and_trailing_commas(self):
        original = '''{
  // user preference
  "editor.fontSize": 14,
  "url": "https://example.test/*not a comment*/",
  "nested": {"array": [1, 2,],},
  "github.copilot.chat.otel.enabled": false, // keep this comment
  /* end comment */
}
'''
        path = self.write('vscode', original)
        self.assertEqual(self.call('setup', 'vscode')[0], 0)
        text = path.read_text()
        data, _ = setup.json_document(text, comments=True)
        self.assertEqual(data['editor.fontSize'], 14)
        self.assertEqual(data['nested'], {'array': [1, 2]})
        self.assertEqual(data['url'], 'https://example.test/*not a comment*/')
        for comment in ('// user preference', '// keep this comment', '/* end comment */'):
            self.assertIn(comment, text)
        for key, value in setup.VSCODE_SETTINGS.items():
            self.assertEqual(data[key], value)
        self.assertEqual(setup.desired_text('vscode', text), text)

    def test_jsonc_empty_object_and_last_value_replacement(self):
        for original in ('{ /*keep*/ }', '{"github.copilot.chat.otel.captureContent":true}',
                         '{"x": "https://a\\\"//b"}', '{"a":null, "b":[{}, false]}'):
            with self.subTest(original=original):
                result = setup.merge_jsonc(original, setup.VSCODE_SETTINGS)
                data, _ = setup.json_document(result, comments=True)
                self.assertFalse(data['github.copilot.chat.otel.captureContent'])
                self.assertEqual(setup.merge_jsonc(result, setup.VSCODE_SETTINGS), result)

    def test_codex_preserves_other_tables_multiline_values_and_comments(self):
        original = '''# my config
model = "gpt-5"
instructions = """
[otel.fake]
metrics_exporter = "not a real assignment"
"""
[otel] # telemetry
metrics_exporter = { otlp-grpc = { endpoint = "https://old.test" } }
exporter = "none" # preserve logs
log_user_prompt = false
[projects."/tmp/a=b"]
trust_level = "trusted"
'''
        result = setup.merge_codex(original)
        self.assertIn('# my config', result)
        self.assertIn('exporter = "none" # preserve logs', result)
        self.assertIn('metrics_exporter = "not a real assignment"', result)
        self.assertIn('[projects."/tmp/a=b"]\ntrust_level = "trusted"', result)
        self.assertNotIn('https://old.test', result)
        self.assertEqual(setup.merge_codex(result), result)
        try:
            import tomllib
        except ImportError:
            return
        data = tomllib.loads(result)
        self.assertEqual(data['otel']['metrics_exporter']['otlp-http']['endpoint'], setup.METRICS)
        self.assertEqual(data['otel']['exporter'], 'none')

    def test_codex_existing_exporter_forms(self):
        for original in (
            'otel.metrics_exporter = "none"\notel.log_user_prompt = false\n',
            '[otel.metrics_exporter.otlp-http]\nendpoint="https://old"\nprotocol="json"\n[otel.metrics_exporter.otlp-http.headers]\nAuthorization="private"\n[other]\na=1\n',
            '[otel]\n"metrics_exporter" = { otlp-http = { endpoint = "https://old" } }\n',
            "[ 'otel' ]\n'metrics_exporter' = 'none'\n",
            '[otel]\nmetrics_exporter = "none"',
        ):
            with self.subTest(original=original):
                updated = setup.merge_codex(original)
                self.assertNotIn('https://old', updated)
                self.assertNotIn('private', updated)
                self.assertEqual(setup.merge_codex(updated), updated)

    def test_codex_unsupported_or_incomplete_config_fails_without_changes(self):
        for original in ('otel = { metrics_exporter = "none" }', '[otel]\nmetrics_exporter = {',
                         '"unterminated', '[[otel.metrics_exporter]]\nx=1', '[otel]\nnot an assignment',
                         '[[otel]]\na=1', '[otel}\na=1'):
            with self.subTest(original=original):
                path = self.write('codex', original)
                self.assertEqual(self.call('setup', 'codex')[0], 1)
                self.assertEqual(path.read_text(), original)
                self.assertEqual(list(path.parent.glob('*.runcat-backup-*')), [])

    def test_symlink_and_concurrent_change_are_not_overwritten(self):
        real = self.home / 'real.json'
        real.write_text('{}')
        path = setup.config_path(self.home, 'claude')
        path.parent.mkdir(parents=True)
        path.symlink_to(real)
        self.assertEqual(self.call('setup', 'claude', '--dry-run')[0], 1)
        self.assertEqual(self.call('setup', 'claude')[0], 1)
        self.assertTrue(path.is_symlink())
        self.assertEqual(real.read_text(), '{}')
        with self.assertRaises(setup.SetupError):
            setup.write_settings(real, '{"changed":true}', '{}')
        self.assertEqual(real.read_text(), '{}')

    def test_all_reports_partial_failure_without_stopping_other_agents(self):
        self.write('codex', 'otel = {}')
        self.assertEqual(self.call('setup', 'all')[0], 1)
        self.assertEqual(self.call('status', 'claude')[0], 0)
        self.assertEqual(self.call('status', 'vscode')[0], 0)

    def test_copilot_launcher_forwards_arguments_and_scopes_environment(self):
        self.assertEqual(self.call('setup', 'copilot')[0], 0)
        launcher = setup.config_path(self.home, 'copilot')
        fake = self.home / 'copilot'
        fake.write_text('#!/bin/sh\nprintf "%s\\n" "$COPILOT_OTEL_ENABLED" "$OTEL_EXPORTER_OTLP_ENDPOINT" "$1" "$2"\n')
        fake.chmod(0o700)
        argument = 'spaces; $(exit 10) `exit 11`'
        result = subprocess.run([str(launcher), argument, '--version'], env={'PATH': str(self.home)},
                                capture_output=True, text=True, check=True)
        self.assertEqual(result.stdout.splitlines(), ['true', setup.BASE, argument, '--version'])
        self.assertNotIn('COPILOT_OTEL_ENABLED', os.environ)
        launcher.chmod(0o600)
        self.assertEqual(self.call('status', 'copilot')[0], 1)
        self.assertEqual(self.call('setup', 'copilot')[0], 0)
        self.assertTrue(os.access(launcher, os.X_OK))

    def test_run_passes_arguments_without_shell_and_without_writes(self):
        for agent in ('claude', 'codex', 'copilot'):
            with self.subTest(agent=agent), mock.patch('agent_setup.shutil.which', return_value='/bin/' + agent), mock.patch('agent_setup.os.execve') as execute:
                self.assertEqual(self.call('run', agent, '--', '--version', '$(example)')[0], 0)
                executable, args, env = execute.call_args[0]
                self.assertEqual(args[-2:], ['--version', '$(example)'])
                if agent == 'codex':
                    self.assertEqual(args[1:3], ['-c', setup.CODEX_OVERRIDE])
                else:
                    self.assertEqual(env['OTEL_EXPORTER_OTLP_METRICS_ENDPOINT'], setup.METRICS)
        self.assertEqual(list(self.home.iterdir()), [])

    def test_run_missing_agent(self):
        with mock.patch('agent_setup.shutil.which', return_value=None):
            self.assertEqual(self.call('run', 'codex')[0], 1)


if __name__ == '__main__':
    unittest.main()
