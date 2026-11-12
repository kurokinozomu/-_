class_name SortingGame
extends Control
## 倉庫の仕分けミニゲーム。
## ベルトで流れてくる荷物を、宛先の区画に対応する棚 (左・中・右) へ振り分ける。
##   var result: Dictionary = await sorting.play()
##   → {pay, correct, wrong, missed}
##
## 記憶による変化:
##   仕事の記憶あり … 正しい棚が少し遅れてうっすら光る (体が覚えている)。いつもの棚割り。
##   仕事の記憶なし … 補助なし・棚割りが毎回変わる・新人日給。
##   文字の記憶なし … 区画名が読めない。図形アイコンで判断する (擦れて図形が見えない荷物もある)。

signal _finished(result: Dictionary)
signal _start_pressed

const KEYS_LEFT := [KEY_A, KEY_LEFT, KEY_1, KEY_KP_1]
const KEYS_MID := [KEY_S, KEY_DOWN, KEY_2, KEY_KP_2]
const KEYS_RIGHT := [KEY_D, KEY_RIGHT, KEY_3, KEY_KP_3]

var cfg: Dictionary = {}
var districts: Array = []
var bins: Array = []          ## bins[i] = [district_idx, district_idx]
var aid: bool = true
var newbie: bool = false
var state: String = "idle"    ## idle / intro / play / result
var time_left: float = 0.0
var correct: int = 0
var wrong: int = 0
var missed: int = 0
var pkg: Dictionary = {}      ## {district, torn, t}
var _since_spawn: float = 0.0   ## 前の荷物が出てからの時間 (一定間隔で流れてくる)
var _flash: Array = [0.0, 0.0, 0.0]
var _flash_ok: Array = [true, true, true]
var _popups: Array = []
var _belt_t: float = 0.0
var _rng := RandomNumberGenerator.new()

var start_button: Button
var done_button: Button
var info_label: RichTextLabel


func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_STOP
	visible = false
	info_label = RichTextLabel.new()
	info_label.bbcode_enabled = true
	info_label.fit_content = true
	info_label.scroll_active = false
	info_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	info_label.add_theme_font_size_override("normal_font_size", 14)
	add_child(info_label)
	start_button = UITheme.make_button("作業開始", 180)
	start_button.pressed.connect(func(): _start_pressed.emit())
	add_child(start_button)
	done_button = UITheme.make_button("報酬を受け取る", 200)
	done_button.pressed.connect(_on_done)
	add_child(done_button)
	resized.connect(_layout)


## ミニゲームを1回遊ぶ。結果の辞書を返す。
func play(seed: int = -1) -> Dictionary:
	cfg = GameState.work_cfg()
	districts = cfg.get("districts", [])
	newbie = GameState.is_sold("work")
	aid = not newbie
	if seed >= 0:
		_rng.seed = seed
	else:
		_rng.randomize()
	_setup_bins()
	correct = 0
	wrong = 0
	missed = 0
	pkg = {}
	_popups.clear()
	time_left = float(cfg.get("duration", 40.0))
	visible = true
	_show_intro()
	await _start_pressed
	state = "play"
	Sound.se("confirm")
	Sound.bgm("work")
	start_button.visible = false
	info_label.visible = false
	_since_spawn = float(cfg.get("spawn_interval", 1.6)) - 0.4
	var result: Dictionary = await _finished
	visible = false
	state = "idle"
	return result


func _setup_bins() -> void:
	bins = []
	var vet: Array = cfg.get("veteran_bins", [[0, 1], [2, 3], [4, 5]])
	if newbie:
		# 慣れた棚割りを忘れた: 毎回ちがう組み合わせ (棚の表示を読むしかない)
		var order := range(districts.size())
		for i in range(order.size() - 1, 0, -1):
			var j := _rng.randi_range(0, i)
			var tmp: int = order[i]
			order[i] = order[j]
			order[j] = tmp
		for b in 3:
			bins.append([order[b * 2], order[b * 2 + 1]])
	else:
		for b in vet:
			bins.append([int(b[0]), int(b[1])])


func base_pay() -> int:
	return int(cfg.get("newbie_base_pay" if newbie else "base_pay", 1500))


func current_pay() -> int:
	var per := int(cfg.get("per_correct", 300))
	var pen := int(cfg.get("per_wrong", 200))
	return maxi(0, base_pay() + correct * per - (wrong + missed) * pen)


