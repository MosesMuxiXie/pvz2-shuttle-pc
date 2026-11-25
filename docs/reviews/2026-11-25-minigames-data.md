# 小游戏与变体玩法数据（460.9）— 判定依据、覆盖与缺口

产物：`native/generated/minigames.json`（1,222,781 字节，sha256 `0bb72dee1448ac319992d405c6ea3fa32e63cf36cb7e4d91e2287aed4059d86d`）
编译器：`tools/contentc/minigames.py`（纯 stdlib）
测试：`tools/tests/test_minigames.py`（24 例）
数据源：`work/obb_packages`（= 460.9 的 PACKAGES 解码）+ `content/levels/*.json`（只提供 level id 身份）

---

## 0. 结论摘要

| 问题 | 结论 |
| --- | --- |
| 1809 关里有多少关挂了玩法模块 | **813 关**（`counts.levels`），其余 996 关只有常规模块 |
| 分出多少个 kind | **20 个**：16 个 `minigame` + 4 个 `variant` |
| 玩法类关卡数 | `minigame` **209 关**、`variant` **673 关**；其中 69 关两类兼具，140 关只有 minigame，604 关只有 variant |
| 任务说的「45 关」是什么 | 是 `content/levels` 的 `extra.special = ["IsVasebreaker"]` 的 **45 关**（= `LevelDefinition.IsVasebreaker` 为真的关卡）。砸罐子 kind 实际覆盖 **47 关**，多出的 `pirate_41` / `plantagenet_18` 没有 `IsVasebreaker` 键但仍挂了 `VaseBreakerProps`，见 §3 |
| 哪些玩法原版**没有**独立模块 | `ZombieChicken`（僵尸鸡）——2116 个包里没有任何 Modules 别名含 Chicken，只有僵尸属性对象；详见 §5。星章挑战（`ChallengeModule`，924 关）不是玩法，未计入任何 kind |
| 判 kind 的唯一凭据 | `LevelDefinition.Modules[]` 里的**模块别名**。参数对象存在不等于玩法存在（`BowlingMinigameProperties` 有 28 个对象 / 27 个包，`BowlingBulbMinigame` 只挂 15 关） |

---

## 1. 口径（R01..R09）

- **R01 kind 只由模块别名判定。** 参数对象（`*MinigameProperties` / `*ChallengeProperties` / `RailcartProperties`）只用来补 `params`，绝不反过来创建 kind。反例见 `BowlingMinigameProperties`：28 个对象分布在 27 个包，其中 12 个包根本没挂 `BowlingBulbMinigame`（纯铁轨关），按参数对象判会把保龄从 15 关虚报成 27 关。
- **R02 只有「锚点模块」创建 kind，辅助模块只记录。** `JoustModule` 是锚点，`JoustZombieWinCondition` / `JoustDarkMowers` / `JoustPointOfLoss` 是辅助。若不分开，joust 会从 4 关膨胀到 6 关（`plantagenet_22` / `plantagenet_23` 只挂了辅助模块）。
- **R03 星章挑战不算玩法。** `ChallengeModule` 覆盖 924 关，只登记在 `counts.excluded`，不生成 kind，也不用它去凑「小游戏 45 关」。
- **R04 `params` 原样收录**该关包内属于该 kind 的参数对象 objdata（键 = objclass，值 = 对象列表），不改字段名、不补默认值。
- **R05 kind 分两类**：`minigame`（自带模块、改写整局规则）与 `variant`（在普通关之上叠一层规则）。分类写死在注册表 `KINDS` 里，不从字段猜。
- **R06 level id 来自 `content/levels/*.json` 的 `extra.package`。** 映射不到的关卡包进 `unknowns`（本次为 0）。
- **R07 `extra.rail` / `extra.vasebreaker` / `extra.special` 只做交叉核对**，差异写进 `crossChecks` 与 `unknowns`，两边都保留，不做「以谁为准」的静默取舍。
- **R08 找不到模块的玩法进 `unknowns`**，并写清它到底是什么（僵尸属性 / 音乐开关 / 目标层），不用星章挑战硬凑。
- **R09 确定性**：`GENERATED` 固定日期、键全 `sort_keys`、LF 换行、`--check` 逐字节比对。

---

## 2. 每个 kind 的判定依据与覆盖

`minigame`（16 个，209 关）

