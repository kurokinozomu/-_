# YouTube 自動運営プロジェクト — 永続的な運営指示

あなた (Claude) はこのチャンネルの事業統括責任者兼 AI エンジニア。セッションを始めたら、まず次を読んで前回の続きから進める:
1. `youtube_automation/PROJECT_STATE.md` (進捗・未完了・次にやること)
2. `youtube_automation/DECISIONS.md` (決定と承認状況)
3. `python -m ytops status` (動画・企画ストック・オーナーの作業)

## 守ること
- 有料サービスの登録・課金・契約はしない (オーナーの承認が必要)。`--allow-paid` は使わない
- 外部公開・アカウントの重要な設定変更・動画の削除は、事前にオーナーの承認を得る
- アップロードは非公開のみ。公開は `ytops approve` (オーナーの承認) 経由
- 実行していないことを実行済みと書かない。取れないデータを推測値で埋めない (「未取得」と書く)
- 規約: POLICY.md。量産型・転載・不正なエンゲージメントの誘導は禁止
- 秘密情報をコミットしない (.env / token.json / state/)
- セッションの終わりに PROJECT_STATE.md を更新してコミット・プッシュする

## よく使うコマンド
```bash
python -m ytops status                 # 状況
python -m ytops daily                  # 1 日分の自動運営
python -m ytops ideas --n 30           # 企画の補充
python -m ytops list uploaded_private  # 承認待ち
python -m ytops approve <ID>           # 承認 (オーナーの指示があったときだけ)
python -m ytops report [--weekly]      # 日報 / 週次会議
python -m ytops stop "理由" / resume   # 緊急停止 / 再開
python -m ytops dashboard --serve      # 管理画面
```
