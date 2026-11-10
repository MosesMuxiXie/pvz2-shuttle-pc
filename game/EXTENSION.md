# 扩展契约（第 9 轮：完整化）

本轮目标：补齐 PvZ2 SHUTTLE 的关键玩法——植物养料、星章挑战、僵尸博士、迷你游戏（砸罐子）、
生存无尽、商店、禅境花园、植物选择（卡组编辑）以及第十二个世界「王朝」Plantagenet。

所有新增代码必须遵守本文件的接口。已有文件按“归属”分工，避免并发冲突。

## 一、数据文件（content/）

### worlds.json
在末尾追加：
```json
{"id":"plantagenet","name_zh":"王朝","name_en":"Plantagenet","order":12,
 "levels":10,"map":"world/plantagenet.png","lawn":"lawn/plantagenet.png",
 "unlock_after":"lunarrainbowmarket","desc_zh":"...","bg_tint":[200,180,150],
 "extra":{"lawn_mode":"full","night_levels":[4,5,9],"boss_level":10}}
```

### plants.json
新增 20 条，字段与现有完全一致：
`id,name_zh,name_en,cost,cooldown,hp,family,art,behavior,damage,interval,projectile,rows,pierce,tags,desc_zh,almanac_no,plantfood`
- behavior 只能取：shoot / lob / boomerang / produce / wall / instant / mine / fume / chomp / support
- art 路径形如 `art/plantagenet/iris.png`（静态立绘，资源来自 `Renders/Plantagenet` 等）

### zombies.json
新增 6 条，字段与现有一致；护甲僵尸用 `armor` 数组 + `extra.art_variants`：
`{"id","name_zh","name_en","hp","speed","eat_dps","armor":[],"behavior":"walk","art","armature":null,"cost","desc_zh","tags","extra"}`
护甲元素：`{"hp":370,"name":"路障","art":"art/plantagenet/royal_cone.png","metal":false}`

### levels/
新增 `plantagenet_1.json` … `plantagenet_10.json`，结构与现有 `content/levels/*.json` 相同：
`{"id","world":"plantagenet","index","title","sun","deck":[plant ids],"waves":[{"delay","flag","zombies":[{"type","row"}]}],"flags","seed_bank","extra":{...}}`
- 第 1–3 关白天、4–5 关夜晚（`extra.night=true`）、6–8 关白天、9 夜晚、10 为 Boss 关（`extra.boss=true`）。
- 波次 8–12 波，旗帜波在第 5 波与最后一波。

### stars.json（新）
按关卡 id 给出 3 个星章条件：
```json
{"frontyard_1":[{"type":"beat","value":0,"text_zh":"通关"},
                {"type":"mowers","value":5,"text_zh":"不损失小推车"},
                {"type":"kill","value":10,"text_zh":"消灭 10 只僵尸"}]}
```
可用 type：`beat`（通关）、`mowers`（剩余小推车≥value）、`kill`（击杀≥value）、
`plants_lost`（损失植物≤value）、`plants_max`（同时植物≤value）、`sun_max`（阳光消耗≤value）、
`sun_produced`（生产阳光≥value）、`time`（限时 value 秒内通关）、`score`（得分≥value）。
只给已存在的 110 关 + 新增 10 关；每关 3 条。数值参考 OBB 原始 StarChallenge 数据（work/expansion_scan.json、work/obb_packages）。

### minigames.json（新）
砸罐子模式，取 OBB 中 45 个 IsVasebreaker 关卡，映射到我们已有世界（frontyard/egypt/...）：
```json
{"vasebreaker":[{"id":"vase_frontyard_1","world":"frontyard","title":"前院·砸罐子 1",
  "sun":0,"vases":[[row,col,"zombie","basic"],[row,col,"plant","peashooter"],[row,col,"sun",25]]}]}
```
- 棋盘 5 行 × 9 列，行 0–4、列 0–8；vases 只放在列 2–7 且避开中央斜线。
- 依据 OBB 的 `MinColumnIndex/MaxColumnIndex/GridSquareExcludelist/Vases` 生成；僵尸类型映射到现有 48 僵尸 id，植物映射到现有 42 植物 id；每关 14–24 个罐子。

### bosses.json（新）
```json
{"bosses":[{"id":"boss_chinesegarden","world":"chinesegarden","title":"僵尸博士·戏曲毁灭者",
  "hp":9000,"minions":["garden_zombie","garden_cone"],"art":"art/chinesegarden/zombot.png","reward":250}]}
```
- 至少 7 个：egypt（夜晚）、pirate、beach、cowboy、kongfu、chinesegarden、plantagenet。
- `art` 指向静态立绘：chinesegarden 用 `Renders/Chinese Garden/Part 1/Zombot Opera Wrecker 1598 (Stage).png`；
  其他世界若无 Boss 立绘，用 `zombies/gargantuar` 的 DB art 路径（`zombies/GargantuarZOMBIE`），
  渲染端会按 HP 放大并染世界色。

