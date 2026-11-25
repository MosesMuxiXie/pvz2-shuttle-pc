# Boss 数据编译报告（pack → bosses_from_pack.json）

由 `tools/contentc/bosses.py` 生成；数据源 `work/obb_packages`（2117 个文件），产物 `native/generated/bosses_from_pack.json`。

```
python tools/contentc/bosses.py            # 写 json + 本报告
python tools/contentc/bosses.py --check    # 校验已落盘文件
```

## 0. 计数

| 项 | 值 | 说明 |
|---|---:|---|
| 编译出的 boss（distinct mech） | 50 | 每个 `ZombieType.TypeName` 一条 |
| 战场放置（battle module 行） | 75 | 同一 mech 可被多个关卡复用 |
| 阶段总数（可上场，本表采用） | 155 | 50 个被 battle module 放置的 mech 之和 |
| 阶段（按 alias 去重） | 227 | 同一 props 在多个关卡包里重复定义时只算一次 |
| 阶段（occurrence 求和） | 258 | s5 盘点报告里的 258 就是这个口径 |
| 阶段表对象 / 其中有 Stages | 168 / 82 | `Zombie*Zomboss*Mech*Props` |
| ZombieType 行 | 1127 | `pkg_2115_ZombieType.json` 全表 |
| 动作引用 / 去重 | 634 / 355 | 阶段 `Actions[]` 展开 |
| 动作类 | 34 | 每种 `*ActionDefinition` 一类 |
| 未解析动作 | 0 | 引用了但包内找不到对象 |
| 无阶段 boss | 1 | 见 §4b 的悬空引用 |
| 有阶段表但未被放置的 mech | 24 | Battlez/Rift 变体，无 spawn，见 §4c |

**三个阶段总数为什么不同**（都保留，不取整也不隐藏）：

- `155`（本表采用）：只有被 `ZombossBattleModuleProperties` 放进关卡的 mech 才算，引擎能真正取到的就是这一批。
- `227`（按 alias 去重）：`@CurrentLevel` 变体（如 `ZombieZombossMechAddedBeach`）会在每个引用它的关卡包里重新定义一份，去重后才是「有多少张阶段表」。
- `258`（occurrence 求和）：逐对象累加，同一张表被重复定义就重复计数 —— `docs/reviews/2026-11-20-s5-data-inventory.md` 里的 258 是这一口径，两者对得上，但 258 不等于可上场阶段数。

## 1. 哪些是 pack 原值、哪些是推断

**pack 原值（逐字段复制，未做任何归一化）**

| 字段 | 来源 |
|---|---|
| `id` | `ZombieType.TypeName` 原字符串（如 `zombossmech_egypt`），不改写 |
| `className` / `popAnim` / `animRig` / `displayTypeName` | `ZombieClass` / `PopAnim` / `AnimRigClass` / `DisplayTypeName` |
| `propsName` / `propsSheet` / `propsPkg` | `Properties = RTID(<name>@<sheet>)` 的两段 + 对象所在包 |
| `stages[].hitPoints` / `stunSeconds` / `animRate` | `HitPoints` / `StunTime` / `AnimRateModifier` |
| `stages[].idleSeconds` | `IdleTime.Min` / `IdleTime.Max` |
| `stages[].damageIndex` | `DamageIndexFull` / `DamageIndexHalf` |
| `stages[].actions[].rtid` / `.type` / `.fields` | 阶段 `Actions[]` 的 RTID、动作对象的 objclass、动作对象**整份** objdata |
| `spawn.*` | `ReservedColumnCount` / `ZombossSpawnGridPosition.mX,mY` / `ZombossDeathRow,Column` |
| `spawn.module` / `moduleObjclass` / `stageModule` | 模块所在包、模块类名、同包 LevelDefinition 的 `StageModule` |
| `stageSelection` | `ZombossStageCount` / `ZombossStartStageIndex`（缺省为 null） |

**推断项（每条都可人工复核）**