| kind | 中文 | 锚点模块（任一命中即算） | 参数对象（原样收录） | 关卡 | 例 |
| --- | --- | --- | --- | --- | --- |
| `vasebreaker` | 砸罐子 | `VaseBreakerArcade` / `VaseBreakerProps` / `TestVaseBreaker` | `VaseBreakerPresetProperties`, `VaseBreakerEndlessProperties` | **47** | `beach_69` (pkg_0290) |
| `laststand` | 背水一战 | `LastStand` | `LastStandMinigameProperties` | **73** | `beach_17` (pkg_0329) |
| `beghouled` | 三消 | `BeghouledArcade` / `BeghouledProps` | `BeghouledPresetProperties`, `BeghouledZombieSpawnerProperties`, `BeghouledSeedBankProperties` | **11** | `modern_32` (pkg_0470) |
| `whackazombie` | 打地鼠 | `WhackAZombieMinigame` | `MinigameWhackAZombieModuleProperties`, `SpawnWhackAZombiesProps` | **1** | `beach_20` (pkg_0582) |
| `joust` | 竞技场 | `JoustModule` | `JoustGameModuleProperties` | **4** | `egypt_8` (pkg_0507) |
| `bowling` | 保龄球 | `BowlingBulbMinigame` | `BowlingMinigameProperties` | **15** | `beach_15` (pkg_0327) |
| `column` | 列攻 | `ColumnMinigame` | `ColumnMinigameProperties` | **8** | `carnival_24` (pkg_0246) |
| `cannon` | 炮击 | `CannonMinigame` | `CannonMinigameProperties` | **8** | `egypt_69` (pkg_0763) |
| `invisighoul` | 隐形僵尸 | `InvisighoulMinigame` | `InvisighoulMinigameProperties` | **8** | `cowboy_11` (pkg_0506) |
| `cowboy` | 西部小游戏 | `CowboyMinigame` | `CowboyMinigameProperties` | **10** | `carnival_84` (pkg_0356) |
| `bigtrouble` | 缩小僵尸 | `BigTroubleLittleZombieMinigameModule` | `BigTroubleLittleZombieMinigameProperties` | **6** | `chinesegarden_62` (pkg_1102) |
| `camel` | 骆驼牌 | `CamelMinigame` | `CamelMinigameProperties` | **2** | `egypt_16` (pkg_1231) |
| `deathexplosion` | 死亡爆炸 | `DeathExplosionMiniGameModule` | `DeathExplosionMiniGameModuleProperties` | **17** | `lunarrainbowmarket_33` (pkg_0813) |
| `sproutplanting` | 种苗 | `SproutPlanting` | `SproutPlantingMinigameProperties` | **2** | `beach_5` (pkg_0567) |
| `seeingstars` | 踩星 | `SeeingStarsModule` | `SeeingStarsModuleProperties` | **3** | `carnival_4` (pkg_0774) |
| `bonuschallenge` | 奖励挑战 | `BonusChallengeModule` | `BonusChallengeModuleProperties` | **2** | `mausoleum_28` (pkg_0548) |

`variant`（4 个，673 关）

| kind | 中文 | 锚点模块 | 参数对象 | 关卡 | 例 |
| --- | --- | --- | --- | --- | --- |
| `rail` | 铁轨/矿车 | `Rails` `Rail` `Railcart` `Railcart1` `MountingRails` `CowboyRails` `BeachRails` `EgyptRails` `FutureRails` `TutorialRails` `WorldcupRails` | `RailcartProperties` | **196** | `beach_10` (pkg_0336) |
| `conveyor` | 传送带出牌 | `ConveyorBelt` | `ConveyorSeedBankProperties` | **332** | `beach_12` (pkg_0338) |
| `tide` | 潮汐 | `Tide` | `TideProperties` | **77** | `beach_1` (pkg_0325) |
| `protecttheplant` | 保护植物 | `ProtectThePlant` | `ProtectThePlantChallengeProperties` | **197** | `beach_14` (pkg_0326) |

辅助模块（只记录在 `relatedModules`，不创建 kind）：`LastStandSeedBank`、`BeghouledIntro` / `BeghouledRiftIntro` / `BeghouledSeedBank`、`WhackPuddles`、`JoustPointOfLoss` / `JoustZombieWinCondition` / `JoustDarkMowers`、`Column`、`InvisibleBrainEater`、`CowboyConveyor`、`PirateCannonTutorial`、`Conveyor`、`ProtectThePlant1` / `ProtectPeanutLevelBasicModule`。

判定依据举例（可直接对照产物）：

