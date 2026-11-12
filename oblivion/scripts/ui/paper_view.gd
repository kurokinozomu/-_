class_name PaperView
extends Control
## 手紙・メモ・看板・ポスターなど「文字を読む」画面。await show_paper(id)。

signal closed

const STYLES := {
	"notice": {"bg": "#e8e4d8", "fg": "#1a1a24", "title": "#c02030", "border": "#8a8478"},
	"memo": {"bg": "#efe58a", "fg": "#2a2830", "title": "#2a2830", "border": "#b8a850"},
	"sign": {"bg": "#1e3a5a", "fg": "#ffffff", "title": "#9ad8ff", "border": "#5a8ab8"},
	"poster": {"bg": "#1a1028", "fg": "#f0e0ff", "title": "#ff5ad0", "border": "#ff5ad0"},
}

var card: PanelContainer
var title_label: RichTextLabel
var body_label: RichTextLabel
var hint: Label
var _raw_title := ""
var _raw_body := ""
var _seed := 0
var _t := 0.0
var _guard := 0.0


func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_STOP
	visible = false
	var dim := ColorRect.new()
	dim.color = Color(0, 0, 0, 0.6)
	dim.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	dim.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(dim)
	card = PanelContainer.new()
	card.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(card)
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 10)
	card.add_child(v)
	title_label = _rich(20)
	body_label = _rich(16)
	v.add_child(title_label)
	v.add_child(body_label)
	hint = UITheme.make_label("タップ / E で閉じる", 12, UITheme.TEXT_DIM)
	add_child(hint)
	gui_input.connect(_on_gui_input)


func _rich(fs: int) -> RichTextLabel:
	var r := RichTextLabel.new()
	r.bbcode_enabled = true
	r.fit_content = true
	r.scroll_active = false
	r.autowrap_mode = TextServer.AUTOWRAP_OFF
	r.mouse_filter = Control.MOUSE_FILTER_IGNORE
	r.add_theme_font_size_override("normal_font_size", fs)
	return r


func show_paper(id: String) -> void:
	var p: Dictionary = GameData.papers.get(id, {"title": id, "body": "(データなし)", "style": "memo"})
	var st: Dictionary = STYLES.get(str(p.get("style", "memo")), STYLES["memo"])
	card.add_theme_stylebox_override("panel", UITheme.box(Color(st["bg"]), Color(st["border"]), 3, 22, 16))
	title_label.add_theme_color_override("default_color", Color(st["title"]))
	body_label.add_theme_color_override("default_color", Color(st["fg"]))
	_raw_title = GameState.read_text(str(p.get("title", "")))
	_raw_body = GameState.read_text(str(p.get("body", "")))
	title_label.visible = _raw_title != ""
	_render()
	visible = true
	_guard = 0.25
	await get_tree().process_frame
	_center()
	await closed
	visible = false


func _render() -> void:
	title_label.text = "[center]" + GlitchText.to_bbcode(_raw_title, _seed) + "[/center]"
	body_label.text = GlitchText.to_bbcode(_raw_body, _seed)


func _center() -> void:
	# 画面に収まるまで文字を小さくする (小さい画面・長文対策)
	var avail := size.y - 40.0
	for fs in [16, 14, 13, 12, 11]:
		body_label.add_theme_font_size_override("normal_font_size", fs)
		title_label.add_theme_font_size_override("normal_font_size", fs + 4)
		body_label.add_theme_constant_override("line_separation", 2 if fs < 16 else 4)
		card.reset_size()
		if card.get_combined_minimum_size().y <= avail:
			break
	card.reset_size()
	var cs := card.get_combined_minimum_size()
	card.size = cs
	card.position = ((size - cs) / 2.0).floor()
	card.position.y = maxf(card.position.y - 8.0, 4.0)
	hint.position = Vector2((size.x - hint.get_minimum_size().x) / 2.0, minf(card.position.y + cs.y + 4, size.y - 16))


func _process(delta: float) -> void:
	if not visible:
		return
	_guard -= delta
	_t += delta
	if (GlitchText.has_glitch(_raw_body) or GlitchText.has_glitch(_raw_title)) and _t > 0.1:
		_t = 0.0
		_seed += 1
		_render()


func _on_gui_input(event: InputEvent) -> void:
	if event is InputEventMouseButton and event.pressed and _guard <= 0.0:
		accept_event()
		closed.emit()


func _unhandled_input(event: InputEvent) -> void:
	if visible and _guard <= 0.0 and (event.is_action_pressed("interact", false) or event.is_action_pressed("cancel", false)):
		get_viewport().set_input_as_handled()
		closed.emit()