| 推断 | 规则 | 复核方式 |
|---|---|---|
| `world` | 关卡 `StageModule` 别名按前缀表 `s5scan.STAGE_WORLD_HINTS` 匹配；匹配不到写 `unknown:<stage>` 并保留 | 见 §3 的 stage→world 表；下方 §4 列全部 unknown 行 |
| `spawn`（主放置） | ① 有已知世界就不选 `unknown:*` ② 优先 stage 名含 `boss` 的放置 ③ 再按包名排序 | 每条的 `placements` 都完整列出，可与 `spawn.module` 对照 |
| `worlds` | 该 mech 所有放置的世界去重排序 | 长度 >1 的 mech 列在 §2 末尾（跨世界复用） |
| `resolution` | 在 `pkg_2115_ZombieType` 找到 → `zombietype`；找不到 → `alias-guess`（用 `Zombie`+CamelCase 猜 props 名） | 全表 `resolution` 计数见下 |

`resolution` 分布：`alias-guess`=1、`zombietype`=49

**明确不采信**：`content/bosses.json` 的 HP（8000 起每条 +200 的等差，26 条 phases 完全相同）——只用于 §5 的对比，不作为任何字段来源。

## 2. 每世界一行

| 世界 | boss id | 阶段数 | 各阶段 HP | spawn(cols / gridX,Y) | 召唤类动作 | Fire 动作 | 来源 pkg |
|---|---|---:|---|---|---:|---:|---|
| kongfu | `kongfu_zomboss_blade` | 3 | 15000 / 25000 / 35000 | 2 / 6,3 | 6 | 0 | `pkg_1593_LevelDefinition` |
| chinesegarden | `zombossmech_added_beach` | 3 | 2000 / 45000 / 50000 | 3 / 6,3 | 5 | 0 | `pkg_1005_LevelDefinition` |
| chinesegarden | `zombossmech_added_chinesegarden` | 3 | 12500 / 18000 / 22000 | 3 / 6,4 | 7 | 2 | `pkg_1107_LevelDefinition` |
| unknown:ChildStage | `zombossmech_added_circus` | 3 | 20000 / 35000 / 50000 | 2 / 6,3 | 11 | 0 | `pkg_1041_LevelDefinition` |
| plantagenet | `zombossmech_added_cowboy` | 3 | 15000 / 30000 / 50000 | 2 / 6,3 | 4 | 2 | `pkg_1017_LevelDefinition` |
| lunarrainbowmarket | `zombossmech_added_dark` | 3 | 10000 / 15000 / 20000 | 3 / 5,3 | 5 | 0 | `pkg_0825_LevelDefinition` |
| fairy | `zombossmech_added_fairytale` | 3 | 7000 / 11000 / 12000 | 3 / 5,3 | 3 | 0 | `pkg_1029_LevelDefinition` |
| lostcity | `zombossmech_added_lostcity` | 3 | 6000 / 10000 / 10000 | 3 / 6,3 | 0 | 0 | `pkg_0651_LevelDefinition` |
| lunarrainbowmarket | `zombossmech_added_market` | 3 | 8000 / 12000 / 18000 | 2 / 6,3 | 0 | 2 | `pkg_0256_LevelDefinition` |
| mausoleum | `zombossmech_added_mausoleum` | 3 | 8000 / 10000 / 15000 | 3 / 6,3 | 3 | 0 | `pkg_1119_LevelDefinition` |
| rift | `zombossmech_added_roman` | 3 | 6000 / 7500 / 9000 | 3 / 6,3 | 3 | 3 | `pkg_1212_LevelDefinition` |
| roof | `zombossmech_adventure` | 5 | 5000 / 6000 / 7500 / 8000 / 8000 | 3 / 6,4 | 11 | 0 | `pkg_2047_LevelDefinition` |
| roof | `zombossmech_adventure2` | 3 | 7000 / 8500 / 10000 | 3 / 6,4 | 6 | 0 | `pkg_2041_LevelDefinition` |
| beach | `zombossmech_beach` | 3 | 10000 / 14000 / 18000 | 3 / 6,3 | 3 | 0 | `pkg_0331_LevelDefinition` |
| chinesegarden | `zombossmech_chinesegarden` | 3 | 6000 / 8000 / 9000 | 3 / 6,4 | 3 | 2 | `pkg_0390_LevelDefinition` |
| carnival | `zombossmech_circus` | 3 | 6300 / 14514 / 19191 | 3 / 6,4 | 6 | 0 | `pkg_0366_LevelDefinition` |
| cowboy | `zombossmech_cowboy` | 3 | 6500 / 10000 / 9000 | 2 / 6,3 | 3 | 3 | `pkg_0426_LevelDefinition` |
| cowboy | `zombossmech_cowboy2` | 3 | 8000 / 12000 / 10000 | 2 / 6,3 | 3 | 3 | `pkg_1173_LevelDefinition` |
| renai | `zombossmech_dark` | 3 | 7000 / 9000 / 11000 | 3 / 5,3 | 3 | 0 | `pkg_1204_LevelDefinition` |
| renai | `zombossmech_dark2` | 3 | 7000 / 9000 / 11000 | 3 / 5,3 | 3 | 0 | `pkg_1794_LevelDefinition` |
| dino | `zombossmech_dino3` | 4 | 10000 / 8000 / 7000 / 7000 | 3 / 6,4 | 4 | 3 | `pkg_1181_LevelDefinition` |
| egypt | `zombossmech_egypt` | 3 | 4000 / 8000 / 6500 | 2 / 6,3 | 3 | 3 | `pkg_0562_LevelDefinition` |
| egypt | `zombossmech_egypt2` | 3 | 8000 / 16000 / 15000 | 2 / 6,3 | 3 | 3 | `pkg_0613_LevelDefinition` |
| rift | `zombossmech_egypt_rift` ⚠无 props | 0 | — | 2 / 6,3 | 0 | 0 | `pkg_0576_LevelDefinition` |
| eighties | `zombossmech_eighties` | 5 | 4500 / 5000 / 5500 / 6000 / 7000 | 2 / 6,3 | 7 | 0 | `pkg_0588_LevelDefinition` |
| eighties | `zombossmech_eighties2` | 5 | 4000 / 4000 / 5000 / 5000 / 9000 | 3 / 6,4 | 8 | 0 | `pkg_0641_LevelDefinition` |
| fairy | `zombossmech_fairytale` | 3 | 7000 / 9000 / 10000 | 3 / 5,3 | 3 | 0 | `pkg_1252_LevelDefinition` |
| fairy | `zombossmech_fairytale_head1` | 1 | 2147483647 | 3 / 5,3 | 0 | 0 | `pkg_1029_LevelDefinition` |
| fairy | `zombossmech_fairytale_head2` | 1 | 2147483647 | 3 / 5,3 | 0 | 0 | `pkg_1029_LevelDefinition` |
| future | `zombossmech_future` | 3 | 13000 / 14410 / 22000 | 1 / 7,3 | 3 | 3 | `pkg_0500_LevelDefinition` |
| lunarrainbowmarket | `zombossmech_future2` | 3 | 16000 / 26000 / 125 | 3 / 6,4 | 5 | 3 | `pkg_0855_LevelDefinition` |
| heian | `zombossmech_heian` | 3 | 7500 / 9750 / 12000 | 3 / 0,3 | 3 | 3 | `pkg_1328_LevelDefinition` |
| iceage | `zombossmech_iceage` | 3 | 5000 / 4000 / 4000 | 3 / 6,3 | 0 | 3 | `pkg_0589_LevelDefinition` |
| kongfu | `zombossmech_kongfu_qigong` | 3 | 6000 / 9000 / 11000 | 2 / 6,3 | 3 | 0 | `pkg_1412_LevelDefinition` |
| lostcity | `zombossmech_lostcity` | 3 | 5000 / 8000 / 9000 | 3 / 6,3 | 0 | 0 | `pkg_1837_LevelDefinition` |
| mausoleum | `zombossmech_mausoleum` | 3 | 6000 / 9000 / 10000 | 3 / 6,3 | 3 | 0 | `pkg_1476_LevelDefinition` |
| modern | `zombossmech_modern1` | 3 | 10000 / 8270 / 18000 | 3 / 6,4 | 7 | 3 | `pkg_1522_LevelDefinition` |
| beach | `zombossmech_modern_beach` | 3 | 7000 / 8000 / 10000 | 3 / 6,3 | 3 | 0 | `pkg_1534_LevelDefinition` |
| cowboy | `zombossmech_modern_cowboy` | 3 | 6500 / 10000 / 9000 | 2 / 6,3 | 3 | 3 | `pkg_1531_LevelDefinition` |
| dark | `zombossmech_modern_dark` | 3 | 11000 / 13000 / 15000 | 3 / 5,3 | 3 | 0 | `pkg_1533_LevelDefinition` |
| dino | `zombossmech_modern_dino` | 3 | 7000 / 9500 / 12000 | 3 / 6,4 | 3 | 2 | `pkg_1538_LevelDefinition` |
| egypt | `zombossmech_modern_egypt` | 3 | 5000 / 9000 / 8500 | 2 / 6,3 | 3 | 3 | `pkg_1529_LevelDefinition` |
| eighties | `zombossmech_modern_eighties` | 5 | 3500 / 4000 / 4500 / 5000 / 7000 | 3 / 6,4 | 8 | 0 | `pkg_1537_LevelDefinition` |
| future | `zombossmech_modern_future` | 3 | 13000 / 13000 / 13000 | 2 / 6,3 | 4 | 3 | `pkg_1532_LevelDefinition` |
| iceage | `zombossmech_modern_iceage` | 3 | 5000 / 4000 / 4000 | 3 / 6,3 | 0 | 3 | `pkg_1535_LevelDefinition` |
| lostcity | `zombossmech_modern_lostcity` | 3 | 6000 / 8000 / 9000 | 3 / 6,3 | 0 | 0 | `pkg_1536_LevelDefinition` |
| pirate | `zombossmech_modern_pirate` | 3 | 15000 / 18000 / 20000 | 2 / 6,3 | 3 | 0 | `pkg_1557_LevelDefinition` |
| renai | `zombossmech_renai` | 6 | 6000 / 21300 / 8000 / 21300 / 11000 / 21300 | 3 / 6,4 | 11 | 0 | `pkg_1080_LevelDefinition` |
| sky | `zombossmech_skycity` | 3 | 10000 / 14000 / 20000 | 3 / 7,2 | 2 | 0 | `pkg_1219_LevelDefinition` |
| steam | `zombossmech_steam` | 3 | 13000 / 17000 / 25000 | 2 / 6,3 | 3 | 3 | `pkg_1887_LevelDefinition` |

