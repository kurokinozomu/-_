class_name PixelArt
extends RefCounted
## コードだけで描くオリジナルのドット絵 (仮素材)。
## 外部画像を使わないので著作権の心配がなく、Web版のダウンロードも軽い。
## 本番素材に差し替えるときは、この描画関数を Sprite2D/AtlasTexture に置き換えればよい。

const TILE := 16

# ---- palette (暗い青・灰・紫 + ネオン)
const C_VOID := Color("#07070f")
const C_WALL_TOP := Color("#15142a")
const C_WALL_FACE := Color("#2b2a52")
const C_WALL_FACE2 := Color("#24234a")
const C_WAINSCOT := Color("#1b1a36")
const C_WOOD_A := Color("#3a2e40")
const C_WOOD_B := Color("#423448")
const C_WOOD_LINE := Color("#2c2232")
const C_KITCHEN_A := Color("#2e3546")
const C_KITCHEN_B := Color("#363e52")
const C_SHOP_A := Color("#1c1230")
const C_SHOP_B := Color("#26193e")
const C_ROOF := Color("#17182a")
const C_ROOF_LINE := Color("#202238")
const C_FACADE := Color("#2b2f47")
const C_FACADE_LINE := Color("#23273c")
const C_WIN_DARK := Color("#171a2b")
const C_WIN_WARM := Color("#e8c27a")
const C_WIN_COOL := Color("#6ac4ee")
const C_METAL := Color("#3a3e4c")
const C_METAL_LINE := Color("#30333f")
const C_SHUTTER := Color("#4a4e5e")
const C_BRICK := Color("#47282c")
const C_BRICK_LINE := Color("#3a1f24")
const C_SHOPWALL := Color("#2a1442")
const C_SHOPWALL_LINE := Color("#22103a")
const C_ALLEY := Color("#0b0b15")
const C_SIDEWALK := Color("#33374a")
const C_SIDEWALK_LINE := Color("#2b2f40")
const C_ROAD := Color("#222437")
const C_ROAD_LINE := Color("#6c6c86")
const C_RAIL := Color("#70748c")
const C_WATER := Color("#0c172a")
const C_WATER_HI := Color("#173050")
const C_NEON_PINK := Color("#ff5ad0")
const C_NEON_CYAN := Color("#45e0ff")
const C_NEON_PURPLE := Color("#b48aff")
const C_OUTLINE := Color("#0a0a14")
const C_SHADOW := Color(0, 0, 0, 0.35)

const SOLID_TILES := "#wWTbghkpaFCDnd"
const WALKABLE_OVERRIDE := "de"   # d=開いているドア e=出口マット


static func is_solid_char(ch: String) -> bool:
	if WALKABLE_OVERRIDE.contains(ch):
		return false
	return SOLID_TILES.contains(ch)


static func hash2(x: int, y: int) -> int:
	var h := (x * 374761393 + y * 668265263) & 0x7fffffff
	h = ((h ^ (h >> 13)) * 1274126177) & 0x7fffffff
	return h


static func px(ci: CanvasItem, x: float, y: float, w: float, h: float, c: Color) -> void:
	ci.draw_rect(Rect2(x, y, w, h), c)


