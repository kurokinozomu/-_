extends Node2D
## マップのタイルを描画する。
## タイルは数千個の小さな矩形になるので、毎フレーム描くとスマホの GPU に重い。
## マップを読み込んだときに一度だけオフスクリーン (SubViewport) に描いて画像にし、
## 以後はその画像1枚を表示する。

var grid: PackedStringArray = []
var floor_ch: String = "."

var _viewport: SubViewport
var _painter: Node2D
var _sprite: Sprite2D


func _ready() -> void:
	_viewport = SubViewport.new()
	_viewport.transparent_bg = true
	_viewport.disable_3d = true
	_viewport.canvas_item_default_texture_filter = Viewport.DEFAULT_CANVAS_ITEM_TEXTURE_FILTER_NEAREST
	_viewport.render_target_update_mode = SubViewport.UPDATE_DISABLED
	add_child(_viewport)
	_painter = Node2D.new()
	_painter.draw.connect(_paint)
	_viewport.add_child(_painter)
	_sprite = Sprite2D.new()
	_sprite.centered = false
	_sprite.texture = _viewport.get_texture()
	add_child(_sprite)


## grid / floor_ch を設定したあとに呼ぶ (World.load_map から)
func rebuild() -> void:
	var h := grid.size()
	var w := grid[0].length() if h > 0 else 1
	_viewport.size = Vector2i(maxi(w, 1) * PixelArt.TILE, maxi(h, 1) * PixelArt.TILE)
	_painter.queue_redraw()
	_viewport.render_target_update_mode = SubViewport.UPDATE_ONCE


func _paint() -> void:
	var h := grid.size()
	for ty in range(h):
		var row := grid[ty]
		for tx in range(row.length()):
			PixelArt.draw_tile(_painter, row[tx], tx, ty, grid, floor_ch)
