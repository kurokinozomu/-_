extends Node
## 自動テスト。ヘッドレスで実行する:
##   godot --headless --path . res://tests/test_runner.tscn
## 1) データ整合性チェック
## 2) Phase 1 の通しプレイ (実際に入力を送って歩く):
##    自宅で目覚める → 通知を読む → 街へ → 買取店 → 母親の記憶を売る → 帰宅 → 母からの電話
## 3) セーブ → ロードで売却状態が保持されるか
## 4) 売らなかった場合の分岐 (通常の電話)

var main: Node
var failures: PackedStringArray = []
var checks := 0
var log_lines: PackedStringArray = []


func _ready() -> void:
	Engine.time_scale = 3.0
	# テスト用のセーブ先 (本番セーブを壊さない)
	GameData.config["save_path"] = "user://test_save.json"
	GameState.delete_save()
	await _run_all()


func _run_all() -> void:
	_test_data_integrity()
	_test_text_and_conditions()
	main = load("res://scenes/main.tscn").instantiate()
	add_child(main)
	await _frames(5)
	await _test_phase1_playthrough()
	await _test_save_load()
	await _test_no_sale_branch()
	_finish()


# ------------------------------------------------------------------ helpers
func check(cond: bool, msg: String) -> void:
	checks += 1
	if cond:
		log_lines.append("  ok   " + msg)
	else:
		failures.append(msg)
		log_lines.append("  FAIL " + msg)
	print(("  ok   " if cond else "  FAIL ") + msg)


func _frames(n: int) -> void:
	for i in n:
		await get_tree().process_frame


func _press(action: String) -> void:
	var ev := InputEventAction.new()
	ev.action = action
	ev.pressed = true
	Input.parse_input_event(ev)
	await _frames(1)
	var ev2 := InputEventAction.new()
	ev2.action = action
	ev2.pressed = false
	Input.parse_input_event(ev2)
	await _frames(1)


## 会話・紙・写真・演出が終わって探索モードに戻るまで進める。choices は順に選ぶ選択肢の番号。
func _advance_until_explore(choices: Array = [], max_frames: int = 6000) -> int:
	var lines := 0
	var f := 0
	while main.mode != "explore" and f < max_frames:
		f += 1
		var dlg: DialogueBox = main.dialogue
		if main.paper.visible and main.paper._guard <= 0.0:
			await _press("interact")
		elif main.photo.visible and main.photo._guard <= 0.0:
			await _press("interact")
		elif dlg.visible and dlg._mode == "choice" and dlg._guard <= 0.0 and dlg._choice_buttons.size() > 0:
			var idx: int = choices.pop_front() if choices.size() > 0 else 0
			log_lines.append("     choose: " + dlg._choice_buttons[idx].text)
			dlg._choice_buttons[idx].pressed.emit()
			await _frames(2)
		elif dlg.visible and dlg._mode == "line" and dlg._guard <= 0.0:
			if not dlg._typing:
				lines += 1
				log_lines.append("     > " + GameState.strip_glitch(dlg._raw, "■"))
			await _press("interact")
		elif main.shop.visible:
			return lines
		else:
			await _frames(1)
	return lines


## 目標地点へ歩く (軸ごとに貪欲に移動)。到達したら true。
func _walk_to(target: Vector2, max_frames: int = 1500) -> bool:
	var p: Player = main.world.player
	var f := 0
	while f < max_frames:
		f += 1
		var d := target - p.position
		for a in ["move_left", "move_right", "move_up", "move_down"]:
			Input.action_release(a)
		if d.length() < 2.0:
			return true
		if main.mode != "explore":
			return false
		if absf(d.x) >= 2.0:
			Input.action_press("move_right" if d.x > 0 else "move_left")
		elif absf(d.y) >= 2.0:
			Input.action_press("move_down" if d.y > 0 else "move_up")
		await get_tree().physics_frame
	for a in ["move_left", "move_right", "move_up", "move_down"]:
		Input.action_release(a)
	print("     walk stuck at ", p.position, " target ", target)
	return false


func _walk_path(points: Array) -> bool:
	for pt in points:
		if not await _walk_to(pt):
			return false
	return true


## 向きを変えてから調べる
func _face_and_interact(dir: String) -> void:
	main.world.player.facing = dir
	await _frames(2)
	await _press("interact")
	await _frames(2)


func _wait_map(id: String, max_frames: int = 600) -> bool:
	var f := 0
	while f < max_frames:
		if main.world.map_id == id and main.fade.color.a < 0.99:
			return true
		f += 1
		await _frames(1)
	return false


