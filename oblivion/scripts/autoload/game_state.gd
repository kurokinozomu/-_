extends Node
## ゲームの進行状態 (所持金・借金・日数・売却した記憶・フラグ・好感度・位置) を保持する。
## 条件式の評価、本文中の {token} 置換、セーブ/ロードもここに集約する。

signal changed
signal notify(text: String, is_error: bool)

const SAVE_VERSION := 1
const GLITCH_OPEN := "[g]"
const GLITCH_CLOSE := "[/g]"

var money: int = 0
var debt: int = 0
var day: int = 1
var deadline_day: int = 8
var sold: Array = []
var flags: Dictionary = {}
var relations: Dictionary = {}
var map_id: String = "home"
var spawn_name: String = "start"
var player_pos: Vector2 = Vector2.ZERO
var has_player_pos: bool = false
var facing: String = "down"
var playtime: float = 0.0
var last_price: int = 0
var debt_paid: int = 0

var _re_cmp := RegEx.new()


func _ready() -> void:
	_re_cmp.compile("^(day|money|debt|days_left|sold_count|rel:[a-z_]+)(>=|<=|==|!=|>|<)(-?\\d+)$")
	new_game()


func _process(delta: float) -> void:
	playtime += delta


# ------------------------------------------------------------------ setup
func new_game() -> void:
	money = int(GameData.cfg("start_money", 3000))
	debt = int(GameData.cfg("start_debt", 100000))
	day = int(GameData.cfg("start_day", 1))
	deadline_day = day + int(GameData.cfg("deadline_days", 7))
	sold = []
	flags = {}
	relations = {}
	map_id = str(GameData.cfg("start_map", "home"))
	spawn_name = str(GameData.cfg("start_spawn", "start"))
	has_player_pos = false
	facing = "down"
	playtime = 0.0
	last_price = 0
	debt_paid = 0
	changed.emit()


# ------------------------------------------------------------------ memories
func is_sold(id: String) -> bool:
	return sold.has(id)


func can_sell(id: String) -> bool:
	var m := GameData.get_memory(id)
	return not m.is_empty() and bool(m.get("enabled", false)) and not is_sold(id)


func sell_memory(id: String) -> bool:
	if not can_sell(id):
		return false
	var m := GameData.get_memory(id)
	last_price = int(m["price"])
	money += last_price
	sold.append(id)
	changed.emit()
	return true


## 売却数に応じた画面ノイズの強さ (0..1)
func noise_level() -> float:
	var base := float(GameData.cfg("noise_base", 0.18))
	var per := float(GameData.cfg("noise_per_memory", 0.16))
	return clampf(base + per * sold.size(), 0.0, 1.0)


# ------------------------------------------------------------------ flags / relations
func has_flag(f: String) -> bool:
	return bool(flags.get(f, false))


func set_flag(f: String, value: Variant = true) -> void:
	if value == null or value == false:
		flags.erase(f)
	else:
		flags[f] = value
	changed.emit()


func add_relation(npc: String, amount: int) -> void:
	relations[npc] = int(relations.get(npc, 0)) + amount
	changed.emit()


func get_relation(npc: String) -> int:
	return int(relations.get(npc, 0))


func add_money(amount: int) -> void:
	money += amount
	changed.emit()


func days_left() -> int:
	return maxi(deadline_day - day, 0)


## 1日を終える。期限を迎えたら "deadline" を返す。
func advance_day() -> String:
	day += 1
	money -= int(GameData.cfg("daily_cost", 2000))
	has_player_pos = false
	map_id = "home"
	spawn_name = "start"
	changed.emit()
	if day >= deadline_day:
		return "deadline"
	return "ok"


## 期限日に返済を試みる。払えたら true。
func try_repay() -> bool:
	if money >= debt:
		debt_paid = debt
		money -= debt
		debt = 0
		changed.emit()
		return true
	return false


# ------------------------------------------------------------------ conditions
## "sold:mother !flag:x day>=2 rel:saeki>=1" のような条件式を評価する (スペース区切りAND)。
func eval_cond(cond: Variant) -> bool:
	if cond == null:
		return true
	var s := str(cond).strip_edges()
	if s.is_empty():
		return true
	for term in s.split(" ", false):
		if not _eval_term(term):
			return false
	return true


func _eval_term(term: String) -> bool:
	var negate := term.begins_with("!")
	if negate:
		term = term.substr(1)
	var result := false
	var m := _re_cmp.search(term)
	if m:
		var lhs := _value_of(m.get_string(1))
		var rhs := int(m.get_string(3))
		match m.get_string(2):
			">=": result = lhs >= rhs
			"<=": result = lhs <= rhs
			"==": result = lhs == rhs
			"!=": result = lhs != rhs
			">": result = lhs > rhs
			"<": result = lhs < rhs
	elif term.begins_with("sold:"):
		result = is_sold(term.substr(5))
	elif term.begins_with("flag:"):
		result = has_flag(term.substr(5))
	elif term.begins_with("map:"):
		result = map_id == term.substr(4)
	else:
		push_warning("未知の条件: " + term)
	return result != negate


func _value_of(key: String) -> int:
	if key.begins_with("rel:"):
		return get_relation(key.substr(4))
	match key:
		"day": return day
		"money": return money
		"debt": return debt
		"days_left": return days_left()
		"sold_count": return sold.size()
	return 0


