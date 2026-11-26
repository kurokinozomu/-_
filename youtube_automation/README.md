# youtube_automation — 運営管理

YouTube チャンネル「むかし暮らし研究所 (案)」を 90 日で収益化するための計画・調査・設定・運営記録。
動画の制作は `aivideo/`、運営の自動化 (企画・審査・投稿・分析・日報・ダッシュボード) は `ytops/` が行う。

| ファイル / フォルダ | 内容 |
|---|---|
| CLAUDE.md | Claude への永続的な運営指示 |
| MASTER_PLAN.md | 戦略の全体像 (目標・ルート逆算・シミュレーション・投稿戦略) |
| PROJECT_STATE.md | 現在の進捗・未完了事項 |
| DECISIONS.md | 意思決定の記録 |
| POLICY.md | 規約・著作権の管理方針 |
| OWNER_TASKS.md | オーナーにしかできない作業 (画面ごとの手順) |
| config/channel.json | チャンネルの方針 (シリーズ・声・色) |
| research/ | 環境調査・規約・ジャンル評価 (25)・競合 (30) |
| strategy/ | チャンネル設計・90 日の日別計画・収益化シミュレーション |
| ideas/backlog.md | 企画ストック (自動更新) |
| scripts/ | 動画ごとの台本シート (映像・字幕・効果音・事実確認・出典) |
| branding/ | ブランド素材の生成スクリプトと出力 |
| scheduler/ | cron / Windows タスクスケジューラ / クラウド実行の手順 |
| database/, reports/, dashboard/ | 運営データの保存先 (リポジトリの非公開化後に使用) |

運営データの実体 (DB・ログ・日報・動画) は `state/` (git 管理外)。

## はじめかた (PC)
```bash
git clone <このリポジトリ> && cd -_
python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m aivideo --check        # 制作環境のチェック
python -m ytops status           # 運営の状況
```
その後 OWNER_TASKS.md の手順 0〜4 → scheduler/README.md で定期実行を設定。

## 毎日の流れ (自動)
データ取得・分析 → 改善ルールの調整 → 企画補充 → 制作 (ショート 2・長尺 火木・睡眠用 土) → 品質審査 (100 点・85 点以上で候補) → 台本シート・サムネ 3 案 → 非公開アップロード → **オーナー承認** → 予約公開 → 日報 → ダッシュボード

## スマホからの操作
- Claude アプリ: このプロジェクトのセッションで「状況を教えて」「承認待ちを見せて」「〇〇を承認」「止めて」
- ダッシュボード: PC で `python -m ytops dashboard --serve --host 0.0.0.0` を Tailscale などの VPN 内で開く (インターネットに直接公開しない)
- YouTube Studio アプリ: 非公開の動画の確認・公開状況
