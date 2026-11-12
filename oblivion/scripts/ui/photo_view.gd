class_name PhotoView
extends Control
## 部屋の写真を拡大表示する。母親の記憶を売ると、女性の顔だけが認識できなくなる。

signal closed

var _t := 0.0
var _guard := 0.0
var lost := false
var kind := "mother"


func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_STOP
	visible = false
	gui_input.connect(func(e):
		if e is InputEventMouseButton and e.pressed and _guard <= 0.0:
			accept_event()
			closed.emit())


func show_photo(p_kind: String = "mother") -> void:
	kind = p_kind
	lost = GameState.is_sold("beloved" if kind == "beloved" else "mother")
	visible = true
	_guard = 0.25
	Sound.se("paper")
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
	if kind == "beloved":
		_draw_beloved(P, s, o)
		return
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


## 雨の橋の下の写真。相手の顔は最初から思い出せない (以前に売っている)。
## 「大切な人の記憶」を売ると、人物そのものが写真から抜け落ちたように見える。
func _draw_beloved(P: Callable, s: float, o: Vector2) -> void:
	P.call(-3, -3, 70, 58, Color("#3a3a48"))
	P.call(-1, -1, 66, 54, Color("#e0e0e8"))
	P.call(1, 1, 62, 44, Color("#3a4a6a"))
	# 橋の裏側
	P.call(1, 1, 62, 10, Color("#22283a"))
	P.call(1, 11, 62, 2, Color("#4a5470"))
	P.call(8, 13, 4, 32, Color("#2a3048"))
	P.call(52, 13, 4, 32, Color("#2a3048"))
	# 雨と川面
	for i in 14:
		var rx := PixelArt.hash2(i, 5) % 60
		var ry := 14 + PixelArt.hash2(i, 6) % 26
		P.call(2 + rx, ry, 1, 3, Color(0.7, 0.8, 1.0, 0.35))
	P.call(1, 38, 62, 7, Color("#1e2a40"))
	# 傘
	P.call(18, 14, 26, 4, Color("#7ad0ff"))
	P.call(21, 12, 20, 2, Color("#7ad0ff"))
	P.call(31, 18, 1, 8, Color("#9a9aae"))
	# 湊
	P.call(21, 20, 7, 7, Color("#e8c4a8"))
	P.call(21, 19, 7, 3, Color("#262838"))
	P.call(23, 23, 1, 1, Color("#101018"))
	P.call(26, 23, 1, 1, Color("#101018"))
	P.call(20, 27, 9, 12, Color("#34466e"))
	if lost:
		# 人物の形に、背景だけが残っている
		var seed := int(_t * 10.0)
		P.call(33, 19, 9, 20, Color("#3a4a6a"))
		for yy in range(19, 39, 2):
			var a := 0.12 + 0.1 * float(PixelArt.hash2(yy, seed) % 3)
			P.call(33, yy, 9, 1, Color(0.8, 0.85, 1.0, a))
	else:
		P.call(34, 20, 7, 7, Color("#f0d0c0"))
		P.call(33, 18, 9, 4, Color("#2a2040"))
		P.call(33, 20, 2, 8, Color("#2a2040"))
		P.call(40, 20, 2, 8, Color("#2a2040"))
		# 顔だけは、以前から思い出せない
		var seed2 := int(_t * 8.0)
		for yy in range(21, 27):
			for xx in range(35, 40):
				if PixelArt.hash2(xx + seed2, yy) % 3 != 0:
					P.call(xx, yy, 1, 1, Color(0.75, 0.7, 0.85, 0.9))
		P.call(33, 27, 9, 12, Color("#2a2040"))
		P.call(29, 30, 5, 2, Color("#f0d0c0"))
	P.call(1, 1, 62, 44, Color(0.7, 0.8, 1.0, 0.08))
	var f := UITheme.font()
	var caption := "約束の日に" if not lost else "（何も書かれていない）"
	draw_string(f, o + Vector2(2, 50) * s + Vector2(0, 2), caption, HORIZONTAL_ALIGNMENT_LEFT, -1, 16, Color("#5a5a68"))
	draw_string(f, Vector2(size.x / 2.0 - 70, o.y + 58 * s + 14), "タップ / E で閉じる", HORIZONTAL_ALIGNMENT_LEFT, -1, 12, UITheme.TEXT_DIM)
