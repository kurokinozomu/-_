class_name HUD
extends Control
## 画面上部のステータス・目標・場所名・調べるプロンプト・通知トースト。

signal menu_pressed

var status_panel: PanelContainer
var status_label: RichTextLabel
var objective_label: Label
var menu_button: Button
var place_label: Label
var prompt: PanelContainer
var prompt_label: Label
var toast_box: VBoxContainer

var _place_t := 0.0
var _prompt_world_pos: Variant = null
var world: World = null
var show_key_hint := true


func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_IGNORE

	status_panel = PanelContainer.new()
	status_panel.mouse_filter = Control.MOUSE_FILTER_IGNORE
	status_panel.add_theme_stylebox_override("panel", UITheme.box(Color(UITheme.BG, 0.8), Color(UITheme.LINE, 0.8), 1, 8, 4))
	add_child(status_panel)
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 0)
	v.mouse_filter = Control.MOUSE_FILTER_IGNORE
	status_panel.add_child(v)
	status_label = RichTextLabel.new()
	status_label.bbcode_enabled = true
	status_label.fit_content = true
	status_label.autowrap_mode = TextServer.AUTOWRAP_OFF
	status_label.scroll_active = false
	status_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	status_label.add_theme_font_size_override("normal_font_size", 14)
	v.add_child(status_label)
	objective_label = UITheme.make_label("", 12, UITheme.ACCENT)
	objective_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	v.add_child(objective_label)

	menu_button = UITheme.make_button("≡ メニュー")
	menu_button.focus_mode = Control.FOCUS_NONE
	menu_button.custom_minimum_size = Vector2(96, 32)
	menu_button.pressed.connect(func(): menu_pressed.emit())
	add_child(menu_button)

	place_label = UITheme.make_label("", 20, Color.WHITE)
	place_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	place_label.modulate.a = 0.0
	add_child(place_label)

	prompt = PanelContainer.new()
	prompt.mouse_filter = Control.MOUSE_FILTER_IGNORE
	prompt.add_theme_stylebox_override("panel", UITheme.box(Color(UITheme.BG, 0.9), UITheme.ACCENT, 1, 6, 2))
	prompt_label = UITheme.make_label("", 12, Color.WHITE)
	prompt.add_child(prompt_label)
	prompt.visible = false
	add_child(prompt)

	toast_box = VBoxContainer.new()
	toast_box.mouse_filter = Control.MOUSE_FILTER_IGNORE
	toast_box.alignment = BoxContainer.ALIGNMENT_END
	add_child(toast_box)

	GameState.changed.connect(refresh)
	resized.connect(_layout)
	refresh()
	_layout()


func _layout() -> void:
	var m := UITheme.safe_margins(get_viewport())
	status_panel.position = Vector2(m.x, m.y)
	menu_button.position = Vector2(size.x - m.z - menu_button.size.x, m.y)
	toast_box.size = Vector2(size.x * 0.7, 0)
	toast_box.position = Vector2(size.x * 0.15, size.y * 0.62)


func refresh() -> void:
	var left := GameState.days_left()
	var money_col := "#ff6a7a" if GameState.money < 0 else "#ffffff"
	var left_col := "#ff6a7a" if left <= 2 else "#e4e2f4"
	status_label.text = "[color=#8a88aa]%d日目[/color]　所持金 [color=%s]%s円[/color]　[color=#8a88aa]借金[/color] %s円　[color=%s]期限まで%d日[/color]" % [
		GameState.day, money_col, GameState.format_yen(GameState.money), GameState.format_yen(GameState.debt), left_col, left]
	objective_label.text = "◇ " + current_objective()
	status_panel.reset_size()


func current_objective() -> String:
	for o in GameData.objectives:
		if GameState.eval_cond(o.get("if", "")):
			return GameState.plain_text(str(o.get("text", "")))
	return ""


func flash_place(text: String) -> void:
	place_label.text = text
	place_label.reset_size()
	place_label.position = Vector2((size.x - place_label.size.x) / 2.0, size.y * 0.2)
	_place_t = 2.6


func set_prompt(obj: WorldObject, touch_mode: bool) -> void:
	if obj == null:
		prompt.visible = false
		_prompt_world_pos = null
		return
	var key := "" if touch_mode else "[E] "
	prompt_label.text = key + obj.prompt_text()
	prompt.reset_size()
	var top := obj.rect.position.y
	if obj.kind == "npc":
		top = obj.position.y - 24
	_prompt_world_pos = Vector2(obj.rect.get_center().x if obj.kind != "npc" else obj.position.x, top)
	prompt.visible = true


func toast(text: String, is_error: bool) -> void:
	var p := PanelContainer.new()
	p.mouse_filter = Control.MOUSE_FILTER_IGNORE
	p.add_theme_stylebox_override("panel", UITheme.box(Color(UITheme.BG, 0.92), UITheme.WARN if is_error else UITheme.ACCENT, 1, 10, 4))
	var l := UITheme.make_label(text, 14, UITheme.WARN if is_error else Color.WHITE)
	l.autowrap_mode = TextServer.AUTOWRAP_ARBITRARY
	l.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	p.add_child(l)
	toast_box.add_child(p)
	var life := 6.0 if is_error else 2.2
	var tw := create_tween()
	tw.tween_interval(life)
	tw.tween_property(p, "modulate:a", 0.0, 0.5)
	tw.tween_callback(p.queue_free)


func _process(delta: float) -> void:
	if _place_t > 0.0:
		_place_t -= delta
		place_label.modulate.a = clampf(minf(_place_t, 2.6 - _place_t) * 2.0, 0.0, 1.0)
	if prompt.visible and _prompt_world_pos != null and world != null:
		var sp := world.world_to_screen(_prompt_world_pos)
		# CanvasLayer 上の UI 座標に合わせる (stretch の都合で canvas transform と一致する)
		prompt.position = (sp - Vector2(prompt.size.x / 2.0, prompt.size.y + 2)).round()