func correct_bin() -> int:
	if pkg.is_empty():
		return -1
	for i in bins.size():
		if bins[i].has(int(pkg["district"])):
			return i
	return -1


# ------------------------------------------------------------------ flow
func _show_intro() -> void:
	state = "intro"
	var t := "[center][color=#ffd25a]仕分けライン[/color]\n\n"
	t += "流れてくる荷物の[color=#45e0ff]宛先[/color]を見て、同じ区画の棚に振り分ける。\n"
	t += "制限時間 %d秒。ベルトの端まで流れたら見逃し。\n\n" % int(cfg.get("duration", 40))
	t += "[color=#8a88aa]PC：A/S/D・←↓→・1/2/3　スマホ・マウス：棚をタップ[/color]\n\n"
	t += "日給 %s円 ＋ 正解1件 %s円　ミス・見逃し1件 −%s円\n" % [
		GameState.format_yen(base_pay()), GameState.format_yen(int(cfg.get("per_correct", 300))), GameState.format_yen(int(cfg.get("per_wrong", 200)))]
	if aid:
		t += "\n[color=#9dff9a]体が手順を覚えている。正しい棚が、なんとなく分かる。[/color]"
	else:
		t += "\n[color=#ff6a7a]手順が思い出せない。棚の表示をよく見るしかない。[/color]"
	if GameState.is_sold("letters"):
		t += "\n[color=#ff6a7a]宛先の文字が読めない。図形を頼りにしよう。[/color]"
	t += "[/center]"
	info_label.text = t
	info_label.visible = true
	start_button.visible = true
	done_button.visible = false
	_layout()
	start_button.grab_focus()


func _end() -> void:
	state = "result"
	pkg = {}
	var t := "[center][color=#ffd25a]作業終了[/color]\n\n"
	t += "正解 %d件　ミス %d件　見逃し %d件\n\n" % [correct, wrong, missed]
	t += "報酬　[color=#9dff9a]%s円[/color][/center]" % GameState.format_yen(current_pay())
	info_label.text = t
	info_label.visible = true
	done_button.visible = true
	_layout()
	done_button.grab_focus()


func _on_done() -> void:
	if state != "result":
		return
	Sound.se("coin")
	_finished.emit({"pay": current_pay(), "correct": correct, "wrong": wrong, "missed": missed})


func _spawn() -> void:
	pkg = {
		"district": _rng.randi_range(0, districts.size() - 1),
		"torn": _rng.randf() < float(cfg.get("torn_icon_rate", 0.25)),
		"t": 0.0,
	}
	_since_spawn = 0.0


## 棚に入れる (0=左, 1=中, 2=右)
func sort_into(b: int) -> void:
	if state != "play" or pkg.is_empty() or b < 0 or b > 2:
		return
	var ok := b == correct_bin()
	Sound.se("correct" if ok else "wrong")
	if ok:
		correct += 1
		_popup(b, "+%d" % int(cfg.get("per_correct", 300)), UITheme.GOOD)
	else:
		wrong += 1
		_popup(b, "ミス", UITheme.WARN)
	_flash[b] = 1.0
	_flash_ok[b] = ok
	pkg = {}


func _popup(b: int, text: String, col: Color) -> void:
	_popups.append({"b": b, "text": text, "col": col, "t": 0.0})


func _process(delta: float) -> void:
	if not visible:
		return
	_belt_t += delta
	for i in 3:
		_flash[i] = maxf(0.0, _flash[i] - delta * 3.0)
	for p in _popups:
		p["t"] += delta
	_popups = _popups.filter(func(p): return p["t"] < 0.8)
	if state == "play":
		time_left -= delta
		if time_left <= 0.0:
			time_left = 0.0
			_end()
		elif pkg.is_empty():
			_since_spawn += delta
			if _since_spawn >= float(cfg.get("spawn_interval", 1.6)):
				_spawn()
		else:
			_since_spawn += delta
			pkg["t"] += delta
			if pkg["t"] >= float(cfg.get("travel_time", 2.6)):
				missed += 1
				Sound.se("wrong", 0.8)
				_popup(1, "見逃し", UITheme.WARN)
				pkg = {}
	queue_redraw()


