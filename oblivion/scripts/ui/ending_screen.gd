class_name EndingScreen
extends Control
## エンディング表示。await show_ending(id)

signal closed

var label: RichTextLabel
var button: Button


func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_STOP
	visible = false
	var bg := ColorRect.new()
	bg.color = Color("#05040a")
	bg.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	add_child(bg)
	label = RichTextLabel.new()
	label.bbcode_enabled = true
	label.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	label.offset_top = 40
	label.offset_left = 40
	label.offset_right = -40
	label.offset_bottom = -70
	label.add_theme_font_size_override("normal_font_size", 16)
	label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(label)
	button = UITheme.make_button("タイトルへ", 180)
	button.pressed.connect(func(): closed.emit())
	add_child(button)
	resized.connect(func(): button.position = Vector2((size.x - button.size.x) / 2.0, size.y - 60))


func show_ending(id: String) -> void:
	var e: Dictionary = GameData.endings.get(id, {"title": "END", "subtitle": id, "body": ""})
	label.text = "[center][color=#8a88aa]%s[/color]\n[font_size=32]%s[/font_size]\n\n%s[/center]" % [
		str(e.get("title", "")), GameState.plain_text(str(e.get("subtitle", ""))), GameState.plain_text(str(e.get("body", "")))]
	visible = true
	modulate.a = 0.0
	var tw := create_tween()
	tw.tween_property(self, "modulate:a", 1.0, 1.2)
	button.grab_focus()
	await closed
	visible = false
