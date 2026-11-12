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
	GameData.config["records_path"] = "user://test_records.json"
	GameState.delete_save()
	if FileAccess.file_exists("user://test_records.json"):
		DirAccess.remove_absolute("user://test_records.json")
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
	await _test_phase2()
	await _test_phase3()
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
		elif main.sorting.visible:
			await _drive_sorting()
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


var sort_policy: Array = [true]   ## 仕分けで正解するかどうかを順に繰り返す
var sort_log: Dictionary = {}


func _drive_sorting() -> void:
	var sg: SortingGame = main.sorting
	match sg.state:
		"intro":
			sort_log = {"aid": sg.aid, "newbie": sg.newbie, "bins": sg.bins.duplicate(true), "answers": 0}
			sg.start_button.pressed.emit()
			await _frames(2)
			sg.time_left = minf(sg.time_left, 9.0)   # テストを速くする
		"play":
			if not sg.pkg.is_empty() and float(sg.pkg["t"]) > 0.1:
				var right: bool = sort_policy[int(sort_log["answers"]) % sort_policy.size()]
				sg.debug_answer(right)
				sort_log["answers"] = int(sort_log["answers"]) + 1
			await _frames(1)
		"result":
			sort_log["correct"] = sg.correct
			sort_log["wrong"] = sg.wrong
			sort_log["missed"] = sg.missed
			sort_log["pay"] = sg.current_pay()
			await _frames(2)
			sg.done_button.pressed.emit()
			await _frames(2)
		_:
			await _frames(1)


## 買取店で記憶を売る (UI を実際に操作する)
func _sell(id: String) -> void:
	main.run_event("karasuma")
	await _frames(3)
	await _advance_until_explore()
	main.shop._select(id)
	main.shop._on_sell_pressed()
	main.shop.confirm_yes.pressed.emit()
	await _frames(2)
	if main.shop.visible and main.shop.confirm_layer.visible:
		main.shop.confirm_yes.pressed.emit()
	await _frames(3)
	await _advance_until_explore()


