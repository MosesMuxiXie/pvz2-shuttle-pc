"""把 Renders 新世界（中国园林 / 洛城风云 / 月虹市场）的植物、僵尸、世界数据
写入 content/*.json。可重复执行：同 id 覆盖更新。

素材来自用户提供的 Renders 目录（静态立绘），由 tools/import_renders.py 导入到
assets/art/<world>/<slug>.png。
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "content"


def P(pid, zh, en, cost, cd, hp, fam, art, beh, dmg=0, interval=0.0,
      proj="pea", rows=None, extra=None, desc="", tags=None):
    d = {
        "id": pid, "name_zh": zh, "name_en": en, "cost": cost, "cooldown": cd,
        "hp": hp, "family": fam, "art": art, "behavior": beh,
        "damage": dmg, "interval": interval, "projectile": proj,
        "rows": rows or [0], "pierce": False, "tags": tags or ["plant", "new"],
        "desc_zh": desc, "almanac_no": 0, "plantfood": "",
    }
    if extra:
        d.update(extra)
    return d


def Z(zid, zh, en, hp, speed, art, base_art=None, armor=None, beh="walk",
      eat=100.0, cost=100, tags=None, desc="", extra=None, garg=False):
    d = {
        "id": zid, "name_zh": zh, "name_en": en, "hp": hp, "speed": speed,
        "eat_dps": eat, "armor": armor or [], "behavior": beh, "art": art,
        "armature": None, "cost": cost, "desc_zh": desc,
        "tags": tags or ["zombie", "new"], "extra": {}}
    if base_art:
        d["extra"]["art_variants"] = {"base": base_art}
        if armor:
            d["extra"]["art_variants"]["armor1"] = armor[0]["art"]
    if garg:
        d["extra"]["art_gargantuar"] = True
    if extra:
        d["extra"].update(extra)
    return d


PLANTS = [
    P("gardenia", "栀子花", "Gardenia", 225, 12, 300, "Gardenia",
      "art/chinesegarden/gardenia.png", "shoot", 30, 1.5,
      desc="栀子花会向整行僵尸抛洒花瓣，花瓣带着淡淡的香气。"),
    P("jasmine", "茉莉", "Jasmine", 125, 25, 300, "Jasmine",
      "art/chinesegarden/jasmine.png", "produce", interval=22.0,
      extra={"sun_value": 25, "sun_interval": 22.0},
      desc="茉莉在月色下安静地产出阳光，偶尔也会哼一段小调。"),
    P("torpedofruit", "鱼雷果", "Torpedo Fruit", 125, 8, 1500, "Torpedo",
      "art/chinesegarden/torpedofruit.png", "shoot", 100, 2.2,
      desc="鱼雷果的果实会笔直地撞向僵尸，威力惊人。"),
    P("seapotatomine", "海土豆雷", "Sea-potato Mine", 75, 20, 300, "Mine",
      "art/chinesegarden/seapotatomine.png", "mine", 1800, 0.0,
      extra={"delay": 12.0},
      desc="海土豆雷把自己埋进石缝里，等待僵尸踩上来。"),
    P("elderbarrier", "接骨木屏障", "Elderbarrier", 75, 15, 3000, "Wall",
      "art/chinesegarden/elderbarrier.png", "wall",
      desc="接骨木编成的屏障，能挡住僵尸很久。"),
    P("birdofparadise", "天堂鸟", "Bird of Paradise", 200, 15, 300, "Bird",
      "art/losantosvice/birdofparadise.png", "shoot", 45, 1.6,
      desc="天堂鸟把花瓣当作回力标，命中两个方向的敌人。"),
    P("poppinpoppies", "虞美人", "Poppin' Poppies", 225, 15, 300, "Poppy",
      "art/losantosvice/poppinpoppies.png", "shoot", 40, 1.8,
      desc="虞美人跳着舞，把种子一颗颗弹向街道尽头的僵尸。"),
    P("yuccaguardian", "丝兰卫士", "Yucca Guardian", 175, 10, 2000, "Yucca",
      "art/losantosvice/yuccaguardian.png", "wall",
      desc="丝兰卫士像路边的绿化带一样沉默而可靠。"),
    P("begonia", "秋海棠", "Begonia", 175, 10, 300, "Begonia",
      "art/lunarrainbowmarket/begonia.png", "lob", 60, 2.4, proj="cabbage",
      desc="秋海棠把花瓣抛向空中，越过前排落在僵尸头顶。"),
    P("potatochip", "薯片", "Potato Chip", 0, 5, 300, "Chip",
      "art/lunarrainbowmarket/potatochip.png", "instant", 300, 0.0,
      extra={"delay": 0.4},
      desc="一片煎得恰到好处的薯片，落地就碎。免费。"),
    P("missiletoast", "导弹吐司", "Missile Toast", 250, 8, 300, "Toast",
      "art/lunarrainbowmarket/missiletoast.png", "lob", 120, 3.0, proj="melon",
      desc="涂抹了过多黄油的吐司，点火后划出抛物线。"),
]

BASE_ARMOR = lambda hp, name, art: {"hp": hp, "name": name, "art": art, "metal": False}

CG = "chinesegarden"
LSV = "losantosvice"
LRM = "lunarrainbowmarket"

ZOMBIES = [
    # ---------------- 中国园林 ----------------
    Z("garden_zombie", "园林僵尸", "Garden Zombie", 190, 0.185,
      "art/chinesegarden/zombie.png", tags=["zombie", CG],
      desc="背着屏风、戴着瓜皮帽的园林僵尸。"),
    Z("garden_cone", "园林路障僵尸", "Garden Conehead", 560, 0.185,
      "art/chinesegarden/conehead.png", base_art="art/chinesegarden/zombie.png",
      armor=[BASE_ARMOR(370, "路障", "art/chinesegarden/conehead.png")],
      tags=["zombie", CG], desc="头上的路障让他能多挨几发豌豆。"),
    Z("garden_bucket", "园林铁桶僵尸", "Garden Buckethead", 1290, 0.185,
      "art/chinesegarden/buckethead.png", base_art="art/chinesegarden/zombie.png",
      armor=[BASE_ARMOR(1100, "铁桶", "art/chinesegarden/buckethead.png")],
      tags=["zombie", CG], desc="铁桶挡住了大部分攻击，但他看不清路。"),
    Z("garden_flag", "园林旗帜僵尸", "Garden Flag Zombie", 190, 0.24,
      "art/chinesegarden/flag.png", base_art="art/chinesegarden/zombie.png",
      tags=["zombie", CG], desc="举着灯笼旗，标志着一大波僵尸的到来。"),
    Z("garden_poet", "诗人僵尸", "Literati Zombie", 570, 0.23,
      "art/chinesegarden/poet.png", tags=["zombie", CG],
      desc="边走边吟诗的僵尸，据说他的诗可以退敌。"),
    Z("garden_umbrella", "纸伞僵尸", "Umbrella Zombie", 420, 0.25,
      "art/chinesegarden/umbrella.png", tags=["zombie", CG],
      desc="撑着纸伞的僵尸，能挡下从正面飞来的豌豆。"),
    Z("garden_imp", "太监小鬼", "Official Imp", 190, 0.22,
      "art/chinesegarden/imp.png", tags=["zombie", CG],
      desc="宫里跑腿的小鬼，跑得很快。"),
    Z("garden_gargantuar", "护园巨人", "Guardian Gargantuar", 3600, 0.24,
      "art/chinesegarden/gargantuar.png", tags=["zombie", CG],
      garg=True, desc="扛着石灯笼的巨人僵尸，一锤就能砸扁一排植物。"),
    Z("garden_cuju", "蹴鞠明星僵尸", "Cuju Star Zombie", 840, 0.22,
      "art/chinesegarden/cujustar.png", tags=["zombie", CG],
      desc="颠着蹴鞠一路小跑的僵尸，球技比走路更熟练。"),
    Z("garden_drummer", "鼓手僵尸", "Drummer Zombie", 400, 0.2,
      "art/chinesegarden/drummer.png", tags=["zombie", CG],
      desc="敲着鼓给同伴打拍子。"),
    # ---------------- 洛城风云 ----------------
    Z("gang_zombie", "帮派僵尸", "Families Zombie", 190, 0.185,
      "art/losantosvice/zombie.png", tags=["zombie", LSV],
      desc="在街区里晃荡的帮派僵尸。"),
    Z("gang_cone", "帮派路障僵尸", "Gang Conehead", 560, 0.185,
      "art/losantosvice/conehead.png", base_art="art/losantosvice/zombie.png",
      armor=[BASE_ARMOR(370, "路障", "art/losantosvice/conehead.png")],
      tags=["zombie", LSV], desc="路障是他从工地顺来的。"),
    Z("gang_bucket", "帮派铁桶僵尸", "Gang Buckethead", 1290, 0.185,
      "art/losantosvice/buckethead.png", base_art="art/losantosvice/zombie.png",
      armor=[BASE_ARMOR(1100, "铁桶", "art/losantosvice/buckethead.png")],
      tags=["zombie", LSV], desc="铁桶是他的头盔，也是他的饭碗。"),
    Z("gang_flag", "帮派旗帜僵尸", "Gang Flag Zombie", 190, 0.24,
      "art/losantosvice/zombie.png", tags=["zombie", LSV],
      desc="挥舞着帮派旗帜，招呼同伙一起上。"),
    Z("gang_molotov", "燃烧瓶僵尸", "Molotov Zombie", 400, 0.12,
      "art/losantosvice/molotov.png", tags=["zombie", LSV],
      desc="手里的燃烧瓶让他走得格外慢。"),
    Z("gang_ozloc", "说唱僵尸", "OZ Loc Zombie", 300, 0.2,
      "art/losantosvice/ozloc.png", tags=["zombie", LSV],
      desc="自称西海岸说唱传奇，边走边押韵。"),
    Z("gang_carl", "卡尔·约翰逊", "Carl Johnson", 1200, 0.18,
      "art/losantosvice/carljohnson.png", tags=["zombie", LSV],
      desc="“All you had to do was guard the lawn, CJ!”"),
    Z("gang_gargantuar", "大烟巨人", "Big Smogantuar", 3600, 0.24,
      "art/losantosvice/gargantuar.png", tags=["zombie", LSV],
      garg=True, desc="拖着巨型烟囱的巨人，走过的地方全是尾气。"),
    Z("gang_imp", "快餐小鬼", "Cluckin' Bell Imp", 190, 0.22,
      "art/losantosvice/imp.png", tags=["zombie", LSV],
      desc="抱着一桶炸鸡的小鬼，跑得飞快。"),
    # ---------------- 月虹市场 ----------------
    Z("market_clockwork", "发条僵尸", "Clockwork Zombie", 340, 0.30,
      "art/lunarrainbowmarket/clockwork.png", tags=["zombie", LRM],
      desc="身上上满发条的市场僵尸，速度快得不太自然。"),
    Z("market_armor1", "发条路障僵尸", "Clockwork Conehead", 900, 0.28,
      "art/lunarrainbowmarket/clockwork.png",
      base_art="art/lunarrainbowmarket/clockwork.png",
      armor=[BASE_ARMOR(640, "齿轮护罩", "art/lunarrainbowmarket/clockwork.png")],
      tags=["zombie", LRM], desc="头上套了半截齿轮箱。"),
    Z("market_armor2", "发条铁桶僵尸", "Clockwork Buckethead", 2200, 0.26,
      "art/lunarrainbowmarket/clockwork.png",
      base_art="art/lunarrainbowmarket/clockwork.png",
      armor=[BASE_ARMOR(1600, "铁皮罩", "art/lunarrainbowmarket/clockwork.png")],
      tags=["zombie", LRM], desc="把整个铁皮罐扣在了头上。"),
    Z("market_mechanic", "机械师僵尸", "Mechanic Zombie", 3000, 0.20,
      "art/lunarrainbowmarket/mechanic.png", tags=["zombie", LRM],
      desc="背着工具箱的机械师，走到哪儿修到哪儿。"),
    Z("market_trapeze", "空中飞人僵尸", "Trapeze Zombie", 350, 0.135,
      "art/lunarrainbowmarket/trapeze.png", tags=["zombie", LRM],
      desc="晃晃悠悠踩着高跷的杂技僵尸。"),
]

WORLDS = [
    {"id": CG, "name_zh": "中国园林", "name_en": "Chinese Garden", "order": 9,
     "levels": 10, "map": "world/chinesegarden.png", "lawn": "lawn/chinesegarden.png",
     "unlock_after": "lostcity", "lawn_mode": "full",
     "desc_zh": "灯笼高挂的园林夜色，纸伞与诗人僵尸在月色下游荡。",
     "bg_tint": [236, 214, 178]},
    {"id": LSV, "name_zh": "洛城风云", "name_en": "Los Santos Vice", "order": 10,
     "levels": 10, "map": "world/losantosvice.png", "lawn": "lawn/losantosvice.png",
     "unlock_after": CG, "lawn_mode": "full",
     "desc_zh": "夕阳下的街区车库，帮派僵尸沿着柏油路压过来。",
     "bg_tint": [240, 198, 150]},
    {"id": LRM, "name_zh": "月虹市场", "name_en": "Lunar Rainbow Market", "order": 11,
     "levels": 10, "map": "world/lunarrainbowmarket.png", "lawn": "lawn/lunarrainbowmarket.png",
     "unlock_after": LSV, "lawn_mode": "full",
     "desc_zh": "月虹之下的夜市石阶，发条与杂技僵尸从摊位之间涌出。",
     "bg_tint": [198, 186, 232]},
]

ALMANAC = {
    "plants": {
        "gardenia": {"desc": "栀子花把花瓣撒向整行僵尸。", "tip": "栀子花的花语是“永恒的爱”，以及“别踩我的草坪”。"},
        "jasmine": {"desc": "茉莉为你产出额外的阳光。", "tip": "夜里的茉莉香气最好，阳光也是。"},
        "torpedofruit": {"desc": "鱼雷果笔直撞向僵尸，造成巨大伤害。", "tip": "它坚持自己是一枚鱼雷，只是长了叶子。"},
        "seapotatomine": {"desc": "埋在地里的海土豆雷，接触即爆。", "tip": "海土豆雷从小就梦想成为海鲜，可惜它只是土豆。"},
        "elderbarrier": {"desc": "接骨木屏障非常耐打。", "tip": "接骨木做屏障，据说还能驱邪。"},
        "birdofparadise": {"desc": "天堂鸟的花瓣会飞回来。", "tip": "它飞出去的花瓣，从来没丢过。"},
        "poppinpoppies": {"desc": "虞美人把种子弹向僵尸。", "tip": "虞美人跳舞的时候，僵尸也会跟着晃两下。"},
        "yuccaguardian": {"desc": "丝兰卫士是可靠的肉盾。", "tip": "它和绿化带的关系一直很好。"},
        "begonia": {"desc": "秋海棠越过前排，把花瓣抛到僵尸头顶。", "tip": "秋海棠喜欢高处，也喜欢砸中别人的头。"},
        "potatochip": {"desc": "免费的薯片，落地即碎。", "tip": "一片薯片能有多大事？——僵尸们不这么想。"},
        "missiletoast": {"desc": "导弹吐司沿抛物线落下，造成范围伤害。", "tip": "烤面包机的最高成就，就是把自己发射出去。"},
    },
    "zombies": {
        "garden_zombie": {"desc": "园林里最常见的基础僵尸。", "tip": "他背着的屏风其实是一面镜子。"},
        "garden_cone": {"desc": "路障让他多挨几发豌豆。", "tip": "路障是从园门口顺的。"},
        "garden_bucket": {"desc": "铁桶提供极高的防护。", "tip": "他把铁桶当成官帽，见人就拱手。"},
        "garden_flag": {"desc": "举旗的僵尸召唤大波进攻。", "tip": "灯笼旗是园里最亮的招牌。"},
        "garden_poet": {"desc": "诗人僵尸能抗又能走。", "tip": "他的诗只有僵尸听得懂。"},
        "garden_umbrella": {"desc": "纸伞可以挡下正面攻击。", "tip": "伞是纸的，但他撑得很认真。"},
        "garden_imp": {"desc": "快速的小鬼僵尸。", "tip": "专门负责传话和偷点心。"},
        "garden_gargantuar": {"desc": "巨人僵尸，一击摧毁植物。", "tip": "他扛着的石灯笼其实是他的夜灯。"},
        "garden_cuju": {"desc": "蹴鞠明星，速度快。", "tip": "颠球一千下才肯出场。"},
        "gang_zombie": {"desc": "街区里的基础僵尸。", "tip": "他只想安安静静地走完这条街。"},
        "gang_cone": {"desc": "路障僵尸，护甲中等。", "tip": "工地就在隔壁，拿一个不算偷。"},
        "gang_bucket": {"desc": "铁桶僵尸，护甲极高。", "tip": "铁桶在他头上已经生锈了。"},
        "gang_flag": {"desc": "举旗召唤同伙。", "tip": "旗子是从洗车店门口拔的。"},
        "gang_molotov": {"desc": "燃烧瓶僵尸走得慢。", "tip": "他其实更想点一份外卖。"},
        "gang_ozloc": {"desc": "说唱僵尸，节奏感很强。", "tip": "他的 mixtape 在僵尸圈很火。"},
        "gang_carl": {"desc": "高血量精英僵尸。", "tip": "“All you had to do was guard the lawn, CJ!”"},
        "gang_gargantuar": {"desc": "巨人僵尸，极其危险。", "tip": "尾气比他的拳头更可怕。"},
        "market_clockwork": {"desc": "上满发条的基础僵尸。", "tip": "发条松了就会原地转圈。"},
        "market_armor1": {"desc": "带护罩的发条僵尸。", "tip": "齿轮罩只挡住了一半的豌豆。"},
        "market_armor2": {"desc": "重甲发条僵尸。", "tip": "他把铁皮罐当成了头盔。"},
        "market_mechanic": {"desc": "高血量精英僵尸。", "tip": "走到哪儿都要拧两下螺丝。"},
        "market_trapeze": {"desc": "踩高跷的杂技僵尸。", "tip": "摔下来会比被豌豆打中更疼。"},
        "garden_drummer": {"desc": "敲鼓的园林僵尸。", "tip": "鼓点一响，僵尸们就走得整齐多了。"},
        "gang_imp": {"desc": "抱炸鸡的小鬼僵尸。", "tip": "他跑得比外卖还快。"},
    },
}


def upsert(items, rows, key="id"):
    index = {it.get(key): i for i, it in enumerate(items)}
    for row in rows:
        k = row.get(key)
        if k in index:
            items[index[k]] = row
        else:
            index[k] = len(items)
            items.append(row)
    return items


def main():
    worlds_path = CONTENT / "worlds.json"
    plants_path = CONTENT / "plants.json"
    zombies_path = CONTENT / "zombies.json"
    almanac_path = CONTENT / "almanac.json"

    worlds = json.load(open(worlds_path, encoding="utf-8"))
    upsert(worlds, WORLDS)
    json.dump(worlds, open(worlds_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("worlds", len(worlds))

    plants = json.load(open(plants_path, encoding="utf-8"))
    upsert(plants, PLANTS)
    # 给新植物补图鉴编号（接在已有最大编号之后）
    _max_no = max((int(p.get("almanac_no") or 0) for p in plants), default=0)
    for p in plants:
        if p["id"] in {x["id"] for x in PLANTS} and not p.get("almanac_no"):
            _max_no += 1
            p["almanac_no"] = _max_no
    json.dump(plants, open(plants_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("plants", len(plants))

    zombies = json.load(open(zombies_path, encoding="utf-8"))
    upsert(zombies, ZOMBIES)
    json.dump(zombies, open(zombies_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("zombies", len(zombies))

    almanac = json.load(open(almanac_path, encoding="utf-8"))
    almanac.setdefault("plants", {}).update(ALMANAC["plants"])
    almanac.setdefault("zombies", {}).update(ALMANAC["zombies"])
    json.dump(almanac, open(almanac_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("almanac", len(almanac["plants"]), len(almanac["zombies"]))


if __name__ == "__main__":
    main()