跨世界复用的 mech（`worlds` 长度 >1，主放置按上面的规则选）：

- `zombossmech_added_cowboy`：主 `plantagenet`，全部 losantosvice、plantagenet
- `zombossmech_added_lostcity`：主 `lostcity`，全部 chinesegarden、lostcity
- `zombossmech_dark`：主 `renai`，全部 dark、renai
- `zombossmech_future2`：主 `lunarrainbowmarket`，全部 future、lunarrainbowmarket
- `zombossmech_kongfu_qigong`：主 `kongfu`，全部 kongfu、unknown:Stage
- `zombossmech_lostcity`：主 `lostcity`，全部 lostcity、unknown:JoustStage
- `zombossmech_modern1`：主 `modern`，全部 modern、unknown:ChildStage

## 3. stage → world 推断表（命中前缀即该世界）

| stage | world |
|---|---|
| `BeachBossStage` | beach |
| `BeachStage` | beach |
| `CarnivalBossStage` | carnival |
| `CarnivalStage` | carnival |
| `ChildStage` | unknown:ChildStage |
| `ChineseGardenBossStage` | chinesegarden |
| `ChineseGardenStage` | chinesegarden |
| `ChineseGardenUBStage` | chinesegarden |
| `DarkStage` | dark |
| `DinoNightsStage` | dino |
| `DinoStage` | dino |
| `EgyptNightsBossStage` | egypt |
| `EgyptStage` | egypt |
| `EightiesStage` | eighties |
| `FairyStage` | fairy |
| `FutureStage` | future |
| `GTAUBStage` | losantosvice |
| `HeianBossStage` | heian |
| `IceageEXStage` | iceage |
| `IceageStage` | iceage |
| `JoustStage` | unknown:JoustStage |
| `KongfuBossStage` | kongfu |
| `LostCityNightsStage` | lostcity |
| `LostCityStage` | lostcity |
| `LunarDaylightUBStage` | lunarrainbowmarket |
| `LunarNoMusicSuffixStage` | lunarrainbowmarket |
| `MarketNightsStage` | lunarrainbowmarket |
| `MausoleumStage` | mausoleum |
| `ModernStage` | modern |
| `ModernUBStage` | modern |
| `PirateBossStage` | pirate |
| `PirateStage` | pirate |
| `PlantagenetBossStage` | plantagenet |
| `PvZ2CRoofNightStage` | roof |
| `RenaiBossStage` | renai |
| `RenaiStage` | renai |
| `RiftStage` | rift |
| `RoofNightStage` | roof |
| `SkyCityBossStage` | sky |
| `SkyCityLostCityBossStage` | lostcity |
| `Stage` | unknown:Stage |
| `SteamBossStage` | steam |
| `WestBossStage` | cowboy |
| `WestNightBossStage` | cowboy |
| `WestStage` | cowboy |

