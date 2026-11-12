extends Control
## 画面空間の雨。屋外マップでのみ表示する。

const DROPS := 110

var _drops: Array = []
var _splashes: Array = []
var intensity: float = 1.0


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	for i in DROPS:
		_drops.append(_new_drop(true))


func _new_drop(anywhere: bool) -> Dictionary:
	var s := size if size.x > 0 else Vector2(640, 360)
	return {
		"p": Vector2(randf() * (s.x + 80) - 40, (randf() * s.y) if anywhere else -randf() * 40.0),
		"v": 340.0 + randf() * 160.0,
		"l": 6.0 + randf() * 8.0,
		"a": 0.10 + randf() * 0.22,
	}


func _process(delta: float) -> void:
	if not visible:
		return
	var s := size
	var wind := Vector2(-0.18, 1.0)
	for d in _drops:
		d["p"] += wind * d["v"] * delta
		if d["p"].y > s.y:
			if randf() < 0.35:
				_splashes.append({"p": Vector2(d["p"].x, s.y * (0.35 + randf() * 0.65)), "t": 0.0})
			var nd := _new_drop(false)
			d["p"] = nd["p"]
	for sp in _splashes:
		sp["t"] += delta
	_splashes = _splashes.filter(func(e): return e["t"] < 0.25)
	queue_redraw()


func _draw() -> void:
	var wind := Vector2(-0.18, 1.0).normalized()
	for d in _drops:
		var p: Vector2 = d["p"]
		draw_line(p, p - wind * d["l"], Color(0.65, 0.75, 1.0, d["a"] * intensity), 1.0)
	for sp in _splashes:
		var k: float = sp["t"] / 0.25
		var c: Vector2 = sp["p"]
		var col := Color(0.7, 0.8, 1.0, 0.35 * (1.0 - k))
		draw_line(c + Vector2(-2 - 3 * k, 0), c + Vector2(-1, 0), col, 1.0)
		draw_line(c + Vector2(1, 0), c + Vector2(2 + 3 * k, 0), col, 1.0)
