extends Node
## BGM・環境音・効果音の再生と音量設定。音源は tools/gen_audio.py で合成したオリジナル。
##   Sound.bgm("town")   Sound.se("confirm")   Sound.rain("out" / "in" / "off")
## Web ではブラウザの仕様で、最初のタップ/クリックまで音が出ない (Godot が自動で再開する)。

const AUDIO_DIR := "res://assets/audio/"
const SETTINGS_PATH := "user://oblivion_settings.json"
const VOLUME_STEPS := [0.0, 0.35, 0.7, 1.0]
const VOLUME_NAMES := ["なし", "小", "中", "大"]

var volume_index: int = 2
var _bgm_a: AudioStreamPlayer
var _bgm_b: AudioStreamPlayer
var _bgm_cur: AudioStreamPlayer
var _bgm_name: String = ""
var _rain: AudioStreamPlayer
var _rain_lowpass: AudioEffectLowPassFilter
var _se_pool: Array[AudioStreamPlayer] = []
var _cache: Dictionary = {}
var _text_cooldown := 0.0
var _tweens: Dictionary = {}   ## プレイヤーごとのフェード (素早く曲を切り替えても止まらないように)


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	_setup_buses()
	_bgm_a = _player("BGM")
	_bgm_b = _player("BGM")
	_bgm_cur = _bgm_a
	_rain = _player("Rain")
	for i in 6:
		_se_pool.append(_player("SE"))
	load_settings()


func _setup_buses() -> void:
	for bus in ["BGM", "SE", "Rain"]:
		if AudioServer.get_bus_index(bus) == -1:
			AudioServer.add_bus()
			var idx := AudioServer.bus_count - 1
			AudioServer.set_bus_name(idx, bus)
			AudioServer.set_bus_send(idx, "Master")
	var ri := AudioServer.get_bus_index("Rain")
	_rain_lowpass = AudioEffectLowPassFilter.new()
	_rain_lowpass.cutoff_hz = 20000.0
	AudioServer.add_bus_effect(ri, _rain_lowpass)
	AudioServer.set_bus_volume_db(AudioServer.get_bus_index("BGM"), -4.0)
	AudioServer.set_bus_volume_db(ri, -6.0)


func _player(bus: String) -> AudioStreamPlayer:
	var p := AudioStreamPlayer.new()
	p.bus = bus
	add_child(p)
	return p


func _stream(name: String, loop: bool) -> AudioStream:
	var key := name + ("_loop" if loop else "")
	if _cache.has(key):
		return _cache[key]
	var path := AUDIO_DIR + name + ".ogg"
	if not ResourceLoader.exists(path):
		push_warning("音源がありません: " + path)
		return null
	var s: AudioStream = load(path)
	if loop and s is AudioStreamOggVorbis:
		s = s.duplicate()
		s.loop = true
	_cache[key] = s
	return s


# ------------------------------------------------------------------ BGM
func bgm(name: String, fade: float = 1.2) -> void:
	if name == _bgm_name:
		return
	_bgm_name = name
	var old := _bgm_cur
	var nxt := _bgm_b if _bgm_cur == _bgm_a else _bgm_a
	_bgm_cur = nxt
	if old.playing:
		var tw := _fade(old)
		tw.tween_property(old, "volume_db", -40.0, fade)
		tw.tween_callback(old.stop)
	if name == "":
		return
	var s := _stream("bgm_" + name, true)
	if s == null:
		return
	var tw2 := _fade(nxt)
	nxt.stream = s
	nxt.volume_db = -40.0
	nxt.play()
	tw2.tween_property(nxt, "volume_db", 0.0, fade)


func _fade(p: AudioStreamPlayer) -> Tween:
	if _tweens.has(p) and _tweens[p].is_valid():
		_tweens[p].kill()
	var tw := create_tween()
	_tweens[p] = tw
	return tw


func current_bgm() -> String:
	return _bgm_name


# ------------------------------------------------------------------ ambience
## "out" = 屋外の雨 / "in" = 屋内でくぐもった雨 / "off"
func rain(mode: String) -> void:
	if mode == "off":
		var t0 := _fade(_rain)
		t0.tween_property(_rain, "volume_db", -40.0, 0.8)
		t0.tween_callback(_rain.stop)
		return
	if not _rain.playing:
		_rain.stream = _stream("amb_rain", true)
		_rain.volume_db = -40.0
		_rain.play()
	_rain_lowpass.cutoff_hz = 20000.0 if mode == "out" else 700.0
	_fade(_rain).tween_property(_rain, "volume_db", 0.0 if mode == "out" else -6.0, 0.8)


# ------------------------------------------------------------------ SE
func se(name: String, pitch: float = 1.0) -> void:
	var s := _stream("se_" + name, false)
	if s == null:
		return
	for p in _se_pool:
		if not p.playing:
			p.stream = s
			p.pitch_scale = pitch
			p.play()
			return
	_se_pool[0].stream = s
	_se_pool[0].play()


## 文字送りの音 (鳴らしすぎないよう間引く)
func text_blip() -> void:
	if _text_cooldown <= 0.0:
		se("text", randf_range(0.95, 1.05))
		_text_cooldown = 0.06


func _process(delta: float) -> void:
	_text_cooldown -= delta


func _exit_tree() -> void:
	_cache.clear()


# ------------------------------------------------------------------ settings
func cycle_volume() -> String:
	volume_index = (volume_index + 1) % VOLUME_STEPS.size()
	_apply_volume()
	save_settings()
	return volume_name()


func volume_name() -> String:
	return VOLUME_NAMES[volume_index]


func _apply_volume() -> void:
	var v: float = VOLUME_STEPS[volume_index]
	AudioServer.set_bus_mute(0, v <= 0.0)
	AudioServer.set_bus_volume_db(0, linear_to_db(maxf(v, 0.001)))


func load_settings() -> void:
	if FileAccess.file_exists(SETTINGS_PATH):
		var d: Variant = JSON.parse_string(FileAccess.get_file_as_string(SETTINGS_PATH))
		if typeof(d) == TYPE_DICTIONARY:
			volume_index = clampi(int(d.get("volume", 2)), 0, VOLUME_STEPS.size() - 1)
	_apply_volume()


func save_settings() -> void:
	var f := FileAccess.open(SETTINGS_PATH, FileAccess.WRITE)
	if f:
		f.store_string(JSON.stringify({"volume": volume_index}))