# ------------------------------------------------------------------ input
func _unhandled_input(event: InputEvent) -> void:
	if not visible:
		return
	if event is InputEventKey and event.pressed and not event.echo:
		var k: int = event.physical_keycode
		var b := -1
		if k in KEYS_LEFT:
			b = 0
		elif k in KEYS_MID:
			b = 1
		elif k in KEYS_RIGHT:
			b = 2
		if b >= 0 and state == "play":
			sort_into(b)
			get_viewport().set_input_as_handled()
			return
		if event.is_action_pressed("interact", false):
			var f := get_viewport().gui_get_focus_owner()
			if f is Button and f.visible:
				f.emit_signal("pressed")
			get_viewport().set_input_as_handled()


func _gui_input(event: InputEvent) -> void:
	if state != "play":
		return
	if event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT:
		for i in 3:
			if bin_rect(i).has_point(event.position):
				sort_into(i)
				accept_event()
				return


# ------------------------------------------------------------------ layout / draw
func _margins() -> Vector4:
	return UITheme.safe_margins(get_viewport())


func bin_rect(i: int) -> Rect2:
	var m := _margins()
	var w := (size.x - m.x - m.z - 24.0) / 3.0
	var h := minf(118.0, size.y * 0.34)
	return Rect2(m.x + 6.0 + i * (w + 6.0), size.y - m.w - h - 4.0, w, h)


func belt_rect() -> Rect2:
	var m := _margins()
	var top := m.y + 40.0
	var h := minf(96.0, bin_rect(0).position.y - top - 12.0)
	return Rect2(m.x, top + 8.0, size.x - m.x - m.z, h)


func _layout() -> void:
	info_label.size = Vector2(minf(520.0, size.x - 40.0), 0)
	info_label.reset_size()
	info_label.size.x = minf(520.0, size.x - 40.0)
	info_label.position = Vector2((size.x - info_label.size.x) / 2.0, size.y * 0.12)
	var by := info_label.position.y + info_label.get_content_height() + 16.0
	start_button.position = Vector2((size.x - start_button.size.x) / 2.0, minf(by, size.y - 50.0))
	done_button.position = Vector2((size.x - done_button.size.x) / 2.0, minf(by, size.y - 50.0))


func _draw() -> void:
	var f := UITheme.font()
	draw_rect(Rect2(Vector2.ZERO, size), Color(0.03, 0.03, 0.07, 1.0))
	if state == "intro" or state == "result":
		_draw_bins(f, false)
		draw_rect(Rect2(Vector2.ZERO, size), Color(0.03, 0.03, 0.07, 0.78))
		return
	var m := _margins()
	# ヘッダ: 残り時間と成績
	var dur := float(cfg.get("duration", 40.0))
	var bar := Rect2(m.x + 4, m.y + 4, size.x - m.x - m.z - 8, 8)
	draw_rect(bar, Color("#1a1830"))
	var k := clampf(time_left / dur, 0.0, 1.0)
	draw_rect(Rect2(bar.position, Vector2(bar.size.x * k, bar.size.y)), UITheme.WARN if k < 0.25 else UITheme.ACCENT)
	var head := "残り %d秒　正解 %d　ミス %d　見逃し %d　報酬 %s円" % [ceili(time_left), correct, wrong, missed, GameState.format_yen(current_pay())]
	draw_string(f, Vector2(m.x + 6, m.y + 32), head, HORIZONTAL_ALIGNMENT_LEFT, -1, 14, UITheme.TEXT)
	# ベルト
	var br := belt_rect()
	draw_rect(br, Color("#202230"))
	var stripe := 24.0
	var off := fmod(_belt_t * 60.0, stripe)
	var x := br.position.x - stripe + off
	while x < br.end.x:
		draw_rect(Rect2(maxf(x, br.position.x), br.position.y + 4, 3, br.size.y - 8), Color("#2c2e40"))
		x += stripe
	draw_rect(Rect2(br.position.x, br.position.y, br.size.x, 3), Color("#4a4e64"))
	draw_rect(Rect2(br.position.x, br.end.y - 3, br.size.x, 3), Color("#4a4e64"))
	draw_rect(Rect2(br.position.x, br.position.y, 6, br.size.y), Color(1.0, 0.4, 0.45, 0.6))
	if not pkg.is_empty():
		_draw_package(f, br)
	_draw_bins(f, true)
	for p in _popups:
		var r := bin_rect(int(p["b"]))
		var a: float = 1.0 - p["t"] / 0.8
		var tw := f.get_string_size(p["text"], HORIZONTAL_ALIGNMENT_LEFT, -1, 20).x
		draw_string(f, Vector2(r.get_center().x - tw / 2.0, r.position.y - 6 - p["t"] * 30.0), p["text"], HORIZONTAL_ALIGNMENT_LEFT, -1, 20, Color(p["col"], a))


