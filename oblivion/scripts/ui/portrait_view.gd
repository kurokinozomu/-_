class_name PortraitView
extends Control
## 会話中の顔グラフィック (32x32 ドットを拡大描画)。

var char_id: String = ""
var expr: String = "normal"
var _t: float = 0.0


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE


func set_face(id: String, e: String) -> void:
	char_id = id
	expr = e if e != "" else "normal"
	visible = id != ""
	queue_redraw()


func _process(delta: float) -> void:
	_t += delta
	if visible and (char_id == "mother" or char_id == "voice"):
		queue_redraw()


func _draw() -> void:
	if char_id == "":
		return
	var s := floorf(minf(size.x, size.y) / 32.0)
	s = maxf(s, 1.0)
	var origin := ((size - Vector2(32, 32) * s) / 2.0).floor()
	var cd := GameData.get_character(char_id)
	var kind := str(cd.get("portrait", ""))
	if kind == "phone":
		PixelArt.draw_phone_portrait(self, origin, s, _t, false)
	elif kind == "phone_noise":
		PixelArt.draw_phone_portrait(self, origin, s, _t, true)
	else:
		PixelArt.draw_portrait(self, origin, s, PixelArt.pal_from(cd), expr)
	draw_rect(Rect2(origin, Vector2(32, 32) * s), UITheme.LINE, false, 2.0)
