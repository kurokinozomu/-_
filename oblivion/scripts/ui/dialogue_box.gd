class_name DialogueBox
extends Control
## 会話ウィンドウ。say() / choose() は await で使う。
##   await box.say("saeki", "smile", "こんにちは")
##   var idx: int = await box.choose(["はい", "いいえ"])

signal _advance
signal _chosen(index: int)

const CHARS_PER_SEC := 42.0
const INPUT_GUARD := 0.18

var panel: Panel
var portrait: PortraitView
var name_tab: PanelContainer
var name_label: RichTextLabel
var body: RichTextLabel
var next_mark: Label
var choice_box: VBoxContainer
var catcher: Control

var _raw: String = ""
var _name_raw: String = ""
var _shown: float = 0.0
var _total: int = 0
var _typing: bool = false
var _mode: String = "idle"   # idle / line / choice
var _guard: float = 0.0
var _glitch_t: float = 0.0
var _glitch_seed: int = 0
var _choice_buttons: Array[Button] = []


func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	visible = false
	# 画面全体のタップを受け取る透明レイヤー (会話中に下のUIを押させない)
	catcher = Control.new()
	catcher.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	catcher.mouse_filter = Control.MOUSE_FILTER_STOP
	catcher.gui_input.connect(_on_catcher_input)
	add_child(catcher)

	panel = Panel.new()
	panel.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(panel)

	portrait = PortraitView.new()
	panel.add_child(portrait)

	body = RichTextLabel.new()
	body.bbcode_enabled = true
	body.scroll_active = false
	body.fit_content = false
	body.mouse_filter = Control.MOUSE_FILTER_IGNORE
	body.add_theme_font_size_override("normal_font_size", 16)
	body.visible_characters_behavior = TextServer.VC_CHARS_AFTER_SHAPING
	panel.add_child(body)

	next_mark = UITheme.make_label("▼", 12, UITheme.ACCENT)
	panel.add_child(next_mark)

	name_tab = PanelContainer.new()
	name_tab.mouse_filter = Control.MOUSE_FILTER_IGNORE
	name_tab.add_theme_stylebox_override("panel", UITheme.box(Color("#1d1a3c"), UITheme.ACCENT, 1, 10, 3))
	add_child(name_tab)
	name_label = RichTextLabel.new()
	name_label.bbcode_enabled = true
	name_label.fit_content = true
	name_label.autowrap_mode = TextServer.AUTOWRAP_OFF
	name_label.scroll_active = false
	name_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	name_tab.add_child(name_label)

	choice_box = VBoxContainer.new()
	choice_box.add_theme_constant_override("separation", 6)
	add_child(choice_box)

	resized.connect(_layout)
	_layout()


func _layout() -> void:
	var m := UITheme.safe_margins(get_viewport())
	var w := size.x - m.x - m.z
	var h := 112.0
	panel.position = Vector2(m.x, size.y - m.w - h)
	panel.size = Vector2(w, h)
	var ps := 96.0
	portrait.position = Vector2(8, 8)
	portrait.size = Vector2(ps, ps)
	var text_x := 8.0 + ps + 12.0 if portrait.visible else 14.0
	body.position = Vector2(text_x, 12)
	body.size = Vector2(w - text_x - 16, h - 20)
	next_mark.position = Vector2(w - 22, h - 22)
	name_tab.position = panel.position + Vector2(text_x - 4, -26)
	choice_box.size = Vector2(minf(320.0, w * 0.6), 0)
	choice_box.position = Vector2(size.x - m.z - choice_box.size.x - 4, panel.position.y - 8 - choice_box.get_combined_minimum_size().y)


# ---------------------------------------------------------------- public API
func open() -> void:
	visible = true
	_guard = INPUT_GUARD


func close() -> void:
	visible = false
	_mode = "idle"
	_clear_choices()


func say(who: String, face: String, text: String) -> void:
	open()
	_set_speaker(who, face)
	_raw = GameState.resolve_text(text)
	_glitch_seed = randi() % 1000
	_render_body()
	_total = body.get_total_character_count()
	_shown = 0.0
	body.visible_characters = 0
	_typing = true
	_mode = "line"
	next_mark.visible = false
	await _advance
	_mode = "idle"