## 4. unknown 归属（保留，不丢）

按 boss（distinct mech）计：`1` 条落在 unknown 世界。按放置计：`unknown:ChildStage` × 2、`unknown:JoustStage` × 1、`unknown:Stage` × 1。

| world | boss id | stage | 说明 |
|---|---|---|---|
| `unknown:ChildStage` | `zombossmech_added_circus` | `ChildStage` | 该 stage 未命中前缀表，原样保留 |

这些行的 `world` 字段原样保留为 `unknown:<StageModule>`，没有被归入任何客户端世界。

## 4b. 悬空引用（battle module 指向的 mech 在包里不存在）

| boss id | module pkg | 结果 |
|---|---|---|
| `zombossmech_egypt_rift` | `pkg_0576_LevelDefinition` | `pkg_2115_ZombieType` 无该 `TypeName` 行；按 `Zombie`+CamelCase 猜出的 props 名 `ZombieZombossmechEgyptRift` 也不存在 → `stages` 为空、`missingProps=true` |

这是 pack 自身的数据缺口（Rift 关卡引用的 mech 类型没有随包发布），不是编译失败；该 boss 仍然出现在表里，只是没有阶段表，引擎需回退到 authored 数值或忽略该关卡。

## 4c. 有完整阶段表、但本包内没有任何关卡放置的 mech（24）