# ------------------------------------------------------------------ 1. data
func _test_data_integrity() -> void:
	print("[1] データ整合性")
	check(GameData.load_errors.is_empty(), "全JSONが読み込める %s" % str(GameData.load_errors))
	check(GameData.memories.size() >= 5, "記憶が5種類以上定義されている")
	var ids := []
	for m in GameData.memories:
		ids.append(m["id"])
		check(GameData.dialogues.has(str(m.get("after_script", ""))), "記憶 %s の売却後スクリプトが存在" % m["id"])
	for need in ["mother", "city", "work", "letters", "beloved"]:
		check(ids.has(need), "記憶 %s が定義されている" % need)
	# 会話スクリプトの参照
	var refs := {"who": [], "run": [], "paper": [], "cond": []}
	for sid in GameData.dialogues.keys():
		if str(sid).begins_with("_"):
			continue
		_collect_refs(GameData.dialogues[sid], refs)
	for w in refs["who"]:
		check(GameData.characters.has(w), "キャラクター %s が定義されている" % w)
	for r in refs["run"]:
		check(GameData.dialogues.has(r), "run 先 %s が存在" % r)
	for p in refs["paper"]:
		check(GameData.papers.has(p), "紙 %s が存在" % p)
	# マップ
	for mid in GameData.maps.keys():
		var m: Dictionary = GameData.maps[mid]
		var tiles: Array = m["tiles"]
		var w: int = str(tiles[0]).length()
		var same := true
		for row in tiles:
			if str(row).length() != w:
				same = false
		check(same, "マップ %s の行幅がそろっている" % mid)
		for o in m.get("objects", []):
			if o.has("script"):
				check(GameData.dialogues.has(o["script"]), "%s/%s のスクリプト %s が存在" % [mid, o["id"], o["script"]])
			if o.get("kind", "") == "warp":
				var to: String = o.get("to", "")
				check(GameData.maps.has(to) and GameData.maps[to]["spawns"].has(o.get("spawn", "")), "%s/%s の行き先 %s:%s が存在" % [mid, o["id"], to, o.get("spawn", "")])
			if o.has("if"):
				refs["cond"].append(o["if"])
		for ev in m.get("on_enter", []):
			check(GameData.dialogues.has(ev["script"]), "%s の on_enter %s が存在" % [mid, ev["script"]])
	for o in GameData.objectives:
		refs["cond"].append(o.get("if", ""))
	# 条件式が全部解釈できるか (未知の条件は警告→ここで検出)
	var re := RegEx.new()
	re.compile("^!?(sold:[a-z_]+|flag:[a-z_0-9]+|map:[a-z_]+|(day|money|debt|days_left|sold_count|rel:[a-z_]+)(>=|<=|==|!=|>|<)-?\\d+)$")
	var bad := []
	for c in refs["cond"]:
		for term in str(c).split(" ", false):
			if re.search(term) == null:
				bad.append(term)
	check(bad.is_empty(), "全条件式が有効 %s" % str(bad))
	# 使っている全文字がフォントに収録されているか (Web版はOSのフォントに頼れないため)
	var font: FontFile = load("res://assets/fonts/DotGothic16-Regular.ttf")
	var missing := {}
	var texts: Array = []
	for fn in DirAccess.get_files_at("res://data"):
		if fn.ends_with(".json"):
			texts.append(FileAccess.get_file_as_string("res://data/" + fn))
	texts.append(GlitchText.NOISE)
	for t in texts:
		for ch in str(t):
			var cp := ch.unicode_at(0)
			if cp > 127 and not font.has_char(cp):
				missing[ch] = true
	check(missing.is_empty(), "全テキストの文字がフォントに収録されている %s" % str(missing.keys()))


func _collect_refs(steps: Variant, refs: Dictionary) -> void:
	if typeof(steps) != TYPE_ARRAY:
		return
	for s in steps:
		if typeof(s) != TYPE_DICTIONARY:
			continue
		if s.has("who") and str(s["who"]) != "" and not refs["who"].has(s["who"]):
			refs["who"].append(s["who"])
		if s.has("run"):
			refs["run"].append(s["run"])
		if s.get("action", "") == "paper":
			refs["paper"].append(s.get("arg", ""))
		if s.has("if"):
			refs["cond"].append(s["if"])
		_collect_refs(s.get("then", []), refs)
		_collect_refs(s.get("else", []), refs)
		for o in s.get("choice", []):
			if o.has("if"):
				refs["cond"].append(o["if"])
			_collect_refs(o.get("do", []), refs)