# =========================================================== tiles
static func draw_tile(ci: CanvasItem, ch: String, tx: int, ty: int, grid: PackedStringArray, floor_ch: String = ".") -> void:
	var x := tx * TILE
	var y := ty * TILE
	var h := hash2(tx, ty)
	match ch:
		"#":
			px(ci, x, y, TILE, TILE, C_WALL_TOP)
			if h % 7 == 0:
				px(ci, x + 3, y + 5, 2, 1, C_WALL_FACE2)
		"w", "W":
			_wall_face(ci, x, y, tx, ty, grid, ch == "W")
		".":
			var c := C_WOOD_A if (ty % 2 == 0) else C_WOOD_B
			px(ci, x, y, TILE, TILE, c)
			px(ci, x, y + 15, TILE, 1, C_WOOD_LINE)
			var off := (ty * 7) % 16
			px(ci, x + off, y, 1, 15, C_WOOD_LINE)
		"_":
			var cc := C_KITCHEN_A if ((tx + ty) % 2 == 0) else C_KITCHEN_B
			px(ci, x, y, TILE, TILE, cc)
		",":
			var sc := C_SHOP_A if ((tx + ty) % 2 == 0) else C_SHOP_B
			px(ci, x, y, TILE, TILE, sc)
			if h % 5 == 0:
				px(ci, x + 7, y + 7, 2, 2, Color(0.7, 0.4, 1.0, 0.08))
		"e":
			draw_tile(ci, floor_ch, tx, ty, grid, floor_ch)
			px(ci, x + 1, y + 2, 14, 12, Color("#3c2a2a"))
			px(ci, x + 2, y + 3, 12, 10, Color("#553838"))
		"T":
			px(ci, x, y, TILE, TILE, C_ROOF)
			px(ci, x, y + (tx % 2) * 8 + 3, TILE, 1, C_ROOF_LINE)
			if h % 23 == 0:
				# 室外機・アンテナ
				px(ci, x + 3, y + 4, 9, 7, Color("#2a2c40"))
				px(ci, x + 4, y + 5, 7, 5, Color("#33364c"))
			elif h % 31 == 0:
				px(ci, x + 7, y + 1, 1, 12, Color("#3a3c52"))
				px(ci, x + 4, y + 3, 7, 1, Color("#3a3c52"))
		"b", "g":
			px(ci, x, y, TILE, TILE, C_FACADE)
			px(ci, x, y + 15, TILE, 1, C_FACADE_LINE)
			if ch == "g":
				var lit := C_WIN_WARM if h % 3 != 0 else C_WIN_COOL
				px(ci, x + 3, y + 3, 10, 9, C_OUTLINE)
				px(ci, x + 4, y + 4, 8, 7, lit.darkened(0.15))
				px(ci, x + 4, y + 4, 8, 2, lit)
				px(ci, x + 7, y + 4, 1, 7, C_OUTLINE)
			elif ty == 2 or h % 4 == 0:
				px(ci, x + 3, y + 3, 10, 9, C_OUTLINE)
				px(ci, x + 4, y + 4, 8, 7, C_WIN_DARK)
		"h":
			px(ci, x, y, TILE, TILE, C_METAL)
			for i in range(0, TILE, 3):
				px(ci, x + i, y, 1, TILE, C_METAL_LINE)
		"D":
			px(ci, x, y, TILE, TILE, C_SHUTTER)
			for j in range(1, TILE, 3):
				px(ci, x, y + j, TILE, 1, C_METAL_LINE)
		"k":
			px(ci, x, y, TILE, TILE, C_BRICK)
			for j in range(0, TILE, 4):
				px(ci, x, y + j, TILE, 1, C_BRICK_LINE)
				px(ci, x + (int(j / 4.0) % 2) * 8, y + j, 1, 4, C_BRICK_LINE)
		"n":
			px(ci, x, y, TILE, TILE, C_BRICK)
			px(ci, x, y, TILE, 9, Color("#b02a32"))
			px(ci, x + 7, y, 2, 9, Color("#7a1a20"))
			px(ci, x + 2, y + 9, 12, 7, Color("#1a0f12"))
		"p":
			px(ci, x, y, TILE, TILE, C_SHOPWALL)
			px(ci, x, y + 15, TILE, 1, C_SHOPWALL_LINE)
			if ty == 3 and h % 3 == 0:
				px(ci, x + 3, y + 3, 10, 10, Color("#1a0a2a"))
				px(ci, x + 4, y + 4, 8, 8, Color(1.0, 0.35, 0.82, 0.25))
		"d":
			px(ci, x, y, TILE, TILE, C_OUTLINE)
			if grid[ty].substr(maxi(tx - 1, 0), 3).contains("p"):
				px(ci, x + 1, y + 1, 14, 15, Color("#2a1440"))
				px(ci, x + 2, y + 2, 12, 14, Color(1.0, 0.35, 0.82, 0.35))
				px(ci, x + 1, y + 1, 14, 1, C_NEON_PINK)
			else:
				px(ci, x + 2, y + 1, 12, 15, Color("#3a3248"))
				px(ci, x + 11, y + 8, 2, 2, Color("#c8b070"))
		"a":
			px(ci, x, y, TILE, TILE, C_ALLEY)
			if h % 5 == 0:
				px(ci, x + 4, y + 10, 6, 6, Color("#15151f"))
		"S":
			px(ci, x, y, TILE, TILE, C_SIDEWALK)
			px(ci, x, y + 15, TILE, 1, C_SIDEWALK_LINE)
			px(ci, x + 15, y, 1, TILE, C_SIDEWALK_LINE)
			if ty == 4:
				px(ci, x, y, TILE, 2, Color("#24273a"))
		"R":
			px(ci, x, y, TILE, TILE, C_ROAD)
			if ty == 7 and tx % 3 != 0:
				px(ci, x, y + 7, TILE, 2, C_ROAD_LINE.darkened(0.3))
			if ty == 6:
				px(ci, x, y, TILE, 1, Color("#4a4e64"))
			if ty == 8:
				px(ci, x, y + 15, TILE, 1, Color("#4a4e64"))
			if h % 9 == 0:
				# 水たまり (ネオンの反射)
				var refl := C_NEON_PINK if h % 2 == 0 else C_NEON_CYAN
				px(ci, x + 2, y + 6, 11, 4, Color("#181a2c"))
				px(ci, x + 4, y + 7, 6, 1, Color(refl, 0.45))
				px(ci, x + 6, y + 8, 4, 1, Color(refl, 0.25))
		"F":
			px(ci, x, y, TILE, TILE, C_SIDEWALK)
			px(ci, x, y + 4, TILE, 2, C_RAIL)
			px(ci, x, y + 10, TILE, 1, C_RAIL.darkened(0.3))
			px(ci, x + 2, y + 4, 2, 10, C_RAIL.darkened(0.15))
			px(ci, x + 10, y + 4, 2, 10, C_RAIL.darkened(0.15))
			px(ci, x, y + 14, TILE, 2, Color("#1c2034"))
		"C":
			px(ci, x, y, TILE, TILE, C_WATER)
			if h % 4 == 0:
				px(ci, x + (h % 9), y + (h % 11) + 2, 5, 1, C_WATER_HI)
			if ty == 11:
				px(ci, x, y, TILE, 2, Color("#060b16"))
		_:
			px(ci, x, y, TILE, TILE, C_VOID)


static func _wall_face(ci: CanvasItem, x: int, y: int, tx: int, ty: int, grid: PackedStringArray, window: bool) -> void:
	var upper := ty > 0 and (grid[ty - 1][tx] == "w" or grid[ty - 1][tx] == "W")
	px(ci, x, y, TILE, TILE, C_WALL_FACE)
	px(ci, x + (tx % 2) * 8, y, 1, TILE, C_WALL_FACE2)
	if upper:
		px(ci, x, y + 9, TILE, 7, C_WAINSCOT)
		px(ci, x, y + 9, TILE, 1, Color("#3a3868"))
	if window:
		px(ci, x + 1, y + 2, 14, 12, C_OUTLINE)
		px(ci, x + 2, y + 3, 12, 10, Color("#101a30"))
		# 窓越しのネオン
		px(ci, x + 3, y + 9, 3, 4, Color(C_NEON_PINK, 0.5))
		px(ci, x + 9, y + 6, 2, 7, Color(C_NEON_CYAN, 0.35))
		px(ci, x + 7, y + 3, 1, 10, C_OUTLINE)


