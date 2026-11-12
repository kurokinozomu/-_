class_name EndingScreen
extends Control
## エンディング表示。結末ごとに背景の情景を描き分ける。 await show_ending(id)

signal closed

var label: RichTextLabel
var button: Button
var ending_id := ""
var _t := 0.0


func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_STOP
	visible = false
	label = RichTextLabel.new()
	label.bbcode_enabled = true
	label.fit_content = true
	label.scroll_active = false
	label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	label.add_theme_font_size_override("normal_font_size", 16)
	add_child(label)
	button = UITheme.make_button("タイトルへ", 180)
	button.pressed.connect(func(): closed.emit())
	add_child(button)
	resized.connect(_layout)


func _layout() -> void:
	label.size = Vector2(size.x - 60, 0)
	label.position = Vector2(30, size.y * 0.1)
	button.position = Vector2((size.x - button.size.x) / 2.0, size.y - 56)


func show_ending(id: String) -> void:
	ending_id = id
	var e: Dictionary = GameData.endings.get(id, {"title": "END", "subtitle": id, "body": ""})
	label.text = "[center][color=#8a88aa]%s[/color]\n[font_size=30]%s[/font_size]\n\n%s[/center]" % [
		str(e.get("title", "")), GameState.plain_text(str(e.get("subtitle", ""))), GameState.plain_text(str(e.get("body", "")))]
	visible = true
	_layout()
	modulate.a = 0.0
	button.visible = false
	var tw := create_tween()
	tw.tween_property(self, "modulate:a", 1.0, 1.5)
	tw.tween_interval(1.5)
	tw.tween_callback(func():
		button.visible = true
		button.grab_focus())
	await closed
	Sound.se("confirm")
	visible = false


func _process(delta: float) -> void:
	if visible:
		_t += delta
		queue_redraw()


func _unhandled_input(event: InputEvent) -> void:
	if visible and button.visible and event.is_action_pressed("interact", false):
		get_viewport().set_input_as_handled()
		closed.emit()


func _draw() -> void:
	var s := size
	var sky_top := Color("#05040a")
	var sky_bot := Color("#0d0c1c")
	var raining := true
	match ending_id:
		"protected":
			sky_top = Color("#1a2240")
			sky_bot = Color("#e8b8a0")
			raining = false
		"secret":
			sky_top = Color("#101828")
			sky_bot = Color("#3a4a6a")
			raining = false
		"loop":
			sky_top = Color("#12061a")
			sky_bot = Color("#2a0a30")
	# 空のグラデーション
	var steps := 24
	for i in steps:
		var k := float(i) / steps
		draw_rect(Rect2(0, s.y * k, s.x, s.y / steps + 1), sky_top.lerp(sky_bot, k))
	var gy := s.y * 0.72
	match ending_id:
		"protected", "secret":
			# 橋と、雨上がりの光
			if ending_id == "protected":
				draw_circle(Vector2(s.x * 0.5, gy), s.x * 0.18, Color(1.0, 0.85, 0.6, 0.25))
				draw_circle(Vector2(s.x * 0.5, gy), s.x * 0.09, Color(1.0, 0.9, 0.7, 0.35))
			draw_rect(Rect2(0, gy - 70, s.x, 16), Color("#0c0c18"))
			draw_rect(Rect2(s.x * 0.2, gy - 54, 14, 54), Color("#0c0c18"))
			draw_rect(Rect2(s.x * 0.8, gy - 54, 14, 54), Color("#0c0c18"))
			_person(Vector2(s.x * 0.47, gy), Color("#0c0c18"))
			var with_nagi := ending_id == "protected" or (not GameState.is_sold("beloved") and not GameState.has_flag("nagi_gone"))
			if with_nagi:
				_person(Vector2(s.x * 0.53, gy), Color("#0c0c18"))
		"forgotten":
			# 誰もいない部屋と、ゴミ袋の中の写真立て
			draw_rect(Rect2(s.x * 0.3, gy - 120, s.x * 0.4, 120), Color("#0a0a14"))
			draw_rect(Rect2(s.x * 0.38, gy - 100, 60, 44), Color("#1a2a40"))
			draw_rect(Rect2(s.x * 0.55, gy - 40, 40, 40), Color("#141420"))
			draw_rect(Rect2(s.x * 0.56, gy - 52, 18, 14), Color("#3a3a4a"))
		"paid", "seized":
			for i in 14:
				var bw := 30.0 + float(PixelArt.hash2(i, 3) % 40)
				var bh := 40.0 + float(PixelArt.hash2(i, 4) % 120)
				draw_rect(Rect2(i * s.x / 12.0 - 10, gy - bh, bw, bh), Color("#0a0a16"))
			_person(Vector2(s.x * 0.5, gy), Color("#000000"))
		"loop":
			# 開く扉と、メモリアのネオン
			draw_rect(Rect2(s.x * 0.38, gy - 110, s.x * 0.24, 110), Color("#1a0a24"))
			var a := 0.6 + 0.4 * sin(_t * 3.0)
			draw_rect(Rect2(s.x * 0.36, gy - 130, s.x * 0.28, 12), Color(1.0, 0.35, 0.82, a))
			draw_rect(Rect2(s.x * 0.45, gy - 80, s.x * 0.1, 80), Color(1.0, 0.35, 0.82, 0.25 * a))
			_person(Vector2(s.x * 0.5, gy + 30), Color("#000000"))
	draw_rect(Rect2(0, gy, s.x, s.y - gy), Color(0, 0, 0, 0.55))
	if raining:
		for i in 90:
			var x := fmod(float(PixelArt.hash2(i, 1) % 1000) + _t * 40.0, s.x)
			var y := fmod(float(PixelArt.hash2(i, 2) % 1000) + _t * 420.0, s.y)
			draw_line(Vector2(x, y), Vector2(x - 3, y + 12), Color(0.6, 0.7, 1.0, 0.2), 1.0)
	# 本文を読みやすく (文字の後ろだけ暗くする)
	draw_rect(Rect2(0, 0, s.x, s.y), Color(0, 0, 0, 0.2))
	var lr := Rect2(label.position - Vector2(0, 12), label.size + Vector2(0, 24))
	var panel_w := minf(s.x - 40.0, 560.0)
	draw_rect(Rect2((s.x - panel_w) / 2.0, lr.position.y, panel_w, lr.size.y), Color(0.02, 0.02, 0.05, 0.62))


func _person(feet: Vector2, c: Color) -> void:
	draw_rect(Rect2(feet.x - 6, feet.y - 34, 12, 34), c)
	draw_circle(feet + Vector2(0, -40), 7, c)
