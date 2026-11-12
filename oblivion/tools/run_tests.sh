#!/usr/bin/env bash
# 自動テスト (データ整合性 + Phase 1 通しプレイ + セーブ/ロード) をヘッドレスで実行する。
# 使い方: GODOT=/path/to/godot4 tools/run_tests.sh
set -euo pipefail
cd "$(dirname "$0")/.."
GODOT="${GODOT:-godot}"
"$GODOT" --headless --path . --editor --quit >/dev/null 2>&1 || true   # 初回インポート
"$GODOT" --headless --path . res://tests/test_runner.tscn