## 区画アイコン (図形)。文字が読めなくても判別できる情報。
static func draw_shape(ci: CanvasItem, shape: String, c: Vector2, r: float, col: Color) -> void:
	match shape:
		"triangle":
			ci.draw_colored_polygon(PackedVector2Array([c + Vector2(0, -r), c + Vector2(r, r * 0.8), c + Vector2(-r, r * 0.8)]), col)
		"circle":
			ci.draw_circle(c, r, col)
		"diamond":
			ci.draw_colored_polygon(PackedVector2Array([c + Vector2(0, -r), c + Vector2(r, 0), c + Vector2(0, r), c + Vector2(-r, 0)]), col)
		"square":
			ci.draw_rect(Rect2(c - Vector2(r, r) * 0.85, Vector2(r, r) * 1.7), col)
		"star":
			var pts := PackedVector2Array()
			for i in 10:
				var rr := r if i % 2 == 0 else r * 0.45
				var a := -PI / 2.0 + i * PI / 5.0
				pts.append(c + Vector2(cos(a), sin(a)) * rr)
			ci.draw_colored_polygon(pts, col)
		"cross":
			ci.draw_rect(Rect2(c.x - r * 0.3, c.y - r, r * 0.6, r * 2.0), col)
			ci.draw_rect(Rect2(c.x - r, c.y - r * 0.3, r * 2.0, r * 0.6), col)
		_:
			ci.draw_circle(c, r * 0.5, col)


## 同心円を重ねて、中心ほど明るい光を描く
static func glow(ci: CanvasItem, c: Vector2, radius: float, col: Color, alpha: float) -> void:
	for i in 4:
		var k := 1.0 - float(i) * 0.25
		ci.draw_circle(c, radius * k, Color(col, alpha))


# =========================================================== characters
static func pal_from(data: Dictionary) -> Dictionary:
	return {
		"skin": Color(str(data.get("skin", "#e8c4a8"))),
		"hair": Color(str(data.get("hair", "#202030"))),
		"coat": Color(str(data.get("coat", "#34466e"))),
		"pants": Color(str(data.get("pants", "#1e2236"))),
		"accent": Color(str(data.get("accent", "#7ad0ff"))),
		"style": str(data.get("style", "short")),
		"glasses": bool(data.get("glasses", false)),
	}


## 足元を原点 (0,0) とした 12x20 のキャラクター。step=歩行フレーム(0-3)。
static func draw_person(ci: CanvasItem, pal: Dictionary, facing: String, step: int, umbrella: bool = false) -> void:
	var skin: Color = pal["skin"]
	var hair: Color = pal["hair"]
	var coat: Color = pal["coat"]
	var pants: Color = pal["pants"]
	var accent: Color = pal["accent"]
	var style: String = pal["style"]
	var bob := 1 if (step == 1 or step == 3) else 0
	# shadow
	px(ci, -5, -1, 10, 2, C_SHADOW)
	# legs
	var l_up := 1 if step == 1 else 0
	var r_up := 1 if step == 3 else 0
	px(ci, -4, -6, 3, 5 - l_up, pants)
	px(ci, 1, -6, 3, 5 - r_up, pants)
	px(ci, -4, -2 - l_up, 3, 1, C_OUTLINE)
	px(ci, 1, -2 - r_up, 3, 1, C_OUTLINE)
	var by := -bob
	# body
	px(ci, -5, -13 + by, 10, 8, coat)
	px(ci, -5, -13 + by, 10, 1, coat.lightened(0.15))
	px(ci, -1, -12 + by, 1, 6, coat.darkened(0.25))
	# arms
	var arm_swing := 0
	if step == 1:
		arm_swing = 1
	elif step == 3:
		arm_swing = -1
	if facing == "left" or facing == "right":
		var ax := -1 if facing == "left" else 0
		px(ci, ax, -12 + by + arm_swing, 2, 6, coat.darkened(0.2))
		px(ci, ax, -6 + by + arm_swing, 2, 1, skin)
	else:
		px(ci, -6, -12 + by + arm_swing, 1, 6, coat.darkened(0.2))
		px(ci, 5, -12 + by - arm_swing, 1, 6, coat.darkened(0.2))
		px(ci, -6, -6 + by + arm_swing, 1, 1, skin)
		px(ci, 5, -6 + by - arm_swing, 1, 1, skin)
	# head
	var hy := -20 + by
	px(ci, -4, hy, 8, 7, skin)
	match style:
		"hood":
			px(ci, -5, hy - 1, 10, 3, coat.darkened(0.1))
			px(ci, -5, hy, 1, 8, coat.darkened(0.1))
			px(ci, 4, hy, 1, 8, coat.darkened(0.1))
			px(ci, -3, hy + 2, 6, 1, hair)
		"bun":
			px(ci, -4, hy, 8, 2, hair)
			px(ci, -4, hy, 1, 4, hair)
			px(ci, 3, hy, 1, 4, hair)
			px(ci, -1, hy - 2, 3, 2, hair)
		"headband":
			px(ci, -4, hy, 8, 2, hair)
			px(ci, -4, hy + 2, 8, 1, accent)
		"slick":
			px(ci, -4, hy, 8, 2, hair)
			px(ci, -4, hy, 2, 3, hair)
		_:
			px(ci, -4, hy - 1, 8, 3, hair)
			px(ci, -4, hy, 1, 4, hair)
			px(ci, 3, hy, 1, 4, hair)
	# face by facing
	match facing:
		"up":
			if style == "hood":
				px(ci, -4, hy, 8, 7, coat.darkened(0.1))
			else:
				px(ci, -4, hy, 8, 6, hair)
		"left":
			px(ci, -3, hy + 3, 1, 1, C_OUTLINE)
			if style != "hood":
				px(ci, 1, hy, 3, 5, hair)
			if pal["glasses"]:
				px(ci, -4, hy + 3, 3, 1, accent)
		"right":
			px(ci, 2, hy + 3, 1, 1, C_OUTLINE)
			if style != "hood":
				px(ci, -4, hy, 3, 5, hair)
			if pal["glasses"]:
				px(ci, 1, hy + 3, 3, 1, accent)
		_:
			px(ci, -2, hy + 3, 1, 2, C_OUTLINE)
			px(ci, 1, hy + 3, 1, 2, C_OUTLINE)
			if pal["glasses"]:
				px(ci, -3, hy + 3, 3, 1, accent)
				px(ci, 0, hy + 3, 3, 1, accent)
	if umbrella:
		draw_umbrella(ci, accent, hy)


