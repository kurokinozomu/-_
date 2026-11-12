class_name GlitchText
extends RefCounted
## [g]…[/g] で囲まれた語 (売った記憶に関わる言葉) を、読めない文字列として描画する。
## 文字数は元の語と同じに保つので、タイプライター表示の文字数計算が狂わない。

const NOISE := "■□◆◇※＃＊△▽〓∴∵≡忘失消空無"
const COLORS := ["#ff5ad0", "#b48aff", "#45e0ff", "#8a88aa"]


## RichTextLabel 用の BBCode に変換する。seed を変えるたびに文字がちらつく。
static func to_bbcode(text: String, seed: int) -> String:
	var out := ""
	var i := 0
	var span := 0
	while i < text.length():
		var a := text.find("[g]", i)
		if a == -1:
			out += _escape(text.substr(i))
			break
		out += _escape(text.substr(i, a - i))
		var b := text.find("[/g]", a)
		if b == -1:
			break
		var inner := text.substr(a + 3, b - a - 3)
		out += "[color=%s]" % COLORS[(seed + span) % COLORS.size()]
		for k in inner.length():
			var h := PixelArt.hash2(seed * 7 + k * 13 + span * 31, k + span)
			out += NOISE[h % NOISE.length()]
		out += "[/color]"
		span += 1
		i = b + 4
	return out


static func has_glitch(text: String) -> bool:
	return text.contains("[g]")


static func _escape(s: String) -> String:
	return s.replace("[", "[lb]")
