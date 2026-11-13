extends Node
## ゲーム全体の進行役。ワールド・UI・会話・演出をつなぐ。
##   mode: "title" / "explore" / "busy" (会話・メニュー・演出中)

var world: World
var fx_layer: CanvasLayer
var rain: Control
var noise: ColorRect
var noise_mat: ShaderMaterial
var ui_root: Control
var hud: HUD
var touch: TouchControls
var dialogue: DialogueBox
var paper: PaperView
var photo: PhotoView
var shop: ShopUI
var menu: GameMenu
var sell_fx: SellFx
var sorting: SortingGame
var tint: CanvasModulate
var top_root: Control
var fade: ColorRect
var title: TitleScreen
var ending: EndingScreen
var runner: DialogueRunner

var mode: String = "title"
var touch_mode: String = "auto"
var _glitch_pulse := 0.0
var _glitch_hold := 0.0
var _ring_t := 0.0
var _shake := 0.0
var day_card: Label
var _autotest := false
var _autotest_t := 0.0


func _ready() -> void:
	_build_scene()
	runner = DialogueRunner.new(dialogue, self)
	GameState.notify.connect(func(t, e): hud.toast(t, e))
	GameState.changed.connect(_on_state_changed)
	get_tree().root.size_changed.connect(_on_resized)
	# ブラウザ自動テスト用: URL に ?autotest があるときだけ状態を window.__ob に公開する
	if OS.has_feature("web"):
		var href: Variant = JavaScriptBridge.eval("window.location.search", true)
		_autotest = typeof(href) == TYPE_STRING and str(href).contains("autotest")
	_show_title()


# ================================================================== build
func _build_scene() -> void:
	world = World.new()
	world.name = "World"
	add_child(world)
	world.warp_triggered.connect(_on_warp)
	world.target_changed.connect(_on_target_changed)
	# 時間帯による色味 (ワールドだけに掛かる)
	tint = CanvasModulate.new()
	add_child(tint)

	fx_layer = CanvasLayer.new()
	fx_layer.layer = 2
	add_child(fx_layer)
	rain = Control.new()
	rain.set_script(load("res://scripts/ui/rain_layer.gd"))
	fx_layer.add_child(rain)
	noise = ColorRect.new()
	noise.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	noise.mouse_filter = Control.MOUSE_FILTER_IGNORE
	noise_mat = ShaderMaterial.new()
	noise_mat.shader = load("res://shaders/screen_noise.gdshader")
	noise.material = noise_mat
	fx_layer.add_child(noise)

	var ui_layer := CanvasLayer.new()
	ui_layer.layer = 10
	add_child(ui_layer)
	ui_root = _full_control("UIRoot")
	ui_layer.add_child(ui_root)
	hud = HUD.new()
	hud.world = world
	ui_root.add_child(hud)
	hud.menu_pressed.connect(_open_menu)
	touch = TouchControls.new()
	ui_root.add_child(touch)
	touch.interact_pressed.connect(_try_interact)
	dialogue = DialogueBox.new()
	ui_root.add_child(dialogue)
	paper = PaperView.new()
	ui_root.add_child(paper)
	photo = PhotoView.new()
	ui_root.add_child(photo)
	shop = ShopUI.new()
	ui_root.add_child(shop)
	menu = GameMenu.new()
	ui_root.add_child(menu)
	menu.closed.connect(_close_menu)
	menu.save_requested.connect(func(): GameState.save_game())
	menu.title_requested.connect(func():
		menu.visible = false
		_back_to_title())
	menu.touch_mode_changed.connect(func(m):
		touch_mode = m
		touch.enabled_mode = m
		_on_target_changed(world.current_target))
	sorting = SortingGame.new()
	ui_root.add_child(sorting)
	sell_fx = SellFx.new()
	ui_root.add_child(sell_fx)
	sell_fx.glitch_level.connect(func(v): _glitch_hold = v)
	# 通知はメニューや会話より手前に出す
	hud.remove_child(hud.toast_box)
	ui_root.add_child(hud.toast_box)

	var top_layer := CanvasLayer.new()
	top_layer.layer = 20
	add_child(top_layer)
	top_root = _full_control("TopRoot")
	top_root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	top_layer.add_child(top_root)
	title = TitleScreen.new()
	top_root.add_child(title)
	title.new_game_requested.connect(_start_new_game)
	title.continue_requested.connect(_continue_game)
	ending = EndingScreen.new()
	top_root.add_child(ending)
	fade = ColorRect.new()
	fade.color = Color(0, 0, 0, 0)
	fade.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	fade.mouse_filter = Control.MOUSE_FILTER_IGNORE
	top_root.add_child(fade)
	day_card = UITheme.make_label("", 28, Color.WHITE)
	day_card.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	day_card.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	day_card.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	day_card.modulate.a = 0.0
	top_root.add_child(day_card)
	world.ghost_vanished.connect(_on_ghost_vanished)
	_on_state_changed()


