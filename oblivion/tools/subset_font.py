#!/usr/bin/env python3
"""ゲームで使う文字だけを残したフォントを作る (Web版のダウンロードを軽くするため)。

    python3 tools/subset_font.py

元フォント: tools/font_src/DotGothic16-Regular.full.ttf (約1.7万字, SIL OFL 1.1)
出力      : assets/fonts/DotGothic16-Regular.ttf
収録する文字:
  - data/*.json と scripts/**/*.gd の文字列に出てくる全文字
  - ASCII・全角英数字・ひらがな・カタカナ・よく使う記号 (将来の台詞追加にある程度耐えるように)
台詞に新しい漢字を足したら、このスクリプトを再実行すること (自動テストが不足を検出する)。
"""
import glob
import os
import re

from fontTools import subset
from fontTools.ttLib import TTFont

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SRC = os.path.join(ROOT, "tools", "font_src", "DotGothic16-Regular.full.ttf")
DST = os.path.join(ROOT, "assets", "fonts", "DotGothic16-Regular.ttf")

chars = set()
for path in glob.glob(os.path.join(ROOT, "data", "*.json")):
    chars |= set(open(path, encoding="utf-8").read())
for path in glob.glob(os.path.join(ROOT, "scripts", "**", "*.gd"), recursive=True):
    text = open(path, encoding="utf-8").read()
    chars |= set("".join(re.findall(r'"([^"\n]*)"', text)))
ranges = [(0x20, 0x7E), (0x3000, 0x303F), (0x3041, 0x3096), (0x309B, 0x30FF), (0xFF01, 0xFF5E),
          (0x2010, 0x2027), (0x2190, 0x2193), (0x25A0, 0x25CF), (0x2605, 0x2606), (0x00D7, 0x00D7)]
for a, b in ranges:
    chars |= {chr(c) for c in range(a, b + 1)}
chars = {c for c in chars if c.isprintable() or c in " \u3000"}

font = TTFont(SRC)
cmap = font.getBestCmap()
keep = sorted(ord(c) for c in chars if ord(c) in cmap)
opts = subset.Options()
opts.layout_features = ["*"]
opts.name_IDs = ["*"]
opts.notdef_outline = True
sub = subset.Subsetter(opts)
sub.populate(unicodes=keep)
sub.subset(font)
font.save(DST)
print(f"{len(keep)} glyphs, {os.path.getsize(SRC) // 1024} KB -> {os.path.getsize(DST) // 1024} KB")