### shop.json（新）
```json
{"items":[{"id":"pf_pack","name_zh":"植物养料 ×3","desc_zh":"...","price":150,"kind":"plantfood","value":3},
          {"id":"sun_start","name_zh":"开局阳光 +150","desc_zh":"...","price":400,"kind":"sun_start","value":150},
          {"id":"mower_repair","name_zh":"补充小推车","desc_zh":"...","price":250,"kind":"mower","value":1},
          {"id":"seed_iris","name_zh":"种子包·鸢尾","desc_zh":"解锁鸢尾","price":600,"kind":"plant","value":"iris"}]}
```
植物种子包覆盖 20 个新植物；价格 500–900。

## 二、存档（game/save.py）
新增字段（缺省容错）：
```python
stars: dict[str, list[bool]]      # 关卡 id -> [3 星]
unlocked_plants: list[str]        # 新植物 id（默认空；前 42 个始终可用）
plantfood: int                    # 库存养料
garden: dict                      # {"pots":[{...}], "last": epoch}
best_survival: dict               # {"world":..., "wave":0, "score":0}
```

## 三、引擎模式（game/engine/modes.py，由 Lead 实现）
```python
class VasebreakerSession:
    def __init__(self, app, mg, on_finish=None)
    # attrs: status("playing"/"won"/"lost"), sun, vases, plants, zombies, suns, message, time
    # methods: update(dt), draw(surf), handle_mouse_down(pos)

class SurvivalSession:  # 继承 LevelSession
    def __init__(self, app, world_id, on_finish=None)
    # attrs 额外：score, endless_wave, spawned_total
    # on_finish(won=False, score=score) 于失败/退出时调用

class BossSession:  # 继承 LevelSession
    def __init__(self, app, world_id, boss_def, on_finish=None)
    # attrs 额外：boss, boss_hp, boss_max_hp, boss_phase
    # on_finish(True) 当 boss 死亡
```

## 四、界面（game/screens/，由 UI 代理实现）
所有 Screen 均有 `name`、`enter()`、`update(dt)`、`draw(surf)`、`handle(event)`，由 `app.switch("...")` 进入。

- `seedchooser.py`：`SeedChooserScreen(app, world_id, level_index, slots)`；网格展示所有可用植物
  （基础 42 + save.unlocked_plants），点选/取消，`app.ui_result = [ids]` 后 `app.switch("level")`。
- `modes.py`：`ModeHubScreen`（name "modes"）：入口按钮 砸罐子 / 生存无尽 / 僵尸博士 / 商店 / 禅境花园 / 返回。
- `minigame.py`：`VasebreakerHubScreen`（列表，读 content/minigames.json）+ `VasebreakerScreen`（包装 VasebreakerSession，暂停/结算）。
- `survival.py`：`SurvivalHubScreen`（选世界）+ `SurvivalScreen`（包装 SurvivalSession，显示分数）。
- `boss.py`：`BossHubScreen` + `BossScreen`（包装 BossSession，Boss 血条）。
- `shop.py`：`ShopScreen`（金币、商品网格、购买写 save）。
- `garden.py`：`GardenScreen`（8 个花盆：种下已解锁植物、浇水、成熟收金币；基于 save.garden，离线进度按时间计算）。

## 五、文件归属（并发写禁止越界）
- Lead：`game/engine/entities.py`、`game/engine/level.py`、`game/engine/combat.py`、`game/engine/modes.py`、
  `game/app.py`、`game/save.py`、`game/screens/level_screen.py`、`game/screens/worldmap.py`、`game/screens/menu.py`、
  `content/stars.json` 的**接入**、测试与打包。
- Content 代理：`content/plants.json`、`content/zombies.json`、`content/worlds.json`、`content/levels/plantagenet_*.json`、
  `content/minigames.json`、`content/bosses.json`、`content/shop.json`、`content/stars.json`（只生成，不改代码）、
  `tools/add_plantagenet.py`、`tools/build_meta_content.py`、`assets/art/plantagenet/*`、`assets/lawn/plantagenet*.png`、
  `assets/world/plantagenet.png`。
- UI 代理：`game/screens/seedchooser.py`、`game/screens/modes.py`、`game/screens/minigame.py`、`game/screens/survival.py`、
  `game/screens/boss.py`、`game/screens/shop.py`、`game/screens/garden.py`、`tests/test_new_screens.py`。
- 其他文件禁止修改。

## 六、渲染约定
- 静态立绘用 `assets.static_sprite(key, target_h)`（已实现），key 为 `art/...` 相对路径（不带 assets/）。
- 新世界草坪：`lawn_mode:"full"` 时 `assets/lawn/plantagenet.png` 铺满 1280×720（见 level_screen）。
- 夜晚关卡：`level_screen` 依据 `level.extra.night` 叠一层深蓝半透明（Lead 实现）。
