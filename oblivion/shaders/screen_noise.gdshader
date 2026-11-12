shader_type canvas_item;
// 画面全体にうっすら乗るノイズ・走査線・周辺減光。
// 画面テクスチャを読まない (コピー不要) ので、モバイル/Web でも軽い。
// intensity: 売った記憶が増えるほど強くなる。 glitch: 売却時などの一時的な乱れ。

uniform float intensity : hint_range(0.0, 1.0) = 0.2;
uniform float glitch : hint_range(0.0, 1.0) = 0.0;
uniform vec4 tint : source_color = vec4(0.05, 0.02, 0.12, 1.0);

float hash(vec2 p) {
	return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453);
}

void fragment() {
	vec2 uv = SCREEN_UV;
	float frame = floor(TIME * 18.0);
	// グレイン
	float n = hash(floor(FRAGCOORD.xy / 2.0) + vec2(frame * 1.37, frame * 2.11));
	float grain = (n - 0.5) * intensity * 0.22;
	// 走査線
	float scan = step(0.5, fract(FRAGCOORD.y / 3.0)) * 0.035 * (0.4 + intensity);
	// 周辺減光
	vec2 c = uv - 0.5;
	float vig = smoothstep(0.30, 0.85, length(c * vec2(1.0, 1.25)));
	float alpha = vig * (0.55 + intensity * 0.25) + scan + abs(grain);
	vec3 col = mix(tint.rgb, vec3(n), clamp(abs(grain) * 4.0, 0.0, 1.0));
	// 横方向の乱れ (グリッチ)
	float g = glitch + intensity * 0.04 * step(0.985, hash(vec2(frame, 7.0)));
	if (g > 0.0) {
		float band = floor(uv.y * 40.0);
		float r = hash(vec2(band, frame));
		if (r < g * 0.45) {
			vec3 gc = mix(vec3(1.0, 0.35, 0.82), vec3(0.27, 0.88, 1.0), step(0.5, hash(vec2(band + 3.0, frame))));
			col = gc;
			alpha = max(alpha, 0.12 + 0.35 * g * hash(vec2(band, frame + 1.0)));
		}
	}
	COLOR = vec4(col, clamp(alpha, 0.0, 0.9));
}