# ------------------------------------------------------------------ 6. phase 2
func _test_phase2() -> void:
	print("[6] Phase 2 生活システム")
	GameState.delete_save()
	main._back_to_title()
	await _frames(3)
	main.title.new_game_requested.emit()
	await _frames(10)
	await _advance_until_explore()
	for f in ["read_notice", "visited_town", "visited_shop", "karasuma_met", "call1_done"]:
		GameState.set_flag(f)
	check(GameState.time_name() == "朝", "1日は朝から始まる")
	check(main.hud.status_label.text.contains("朝"), "HUD に時間帯が出る")

	# --- 倉庫まで歩いて働く
	await _walk_path([Vector2(72, 150), Vector2(128, 150), Vector2(128, 172)])
	check(await _wait_map("town"), "街へ出る")
	await _advance_until_explore()
	check(await _walk_path([Vector2(88, 90), Vector2(320, 90)]), "倉庫の前まで歩ける")
	await _walk_path([Vector2(320, 60)])
	check(await _wait_map("work"), "倉庫に入れる (休業が解除された)")
	await _advance_until_explore()
	check(await _walk_path([Vector2(184, 140), Vector2(184, 134)]), "主任の前まで歩ける")
	await _face_and_interact("up")
	var m0 := GameState.money
	sort_policy = [true, true, true, false]
	await _advance_until_explore([0, 0])
	check(sort_log.get("aid", false) and not sort_log.get("newbie", true), "仕事の記憶があれば補助あり・通常日給")
	check(sort_log.get("bins", []) == [[0, 1], [2, 3], [4, 5]], "いつもの棚割り (北・港=左 …)")
	var exp_pay: int = maxi(0, 1500 + int(sort_log.get("correct", 0)) * 300 - (int(sort_log.get("wrong", 0)) + int(sort_log.get("missed", 0))) * 200)
	check(int(sort_log.get("correct", 0)) > 0 and int(sort_log.get("wrong", 0)) > 0, "正解とミスが記録される (正解%d ミス%d 見逃し%d)" % [sort_log.get("correct", 0), sort_log.get("wrong", 0), sort_log.get("missed", 0)])
	check(GameState.money == m0 + exp_pay and GameState.last_pay == exp_pay, "報酬 = 日給 + 出来高 − ミス (%d円)" % exp_pay)
	check(GameState.time_slot == 2, "働くと時間が2つ進む (朝→夕方)")
	check(GameState.has_flag("worked_once"), "勤務記録")
	check(main.tint.color != Color.WHITE, "夕方は画面の色味が変わる")
	# 夕方はもう働けない
	main.run_event("makabe")
	await _frames(3)
	var before := log_lines.size()
	await _advance_until_explore()
	check("\n".join(log_lines.slice(before)).contains("受付は終わり"), "夕方以降は仕事の受付が終わっている")

	# --- 返済
	GameState.money = 45000
	GameState.changed.emit()
	main.run_event("atm")
	await _frames(3)
	await _advance_until_explore([0])
	check(GameState.debt == 90000 and GameState.money == 35000, "ATMで1万円返済できる")
	check(GameState.has_save(), "返済後に自動セーブ")

	# --- 生活費の不足 → 自動融資
	GameState.money = 500
	var d0 := GameState.debt
	main.run_event("home_bed")
	await _frames(3)
	await _advance_until_explore([0])
	check(GameState.money == 0 and GameState.debt == d0 + 1650 and GameState.last_loan == 1650, "生活費不足分×1.1が借金に上乗せされる")
	check(GameState.time_slot == 0 and GameState.day == 2, "翌朝に時間がリセットされる")

	# --- 近道 (街の記憶があるうち)
	main.world.load_map("town", "home_door")
	await _frames(2)
	main.run_event("alley_west")
	await _frames(3)
	await _advance_until_explore([0])
	check(main.world.map_id == "town" and main.world.player.position.x > 700.0, "近道の路地で街の東へ抜けられる")
	# --- 街の記憶
	check(GameState.plain_read("{shop_name}") == "メモリア", "売る前は店名が読める")
	await _sell("city")
	check(GameState.is_sold("city") and GameState.money == 12000, "街の記憶を売れる (+12,000)")
	check(GameState.plain_read("記憶買取 {shop_name}").contains("？"), "看板の店名が読めなくなる")
	main.world.load_map("town", "home_door")
	await _frames(2)
	check(not main.world.objects.any(func(o): return o.data["id"] == "guide"), "道案内の看板が消える")
	main.run_event("alley_west")
	await _frames(3)
	before = log_lines.size()
	await _advance_until_explore()
	check(main.world.map_id == "town" and main.world.player.position.x < 300.0, "近道の路地が使えなくなる")

	# --- 仕事の記憶 → 新人扱い・別の働き方
	await _sell("work")
	GameState.time_slot = 0
	main.world.load_map("work", "entrance")
	main.run_event("makabe")
	await _frames(3)
	sort_policy = [true]
	await _advance_until_explore([0])
	check(sort_log.get("newbie", false) and not sort_log.get("aid", true), "仕事の記憶を売ると補助が消え新人扱い")
	check(GameState.last_pay == maxi(0, 800 + int(sort_log.get("correct", 0)) * 300 - (int(sort_log.get("wrong", 0)) + int(sort_log.get("missed", 0))) * 200), "新人日給で計算される")
	GameState.advance_day()
	main.run_event("makabe")
	await _frames(3)
	var m1 := GameState.money
	await _advance_until_explore([1])
	check(GameState.money == m1 + 3500 and GameState.has_flag("found_carry_job"), "別の働き方 (荷運び) を見つけられる")

	# --- 文字の記憶
	await _sell("letters")
	var notice := GameState.read_text("ご返済金額　{debt}円")
	check(notice.contains("[g]") and notice.contains(GameState.format_yen(GameState.debt)), "文字が崩れるが数字は読める")
	check(GameState.plain_read("北区").contains("？"), "仕分けの区画名が読めなくなる (図形は残る)")
	main.world.load_map("home", "start")
	main.run_event("home_letter")
	await _frames(3)
	await _advance_until_explore()

	# --- 大切な人の記憶 (二重確認)
	main.run_event("karasuma")
	await _frames(3)
	await _advance_until_explore()
	main.shop._select("beloved")
	main.shop._on_sell_pressed()
	main.shop.confirm_yes.pressed.emit()
	await _frames(2)
	check(main.shop.visible and main.shop.confirm_layer.visible and main.shop._confirm_stage == 1, "大切な人の記憶は二度確認される")
	main.shop.confirm_yes.pressed.emit()
	await _frames(3)
	await _advance_until_explore()
	check(GameState.is_sold("beloved"), "大切な人の記憶を売れる")
	main.run_event("nagi")
	await _frames(3)
	await _advance_until_explore()
	check(GameState.has_flag("nagi_gone"), "フードの女が去る")
	main.world.load_map("town", "home_door")
	await _frames(2)
	check(not main.world.objects.any(func(o): return o.data["id"] == "nagi"), "以後、街に現れない")
	main.world.load_map("home", "start")
	main.run_event("home_photo2")
	await _frames(4)
	check(main.photo.visible and main.photo.kind == "beloved" and main.photo.lost, "写真の人物が分からなくなる")
	await _advance_until_explore()
	check(GameState.noise_level() >= 0.8, "4つ売ると画面ノイズがかなり強くなる (%.2f)" % GameState.noise_level())

	# --- セーブに時間帯が残る / 全額返済でエンディング
	GameState.time_slot = 1
	GameState.save_game(true)
	GameState.new_game()
	GameState.load_game()
	check(GameState.time_slot == 1 and GameState.sold.size() == 4, "時間帯と売却状態がセーブされる")
	GameState.money = GameState.debt + 10
	main.run_event("atm")
	await _frames(3)
	await _advance_until_explore([2], 1500)
	check(GameState.debt == 0, "全額返済できる")
	var f := 0
	while not main.ending.visible and f < 600:
		f += 1
		await _frames(1)
	check(main.ending.visible, "完済でエンディングになる")
	main.ending.closed.emit()
	await _frames(3)
	check(main.title.visible, "エンディング後タイトルへ戻る")


