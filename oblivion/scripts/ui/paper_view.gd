class_name PaperView
extends Control
## 手紙・メモ・看板・ポスターなど「文字を読む」画面。await show_paper(id)。

signal closed

const STYLES := {
	"notice": {"bg": "#e8e4d8", "fg": "#1a1a24", "title": "#c02030", "border": "#8a8478"},
	"memo": {"bg": "#efe58a", "fg": "#2a2830", "title": "#2a2830", "border": "#b8a850"},
	"sign": {"bg": "#1e3a5a", "fg": "#ffffff", "title": "#9ad8ff", "border": "#5a8ab8"},
	"poster": {"bg": "#1a1028", "fg": "#f0e0ff", "title": "#ff5ad0", "border": "#ff5ad0"},
	"letter": {"bg": "#f2eee2", "fg": "#28283a", "title": "#3a4a7a", "border": "#a8a090"},
}

var card: PanelContainer
var title_label: RichTextLabel
var body_label: RichTextLabel
var hint: Label
var sketch: Control
var _image := ""
var _fs := 16
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
	# 本文と挿絵は横に並べる (横長の画面を生かして、縦にはみ出さないように)
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 18)
	row.mouse_filter = Control.MOUSE_FILTER_IGNORE
	v.add_child(row)
	row.add_child(body_label)
	# 手描きの挿絵 (文字が読めなくても、絵なら分かる)
	sketch = Control.new()
	sketch.custom_minimum_size = Vector2(0, 0)
	sketch.mouse_filter = Control.MOUSE_FILTER_IGNORE
	sketch.draw.connect(_draw_sketch)
	row.add_child(sketch)
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
	_image = str(p.get("image", ""))
	sketch.visible = _image != ""
	sketch.custom_minimum_size = Vector2(0, 0)
	Sound.se("paper")
	_render()
	visible = true
	_guard = 0.25
	await get_tree().process_frame
	await _center()
	await closed
	visible = false


func _render() -> void:
	# 文字サイズは BBCode で直接指定する (テーマ上書きは組版に反映されないことがあるため)
	title_label.text = "[center][font_size=%d]%s[/font_size][/center]" % [_fs + 4, GlitchText.to_bbcode(_raw_title, _seed)]
	body_label.text = "[font_size=%d]%s[/font_size]" % [_fs, GlitchText.to_bbcode(_raw_body, _seed)]


func _center() -> void:
	# 画面に収まる文字サイズを、行数から先に計算する
	# (RichTextLabel の高さは次フレームまで確定しないため、測ってから縮めるやり方は使えない)
	var avail := size.y - 34.0
	var extra := 16.0 * 2 + 10.0      # パネルの上下余白 + 段落間
	if _image != "":
		sketch.custom_minimum_size = Vector2(200, 90)
		sketch.queue_redraw()
	var lines := _raw_body.count("\n") + 1
	var chosen := 11
	var f := UITheme.font()
	for fs in [16, 14, 13, 12, 11]:
		var sep: int = 4 if fs >= 16 else 2
		var h: float = extra + lines * (f.get_height(fs) + sep)
		if _raw_title != "":
			h += f.get_height(fs + 4) + 10
		if h <= avail:
			chosen = fs
			break
	_fs = chosen
	body_label.add_theme_constant_override("line_separation", 4 if chosen >= 16 else 2)
	_render()
	# 文字の組版が終わって大きさが落ち着くまで数フレーム待つ
	var cs := Vector2.ZERO
	for i in 6:
		await get_tree().process_frame
		card.reset_size()
		var now := card.get_combined_minimum_size()
		if now == cs:
			break
		cs = now
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


func _draw_sketch() -> void:
	if _image != "bridge":
		return
	var w := sketch.size.x
	var ink := Color("#3a4a7a")
	var o := Vector2((w - 200.0) / 2.0, (sketch.size.y - 46.0) / 2.0)
	# 鉛筆書きの橋・雨・傘のふたり
	sketch.draw_line(o + Vector2(0, 10), o + Vector2(200, 10), ink, 2.0)
	sketch.draw_line(o + Vector2(0, 14), o + Vector2(200, 14), ink, 1.0)
	sketch.draw_line(o + Vector2(40, 14), o + Vector2(40, 42), ink, 2.0)
	sketch.draw_line(o + Vector2(160, 14), o + Vector2(160, 42), ink, 2.0)
	for i in 14:
		var rx := 6.0 + i * 14.0
		sketch.draw_line(o + Vector2(rx, 18 + (i % 3) * 4), o + Vector2(rx - 2, 24 + (i % 3) * 4), Color(ink, 0.5), 1.0)
	sketch.draw_arc(o + Vector2(100, 30), 14, PI, TAU, 12, ink, 2.0)
	sketch.draw_line(o + Vector2(100, 30), o + Vector2(100, 42), ink, 1.0)
	sketch.draw_circle(o + Vector2(93, 34), 3, ink)
	sketch.draw_circle(o + Vector2(107, 34), 3, ink)
	sketch.draw_line(o + Vector2(0, 44), o + Vector2(200, 44), Color(ink, 0.6), 1.0)