func choose(options: Array) -> int:
	open()
	_clear_choices()
	_mode = "choice"
	next_mark.visible = false
	for i in options.size():
		var b := UITheme.make_button(GameState.plain_text(str(options[i])))
		b.alignment = HORIZONTAL_ALIGNMENT_LEFT
		b.custom_minimum_size = Vector2(0, 38)
		var idx := i
		b.pressed.connect(func(): _on_choice(idx))
		choice_box.add_child(b)
		_choice_buttons.append(b)
	_layout()
	await get_tree().process_frame
	_layout()
	if _choice_buttons.size() > 0:
		_choice_buttons[0].grab_focus()
	_guard = INPUT_GUARD + 0.1
	var result: int = await _chosen
	_clear_choices()
	_mode = "idle"
	return result


# ---------------------------------------------------------------- internals
func _set_speaker(who: String, face: String) -> void:
	if who == "":
		portrait.set_face("", "")
		name_tab.visible = false
	else:
		var cd := GameData.get_character(who)
		_name_raw = GameState.resolve_text(str(cd.get("name", who)))
		name_label.text = GlitchText.to_bbcode(_name_raw, _glitch_seed)
		name_tab.visible = true
		portrait.set_face(who, face)
	_layout()


func _render_body() -> void:
	body.text = GlitchText.to_bbcode(_raw, _glitch_seed)
	if _name_raw != "" and name_tab.visible and GlitchText.has_glitch(_name_raw):
		name_label.text = GlitchText.to_bbcode(_name_raw, _glitch_seed)


func _clear_choices() -> void:
	for b in _choice_buttons:
		b.queue_free()
	_choice_buttons.clear()


func _process(delta: float) -> void:
	if not visible:
		return
	if _guard > 0.0:
		_guard -= delta
	if _mode == "line":
		if _typing:
			_shown += delta * CHARS_PER_SEC
			body.visible_characters = int(_shown)
			if int(_shown) >= _total:
				_typing = false
				body.visible_characters = -1
		next_mark.visible = not _typing and int(Time.get_ticks_msec() / 400.0) % 2 == 0
	# 文字化けした語をちらつかせる
	if GlitchText.has_glitch(_raw) or GlitchText.has_glitch(_name_raw):
		_glitch_t += delta
		if _glitch_t > 0.09:
			_glitch_t = 0.0
			_glitch_seed += 1
			var vc := body.visible_characters
			_render_body()
			body.visible_characters = vc


func _try_advance() -> void:
	if _guard > 0.0 or _mode != "line":
		return
	if _typing:
		_typing = false
		body.visible_characters = -1
		_guard = 0.08
	else:
		_advance.emit()


func _on_choice(idx: int) -> void:
	if _guard > 0.0 or _mode != "choice":
		return
	_chosen.emit(idx)


func _on_catcher_input(event: InputEvent) -> void:
	if event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT:
		_try_advance()
		accept_event()


func _unhandled_input(event: InputEvent) -> void:
	if not visible:
		return
	if _mode == "line" and event.is_action_pressed("interact", false):
		_try_advance()
		get_viewport().set_input_as_handled()
	elif _mode == "choice":
		if event.is_action_pressed("move_up", false) or event.is_action_pressed("move_down", false):
			var cur := -1
			for i in _choice_buttons.size():
				if _choice_buttons[i].has_focus():
					cur = i
			var d := -1 if event.is_action_pressed("move_up", false) else 1
			var n := clampi(cur + d, 0, _choice_buttons.size() - 1)
			if _choice_buttons.size() > 0:
				_choice_buttons[n].grab_focus()
			get_viewport().set_input_as_handled()
		elif event.is_action_pressed("interact", false):
			for i in _choice_buttons.size():
				if _choice_buttons[i].has_focus():
					_on_choice(i)
			get_viewport().set_input_as_handled()