static func draw_umbrella(ci: CanvasItem, col: Color, hy: int) -> void:
	var c := Color(col, 0.55)
	px(ci, -9, hy - 7, 18, 3, c)
	px(ci, -7, hy - 9, 14, 2, c)
	px(ci, -3, hy - 10, 6, 1, c)
	px(ci, 0, hy - 6, 1, 6, Color("#9a9aae"))


# =========================================================== portraits (32x32)
static func draw_portrait(ci: CanvasItem, origin: Vector2, s: float, pal: Dictionary, expr: String) -> void:
	var o := origin
	var skin: Color = pal["skin"]
	var hair: Color = pal["hair"]
	var coat: Color = pal["coat"]
	var accent: Color = pal["accent"]
	var style: String = pal["style"]
	if expr == "blank":
		skin = skin.lerp(Color("#b0b0c0"), 0.35)
	var P := func(x: float, y: float, w: float, h: float, c: Color) -> void:
		ci.draw_rect(Rect2(o.x + x * s, o.y + y * s, w * s, h * s), c)
	# background glow
	P.call(0, 0, 32, 32, Color("#141228"))
	P.call(0, 26, 32, 6, Color("#100e20"))
	# shoulders
	P.call(4, 25, 24, 7, coat)
	P.call(4, 25, 24, 1, coat.lightened(0.15))
	P.call(15, 25, 2, 7, coat.darkened(0.3))
	# neck
	P.call(13, 21, 6, 4, skin.darkened(0.12))
	# head
	P.call(9, 6, 14, 16, skin)
	P.call(8, 8, 1, 11, skin)
	P.call(23, 8, 1, 11, skin)
	P.call(10, 21, 12, 1, skin.darkened(0.1))
	# hair
	match style:
		"hood":
			P.call(6, 3, 20, 5, coat.darkened(0.15))
			P.call(5, 6, 4, 19, coat.darkened(0.15))
			P.call(23, 6, 4, 19, coat.darkened(0.15))
			P.call(9, 7, 14, 3, hair)
			P.call(9, 10, 3, 6, hair)
			P.call(20, 10, 3, 5, hair)
		"bun":
			P.call(8, 4, 16, 6, hair)
			P.call(7, 7, 3, 9, hair)
			P.call(22, 7, 3, 9, hair)
			P.call(13, 1, 6, 4, hair)
			P.call(11, 9, 10, 1, hair.darkened(0.2))
		"headband":
			P.call(8, 4, 16, 5, hair)
			P.call(7, 6, 2, 8, hair)
			P.call(23, 6, 2, 8, hair)
			P.call(8, 8, 16, 2, accent)
			P.call(22, 7, 4, 2, accent)
		"slick":
			P.call(8, 4, 16, 5, hair)
			P.call(7, 5, 3, 10, hair)
			P.call(22, 5, 3, 8, hair)
			P.call(12, 8, 8, 1, hair.lightened(0.1))
		_:
			P.call(8, 4, 16, 6, hair)
			P.call(7, 6, 3, 10, hair)
			P.call(22, 6, 3, 10, hair)
			P.call(12, 9, 3, 2, hair)
			P.call(18, 9, 2, 2, hair)
	# brows / eyes / mouth by expression
	var eye := C_OUTLINE
	match expr:
		"smile":
			P.call(11, 14, 3, 1, eye)
			P.call(18, 14, 3, 1, eye)
			P.call(10, 13, 1, 1, eye)
			P.call(21, 13, 1, 1, eye)
			P.call(14, 18, 4, 1, skin.darkened(0.45))
			P.call(13, 17, 1, 1, skin.darkened(0.45))
			P.call(18, 17, 1, 1, skin.darkened(0.45))
			P.call(10, 16, 2, 1, Color(1, 0.4, 0.5, 0.35))
			P.call(20, 16, 2, 1, Color(1, 0.4, 0.5, 0.35))
		"sad":
			P.call(10, 11, 2, 1, hair.darkened(0.2))
			P.call(12, 10, 1, 1, hair.darkened(0.2))
			P.call(20, 11, 2, 1, hair.darkened(0.2))
			P.call(19, 10, 1, 1, hair.darkened(0.2))
			P.call(11, 14, 2, 2, eye)
			P.call(19, 14, 2, 2, eye)
			P.call(14, 19, 4, 1, skin.darkened(0.45))
			P.call(13, 20, 1, 1, skin.darkened(0.45))
			P.call(18, 20, 1, 1, skin.darkened(0.45))
		"surprised":
			P.call(10, 11, 3, 1, hair.darkened(0.2))
			P.call(19, 11, 3, 1, hair.darkened(0.2))
			P.call(11, 13, 2, 3, eye)
			P.call(19, 13, 2, 3, eye)
			P.call(11, 13, 1, 1, Color.WHITE)
			P.call(19, 13, 1, 1, Color.WHITE)
			P.call(15, 18, 2, 2, skin.darkened(0.5))
		"blank":
			P.call(11, 14, 2, 1, Color("#4a4a5a"))
			P.call(19, 14, 2, 1, Color("#4a4a5a"))
			P.call(14, 19, 4, 1, skin.darkened(0.3))
		_:
			P.call(11, 13, 2, 2, eye)
			P.call(19, 13, 2, 2, eye)
			P.call(11, 13, 1, 1, Color(1, 1, 1, 0.8))
			P.call(19, 13, 1, 1, Color(1, 1, 1, 0.8))
			P.call(14, 18, 4, 1, skin.darkened(0.4))
	if pal["glasses"]:
		P.call(9, 12, 6, 1, accent)
		P.call(17, 12, 6, 1, accent)
		P.call(9, 12, 1, 4, accent)
		P.call(14, 12, 1, 4, accent)
		P.call(17, 12, 1, 4, accent)
		P.call(22, 12, 1, 4, accent)
		P.call(9, 15, 6, 1, Color(accent, 0.5))
		P.call(17, 15, 6, 1, Color(accent, 0.5))
		P.call(10, 13, 4, 2, Color(accent, 0.18))
		P.call(18, 13, 4, 2, Color(accent, 0.18))
	# nose
	P.call(16, 16, 1, 1, skin.darkened(0.2))


