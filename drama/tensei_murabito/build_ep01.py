"""第1話「転生したら最弱の村人だった」のカット表 (plan.json) を作る。

    python drama/tensei_murabito/build_ep01.py
    python -m aivideo --plan drama/tensei_murabito/ep01_plan.json --shorts --out output/drama
"""
import json
from pathlib import Path

HERE = Path(__file__).parent

MINATO = ("a 25-year-old Japanese man, short messy black hair, dark brown eyes, slim build, clean-shaven, "
          "wearing a worn beige linen tunic with a brown leather belt and dark brown trousers")
MINATO_SUIT = ("a 25-year-old Japanese man, short messy black hair, dark brown eyes, slim build, "
               "wearing a dark navy business suit and loosened tie")
RINA = ("an 18-year-old young woman, long chestnut-brown hair in a side braid, green eyes, gentle face, "
        "wearing a moss-green linen dress with a white apron")
GALD = ("a tall arrogant knight in his late 20s, slicked-back blond hair, sharp blue eyes, "
        "polished silver plate armor, long crimson cape")
ORD = "an elderly priest with a long white beard, white hooded robe with gold trim, holding a wooden staff"
VILLAGE = ("a small medieval European-style frontier village with timber-framed houses, "
           "surrounded by forest and distant mountains")
SQUARE = "the village square with a stone pedestal holding a large glowing crystal orb"

STYLE = ("photorealistic live-action fantasy film still, cinematic lighting, shallow depth of field, "
         "35mm anamorphic lens, natural skin texture, vertical composition")

# (話し手, セリフ, 映像, カメラ, 転換, 効果音, テロップ, 間(秒))
SHOTS = [
    ("ナレーション", "死んだと思ったら、異世界にいた。しかも――",
     f"{MINATO}, standing alone in {VILLAGE} at dawn, staring in shock at a translucent glowing blue status window floating in front of him",
     "zoom_in", "fade", "impact", "転生したら――\nレベル1の村人だった", 0.3),
    ("ナレーション", "二十五歳、会社帰り。トラックから子どもを助けて、俺は死んだ。",
     f"{MINATO_SUIT}, on a rainy Tokyo street at night, pushing a small child out of the way as blinding truck headlights rush toward him, neon reflections on wet asphalt",
     "zoom_in", "fadeblack", "whoosh", "", 0.0),
    ("ナレーション", "次に目を開けると――",
     "a vast endless white space filled with soft divine light and floating particles, a silhouette of a man lying in the center",
     "zoom_out", "fadeblack", "chime", "", 0.4),
    ("湊", "……ここ、どこだ？",
     f"{MINATO}, lying on the grass and slowly sitting up, confused, in {VILLAGE}, morning sunlight, villagers watching from a distance",
     "pan_right", "fade", "none", "", 0.0),
    ("神官", "次の者。水晶に手をかざしなさい。",
     f"{ORD}, standing beside {SQUARE}, villagers gathered in a line for a job appraisal ceremony",
     "zoom_in", "slideleft", "none", "", 0.0),
    ("湊", "職業鑑定……ゲームかよ。",
     f"close-up of the hand of {MINATO} touching a large crystal orb on a stone pedestal, the crystal glowing faintly gray",
     "push", "dissolve", "chime", "", 0.0),
    ("神官", "職業……村人。レベル、1じゃ。",
     f"close-up of {ORD} squinting at the crystal orb with a disappointed expression, soft gray glow on his face",
     "zoom_in", "fade", "none", "職業：村人　Lv.1", 0.0),
    ("ガルド", "ハッ。転生者と聞いて期待したが、ただの村人か。",
     f"{GALD}, laughing mockingly with arms crossed in {VILLAGE}, crowd of villagers laughing behind him",
     "zoom_in", "slideright", "pop", "", 0.0),
    ("ガルド", "せいぜい畑でも耕してろ。",
     f"low angle close-up of {GALD} looking down with a cold smirk, crimson cape blowing in the wind",
     "push", "fade", "none", "", 0.0),
    ("湊", "（村人って……最弱じゃねえか）",
     f"close-up of {MINATO} clenching his fist and lowering his head in humiliation, crowd blurred in background",
     "zoom_in", "fade", "none", "", 0.0),
    ("リナ", "大丈夫？　私はリナ。あんな人、気にしないで。",
     f"{RINA}, smiling kindly and offering her hand toward the camera, warm afternoon light, {VILLAGE}",
     "zoom_in", "dissolve", "none", "", 0.0),
    ("ナレーション", "その時だった。",
     "the edge of a forest beside a medieval village, a pack of huge black wolves with glowing red eyes bursting out of the trees, villagers screaming and running",
     "zoom_in", "fadeblack", "impact", "", 0.0),
    ("ガルド", "下がってろ、雑魚ども！　ファイアボール！",
     f"{GALD}, casting a huge blazing fireball from his outstretched hand toward black wolves, fire lighting up his armor, epic action shot",
     "zoom_out", "zoomin", "impact", "", 0.0),
    ("湊", "……なんだ、これ。",
     f"extreme close-up of the eyes of {MINATO}, the reflection of a fireball in his pupils, faint blue glowing light around him",
     "push", "fade", "whoosh", "", 0.0),
    ("システム", "隠しスキル、模倣を確認しました。",
     f"{MINATO} staring at a translucent glowing blue holographic status window in the air, mystical blue light on his face, dusk",
     "zoom_in", "circleopen", "chime", "隠しスキル【模倣】", 0.3),
    ("湊", "俺にも……使える、のか？",
     f"close-up of the open palm of {MINATO}, a small flickering flame igniting in his hand, his astonished face lit by firelight",
     "zoom_in", "fade", "impact", "", 0.4),
    ("ナレーション", "最弱の村人の、成り上がりが始まる。",
     f"{MINATO} standing on a hill above {VILLAGE} at sunset, holding a small flame in his palm, wind in his hair, epic wide shot",
     "zoom_out", "fadeblack", "chime", "次回　第2話\n村人、初めての魔法", 1.5),
]

