extends Node2D
## マップのタイルを一括描画する。内容が変わったときだけ再描画するので軽い。

var grid: PackedStringArray = []
var floor_ch: String = "."


func _draw() -> void:
	var h := grid.size()
	for ty in range(h):
		var row := grid[ty]
		for tx in range(row.length()):
			PixelArt.draw_tile(self, row[tx], tx, ty, grid, floor_ch)
