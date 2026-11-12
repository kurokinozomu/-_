# 忘却都市 — Project OBLIVION

> 生きるために、人生を忘れていく。

2D生活シミュレーション × 心理ホラー × アドベンチャー。Godot 4.3 (GDScript) / Web ブラウザ向け (PC・iPhone・Android)。

現在 **Phase 3（物語と完成度向上）** まで実装済み。最初から最後まで遊べ、エンディングは6種類。
- Phase 1: 「自宅で目覚める → 街へ出る → 記憶買取店に入る → 母親の記憶を売る → 自宅へ戻る → 母親からの電話に違和感を覚える」
- Phase 2: 倉庫の仕分けミニゲーム・時間帯（朝/昼/夕方/夜）・生活費と自動融資・ATM返済・5種類すべての記憶の売却と影響
- Phase 3: 過去の自分の手紙・橋の下・秘密の証拠集めと対決・エンディング6種・BGM/環境音/効果音・演出強化

## 起動方法

### Godot エディタで遊ぶ
1. [Godot 4.3](https://godotengine.org/download/) (標準版) をインストール
2. Godot を起動 →「インポート」→ この `oblivion/project.godot` を選ぶ
3. F5 (または右上の ▶) で実行

### Web 版をローカルで遊ぶ
```bash
# Godot 4.3 のエクスポートテンプレートをインストール済みであること
GODOT=/path/to/godot tools/export_web.sh
python3 -m http.server -d build/web 8000
# → http://localhost:8000 を開く (スマホからは同じ LAN の PC の IP で)
```
スレッド無しの書き出し設定なので、COOP/COEP ヘッダーなしの静的ホスティング (GitHub Pages, Netlify, itch.io 等) にそのまま置ける。

### 自動テスト
```bash
GODOT=/path/to/godot tools/run_tests.sh
```
データ整合性 (会話の参照先・条件式・マップの出入口・フォントの収録文字)、Phase 1 の通しプレイ（実際に入力を送って歩かせる）、セーブ/ロード、分岐、Phase 2 の仕事・返済・自動融資・各記憶の影響を検証する 、Phase 3 の物語の流れと6種類すべてのエンディング (243項目)。

## 操作方法

| | PC | スマホ |
|---|---|---|
| 移動 | WASD / 矢印キー | 画面左半分をドラッグ (仮想スティック) |
| 調べる・話す・会話を進める | E / Space / Enter | 右下のボタン / 会話中は画面タップ |
| 選択肢 | W/S・↑↓ + E、またはマウス | タップ |
| メニュー | Esc / Tab / 右上の「≡ メニュー」 | 右上の「≡ メニュー」 |
| 仕分け (仕事) | A/S/D・←↓→・1/2/3、または棚をクリック | 棚をタップ |

縦持ちのスマホでは「横画面にしてください」と表示される。

## フォルダ構成

```
oblivion/
├─ project.godot            プロジェクト設定 (640x360 基準・canvas_items 拡大・GL Compatibility)
├─ export_presets.cfg       Web 書き出し設定 (スレッド無し / セーフエリア用CSS / 縦向き警告)
├─ data/                    ★ゲーム内容はすべてここ (コード変更なしで調整できる)
│  ├─ config.json           所持金・借金・生活費・期限・自動融資率・時間帯・仕事の報酬などの数値、文字化けさせる語句
│  ├─ memories.json         売れる記憶 (価格・鑑定文・断片・有効/無効)
│  ├─ dialogue.json         全会話・イベント (分岐・選択肢・フラグ)
│  ├─ maps.json             マップ (タイル文字列・オブジェクト・出入口・入場イベント)
│  ├─ characters.json       キャラクターの名前と配色
│  ├─ papers.json           手紙・メモ・看板・ポスターの本文
│  ├─ objectives.json       画面左上の「目標」表示
│  └─ endings.json          エンディング
├─ scenes/main.tscn         エントリーポイント
├─ scripts/
│  ├─ autoload/             GameData (データ読込・入力登録) / GameState (状態・条件式・置換・セーブ)
│  ├─ core/                 main.gd (進行役) / dialogue_runner.gd (会話スクリプト実行)
│  ├─ world/                マップ描画・衝突判定・プレイヤー・NPC/小物
│  ├─ art/pixel_art.gd      コードで描くドット絵 (タイル・キャラ・顔・小物)
│  └─ ui/                   HUD・会話・買取店・演出・タッチ操作・メニュー・タイトル等
├─ shaders/screen_noise.gdshader  画面ノイズ・走査線・グリッチ
├─ assets/fonts/            DotGothic16 (SIL Open Font License 1.1, OFL.txt 同梱)
├─ assets/audio/            BGM・環境音・効果音 (tools/gen_audio.py で合成したオリジナル)
├─ tests/                   自動テスト
├─ tools/                   テスト・Web書き出し・音源生成スクリプト
└─ docs/DESIGN.md           企画・物語設定・システム設計・ロードマップ
```

## 素材とライセンス
- グラフィックはすべてコード (`scripts/art/pixel_art.gd`) で描いたオリジナル。外部画像・有料素材は不使用。
- BGM・効果音もすべて `tools/gen_audio.py` が数式から合成したオリジナル (`python3 tools/gen_audio.py` で再生成。numpy と ffmpeg が必要)。
- フォント: [DotGothic16](https://github.com/fontworks-fonts/DotGothic16) (SIL OFL 1.1)。npm の `@fontsource/dotgothic16` に同梱のサブセットを結合して1ファイル化。
- 外部の生成AI API・有料サービスは不使用。
