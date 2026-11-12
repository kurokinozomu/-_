class_name UITheme
extends RefCounted
## UI 全体の見た目 (フォント・ボタン・パネル) をコードで定義する。

const BG := Color("#0d0c1c")
const BG2 := Color("#171530")
const LINE := Color("#4a4680")
const TEXT := Color("#e4e2f4")
const TEXT_DIM := Color("#8a88aa")
const ACCENT := Color("#45e0ff")
const PINK := Color("#ff5ad0")
const WARN := Color("#ff6a7a")
const GOOD := Color("#9dff9a")

static var _theme: Theme
static var _font: Font


static func font() -> Font:
	if _font == null:
		_font = load("res://assets/fonts/DotGothic16-Regular.ttf")
	return _font


static func get_theme() -> Theme:
	if _theme != null:
		return _theme
	var t := Theme.new()
	t.default_font = font()
	t.default_font_size = 16
	t.set_color("font_color", "Label", TEXT)
	t.set_color("default_color", "RichTextLabel", TEXT)
	t.set_constant("line_separation", "RichTextLabel", 4)
	t.set_constant("line_spacing", "Label", 2)
	t.set_stylebox("panel", "Panel", box(Color(BG, 0.94), LINE, 2))
	t.set_stylebox("panel", "PanelContainer", box(Color(BG, 0.94), LINE, 2))
	t.set_stylebox("normal", "Button", box(BG2, LINE, 1, 8, 5))
	t.set_stylebox("hover", "Button", box(Color("#211e44"), ACCENT, 1, 8, 5))
	t.set_stylebox("pressed", "Button", box(Color("#2c2860"), PINK, 1, 8, 5))
	t.set_stylebox("focus", "Button", box(Color(0, 0, 0, 0), PINK, 2, 8, 5))
	t.set_stylebox("disabled", "Button", box(Color("#121124"), Color("#2a2848"), 1, 8, 5))
	t.set_color("font_color", "Button", TEXT)
	t.set_color("font_hover_color", "Button", Color.WHITE)
	t.set_color("font_pressed_color", "Button", Color.WHITE)
	t.set_color("font_focus_color", "Button", Color.WHITE)
	t.set_color("font_disabled_color", "Button", Color("#5a587a"))
	t.set_font_size("font_size", "Button", 16)
	t.set_stylebox("panel", "TooltipPanel", box(BG, LINE, 1))
	t.set_stylebox("scroll", "VScrollBar", box(Color("#121124"), Color("#121124"), 0, 2, 2))
	t.set_stylebox("grabber", "VScrollBar", box(LINE, LINE, 0, 2, 2))
	_theme = t
	return t


static func box(bg: Color, border: Color, bw: int, mx: int = 10, my: int = 8) -> StyleBoxFlat:
	var s := StyleBoxFlat.new()
	s.bg_color = bg
	s.border_color = border
	s.set_border_width_all(bw)
	s.content_margin_left = mx
	s.content_margin_right = mx
	s.content_margin_top = my
	s.content_margin_bottom = my
	return s


static func make_label(text: String, size: int = 16, color: Color = TEXT) -> Label:
	var l := Label.new()
	l.text = text
	l.add_theme_font_size_override("font_size", size)
	l.add_theme_color_override("font_color", color)
	return l


static func make_button(text: String, min_w: float = 0.0) -> Button:
	var b := Button.new()
	b.text = text
	b.custom_minimum_size = Vector2(min_w, 34)
	b.focus_mode = Control.FOCUS_ALL
	return b


## セーフエリア (ノッチ等) を考慮した、UI 座標系での余白 [left, top, right, bottom]。
static func safe_margins(vp: Viewport) -> Vector4:
	var base := 6.0
	var m := Vector4(base, base, base, base)
	var vsize := vp.get_visible_rect().size
	if OS.has_feature("web"):
		if Engine.has_singleton("JavaScriptBridge") or ClassDB.class_exists("JavaScriptBridge"):
			var js := "(function(){var s=getComputedStyle(document.documentElement);function g(n){return parseFloat(s.getPropertyValue(n))||0;}return [g('--sal'),g('--sat'),g('--sar'),g('--sab'),window.innerWidth,window.innerHeight].join(',');})()"
			var res: Variant = JavaScriptBridge.eval(js, true)
			if typeof(res) == TYPE_STRING:
				var parts: PackedStringArray = str(res).split(",")
				if parts.size() == 6 and float(parts[4]) > 0:
					var k := vsize.x / float(parts[4])
					m = Vector4(base + float(parts[0]) * k, base + float(parts[1]) * k, base + float(parts[2]) * k, base + float(parts[3]) * k)
		return m
	var screen := DisplayServer.screen_get_size()
	var safe := DisplayServer.get_display_safe_area()
	if screen.x > 0 and safe.size.x > 0 and safe.size != screen:
		var kx := vsize.x / float(screen.x)
		var ky := vsize.y / float(screen.y)
		m.x = base + safe.position.x * kx
		m.y = base + safe.position.y * ky
		m.z = base + (screen.x - safe.end.x) * kx
		m.w = base + (screen.y - safe.end.y) * ky
	return m
