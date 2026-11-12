class_name PhotoView
extends Control
## 部屋の写真を拡大表示する。母親の記憶を売ると、女性の顔だけが認識できなくなる。

signal closed

var _t := 0.0
var _guard := 0.0
var lost := false


func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_STOP
	visible = false
	gui_input.connect(func(e):
		if e is InputEventMouseButton and e.pressed and _guard <= 0.0:
			accept_event()
			closed.emit())


func show_photo() -> void:
	lost = GameState.is_sold("mother")
	visible = true
	_guard = 0.25
	await closed
	visible = false


func _process(delta: float) -> void:
	if visible:
		_t += delta
		_guard -= delta
		queue_redraw()


func _unhandled_input(event: InputEvent) -> void:
	if visible and _guard <= 0.0 and (event.is_action_pressed("interact", false) or event.is_action_pressed("cancel", false)):
		get_viewport().set_input_as_handled()
		closed.emit()


func _draw() -> void:
	draw_rect(Rect2(Vector2.ZERO, size), Color(0, 0, 0, 0.7))
	var s := floorf(minf(size.x / 80.0, size.y / 70.0))
	s = maxf(s, 2.0)
	var o := ((size - Vector2(64, 52) * s) / 2.0).floor()
	var P := func(x: float, y: float, w: float, h: float, c: Color) -> void:
		draw_rect(Rect2(o.x + x * s, o.y + y * s, w * s, h * s), c)
	# 額縁と退色した写真
	P.call(-3, -3, 70, 58, Color("#6a5038"))
	P.call(-1, -1, 66, 54, Color("#e8e0d0"))
	P.call(1, 1, 62, 44, Color("#a8b8c8"))
	P.call(1, 30, 62, 15, Color("#7a9070"))
	# 桜
	for i in 9:
		var hx := PixelArt.hash2(i, 3) % 58
		var hy := PixelArt.hash2(i, 9) % 18
		P.call(2 + hx, 2 + hy, 6, 4, Color("#f0c0d0"))
	P.call(48, 10, 3, 22, Color("#5a4038"))
	# 子ども (幼い湊)
	P.call(14, 26, 8, 8, Color("#e8c4a8"))
	P.call(14, 25, 8, 3, Color("#262838"))
	P.call(16, 29, 1, 1, Color("#101018"))
	P.call(19, 29, 1, 1, Color("#101018"))
	P.call(13, 34, 10, 9, Color("#e8d060"))
	# 女性
	P.call(30, 14, 12, 12, Color("#e8c4a8"))
	P.call(29, 12, 14, 4, Color("#3a2a30"))
	P.call(29, 14, 3, 14, Color("#3a2a30"))
	P.call(40, 14, 3, 14, Color("#3a2a30"))
	P.call(28, 26, 16, 18, Color("#a05070"))
	P.call(26, 32, 6, 3, Color("#a05070"))
	P.call(22, 33, 6, 2, Color("#e8c4a8"))
	if lost:
		# 顔だけが、どうしても認識できない
		var seed := int(_t * 14.0)
		for yy in range(12, 27):
			for xx in range(29, 43):
				var v := PixelArt.hash2(xx + seed * 13, yy + seed * 7) % 100
				if v < 70:
					P.call(xx, yy, 1, 1, Color(0.55 + v * 0.004, 0.5, 0.65, 0.95))
		var jx := float(PixelArt.hash2(seed, 1) % 5) - 2.0
		P.call(26 + jx, 18, 20, 1, Color(1.0, 0.35, 0.82, 0.8))
	else:
		P.call(33, 19, 2, 1, Color("#101018"))
		P.call(38, 19, 2, 1, Color("#101018"))
		P.call(34, 22, 4, 1, Color("#a06060"))
	# 退色・傷
	P.call(1, 1, 62, 44, Color(1.0, 0.9, 0.7, 0.12))
	P.call(50, 3, 1, 30, Color(1, 1, 1, 0.25))
	var f := UITheme.font()
	var caption := "霧野公園にて" if not lost else "？？？と。霧野公園にて"
	draw_string(f, o + Vector2(2, 50) * s + Vector2(0, 2), caption, HORIZONTAL_ALIGNMENT_LEFT, -1, 16, Color("#5a5048"))
	draw_string(f, Vector2(size.x / 2.0 - 70, o.y + 58 * s + 14), "タップ / E で閉じる", HORIZONTAL_ALIGNMENT_LEFT, -1, 12, UITheme.TEXT_DIM)