func _full_control(n: String) -> Control:
	var c := Control.new()
	c.name = n
	c.theme = UITheme.get_theme()
	c.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	c.mouse_filter = Control.MOUSE_FILTER_IGNORE
	return c


func _on_resized() -> void:
	# safe area は画面回転などで変わるので再計算させる
	for c in [hud, dialogue, shop, menu, title]:
		if c.has_method("_layout"):
			c.call_deferred("_layout")


# ================================================================== title / start
func _show_title() -> void:
	mode = "title"
	_set_explore(false)
	title.visible = true
	hud.visible = false
	rain.visible = false
	Sound.bgm("title")
	Sound.rain("out")
	title.refresh()


func _start_new_game() -> void:
	title.visible = false
	GameState.new_game()
	runner.aborted = false
	fade.color.a = 1.0
	hud.visible = true
	await _enter_map(str(GameData.cfg("start_map", "home")), str(GameData.cfg("start_spawn", "start")), null, true)


func _continue_game() -> void:
	if not GameState.load_game():
		return
	title.visible = false
	runner.aborted = false
	fade.color.a = 1.0
	hud.visible = true
	var pos: Variant = GameState.player_pos if GameState.has_player_pos else null
	await _enter_map(GameState.map_id, GameState.spawn_name, pos, false, GameState.facing)
	GameState.notify.emit("%d日目から再開しました" % GameState.day, false)


func _back_to_title() -> void:
	runner.aborted = true
	dialogue.close()
	shop.visible = false
	sorting.visible = false
	paper.visible = false
	photo.visible = false
	_show_title()


# ================================================================== map flow
func _enter_map(id: String, spawn: String, pos: Variant = null, keep_black: bool = false, facing: String = "") -> void:
	mode = "busy"
	_set_explore(false)
	if fade.color.a < 1.0:
		await _fade_to(1.0, 0.18)
	if not world.load_map(id, spawn, pos, facing):
		GameState.notify.emit("マップ「%s」を読み込めませんでした" % id, true)
		world.load_map("home", "start")
	rain.visible = world.is_outdoor()
	_apply_map_audio()
	hud.refresh()
	if not keep_black:
		await _fade_to(0.0, 0.22)
	hud.flash_place(world.map_name())
	# マップに入ったときのイベント
	for ev in world.map.get("on_enter", []):
		if runner.aborted:
			return
		if GameState.eval_cond(ev.get("if", "")):
			await runner.run(str(ev.get("script", "")))
	dialogue.close()
	if fade.color.a > 0.0:
		await _fade_to(0.0, 0.3)
	if runner.aborted:
		return
	GameState.save_game(true)
	_resume_explore()


func _on_warp(to_map: String, spawn: String) -> void:
	if mode != "explore":
		return
	Sound.se("door")
	await _enter_map(to_map, spawn)


func _apply_map_audio() -> void:
	Sound.bgm(str(world.map.get("bgm", "")))
	Sound.rain("out" if world.is_outdoor() else "in")


func _fade_to(a: float, dur: float) -> void:
	var tw := create_tween()
	tw.tween_property(fade, "color:a", a, dur)
	await tw.finished


func _set_explore(on: bool) -> void:
	world.player.control_enabled = on
	touch.active = on
	if not on:
		touch.reset()
		world.player.touch_vector = Vector2.ZERO
	hud.set_prompt(world.current_target if on else null, touch.is_shown())


func _resume_explore() -> void:
	if runner.aborted or title.visible:
		return
	mode = "explore"
	_set_explore(true)
	_on_target_changed(world.find_target())


# ================================================================== interaction
func _unhandled_input(event: InputEvent) -> void:
	if mode != "explore":
		return
	if event.is_action_pressed("interact", false):
		get_viewport().set_input_as_handled()
		_try_interact()
	elif event.is_action_pressed("menu", false):
		get_viewport().set_input_as_handled()
		_open_menu()


func _process(delta: float) -> void:
	if mode == "explore":
		world.player.touch_vector = touch.vector
	# 着信中は電話が鳴り続ける
	if GameState.has_flag("call_pending") and world.map_id == "home" and not title.visible:
		_ring_t -= delta
		if _ring_t <= 0.0:
			_ring_t = 2.4
			Sound.se("ring")
	if _shake > 0.0:
		_shake = maxf(0.0, _shake - delta)
		world.camera.offset = Vector2(randf_range(-1, 1), randf_range(-1, 1)) * 3.0 * (_shake / 0.5)
	elif world.camera.offset != Vector2.ZERO:
		world.camera.offset = Vector2.ZERO
	# 一時的なグリッチ
	_glitch_pulse = maxf(0.0, _glitch_pulse - delta * 1.2)
	noise_mat.set_shader_parameter("glitch", maxf(_glitch_pulse, _glitch_hold))
	if _autotest:
		_autotest_t += delta
		if _autotest_t > 0.1:
			_autotest_t = 0.0
			_publish_state()


