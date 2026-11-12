class_name World
extends Node2D
## 現在のマップ (タイル・オブジェクト・プレイヤー・カメラ) を管理する。
## タイルはグリッド判定で衝突させる (物理エンジン不使用: 軽量でモバイル向き)。

signal warp_triggered(to_map: String, spawn: String)
signal target_changed(obj: WorldObject)

const TILE := PixelArt.TILE
const ZOOM := 2.0
const FLOOR_CHARS := {"wood": ".", "shop": ",", "street": "S"}

var map_id: String = ""
var map: Dictionary = {}
var grid: PackedStringArray = []
var map_w: int = 0
var map_h: int = 0
var objects: Array[WorldObject] = []
var player: Player
var camera: Camera2D
var tile_layer: Node2D
var entities: Node2D
var font: Font
var warp_armed: bool = false
var current_target: WorldObject = null


func _ready() -> void:
	font = load("res://assets/fonts/DotGothic16-Regular.ttf")
	tile_layer = Node2D.new()
	tile_layer.name = "TileLayer"
	tile_layer.z_index = -10
	tile_layer.set_script(load("res://scripts/world/tile_layer.gd"))
	add_child(tile_layer)
	entities = Node2D.new()
	entities.name = "Entities"
	entities.y_sort_enabled = true
	add_child(entities)
	player = Player.new()
	player.name = "Player"
	player.world = self
	entities.add_child(player)
	camera = Camera2D.new()
	camera.zoom = Vector2(ZOOM, ZOOM)
	add_child(camera)
	camera.make_current()
	GameState.changed.connect(_on_state_changed)


func is_outdoor() -> bool:
	return bool(map.get("outdoor", false))


func map_name() -> String:
	return GameState.plain_text(str(map.get("name", "")))


func pixel_size() -> Vector2:
	return Vector2(map_w * TILE, map_h * TILE)


func load_map(id: String, spawn: String, saved_pos: Variant = null, saved_facing: String = "") -> bool:
	if not GameData.maps.has(id):
		push_error("マップがありません: " + id)
		return false
	map_id = id
	map = GameData.maps[id]
	grid = PackedStringArray(map.get("tiles", []))
	map_h = grid.size()
	map_w = grid[0].length() if map_h > 0 else 0
	tile_layer.set("grid", grid)
	tile_layer.set("floor_ch", FLOOR_CHARS.get(str(map.get("floor", "wood")), "."))
	tile_layer.queue_redraw()
	_rebuild_objects()
	# プレイヤー配置
	var spawns: Dictionary = map.get("spawns", {})
	var sp: Array = spawns.get(spawn, spawns.values()[0] if spawns.size() > 0 else [1, 1, "down"])
	if saved_pos is Vector2:
		player.position = saved_pos
		player.facing = saved_facing if saved_facing != "" else "down"
	else:
		player.position = Vector2(float(sp[0]) * TILE, float(sp[1]) * TILE)
		player.facing = str(sp[2]) if sp.size() > 2 else "down"
	warp_armed = false
	GameState.map_id = id
	GameState.spawn_name = spawn
	_update_camera(true)
	_update_target()
	return true


func _rebuild_objects() -> void:
	for o in objects:
		o.queue_free()
	objects.clear()
	for d in map.get("objects", []):
		if d.has("if") and not GameState.eval_cond(d["if"]):
			continue
		var o := WorldObject.new()
		o.setup(d, font)
		entities.add_child(o)
		objects.append(o)


func _on_state_changed() -> void:
	if map.is_empty():
		return
	# 条件付きオブジェクトの表示を更新する (メモが現れる、など)
	var want: Array = []
	for d in map.get("objects", []):
		if not d.has("if") or GameState.eval_cond(d["if"]):
			want.append(str(d.get("id", "")))
	var have: Array = []
	for o in objects:
		have.append(str(o.data.get("id", "")))
	if want != have:
		_rebuild_objects()


# ------------------------------------------------------------------ collision
func tile_at(tx: int, ty: int) -> String:
	if ty < 0 or ty >= map_h or tx < 0 or tx >= map_w:
		return "#"
	return grid[ty][tx]


func is_blocked(r: Rect2) -> bool:
	var x0 := int(floor(r.position.x / TILE))
	var x1 := int(floor((r.end.x - 0.01) / TILE))
	var y0 := int(floor(r.position.y / TILE))
	var y1 := int(floor((r.end.y - 0.01) / TILE))
	for ty in range(y0, y1 + 1):
		for tx in range(x0, x1 + 1):
			if PixelArt.is_solid_char(tile_at(tx, ty)):
				return true
	for o in objects:
		if o.solid_rect.size != Vector2.ZERO and o.solid_rect.intersects(r):
			return true
	return false


# ------------------------------------------------------------------ per frame
func _process(_delta: float) -> void:
	if map.is_empty():
		return
	_update_camera(false)
	_check_warps()
	_update_target()
	GameState.player_pos = player.position
	GameState.facing = player.facing
	GameState.has_player_pos = true


func _update_camera(_snap: bool) -> void:
	var view := get_viewport_rect().size / ZOOM
	var size := pixel_size()
	var c := player.position + Vector2(0, -8)
	if size.x <= view.x:
		c.x = size.x / 2.0
	else:
		c.x = clampf(c.x, view.x / 2.0, size.x - view.x / 2.0)
	if size.y <= view.y:
		c.y = size.y / 2.0
	else:
		c.y = clampf(c.y, view.y / 2.0, size.y - view.y / 2.0)
	camera.position = c.snapped(Vector2(0.5, 0.5))


func _check_warps() -> void:
	if not player.control_enabled:
		return
	var foot := player.position + Vector2(0, -2)
	var inside := false
	for o in objects:
		if o.kind == "warp" and bool(o.data.get("auto", false)) and o.rect.has_point(foot):
			inside = true
			if warp_armed:
				warp_armed = false
				warp_triggered.emit(str(o.data.get("to", "")), str(o.data.get("spawn", "")))
				return
	if not inside:
		warp_armed = true


func _update_target() -> void:
	var t: WorldObject = null
	if player.control_enabled:
		t = find_target()
	if t != current_target:
		current_target = t
		target_changed.emit(t)


## プレイヤーの正面にある「調べられるもの」を探す
func find_target() -> WorldObject:
	var front := player.position + player.dir_vector() * 11.0 + Vector2(0, -4)
	var best: WorldObject = null
	var best_d := INF
	for o in objects:
		if not o.is_interactable():
			continue
		var r := o.rect.grow(2.0)
		if r.has_point(front) or r.has_point(player.position + Vector2(0, -3)):
			var d := r.get_center().distance_squared_to(front)
			# 出入口よりも人や物を優先する
			if o.kind == "warp":
				d += 10000.0
			if d < best_d:
				best_d = d
				best = o
	return best


## ワールド座標 → 画面 (UI) 座標
func world_to_screen(p: Vector2) -> Vector2:
	return get_viewport().get_canvas_transform() * p
