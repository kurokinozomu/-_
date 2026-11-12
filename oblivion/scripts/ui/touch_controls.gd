class_name TouchControls
extends Control
## スマホ用の仮想スティック (画面左半分のどこでも) と「調べる」ボタン (右下)。
## マルチタッチ対応: スティックを倒したまま、別の指でボタンを押せる。

signal interact_pressed

const STICK_R := 44.0
const KNOB_R := 18.0
const BTN_R := 38.0

var vector: Vector2 = Vector2.ZERO
var active: bool = false        ## 探索中のみ true
var enabled_mode: String = "auto"   ## auto / on / off
var label: String = "調べる"
var has_target: bool = false

var _stick_finger := -1
var _stick_center := Vector2.ZERO
var _stick_pos := Vector2.ZERO
var _btn_finger := -1
var _seen_touch := false


func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	_seen_touch = DisplayServer.is_touchscreen_available()


func is_shown() -> bool:
	match enabled_mode:
		"on": return true
		"off": return false
	return _seen_touch


func button_center() -> Vector2:
	var m := UITheme.safe_margins(get_viewport())
	return Vector2(size.x - m.z - BTN_R - 18, size.y - m.w - BTN_R - 22)


func reset() -> void:
	_stick_finger = -1
	_btn_finger = -1
	vector = Vector2.ZERO
	queue_redraw()


func _input(event: InputEvent) -> void:
	if event is InputEventScreenTouch:
		_seen_touch = true
		if not active or not is_shown():
			if not event.pressed:
				reset()
			return
		if event.pressed:
			if event.position.distance_to(button_center()) <= BTN_R + 14 and _btn_finger == -1:
				_btn_finger = event.index
				interact_pressed.emit()
			elif event.position.x < size.x * 0.5 and event.position.y > size.y * 0.18 and _stick_finger == -1:
				_stick_finger = event.index
				_stick_center = event.position
				_stick_pos = event.position
		else:
			if event.index == _stick_finger:
				_stick_finger = -1
				vector = Vector2.ZERO
			if event.index == _btn_finger:
				_btn_finger = -1
		queue_redraw()
	elif event is InputEventScreenDrag:
		if event.index == _stick_finger and active:
			_stick_pos = event.position
			var d := _stick_pos - _stick_center
			if d.length() > STICK_R:
				# スティックの中心を指に追従させる (大きく動かしても操作が途切れない)
				_stick_center = _stick_pos - d.normalized() * STICK_R
				d = _stick_pos - _stick_center
			var v := d / STICK_R
			vector = v if v.length() > 0.2 else Vector2.ZERO
			queue_redraw()


func _process(_delta: float) -> void:
	if not active and (_stick_finger != -1 or vector != Vector2.ZERO):
		reset()
	queue_redraw()


func _draw() -> void:
	if not active or not is_shown():
		return
	var f := UITheme.font()
	# スティック
	if _stick_finger != -1:
		draw_circle(_stick_center, STICK_R, Color(0.1, 0.1, 0.2, 0.35))
		draw_arc(_stick_center, STICK_R, 0, TAU, 40, Color(0.6, 0.6, 0.9, 0.5), 2.0)
		var kp := _stick_center + vector * STICK_R
		draw_circle(kp, KNOB_R, Color(0.45, 0.85, 1.0, 0.55))
	else:
		var m := UITheme.safe_margins(get_viewport())
		var hint_c := Vector2(m.x + STICK_R + 26, size.y - m.w - STICK_R - 22)
		draw_arc(hint_c, STICK_R, 0, TAU, 40, Color(0.6, 0.6, 0.9, 0.22), 2.0)
		draw_circle(hint_c, KNOB_R, Color(0.6, 0.6, 0.9, 0.15))
	# 調べるボタン
	var bc := button_center()
	var pressed := _btn_finger != -1
	var col := Color(1.0, 0.35, 0.82, 0.75 if has_target else 0.3)
	draw_circle(bc, BTN_R, Color(0.08, 0.05, 0.15, 0.55 if not pressed else 0.8))
	draw_arc(bc, BTN_R, 0, TAU, 48, col, 3.0)
	var text := label if has_target else "調べる"
	var fs := 14
	var tw := f.get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, -1, fs).x
	draw_string(f, bc + Vector2(-tw / 2.0, fs * 0.35), text, HORIZONTAL_ALIGNMENT_LEFT, -1, fs, Color(1, 1, 1, 0.95 if has_target else 0.5))