func _draw_package(f: Font, br: Rect2) -> void:
	var travel := float(cfg.get("travel_time", 2.6))
	var k := clampf(float(pkg["t"]) / travel, 0.0, 1.0)
	var pw := minf(150.0, br.size.x * 0.3)
	var ph := br.size.y - 14.0
	var px := lerpf(br.end.x - pw - 6.0, br.position.x + 8.0, k)
	var r := Rect2(px, br.position.y + 7.0, pw, ph)
	draw_rect(r, Color("#a07848"))
	draw_rect(Rect2(r.position.x, r.position.y, r.size.x, 4), Color("#b88a58"))
	draw_rect(Rect2(r.get_center().x - 3, r.position.y, 6, r.size.y), Color("#c8a070", 0.6))
	# 伝票
	var d: Dictionary = districts[int(pkg["district"])]
	var tag := Rect2(r.position.x + 8, r.position.y + 8, r.size.x - 16, r.size.y - 16)
	draw_rect(tag, Color("#ece6d6"))
	var name := GameState.plain_read(str(d["name"]))
	draw_string(f, tag.position + Vector2(tag.size.y + 4, tag.size.y * 0.5 + 8), name, HORIZONTAL_ALIGNMENT_LEFT, -1, 22, Color("#1a1a24"))
	var ic := tag.position + Vector2(tag.size.y * 0.5, tag.size.y * 0.5)
	if bool(pkg["torn"]):
		# 擦れて図形が見えない
		draw_rect(Rect2(ic - Vector2(14, 14), Vector2(28, 28)), Color("#c8c0b0"))
		for i in 5:
			draw_line(ic + Vector2(-14, -10 + i * 5), ic + Vector2(14, -14 + i * 6), Color("#a09888"), 2.0)
	else:
		PixelArt.draw_shape(self, str(d["shape"]), ic, 13.0, Color(str(d["color"])))


func _draw_bins(f: Font, show_aid: bool) -> void:
	var cb := correct_bin()
	var aid_on := show_aid and aid and not pkg.is_empty() and float(pkg["t"]) >= float(cfg.get("aid_delay", 0.35))
	var keys := ["A / ← / 1", "S / ↓ / 2", "D / → / 3"]
	for i in 3:
		var r := bin_rect(i)
		draw_rect(r, Color("#151329"))
		var border := UITheme.LINE
		if aid_on and i == cb:
			var pulse := 0.35 + 0.25 * sin(_belt_t * 8.0)
			draw_rect(r, Color(0.6, 1.0, 0.6, pulse * 0.35))
			border = UITheme.GOOD
		if _flash[i] > 0.0:
			draw_rect(r, Color(UITheme.GOOD if _flash_ok[i] else UITheme.WARN, _flash[i] * 0.4))
		draw_rect(r, border, false, 2.0)
		var lines: Array = bins[i] if i < bins.size() else []
		for j in lines.size():
			var d: Dictionary = districts[int(lines[j])]
			var y := r.position.y + 26.0 + j * 34.0
			PixelArt.draw_shape(self, str(d["shape"]), Vector2(r.position.x + 22, y), 10.0, Color(str(d["color"])))
			draw_string(f, Vector2(r.position.x + 40, y + 7), GameState.plain_read(str(d["name"])), HORIZONTAL_ALIGNMENT_LEFT, -1, 18, UITheme.TEXT)
		draw_string(f, Vector2(r.position.x + 8, r.end.y - 8), keys[i], HORIZONTAL_ALIGNMENT_LEFT, -1, 11, UITheme.TEXT_DIM)


# ------------------------------------------------------------------ test hooks
## 自動テスト用: 現在の荷物を正しく (または間違えて) 仕分ける
func debug_answer(right: bool) -> void:
	var c := correct_bin()
	if c < 0:
		return
	sort_into(c if right else (c + 1) % 3)