这些是 Battlez / Rift 变体，`Stages` 齐全但没有 `ZombossBattleModuleProperties` 把它们放上场，因此没有 `spawn`，默认不编入 `bosses`（列在这里以免看起来是被丢掉了）。

| boss id | props | 阶段数 | 来源 pkg |
|---|---|---:|---|
| `zombossmech_added_iceage` | `ZombieZombossMechAddedIceAge` | 3 | `pkg_0993_LevelDefinition` |
| `zombossmech_beach2` | `ZombieZombossMechBeach2` | 3 | `pkg_2112_ZombiePropertySheet` |
| `zombossmech_circus_battlez` | `ZombieZombossMechBattlezCircus` | 3 | `pkg_2112_ZombiePropertySheet` |
| `zombossmech_circus_rift` | `ZombieZombossMechRiftCircus` | 3 | `pkg_2112_ZombiePropertySheet` |
| `zombossmech_cowboy_battlez` | `ZombieZombossMechBattlezCowboy` | 3 | `pkg_2112_ZombiePropertySheet` |
| `zombossmech_cowboy_rift` | `ZombieZombossMechRiftCowboy` | 3 | `pkg_2112_ZombiePropertySheet` |
| `zombossmech_dark_battlez` | `ZombieZombossMechDarkBattlez` | 3 | `pkg_2112_ZombiePropertySheet` |
| `zombossmech_dark_rift` | `ZombieZombossMechDarkRift` | 3 | `pkg_2112_ZombiePropertySheet` |
| `zombossmech_dino` | `ZombieZombossMechDino` | 3 | `pkg_2112_ZombiePropertySheet` |
| `zombossmech_dino2` | `ZombieZombossMechDino2` | 3 | `pkg_2112_ZombiePropertySheet` |
| `zombossmech_dino_battlez` | `ZombieZombossMechBattlezDino` | 3 | `pkg_2112_ZombiePropertySheet` |
| `zombossmech_egypt_battlez` | `ZombieZombossMechBattlezEgypt` | 3 | `pkg_2112_ZombiePropertySheet` |
| `zombossmech_future_battlez` | `ZombieZombossMechBattlezFuture` | 3 | `pkg_2112_ZombiePropertySheet` |
| `zombossmech_future_rift` | `ZombieZombossMechRiftFuture` | 3 | `pkg_2112_ZombiePropertySheet` |
| `zombossmech_iceage2` | `ZombieZombossMechIceAge2` | 3 | `pkg_2112_ZombiePropertySheet` |
| `zombossmech_iceage_battlez` | `ZombieZombossMechBattlezIceAge` | 3 | `pkg_2112_ZombiePropertySheet` |
| `zombossmech_lostcity2` | `ZombieZombossMechLostCity2` | 3 | `pkg_2112_ZombiePropertySheet` |
| `zombossmech_lostcity_battlez` | `ZombieZombossMechBattlezLostCity` | 3 | `pkg_2112_ZombiePropertySheet` |
| `zombossmech_market` | `ZombieZombossMechMarket` | 3 | `pkg_2112_ZombiePropertySheet` |
| `zombossmech_pirate` | `ZombieZombossMechPirate` | 3 | `pkg_2112_ZombiePropertySheet` |
| `zombossmech_pirate2` | `ZombieZombossMechPirate2` | 3 | `pkg_2112_ZombiePropertySheet` |
| `zombossmech_pirate_battlez` | `ZombieZombossMechBattlezPirate` | 3 | `pkg_2112_ZombiePropertySheet` |
| `zombossmech_pirate_rift` | `ZombieZombossMechRiftPirate` | 3 | `pkg_2112_ZombiePropertySheet` |
| `zombossmech_roman` | `ZombieZombossMechRoman` | 3 | `pkg_2112_ZombiePropertySheet` |

