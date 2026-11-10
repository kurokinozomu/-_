# AI動画自動制作システム (aivideo)

テーマを1行入力するだけで、YouTubeに投稿できる完成動画 (MP4) と、タイトル案・概要欄・タグ・サムネイルを自動で生成します。

```bash
python -m aivideo "深海生物の不思議というテーマで8分の動画を作って"
```

## 出力されるファイル

`output/<日時>_<テーマ>/` に以下が作られます。

| ファイル | 内容 |
|---|---|
| `video.mp4` | 完成動画 (1920×1080 / 16:9 / 30fps / H.264 + AAC / -14 LUFS) |
| `thumbnail.png` | サムネイル (1280×720) |
| `metadata.md` | タイトル案5個・概要欄 (チャプター・クレジット込み)・タグ・サムネ案・企画・タイムスタンプ付き台本 |
| `metadata.json` | 上記の機械可読版 |
| `subtitles.srt` | YouTube にアップロードできる字幕ファイル |
| `plan.json` | 台本データ。手直しして `--plan` で再レンダリングできる |

## 制作工程

| # | 工程 | 使用技術 (無料を優先) |
|---|---|---|
| 1-3 | 企画・台本・シーン分割 | Claude (`claude -p`、Claude Code のログインを利用) → 全体構成を作ってから章ごとにシーンを生成 |
| 4 | シーン映像 | Pollinations.ai (無料・キー不要のAI画像生成 FLUX) / 接続できない場合は、シーンの内容に合わせて台本AIが選んだイラスト (Noto Emoji) をバラエティ番組風の集中線背景に配置。見出しはテレビ風のテロップで、画面に固定してスライドイン |
| 5 | 日本語ナレーション | VOICEVOX (ローカルで起動している場合) / Open JTalk の女性の声「Mei」(既定は明るく柔らかい happy。耳ざわりな高音を抑える処理つき) |
| 6 | BGM・効果音 | プログラム内で数式から合成するオリジナル音源 (著作権フリー)。ナレーション中はBGMを自動で下げる |
| 7 | 字幕 | テレビ・YouTube で定番の「二重縁取り」字幕 (丸ゴシック極太・白文字・黒の内フチ・色付きの外フチ)。大事な語は黄色で強調。文ごとに音声の長さを測って表示するのでずれない |
| 8 | 自動編集 | FFmpeg: シーンごとのカメラワーク (ズームイン/アウト・上下左右のパン)、10種類の場面転換、字幕の焼き込み |
| 9 | 書き出し | MP4 (faststart)、音量は YouTube 推奨の -14 LUFS に正規化 |
| 10 | YouTube 用素材 | タイトル案・概要欄・タグ・チャプター (実際の時間から算出)・サムネイル (ラベル・二段の大見出し・赤の強調語・バッジ・イラスト・下帯) |

## セットアップ

