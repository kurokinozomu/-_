class_name WorldObject
extends Node2D
## マップ上の NPC・小物・看板・出入口。maps.json の objects の1要素に対応する。

const TILE := PixelArt.TILE

var data: Dictionary = {}
var kind: String = "prop"
var rect: Rect2 = Rect2()          ## 当たり判定/調べる範囲 (ワールド座標, px)
var solid_rect: Rect2 = Rect2()    ## 通行不可範囲 (無い場合は size=0)
var facing: String = "down"
var pal: Dictionary = {}
var font: Font
var _t: float = 0.0
var _anim_speed: float = 0.0
var _base_facing: String = "down"
var _look_timer: float = 0.0
var _redraw_acc: float = 0.0


func setup(d: Dictionary, p_font: Font) -> void:
	data = d
	font = p_font
	kind = str(d.get("kind", "prop"))
	name = str(d.get("id", "obj"))
	if kind == "npc":
		var p: Array = d.get("pos", [0, 0])
		position = Vector2(float(p[0]) * TILE, float(p[1]) * TILE)
		var r: Array = d.get("rect", [])
		if r.size() == 4:
			rect = _tile_rect(r)
		else:
			rect = Rect2(position.x - 8, position.y - 12, 16, 14)
		solid_rect = Rect2(position.x - 6, position.y - 5, 12, 6)
		facing = str(d.get("facing", "down"))
		_base_facing = facing
		pal = PixelArt.pal_from(GameData.get_character(str(d.get("char", ""))))
		_anim_speed = 1.0
	else:
		rect = _tile_rect(d.get("rect", [0, 0, 1, 1]))
		# y ソート用に原点を矩形の下端に置く
		position = Vector2(rect.position.x, rect.end.y)
		if bool(d.get("solid", false)):
			solid_rect = rect
		if kind == "deco":
			z_index = -1
		if kind == "sign":
			z_index = -1
	if d.has("vanish"):
		modulate = Color(0.85, 0.85, 1.0, 0.7)
	_t = randf() * 10.0


static func _tile_rect(r: Array) -> Rect2:
	return Rect2(float(r[0]) * TILE, float(r[1]) * TILE, float(r[2]) * TILE, float(r[3]) * TILE)


func is_interactable() -> bool:
	return data.has("script") or kind == "warp"


func prompt_text() -> String:
	return str(data.get("prompt", "調べる"))


## プレイヤーの方を向く (会話開始時)
func face_towards(p: Vector2) -> void:
	if kind != "npc":
		return
	var d := p - position
	if absf(d.x) > absf(d.y):
		facing = "right" if d.x > 0 else "left"
	else:
		facing = "down" if d.y > 0 else "up"
	_look_timer = 4.0
	queue_redraw()


func _process(delta: float) -> void:
	_t += delta
	if _look_timer > 0.0:
		_look_timer -= delta
		if _look_timer <= 0.0:
			facing = _base_facing
	# アニメーションするものだけ、毎秒15回まで再描画する (モバイルの負荷対策)
	if kind == "npc" or kind == "sign" or _is_animated_prop():
		_redraw_acc += delta
		if _redraw_acc >= 1.0 / 15.0:
			_redraw_acc = 0.0
			queue_redraw()


func _is_animated_prop() -> bool:
	var s := str(data.get("sprite", ""))
	return s in ["phone", "letter", "memo", "lamp", "vending", "yatai", "jars", "jarwall", "counter", "photo", "photo_b", "atm", "conveyor"]


func _draw() -> void:
	match kind:
		"npc":
			# ときどき体重を移す程度の待機モーション
			var idle_step := 1 if int(_t * 0.7) % 5 == 0 else 0
			PixelArt.draw_person(self, pal, facing, idle_step, false)
		"warp":
			pass
		"sign":
			var local := Rect2(Vector2(0, -rect.size.y), rect.size)
			var label := GameState.plain_read(str(data.get("label", "")))
			var broken := label.contains("？")
			PixelArt.draw_neon_sign(self, local, label, Color(str(data.get("color", "#ff5ad0"))), _t, font, broken)
		_:
			var local2 := Rect2(Vector2(0, -rect.size.y), rect.size)
			PixelArt.draw_prop(self, str(data.get("sprite", "")), local2, _t, _prop_state())


func _prop_state() -> Dictionary:
	var s := str(data.get("sprite", ""))
	match s:
		"phone":
			return {"ringing": GameState.has_flag("call_pending") and GameState.map_id == "home"}
		"letter":
			return {"new": not GameState.has_flag("read_notice")}
		"memo":
			return {"new": not GameState.has_flag("read_memo_mother")}
		"photo":
			return {"lost": GameState.is_sold("mother")}
		"photo_b":
			return {"lost": GameState.is_sold("beloved")}
	return {}
