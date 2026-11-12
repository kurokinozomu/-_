class_name ShopUI
extends Control
## 記憶買取店の査定カウンター。記憶の一覧・鑑定内容・売却確認を扱う。
##   var sold_id: String = await shop.open_shop()   # 売らずに閉じたら ""

signal _done(result: String)

var root_panel: PanelContainer
var list_box: VBoxContainer
var title_label: Label
var detail_name: RichTextLabel
var detail_price: Label
var detail_text: RichTextLabel
var detail_hint: Label
var sell_button: Button
var back_button: Button
var status_label: Label
var confirm_layer: Control
var confirm_text: RichTextLabel
var confirm_yes: Button
var confirm_no: Button

var _selected: String = ""
var _buttons: Dictionary = {}
var _seed := 0
var _t := 0.0


func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_STOP
	visible = false
	var dim := ColorRect.new()
	dim.color = Color(0.02, 0.0, 0.06, 0.75)
	dim.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	dim.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(dim)

	root_panel = PanelContainer.new()
	root_panel.add_theme_stylebox_override("panel", UITheme.box(Color("#0e0a1c", 0.97), UITheme.PINK, 2, 12, 10))
	add_child(root_panel)
	var outer := VBoxContainer.new()
	outer.add_theme_constant_override("separation", 8)
	root_panel.add_child(outer)

	var head := HBoxContainer.new()
	outer.add_child(head)
	title_label = UITheme.make_label("記憶買取 メモリア ― 査定カウンター", 18, UITheme.PINK)
	title_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	head.add_child(title_label)
	status_label = UITheme.make_label("", 14, UITheme.TEXT_DIM)
	head.add_child(status_label)

	var body := HBoxContainer.new()
	body.add_theme_constant_override("separation", 10)
	body.size_flags_vertical = Control.SIZE_EXPAND_FILL
	outer.add_child(body)

	var left := ScrollContainer.new()
	left.custom_minimum_size = Vector2(196, 0)
	left.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	body.add_child(left)
	list_box = VBoxContainer.new()
	list_box.add_theme_constant_override("separation", 6)
	list_box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	left.add_child(list_box)

	var right := PanelContainer.new()
	right.add_theme_stylebox_override("panel", UITheme.box(Color("#151129"), UITheme.LINE, 1, 12, 8))
	right.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	body.add_child(right)
	var rv := VBoxContainer.new()
	rv.add_theme_constant_override("separation", 6)
	right.add_child(rv)
	detail_name = RichTextLabel.new()
	detail_name.bbcode_enabled = true
	detail_name.fit_content = true
	detail_name.scroll_active = false
	detail_name.add_theme_font_size_override("normal_font_size", 18)
	rv.add_child(detail_name)
	detail_price = UITheme.make_label("", 16, UITheme.GOOD)
	rv.add_child(detail_price)
	detail_text = RichTextLabel.new()
	detail_text.bbcode_enabled = true
	detail_text.size_flags_vertical = Control.SIZE_EXPAND_FILL
	detail_text.add_theme_font_size_override("normal_font_size", 13)
	detail_text.add_theme_constant_override("line_separation", 2)
	rv.add_child(detail_text)
	detail_hint = UITheme.make_label("", 11, UITheme.WARN)
	detail_hint.autowrap_mode = TextServer.AUTOWRAP_ARBITRARY
	rv.add_child(detail_hint)
	var btns := HBoxContainer.new()
	btns.add_theme_constant_override("separation", 8)
	btns.alignment = BoxContainer.ALIGNMENT_END
	rv.add_child(btns)
	back_button = UITheme.make_button("店を出る", 120)
	back_button.pressed.connect(func(): _done.emit(""))
	btns.add_child(back_button)
	sell_button = UITheme.make_button("この記憶を売る", 160)
	sell_button.add_theme_color_override("font_color", UITheme.PINK)
	sell_button.pressed.connect(_on_sell_pressed)
	btns.add_child(sell_button)

	_build_confirm()
	resized.connect(_layout)


func _build_confirm() -> void:
	confirm_layer = Control.new()
	confirm_layer.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	confirm_layer.mouse_filter = Control.MOUSE_FILTER_STOP
	confirm_layer.visible = false
	add_child(confirm_layer)
	var dim := ColorRect.new()
	dim.color = Color(0, 0, 0, 0.7)
	dim.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	confirm_layer.add_child(dim)
	var p := PanelContainer.new()
	p.name = "Box"
	p.add_theme_stylebox_override("panel", UITheme.box(Color("#120c22"), UITheme.WARN, 2, 18, 14))
	confirm_layer.add_child(p)
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 12)
	p.add_child(v)
	confirm_text = RichTextLabel.new()
	confirm_text.bbcode_enabled = true
	confirm_text.fit_content = true
	confirm_text.custom_minimum_size = Vector2(360, 0)
	confirm_text.scroll_active = false
	v.add_child(confirm_text)
	var h := HBoxContainer.new()
	h.alignment = BoxContainer.ALIGNMENT_CENTER
	h.add_theme_constant_override("separation", 16)
	v.add_child(h)
	confirm_no = UITheme.make_button("やめる", 130)
	confirm_yes = UITheme.make_button("売る", 130)
	confirm_yes.add_theme_color_override("font_color", UITheme.WARN)
	h.add_child(confirm_no)
	h.add_child(confirm_yes)
	confirm_no.pressed.connect(func():
		confirm_layer.visible = false
		sell_button.grab_focus())
	confirm_yes.pressed.connect(func():
		confirm_layer.visible = false
		_done.emit(_selected))