### 必要なもの
- Python 3.10 以上
- FFmpeg (libass 付き。一般的な配布版なら入っています)
- 日本語フォント
- (推奨) [Claude Code](https://claude.com/claude-code): 台本を作るのに使います

```bash
# Ubuntu / Debian
sudo apt install ffmpeg fonts-noto-cjk
# macOS
brew install ffmpeg
# Windows
winget install Gyan.FFmpeg

pip install -r requirements.txt
cp .env.example .env   # 必要に応じて編集

python -m aivideo --check   # 足りないものとインストール方法を表示
```

### (任意) VOICEVOX で音声を高品質にする
1. https://voicevox.hiroshiba.jp/ から VOICEVOX をインストールして起動します (エンジンが `http://127.0.0.1:50021` で動きます)
2. 起動中は自動で VOICEVOX が使われます。話者は `.env` の `VOICEVOX_SPEAKER` で変更できます (13 = 青山龍星)
3. VOICEVOX の利用規約に従い、概要欄に「VOICEVOX:キャラクター名」のクレジットが自動で入ります

## 使い方

```bash
# 自然な文章で指示 (テーマと長さを自動で読み取ります)
python -m aivideo "睡眠の科学というテーマで3分の動画を作って"
python -m aivideo "テーマ：ピラミッドの謎で1分30秒"

# 引数で指定
python -m aivideo --theme "量子コンピュータ入門" --minutes 10

# ショート動画 (縦型 1080x1920、既定 50 秒)
python -m aivideo "江戸の庶民は昼で仕事終了？というテーマでショート動画を作って"
python -m aivideo --theme "信長が生きていたら" --shorts --seconds 45

# 台本 (plan.json) を手直ししてから作り直す
python -m aivideo --plan output/xxxx/plan.json

# ネットワークを使わずに動かす (動作確認用)
python -m aivideo "テスト" --seconds 30 --llm offline --visuals procedural
```

### ショート動画
指示文に「ショート」「縦型」が入っているか `--shorts` を付けると、縦型 (1080x1920) で作ります。
- 台本: 最初の 1 文で結論か強い問いを出し、1 シーン 2〜4 秒のテンポで進めて、最後に「詳しくは関連動画で」と長尺へ誘導
- 画面: 見出しテロップは上部、字幕はショートの下部ボタンにかからない高さに配置
- 表紙はアプリ上で動画内のフレームを選ぶため、サムネイル画像は作りません (タイトル・概要欄・タグは作ります)

### 声と語り口を変える (`.env`)
- `AIVIDEO_VOICE=happy` … 明るく柔らかい声 (既定)。`normal` は落ち着いた声、`bashful` はささやくようなゆっくりした声
- `AIVIDEO_TONE=` … 台本の語り口。空なら「やさしく親しみやすい、柔らかい語り口」。例: `落ち着いたドキュメンタリー風`

長さは 15秒〜60分 で指定できます。台本は目標の長さに合わせた文字数で書かせ、仕上がりの長さが大きくずれた場合は話す速さを自動で調整します (最大1.2倍)。

Claude Code から使う場合は、チャットで「〇〇というテーマで8分の動画を作って」と頼むだけで、このコマンドが実行されます (`CLAUDE.md` 参照)。

## 費用と制限 (隠さずに説明します)

| 機能 | 無料で使えるか | 補足 |
|---|---|---|
| 台本作成 (claude CLI) | Claude のサブスクリプションの範囲内 | 従量課金なし。8分動画で Claude を約8回呼び出します |
| 台本作成 (Anthropic API) | **有料** | `ANTHROPIC_API_KEY` に加え `AIVIDEO_ALLOW_PAID=1` または `--allow-paid` を指定したときだけ使います。8分動画1本で数十円程度が目安です |
| AI画像 (Pollinations) | 無料 | 混雑時は遅くなることや、回数制限がかかることがあります。失敗したシーンはオフライン画像に自動で切り替わります |
| 音声・BGM・効果音・編集 | 無料 (ローカル処理) | |
| **AI動画生成 (Runway, Veo, Kling など)** | **無料では実用的でない** | 映像そのものを動画として生成するAPIはすべて有料で、1本あたり数千円以上かかることもあります。このシステムでは AI画像にカメラワークと場面転換をつけて動きを出しています。有料の動画生成APIを追加したい場合は、事前にご相談ください |

## 著作権について
- 画像: AIで生成したもの、またはプログラムで描いたもののみを使います。実在の人物・ロゴ・作品は画像の指示に含めないよう台本AIに指示しています
- BGM・効果音: すべてプログラムで合成したオリジナル音源です
- 音声: Open JTalk (修正BSDライセンス) / HTS Voice "Mei" (CC BY 3.0、`assets/voices` に同梱、概要欄にクレジットを自動で記載) / VOICEVOX (クレジット表記を自動で記載)
- イラスト: Noto Emoji (Apache License 2.0)、フォント: M PLUS Rounded 1c・Dela Gothic One (SIL Open Font License)。初回実行時に自動でダウンロードします
- 生成した台本の事実確認は、投稿前にご自身でも行ってください

## APIキーの扱い
- キーは `.env` ファイルか環境変数に設定します。`.env` は `.gitignore` に入っているため、Git にはコミットされません
- ソースコードにはキーを書いていません

## 構成

```
aivideo/
  __main__.py   コマンドライン (指示文からテーマと長さを読み取る)
  pipeline.py   全工程の制御・タイムライン計算・メタデータ出力
  planner.py    企画・章立て・シーン分割 (プロンプト)
  llm.py        claude CLI / Anthropic API / オフライン
  tts.py        VOICEVOX / Open JTalk
  visuals.py    AI画像 / オフライン画像 / テキスト合成 / サムネイル
  audio.py      BGM・効果音の合成、ダッキング、ミックス
  subtitles.py  字幕の分割・改行・二重縁取り・強調 (ASS/SRT)
  assets.py     フォント・イラスト・声の取得とキャッシュ
  render.py     FFmpeg (カメラワーク、場面転換、焼き込み、書き出し)
```
