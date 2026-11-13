class_name WebPlatform
extends RefCounted
## ブラウザ・端末ごとの違いを吸収する小さな窓口。Web 以外では安全な既定値を返す。


static func _js(code: String) -> Variant:
	if not OS.has_feature("web"):
		return null
	return JavaScriptBridge.eval(code, true)


## JS の真偽値は 1/0 (int) で返ってくるので bool に揃える
static func _js_bool(code: String) -> bool:
	var r: Variant = _js(code)
	match typeof(r):
		TYPE_BOOL: return r
		TYPE_INT, TYPE_FLOAT: return r != 0
		TYPE_STRING: return r == "true"
	return false


## iPhone / iPad の Safari 系か
static func is_ios() -> bool:
	return _js_bool("/iPhone|iPad|iPod/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1)")


## ホーム画面から起動したアプリ表示 (アドレスバーなし) か
static func is_standalone() -> bool:
	return _js_bool("window.navigator.standalone === true || window.matchMedia('(display-mode: standalone)').matches || window.matchMedia('(display-mode: fullscreen)').matches")


## 全画面ボタンを出してよいか (iPhone の Safari は全画面 API を持たない)
static func can_toggle_fullscreen() -> bool:
	if not OS.has_feature("web"):
		return OS.has_feature("pc")
	return _js_bool("!!(document.fullscreenEnabled || document.webkitFullscreenEnabled)") and not is_standalone()


static func is_fullscreen() -> bool:
	return DisplayServer.window_get_mode() in [DisplayServer.WINDOW_MODE_FULLSCREEN, DisplayServer.WINDOW_MODE_EXCLUSIVE_FULLSCREEN]


## ボタンを押した瞬間 (ユーザー操作中) に呼ぶこと。ブラウザはそれ以外の全画面化を拒否する。
static func toggle_fullscreen() -> void:
	if is_fullscreen():
		DisplayServer.window_set_mode(DisplayServer.WINDOW_MODE_WINDOWED)
	else:
		DisplayServer.window_set_mode(DisplayServer.WINDOW_MODE_FULLSCREEN)
