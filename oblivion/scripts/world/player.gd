class_name Player
extends Node2D
## プレイヤー。入力 (キーボード + 仮想スティック) で移動し、World に衝突判定を問い合わせる。

const FOOT_W := 10.0
const FOOT_H := 6.0

var world: Node = null
var speed: float = 72.0
var facing: String = "down"
var control_enabled: bool = true
var touch_vector: Vector2 = Vector2.ZERO   ## TouchControls から毎フレーム渡される
var pal: Dictionary
var _anim_t: float = 0.0
var _moving: bool = false


func _ready() -> void:
	pal = PixelArt.pal_from(GameData.get_character("minato"))
	speed = float(GameData.cfg("player_speed", 72.0))


func dir_vector() -> Vector2:
	match facing:
		"up": return Vector2.UP
		"left": return Vector2.LEFT
		"right": return Vector2.RIGHT
	return Vector2.DOWN


func foot_rect_at(p: Vector2) -> Rect2:
	return Rect2(p.x - FOOT_W / 2.0, p.y - FOOT_H, FOOT_W, FOOT_H)


func read_input() -> Vector2:
	var v := Input.get_vector("move_left", "move_right", "move_up", "move_down")
	if touch_vector.length() > v.length():
		v = touch_vector
	return v.limit_length(1.0)


func _physics_process(delta: float) -> void:
	var v := Vector2.ZERO
	if control_enabled:
		v = read_input()
	_moving = v.length() > 0.15
	if _moving:
		if absf(v.x) > absf(v.y) + 0.05:
			facing = "right" if v.x > 0 else "left"
		else:
			facing = "down" if v.y > 0 else "up"
		_move(v * speed * delta)
		_anim_t += delta * (6.0 + 4.0 * v.length())
	else:
		_anim_t = 0.0
	queue_redraw()


func _move(m: Vector2) -> void:
	if world == null:
		position += m
		return
	# 軸ごとに移動し、壁に当たったら壁ぎりぎりまで寄せる
	# (低フレームレートで1歩が大きくても、手前で止まらないようにする)
	if m.x != 0.0 and not _step_axis(Vector2(m.x, 0)) and absf(m.y) < 0.01:
		_slide_around(Vector2(signf(m.x), 0), Vector2.DOWN)
	if m.y != 0.0 and not _step_axis(Vector2(0, m.y)) and absf(m.x) < 0.01:
		_slide_around(Vector2(0, signf(m.y)), Vector2.RIGHT)


## 1軸ぶんの移動。全量動けたら true、途中で止まったら false。
func _step_axis(m: Vector2) -> bool:
	var target := position + m
	if not world.is_blocked(foot_rect_at(target)):
		position = target
		return true
	var dir := m.normalized()
	var remaining := m.length()
	while remaining > 0.0:
		var step := minf(0.5, remaining)
		var p := position + dir * step
		if world.is_blocked(foot_rect_at(p)):
			break
		position = p
		remaining -= step
	return false


## 角に引っかかったとき、少しだけ横にずらして通す (ドアに入りやすくする)
func _slide_around(m: Vector2, axis: Vector2) -> void:
	for i in range(1, 7):
		for sgn in [1.0, -1.0]:
			var off: Vector2 = axis * float(i) * sgn
			if not world.is_blocked(foot_rect_at(position + off + m)):
				var nudge: Vector2 = off.normalized()
				if not world.is_blocked(foot_rect_at(position + nudge)):
					position += nudge
				return


func _draw() -> void:
	var step := 0
	if _moving:
		step = int(_anim_t) % 4
	var outdoor: bool = world != null and world.is_outdoor()
	PixelArt.draw_person(self, pal, facing, step, outdoor)