- `beach_69`（pkg_0290）`Modules` 含 `VaseBreakerArcade` / `VaseBreakerProps` / `Tide` → `kinds = ["vasebreaker","tide"]`；`params.vasebreaker.VaseBreakerPresetProperties[0]` 的 `MinColumnIndex 2`、`MaxColumnIndex 8`、`Vases` 12 条。
- `egypt_8`（pkg_0507）`Modules` 含 `JoustModule` / `JoustPointOfLoss` / `LastStand` → `kinds = ["laststand","joust"]`；`JoustGameModuleProperties[0] = {TimeLimit: 180.0, SuggestedLoadout: "SunBasic"}`。
- `modern_32`（pkg_0470）`Modules` 含 `BeghouledIntro` / `BeghouledSeedBank` / `BeghouledArcade` / `BeghouledProps` → `kinds = ["beghouled"]`；`BeghouledPresetProperties[0].MatchesToWin = 1000000`、`BeghouledSeedBankProperties[0].SelectionMethod = "beghouled"`。
- `beach_20`（pkg_0582）`Modules` 含 `WhackAZombieMinigame` / `WhackPuddles` → 唯一一关打地鼠；`HammerTapsToDecay = [60,40,20]`。

---

## 3. 与 `content/levels` 的交叉核对

| 项 | pack 侧 | content 侧 | 一致 | 差异 |
| --- | --- | --- | --- | --- |
| 砸罐子 | 47 | `extra.vasebreaker` 47 | **47 / 47** | 无 |
| `IsVasebreaker` | 45（`LevelDefinition` 有该键） | `extra.special=["IsVasebreaker"]` 45 | **45 / 45** | 45 关全部被 vasebreaker kind 覆盖 |
| 铁轨 | 196 | `extra.rail` 192 | 189 | pack 多 7、content 多 3 |

- 砸罐子的 47 = 45 个 `IsVasebreaker` + `pirate_41`(pkg_1557) + `plantagenet_18`(pkg_1576)。这两关没有 `IsVasebreaker` 键，但确实挂了 `VaseBreakerProps`，罐表也在（分别 1 条 35 僵尸罐 / 1 条）。所以「45 关」是 `IsVasebreaker` 的口径，「47 关」是模块口径，两者都对，但回答不同的问题。
- 铁轨的差异是真实的、双向的，不是解析漏项：
  - **只有 content 标了 rail（3 关）**：`cowboy_41`(pkg_0435)、`cowboy_42`(pkg_0466)、`kongfu_44`(pkg_1405)。这三关包里没有 `*Rails` / `Railcart` 模块；`cowboy_41` / `cowboy_42` 走的是 `DangerRoomRailcartDesigner`（危险房自动布轨），`kongfu_44` 只有 `minecarts` 数据。
  - **只有 pack 挂了铁轨模块（7 关）**：`egypt_46`、`fairy_31`、`frontyard_98`、`future_66`、`future_69`、`future_70`、`plantagenet_47`。这些关 `extra.rail=false`，其中 `future_69` / `egypt_46` 用的是 `CowboyRails` 别名但没配 minecart 坐标。
- 两边差异原样进了 `crossChecks.rail.packOnly` / `contentOnly` 与 `unknowns`（见 §5），没有静默取某一侧。

---

## 4. 多 kind 关卡

- 181 关同时属于 ≥2 个 kind；最多 4 个：`iceage_69`（rail + bowling + conveyor + protecttheplant）、`kongfu_83`（vasebreaker + rail + laststand + protecttheplant）。
- 高频组合：`conveyor` 266 关单独、`protecttheplant` 116 关单独、`rail` 79 关单独、`rail+protecttheplant` 51 关、`laststand` 49 关单独、`tide` 36 关单独、`vasebreaker` 35 关单独。
- 因此「小游戏关卡数」必须说明口径：按关去重是 813，按 kind 出现次数是 **1019**。

---

## 5. 未知 / 原版没有独立模块的玩法

完整清单在产物 `unknowns[]`，共 3 行：

1. `kind-without-module: chicken` —— **僵尸鸡没有独立模块**。2116 个包里没有任何 `Modules` 别名含 `Chicken`（`--needle chicken` 只命中僵尸属性对象：`ZombieChickenProps` 在 pkg_2112、`ZombieChickenFarmerProps` 14 个对象 / 8 个包）。它不是小游戏关卡，是僵尸类型 + 农场主属性，所以 `levels: 0`。
2. `content-rail-without-module` —— `cowboy_41`、`cowboy_42`、`kongfu_44`（见 §3）。
3. `rail-module-without-content-rail` —— `egypt_46`、`fairy_31`、`frontyard_98`、`future_66`、`future_69`、`future_70`、`plantagenet_47`（见 §3）。

另外两类**已知但不算玩法**的模块，登记在 `counts.excluded` 而不是 `unknowns`：