func _test_text_and_conditions() -> void:
	print("[2] テキスト置換・条件式")
	GameState.new_game()
	check(GameState.resolve_text("{mother_name}") == "春子", "売却前は母の名前が読める")
	check(GameState.eval_cond("!sold:mother day>=1 money>=3000"), "条件式の評価 (AND)")
	check(not GameState.eval_cond("flag:nothing"), "未設定フラグは偽")
	GameState.sold.append("mother")
	check(GameState.resolve_text("{mother_name}さん") == "[g]春子[/g]さん", "売却後は母の名前が文字化けマーク付きになる")
	check(GameState.plain_text("{mom}") == "？？？", "HUD等では伏せ字になる")
	check(GameState.format_yen(100000) == "100,000" and GameState.format_yen(-1500) == "-1,500", "金額の3桁区切り")
	check(GlitchText.to_bbcode("[g]春子[/g]", 1).length() > 0, "文字化けBBCode生成")
	GameState.new_game()


# ------------------------------------------------------------------ 3. playthrough
func _test_phase1_playthrough() -> void:
	print("[3] Phase 1 通しプレイ")
	check(main.title.visible, "タイトル画面が表示される")
	main.title.new_game_requested.emit()
	await _frames(10)
	await _advance_until_explore()
	check(main.mode == "explore", "目覚めのモノローグ後に操作可能になる")
	check(main.world.map_id == "home", "自宅から始まる")
	check(GameState.money == 3000 and GameState.debt == 100000 and GameState.days_left() == 7, "初期値: 所持金3000/借金100000/期限7日")
	check(main.hud.current_objective().contains("封筒"), "最初の目標が表示される: " + main.hud.current_objective())

	# 督促状を読む
	check(await _walk_path([Vector2(72, 104), Vector2(72, 74)]), "机の前まで歩ける")
	check(main.world.find_target() != null and main.world.find_target().data["id"] == "letter", "正面の封筒が調べる対象になる")
	await _face_and_interact("up")
	check(main.paper.visible, "督促状の紙が表示される")
	await _advance_until_explore()
	check(GameState.has_flag("read_notice"), "督促状を読んだ")

	# 外へ
	await _walk_path([Vector2(72, 150), Vector2(128, 150), Vector2(128, 172)])
	check(await _wait_map("town"), "街へ出られる")
	await _advance_until_explore()
	check(GameState.has_flag("visited_town"), "街の初回イベントが発生")

	# 源さんと話して買取店を知る
	check(await _walk_path([Vector2(88, 90), Vector2(512, 90)]), "屋台の前まで歩ける")
	await _face_and_interact("up")
	await _advance_until_explore([0])
	check(GameState.has_flag("gen_met") and GameState.has_flag("knows_shop"), "源さんから記憶買取店の話を聞ける")

	# 買取店へ
	check(await _walk_path([Vector2(912, 90)]), "買取店の入口まで歩ける")
	await _walk_path([Vector2(912, 60)])
	check(await _wait_map("shop"), "記憶買取店に入れる")
	await _advance_until_explore()
	check(GameState.has_flag("visited_shop") and GameState.has_flag("call_pending"), "入店フラグと電話予約")
	check(await _walk_path([Vector2(128, 86)]), "カウンター前まで歩ける")
	await _face_and_interact("up")
	await _advance_until_explore()
	check(main.shop.visible, "査定画面が開く")
	main.shop._select("city")
	check(main.shop.sell_button.disabled, "Phase 1 では他の記憶は査定準備中")
	main.shop._select("mother")
	check(not main.shop.sell_button.disabled, "母親の記憶は売却可能")
	main.shop._on_sell_pressed()
	check(main.shop.confirm_layer.visible, "売却確認ダイアログが出る")
	main.shop.confirm_yes.pressed.emit()
	await _frames(5)
	check(main.sell_fx.visible, "売却演出が再生される")
	await _advance_until_explore()
	check(GameState.is_sold("mother"), "母親の記憶が売却済みになる")
	check(GameState.money == 23000, "所持金が 3000 + 20000 = 23000 になる (実際: %d)" % GameState.money)
	check(GameState.noise_level() > float(GameData.cfg("noise_base", 0.18)), "画面ノイズが強くなる")
	check(GameState.has_save(), "売却直後に自動セーブされる")

	# 帰宅
	await _walk_path([Vector2(128, 140), Vector2(128, 152)])
	check(await _wait_map("town"), "街に戻る")
	await _advance_until_explore()
	# 佐伯さんの反応が変わる
	check(await _walk_path([Vector2(912, 90), Vector2(136, 90)]), "佐伯さんの前まで歩ける")
	await _face_and_interact("up")
	var before_lines := log_lines.size()
	await _advance_until_explore([1])
	var saeki_text := "\n".join(log_lines.slice(before_lines))
	check(GameState.has_flag("saeki_after") and saeki_text.contains("■"), "隣人の会話で母の名前が聞き取れなくなる")
	check(await _walk_path([Vector2(88, 90)]), "自宅の入口まで歩ける")
	await _walk_path([Vector2(88, 60)])
	check(await _wait_map("home"), "自宅に戻れる")
	await _advance_until_explore()
	check(main.world.objects.any(func(o): return o.data["id"] == "memo"), "売却後、机に見覚えのないメモが現れる")

	# 母からの電話
	check(await _walk_path([Vector2(152, 147), Vector2(152, 122)]), "スマホの前まで歩ける")
	await _face_and_interact("up")
	before_lines = log_lines.size()
	await _advance_until_explore([0])
	var call_text := "\n".join(log_lines.slice(before_lines))
	check(GameState.has_flag("strange_call_done"), "違和感のある電話イベントが発生する")
	check(call_text.contains("読めない") and call_text.contains("また、なのね"), "電話の相手が誰か分からない会話になる")
	check(not GameState.has_flag("call_pending"), "着信が止まる")

	# 写真
	check(await _walk_path([Vector2(136, 122), Vector2(136, 60)]), "写真の前まで歩ける")
	await _face_and_interact("up")
	check(main.photo.visible and main.photo.lost, "写真の女性の顔が認識できない表示になる")
	await _advance_until_explore()
	check(GameState.has_flag("saw_photo_after"), "写真の描写が変化する")

	# メモ
	check(await _walk_path([Vector2(136, 74), Vector2(104, 74)]), "メモの前まで歩ける")
	await _face_and_interact("up")
	await _advance_until_explore()
	check(GameState.has_flag("read_memo_mother"), "過去の自分のメモを読める")
	for l in log_lines:
		if l.begins_with("     >") and l.contains("■"):
			print(l)


