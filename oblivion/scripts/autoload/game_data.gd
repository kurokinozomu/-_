extends Node
## 静的データ (data/*.json) の読み込みと入力マップの登録を担当する。
## ゲームバランスやシナリオはすべて JSON 側にあり、コードを触らずに調整できる。

const DATA_DIR := "res://data/"

var config: Dictionary = {}
var memories: Array = []
var memory_by_id: Dictionary = {}
var characters: Dictionary = {}
var dialogues: Dictionary = {}
var maps: Dictionary = {}
var objectives: Array = []
var papers: Dictionary = {}
var endings: Dictionary = {}

var load_errors: PackedStringArray = []


func _ready() -> void:
	_register_input()
	load_all()


func load_all() -> void:
	load_errors.clear()
	config = _load_json("config.json", {})
	memories = _load_json("memories.json", [])
	characters = _load_json("characters.json", {})
	dialogues = _load_json("dialogue.json", {})
	maps = _load_json("maps.json", {})
	objectives = _load_json("objectives.json", [])
	papers = _load_json("papers.json", {})
	endings = _load_json("endings.json", {})
	memory_by_id.clear()
	for m in memories:
		memory_by_id[m["id"]] = m


func cfg(key: String, default_value: Variant = null) -> Variant:
	return config.get(key, default_value)


func get_memory(id: String) -> Dictionary:
	return memory_by_id.get(id, {})


func get_character(id: String) -> Dictionary:
	return characters.get(id, {})


func _load_json(file: String, fallback: Variant) -> Variant:
	var path := DATA_DIR + file
	var f := FileAccess.open(path, FileAccess.READ)
	if f == null:
		var msg := "データを開けません: %s (%s)" % [path, error_string(FileAccess.get_open_error())]
		push_error(msg)
		load_errors.append(msg)
		return fallback
	var json := JSON.new()
	var err := json.parse(f.get_as_text())
	if err != OK:
		var msg2 := "JSON構文エラー: %s 行%d: %s" % [path, json.get_error_line(), json.get_error_message()]
		push_error(msg2)
		load_errors.append(msg2)
		return fallback
	return json.data


# ---------------------------------------------------------------- input map
func _register_input() -> void:
	_add_action("move_left", [KEY_A, KEY_LEFT])
	_add_action("move_right", [KEY_D, KEY_RIGHT])
	_add_action("move_up", [KEY_W, KEY_UP])
	_add_action("move_down", [KEY_S, KEY_DOWN])
	_add_action("interact", [KEY_E, KEY_SPACE, KEY_ENTER, KEY_KP_ENTER, KEY_Z])
	_add_action("cancel", [KEY_ESCAPE, KEY_X, KEY_BACKSPACE])
	_add_action("menu", [KEY_ESCAPE, KEY_TAB, KEY_M])


func _add_action(action: String, keys: Array) -> void:
	if not InputMap.has_action(action):
		InputMap.add_action(action, 0.3)
	for k in keys:
		var ev := InputEventKey.new()
		ev.physical_keycode = k
		InputMap.action_add_event(action, ev)
