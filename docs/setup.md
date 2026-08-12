# セットアップと設定

## 1. インストール

Homebrewを推奨します。インストール時にバックグラウンドアプリと1分間隔の
LaunchAgentが自動設定されます。

```sh
brew tap Simo-C3/runcat-ai-usage https://github.com/Simo-C3/runcat-ai-usage
brew trust --formula Simo-C3/runcat-ai-usage/runcat-ai-usage
brew install runcat-ai-usage
```

RunCat Neoの **Settings → Metrics → Custom Metrics** で
**Add Custom Metrics Source** を選び、次のファイルを追加します。

- `~/RunCatMetrics/claude-code.json`
- `~/RunCatMetrics/codex.json`
- `~/RunCatMetrics/github-copilot.json`

各サービスは独立して動作します。未ログインのサービスがあっても、ほかの
サービスの更新には影響しません。

## 2. 表示設定

現在値の確認、変更、初期化には `config` コマンドを使います。

```sh
runcat-ai-usage config show
runcat-ai-usage config set --language ja --trend-period 1d
runcat-ai-usage config reset
```

| 設定 | 初期値 | 指定できる値 |
| --- | --- | --- |
| `--rows` | `rate,change,trend` | `rate`、`change`、`trend`の任意の順序 |
| `--rate-format` | `full` | `full`、`percentage` |
| `--percentage-precision` | `1` | `0`〜`3` |
| `--language` | `en` | `en`、`ja` |
| `--trend-period` | `1w` | `1h`、`1d`、`1w`、`1mo`、または7分〜365日の期間 |

カスタム期間は `90m`、`12h`、`14d` のように指定します。推移は期間にかかわらず
7区間で表示されます。設定は次回の1分更新から反映されます。

## 3. 診断と手動更新

認証情報を表示せずに、各サービスへの接続を確認できます。

```sh
runcat-ai-usage --doctor
```

バックグラウンド更新をすぐに実行する場合:

```sh
launchctl kickstart -k "gui/$(id -u)/dev.runcat.ai-usage"
```

問題がある場合は次のログとLaunchAgentの状態を確認します。

```sh
tail -n 50 "$HOME/Library/Logs/RunCat AI Usage/monitor.error.log"
launchctl print "gui/$(id -u)/dev.runcat.ai-usage"
```

セットアップの修復や再起動には `runcat-ai-usage-install` を再実行します。

## 4. 保存先の変更

JSONの出力先を永続的に変更する場合は、環境変数を付けてセットアップを
再実行します。既存の履歴はそのまま維持されます。

```sh
RUNCAT_AI_USAGE_OUTPUT_DIR="$HOME/MyMetrics" runcat-ai-usage-install
```

1回だけ直接実行するときは、次の共通オプションも利用できます。

| オプション | 初期値 | 内容 |
| --- | --- | --- |
| `--output-dir` | `~/RunCatMetrics` | JSON出力先 |
| `--state-dir` | `~/Library/Application Support/RunCat AI Usage/state` | 設定・履歴・キャッシュの保存先 |
| `--refresh-seconds` | `55` | APIを再取得する最短間隔 |

LaunchAgent自体は60秒ごとに起動します。