plan = {
    "theme": "転生したらレベル1の村人だった 第1話「転生したら最弱の村人だった」",
    "target_seconds": 80, "shorts": True, "drama": True,
    "concept": {"angle": "異世界転生ショートドラマ 第1話", "hook": "死んだと思ったら、異世界にいた。"},
    "visual_style": STYLE, "bgm_mood": "epic", "palette": ["#1B2A4A", "#C9A227", "#2F80ED"],
    "voices": {"湊": 11, "リナ": 8, "ガルド": 13, "神官": 42, "ナレーション": 52, "システム": 89},
    "colors": {"湊": "#2F80ED", "リナ": "#27AE60", "ガルド": "#EB5757", "神官": "#9B51E0", "システム": "#00A6D6"},
    "titles": ["【第1話】転生したらレベル1の村人だった #異世界転生 #ショートドラマ"],
    "description": ("トラックから子どもを助けて死んだ25歳の会社員・湊。\n"
                    "転生した異世界で与えられた職業は、最弱の「村人」だった――。\n"
                    "見下される日々の中、彼は自分だけの隠しスキルに気づく。\n\n"
                    "毎話60〜90秒の異世界転生ショートドラマ。続きは次回！\n"
                    "※この作品はフィクションです。映像は AI で生成しています。\n\n"
                    "#異世界転生 #ショートドラマ #AIドラマ"),
    "tags": ["異世界転生", "ショートドラマ", "AIドラマ", "ファンタジー", "成り上がり"],
    "thumbnail": {"text": "レベル1の村人", "ideas": []},
    "chapters": [{"title": "第1話 転生したら最弱の村人だった", "goal": "", "seconds": 80, "scenes": []}],
}
for i, (spk, line, visual, cam, trans, sfx, telop, hold) in enumerate(SHOTS):
    plan["chapters"][0]["scenes"].append({
        "id": f"s{i:03d}", "chapter": 0, "speaker": spk, "narration": line,
        "onscreen_text": telop.replace("\n", " ") if telop else "",
        "visual_prompt": visual, "camera": cam, "transition": trans, "sfx": sfx,
        "emoji": [], "highlight": [], "hold": hold,
    })

out = HERE / "ep01_plan.json"
out.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"{out} ({len(SHOTS)}カット)")
