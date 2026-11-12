class_name DialogueRunner
extends RefCounted
## dialogue.json のスクリプトを順番に実行する。
## 1ステップ = 1つの辞書。say / choice / if / set / unset / rel / money / action / run / wait。

var box: DialogueBox
var host: Node          ## do_action(name, arg) を持つ Main
var aborted := false


func _init(p_box: DialogueBox, p_host: Node) -> void:
	box = p_box
	host = p_host


func has_script(id: String) -> bool:
	return GameData.dialogues.has(id)


func run(id: String) -> void:
	if not GameData.dialogues.has(id):
		push_error("会話スクリプトがありません: " + id)
		await box.say("", "", "（会話データ「%s」が見つかりません）" % id)
		return
	var steps: Variant = GameData.dialogues[id]
	if typeof(steps) != TYPE_ARRAY:
		push_error("会話スクリプトの形式が不正: " + id)
		return
	await run_steps(steps)


func run_steps(steps: Array) -> void:
	for step in steps:
		if aborted:
			return
		if typeof(step) != TYPE_DICTIONARY:
			continue
		await run_step(step)


func run_step(s: Dictionary) -> void:
	if s.has("say"):
		await box.say(str(s.get("who", "")), str(s.get("face", "normal")), str(s["say"]))
	elif s.has("choice"):
		var opts: Array = []
		for o in s["choice"]:
			if GameState.eval_cond(o.get("if", "")):
				opts.append(o)
		if opts.is_empty():
			return
		var labels: Array = []
		for o in opts:
			labels.append(str(o.get("text", "")))
		var idx: int = await box.choose(labels)
		await run_steps(opts[idx].get("do", []))
	elif s.has("if"):
		if GameState.eval_cond(s["if"]):
			await run_steps(s.get("then", []))
		else:
			await run_steps(s.get("else", []))
	elif s.has("set"):
		var v: Variant = s["set"]
		if typeof(v) == TYPE_ARRAY:
			for f in v:
				GameState.set_flag(str(f))
		elif typeof(v) == TYPE_DICTIONARY:
			for k in v.keys():
				GameState.set_flag(str(k), v[k])
		else:
			GameState.set_flag(str(v))
	elif s.has("unset"):
		var u: Variant = s["unset"]
		if typeof(u) == TYPE_ARRAY:
			for f in u:
				GameState.set_flag(str(f), false)
		else:
			GameState.set_flag(str(u), false)
	elif s.has("rel"):
		var r: Dictionary = s["rel"]
		for k in r.keys():
			GameState.add_relation(str(k), int(r[k]))
	elif s.has("money"):
		GameState.add_money(int(s["money"]))
	elif s.has("action"):
		box.visible = false if str(s["action"]) in ["open_shop", "photo", "paper", "sleep", "ending"] else box.visible
		await host.do_action(str(s["action"]), s.get("arg", null))
	elif s.has("run"):
		await run(str(s["run"]))
	elif s.has("wait"):
		await host.get_tree().create_timer(float(s["wait"])).timeout