| 模块 | 关卡 | 为什么不算 |
| --- | --- | --- |
| `ChallengeModule` | 924 | 星章挑战目标层（三星任务），覆盖一半以上的关卡，是关卡目标系统不是玩法模式 |
| `PlantagenetMiniGameMusic` / `RenaiMiniGameMusic` / `SteamMiniGameMusic` | 各 1 | 只开关小游戏 BGM，没有任何规则字段 |

**「45 关小游戏」这个说法要按口径读**：`extra.special` 的 45 关只是 `IsVasebreaker` 的标记集合，并不代表全部小游戏；本表的小游戏（`minigame` 类）去重后有 209 关。

---

## 6. 产物结构

```jsonc
{
  "format": "pvz2-shuttle/minigames@1",
  "generated": "2026-11-25",
  "levels": {
    "beach_69": {
      "package": "pkg_0290",
      "levelFile": "beach_69",
      "kinds": ["vasebreaker", "tide"],          // 按注册表顺序，非字母序
      "categories": ["minigame", "variant"],
      "modules": ["StandardIntro", "VaseBreakerArcade", ...],   // 该关全部模块，原样
      "relatedModules": ["..."],                 // 同族但不创建 kind 的模块
      "params": {                                // objclass -> 对象列表（objdata 原样）
        "vasebreaker": {"VaseBreakerPresetProperties": [{"MinColumnIndex": 2, ...}]},
        "tide": {"TideProperties": [{"StartingWaveLocation": 4}]}
      },
      "extra": {"rail": false, "vasebreaker": true, "special": [], "minecarts": 0}
    }
  },
  "counts": {"levels": 813, "levelsScanned": 1809, "byKind": {...}, "byCategory": {...}, "excluded": {...}},
  "crossChecks": {"rail": {...}, "vasebreaker": {...}, "special": {...}},
  "unknowns": [...],
  "sources": {...}
}
```

引擎侧最小用法：`levels[<id>].kinds` 决定走哪套规则；`params[kind][objclass][0]` 取该玩法的数值（罐表、铁轨坐标、保龄犯规线、Last Stand 起始阳光…）；`modules` 保留原始模块列表，便于以后接新模块时不必重编译。

---

## 7. 复现命令

```powershell
# 生成产物
python tools/contentc/minigames.py

# 逐字节自检（过期 / 含 CRLF / 计数不自洽都会 exit 1）
python tools/contentc/minigames.py --check

# 单元测试（24 例）
python -m unittest tools.tests.test_minigames -v

# 回答「某个玩法到底有没有模块」这类问题
python tools/contentc/minigames.py -n chicken      # 2116 包内 objclass/文件名命中
python tools/contentc/minigames.py -n vasebreaker
```

`--check` 当前输出：

```
minigames levels=813 minigame=209 variant=673 kinds=20
           byKind: vasebreaker=47 rail=196 laststand=73 beghouled=11 whackazombie=1 joust=4 bowling=15 column=8 cannon=8 invisighoul=8 cowboy=10 bigtrouble=6 camel=2 deathexplosion=17 sproutplanting=2 seeingstars=3 bonuschallenge=2 conveyor=332 tide=77 protecttheplant=197
OK
```

---

## 8. 诚实边界

1. **判定只看模块名**。如果某个玩法在数据里用了一个我没想到的别名，它会被 `unregistered-module` 抓出来（当前为空），但别名与玩法语义的对应关系仍是我按名称 + 参数对象推的，不是官方声明。
2. **`extra.rail` 与模块口径不一致的 10 关不强行对齐**。我保留了两侧原值；以谁为准取决于引擎要不要「有轨无车」或「有车数据无模块」这两种情况。
3. **`params` 是原样 objdata**，没有解释字段语义（例如 `BowlingFoulLine` 是第几行、`GridSquareExcludelist` 的单位）。这些留给接线时按字段名读，本表不做二次加工，避免把猜测写进数据。
4. **`ChallengeModule` 的 924 关没有细分**成各个星章挑战类型（那是 `StarChallenge*Props` 的事，另有 13 个类，共 2064 个对象）。本表只声明它「不是玩法」，不冒充已解析。
5. **`joust` 只算 4 关**（有 `JoustModule` 的），`plantagenet_22` / `plantagenet_23` 有 `JoustZombieWinCondition` / `JoustDarkMowers` 但没有锚点模块，因此不在这 4 关里，只在它们所属关的 `relatedModules` 里出现。
6. **僵尸鸡的结论是「没有模块」而不是「没有数据」**：相关僵尸属性对象确实存在，缺的是关卡级玩法模块，所以它进 `unknowns` 而不是 `levels`。