func _layout() -> void:
	var m := UITheme.safe_margins(get_viewport())
	root_panel.position = Vector2(m.x + 4, m.y + 4)
	root_panel.size = size - Vector2(m.x + m.z + 8, m.y + m.w + 8)
	var box: Control = confirm_layer.get_node("Box")
	box.reset_size()
	var bs := box.get_combined_minimum_size()
	box.position = ((size - bs) / 2.0).floor()


func open_shop() -> String:
	visible = true
	confirm_layer.visible = false
	_refresh_list()
	_layout()
	var first := ""
	for m in GameData.memories:
		if GameState.can_sell(m["id"]):
			first = m["id"]
			break
	if first == "" and GameData.memories.size() > 0:
		first = GameData.memories[0]["id"]
	_select(first)
	await get_tree().process_frame
	_layout()
	if _buttons.has(first):
		_buttons[first].grab_focus()
	var result: String = await _done
	visible = false
	return result


func _refresh_list() -> void:
	for c in list_box.get_children():
		c.queue_free()
	_buttons.clear()
	for m in GameData.memories:
		var id: String = m["id"]
		var b := UITheme.make_button("")
		b.alignment = HORIZONTAL_ALIGNMENT_LEFT
		b.custom_minimum_size = Vector2(188, 38)
		b.add_theme_font_size_override("font_size", 14)
		b.text = _list_label(m)
		if GameState.is_sold(id):
			b.add_theme_color_override("font_color", UITheme.TEXT_DIM)
		elif not bool(m.get("enabled", false)):
			b.add_theme_color_override("font_color", Color("#6a6890"))
		else:
			b.add_theme_color_override("font_color", Color(str(m.get("color", "#ffffff"))))
		b.pressed.connect(func():
			_select(id)
			# 決定したら「売る」ボタンへフォーカスを移す (キーボード/パッド操作向け)
			if GameState.can_sell(id):
				sell_button.grab_focus())
		b.focus_entered.connect(func(): _select(id))
		list_box.add_child(b)
		_buttons[id] = b
	status_label.text = "所持金 %s円 ／ 借金 %s円" % [GameState.format_yen(GameState.money), GameState.format_yen(GameState.debt)]


func _list_label(m: Dictionary) -> String:
	var id: String = m["id"]
	if GameState.is_sold(id):
		return "%s　売却済" % str(m.get("lost_name", "？？？"))
	if not bool(m.get("enabled", false)):
		return "%s　査定準備中" % str(m["name"])
	return "%s　%s円" % [str(m["name"]), GameState.format_yen(int(m["price"]))]


func _select(id: String) -> void:
	if id == "":
		return
	_selected = id
	_render_detail()


func _render_detail() -> void:
	var m := GameData.get_memory(_selected)
	if m.is_empty():
		return
	var id := _selected
	var col := Color(str(m.get("color", "#ffffff")))
	if GameState.is_sold(id):
		detail_name.text = "[color=#8a88aa]%s[/color]" % GlitchText.to_bbcode("[g]" + str(m["name"]) + "[/g]", _seed)
		detail_price.text = "売却済み"
		detail_text.text = "この記憶は、もうあなたの中にありません。\n\n棚のどこかで、淡く光っているはずです。"
		detail_hint.text = ""
		sell_button.disabled = true
		sell_button.text = "売却済み"
		return
	detail_name.text = "[color=#%s]%s[/color]" % [col.to_html(false), str(m["name"])]
	detail_price.text = "買取価格　%s円" % GameState.format_yen(int(m["price"]))
	var frags := ""
	for f in m.get("fragments", []):
		frags += "・" + GameState.plain_text(str(f)) + "\n"
	detail_text.text = "%s\n\n[color=#8a88aa]含まれる断片：[/color]\n%s" % [GameState.plain_text(str(m.get("appraisal", ""))), frags]
	if bool(m.get("enabled", false)):
		detail_hint.text = str(m.get("effects_hint", ""))
		sell_button.disabled = false
		sell_button.text = "この記憶を売る"
	else:
		detail_hint.text = "「そちらは、まだ査定の準備が整っておりません」"
		sell_button.disabled = true
		sell_button.text = "査定準備中"


func _on_sell_pressed() -> void:
	if not GameState.can_sell(_selected):
		return
	var m := GameData.get_memory(_selected)
	confirm_text.text = "[center]本当に [color=#%s]%s[/color] を売りますか？\n\n買取価格：%s円\n\n[color=#ff6a7a]売った記憶は、二度と戻りません。[/color][/center]" % [
		Color(str(m.get("color", "#ffffff"))).to_html(false), str(m["name"]), GameState.format_yen(int(m["price"]))]
	confirm_layer.visible = true
	_layout()
	confirm_no.grab_focus()


func _process(delta: float) -> void:
	if not visible:
		return
	_t += delta
	if _t > 0.12 and GameState.is_sold(_selected):
		_t = 0.0
		_seed += 1
		_render_detail()


func _unhandled_input(event: InputEvent) -> void:
	if not visible:
		return
	if event.is_action_pressed("cancel", false):
		get_viewport().set_input_as_handled()
		if confirm_layer.visible:
			confirm_layer.visible = false
			sell_button.grab_focus()
		else:
			_done.emit("")
	elif event.is_action_pressed("interact", false):
		# E キーでもフォーカス中のボタンを押せるようにする
		var f := get_viewport().gui_get_focus_owner()
		if f is Button and not f.disabled:
			get_viewport().set_input_as_handled()
			f.emit_signal("pressed")
