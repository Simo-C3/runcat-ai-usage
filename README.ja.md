# RunCat AI Usage

[RunCat Neo](https://github.com/runcat-dev/RunCatNeo) に Claude Code、Codex、
GitHub Copilot のプラン利用状況を表示します。

```text
GitHub Copilot
Rate:       14.1% · 6,972 / 50,000 AIC
Today / 1h: 145 / 12 AIC
7d Trend:   ▁▂▃▅▆▇█
```

1分ごとに値を更新し、ローカルに40日分の履歴を保存します。外部Python
パッケージは不要です。

[English](README.md)

## 必要なもの

- macOS 13以降
- Custom Metrics対応のRunCat Neo
- `/usr/bin/python3`
- 利用したいサービスのログイン済みCLI
  - Claude Code
  - Codex
  - GitHub Copilot契約のあるアカウントで認証したGitHub CLI (`gh`)

未ログインのサービスは `Unavailable` となり、ほかのカードは通常どおり
更新されます。

## インストール

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

更新時は、新しいコードで `./scripts/install.sh` をもう一度実行してください。

## 表示内容

| 項目 | 内容 |
| --- | --- |
| **Rate** | 現在の利用率。取得できる場合は `使用量 / 上限` も表示 |
| **Today / 1h** | ローカル日付の当日増加量 / 直近60分の増加量 |
| **7d Trend** | 左が6日前、右が今日。`·` は記録なし |

履歴はインストール後から蓄積され、過去分は復元できません。TodayとTrendは
サービスから絶対使用量を取得できる場合だけ表示されます。

| サービス | Rateに使う値 |
| --- | --- |
| Claude Code | 5時間・7日枠の高い方。該当枠がないEnterpriseでは月次Extra Usage |
| Codex | Workspaceの個人Spend Control。なければ取得できたローリング利用率の高い方 |
| GitHub Copilot | 月次Premium Request（AI Credit）枠 |

## 診断

認証情報を表示せずに、3サービスの接続状況を確認できます。

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

```sh
./scripts/uninstall.sh
```

履歴とJSONも削除する場合:

```sh
./scripts/uninstall.sh --purge
```

RunCat Neoに追加したCustom Metrics Sourceは別途削除してください。

## ライセンス

[MIT](LICENSE)