## 5. 零数据世界

按放置（75 条 battle module）统计：26 个客户端世界里 **23 个有 boss 关**；完全没有 boss 数据的 **3 个**：`frontyard`、`memorytour`、`muji`。

另有 5 个由 stage 名推断出来的非客户端世界（`rift`、`roof`、`unknown:ChildStage`、`unknown:JoustStage`、`unknown:Stage`）——它们是 pack 里的屋顶/Rift/其它关卡，不属于 26 个世界，但数据保留在表里。

这些世界在 `content/bosses.json` 里有条目（`boss_frontyard`、`boss_memorytour`、`boss_muji`），但 pack 里既无 `ZombossBattleModuleProperties` 也无对应 mech —— 它们只能 authored。

## 6. 与 `content/bosses.json` 的对比

来源：`content/bosses.json`（客户端合成数据）。

| 世界 | 代表 pack boss | 代表 HP 序列 | 代表 HP 合计 | 该世界全部 mech / 阶段 | 客户端 id | 客户端 HP | 客户端阶段 | HP 差 | 阶段差 |
|---|---|---|---:|---|---|---:|---:|---:|---:|
| beach | `zombossmech_beach` | 10000 / 14000 / 18000 | 42000 | `zombossmech_beach`、`zombossmech_modern_beach` / 6 | `boss_beach` | 9200 | 3 | +32800 | +0 |
| carnival | `zombossmech_circus` | 6300 / 14514 / 19191 | 40005 | `zombossmech_circus` / 3 | `boss_carnival` | 13000 | 3 | +27005 | +0 |
| chinesegarden | `zombossmech_added_beach` | 2000 / 45000 / 50000 | 97000 | `zombossmech_added_beach`、`zombossmech_added_chinesegarden`、`zombossmech_added_lostcity`、`zombossmech_chinesegarden` / 12 | `boss_chinesegarden` | 11000 | 3 | +86000 | +0 |
| cowboy | `zombossmech_cowboy` | 6500 / 10000 / 9000 | 25500 | `zombossmech_cowboy`、`zombossmech_cowboy2`、`zombossmech_modern_cowboy` / 9 | `boss_cowboy` | 8600 | 3 | +16900 | +0 |
| dark | `zombossmech_dark` | 7000 / 9000 / 11000 | 27000 | `zombossmech_dark`、`zombossmech_modern_dark` / 6 | `boss_dark` | 9000 | 3 | +18000 | +0 |
| dino | `zombossmech_dino3` | 10000 / 8000 / 7000 / 7000 | 32000 | `zombossmech_dino3`、`zombossmech_modern_dino` / 7 | `boss_dino` | 10000 | 3 | +22000 | +1 |
| egypt | `zombossmech_egypt` | 4000 / 8000 / 6500 | 18500 | `zombossmech_egypt`、`zombossmech_egypt2`、`zombossmech_modern_egypt` / 9 | `boss_egypt` | 8200 | 3 | +10300 | +0 |
| eighties | `zombossmech_eighties` | 4500 / 5000 / 5500 / 6000 / 7000 | 28000 | `zombossmech_eighties`、`zombossmech_eighties2`、`zombossmech_modern_eighties` / 15 | `boss_eighties` | 10200 | 3 | +17800 | +2 |
| fairy | `zombossmech_added_fairytale` | 7000 / 11000 / 12000 | 30000 | `zombossmech_added_fairytale`、`zombossmech_fairytale`、`zombossmech_fairytale_head1`、`zombossmech_fairytale_head2` / 8 | `boss_fairy` | 11400 | 3 | +18600 | +0 |
| frontyard | — | — | — | — / 0 | `boss_frontyard` | 8000 | 3 | — | — |
| future | `zombossmech_future` | 13000 / 14410 / 22000 | 49410 | `zombossmech_future`、`zombossmech_future2`、`zombossmech_modern_future` / 9 | `boss_future` | 8800 | 3 | +40610 | +0 |
| heian | `zombossmech_heian` | 7500 / 9750 / 12000 | 29250 | `zombossmech_heian` / 3 | `boss_heian` | 11200 | 3 | +18050 | +0 |
| iceage | `zombossmech_iceage` | 5000 / 4000 / 4000 | 13000 | `zombossmech_iceage`、`zombossmech_modern_iceage` / 6 | `boss_iceage` | 9600 | 3 | +3400 | +0 |
| kongfu | `kongfu_zomboss_blade` | 15000 / 25000 / 35000 | 75000 | `kongfu_zomboss_blade`、`zombossmech_kongfu_qigong` / 6 | `boss_kongfu` | 9800 | 3 | +65200 | +0 |
| losantosvice | `zombossmech_added_cowboy` | 15000 / 30000 / 50000 | 95000 | `zombossmech_added_cowboy` / 3 | `boss_losantosvice` | 12200 | 3 | +82800 | +0 |
| lostcity | `zombossmech_added_lostcity` | 6000 / 10000 / 10000 | 26000 | `zombossmech_added_lostcity`、`zombossmech_lostcity`、`zombossmech_modern_lostcity` / 9 | `boss_lostcity` | 9400 | 3 | +16600 | +0 |
| lunarrainbowmarket | `zombossmech_added_dark` | 10000 / 15000 / 20000 | 45000 | `zombossmech_added_dark`、`zombossmech_added_market`、`zombossmech_future2` / 9 | `boss_lunarrainbowmarket` | 12400 | 3 | +32600 | +0 |
| mausoleum | `zombossmech_added_mausoleum` | 8000 / 10000 / 15000 | 33000 | `zombossmech_added_mausoleum`、`zombossmech_mausoleum` / 6 | `boss_mausoleum` | 11600 | 3 | +21400 | +0 |
| memorytour | — | — | — | — / 0 | `boss_memorytour` | 12000 | 3 | — | — |
| modern | `zombossmech_modern1` | 10000 / 8270 / 18000 | 36270 | `zombossmech_modern1` / 3 | `boss_modern` | 10400 | 3 | +25870 | +0 |
| muji | — | — | — | — / 0 | `boss_muji` | 12800 | 3 | — | — |
| pirate | `zombossmech_modern_pirate` | 15000 / 18000 / 20000 | 53000 | `zombossmech_modern_pirate` / 3 | `boss_pirate` | 8400 | 3 | +44600 | +0 |
| plantagenet | `zombossmech_added_cowboy` | 15000 / 30000 / 50000 | 95000 | `zombossmech_added_cowboy` / 3 | `boss_plantagenet` | 13200 | 3 | +81800 | +0 |
| renai | `zombossmech_renai` | 6000 / 21300 / 8000 / 21300 / 11000 / 21300 | 88900 | `zombossmech_dark`、`zombossmech_dark2`、`zombossmech_renai` / 12 | `boss_renai` | 12600 | 3 | +76300 | +3 |
| rift | `zombossmech_added_roman` | 6000 / 7500 / 9000 | 22500 | `zombossmech_added_roman`、`zombossmech_egypt_rift` / 3 | — | — | — | — | +3 |
| roof | `zombossmech_adventure` | 5000 / 6000 / 7500 / 8000 / 8000 | 34500 | `zombossmech_adventure`、`zombossmech_adventure2` / 8 | — | — | — | — | +5 |
| sky | `zombossmech_skycity` | 10000 / 14000 / 20000 | 44000 | `zombossmech_skycity` / 3 | `boss_sky` | 10600 | 3 | +33400 | +0 |
| steam | `zombossmech_steam` | 13000 / 17000 / 25000 | 55000 | `zombossmech_steam` / 3 | `boss_steam` | 11800 | 3 | +43200 | +0 |
| unknown:ChildStage | `zombossmech_added_circus` | 20000 / 35000 / 50000 | 105000 | `zombossmech_added_circus`、`zombossmech_modern1` / 6 | — | — | — | — | +3 |
| unknown:JoustStage | `zombossmech_lostcity` | 5000 / 8000 / 9000 | 22000 | `zombossmech_lostcity` / 3 | — | — | — | — | +3 |
| unknown:Stage | `zombossmech_kongfu_qigong` | 6000 / 9000 / 11000 | 26000 | `zombossmech_kongfu_qigong` / 3 | — | — | — | — | +3 |

