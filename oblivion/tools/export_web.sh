#!/usr/bin/env bash
# Web 版を build/web/ に書き出す (スレッド無し版: 特別な HTTP ヘッダー不要で iOS Safari / GitHub Pages 等で動く)。
# 事前に Godot 4.3 のエクスポートテンプレートをインストールしておくこと。
# 使い方: GODOT=/path/to/godot4 tools/export_web.sh  →  python3 -m http.server -d build/web 8000
#         SKIP_TESTS=1 で自動テストを省略
set -euo pipefail
cd "$(dirname "$0")/.."
GODOT="${GODOT:-godot}"
OUT=build/web
mkdir -p "$OUT"
touch build/.gdignore   # 書き出し先を Godot に取り込ませない
"$GODOT" --headless --path . --editor --quit >/dev/null 2>&1 || true
# 書き出しはスクリプトエラーがあっても成功してしまうので、先にテストで止める
if [ "${SKIP_TESTS:-0}" != "1" ]; then
  "$GODOT" --headless --path . res://tests/test_runner.tscn
fi
rm -f "$OUT"/*
"$GODOT" --headless --path . --export-release "Web" "$OUT/index.html"
# Godot 4.3 の PWA は、スレッド無し版に存在しない index.worker.js をキャッシュ対象に入れてしまい、
# Service Worker のインストールが失敗する。実在しないファイルを一覧から取り除く。
python3 - "$OUT" <<'PY'
import os, re, sys
out = sys.argv[1]
sw = os.path.join(out, "index.service.worker.js")
if os.path.exists(sw):
    src = open(sw, encoding="utf-8").read()
    def fix(m):
        files = [f for f in re.findall(r'"([^"]+)"', m.group(2)) if os.path.exists(os.path.join(out, f))]
        return m.group(1) + "[" + ",".join('"%s"' % f for f in files) + "]"
    src = re.sub(r'(const CACHED_FILES = )\[([^\]]*)\]', fix, src)
    open(sw, "w", encoding="utf-8").write(src)
    print("service worker:", re.search(r'const CACHED_FILES = \[[^\]]*\]', src).group(0))
PY
ls -la "$OUT"