## ATM の画面
static func draw_atm_portrait(ci: CanvasItem, origin: Vector2, s: float, t: float) -> void:
	var o := origin
	var P := func(x: float, y: float, w: float, h: float, c: Color) -> void:
		ci.draw_rect(Rect2(o.x + x * s, o.y + y * s, w * s, h * s), c)
	P.call(0, 0, 32, 32, Color("#0e1a28"))
	P.call(3, 3, 26, 17, Color("#1a3a5a"))
	P.call(5, 5, 22, 3, Color(0.4, 0.85, 1.0, 0.8))
	P.call(5, 10, 14, 2, Color(0.7, 0.9, 1.0, 0.6))
	P.call(5, 14, 10, 2, Color(0.7, 0.9, 1.0, 0.6 if int(t * 2.0) % 2 == 0 else 0.2))
	for i in 3:
		for j in 3:
			P.call(5 + i * 5, 22 + j * 3, 4, 2, Color("#3a4a5a"))
	P.call(22, 23, 6, 7, Color("#2a3a4a"))


## 電話の向こうの相手 (顔が見えない)。noise=true で砂嵐。
static func draw_phone_portrait(ci: CanvasItem, origin: Vector2, s: float, t: float, noise: bool) -> void:
	var o := origin
	var P := func(x: float, y: float, w: float, h: float, c: Color) -> void:
		ci.draw_rect(Rect2(o.x + x * s, o.y + y * s, w * s, h * s), c)
	P.call(0, 0, 32, 32, Color("#141228"))
	P.call(10, 4, 12, 24, C_OUTLINE)
	P.call(11, 5, 10, 22, Color("#1c2440"))
	P.call(14, 25, 4, 1, Color("#4a5070"))
	if noise:
		var seed := int(t * 20.0)
		for yy in range(6, 24):
			for xx in range(12, 20):
				var v := hash2(xx + seed * 31, yy + seed * 17) % 100
				if v < 45:
					P.call(xx, yy, 1, 1, Color(0.6, 0.6, 0.75, float(v) / 70.0))
		P.call(12, 12, 8, 2, Color(C_NEON_PINK, 0.5))
	else:
		P.call(12, 9, 8, 6, Color("#2a3a64"))
		P.call(15, 10, 2, 2, Color("#9ab0e0"))
		P.call(14, 12, 4, 2, Color("#9ab0e0"))
		var wave := int(t * 3.0) % 3
		for i in range(wave + 1):
			P.call(23 + i * 2, 12 - i, 1, 2 + i * 2, Color(C_NEON_CYAN, 0.8))
			P.call(8 - i * 2, 12 - i, 1, 2 + i * 2, Color(C_NEON_CYAN, 0.8))
		P.call(12, 18, 8, 1, Color("#6a80b0"))
		P.call(13, 20, 6, 1, Color("#4a5a80"))


