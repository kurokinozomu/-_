class_name GameMenu
extends Control
## ポーズメニュー: 状態確認・記憶一覧・セーブ・操作設定・タイトルへ。

signal closed
signal save_requested
signal title_requested
signal touch_mode_changed(mode: String)

var panel: PanelContainer
var info: RichTextLabel
var touch_button: Button
var save_button: Button
var close_button: Button
var _touch_mode := "auto"
var _seed := 0
var _t := 0.0
var _confirm_title := false
var title_button: Button
var volume_button: Button
var fullscreen_button: Button


func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_STOP
	visible = false
	var dim := ColorRect.new()
	dim.color = Color(0, 0, 0, 0.6)
	dim.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	add_child(dim)
	panel = PanelContainer.new()
	add_child(panel)
	var h := HBoxContainer.new()
	h.add_theme_constant_override("separation", 14)
	panel.add_child(h)
	info = RichTextLabel.new()
	info.bbcode_enabled = true
	info.custom_minimum_size = Vector2(330, 286)
	info.scroll_active = false
	info.add_theme_font_size_override("normal_font_size", 13)
	info.add_theme_constant_override("line_separation", 1)
	h.add_child(info)
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 6)
	h.add_child(v)
	close_button = UITheme.make_button("ゲームに戻る", 170)
	close_button.pressed.connect(func(): closed.emit())
	save_button = UITheme.make_button("セーブ", 170)
	save_button.pressed.connect(func(): save_requested.emit())
	touch_button = UITheme.make_button("", 170)
	touch_button.pressed.connect(_cycle_touch)
	volume_button = UITheme.make_button("", 170)
	volume_button.pressed.connect(func():
		volume_button.text = "音量: " + Sound.cycle_volume()
		Sound.se("select"))
	fullscreen_button = UITheme.make_button("全画面にする", 170)
	fullscreen_button.pressed.connect(func():
		WebPlatform.toggle_fullscreen()
		Sound.se("select")
		await get_tree().create_timer(0.3).timeout
		_update_fullscreen_label())
	title_button = UITheme.make_button("タイトルへ戻る", 170)
	title_button.pressed.connect(_on_title)
	for b in [close_button, save_button, touch_button, volume_button, fullscreen_button, title_button]:
		b.custom_minimum_size.y = 30
		v.add_child(b)
	var help := UITheme.make_label("PC：WASD/矢印で移動・E で調べる\nスマホ：左側をドラッグで移動\n　　　　右下のボタンで調べる", 11, UITheme.TEXT_DIM)
	v.add_child(help)
	resized.connect(_layout)
	_update_touch_label()


func open_menu(touch_mode: String) -> void:
	_touch_mode = touch_mode
	_confirm_title = false
	title_button.text = "タイトルへ戻る"
	_update_touch_label()
	volume_button.text = "音量: " + Sound.volume_name()
	fullscreen_button.visible = WebPlatform.can_toggle_fullscreen()
	_update_fullscreen_label()
	Sound.se("select")
	_render()
	visible = true
	_layout()
	close_button.grab_focus()


func _layout() -> void:
	panel.reset_size()
	var s := panel.get_combined_minimum_size()
	panel.position = ((size - s) / 2.0).floor()


func _render() -> void:
	var t := "[color=#ff5ad0]― 状態 ―[/color]\n"
	t += "%d日目　返済期限まであと%d日\n" % [GameState.day, GameState.days_left()]
	t += "所持金 %s円　借金 %s円\n生活費 %s円／日\n\n" % [GameState.format_yen(GameState.money), GameState.format_yen(GameState.debt), GameState.format_yen(int(GameData.cfg("daily_cost", 2000)))]
	t += "[color=#45e0ff]― 記憶 ―[/color]\n"
	for m in GameData.memories:
		if GameState.is_sold(m["id"]):
			t += "[color=#5a587a]×[/color] " + GlitchText.to_bbcode("[g]" + str(m["name"]) + "[/g]", _seed) + " [color=#5a587a]（売却済み）[/color]\n"
		else:
			t += "[color=#9dff9a]○[/color] %s\n" % str(m["name"])
	info.text = t


func _process(delta: float) -> void:
	if visible and GameState.sold.size() > 0:
		_t += delta
		if _t > 0.12:
			_t = 0.0
			_seed += 1
			_render()


func _update_fullscreen_label() -> void:
	fullscreen_button.text = "全画面を解除" if WebPlatform.is_fullscreen() else "全画面にする"


func _cycle_touch() -> void:
	var order := ["auto", "on", "off"]
	_touch_mode = order[(order.find(_touch_mode) + 1) % order.size()]
	_update_touch_label()
	touch_mode_changed.emit(_touch_mode)


func _update_touch_label() -> void:
	if touch_button:
		var names := {"auto": "自動", "on": "表示", "off": "非表示"}
		touch_button.text = "タッチ操作: " + str(names.get(_touch_mode, "自動"))


func _on_title() -> void:
	if not _confirm_title:
		_confirm_title = true
		title_button.text = "本当に戻る？(未セーブは消える)"
		return
	title_requested.emit()


func _unhandled_input(event: InputEvent) -> void:
	if visible and (event.is_action_pressed("cancel", false) or event.is_action_pressed("menu", false)):
		get_viewport().set_input_as_handled()
		closed.emit()
