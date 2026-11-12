class_name SellFx
extends Control
## 記憶を売ったときの演出。記憶の断片が画面に浮かび、文字から順に崩れて消えていく。
##   await sell_fx.play(memory_dict)

signal glitch_level(v: float)

var _frags: Array = []   # {text, pos, t0, life}
var _t := 0.0
var _phase := ""
var _dim := 0.0
var _flash := 0.0
var _caption := ""
var _sub := ""
var _caption_a := 0.0
var _color := Color.WHITE


func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_STOP
	visible = false


func play(mem: Dictionary) -> void:
	visible = true
	_t = 0.0
	_frags.clear()
	_color = Color(str(mem.get("color", "#ff7ab8")))
	var texts: Array = []
	for f in mem.get("fragments", []):
		texts.append(GameState.plain_text(str(f)))
	var n := texts.size()
	for i in n:
		var ang := TAU * float(i) / float(maxi(n, 1)) + randf() * 0.5
		var pos := size / 2.0 + Vector2(cos(ang) * size.x * 0.28, sin(ang) * size.y * 0.26)
		_frags.append({"text": texts[i], "pos": pos, "t0": 0.4 + i * 0.35, "life": 3.6})
	_caption = "《%s》" % str(mem.get("name", ""))
	_sub = ""
	_caption_a = 0.0
	_flash = 0.0
	var tw := create_tween()
	tw.tween_property(self, "_dim", 0.88, 0.5)
	await get_tree().create_timer(0.3).timeout
	_caption_a = 1.0
	await get_tree().create_timer(0.4 + n * 0.35 + 1.6).timeout
	# 崩壊
	for k in 12:
		glitch_level.emit(0.2 + 0.07 * k)
		await get_tree().create_timer(0.06).timeout
	_flash = 1.0
	glitch_level.emit(1.0)
	_frags.clear()
	await get_tree().create_timer(0.25).timeout
	glitch_level.emit(0.0)
	_caption = "記憶をひとつ、売却しました"
	_sub = "+%s円" % GameState.format_yen(int(mem.get("price", 0)))
	await get_tree().create_timer(2.2).timeout
	var tw2 := create_tween()
	tw2.tween_property(self, "_dim", 0.0, 0.6)
	tw2.parallel().tween_property(self, "_caption_a", 0.0, 0.5)
	await tw2.finished
	visible = false


func _process(delta: float) -> void:
	if not visible:
		return
	_t += delta
	_flash = maxf(0.0, _flash - delta * 1.6)
	queue_redraw()


func _draw() -> void:
	draw_rect(Rect2(Vector2.ZERO, size), Color(0.02, 0.0, 0.05, _dim))
	var f := UITheme.font()
	for fr in _frags:
		var lt: float = _t - float(fr["t0"])
		if lt < 0.0:
			continue
		var life: float = fr["life"]
		var k := clampf(lt / life, 0.0, 1.0)
		var text: String = fr["text"]
		var shown := ""
		# 時間とともに、文字が一つずつノイズに置き換わっていく
		var decay := int(pow(k, 1.4) * text.length() * 1.2)
		for i in text.length():
			var h := PixelArt.hash2(i * 17, int(_t * 15.0))
			if i < decay and h % 3 != 0:
				shown += GlitchText.NOISE[h % GlitchText.NOISE.length()]
			else:
				shown += text[i]
		var a := minf(lt * 2.0, 1.0) * (1.0 - smoothstep(0.75, 1.0, k))
		var p: Vector2 = fr["pos"] + Vector2(0, -lt * 6.0)
		var tw := f.get_string_size(shown, HORIZONTAL_ALIGNMENT_LEFT, -1, 16).x
		var jitter := Vector2(float(PixelArt.hash2(int(_t * 30.0), i_of(fr)) % 3) - 1.0, 0) * k * 2.0
		draw_string(f, p - Vector2(tw / 2.0, 0) + jitter + Vector2(1, 0), shown, HORIZONTAL_ALIGNMENT_LEFT, -1, 16, Color(0.3, 0.9, 1.0, a * 0.5))
		draw_string(f, p - Vector2(tw / 2.0, 0) + jitter, shown, HORIZONTAL_ALIGNMENT_LEFT, -1, 16, Color(_color.lightened(0.3), a))
	if _caption_a > 0.0:
		var cw := f.get_string_size(_caption, HORIZONTAL_ALIGNMENT_LEFT, -1, 24).x
		draw_string(f, Vector2((size.x - cw) / 2.0, size.y / 2.0 + 8), _caption, HORIZONTAL_ALIGNMENT_LEFT, -1, 24, Color(1, 1, 1, _caption_a))
		if _sub != "":
			var sw := f.get_string_size(_sub, HORIZONTAL_ALIGNMENT_LEFT, -1, 20).x
			draw_string(f, Vector2((size.x - sw) / 2.0, size.y / 2.0 + 42), _sub, HORIZONTAL_ALIGNMENT_LEFT, -1, 20, Color(UITheme.GOOD, _caption_a))
	if _flash > 0.0:
		draw_rect(Rect2(Vector2.ZERO, size), Color(1, 1, 1, _flash * 0.85))


func i_of(fr: Dictionary) -> int:
	return int(fr["t0"] * 10.0)
