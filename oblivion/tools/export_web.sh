#!/usr/bin/env bash
# Web 版を build/web/ に書き出す (スレッド無し版: 特別な HTTP ヘッダー不要で iOS Safari / GitHub Pages 等で動く)。
# 事前に Godot 4.3 のエクスポートテンプレートをインストールしておくこと。
# 使い方: GODOT=/path/to/godot4 tools/export_web.sh  →  python3 -m http.server -d build/web 8000
set -euo pipefail
cd "$(dirname "$0")/.."
GODOT="${GODOT:-godot}"
mkdir -p build/web
"$GODOT" --headless --path . --editor --quit >/dev/null 2>&1 || true
# 書き出しはスクリプトエラーがあっても成功してしまうので、先にテストで止める
if [ "${SKIP_TESTS:-0}" != "1" ]; then
  "$GODOT" --headless --path . res://tests/test_runner.tscn
fi
"$GODOT" --headless --path . --export-release "Web" build/web/index.html
ls -la build/web