func _publish_state() -> void:
	var p := world.player.position
	var st := {
		"mode": mode, "map": world.map_id, "ios": WebPlatform.is_ios(), "fs_ok": WebPlatform.can_toggle_fullscreen(), "fps": Engine.get_frames_per_second(), "x": p.x, "y": p.y,
		"dialog": dialogue._mode if dialogue.visible else "",
		"typing": dialogue._typing,
		"paper": paper.visible, "photo": photo.visible, "shop": shop.visible,
		"fx": sell_fx.visible, "title": title.visible, "can_continue": not title.cont_button.disabled,
		"target": str(world.current_target.data.get("id", "")) if world.current_target else "",
		"money": GameState.money, "sold": GameState.sold, "flags": GameState.flags.keys(),
	}
	JavaScriptBridge.eval("window.__ob=" + JSON.stringify(st) + ";", true)
	# 自動テスト用コマンド (?autotest のときだけ): window.__obcmd = "money:50000" など
	var cmd: Variant = JavaScriptBridge.eval("(function(){var c=window.__obcmd||'';window.__obcmd='';return c;})()", true)
	if typeof(cmd) == TYPE_STRING and str(cmd) != "":
		_debug_command(str(cmd))


func _debug_command(cmd: String) -> void:
	var p := cmd.split(":")
	match p[0]:
		"money": GameState.money = int(p[1]); GameState.changed.emit()
		"time": GameState.time_slot = int(p[1]); GameState.changed.emit()
		"flag": GameState.set_flag(p[1])
		"sell": GameState.sold.append(p[1]); GameState.changed.emit()
		"map": world.load_map(p[1], p[2] if p.size() > 2 else "")
		"event": run_event(p[1])
		"sort_time": sorting.time_left = float(p[1])
		"day": GameState.day = int(p[1]); GameState.changed.emit()
		"debt": GameState.debt = int(p[1]); GameState.changed.emit()
		"hide":
			match p[1]:
				"noise": noise.visible = false
				"rain": rain.visible = false
				"tiles": world.tile_layer.visible = false
				"objects":
					for o in world.objects: o.visible = false
				"hud": hud.visible = false


func _try_interact() -> void:
	if mode != "explore":
		return
	var t := world.find_target()
	if t == null:
		return
	if t.kind == "warp":
		await _enter_map(str(t.data.get("to", "")), str(t.data.get("spawn", "")))
		return
	t.face_towards(world.player.position)
	await run_event(str(t.data.get("script", "")))


## 会話・イベントを実行し、終わったら探索に戻る
func run_event(script_id: String) -> void:
	if script_id == "":
		return
	mode = "busy"
	_set_explore(false)
	await runner.run(script_id)
	dialogue.close()
	if runner.aborted:
		return
	_resume_explore()


func _on_target_changed(obj: WorldObject) -> void:
	var shown := touch.is_shown()
	hud.set_prompt(obj if mode == "explore" else null, shown)
	touch.has_target = obj != null
	touch.label = obj.prompt_text() if obj != null else "調べる"


func _on_state_changed() -> void:
	if noise_mat:
		noise_mat.set_shader_parameter("intensity", GameState.noise_level())
	if tint:
		var tints: Array = GameData.cfg("time_tints", [])
		var c := Color.WHITE
		if GameState.time_slot < tints.size():
			c = Color(str(tints[GameState.time_slot]))
		tint.color = c


# ================================================================== menu
func _open_menu() -> void:
	if mode != "explore":
		return
	mode = "busy"
	_set_explore(false)
	menu.open_menu(touch_mode)


func _close_menu() -> void:
	menu.visible = false
	_resume_explore()


