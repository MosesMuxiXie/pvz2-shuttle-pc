#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PvZ2 SHUTTLE 内容生成器。

把 work/gamedata 里拆包出来的真实 PvZ2 数据，转换成游戏运行时的 content/*.json：

    content/plants.json     30 株植物（数值、行为、图鉴文案）
    content/zombies.json    24 种僵尸（血量、护甲、速度）
    content/worlds.json     8 个世界（解锁顺序）
    content/levels/*.json   80 个关卡（8 世界 × 10 关，波次来自真实关卡文件）
    content/almanac.json    图鉴文字（植物 30 + 僵尸 24）

用法（在 PvZ2SHUTTLE 或工作区根目录都能跑）：

    python tools/build_content.py            # 读 gamedata，重写 content/
    python tools/build_content.py --check    # 只校验现有 content/，不写盘

数据来源（默认 D:/.../pvz_shuttle/work/gamedata，可用 --gamedata 覆盖）：

    json__Features__PlantFeatures.json   植物 CODENAME / 中英文名 / RES 预制体
    json__Objects__PlantProps.json       SunCost / Cooldown / Toughness / ShootInterval ...
    json__Objects__PlantAlmanac.json     植物图鉴 Introduction / Chat（中文）
    json__Features__ZombieFeatures.json  僵尸 CODENAME / 名字 / RES
    json__Objects__ZombieProps.json      Toughness / WalkSPS / EatDPS / StartingArmors
    json__Objects__ArmorProps.json       护甲血量（路障 +370，铁桶 +1100）
    json__Objects__ZombieAlmanac.json    僵尸图鉴
    levels__<world><n>.json              真实关卡：WaveManagerProperties.Waves + 每波 Zombies
    ../cache_resources_config_json       Cocos 资源清单，用来校验 art 预制体是否真的存在

约定
----
* art 一律写 bundle 内的 prefab 路径（不带扩展名），例如
  plants/PeashooterPLANT、zombies/BasicZOMBIE、armors/EgyptConeARMOR。
  引擎按 assets/db/<prefab> 取骨架/图集/贴图，所以这里必须是资源清单里真实存在的路径。
* 僵尸护甲是独立预制体：body 用 zombies/<Res>ZOMBIE，护甲用 armors/<World><Cone|Bucket>ARMOR，
  并在 armor[].armature 标出骨骼动画名（Cone / Bucket），供渲染层叠在 body 上。
* 行为取值来自 game/DESIGN.md：shoot|lob|produce|wall|instant|chomp|fume|mine|support|
  boomerang；另外使用了 spike（地刺/近战持续伤害）——引擎若未实现会退化成普通植物，
  见文件末尾「行为说明」。
* 确定性：所有随机洗牌都用固定种子 SEED + 世界序号 + 关卡序号，重跑结果完全一致。

替换说明（不存在于本 PvZ2 版本的 id）
------------------------------------
* cattail（猫尾草，PvZ1 泳池植物）→ homingthistle（导向蓟 Homing Thistle）：同样是任意行追踪。
* pole_vaulter（撑杆僵尸）→ iceage_dodo（渡渡鸟骑手）：本版本没有任何撑杆/跳跃僵尸，
  渡渡鸟骑手带有 PlantsToFlyOver 属性，是唯一真正会跳过植物的僵尸，behavior 记为 jump。

映射与已知限制
--------------
* 24 种僵尸：任务清单写了 25 个 id，但要求恰好 24 个；这里去掉 dino（侏罗纪不在 8 个战役世界内，
  数值上也只是 190/0.22/150 的普通僵尸）。要恢复只需在 ZOMBIES 里加一行。
* 真实关卡里共出现 88 种僵尸类型，多数是本作没有的世界特种僵尸。折叠顺序为
  精确表 → 巨尸 → 旗帜 → 同世界护甲后缀 → 世界前缀 → basic。
* beach/iceage/lostcity/kongfu/eighties 没有带甲 id，护甲变体折叠成基础僵尸（保留世界画风）；
  前院/埃及/海盗/牛仔/未来/黑暗使用真实护甲僵尸 + armors/<World>Cone|BucketARMOR。
* 旗帜僵尸不出现在关卡波次里（真实 PvZ2 也是由引擎在 flag 波自动追加），关卡用 waves[].flag
  标记；引擎需要时可在 flag 波生成 type=flag，它的 art 是 zombies/BasicFlagZOMBIE。
* kongfu/iceage/eighties 三个世界不在本作 8 个战役世界内，真实关卡里只在 Modern Day
  跨世界关卡出现；为了让 24 种僵尸都能在战役里出场，前院第 10 天保留 3 只"时空裂缝"
  客串，未来第 10 天放 2 只机甲橄榄球僵尸（记录在 level.extra.guests）。
* 真实波数 > 10 的关卡按顺序均匀合并成 10 波，单波上限 26 只，被砍掉的数量记录在
  level.extra.truncated_zombies，并汇总进运行报告的 wave_truncated 条目。
* 少数真实关卡没有可用波次（modern8 是 Beghouled 小游戏，egypt5 是墓碑关），
  用 10 波递增合成波兜底并标记 level.extra.synthesized。
* 关卡真实数据里没有 StartingSun，初始阳光按世界进度表 WORLD_SUN 给。
* 前院（第 1 世界）用的是真实 Modern Day 关卡，它是 PvZ2 的终盘跨世界关卡
  （单关最多 100 只、混入 future/beach/dark 等世界僵尸），不适合新手世界：
  这里把非前院系类型折成 basic/conehead/buckethead，并按 FRONTYARD_BUDGET
  裁剪总数（原数量记录在 level.extra.original_zombies）。pole_vaulter 保留
  2 只做跳跃行为演示。埃及/海盗/牛仔/未来/黑暗/海滩/失落之城保持真实构成。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# --------------------------------------------------------------------------- #
# 路径 / 常量
# --------------------------------------------------------------------------- #

ROOT = Path(__file__).resolve().parent.parent          # PvZ2SHUTTLE/
WORK_DEFAULT = ROOT.parent / "work"
CONTENT = ROOT / "content"
LEVELS_DIR = CONTENT / "levels"

SEED = 20261109
ROWS = 5
COOLDOWN_MIN, COOLDOWN_MAX = 3, 30
MAX_ZOMBIES_PER_WAVE = 26          # 压缩后单波上限，超出会记录到报告
TARGET_WAVES = 10                  # 每关目标波数

MISSING = object()

# 世界定义：id, 中文名, 英文名, 真实关卡文件前缀
WORLD_SPECS = [
    ("frontyard", "前院", "Frontyard", "modern"),
    ("egypt", "神秘埃及", "Ancient Egypt", "egypt"),
    ("pirate", "海盗港湾", "Pirate Seas", "pirate"),
    ("cowboy", "狂野西部", "Wild West", "cowboy"),
    ("future", "未来世界", "Far Future", "future"),
    ("dark", "黑暗时代", "Dark Ages", "dark"),
    ("beach", "神秘海滩", "Big Wave Beach", "beach"),
    ("lostcity", "失落之城", "Lost City", "lostcity"),
]

WORLD_DESC = {
    "frontyard": "草坪上的第一场战斗，学会种向日葵、豌豆射手和坚果墙。",
    "egypt": "黄沙下的金字塔，木乃伊僵尸成排走来，抛射植物开始发光。",
    "pirate": "甲板与海风之间，海盗僵尸会从船舷跃上你的草坪。",
    "cowboy": "尘土飞扬的西部小镇，牛仔僵尸的帽檐下藏着坏心思。",
    "future": "高科技都市，未来僵尸的机械护甲能挡下成吨豌豆。",
    "dark": "月光下的墓园，迷雾里传来骑士与弄臣的笑声。",
    "beach": "潮水涨落的海岸，深海僵尸会随浪头一起上岸。",
    "lostcity": "丛林深处的黄金遗迹，探宝僵尸正想搬走你的脑子。",
}

WORLD_TINT = {
    "frontyard": [232, 246, 214],
    "egypt": [255, 232, 186],
    "pirate": [196, 228, 255],
    "cowboy": [255, 222, 184],
    "future": [196, 240, 255],
    "dark": [186, 176, 214],
    "beach": [255, 242, 200],
    "lostcity": [216, 246, 206],
}

# 每关初始阳光（真实战役关卡没有 StartingSun，这里按世界进度给）
WORLD_SUN = {
    "frontyard": [150, 150, 150, 200, 200, 250, 250, 250, 250, 250],
    "egypt": [250, 250, 250, 250, 300, 300, 300, 300, 350, 350],
    "pirate": [250, 250, 300, 300, 300, 350, 350, 350, 400, 400],
    "cowboy": [300, 300, 300, 350, 350, 350, 400, 400, 400, 450],
    "future": [350, 350, 350, 400, 400, 400, 400, 450, 450, 500],
    "dark": [250, 250, 250, 300, 300, 300, 350, 350, 350, 400],
    "beach": [350, 350, 400, 400, 400, 450, 450, 450, 500, 500],
    "lostcity": [400, 400, 400, 450, 450, 450, 500, 500, 500, 550],
}

# 卡组池：按世界进度逐步解锁，前 3 张始终是向日葵/豌豆射手/坚果墙
WORLD_DECKS = {
    "frontyard": ["sunflower", "peashooter", "wallnut", "potatomine", "snowpea",
                  "bloomerang", "repeater", "cabbagepult"],
    "egypt": ["sunflower", "peashooter", "wallnut", "potatomine", "bonkchoy",
              "snowpea", "cabbagepult", "bloomerang"],
    "pirate": ["sunflower", "peashooter", "wallnut", "repeater", "kernelpult",
               "torchwood", "cherry_bomb", "threepeater"],
    "cowboy": ["sunflower", "twinsunflower", "peashooter", "wallnut", "tallnut",
               "melonpult", "splitpea", "jalapeno"],
    "future": ["sunflower", "twinsunflower", "peashooter", "magnifyinggrass",
               "gatling", "squash", "starfruit", "tallnut"],
    "dark": ["sunshroom", "sunflower", "fumeshroom", "peashooter", "chomper",
             "homingthistle", "umbrellaleaf", "wallnut"],
    "beach": ["sunflower", "twinsunflower", "peashooter", "wallnut",
              "homingthistle", "wintermelon", "iceburg", "spikeweed"],
    "lostcity": ["sunflower", "twinsunflower", "peashooter", "repeater",
                 "melonpult", "wintermelon", "tallnut", "gatling"],
}

# 前院是新手世界：真实 Modern Day 关卡里的跨世界僵尸折成前院三件套 + 读报僵尸，
# 只给撑杆跳僵尸（渡渡鸟）留 2 只出场机会，用来让引擎验证 jump 行为。
FRONTYARD_ALLOWED = {"basic", "conehead", "buckethead", "flag", "newspaper", "pole_vaulter"}
# 前院 1..10 天的僵尸总数预算（真实 Modern Day 是终盘世界，动辄 100 只，不适合新手）
FRONTYARD_BUDGET = [16, 20, 24, 28, 32, 36, 40, 44, 48, 56]

# 少量"客串"：冰河/八十年代/功夫世界不在本作 8 个战役世界里，只在真实 Modern Day
# 关卡里出现过；为了让 24 种僵尸都能在战役中出场，在前院终章留 3 只时空裂缝客串，
# 未来世界终章放 2 只机甲橄榄球僵尸当小 Boss（它本来就是未来世界的僵尸）。
GUEST_APPEARANCES = {
    ("frontyard", 10): [("basic", "iceage"), ("basic", "eighties"), ("basic", "kongfu")],
    ("future", 10): [("future", "football"), ("future", "football")],
}

# 真实关卡里的僵尸类型 → 本作 24 个 id；先查精确表，再按前缀/护甲后缀折叠
ZOMBIE_ALIASES = {
    # 真实 PvZ2 世界特种僵尸（本作没有的 id，折叠到同世界基础僵尸）
    "seagull": "pirate", "swashbuckler": "pirate", "barrelroller": "pirate",
    "cannon": "pirate", "pirate_imp": "pirate",
    "prospector": "cowboy", "poncho": "cowboy", "poncho_plate": "cowboy",
    "poncho_no_plate": "cowboy", "piano": "cowboy", "chicken_farmer": "cowboy",
    # 骆驼僵尸只出现在埃及关卡（中文版埃及第二部分的骆驼队），按世界画风折到木乃伊
    "camel_onehump": "mummy", "camel_twohump": "mummy",
    "camel_threehump": "mummy", "camel_manyhump": "mummy",
    "camel_onehump_touch": "mummy", "camel_twohump_touch": "mummy",
    "camel_threehump_touch": "mummy",
    "ra": "mummy", "explorer": "mummy", "tomb_raiser": "mummy",
    "pharaoh": "mummy", "egypt_imp": "mummy",
    "future_jetpack": "future", "future_protector": "future",
    "future_imp": "future", "mech_cone": "future", "disco_mech": "future",
    "dark_juggler": "dark", "dark_wizard": "dark", "dark_imp": "dark",
    "dark_imp_dragon": "dark",
    "beach_snorkel": "beach", "beach_fem": "beach", "beach_octopus": "beach",
    "beach_imp": "beach", "beach_fem_armor1": "beach", "beach_fem_armor2": "beach",
    "lostcity_excavator": "lostcity", "lostcity_jane": "lostcity",
    "lostcity_imp": "lostcity", "lostcity_impporter": "lostcity",
    "iceage_troglobite_1block": "iceage", "iceage_troglobite_2block": "iceage",
    "iceage_hunter": "iceage", "iceage_weaselhoarder": "iceage",
    "iceage_imp": "iceage",
    "dino_imp": "basic",
    "modern_balloon": "basic",
    "modern_newspaper": "newspaper",
    "football_mech": "football",
    # 撑杆僵尸的替代品：渡渡鸟骑手（唯一带 PlantsToFlyOver 的跳跃僵尸）
    "iceage_dodo": "pole_vaulter",
}

# 世界前缀 → (基础僵尸 id, {护甲等级: 带甲 id})
WORLD_ZOMBIE = {
    "tutorial": ("basic", {1: "conehead", 2: "buckethead"}),
    "lawn": ("basic", {1: "conehead", 2: "buckethead"}),
    "frontyard": ("basic", {1: "conehead", 2: "buckethead"}),
    "mummy": ("mummy", {1: "mummy_armor1", 2: "mummy_armor2"}),
    "egypt": ("mummy", {1: "mummy_armor1", 2: "mummy_armor2"}),
    "pirate": ("pirate", {1: "pirate_armor1"}),
    "cowboy": ("cowboy", {1: "cowboy_armor1"}),
    "future": ("future", {1: "future_armor1"}),
    "dark": ("dark", {1: "dark_armor1"}),
    "beach": ("beach", {}),
    "iceage": ("iceage", {}),
    "lostcity": ("lostcity", {}),
    "kongfu": ("kongfu", {}),
    "eighties": ("eighties", {}),
    "dino": ("basic", {}),
    "modern": ("basic", {}),
}

# --------------------------------------------------------------------------- #
# 植物表：字段为「行为/手感」，数值能读真实 props 的就不写死
# --------------------------------------------------------------------------- #

PLANTS = [
    dict(id="peashooter", behavior="shoot", damage=20, interval=1.35,
         projectile="pea", rows=[0], tags=["shooter", "day"]),
    dict(id="sunflower", behavior="produce", damage=0, interval=24,
         sun_value=25, sun_interval=24, tags=["sun", "day"]),
    dict(id="wallnut", behavior="wall", damage=0, interval=0, tags=["wall", "day"]),
    dict(id="potatomine", behavior="mine", damage=1800, interval=0, delay=14,
         splash=1.0, tags=["explosive", "day"]),
    dict(id="snowpea", behavior="shoot", damage=20, interval=1.35,
         projectile="pea_snow", rows=[0], slow=0.5, tags=["shooter", "ice"]),
    dict(id="repeater", behavior="shoot", damage=20, interval=1.35,
         projectile="pea", rows=[0], tags=["shooter", "day"], extra={"shots": 2}),
    dict(id="bloomerang", behavior="boomerang", damage=20, interval=2.7,
         projectile="boomerang", rows=[0], pierce=True,
         tags=["shooter", "pierce"], extra={"pierce_count": 3}),
    dict(id="cabbagepult", behavior="lob", damage=40, interval=2.7,
         projectile="cabbage", rows=[0], tags=["lobber"]),
    dict(id="chomper", behavior="chomp", damage=1800, interval=17, melee_range=1.6,
         tags=["melee"], extra={"chew_time": 17, "max_contain": 2}),
    dict(id="fumeshroom", behavior="fume", damage=40, interval=2.4, projectile="fume",
         rows=[0], pierce=True, melee_range=5.5,
         tags=["fume", "night"], extra={"shoot_range": 5.5}),
    dict(id="torchwood", behavior="support", damage=6.25, interval=1,
         tags=["buff", "fire"], extra={"fire_multiplier": 2, "death_damage": 450}),
    dict(id="cherry_bomb", behavior="instant", damage=1800, interval=0,
         splash=2.2, delay=1.2, plantfood=False, tags=["explosive"]),
    dict(id="jalapeno", behavior="instant", damage=1800, interval=0,
         splash=99, delay=1.2, plantfood=False,
         tags=["explosive", "fire"], extra={"row_wide": True}),
    dict(id="squash", behavior="instant", damage=1800, interval=0,
         splash=1.0, delay=1.0, tags=["melee"], extra={"single_target": True}),
    dict(id="threepeater", behavior="shoot", damage=20, interval=1.35,
         projectile="pea", rows=[-1, 0, 1], tags=["shooter", "multi_lane"]),
    dict(id="kernelpult", behavior="lob", damage=20, interval=2.7,
         projectile="corn", rows=[0], tags=["lobber"],
         extra={"butter_chance": 0.3, "butter_damage": 60, "butter_duration": 8}),
    dict(id="melonpult", behavior="lob", damage=80, interval=2.7,
         projectile="melon", splash=40, rows=[0],
         tags=["lobber", "splash"], extra={"splash_radius": 1.5}),
    dict(id="wintermelon", behavior="lob", damage=80, interval=2.7,
         projectile="winter_melon", splash=40, slow=0.5, rows=[0],
         tags=["lobber", "splash", "ice"], extra={"splash_radius": 1.5}),
    dict(id="spikeweed", behavior="spike", damage=10, interval=0.5, melee_range=1.0,
         tags=["spike", "ground"], extra={"ground_only": True}),
    dict(id="starfruit", behavior="shoot", damage=20, interval=1.35,
         projectile="star", rows=[0], tags=["shooter", "multi_lane"],
         extra={"five_way": True}),
    dict(id="tallnut", behavior="wall", damage=0, interval=0,
         tags=["wall"], extra={"tall": True}),
    dict(id="magnifyinggrass", behavior="shoot", damage=550, interval=0.333,
         projectile="magnifying_grass", rows=[0],
         tags=["shooter", "sun"], extra={"sun_cost_per_shot": 50}),
    dict(id="bonkchoy", behavior="spike", damage=15, interval=0.3, melee_range=1.6,
         tags=["melee", "spike"], extra={"melee": True, "heavy_damage": 30}),
    dict(id="twinsunflower", behavior="produce", damage=0, interval=24,
         sun_value=100, sun_interval=24, tags=["sun"],
         extra={"multi_sun": True}),
    dict(id="gatling", behavior="shoot", damage=20, interval=0.9,
         projectile="pea", rows=[0], tags=["shooter", "burst"],
         extra={"shots": 4, "burst_interval": 0.1}),
    dict(id="splitpea", behavior="shoot", damage=20, interval=1.35,
         projectile="pea", rows=[0], tags=["shooter", "backward"],
         extra={"shots": 2, "backward": True}),
    dict(id="iceburg", behavior="instant", damage=0, interval=0,
         splash=1.5, delay=0.6, slow=1.0, tags=["ice"],
         extra={"freeze_duration": 10, "freeze": True}),
    dict(id="sunshroom", behavior="produce", damage=0, interval=24,
         sun_value=15, sun_interval=24, tags=["sun", "night"],
         extra={"sun_value_list": [25, 50, 75], "grow_times": [18, 54]}),
    dict(id="homingthistle", behavior="shoot", damage=40, interval=1.35,
         projectile="homing_thistle", rows=[0], tags=["shooter", "homing"],
         extra={"homing": True, "any_lane": True}),
    dict(id="umbrellaleaf", behavior="support", damage=0, interval=0,
         tags=["support", "defence"],
         extra={"blocks_lob": True, "blocks_parachute": True}),
]

# 手册给出的行为映射覆盖（DESIGN 里的数值优先于拆包数值）
SUNFLOWER_OVERRIDE = {"sun_value": 25, "sun_interval": 24}
SUNSHROOM_OVERRIDE = {"sun_value": 15, "sun_interval": 24}

# --------------------------------------------------------------------------- #
# 僵尸表：id ← 真实 CODENAME（RES 决定 art），共 24 个
# --------------------------------------------------------------------------- #

ZOMBIES = [
    dict(id="basic", codename="tutorial", behavior="walk",
         tags=["frontyard", "basic"]),
    dict(id="conehead", codename="tutorial_armor1", behavior="walk",
         tags=["frontyard", "armored", "basic"]),
    dict(id="buckethead", codename="tutorial_armor2", behavior="walk",
         tags=["frontyard", "armored", "basic"]),
    dict(id="flag", codename="tutorial_flag", behavior="walk",
         tags=["frontyard", "flag"], extra={"is_flag": True}),
    dict(id="mummy", codename="mummy", behavior="walk", tags=["egypt", "basic"]),
    dict(id="mummy_armor1", codename="mummy_armor1", behavior="walk",
         tags=["egypt", "armored"]),
    dict(id="mummy_armor2", codename="mummy_armor2", behavior="walk",
         tags=["egypt", "armored"]),
    dict(id="pirate", codename="pirate", behavior="walk", tags=["pirate", "basic"]),
    dict(id="pirate_armor1", codename="pirate_armor1", behavior="walk",
         tags=["pirate", "armored"]),
    dict(id="cowboy", codename="cowboy", behavior="walk", tags=["cowboy", "basic"]),
    dict(id="cowboy_armor1", codename="cowboy_armor1", behavior="walk",
         tags=["cowboy", "armored"]),
    dict(id="future", codename="future", behavior="walk", tags=["future", "basic"]),
    dict(id="future_armor1", codename="future_armor1", behavior="walk",
         tags=["future", "armored"]),
    dict(id="dark", codename="dark", behavior="walk", tags=["dark", "basic"]),
    dict(id="dark_armor1", codename="dark_armor1", behavior="walk",
         tags=["dark", "armored"]),
    dict(id="beach", codename="beach", behavior="walk", tags=["beach", "basic"]),
    dict(id="iceage", codename="iceage", behavior="walk", tags=["iceage", "basic"],
         extra={"chill_instead_of_freeze": True}),
    dict(id="lostcity", codename="lostcity", behavior="walk",
         tags=["lostcity", "basic"]),
    dict(id="kongfu", codename="kongfu", behavior="walk", tags=["kongfu", "basic"],
         extra={"summon_count": 3}),
    dict(id="eighties", codename="eighties", behavior="walk",
         tags=["eighties", "basic"]),
    dict(id="gargantuar", codename="tutorial_gargantuar", behavior="gargantuar",
         tags=["boss", "gargantuar"],
         extra={"smash_damage": 1500, "imp_type": "basic"}),
    dict(id="football", codename="football_mech", behavior="walk",
         tags=["future", "special"],
         extra={"push_damage": 400, "immune_to_garlic": True}),
    dict(id="newspaper", codename="modern_newspaper", behavior="walk",
         tags=["frontyard", "special"],
         extra={"newspaper_hp": 800, "enrage_damage_scale": 4,
                "enrage_speed_scale": 4}),
    dict(id="pole_vaulter", codename="iceage_dodo", behavior="jump",
         tags=["iceage", "jump", "substitute"],
         extra={"jump_distance": 1, "is_substitute": True,
                "note": "本版本无撑杆僵尸，改用唯一会跳过植物的渡渡鸟骑手"}),
]

# RES → 护甲世界前缀（决定 armors/<World>ConeARMOR 的路径）
ARMOR_WORLD = {
    "Basic": "Basic", "BasicFlag": "Basic",
    "EgyptBasic": "Egypt", "PirateBasic": "Pirate", "CowboyBasic": "Cowboy",
    "FutureBasic": "Future", "DarkBasic": "Dark", "BeachBasic": "Beach",
    "IceageBasic": "Iceage", "LostcityBasic": "Lostcity",
    "KongfuBasic": "Kongfu", "EightiesBasic": "Eighties", "DinoBasic": "Dino",
    "Gargantuar": None, "FutureMechFootball": None, "ModernNewspaper": None,
}

ARMOR_TIER_NAME = {1: "Cone", 2: "Bucket", 3: "Bucket", 4: "Bucket"}

# 报告用的替换说明
SUBSTITUTIONS = [
    ("cattail", "homingthistle", "本版本无猫尾草，用同为任意行追踪的导向蓟代替"),
    ("pole_vaulter", "iceage_dodo", "本版本无撑杆僵尸，改用唯一会跳过植物的渡渡鸟骑手（jump）"),
]

FALLBACK_LOG = []      # (kind, detail) 构建过程中的降级/折叠记录


# --------------------------------------------------------------------------- #
# 工具函数
# --------------------------------------------------------------------------- #

def jload(path: Path):
    with open(path, "r", encoding="utf-8-sig") as fh:
        return json.load(fh)


def jdump(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, ensure_ascii=False, indent=2) + "\n"
    path.write_text(text, encoding="utf-8")


def index_by_alias(objects, key="objdata"):
    """把 {"objects": [{aliases:[...], objdata:{...}}]} 展平成 alias → objdata。"""
    out = {}
    for obj in objects:
        data = obj.get(key) or {}
        for alias in (obj.get("aliases") or []):
            out.setdefault(alias, data)
    return out


def rid(value):
    """'RTID(mummy@ZombieTypes)' → 'mummy'；已是裸名则原样返回。"""
    if not isinstance(value, str):
        return ""
    m = re.search(r"RTID\(([^@)]+)", value)
    return m.group(1) if m else value


def clamp(value, lo, hi, what):
    if value < lo:
        FALLBACK_LOG.append(("clamp", f"{what}: {value} → {lo}"))
        return lo
    if value > hi:
        FALLBACK_LOG.append(("clamp", f"{what}: {value} → {hi}"))
        return hi
    return value


_CJK = re.compile(r"[\u3000-\u303f\u4e00-\u9fff\uff00-\uffef]")
_TAGS = re.compile(r"<[^>]+>")


def clean_text(text: str) -> str:
    if not text:
        return ""
    text = _TAGS.sub("", str(text))
    text = text.replace("\\n", " ").replace("\r", " ").replace("\n", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def first_sentences(text: str, limit: int = 2, max_chars: int = 240) -> str:
    """取前 1-2 个完整句子；句子后面的引号/括号跟着一起保留，不在句中截断。"""
    text = clean_text(text)
    if not text:
        return ""
    parts = re.findall(r"[^。！？!?]*[。！？!?]+[”’」』）)]?", text)
    if not parts:
        return text[:max_chars]
    out = ""
    for part in parts:
        if len(out) + len(part) > max_chars:
            break
        out += part
        if len(re.findall(r"[。！？!?]", out)) >= limit:
            break
    out = out.strip()
    # 若整段文字本身很短（多数图鉴吐槽都是 1-3 句），保留完整内容更自然
    if out and len(text) <= max_chars and out != text:
        return text
    return out or text[:max_chars]


# --------------------------------------------------------------------------- #
# 载入原始数据
# --------------------------------------------------------------------------- #

class Source:
    def __init__(self, gamedata: Path, work: Path):
        self.gamedata = gamedata
        self.work = work
        pf = jload(gamedata / "json__Features__PlantFeatures.json")
        self.plant_features = {p["CODENAME"]: p for p in pf["PLANTS"]}
        self.plant_props = index_by_alias(
            jload(gamedata / "json__Objects__PlantProps.json")["objects"])
        self.plant_almanac = index_by_alias(
            jload(gamedata / "json__Objects__PlantAlmanac.json")["objects"])
        zf = jload(gamedata / "json__Features__ZombieFeatures.json")["ZOMBIES"]
        self.zombie_features = {z["CODENAME"]: z for z in zf}
        self.zombie_props = index_by_alias(
            jload(gamedata / "json__Objects__ZombieProps.json")["objects"])
        self.armor_props = index_by_alias(
            jload(gamedata / "json__Objects__ArmorProps.json")["objects"])
        self.zombie_almanac = index_by_alias(
            jload(gamedata / "json__Objects__ZombieAlmanac.json")["objects"])
        manifest = jload(work / "cache_resources_config_json")
        self.resources = {v[0] for v in (manifest.get("paths") or {}).values()}
        self.projectile_props = {}
        pj = gamedata / "json__Objects__ProjectileProps.json"
        if pj.exists():
            self.projectile_props = index_by_alias(jload(pj)["objects"])

    # -- 植物 ------------------------------------------------------------- #
    def almanac_entry(self, table, codename):
        if codename in table:
            return table[codename]
        alt = codename.replace("modern_", "")
        if alt in table:
            FALLBACK_LOG.append(("almanac_alias", f"{codename} → {alt}"))
            return table[alt]
        return {}

    def plant_art(self, codename):
        feat = self.plant_features[codename]
        res = feat.get("RES") or {}
        base = res.get("Plant") if isinstance(res, dict) else res
        return f"plants/{base}PLANT"

    def zombie_art(self, codename):
        res = self.zombie_features[codename].get("RES")
        return f"zombies/{res}ZOMBIE"


# --------------------------------------------------------------------------- #
# plants.json
# --------------------------------------------------------------------------- #

def build_plants(src: Source):
    plants = []
    for no, spec in enumerate(PLANTS, 1):
        cid = spec["id"]
        feat = src.plant_features[cid]
        props = src.plant_props.get(cid) or {}
        name_zh = feat["NAME"]["zh"]
        name_en = feat["NAME"]["en"]

        art = src.plant_art(cid)
        if art not in src.resources:
            FALLBACK_LOG.append(("art_missing", f"{cid}: {art}"))

        interval = spec.get("interval", props.get("ShootInterval") or 0)
        if cid == "sunflower":
            interval = SUNFLOWER_OVERRIDE["sun_interval"]
        elif cid == "sunshroom":
            interval = SUNSHROOM_OVERRIDE["sun_interval"]

        entry = {
            "id": cid,
            "name_zh": name_zh,
            "name_en": name_en,
            "cost": int(props.get("SunCost", 100)),
            "cooldown": clamp(int(props.get("Cooldown", 5)), COOLDOWN_MIN,
                              COOLDOWN_MAX, f"{cid}.cooldown"),
            "hp": int(spec.get("hp") or props.get("Toughness") or 300),
            "family": props.get("Family") or "Special",
            "art": art,
            "behavior": spec["behavior"],
            "damage": spec.get("damage", 0),
            "interval": interval,
            "projectile": spec.get("projectile"),
            "rows": spec.get("rows", [0]),
            "pierce": spec.get("pierce", False),
            "tags": ["plant", *spec.get("tags", [])],
            "desc_zh": "",
            "almanac_no": no,
            "plantfood": spec.get("plantfood", True),
        }
        for key in ("sun_value", "sun_interval", "splash", "slow",
                    "melee_range", "delay"):
            if key in spec:
                entry[key] = spec[key]
        if cid == "sunflower":
            entry.update(SUNFLOWER_OVERRIDE)
        elif cid == "sunshroom":
            entry.update(SUNSHROOM_OVERRIDE)
        if spec.get("extra"):
            entry["extra"] = dict(spec["extra"])

        alm = src.almanac_entry(src.plant_almanac, cid)
        desc = clean_text((alm.get("Introduction") or {}).get("zh"))
        entry["desc_zh"] = desc or f"{name_zh}，{cid} 的图鉴资料暂缺。"
        plants.append(entry)
    return plants


# --------------------------------------------------------------------------- #
# zombies.json
# --------------------------------------------------------------------------- #

def armor_for(src: Source, codename, res):
    """按 ZombieProps.StartingArmors 生成 armor 列表（真实血量 + 真实护甲预制体）。"""
    props = src.zombie_props.get(codename) or {}
    world = ARMOR_WORLD.get(res)
    armor = []
    for alias in (props.get("StartingArmors") or []):
        alias = rid(alias) if isinstance(alias, str) else str(alias)
        apr = src.armor_props.get(alias)
        if apr is None:
            FALLBACK_LOG.append(("armor_props_missing", f"{codename}: {alias}"))
            continue
        tier = int(alias[-1]) if alias[-1:].isdigit() else 1
        part = ARMOR_TIER_NAME.get(tier, "Cone")
        art = f"armors/{world}{part}ARMOR" if world else None
        if art is None:
            FALLBACK_LOG.append(("armor_world_missing", f"{codename}: {alias}"))
            continue
        if art not in src.resources:
            FALLBACK_LOG.append(("armor_art_missing", f"{codename}: {art}"))
        armor.append({
            "hp": int(apr.get("Toughness", 370)),
            "art": art,
            "armature": part,
            "metal": bool(apr.get("isMetal")),
        })
    return armor


def build_zombies(src: Source):
    zombies = []
    for spec in ZOMBIES:
        cid = spec["id"]
        codename = spec["codename"]
        feat = src.zombie_features[codename]
        props = src.zombie_props.get(codename) or src.zombie_props.get(
            codename.replace("modern_", "")) or {}
        res = feat.get("RES")
        art = src.zombie_art(codename)
        if art not in src.resources:
            FALLBACK_LOG.append(("art_missing", f"{cid}: {art}"))

        entry = {
            "id": cid,
            "name_zh": feat["NAME"]["zh"],
            "name_en": feat["NAME"]["en"],
            "hp": int(props.get("Toughness") or 190),
            "speed": float(props.get("WalkSPS") or 0.185),
            "eat_dps": float(props.get("EatDPS") or 100),
            "armor": armor_for(src, codename, res),
            "behavior": spec.get("behavior", "walk"),
            "art": art,
            "armature": None,
            "cost": int(props.get("WavePointCost") or 100),
            "desc_zh": "",
            "tags": ["zombie", *spec.get("tags", [])],
        }
        entry["extra"] = {"source_codename": codename,
                          "res": res, **spec.get("extra", {})}

        alm = src.almanac_entry(src.zombie_almanac, codename)
        desc = clean_text((alm.get("Introduction") or {}).get("zh"))
        entry["desc_zh"] = desc or f"{entry['name_zh']}，图鉴资料暂缺。"
        zombies.append(entry)
    return zombies


# --------------------------------------------------------------------------- #
# worlds.json
# --------------------------------------------------------------------------- #

def build_worlds(_src: Source):
    worlds = []
    for order, (wid, zh, en, _prefix) in enumerate(WORLD_SPECS, 1):
        worlds.append({
            "id": wid,
            "name_zh": zh,
            "name_en": en,
            "order": order,
            "levels": 10,
            "map": f"world/{wid}.png",
            "lawn": f"lawn/{wid}.png",
            "unlock_after": None if order == 1 else WORLD_SPECS[order - 2][0],
            "desc_zh": WORLD_DESC[wid],
            "bg_tint": WORLD_TINT[wid],
        })
    return worlds


# --------------------------------------------------------------------------- #
# levels/*.json
# --------------------------------------------------------------------------- #

def load_level_waves(src: Source, prefix: str, n: int):
    """读取真实关卡的波次：[[(类型, row|None), ...], ...]；无波次管理返回 []。"""
    path = src.gamedata / f"levels__{prefix}{n}.json"
    if not path.exists():
        FALLBACK_LOG.append(("level_missing", f"{prefix}{n}.json"))
        return []
    doc = jload(path)
    objects = doc.get("objects") or []
    by_alias = {}
    for obj in objects:
        for alias in (obj.get("aliases") or []):
            by_alias.setdefault(alias, obj)
    wm = next((o for o in objects
               if o.get("objclass") == "WaveManagerProperties"), None)
    if wm is None:
        return []
    waves = []
    for entry in (wm.get("objdata") or {}).get("Waves") or []:
        items = entry if isinstance(entry, list) else [entry]
        spawner = None
        for item in items:
            alias = rid(item)
            obj = by_alias.get(alias)
            if obj is not None and obj.get("objclass") == "SpawnZombiesJitteredWaveActionProps":
                spawner = obj
                break
        if spawner is None:
            continue
        zombies = []
        for z in (spawner.get("objdata") or {}).get("Zombies") or []:
            ztype = rid(z.get("Type"))
            try:
                row = int(z["Row"]) - 1
                if not 0 <= row < ROWS:
                    row = None
            except (KeyError, TypeError, ValueError):
                row = None
            zombies.append((ztype, row))
        waves.append(zombies)
    return waves


def map_zombie(ztype: str, world_id: str) -> str:
    """真实僵尸类型 → 本作 24 个 id 之一。"""
    if ztype in {z["id"] for z in ZOMBIES}:
        return ztype
    if ztype in ZOMBIE_ALIASES:
        return ZOMBIE_ALIASES[ztype]
    if "gargantuar" in ztype:
        return "gargantuar"
    if ztype.endswith("_flag"):
        return "flag"

    # 护甲后缀：<base>_armorN
    m = re.match(r"^(.*?)_armor(\d+)$", ztype)
    if m:
        base, tier = m.group(1), int(m.group(2))
        if base in WORLD_ZOMBIE:
            plain, armored = WORLD_ZOMBIE[base]
            if armored:
                best = max(t for t in armored if t <= tier) if any(
                    t <= tier for t in armored) else min(armored)
                return armored[best]
            return plain
        return map_zombie(base, world_id)

    # 世界前缀（长的先匹配，避免 beach_fem 落到 beach 之外的规则）
    for key in sorted(WORLD_ZOMBIE, key=len, reverse=True):
        if ztype == key or ztype.startswith(key + "_"):
            return WORLD_ZOMBIE[key][0]

    FALLBACK_LOG.append(("zombie_type", f"{world_id}: {ztype} → basic"))
    return "basic"


def compress_waves(raw, rng):
    """真实波次 → 至多 10 波；返回 (zombies_per_wave, truncated_count)。"""
    usable = [w for w in raw if w]
    if len(usable) < 5:
        return None, 0
    if len(usable) > TARGET_WAVES:
        n = len(usable)
        waves = [sum(usable[i * n // TARGET_WAVES:(i + 1) * n // TARGET_WAVES], [])
                 for i in range(TARGET_WAVES)]
    else:
        waves = usable
    truncated = 0
    capped = []
    for wave in waves:
        if len(wave) > MAX_ZOMBIES_PER_WAVE:
            truncated += len(wave) - MAX_ZOMBIES_PER_WAVE
            wave = wave[:MAX_ZOMBIES_PER_WAVE]
        capped.append(wave)
    return capped, truncated


def synthesized_waves(world_id: str, index: int):
    """没有可用真实波次时的稳妥方案：10 波，数量递增，后期加护甲/巨尸。"""
    plain, armored = WORLD_ZOMBIE.get(world_id, ("basic", {}))
    # 合成波也随关卡序号爬坡：第 5 天约 32 只，第 8 天约 37 只，不会比相邻真实关卡更离谱
    base = [1, 1, 2, 2, 2, 3, 3, 4, 5, 7]
    scale = 0.55 + 0.055 * index
    counts = [max(1, round(c * scale)) for c in base]
    waves = []
    for k, count in enumerate(counts):
        wave = [(plain, None) for _ in range(count)]
        if armored and k >= 5:
            tier = 1 if k < 8 else max(armored)
            for _ in range(1 + (k - 5) // 3):
                wave.append((armored[tier], None))
        if k == len(counts) - 1 and index >= 9:
            wave.append(("gargantuar", None))
        waves.append(wave)
    return waves


def frontyard_type(ztype: str) -> str:
    """前院是新手世界：真实关卡里的跨世界/特种僵尸统一折成前院三件套 + 读报僵尸。"""
    zid = map_zombie(ztype, "frontyard")
    if zid in FRONTYARD_ALLOWED:
        return zid
    if "gargantuar" in ztype:
        return "buckethead"
    if re.search(r"_armor([2-9])", ztype):
        return "buckethead"
    if ztype.endswith("_armor1"):
        return "conehead"
    return "basic"


def rebalance_waves(wave_lists, cap: int, rng):
    """把总数超预算的关卡按比例裁剪；每波至少留 1 只，护甲比例大致保留。"""
    total = sum(len(w) for w in wave_lists)
    if total <= cap:
        return wave_lists, 0
    out = []
    for wave in wave_lists:
        wave = list(wave)
        keep = max(1, round(len(wave) * cap / total))
        if keep < len(wave):
            rng.shuffle(wave)
            wave = wave[:keep]
        out.append(wave)
    return out, total


def build_levels(src: Source, plants):
    plant_ids = {p["id"] for p in plants}
    size_by_index = {}
    levels = []
    for widx, (world_id, _zh, _en, prefix) in enumerate(WORLD_SPECS):
        deck_pool = WORLD_DECKS[world_id]
        for index in range(1, 11):
            rng = __import__("random").Random(SEED + widx * 100 + index)
            raw = load_level_waves(src, prefix, index)
            wave_lists, truncated, synthesized = None, 0, False
            if raw:
                wave_lists, truncated = compress_waves(raw, rng)
            if wave_lists is None:
                synthesized = True
                FALLBACK_LOG.append(
                    ("level_synth", f"{world_id}_{index} ({prefix}{index})"))
                wave_lists = synthesized_waves(world_id, index)
                truncated = sum(max(0, len(w) - MAX_ZOMBIES_PER_WAVE)
                                for w in wave_lists)
                wave_lists = [w[:MAX_ZOMBIES_PER_WAVE] for w in wave_lists]

            # 前院归一：真实 Modern Day 是终盘跨世界关卡，新手世界只留前院系僵尸，
            # 并按 FRONTYARD_BUDGET 裁剪总数（跨世界特种僵尸在 frontyard_type 里折叠）。
            original_zombies = 0
            if world_id == "frontyard":
                wave_lists = [[(frontyard_type(t), r) for (t, r) in w]
                              for w in wave_lists]
                if index <= 2:  # 前两天的教学坡道：铁桶降级成路障
                    wave_lists = [[("conehead" if t == "buckethead" else t, r)
                                   for (t, r) in w] for w in wave_lists]
                before = sum(len(w) for w in wave_lists)
                cap = FRONTYARD_BUDGET[index - 1]
                if before > cap:
                    wave_lists, _ = rebalance_waves(wave_lists, cap, rng)
                    original_zombies = before
                    FALLBACK_LOG.append(
                        ("level_rebalance",
                         f"frontyard_{index}: {before} → "
                         f"{sum(len(w) for w in wave_lists)}"))

            # 行号：真实数据带 Row 就保留；没有 Row 的在波内均衡分配（每行最多 ceil(n/5) 只）
            waves = []
            for wi, wave in enumerate(wave_lists):
                flag = (wi == 4) or (wi == len(wave_lists) - 1)
                missing = [i for i, (_t, r) in enumerate(wave) if r is None]
                if missing:
                    spread = [0, 1, 2, 3, 4] * ((len(missing) + 4) // 5)
                    rng.shuffle(spread)
                    for slot, i in zip(spread[:len(missing)], missing):
                        wave[i] = (wave[i][0], slot)
                zombies = [{"type": map_zombie(ztype, world_id), "row": row}
                           for ztype, row in wave]
                waves.append({
                    "delay": 18 if wi == 0 else (24 if flag else 20),
                    "flag": flag,
                    "zombies": zombies,
                })

            # 客串僵尸：放在最后一波，保证一定出场（见 GUEST_APPEARANCES 的说明）
            guests = []
            for src_type, guest in GUEST_APPEARANCES.get((world_id, index), []):
                for spawn in waves[-1]["zombies"]:
                    if spawn["type"] == src_type:
                        spawn["type"] = guest
                        guests.append(guest)
                        break

            # 卡组随世界与关卡推进：前院 3 张起，后面的世界一上来就给更多张
            size = 3 + widx + round(3 * (index - 1) / 9)
            size = max(3, min(len(deck_pool), 8, size))
            deck = deck_pool[:size]
            assert all(d in plant_ids for d in deck), (world_id, index, deck)
            size_by_index[f"{world_id}_{index}"] = size

            level = {
                "id": f"{world_id}_{index}",
                "world": world_id,
                "index": index,
                "title": f"第 {index} 天",
                "sun": WORLD_SUN[world_id][index - 1],
                "deck": deck,
                "waves": waves,
                "flags": sum(1 for w in waves if w["flag"]),
                "seed_bank": max(6, len(deck)),
            }
            if synthesized or truncated or original_zombies or guests:
                level["extra"] = {}
                if synthesized:
                    level["extra"]["synthesized"] = True
                if truncated:
                    level["extra"]["truncated_zombies"] = truncated
                if original_zombies:
                    level["extra"]["original_zombies"] = original_zombies
                if guests:
                    level["extra"]["guests"] = guests
            if truncated:
                FALLBACK_LOG.append(
                    ("wave_truncated", f"{world_id}_{index}: -{truncated}"))
            levels.append(level)
    return levels


# --------------------------------------------------------------------------- #
# almanac.json
# --------------------------------------------------------------------------- #

def build_almanac(src: Source, plants, zombies):
    out = {"plants": {}, "zombies": {}}
    for plant in plants:
        cid = plant["id"]
        alm = src.almanac_entry(src.plant_almanac, cid)
        intro = clean_text((alm.get("Introduction") or {}).get("zh"))
        chat = clean_text((alm.get("Chat") or {}).get("zh"))
        special = alm.get("Special") or []
        tip = first_sentences(chat, limit=2) if chat else ""
        if not tip and special:
            desc = (special[0].get("DESCRIPTION") or {})
            tip = first_sentences(desc.get("zh", ""), limit=2)
        out["plants"][cid] = {
            "desc": intro or plant["desc_zh"],
            "tip": tip or f"{plant['name_zh']}：花费 {plant['cost']} 阳光，"
                          f"冷却 {plant['cooldown']} 秒。",
        }
    for zombie in zombies:
        alm = src.almanac_entry(src.zombie_almanac,
                                zombie["extra"]["source_codename"])
        intro = clean_text((alm.get("Introduction") or {}).get("zh"))
        chat = clean_text((alm.get("Chat") or {}).get("zh"))
        out["zombies"][zombie["id"]] = {
            "desc": intro or zombie["desc_zh"],
            "tip": first_sentences(chat, limit=2) if chat
                   else f"{zombie['name_zh']}：生命 {zombie['hp']}。",
        }
    return out


# --------------------------------------------------------------------------- #
# 校验
# --------------------------------------------------------------------------- #

REQUIRED_PLANTS = ["peashooter", "sunflower", "wallnut", "potatomine", "snowpea",
                   "repeater", "bloomerang", "cabbagepult", "chomper", "fumeshroom"]
ALLOWED_BEHAVIORS = {"shoot", "lob", "produce", "wall", "instant", "chomp",
                     "fume", "mine", "support", "boomerang", "spike"}


def validate(src: Source, verbose: bool = True) -> int:
    problems = []
    plants = jload(CONTENT / "plants.json")
    zombies = jload(CONTENT / "zombies.json")
    worlds = jload(CONTENT / "worlds.json")
    almanac = jload(CONTENT / "almanac.json")
    level_files = sorted(LEVELS_DIR.glob("*.json"))
    levels = [jload(p) for p in level_files]

    def check(cond, msg):
        if not cond:
            problems.append(msg)

    # 数量
    check(len(plants) == 30, f"plants 数量 {len(plants)} ≠ 30")
    check(len(zombies) == 24, f"zombies 数量 {len(zombies)} ≠ 24")
    check(len(worlds) == 8, f"worlds 数量 {len(worlds)} ≠ 8")
    check(len(levels) == 80, f"levels 数量 {len(levels)} ≠ 80")

    plant_ids = [p["id"] for p in plants]
    zombie_ids = [z["id"] for z in zombies]
    check(len(set(plant_ids)) == 30, "plants id 有重复")
    check(len(set(zombie_ids)) == 24, "zombies id 有重复")
    for cid in REQUIRED_PLANTS:
        check(cid in plant_ids, f"缺少必备植物 {cid}")

    # 植物字段
    for p in plants:
        check(p["behavior"] in ALLOWED_BEHAVIORS,
              f"{p['id']} behavior 非法: {p['behavior']}")
        check(COOLDOWN_MIN <= p["cooldown"] <= COOLDOWN_MAX,
              f"{p['id']} cooldown 越界: {p['cooldown']}")
        check(p["cost"] >= 0, f"{p['id']} cost 为负")
        check(p["hp"] > 0, f"{p['id']} hp ≤ 0")
        check(p["art"] in src.resources, f"{p['id']} art 不存在: {p['art']}")
        check(bool(p["desc_zh"]), f"{p['id']} desc_zh 为空")
        rows = p.get("rows") or [0]
        check(all(-4 <= r <= 4 for r in rows), f"{p['id']} rows 越界: {rows}")

    # 僵尸字段
    for z in zombies:
        check(z["art"] in src.resources, f"{z['id']} art 不存在: {z['art']}")
        check(z["hp"] > 0, f"{z['id']} hp ≤ 0")
        check(z["speed"] > 0, f"{z['id']} speed ≤ 0")
        check(bool(z["desc_zh"]), f"{z['id']} desc_zh 为空")
        for armor in z.get("armor") or []:
            check(armor.get("art") in src.resources,
                  f"{z['id']} armor art 不存在: {armor.get('art')}")
            check(armor.get("hp", 0) > 0, f"{z['id']} armor hp ≤ 0")

    # 世界
    check([w["order"] for w in worlds] == list(range(1, 9)),
          "worlds order 不是 1..8")
    check(worlds[0]["unlock_after"] is None, "首个世界不应有 unlock_after")
    for world in worlds:
        check(world["levels"] == 10, f"{world['id']} levels ≠ 10")

    # 关卡
    seen = set()
    for level in levels:
        lid = level["id"]
        check(lid not in seen, f"level id 重复: {lid}")
        seen.add(lid)
        check(level["world"] in {w["id"] for w in worlds},
              f"{lid} world 不存在: {level['world']}")
        check(1 <= level["index"] <= 10, f"{lid} index 越界")
        check(len(level["deck"]) >= 3, f"{lid} deck 太少")
        for d in level["deck"]:
            check(d in plant_ids, f"{lid} deck 含未知植物 {d}")
        check(level["seed_bank"] >= len(level["deck"]),
              f"{lid} seed_bank < deck ({level['seed_bank']} < {len(level['deck'])})")
        check(bool(level["waves"]), f"{lid} 没有波次")
        check(sum(1 for w in level["waves"] if w["flag"]) == level["flags"],
              f"{lid} flags 计数不一致")
        check(5 <= len(level["waves"]) <= 10, f"{lid} 波数异常")
        for wi, wave in enumerate(level["waves"]):
            check(bool(wave["zombies"]), f"{lid} 第 {wi + 1} 波为空")
            check(10 <= wave["delay"] <= 30, f"{lid} 波次 delay 异常")
            for spawn in wave["zombies"]:
                check(spawn["type"] in zombie_ids,
                      f"{lid} 波次含未知僵尸 {spawn['type']}")
                check(0 <= spawn["row"] < ROWS,
                      f"{lid} 僵尸行号越界 {spawn['row']}")

    # 图鉴
    for cid in plant_ids:
        entry = (almanac.get("plants") or {}).get(cid) or {}
        check(bool(entry.get("desc")), f"almanac 缺植物 {cid}")
    for zid in zombie_ids:
        entry = (almanac.get("zombies") or {}).get(zid) or {}
        check(bool(entry.get("desc")), f"almanac 缺僵尸 {zid}")

    total_spawns = sum(len(w["zombies"]) for lv in levels for w in lv["waves"])
    max_wave = max((len(w["zombies"]) for lv in levels for w in lv["waves"]),
                   default=0)
    n_synth = sum(1 for lv in levels if (lv.get("extra") or {}).get("synthesized"))
    n_trunc = sum((lv.get("extra") or {}).get("truncated_zombies", 0)
                  for lv in levels)

    if verbose:
        print("=== PvZ2 SHUTTLE content 校验 ===")
        print(f"plants={len(plants)} zombies={len(zombies)} worlds={len(worlds)} "
              f"levels={len(levels)} almanac=({len(almanac['plants'])}/"
              f"{len(almanac['zombies'])})")
        print(f"波次总数={total_spawns} 单波最多={max_wave} "
              f"合成关卡={n_synth} 超上限裁剪={n_trunc}")
        print(f"资源清单 prefab={len(src.resources)} 条")
        if problems:
            print(f"校验失败 {len(problems)} 条：")
            for msg in problems[:40]:
                print("  -", msg)
            if len(problems) > 40:
                print(f"  ... 其余 {len(problems) - 40} 条省略")
            return 1
        print("校验通过 ✅")
    else:
        for msg in problems:
            print("FAIL:", msg)
    return 0 if not problems else 1


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #

def report_fallbacks():
    if not FALLBACK_LOG:
        print("fallback: 无")
        return
    grouped = {}
    for kind, detail in FALLBACK_LOG:
        grouped.setdefault(kind, []).append(detail)
    print(f"fallback {len(FALLBACK_LOG)} 条：")
    for kind, items in sorted(grouped.items()):
        print(f"  [{kind}] x{len(items)}")
        for item in items[:8]:
            print("    -", item)
        if len(items) > 8:
            print(f"    ... 其余 {len(items) - 8} 条省略")


def report_world_assets():
    """worlds.json 里的 map/lawn 是普通 PNG（不是 prefab），这里只做提示，不影响校验。"""
    missing = []
    for world_id, *_ in WORLD_SPECS:
        for kind in ("world", "lawn"):
            if not (ROOT / "assets" / kind / f"{world_id}.png").exists():
                missing.append(f"{kind}/{world_id}.png")
    if missing:
        print(f"美术资源提示：assets/ 下暂缺 {len(missing)} 个世界图 —— "
              + ", ".join(missing[:8]) + (" ..." if len(missing) > 8 else ""))
    else:
        print("美术资源提示：8 个世界的 map/lawn 图齐全")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="生成 PvZ2 SHUTTLE 内容数据")
    ap.add_argument("--gamedata", default=str(WORK_DEFAULT / "gamedata"),
                    help="拆包数据目录（默认 work/gamedata）")
    ap.add_argument("--work", default=str(WORK_DEFAULT),
                    help="work 目录（默认 PvZ2SHUTTLE/../work）")
    ap.add_argument("--check", action="store_true",
                    help="只校验现有 content/，不写盘")
    args = ap.parse_args(argv)

    src = Source(Path(args.gamedata), Path(args.work))
    FALLBACK_LOG.clear()

    if args.check:
        return validate(src)

    plants = build_plants(src)
    zombies = build_zombies(src)
    worlds = build_worlds(src)
    levels = build_levels(src, plants)
    almanac = build_almanac(src, plants, zombies)

    jdump(CONTENT / "plants.json", plants)
    jdump(CONTENT / "zombies.json", zombies)
    jdump(CONTENT / "worlds.json", worlds)
    jdump(CONTENT / "almanac.json", almanac)

    LEVELS_DIR.mkdir(parents=True, exist_ok=True)
    for old in LEVELS_DIR.glob("*.json"):
        old.unlink()
    for level in levels:
        jdump(LEVELS_DIR / f"{level['id']}.json", level)

    print("=== 已写入 content/ ===")
    print(f"plants.json {len(plants)} 株 / zombies.json {len(zombies)} 种 / "
          f"worlds.json {len(worlds)} 世界 / levels/ {len(levels)} 关 / "
          f"almanac.json {len(almanac['plants'])} 植物 + "
          f"{len(almanac['zombies'])} 僵尸")
    print("替换说明：")
    for old, new, why in SUBSTITUTIONS:
        print(f"  - {old} → {new}：{why}")
    report_fallbacks()
    report_world_assets()
    print()
    return validate(src)


if __name__ == "__main__":
    sys.exit(main())