# =========================================================== props
## rect はピクセル単位 (ノード原点からの相対)。state でアニメーション等を受け取る。
static func draw_prop(ci: CanvasItem, sprite: String, r: Rect2, t: float, state: Dictionary) -> void:
	var x := r.position.x
	var y := r.position.y
	var w := r.size.x
	var h := r.size.y
	match sprite:
		"bed":
			px(ci, x, y + 2, w, h - 2, Color("#1e1a30"))
			px(ci, x + 1, y + 1, w - 2, h - 3, Color("#3a4a7a"))
			px(ci, x + 3, y + 3, w - 6, 8, Color("#d8d8e8"))
			px(ci, x + 1, y + 14, w - 2, h - 16, Color("#2c3a66"))
			px(ci, x + 1, y + 14, w - 2, 2, Color("#4a5c94"))
			px(ci, x, y + h - 2, w, 2, C_OUTLINE)
		"desk":
			px(ci, x, y, w, h - 3, Color("#5a4048"))
			px(ci, x, y, w, 2, Color("#6e5058"))
			px(ci, x + 1, y + h - 3, 2, 3, Color("#3a2830"))
			px(ci, x + w - 3, y + h - 3, 2, 3, Color("#3a2830"))
			px(ci, x + 17, y + 6, 14, 5, Color("#4a3038"))
			px(ci, x + 23, y + 8, 2, 1, Color("#c8b070"))
			# デスクライト
			px(ci, x + 40, y - 8, 2, 10, Color("#6a6a80"))
			px(ci, x + 36, y - 10, 8, 3, Color("#8a8aa0"))
			ci.draw_circle(Vector2(x + 40, y + 2), 9, Color(1, 0.85, 0.5, 0.08))
		"letter":
			var hi := 0.5 + 0.5 * sin(t * 4.0)
			px(ci, x + 3, y + 3, 11, 8, Color("#e8e4d8"))
			px(ci, x + 3, y + 3, 11, 1, Color("#c8c4b8"))
			px(ci, x + 5, y + 6, 7, 2, Color("#d03040"))
			if state.get("new", false):
				px(ci, x + 13, y - 1, 2, 2, Color(1, 0.9, 0.3, hi))
		"memo":
			px(ci, x + 4, y + 2, 9, 10, Color("#f0e890"))
			px(ci, x + 5, y + 4, 6, 1, Color("#606070"))
			px(ci, x + 5, y + 6, 5, 1, Color("#606070"))
			px(ci, x + 5, y + 8, 6, 1, Color("#606070"))
			if state.get("new", false):
				px(ci, x + 12, y, 2, 2, Color(1, 0.9, 0.3, 0.5 + 0.5 * sin(t * 4.0)))
		"photo":
			px(ci, x + 2, y + 2, 12, 11, Color("#8a7050"))
			px(ci, x + 3, y + 3, 10, 9, Color("#c8d0e0"))
			px(ci, x + 4, y + 7, 3, 5, Color("#506080"))
			if state.get("lost", false):
				var n := int(t * 12.0) % 3
				px(ci, x + 8 + n % 2, y + 4, 3, 8, Color("#606070"))
				px(ci, x + 8, y + 4 + n, 4, 2, Color(C_NEON_PINK, 0.6))
			else:
				px(ci, x + 8, y + 4, 3, 8, Color("#a05070"))
				px(ci, x + 8, y + 4, 3, 2, Color("#e0b8a0"))
		"lowtable":
			px(ci, x, y + 2, w, h - 4, Color("#4a3a44"))
			px(ci, x, y + 2, w, 2, Color("#5c4a54"))
			px(ci, x + 1, y + h - 2, 2, 2, Color("#2a2028"))
			px(ci, x + w - 3, y + h - 2, 2, 2, Color("#2a2028"))
			px(ci, x + 18, y + 4, 8, 6, Color("#5a7a9a"))
		"phone":
			var ringing: bool = state.get("ringing", false)
			var jx := 0.0
			if ringing:
				jx = 1.0 if int(t * 30.0) % 2 == 0 else -1.0
			px(ci, x + 5 + jx, y + 3, 6, 9, C_OUTLINE)
			var scr := Color("#3a4a7a")
			if ringing:
				scr = Color("#7ad0ff") if int(t * 4.0) % 2 == 0 else Color("#ff5ad0")
			px(ci, x + 6 + jx, y + 4, 4, 6, scr)
			if ringing:
				var a := 0.5 + 0.5 * sin(t * 10.0)
				ci.draw_circle(Vector2(x + 8, y + 7), 10.0, Color(0.45, 0.85, 1.0, 0.12 * a))
				px(ci, x + 13, y - 2, 1, 3, Color(1, 1, 1, a))
				px(ci, x + 14, y - 3, 2, 1, Color(1, 1, 1, a))
				px(ci, x + 2, y - 1, 1, 3, Color(1, 1, 1, 1.0 - a))
		"kitchen":
			px(ci, x, y, w, h, Color("#5a6070"))
			px(ci, x, y, w, 3, Color("#7a8090"))
			px(ci, x + 6, y + 4, 18, 9, Color("#3a4050"))
			px(ci, x + 8, y + 5, 14, 7, Color("#2a3040"))
			px(ci, x + 12, y + 6, 4, 4, Color("#e8e8f0"))
			px(ci, x + 17, y + 7, 4, 4, Color("#d0c0e0"))
			px(ci, x + 38, y + 4, 8, 8, Color("#2a2a30"))
			px(ci, x + 40, y + 6, 4, 4, Color("#aa3020"))
		"fridge":
			px(ci, x, y - 10, w, h + 10, Color("#c8ccd8"))
			px(ci, x, y - 10, w, 1, Color("#e8ecf0"))
			px(ci, x, y + 4, w, 1, Color("#8a8e9a"))
			px(ci, x + w - 3, y - 6, 1, 6, Color("#6a6e7a"))
			px(ci, x + 3, y - 4, 4, 4, Color("#f0e890"))
		"rug":
			px(ci, x + 2, y + 2, w - 4, h - 4, Color("#3a2a52"))
			px(ci, x + 4, y + 4, w - 8, h - 8, Color("#45325e"))
			px(ci, x + 4, y + 4, w - 8, 1, Color("#6a4a8a"))
			px(ci, x + 4, y + h - 5, w - 8, 1, Color("#6a4a8a"))
		"plant":
			px(ci, x + 4, y + 9, 8, 7, Color("#6a4030"))
			px(ci, x + 3, y + 9, 10, 2, Color("#7a5040"))
			px(ci, x + 2, y + 1, 5, 8, Color("#3a5a3a"))
			px(ci, x + 8, y - 2, 5, 11, Color("#2e4a30"))
			px(ci, x + 6, y + 3, 3, 6, Color("#4a6a3a"))
		"plate":
			px(ci, x + 2, y + 4, 12, 7, Color("#6a6e86"))
			px(ci, x + 3, y + 5, 10, 5, Color("#cfd4e0"))
			px(ci, x + 4, y + 7, 8, 1, Color("#404458"))
		"guide":
			px(ci, x + 7, y + 4, 2, 12, Color("#5a5e74"))
			px(ci, x, y - 6, 16, 11, Color("#1e3a5a"))
			px(ci, x + 1, y - 5, 14, 9, Color("#2a5080"))
			px(ci, x + 2, y - 3, 4, 1, Color.WHITE)
			px(ci, x + 10, y - 3, 4, 1, Color.WHITE)
			px(ci, x + 2, y, 12, 1, Color(1, 1, 1, 0.6))
		"lamp":
			px(ci, x + 7, y - 26, 2, 40, Color("#4a4e64"))
			px(ci, x + 4, y + 12, 8, 3, Color("#3a3e52"))
			px(ci, x + 3, y - 28, 10, 3, Color("#5a5e74"))
			var fl := 1.0 if (int(t * 7.0 + x) % 23) != 0 else 0.4
			px(ci, x + 4, y - 25, 8, 2, Color(0.75, 0.95, 1.0, fl))
			glow(ci, Vector2(x + 8, y - 22), 16.0, Color(0.45, 0.8, 1.0), 0.05 * fl)
			glow(ci, Vector2(x + 8, y + 12), 12.0, Color(0.45, 0.8, 1.0), 0.04 * fl)
		"vending":
			px(ci, x, y - 14, w, h + 14, Color("#d03a4a"))
			px(ci, x + 2, y - 12, w - 4, 12, Color("#20283a"))
			for i in range(4):
				var cc: Color = [Color("#e8c050"), Color("#50a0e8"), Color("#e86050"), Color("#70d080")][i]
				px(ci, x + 4 + i * 6, y - 10, 4, 4, cc)
				px(ci, x + 4 + i * 6, y - 5, 4, 3, Color(cc, 0.6))
			px(ci, x + 2, y + 2, w - 4, 4, Color("#20283a"))
			px(ci, x + w - 6, y - 14, 4, 2, Color(1, 1, 1, 0.5 + 0.3 * sin(t * 3.0)))
			ci.draw_circle(Vector2(x + w / 2, y), 18.0, Color(1, 0.4, 0.4, 0.06))
		"yatai":
			px(ci, x, y + 2, w, h - 2, Color("#5a3428"))
			px(ci, x, y + 2, w, 3, Color("#7a4a38"))
			px(ci, x + 2, y + 8, w - 4, 1, Color("#3a2018"))
			# 屋根と提灯
			px(ci, x - 2, y - 26, w + 4, 4, Color("#3a2018"))
			px(ci, x, y - 22, 2, 24, Color("#3a2018"))
			px(ci, x + w - 2, y - 22, 2, 24, Color("#3a2018"))
			var glow := 0.75 + 0.25 * sin(t * 2.3)
			px(ci, x + 6, y - 21, 6, 8, Color(1.0, 0.35, 0.25, glow))
			px(ci, x + w - 12, y - 21, 6, 8, Color(1.0, 0.35, 0.25, glow))
			ci.draw_circle(Vector2(x + w / 2, y - 12), 26.0, Color(1, 0.5, 0.3, 0.08 * glow))
			# 湯気
			for i in range(3):
				var sy := fmod(t * 8.0 + i * 5.0, 14.0)
				px(ci, x + 20 + i * 6 + sin(t * 2.0 + i) * 2.0, y - sy, 2, 2, Color(1, 1, 1, 0.25 * (1.0 - sy / 14.0)))
		"poster":
			px(ci, x + 1, y + 1, 14, 14, Color("#e8e0f0"))
			px(ci, x + 2, y + 2, 12, 6, Color("#ff5ad0"))
			px(ci, x + 4, y + 4, 8, 2, Color("#ffffff"))
			px(ci, x + 3, y + 10, 10, 1, Color("#404058"))
			px(ci, x + 3, y + 12, 7, 1, Color("#404058"))
		"counter":
			px(ci, x, y, w, h, Color("#20142e"))
			px(ci, x, y, w, 3, Color("#3a2650"))
			px(ci, x, y + 3, w, 1, C_NEON_CYAN.darkened(0.3))
			px(ci, x + 14, y - 2, 10, 4, Color("#101018"))
			px(ci, x + 15, y - 1, 8, 2, Color(C_NEON_CYAN, 0.5 + 0.2 * sin(t * 5.0)))
			px(ci, x + 90, y - 3, 6, 5, Color("#d0d0e0"))
		"jars":
			px(ci, x, y - 6, w, h + 6, Color("#2a1a3a"))
			for i in range(int(h / 8.0) + 1):
				var jy := y - 4 + i * 9
				var hue := fmod(0.75 + i * 0.13 + x * 0.01, 1.0)
				var a := 0.45 + 0.35 * sin(t * 1.7 + i + x)
				px(ci, x + 4, jy, 8, 7, Color("#1a1028"))
				px(ci, x + 5, jy + 2, 6, 5, Color.from_hsv(hue, 0.6, 1.0, a))
				px(ci, x + 5, jy, 6, 1, Color("#8a8aa0"))
		"jarwall":
			for i in range(int(w / 16.0)):
				for j in range(2):
					var jx := x + i * 16 + 3
					var jy2 := y + j * 14 + 2
					var hue2 := fmod(0.7 + (i * 7 + j * 3) * 0.031, 1.0)
					var a2 := 0.35 + 0.3 * sin(t * 1.3 + i * 0.7 + j)
					px(ci, jx, jy2, 10, 10, Color("#1a1028"))
					px(ci, jx + 1, jy2 + 3, 8, 6, Color.from_hsv(hue2, 0.55, 1.0, a2))
					px(ci, jx + 2, jy2 + 1, 6, 1, Color("#7a7a90"))
				px(ci, x + i * 16, y + 13, 16, 1, Color("#3a2a50"))
				px(ci, x + i * 16, y + 27, 16, 1, Color("#3a2a50"))
		"photo_b":
			px(ci, x + 2, y + 2, 12, 11, Color("#3a3a4a"))
			px(ci, x + 3, y + 3, 10, 9, Color("#4a5a7a"))
			px(ci, x + 3, y + 9, 10, 3, Color("#2a3048"))
			px(ci, x + 4, y + 4, 8, 2, Color("#8090b0"))
			px(ci, x + 5, y + 7, 2, 4, Color("#34466e"))
			if not state.get("lost", false):
				px(ci, x + 9, y + 7, 2, 4, Color("#6a4a8a"))
			else:
				px(ci, x + 9, y + 7, 2, 4, Color(0.6, 0.6, 0.7, 0.3 + 0.2 * sin(t * 6.0)))
		"atm":
			px(ci, x + 1, y + 1, 14, 15, Color("#1a2a3a"))
			px(ci, x + 2, y + 2, 12, 6, Color(0.35, 0.8, 1.0, 0.6 + 0.2 * sin(t * 2.0)))
			px(ci, x + 3, y + 3, 6, 1, Color.WHITE)
			px(ci, x + 3, y + 10, 10, 3, Color("#2a3a4a"))
			px(ci, x + 4, y + 11, 2, 1, Color("#8aa0b8"))
			px(ci, x + 7, y + 11, 2, 1, Color("#8aa0b8"))
			px(ci, x + 10, y + 11, 2, 1, Color("#8aa0b8"))
			glow(ci, Vector2(x + 8, y + 6), 14.0, Color(0.35, 0.8, 1.0), 0.04)
		"rack":
			px(ci, x, y - 14, w, h + 14, Color("#2a2c38"))
			for j in range(0, int(h) + 14, 14):
				px(ci, x, y - 14 + j, w, 2, Color("#5a5e70"))
				for i in range(2, int(w) - 8, 11):
					var bc := Color("#a07848") if hash2(int(x) + i, j) % 3 != 0 else Color("#8a6a40")
					px(ci, x + i, y - 14 + j + 4, 9, 9, bc)
			px(ci, x, y - 14, 2, h + 14, Color("#6a6e80"))
			px(ci, x + w - 2, y - 14, 2, h + 14, Color("#6a6e80"))
		"conveyor":
			px(ci, x, y + 2, w, h - 4, Color("#30323e"))
			var off2 := int(t * 20.0) % 8
			for i in range(-8, int(w), 8):
				px(ci, x + maxf(0, i + off2), y + 4, 2, h - 8, Color("#3e4050"))
			px(ci, x, y + 2, w, 2, Color("#5a5e70"))
			px(ci, x, y + h - 4, w, 2, Color("#5a5e70"))
			px(ci, x + 30, y + 3, 14, 10, Color("#a07848"))
			px(ci, x + 33, y + 5, 8, 4, Color("#ece6d6"))
		"bins":
			for i in 3:
				var bx := x + i * (w / 3.0)
				var cc2: Color = [Color("#ff6a7a"), Color("#b48aff"), Color("#9dff7a")][i]
				px(ci, bx + 2, y + 1, w / 3.0 - 4, h - 2, Color("#3a3e4c"))
				px(ci, bx + 2, y + 1, w / 3.0 - 4, 3, cc2.darkened(0.3))
		"timecard":
			px(ci, x + 3, y + 2, 10, 12, Color("#5a5e70"))
			px(ci, x + 4, y + 3, 8, 3, Color("#2a2c38"))
			px(ci, x + 5, y + 8, 6, 5, Color("#e8e4d8"))
		"boxes":
			px(ci, x, y - 6, 14, 14, Color("#a07848"))
			px(ci, x + 14, y - 2, 16, 12, Color("#8a6a40"))
			px(ci, x + 4, y - 14, 12, 9, Color("#b88a58"))
			px(ci, x + 6, y - 6, 2, 14, Color("#c8a070", 0.5))
		"chair":
			px(ci, x + 3, y - 6, 10, 8, Color("#4a2a5a"))
			px(ci, x + 3, y + 2, 10, 4, Color("#5a3a6a"))
			px(ci, x + 4, y + 6, 2, 8, Color("#2a1a3a"))
			px(ci, x + 10, y + 6, 2, 8, Color("#2a1a3a"))
		_:
			pass