# ================================================================== actions (dialogue.json の action)
func do_action(action: String, arg: Variant) -> void:
	match action:
		"open_shop":
			await _action_shop()
		"sleep":
			await _action_sleep()
		"save":
			GameState.save_game()
		"photo":
			await photo.show_photo(str(arg) if arg != null else "mother")
		"work_sort":
			await _action_work_sort()
		"work_carry":
			await _action_work_carry()
		"repay":
			var paid := GameState.repay(int(arg) if arg != null else -1)
			if paid > 0:
				Sound.se("atm")
				GameState.notify.emit("%s円を返済しました" % GameState.format_yen(paid), false)
				GameState.save_game(true)
		"warp":
			var parts := str(arg).split(":")
			dialogue.close()
			await _enter_map(parts[0], parts[1] if parts.size() > 1 else "")
			mode = "busy"
			_set_explore(false)
		"paper":
			await paper.show_paper(str(arg))
		"glitch":
			_glitch_pulse = float(arg) if arg != null else 0.6
			Sound.se("glitch")
			await get_tree().create_timer(0.35).timeout
		"shake":
			_shake = 0.5
			_glitch_pulse = 0.3
			Sound.se("heartbeat")
		"se":
			Sound.se(str(arg))
		"advance_time":
			GameState.advance_time(int(arg) if arg != null else 1)
		"rest_until_night":
			dialogue.close()
			await _fade_to(1.0, 0.6)
			GameState.time_slot = 3
			GameState.changed.emit()
			await get_tree().create_timer(0.4).timeout
			await _fade_to(0.0, 0.6)
		"day_card":
			await _show_day_card()
		"sell_secret":
			dialogue.close()
			Sound.se("sell")
			_glitch_hold = 1.0
			await _fade_to(1.0, 1.2)
			_glitch_hold = 0.0
			await get_tree().create_timer(0.6).timeout
			await _fade_to(0.0, 1.0)
		"ring":
			_glitch_pulse = 0.25
			Sound.se("ring")
			_ring_t = 2.4
		"ring_stop":
			GameState.set_flag("call_pending", false)
		"fade_in_slow":
			await _fade_to(0.0, 2.0)
		"ending":
			await _action_ending(str(arg))
		_:
			push_warning("未知のアクション: " + action)


func _action_shop() -> void:
	dialogue.close()
	var sold_id: String = await shop.open_shop()
	if sold_id == "":
		await dialogue.say("karasuma", "smile", "またのお越しを。……記憶は、逃げませんから。")
		return
	var mem := GameData.get_memory(sold_id)
	dialogue.close()
	Sound.bgm("")
	await sell_fx.play(mem)
	Sound.bgm("shop")
	_glitch_hold = 0.0
	if not GameState.sell_memory(sold_id):
		GameState.notify.emit("売却処理に失敗しました", true)
		return
	GameState.save_game(true)
	_on_state_changed()
	var after := str(mem.get("after_script", ""))
	if after != "":
		await runner.run(after)


func _action_work_sort() -> void:
	dialogue.close()
	var res: Dictionary = await sorting.play()
	GameState.last_pay = int(res.get("pay", 0))
	GameState.add_money(GameState.last_pay)
	GameState.advance_time(int(GameState.work_cfg().get("time_cost", 2)))
	GameState.save_game(true)
	await runner.run("work_done")


func _action_work_carry() -> void:
	dialogue.close()
	await _fade_to(1.0, 0.6)
	GameState.last_pay = int(GameState.work_cfg().get("carry_pay", 3500))
	GameState.add_money(GameState.last_pay)
	GameState.advance_time(int(GameState.work_cfg().get("time_cost", 2)))
	await get_tree().create_timer(0.5).timeout
	await _fade_to(0.0, 0.6)
	GameState.save_game(true)
	await runner.run("work_carry_done")


func _action_sleep() -> void:
	dialogue.close()
	await _fade_to(1.0, 0.8)
	var result := GameState.advance_day()
	world.load_map("home", "start")
	rain.visible = false
	_apply_map_audio()
	hud.refresh()
	await get_tree().create_timer(0.6).timeout
	await _fade_to(0.0, 0.8)
	if result == "deadline":
		if GameState.try_repay():
			await runner.run("deadline_paid")
		else:
			await runner.run("deadline_failed")
		return
	GameState.save_game()
	await runner.run("sleep_morning")


func _action_ending(id: String) -> void:
	dialogue.close()
	Sound.bgm("ending", 2.5)
	Sound.rain("off" if id in ["protected", "secret"] else "in")
	await _fade_to(1.0, 1.4)
	runner.aborted = true
	GameState.record_ending(id)
	GameState.delete_save()
	fade.color.a = 0.0
	await ending.show_ending(id)
	_show_title()


## 「2日目　返済期限まであと6日」のカード (眠った翌朝)
func _show_day_card() -> void:
	dialogue.close()
	day_card.text = "%d日目\n返済期限まで あと%d日" % [GameState.day, GameState.days_left()]
	fade.color.a = 1.0
	var tw := create_tween()
	tw.tween_property(day_card, "modulate:a", 1.0, 0.5)
	tw.tween_interval(1.1)
	tw.tween_property(day_card, "modulate:a", 0.0, 0.5)
	tw.tween_property(fade, "color:a", 0.0, 0.6)
	await tw.finished


func _on_ghost_vanished() -> void:
	_glitch_pulse = 0.8
	Sound.se("glitch")
	if mode == "explore":
		await run_event("ghost_vanish")
