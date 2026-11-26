# AI動画自動制作システム

ユーザーが「〇〇というテーマで△分の動画を作って」のように動画制作を頼んだら、次のコマンドを実行して完成させる。

```bash
python -m aivideo "<ユーザーの指示文そのまま>"
```

- 実行には数分から数十分かかる。長尺のときはバックグラウンドで実行する
- 完了したら `output/<日時>_<テーマ>/` の `video.mp4`、`thumbnail.png`、`metadata.md` (タイトル案・概要欄) の場所を伝える
- 「ショート」「縦型」と頼まれたら縦型 (1080x1920) になる (指示文にその語が入っていれば自動、または `--shorts`)
- 有料API (`--allow-paid`) は、ユーザーが明示的に許可した場合だけ使う
- 台本を直したいと言われたら、`plan.json` を編集してから `python -m aivideo --plan <path>` で作り直す

## YouTube 自動運営 (ytops)
チャンネルの運営 (企画・品質審査・投稿・分析・日報) を頼まれたら、まず `youtube_automation/CLAUDE.md` と `youtube_automation/PROJECT_STATE.md` を読み、`python -m ytops status` で現状を確認してから続きを進める。
