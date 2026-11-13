#!/usr/bin/env python3
"""Web 書き出し (build/web) から、claude.ai のアーティファクトとして載せられる形を作る。

    python3 tools/make_artifact_page.py   →  build/artifact/

アーティファクトは1ファイル15MBまでなので、エンジン (index.wasm 35MB) とデータ (index.pck) を
gzip で圧縮して置き、ページ側で fetch を差し替えてブラウザの DecompressionStream で展開する。
アーティファクトは .gz を配信しないので、圧縮ファイルは配信できる拡張子 .wasm の名前で置く
(中身は gzip。ページの fetch 差し替えが中身を展開するので、拡張子は関係ない)。
Service Worker は使えないので PWA 機能は外す。
"""
import gzip
import json
import os
import re
import shutil

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SRC = os.path.join(ROOT, "build", "web")
DST = os.path.join(ROOT, "build", "artifact")

html = open(os.path.join(SRC, "index.html"), encoding="utf-8").read()
config = json.loads(re.search(r"const GODOT_CONFIG = (\{.*?\});", html, re.S).group(1))
config["serviceWorker"] = ""
config["ensureCrossOriginIsolationHeaders"] = False

shutil.rmtree(DST, ignore_errors=True)
os.makedirs(DST)
for name in ("index.js", "index.audio.worklet.js"):
    shutil.copy(os.path.join(SRC, name), DST)
PACKED = {"index.wasm": "z-engine.wasm", "index.pck": "z-data.wasm"}
for name, packed in PACKED.items():
    with open(os.path.join(SRC, name), "rb") as f, gzip.open(os.path.join(DST, packed), "wb", 9) as g:
        shutil.copyfileobj(f, g)

PAGE = r"""<title>忘却都市</title>
<meta name="claude:viewport-fit-sides" content="cover">
<style>
/* 一枚の雨の夜。ゲーム画面を全面に置き、読み込み中だけ控えめな表示を出す */
:root {
  --night: #07060f; --ink: #e4e2f4; --dim: #8a88aa; --neon: #ff5ad0; --cyan: #45e0ff;
  --sat: env(safe-area-inset-top, 0px); --sab: env(safe-area-inset-bottom, 0px);
  --sal: env(safe-area-inset-left, 0px); --sar: env(safe-area-inset-right, 0px);
  color-scheme: dark;
}
html, body { height: 100%; background: var(--night); color: var(--ink); overflow: hidden;
  overscroll-behavior: none; touch-action: none; -webkit-user-select: none; user-select: none; -webkit-touch-callout: none; }
#canvas { position: fixed; inset: 0; width: 100%; height: 100%; display: block; outline: none; background: var(--night); }
#boot { position: fixed; inset: 0; display: grid; place-content: center; gap: 14px; text-align: center;
  padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px));
  font-family: "Hiragino Sans", "Noto Sans JP", system-ui, sans-serif; background: var(--night); }
#boot h1 { margin: 0; font-size: 28px; letter-spacing: .3em; font-weight: 600; text-shadow: -2px 0 var(--cyan), 2px 0 var(--neon); }
#boot p { margin: 0; color: var(--dim); font-size: 13px; letter-spacing: .05em; }
#bar { width: min(280px, 70vw); height: 4px; background: #1a1830; justify-self: center; }
#bar span { display: block; height: 100%; width: 0; background: var(--cyan); transition: width .2s; }
#rotate { position: fixed; inset: 0; display: none; place-content: center; text-align: center; gap: 8px;
  background: var(--night); color: var(--ink); font: 15px/1.8 system-ui, sans-serif; z-index: 5; }
@media (orientation: portrait) and (max-width: 900px) { #rotate { display: grid; } }
@media (prefers-reduced-motion: reduce) { #bar span { transition: none; } }
</style>
<canvas id="canvas" tabindex="0">このブラウザは HTML5 canvas に対応していません。</canvas>
<div id="boot" role="status">
  <h1>忘却都市</h1>
  <div id="bar"><span></span></div>
  <p id="msg">読み込み中… 初回は約11MBのダウンロードがあります</p>
</div>
<div id="rotate"><div>横画面にしてください</div><div style="color:#8a88aa;font-size:12px">Please rotate your device</div></div>
<script>
// エンジンとデータは gzip で置いてあるので、取得時にブラウザで展開する
(function () {
  const realFetch = window.fetch.bind(window);
  // 本来のファイル名 → gzip 済みファイル名 と、展開後の種類
  const packed = { "index.wasm": ["z-engine.wasm", "application/wasm"], "index.pck": ["z-data.wasm", "application/octet-stream"] };
  window.fetch = function (input, init) {
    const url = typeof input === "string" ? input : (input && input.url) || "";
    const file = url.split("?")[0].split("/").pop();
    const hit = packed[file];
    if (!hit || typeof DecompressionStream === "undefined") return realFetch(input, init);
    return realFetch(url.replace(file, hit[0]), init).then((res) => {
      if (!res.ok) return res;
      const body = res.body.pipeThrough(new DecompressionStream("gzip"));
      return new Response(body, { status: 200, headers: { "Content-Type": hit[1] } });
    });
  };
})();
</script>
<script src="index.js"></script>
<script>
const GODOT_CONFIG = __CONFIG__;
const bar = document.querySelector("#bar span");
const msg = document.getElementById("msg");
const boot = document.getElementById("boot");
function fail(text) { msg.textContent = text; msg.style.color = "#ff6a7a"; bar.style.background = "#ff6a7a"; }
if (typeof DecompressionStream === "undefined") {
  fail("このブラウザは古いため遊べません。最新の Chrome / Safari / Firefox で開いてください。");
} else if (!Engine.isWebGLAvailable(2)) {
  fail("WebGL 2 が使えないため遊べません。別のブラウザか端末で開いてください。");
} else {
  const engine = new Engine(GODOT_CONFIG);
  engine.startGame({
    onProgress: (cur, total) => { if (total > 0) bar.style.width = Math.min(100, (cur / total) * 100) + "%"; },
  }).then(() => { boot.hidden = true; }, (err) => { console.error(err); fail("起動に失敗しました: " + (err && err.message ? err.message : err)); });
}
</script>
"""
open(os.path.join(DST, "oblivion.html"), "w", encoding="utf-8").write(PAGE.replace("__CONFIG__", json.dumps(config)))
for n in sorted(os.listdir(DST)):
    print(f"{n:28s} {os.path.getsize(os.path.join(DST, n)) // 1024:6d} KB")