# ------------------------------------------------------------------ 7. phase 3
func _new_game() -> void:
	GameState.delete_save()
	main._back_to_title()
	await _frames(3)
	main.title.new_game_requested.emit()
	await _frames(10)
	await _advance_until_explore()


func _event(id: String, choices: Array = []) -> void:
	main.run_event(id)
	await _frames(3)
	await _advance_until_explore(choices, 3000)


## エンディング画面が出るまで待ち、閉じてタイトルへ戻る。出たエンディングIDを返す
func _await_ending() -> String:
	var f := 0
	while not main.ending.visible and f < 900:
		f += 1
		await _frames(1)
	var id: String = main.ending.ending_id if main.ending.visible else ""
	main.ending.closed.emit()
	await _frames(5)
	return id


func _test_phase3() -> void:
	print("[7] Phase 3 物語とエンディング")
	await _new_game()
	check(Sound.current_bgm() == "home", "自宅ではBGM『home』が流れる")
	for f in ["read_notice", "visited_town", "visited_shop", "karasuma_met", "call1_done"]:
		GameState.set_flag(f)
	# 時間つぶし
	await _event("home_bed", [1])
	check(GameState.time_slot == 3, "ベッドで夜まで休める")
	# 2日目の夢 → 鍵 → 引き出し
	await _event("home_bed", [0])
	check(GameState.day == 2 and GameState.has_flag("dream_bridge"), "2日目の朝に橋の夢を見る")
	check(main.hud.current_objective().contains("写真"), "目標が夢の写真へ誘導する")
	await _event("home_drawer")
	check(not GameState.has_flag("read_past_letter"), "鍵がないと引き出しは開かない")
	await _event("home_photo2")
	check(GameState.has_flag("found_key"), "写真立ての裏に鍵がある")
	main.run_event("home_drawer")
	await _frames(4)
	var saw_letter := false
	var f := 0
	while main.mode != "explore" and f < 3000:
		f += 1
		if main.paper.visible and main.paper._raw_body.contains("絶対に売るな"):
			saw_letter = true
		await _advance_until_explore([], 1)
	check(saw_letter, "過去の自分の手紙「あの人の記憶だけは絶対に売るな」が読める")
	check(GameState.has_flag("read_past_letter") and GameState.has_flag("clue_contract"), "去年の契約書（証拠1）を手に入れる")
	# 橋の下へ (実際に歩く)
	GameState.time_slot = 0
	main.world.load_map("town", "shop_door")
	await _frames(3)
	check(not main.world.objects.any(func(o): return o.data["id"] == "nagi"), "手紙を読むと、凪は街から橋の下へ移る")
	check(await _walk_path([Vector2(912, 90), Vector2(992, 90), Vector2(992, 150)]), "東端の階段まで歩ける")
	await _walk_path([Vector2(992, 168)])
	check(await _wait_map("bridge"), "階段を下りて橋の下へ行ける")
	await _advance_until_explore()
	check(Sound.current_bgm() == "title", "橋の下では別のBGMになる")
	check(await _walk_path([Vector2(40, 112), Vector2(168, 112), Vector2(168, 98)]), "凪の前まで歩ける")
	await _face_and_interact("up")
	await _advance_until_explore([0])
	check(GameState.has_flag("bridge_promise") and GameState.has_flag("clue_nagi"), "凪と約束し、台帳の手がかりを得る")
	# 夜の店で台帳
	GameState.time_slot = 3
	main.world.load_map("shop", "entrance")
	await _frames(3)
	check(not main.world.objects.any(func(o): return o.data["id"] == "karasuma"), "夜の店に烏間はいない")
	check(main.world.objects.any(func(o): return o.data["id"] == "ledger"), "夜はカウンターに台帳がある")
	await _event("shop_ledger")
	check(GameState.has_flag("clue_ledger"), "台帳（証拠2）を読める")
	await _event("poster")
	check(main.hud.current_objective().contains("烏間"), "証拠がそろうと目標が対決を示す")
	# エンディング A: 約束して完済
	GameState.money = GameState.debt
	main.run_event("atm")
	await _frames(3)
	await _advance_until_explore([2], 1500)
	check(await _await_ending() == "protected", "約束して完済 → ENDING A 雨上がりの橋")

	# エンディング C / F: 対決
	await _new_game()
	for fl in ["karasuma_met", "clue_poster", "clue_contract", "clue_ledger"]:
		GameState.set_flag(fl)
	main.world.load_map("shop", "entrance")
	main.run_event("karasuma")
	await _frames(3)
	await _advance_until_explore([0, 1], 3000)
	check(await _await_ending() == "secret", "証拠を突きつけて売らない → ENDING C メモリア閉店")
	await _new_game()
	for fl in ["karasuma_met", "clue_poster", "clue_contract", "clue_ledger"]:
		GameState.set_flag(fl)
	main.world.load_map("shop", "entrance")
	main.run_event("karasuma")
	await _frames(3)
	await _advance_until_explore([0, 0], 3000)
	check(await _await_ending() == "loop", "秘密の記憶まで売る → ENDING F はじめてのお客様")

	# エンディング B: 大切な人を売って完済
	await _new_game()
	await _sell("beloved")
	GameState.money = GameState.debt
	main.run_event("atm")
	await _frames(3)
	await _advance_until_explore([2], 1500)
	check(await _await_ending() == "forgotten", "大切な人を売って完済 → ENDING B 忘却の朝")

	# エンディング D: 約束せずに期限日に完済 (自動返済)
	await _new_game()
	GameState.day = GameState.deadline_day - 1
	GameState.money = GameState.debt + 2000
	main.run_event("home_bed")
	await _frames(3)
	await _advance_until_explore([0], 3000)
	check(await _await_ending() == "paid", "約束せず期限日に完済 → ENDING D 返済完了")

	# エンディング E: 期限切れ
	await _new_game()
	GameState.day = GameState.deadline_day - 1
	main.run_event("home_bed")
	await _frames(3)
	await _advance_until_explore([0], 3000)
	check(await _await_ending() == "seized", "返せずに期限 → ENDING E 差押え")
	check(not GameState.has_save(), "エンディング後はセーブが消える")
	var seen := GameState.endings_seen()
	check(seen.size() == 6, "6種類のエンディングがすべて記録される %s" % str(seen))
	check(main.title.info_label.text.contains("6/6"), "タイトルに回収状況が出る: " + main.title.info_label.text)

	# その他の演出
	await _new_game()
	GameState.sold = ["mother", "city"]
	GameState.time_slot = 2
	GameState.changed.emit()
	main.world.load_map("town", "home_door")
	await _frames(3)
	var ghost: WorldObject = null
	for o in main.world.objects:
		if o.data["id"] == "ghost":
			ghost = o
	check(ghost != null, "記憶を2つ以上売った夕方以降、街に『自分』の人影が立つ")
	if ghost:
		main.world.player.position = ghost.position + Vector2(-80, 0)
		await _walk_to(ghost.position + Vector2(-40, 0))
		await _frames(5)
		await _advance_until_explore()
		check(GameState.has_flag("ghost_seen") and not main.world.objects.any(func(o): return o.data["id"] == "ghost"), "近づくと人影は消える")
	GameState.time_slot = 0
	GameState.money = 1000
	GameState.set_flag("gen_met")
	GameState.set_flag("gen_talked")
	main.run_event("gen")
	await _frames(3)
	await _advance_until_explore([0])
	check(GameState.money == 500 and GameState.time_slot == 1, "屋台で一杯食べると時間が進む")
	GameState.sold.append("letters")
	main.world.load_map("home", "start")
	GameState.set_flag("found_key")
	main.run_event("home_drawer")
	await _frames(3)
	var b0 := log_lines.size()
	await _advance_until_explore([], 3000)
	check("\n".join(log_lines.slice(b0)).contains("絵だけは分かる"), "文字を売っていても、手紙の絵から橋へたどり着ける")


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
	re.compile("^!?(money>=debt|sold:[a-z_]+|flag:[a-z_0-9]+|map:[a-z_]+|(day|time|money|debt|days_left|sold_count|last_loan|last_pay|rel:[a-z_]+)(>=|<=|==|!=|>|<)-?\\d+)$")
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
	check(not main.shop.sell_button.disabled, "Phase 2: 他の記憶も売却可能")
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
