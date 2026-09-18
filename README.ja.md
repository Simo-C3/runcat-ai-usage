# RunCat AI Usage

[![Test](https://github.com/Simo-C3/runcat-ai-usage/actions/workflows/test.yml/badge.svg)](https://github.com/Simo-C3/runcat-ai-usage/actions/workflows/test.yml)
[![Release](https://img.shields.io/github/v/release/Simo-C3/runcat-ai-usage)](https://github.com/Simo-C3/runcat-ai-usage/releases)

[RunCat Neo](https://github.com/runcat-dev/RunCatNeo) に Claude Code、Codex、
GitHub Copilot のプラン利用状況を表示します。

```text
GitHub Copilot
Rate:       14.1% · 6,972 / 50,000 AIC
Today / 1h: 145 / 12 AIC
7d Trend:   ▁▂▃▅▆▇█
```

1分ごとの残量取得と各エージェントの公式OTel出力をCollectorへ送り、
OTLP受信アダプターがRunCat用JSONを生成します。最大366日分の履歴を保存します。
外部Pythonパッケージは不要で、公式OTel Collectorをチェックサム検証して設置します。

エージェント設定と外部送信先の追加は[OTelの設定](docs/otel.md)を参照してください。
この構成と設定コマンドはv0.5.1以降で利用できます。

[English](README.md)

## ドキュメント

設定、データ保存、開発者向け情報は[ドキュメント一覧](docs/README.md)に
まとめています。

## 必要なもの

- macOS 13以降
- Custom Metrics対応のRunCat Neo
- 利用したいサービスのログイン済みCLI
  - Claude Code
  - Codex
  - GitHub Copilot契約のあるアカウントで認証したGitHub CLI (`gh`)

未ログインのサービスは `Unavailable` となり、ほかのカードは通常どおり
更新されます。

Homebrewでインストールする場合、Pythonも自動で管理されます。手動
インストールでは `/usr/bin/python3` が別途必要です。

## Homebrewでインストール（推奨）

```sh
brew tap Simo-C3/runcat-ai-usage https://github.com/Simo-C3/runcat-ai-usage
brew trust --formula Simo-C3/runcat-ai-usage/runcat-ai-usage
brew install runcat-ai-usage
runcat-ai-usage-install --no-open
```

`brew trust` ではtap全体ではなく、このFormulaだけを信頼対象にします。

アップデート:

```sh
brew update
brew upgrade runcat-ai-usage
runcat-ai-usage-install --no-open
```

Homebrewのインストール・更新後は、ユーザーのターミナルから
`runcat-ai-usage-install --no-open` を実行してください。Homebrewのインストール処理は
一時的なホームに隔離されるため、ユーザー用の常駐設定は別途実行します。
このコマンドが名前付きアプリ・毎分の残量取得・Collector・受信アダプターを
まとめて設置・起動します。初回JSONは1〜2分以内に生成され、既存の履歴は維持されます。

## 手動でインストール

```sh
git clone https://github.com/Simo-C3/runcat-ai-usage.git
cd runcat-ai-usage
./scripts/install.sh
```

インストーラーは **RunCat AI Usage Monitor** という名前のバックグラウンド
アプリ、毎分の残量取得、Collector・受信アダプターのLaunchAgentを作成し、
`~/RunCatMetrics` を開きます。各エージェントのOTel設定は `runcat-ai-usage agents setup all` で適用できます（[詳細](docs/otel.md)）。

RunCat Neoの **Settings → Metrics → Custom Metrics** で
**Add Custom Metrics Source** を選び、次の3ファイルを追加してください。

- `~/RunCatMetrics/claude-code.json`
- `~/RunCatMetrics/codex.json`
- `~/RunCatMetrics/github-copilot.json`

RunCat側で必要な設定はこのファイル選択だけです。必要に応じてMetrics Barで
各ソースを有効にすると、メニューバーにも現在のRateを表示できます。

手動インストールの更新時は、新しいコードで `./scripts/install.sh` をもう一度
実行してください。

## 表示内容

| 項目 | 内容 |
| --- | --- |
| **Rate** | 現在の利用率。取得できる場合は `使用量 / 上限` も表示 |
| **Today / 1h** | ローカル日付の当日増加量 / 直近60分の増加量 |
| **推移** | 設定期間の7区間を古い順に表示。7日以上の日単位の期間はローカル日付の境界で区切り、短い期間は等間隔。`·` は記録なし |

履歴はインストール後から蓄積され、過去分は復元できません。TodayとTrendは
サービスから絶対使用量を取得できる場合だけ表示されます。
Claude のキャッシュと履歴は、資格情報から算出した非可逆の識別子で
サインインごとに分離されます。

| サービス | Rateに使う値 |
| --- | --- |
| Claude Code | 5時間・7日枠を個別表示。月次Extra Usageは利用額・上限、無効時は「無効」を表示 |
| Codex | Workspaceの個人Spend Control。なければ取得できたローリング利用率の高い方 |
| GitHub Copilot | 月次Premium Request（AI Credit）枠 |

## コマンド

現在の表示設定を確認します。

```sh
runcat-ai-usage config show
```

表示する行と順序、Rateの形式、パーセント精度、ラベル言語、推移期間を変更できます。

```sh
runcat-ai-usage config set \
  --rows rate,change,trend \
  --rate-format full \
  --percentage-precision 1 \
  --language ja \
  --trend-period 1w
```

- `--rows`: `rate`、`change`、`trend`、`remaining`、`tokens`、`cost` を任意の順序で指定
  初期値は `rate,change,trend,tokens,cost`。トークン・推定費用は受信後に表示します。
- `--rate-format percentage`: 使用量と上限を隠して利用率のみ表示
- `--percentage-precision`: 小数点以下の最大桁数を `0`〜`3` で指定
- `--language`: 項目ラベルを `en` または `ja` に変更
- `--trend-period`: `1h`、`1d`、`1w`、`1mo`、または `90m`、`12h`、
  `14d` のような7分〜365日の任意期間を指定（`1mo` は30日）。7日以上の
  日単位の期間はローカル日付の境界で、それより短い期間は7つの等間隔で表示

設定はstateディレクトリに保存され、次回の更新から反映されます。初期設定へ
戻す場合は次を実行します。

```sh
runcat-ai-usage config reset
```

手動インストールの場合、例中の `runcat-ai-usage` は下記の診断で示す
バックグラウンドアプリの実行ファイルパスに読み替えてください。

### 診断

認証情報を表示せずに、自動更新の状態と3サービスの接続状況を確認できます。

```sh
runcat-ai-usage --doctor
```

バックグラウンドアプリとLaunchAgentの設置・登録・有効状態、60秒間隔の設定、
直近の終了結果、Collector・受信アダプターの稼働、OTLP配送、各JSONの書き込みと
データ取得が3分以内かを確認します。未使用時のネイティブOTel無通信は異常にしません。
実行間の待機状態（`not running`）は正常です。APIに接続できても、JSONが未生成、
古い、または取得不可なら `FAIL` となり、終了コードは1になります。

問題に応じて再セットアップ・再起動・再ログインの手順を表示します。
診断自体は設定やJSONを書き換えません。復旧後は1〜2分待って再診断してください。
未設置の場合は `runcat-ai-usage-install --no-open`、手動インストールの場合は
ソースのディレクトリで `./scripts/install.sh --no-open` を実行します。

出力先は設置済みLaunchAgentから読み取ります。`--output-dir` または
`RUNCAT_AI_USAGE_OUTPUT_DIR` で上書きできます。RunCat Neo画面への反映は診断対象外です。

手動インストールの場合:

```sh
"$HOME/Library/Application Support/RunCat AI Usage/RunCat AI Usage Monitor.app/Contents/MacOS/RunCat AI Usage Monitor" --doctor
```

エラーログ:

```sh
tail -n 50 "$HOME/Library/Logs/RunCat AI Usage/monitor.error.log"
```

使用する認証情報とAPIの注意事項は英語版READMEの
[Privacy and API stability](README.md#privacy-and-api-stability) と
[SECURITY.md](SECURITY.md) を参照してください。

## アンインストール

Homebrew:

```sh
runcat-ai-usage-uninstall
brew uninstall runcat-ai-usage
brew untrust --formula Simo-C3/runcat-ai-usage/runcat-ai-usage
brew untap Simo-C3/runcat-ai-usage
```

手動インストール:

```sh
./scripts/uninstall.sh
```

どちらも履歴とJSONは残します。これらも削除する場合は、Formulaを削除する
前にアンインストールコマンドへ `--purge` を付けます。

```sh
runcat-ai-usage-uninstall --purge
# または: ./scripts/uninstall.sh --purge
```

RunCat Neoに追加したCustom Metrics Sourceは別途削除してください。

`--purge` でも各エージェントのOTel設定・バックアップ・Copilot用ランチャーは残ります。
設定の自動解除コマンドはありません。アンインストール前に[設定の復元手順](docs/otel.md)で
OTel設定を戻し、不要になった `~/.local/bin/runcat-copilot` を削除してください。
バックアップ後に別の変更を加えた場合は、OTel部分だけ戻してその変更を維持してください。

## ライセンス

[MIT](LICENSE)

リリースはSemVerタグから自動作成します。手順は
[RELEASING.md](RELEASING.md) を参照してください。