# ------------------------------------------------------------------ 4. save/load
func _test_save_load() -> void:
	print("[4] セーブ／ロード")
	var ok := GameState.save_game(true)
	check(ok, "セーブできる")
	var money := GameState.money
	var pos := GameState.player_pos
	GameState.new_game()
	check(not GameState.is_sold("mother"), "新規状態にリセットされる")
	check(GameState.load_game(), "ロードできる")
	check(GameState.is_sold("mother"), "ロード後も母親の記憶は売却済み")
	check(GameState.money == money, "所持金が復元される")
	check(GameState.has_flag("strange_call_done"), "ストーリーフラグが復元される")
	check(GameState.relations.get("mother", 0) == -1, "NPCとの関係値が復元される")
	check(GameState.player_pos.distance_to(pos) < 0.5 and GameState.map_id == "home", "マップと位置が復元される")
	# タイトル→つづきから
	main._back_to_title()
	await _frames(5)
	check(main.title.visible and not main.title.cont_button.disabled, "タイトルで「つづきから」が有効")
	main.title.continue_requested.emit()
	await _frames(5)
	await _advance_until_explore()
	check(main.mode == "explore" and main.world.map_id == "home", "つづきから再開できる")
	check(main.world.player.position.distance_to(pos) < 1.0, "保存した位置から再開する")
	# 壊れたセーブ
	var f := FileAccess.open(GameState.save_path(), FileAccess.WRITE)
	f.store_string("{broken")
	f.close()
	var errors: Array = []
	var cb := func(t, e): if e: errors.append(t)
	GameState.notify.connect(cb)
	check(not GameState.load_game(), "壊れたセーブはロードを拒否する")
	check(errors.size() > 0, "壊れたセーブでエラーを表示する: %s" % str(errors))
	GameState.notify.disconnect(cb)


# ------------------------------------------------------------------ 5. branch
func _test_no_sale_branch() -> void:
	print("[5] 売らなかった場合の分岐")
	GameState.delete_save()
	main._back_to_title()
	await _frames(3)
	main.title.new_game_requested.emit()
	await _frames(10)
	await _advance_until_explore()
	GameState.set_flag("read_notice")
	GameState.set_flag("visited_town")
	GameState.set_flag("visited_shop")
	GameState.set_flag("call_pending")
	main.run_event("home_phone")
	await _frames(3)
	await _advance_until_explore([0])
	check(GameState.has_flag("call1_done") and GameState.has_flag("told_mom_debt"), "売らなければ母と普通に話せる")
	check(not GameState.has_flag("strange_call_done"), "違和感イベントは起きない")
	check(GameState.resolve_text("{mother_name}") == "春子", "母の名前を覚えている")
	# 1日経過
	var m0 := GameState.money
	var d0 := GameState.day
	main.run_event("home_bed")
	await _frames(5)
	await _advance_until_explore([0])
	check(GameState.day == d0 + 1 and GameState.money == m0 - 2000, "眠ると1日進み生活費が引かれる")


func _finish() -> void:
	print("")
	print("==== %d checks, %d failed ====" % [checks, failures.size()])
	for f in failures:
		print("FAILED: " + f)
	GameState.delete_save()
	var out := FileAccess.open("user://test_report.txt", FileAccess.WRITE)
	if out:
		out.store_string("\n".join(log_lines))
	get_tree().quit(1 if failures.size() > 0 else 0)