## ネオン看板。flicker で瞬く。
static func draw_neon_sign(ci: CanvasItem, r: Rect2, text: String, col: Color, t: float, font: Font, broken: bool) -> void:
	var on := 1.0
	var phase := int(t * 9.0 + r.position.x)
	if broken:
		on = 0.25 if phase % 5 == 0 or phase % 7 == 0 else 0.7
	elif phase % 41 == 0:
		on = 0.35
	px(ci, r.position.x, r.position.y + 1, r.size.x, r.size.y - 2, Color("#0c0a16"))
	px(ci, r.position.x, r.position.y + 1, r.size.x, 1, Color(col, 0.5 * on))
	px(ci, r.position.x, r.position.y + r.size.y - 2, r.size.x, 1, Color(col, 0.5 * on))
	glow(ci, r.get_center(), r.size.y * 2.2, col, 0.035 * on)
	if font == null:
		return
	var fs := 12
	var tw := font.get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, -1, fs).x
	var pos := Vector2(r.get_center().x - tw / 2.0, r.position.y + r.size.y / 2.0 + fs * 0.38)
	ci.draw_string(font, pos + Vector2(0, 1), text, HORIZONTAL_ALIGNMENT_LEFT, -1, fs, Color(col, 0.3 * on))
	ci.draw_string(font, pos, text, HORIZONTAL_ALIGNMENT_LEFT, -1, fs, Color(col.lightened(0.35), on))