# ------------------------------------------------------------------ text
## 本文の {token} を置換する。売却済みの記憶に関わる語は [g]…[/g] で囲まれ、
## 表示側で文字化け (理解できない言葉) として描画される。
func resolve_text(text: String) -> String:
	if text.find("{") == -1:
		return text
	var out := text
	var tokens: Dictionary = GameData.cfg("tokens", {})
	for key in tokens.keys():
		if str(key).begins_with("_"):
			continue
		var tag: String = "{" + str(key) + "}"
		if out.find(tag) == -1:
			continue
		var t: Dictionary = tokens[key]
		var word := str(t.get("text", ""))
		var mem := str(t.get("memory", ""))
		if mem != "" and is_sold(mem):
			word = GLITCH_OPEN + word + GLITCH_CLOSE
		out = out.replace(tag, word)
	out = out.replace("{player}", str(GameData.cfg("player_name", "湊")))
	out = out.replace("{money}", format_yen(money))
	out = out.replace("{debt}", format_yen(debt))
	out = out.replace("{day}", str(day))
	out = out.replace("{days_left}", str(days_left()))
	out = out.replace("{deadline_days}", str(int(GameData.cfg("deadline_days", 7))))
	out = out.replace("{daily_cost}", format_yen(int(GameData.cfg("daily_cost", 2000))))
	out = out.replace("{last_price}", format_yen(last_price))
	out = out.replace("{debt_paid}", format_yen(debt_paid))
	return out


## [g]…[/g] を伏せ字にした、装飾なしの文字列 (HUD・看板用)。
func plain_text(text: String) -> String:
	return strip_glitch(resolve_text(text), "？")


static func strip_glitch(text: String, mask: String) -> String:
	var out := ""
	var i := 0
	while i < text.length():
		var a := text.find(GLITCH_OPEN, i)
		if a == -1:
			out += text.substr(i)
			break
		out += text.substr(i, a - i)
		var b := text.find(GLITCH_CLOSE, a)
		if b == -1:
			break
		var inner_len := b - a - GLITCH_OPEN.length()
		out += mask.repeat(maxi(inner_len, 1))
		i = b + GLITCH_CLOSE.length()
	return out


static func format_yen(v: int) -> String:
	var neg := v < 0
	var s := str(absi(v))
	var out := ""
	var count := 0
	for idx in range(s.length() - 1, -1, -1):
		out = s[idx] + out
		count += 1
		if count % 3 == 0 and idx > 0:
			out = "," + out
	return ("-" if neg else "") + out


# ------------------------------------------------------------------ save / load
func save_path() -> String:
	return str(GameData.cfg("save_path", "user://oblivion_save_v1.json"))


func to_dict() -> Dictionary:
	return {
		"version": SAVE_VERSION,
		"money": money, "debt": debt, "day": day, "deadline_day": deadline_day,
		"sold": sold, "flags": flags, "relations": relations,
		"map_id": map_id, "spawn_name": spawn_name,
		"player_pos": [player_pos.x, player_pos.y], "has_player_pos": has_player_pos,
		"facing": facing, "playtime": playtime,
		"last_price": last_price, "debt_paid": debt_paid,
		"saved_at": Time.get_datetime_string_from_system(),
	}


func from_dict(d: Dictionary) -> void:
	money = int(d.get("money", money))
	debt = int(d.get("debt", debt))
	day = int(d.get("day", day))
	deadline_day = int(d.get("deadline_day", deadline_day))
	sold = Array(d.get("sold", []))
	flags = Dictionary(d.get("flags", {}))
	relations = Dictionary(d.get("relations", {}))
	map_id = str(d.get("map_id", "home"))
	spawn_name = str(d.get("spawn_name", "start"))
	var p: Array = d.get("player_pos", [0, 0])
	player_pos = Vector2(float(p[0]), float(p[1]))
	has_player_pos = bool(d.get("has_player_pos", false))
	facing = str(d.get("facing", "down"))
	playtime = float(d.get("playtime", 0.0))
	last_price = int(d.get("last_price", 0))
	debt_paid = int(d.get("debt_paid", 0))
	# JSON は数値を float で返すので、関係値を int に正規化する
	for k in relations.keys():
		relations[k] = int(relations[k])
	if not GameData.maps.has(map_id):
		map_id = "home"
		has_player_pos = false
	changed.emit()


## セーブする。失敗したらエラー内容を通知して false を返す。
func save_game(quiet: bool = false) -> bool:
	var f := FileAccess.open(save_path(), FileAccess.WRITE)
	if f == null:
		var err := FileAccess.get_open_error()
		notify.emit("セーブに失敗しました（%s）。ブラウザの保存領域が無効になっている可能性があります。" % error_string(err), true)
		return false
	f.store_string(JSON.stringify(to_dict(), "\t"))
	var write_err := f.get_error()
	f.close()
	if write_err != OK:
		notify.emit("セーブデータの書き込みに失敗しました（%s）。" % error_string(write_err), true)
		return false
	if not quiet:
		if OS.has_feature("web") and not OS.is_userfs_persistent():
			notify.emit("保存しましたが、このブラウザでは閉じると消える可能性があります（プライベートモード等）。", true)
		else:
			notify.emit("セーブしました", false)
	return true


func has_save() -> bool:
	return FileAccess.file_exists(save_path())


func load_game() -> bool:
	if not has_save():
		notify.emit("セーブデータが見つかりません。", true)
		return false
	var f := FileAccess.open(save_path(), FileAccess.READ)
	if f == null:
		notify.emit("セーブデータを開けません（%s）。" % error_string(FileAccess.get_open_error()), true)
		return false
	var data: Variant = JSON.parse_string(f.get_as_text())
	if typeof(data) != TYPE_DICTIONARY:
		notify.emit("セーブデータが壊れています。", true)
		return false
	new_game()
	from_dict(data)
	return true


func delete_save() -> void:
	if has_save():
		DirAccess.remove_absolute(save_path())
