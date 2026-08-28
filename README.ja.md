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

1分ごとに値を更新し、ローカルに最大366日分の履歴を保存します。外部Python
パッケージは不要です。

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
```

`brew trust` ではtap全体ではなく、このFormulaだけを信頼対象にします。

アップデート:

```sh
brew update
brew upgrade runcat-ai-usage
```

Homebrewが名前付きバックグラウンドアプリのインストールまたは更新、1分間隔の
LaunchAgentの起動、初回JSON生成まで自動で行います。既存の履歴は維持されます。
`runcat-ai-usage-install` はセットアップの修復や手動再起動が必要な場合だけ
実行してください。

## 手動でインストール

```sh
git clone https://github.com/Simo-C3/runcat-ai-usage.git
cd runcat-ai-usage
./scripts/install.sh
```

インストーラーは **RunCat AI Usage Monitor** という名前のバックグラウンド
アプリと1分間隔のLaunchAgentを作成し、`~/RunCatMetrics` を開きます。

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

- `--rows`: `rate`、`change`、`trend` を任意の順序で指定
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

認証情報を表示せずに、3サービスの接続状況を確認できます。

```sh
runcat-ai-usage --doctor
```

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

## ライセンス

[MIT](LICENSE)

リリースはSemVerタグから自動作成します。手順は
[RELEASING.md](RELEASING.md) を参照してください。
