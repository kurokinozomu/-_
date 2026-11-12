class_name TitleScreen
extends Control
## タイトル画面。雨の街のシルエットとロゴを描画する。

signal new_game_requested
signal continue_requested

var new_button: Button
var cont_button: Button
var confirm_overwrite := false
var info_label: Label
var _t := 0.0
var buttons: VBoxContainer


func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_STOP
	buttons = VBoxContainer.new()
	buttons.add_theme_constant_override("separation", 10)
	add_child(buttons)
	cont_button = UITheme.make_button("つづきから", 220)
	new_button = UITheme.make_button("はじめから", 220)
	buttons.add_child(cont_button)
	buttons.add_child(new_button)
	cont_button.pressed.connect(func(): continue_requested.emit())
	new_button.pressed.connect(_on_new)
	info_label = UITheme.make_label("", 12, UITheme.TEXT_DIM)
	info_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	add_child(info_label)
	var rain := Control.new()
	rain.set_script(load("res://scripts/ui/rain_layer.gd"))
	add_child(rain)
	move_child(rain, 0)
	resized.connect(_layout)
	refresh()


func refresh() -> void:
	confirm_overwrite = false
	new_button.text = "はじめから"
	cont_button.disabled = not GameState.has_save()
	var info := "v%s　Phase 1 プロトタイプ" % str(ProjectSettings.get_setting("application/config/version", ""))
	if GameData.load_errors.size() > 0:
		info = "データ読み込みエラー: " + GameData.load_errors[0]
		info_label.add_theme_color_override("font_color", UITheme.WARN)
	info_label.text = info
	_layout()
	await get_tree().process_frame
	if not cont_button.disabled:
		cont_button.grab_focus()
	else:
		new_button.grab_focus()


func _on_new() -> void:
	if GameState.has_save() and not confirm_overwrite:
		confirm_overwrite = true
		new_button.text = "セーブを消して始める？"
		return
	new_game_requested.emit()


func _layout() -> void:
	buttons.reset_size()
	var bs := buttons.get_combined_minimum_size()
	buttons.position = Vector2((size.x - bs.x) / 2.0, size.y * 0.58)
	info_label.size = Vector2(size.x, 20)
	var m := UITheme.safe_margins(get_viewport())
	info_label.position = Vector2(0, size.y - m.w - 20)


func _process(delta: float) -> void:
	_t += delta
	queue_redraw()


func _unhandled_input(event: InputEvent) -> void:
	if visible and event.is_action_pressed("interact", false):
		var f := get_viewport().gui_get_focus_owner()
		if f is Button and not f.disabled:
			get_viewport().set_input_as_handled()
			f.emit_signal("pressed")


func _draw() -> void:
	draw_rect(Rect2(Vector2.ZERO, size), Color("#07060f"))
	# 遠景のビル
	var gy := size.y * 0.78
	for i in 26:
		var bw := 18.0 + float(PixelArt.hash2(i, 1) % 30)
		var bh := 60.0 + float(PixelArt.hash2(i, 2) % 140)
		var bx := float(i) * size.x / 22.0 - 20.0
		draw_rect(Rect2(bx, gy - bh, bw, bh), Color("#11102a"))
		for k in 6:
			if PixelArt.hash2(i, k + 5) % 4 == 0:
				var wy := gy - bh + 8 + k * 14
				var on := 0.6 if PixelArt.hash2(i * 3 + k, int(_t * 0.5)) % 13 != 0 else 0.1
				draw_rect(Rect2(bx + 4, wy, 3, 4), Color(0.9, 0.75, 0.45, on * 0.5))
	draw_rect(Rect2(0, gy, size.x, size.y - gy), Color("#0a0918"))
	# 水面の反射
	for k in 18:
		var ry := gy + 6 + k * 5
		var rx := fmod(float(PixelArt.hash2(k, 4) % 600) + _t * (6 + k), size.x)
		draw_rect(Rect2(rx, ry, 30 + k * 2, 1), Color(1.0, 0.35, 0.82, 0.12))
	# ロゴ
	var f := UITheme.font()
	var title := "忘却都市"
	var fs := 56
	var tw := f.get_string_size(title, HORIZONTAL_ALIGNMENT_LEFT, -1, fs).x
	var pos := Vector2((size.x - tw) / 2.0, size.y * 0.36)
	var g := 1.0
	if int(_t * 10.0) % 37 == 0:
		g = 3.0
	draw_string(f, pos + Vector2(-2 * g, 0), title, HORIZONTAL_ALIGNMENT_LEFT, -1, fs, Color(0.27, 0.88, 1.0, 0.55))
	draw_string(f, pos + Vector2(2 * g, 0), title, HORIZONTAL_ALIGNMENT_LEFT, -1, fs, Color(1.0, 0.35, 0.82, 0.55))
	draw_string(f, pos, title, HORIZONTAL_ALIGNMENT_LEFT, -1, fs, Color(0.95, 0.94, 1.0))
	var sub := "― Project OBLIVION ―"
	var sw := f.get_string_size(sub, HORIZONTAL_ALIGNMENT_LEFT, -1, 16).x
	draw_string(f, Vector2((size.x - sw) / 2.0, pos.y + 30), sub, HORIZONTAL_ALIGNMENT_LEFT, -1, 16, Color(0.7, 0.68, 0.9))
	var tag := "生きるために、人生を忘れていく。"
	var tgw := f.get_string_size(tag, HORIZONTAL_ALIGNMENT_LEFT, -1, 14).x
	draw_string(f, Vector2((size.x - tgw) / 2.0, pos.y + 56), tag, HORIZONTAL_ALIGNMENT_LEFT, -1, 14, Color(0.55, 0.53, 0.7, 0.6 + 0.3 * sin(_t)))
