# セットアップと設定

## 1. インストール

Homebrewを推奨します。導入・更新後にユーザーのターミナルから
`runcat-ai-usage-install --no-open` を実行すると、バックグラウンドアプリ・毎分の
残量取得LaunchAgent・Collector・OTLP受信アダプターをまとめて設置・起動します。
Homebrewのインストール処理は一時的なホームに隔離されるため、自動起動の設定は別途実行します。
エージェント側は `runcat-ai-usage agents setup all` で設定できます。
`agents setup all --dry-run` で変更対象、`agents status` で設定状態を確認できます。
Copilot CLIは生成した `~/.local/bin/runcat-copilot` から起動します。
OTel対応はv0.5.1以降で利用できます。ソースからの導入・外部送信先の追加は
[OTel設定](otel.md)を参照してください。

```sh
brew tap Simo-C3/runcat-ai-usage https://github.com/Simo-C3/runcat-ai-usage
brew trust --formula Simo-C3/runcat-ai-usage/runcat-ai-usage
brew install runcat-ai-usage
runcat-ai-usage-install --no-open
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
| `--rows` | `rate,change,trend,tokens,cost` | `rate`、`change`、`trend`、`remaining`、`tokens`、`cost`の任意の順序 |
| `--rate-format` | `full` | `full`、`percentage` |
| `--percentage-precision` | `1` | `0`〜`3` |
| `--language` | `en` | `en`、`ja` |
| `--trend-period` | `1w` | `1h`、`1d`、`1w`、`1mo`、または7分〜365日の期間 |

カスタム期間は `90m`、`12h`、`14d` のように指定します。7日以上の日単位の期間は
ローカル日付の境界で区切り、それより短い期間は7つの等間隔な区間で表示されます。
設定は次回の1分更新から反映されます。

## 3. 診断と手動更新

認証情報を表示せずに、自動更新の状態と各サービスへの接続を確認できます。

```sh
runcat-ai-usage --doctor
```

診断項目:

- バックグラウンドアプリとLaunchAgentの設置、登録、有効状態
- LaunchAgentに読み込まれた60秒間隔の設定と直近の終了結果
- 各JSONの書き込み時刻とデータ取得時刻が3分以内か、取得不可になっていないか
- Collector・受信アダプターの起動とHTTP応答、最近のOTLP配送
- 各サービスへの直接接続

定期実行の待機中（`not running`）は正常です。接続確認に成功しても、
自動更新が止まっていれば `FAIL` になり、終了コード1を返します。
出力先はLaunchAgentの設定を使い、`--output-dir` または
`RUNCAT_AI_USAGE_OUTPUT_DIR` で上書きできます。

問題がある場合は、診断結果に表示された復旧手順を実行します。
未設置・未登録・無効化には再セットアップ、更新停止には再起動とログ確認、
認証エラーにはサービス別のログイン手順を案内します。診断自体は読み取り専用です。
再起動で改善しなければ再セットアップし、復旧後は1〜2分待って再診断してください。
この確認は最近の更新実績を調べるもので、RunCat Neo画面への反映は確認しません。

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

残量取得LaunchAgentは60秒ごとに起動します。Collectorと受信アダプターは常駐します。
引数なし／`collect`はOTLP送信だけを行い、`serve`がJSONを生成します。
`--otlp-endpoint`は残量送信先の完全なメトリクスURLを指定します。