「代表 boss」= 该世界里阶段数最多的 mech（并列取 id 最小），因为客户端的每行只描述一只 boss；「该世界全部 mech / 阶段」是这个世界在 pack 里的完整规模（含 Battlez/UB 等变体表）。

### 三个具体例子

- **chinesegarden**：pack 的 `zombossmech_added_beach` 有 3 个阶段、HP 依次 2000 / 45000 / 50000（合计 97000），客户端 `boss_chinesegarden` 只有 3 个阶段、单一 HP 11000 —— HP 差 +86000，阶段差 +0。
- **losantosvice**：pack 的 `zombossmech_added_cowboy` 有 3 个阶段、HP 依次 15000 / 30000 / 50000（合计 95000），客户端 `boss_losantosvice` 只有 3 个阶段、单一 HP 12200 —— HP 差 +82800，阶段差 +0。
- **plantagenet**：pack 的 `zombossmech_added_cowboy` 有 3 个阶段、HP 依次 15000 / 30000 / 50000（合计 95000），客户端 `boss_plantagenet` 只有 3 个阶段、单一 HP 13200 —— HP 差 +81800，阶段差 +0。

结论：客户端的 HP 是「世界顺序 × 200」的等差数列（8000…13200），阶段数恒为 3，三条 `phases` 的 `speed`/`eat_mult` 也完全相同；pack 的分阶段 HP、阶段数（3 / 4 / 5 / 6）、每阶段的动作池都不同，且没有一条 world 的 HP 与客户端相同。`bosses_from_pack.json` 可以直接替换它的 `hp`/`phases` 数值来源。

## 7. 引擎怎么用这张表

1. 按 `world`（或 `modulePkg` 精确到关）取 boss；`unknown:*` 的行按 `spawn.stageModule` 自行决定归属。
2. 用 `stages[i].hitPoints` 作为第 i 阶段血量上限；`stages[i].actions` 是这一阶段的行动池，`type` 决定走哪个动作分支（Fire / Spawn / Summon / Rush / Walk…），`fields` 是原值参数。
3. `spawn.reservedColumns` 是本关要为 boss 预留的列数，`gridX/gridY` 是出场格；`deathRow/deathColumn` 是死亡演出定位。
4. `stageSelection` 非空时（如 SkyCity 的 `count=3/startIndex=0`），按它裁剪 `stages`。

未做的事（诚实边界）：没有把 `Actions[]` 里的僵尸类型 RTID 展开成刷怪波次，也没有解析 `@ZombieActions` 的动作时长/前摇（这些字段在动作对象里，引擎侧按需读取即可）；`content/bosses.json` 的文案/奖励/小怪列表仍未与 pack 建立映射。

