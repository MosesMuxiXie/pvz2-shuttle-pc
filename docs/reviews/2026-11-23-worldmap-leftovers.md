# 世界地图遗留清理：62 悬空 world / kungfu 拼写 / cleared 口径

对 `native/generated/world_gates.json`（97 条门）与客户端世界表做只读核对。本文件不含代码改动，只给证据、计数与建议。

## 结论摘要

1. **悬空 world 62 条**：真别名 9、活动/赛事世界 49、测试残留 3、拼写错 1。按 `worldClient` 归一后真正无家可归的只有 1 条（`kungfu`）。
2. **拼写判决：用 `kongfu`**。客户端 `content/worlds.json`、`content/worldmap.json`、`content/levels/*.json`（83 关）全部是 `kongfu`；`kungfu` 只出现在 1 条门的世界名和 1 条 worldgate 的 target 里，属原表变体条目。
3. **cleared 口径两处一致**：`main.cpp` 的 `--worldmap` 与 `worldmap_view.cpp` 的屏幕路径用同一前缀统计，175/175 夹具下 `completed` 都是 1，`unlocked` 与 `available` 都是 25。两处算法应抽公共函数防漂移。

## 复现命令

```powershell
cd D:\OneDrive\文档\pvz_shuttle\repo\pvz2-shuttle-pc
python tools/contentc/worlds.py                      # 重新生成 world_gates.json
python -c "..."                                      # 本报告的分类与计数（见附录）
build\desktop-gate\Release\PvZ2SHUTTLE.exe --worldmap content --progress <fixture>.json
build\desktop-gate\Release\PvZ2SHUTTLE.exe --worldmap-screen content --progress <fixture>.json --assets <assets> --frames 1 --snapshot <out.png>
```

## 一、62 条悬空 world

### 1.1 计数口径

「悬空」= 门的 `world` 字段不是 `content/worlds.json` 的 26 个世界 id 之一。归一前后的差别如下表——这也是 62 与 53 两个数字的来源，写文档时必须带上前提。

| 口径 | 条数 | 说明 |
| --- | --- | --- |
| `world` 原值不在 26 世界 | **62** | 任务书与 t36 复审用的数字 |
| `worldClient`（过 `ALIASES`）仍不在 26 世界 | 53 | 别名被消掉后的真实缺口 |
| 门的 `world` 在 26 世界内 | 35 | 其余门 |
| 门总数 | 97 | |

### 1.2 分类计数

| 类别 | 条数 | 涉及 world | 处置建议 |
| --- | --- | --- | --- |
| 真别名 | 9 | `gta`、`rainbowmarket`、`skycity` | 已由 `ALIASES` 归一，导出侧无需改；S6 判定用 `worldClient` |
| 活动/赛事/节日世界 | 49 | `aprilfools`、`atlantis`、`cerydra`、`collab1`、`collab2`、`epicquest`、`fifthanniversary`、`firefly`、`fourthanniversary`、`funtime`、`hysilens`、`lny`、`secondanniversary`、`sixthanniversary`、`thirdanniversary`、`thymedevent`、`tower`、`tutorial`、`yourhouse`、`yourhousex` | 客户端没有这些世界，门应标 `worldClient: null` 或留在「无主门」清单，不参与 26 世界解锁判定 |
| 测试残留世界 | 3 | `element`、`tes12`、`tes13` | 同活动世界；建议在报告里单列，避免被当成正式世界 |
| 拼写错 | 1 | `kungfu` | 改成 `kongfu`（见第二节） |
| **合计** | **62** | | |

### 1.3 全量 62 条

字段与 `world_gates.json` 一致；`raw` 只摘与判定相关的 `m_` 字段。

| # | event | kind | world | worldClient | target | stars | keys | raw 摘要 | 类别 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `aprilfools_stargate_start` | star_gate | `aprilfools` | `aprilfools` | null | 0 | null | m_name=aprilfools_stargate_start; m_cost=0 | 活动/赛事/节日世界（不在 26 世界内） |
| 2 | `atlantis_stargate_start` | star_gate | `atlantis` | `atlantis` | `egypt_level_1` | 10 | null | m_name=atlantis_stargate_start; m_cost=10; m_unlockedFrom=egypt_level_1 | 活动/赛事/节日世界（不在 26 世界内） |
| 3 | `cerydra_stargate_start` | star_gate | `cerydra` | `cerydra` | null | 0 | null | m_name=cerydra_stargate_start; m_cost=0 | 活动/赛事/节日世界（不在 26 世界内） |
| 4 | `collab1_stargate_start` | star_gate | `collab1` | `collab1` | `egypt_level_1` | 10 | null | m_name=collab1_stargate_start; m_cost=10; m_unlockedFrom=egypt_level_1 | 活动/赛事/节日世界（不在 26 世界内） |
| 5 | `collab2_stargate_start` | star_gate | `collab2` | `collab2` | `egypt_level_1` | 0 | null | m_name=collab2_stargate_start; m_cost=0; m_unlockedFrom=egypt_level_1 | 活动/赛事/节日世界（不在 26 世界内） |
| 6 | `element_stargate_start` | star_gate | `element` | `element` | `egypt_level_1` | 10 | null | m_name=element_stargate_start; m_cost=10; m_unlockedFrom=egypt_level_1 | 测试残留世界（不在 26 世界内） |
| 7 | `epicquest_level_intro1` | star_gate | `epicquest` | `epicquest` | `egypt_level_7` | 0 | null | m_name=epicquest_level_intro1; m_cost=0; m_unlockedFrom=egypt_level_7 | 活动/赛事/节日世界（不在 26 世界内） |
| 8 | `fifthanniversary_stargate_start` | star_gate | `fifthanniversary` | `fifthanniversary` | `egypt_level_1` | 10 | null | m_name=fifthanniversary_stargate_start; m_cost=10; m_unlockedFrom=egypt_level_1 | 活动/赛事/节日世界（不在 26 世界内） |
| 9 | `firefly_stargate_start` | star_gate | `firefly` | `firefly` | null | 0 | null | m_name=firefly_stargate_start; m_cost=0 | 活动/赛事/节日世界（不在 26 世界内） |
| 10 | `fourthanniversary_keygate_chal_laststand` | key_gate | `fourthanniversary` | `fourthanniversary` | null | null | 5 | m_name=fourthanniversary_keygate_chal_laststand; m_cost=5 | 活动/赛事/节日世界（不在 26 世界内） |
| 11 | `fourthanniversary_keygate_chal_minigame` | key_gate | `fourthanniversary` | `fourthanniversary` | null | null | 3 | m_name=fourthanniversary_keygate_chal_minigame; m_cost=3 | 活动/赛事/节日世界（不在 26 世界内） |
| 12 | `fourthanniversary_keygate_chal_preset` | key_gate | `fourthanniversary` | `fourthanniversary` | null | null | 4 | m_name=fourthanniversary_keygate_chal_preset; m_cost=4 | 活动/赛事/节日世界（不在 26 世界内） |
| 13 | `fourthanniversary_keygate_chal_protect` | key_gate | `fourthanniversary` | `fourthanniversary` | null | null | 4 | m_name=fourthanniversary_keygate_chal_protect; m_cost=4 | 活动/赛事/节日世界（不在 26 世界内） |
| 14 | `fourthanniversary_stargate_exit` | star_gate | `fourthanniversary` | `fourthanniversary` | `fourthanniversary_level_10` | 20 | null | m_name=fourthanniversary_stargate_exit; m_cost=20; m_unlockedFrom=fourthanniversary_level_10 | 活动/赛事/节日世界（不在 26 世界内） |
| 15 | `fourthanniversary_stargate_start` | star_gate | `fourthanniversary` | `fourthanniversary` | `egypt_level_1` | 0 | null | m_name=fourthanniversary_stargate_start; m_cost=0; m_unlockedFrom=egypt_level_1 | 活动/赛事/节日世界（不在 26 世界内） |
| 16 | `funtime_stargate_start` | star_gate | `funtime` | `funtime` | `egypt_level_1` | 10 | null | m_name=funtime_stargate_start; m_cost=10; m_unlockedFrom=egypt_level_1 | 活动/赛事/节日世界（不在 26 世界内） |
| 17 | `gangster_keygate_chal_laststand` | key_gate | `gta` | `losantosvice` | null | null | 4 | m_name=gangster_keygate_chal_laststand; m_cost=4 | 真别名（ALIASES 可映射到 26 世界） |
| 18 | `gangster_keygate_chal_minigame` | key_gate | `gta` | `losantosvice` | null | null | 3 | m_name=gangster_keygate_chal_minigame; m_cost=3 | 真别名（ALIASES 可映射到 26 世界） |
| 19 | `gangster_keygate_chal_preset` | key_gate | `gta` | `losantosvice` | null | null | 5 | m_name=gangster_keygate_chal_preset; m_cost=5 | 真别名（ALIASES 可映射到 26 世界） |
| 20 | `gangster_keygate_chal_protect` | key_gate | `gta` | `losantosvice` | null | null | 4 | m_name=gangster_keygate_chal_protect; m_cost=4 | 真别名（ALIASES 可映射到 26 世界） |
| 21 | `gangster_stargate_exit` | star_gate | `gta` | `losantosvice` | `cowboy_level_10` | 0 | null | m_name=gangster_stargate_exit; m_cost=0; m_unlockedFrom=cowboy_level_10 | 真别名（ALIASES 可映射到 26 世界） |
| 22 | `gangster_stargate_start` | star_gate | `gta` | `losantosvice` | null | 10 | null | m_name=gangster_stargate_start; m_cost=10 | 真别名（ALIASES 可映射到 26 世界） |
| 23 | `hysilens_stargate_start` | star_gate | `hysilens` | `hysilens` | null | 0 | null | m_name=hysilens_stargate_start; m_cost=0 | 活动/赛事/节日世界（不在 26 世界内） |
| 24 | `kungfu_stargate_start` | star_gate | `kungfu` | `kungfu` | `kongfu_level_boss` | null | null | m_name=kungfu_stargate_start; m_unlockedFrom=kongfu_level_boss | 拼写错 |
| 25 | `lny2026_stargate_start` | star_gate | `lny` | `lny` | `egypt_level_1` | 0 | null | m_name=lny2026_stargate_start; m_cost=0; m_unlockedFrom=egypt_level_1 | 活动/赛事/节日世界（不在 26 世界内） |
| 26 | `rainbowmarket_stargate_start` | star_gate | `rainbowmarket` | `lunarrainbowmarket` | null | 10 | null | m_name=rainbowmarket_stargate_start; m_cost=10 | 真别名（ALIASES 可映射到 26 世界） |
| 27 | `secondanniversary_stargate_start` | star_gate | `secondanniversary` | `secondanniversary` | `egypt_level_1` | 10 | null | m_name=secondanniversary_stargate_start; m_cost=10; m_unlockedFrom=egypt_level_1 | 活动/赛事/节日世界（不在 26 世界内） |
| 28 | `sixthanniversary_keygate_chal_preset` | key_gate | `sixthanniversary` | `sixthanniversary` | null | null | 4 | m_name=sixthanniversary_keygate_chal_preset; m_cost=4 | 活动/赛事/节日世界（不在 26 世界内） |
| 29 | `sixthanniversary_keygate_chal_protect` | key_gate | `sixthanniversary` | `sixthanniversary` | null | null | 3 | m_name=sixthanniversary_keygate_chal_protect; m_cost=3 | 活动/赛事/节日世界（不在 26 世界内） |
| 30 | `sixthanniversary_stargate_start` | star_gate | `sixthanniversary` | `sixthanniversary` | null | 0 | null | m_name=sixthanniversary_stargate_start; m_cost=0 | 活动/赛事/节日世界（不在 26 世界内） |
| 31 | `skycity_stargate_exit` | star_gate | `skycity` | `sky` | `skycity_level_8` | 8 | null | m_name=skycity_stargate_exit; m_cost=8; m_unlockedFrom=skycity_level_8 | 真别名（ALIASES 可映射到 26 世界） |
| 32 | `skycity_stargate_start` | star_gate | `skycity` | `sky` | null | null | null | m_name=skycity_stargate_start | 真别名（ALIASES 可映射到 26 世界） |
| 33 | `tes12_stargate_start` | star_gate | `tes12` | `tes12` | null | 0 | null | m_name=tes12_stargate_start; m_cost=0 | 测试残留世界（不在 26 世界内） |
| 34 | `tes13_stargate_start` | star_gate | `tes13` | `tes13` | null | 0 | null | m_name=tes13_stargate_start; m_cost=0 | 测试残留世界（不在 26 世界内） |
| 35 | `thirdanniversary_keygate_chal_0` | key_gate | `thirdanniversary` | `thirdanniversary` | null | null | 1 | m_name=thirdanniversary_keygate_chal_0; m_cost=1 | 活动/赛事/节日世界（不在 26 世界内） |
| 36 | `thirdanniversary_keygate_chal_laststand` | key_gate | `thirdanniversary` | `thirdanniversary` | null | null | 5 | m_name=thirdanniversary_keygate_chal_laststand; m_cost=5 | 活动/赛事/节日世界（不在 26 世界内） |
| 37 | `thirdanniversary_keygate_chal_minigame` | key_gate | `thirdanniversary` | `thirdanniversary` | null | null | 4 | m_name=thirdanniversary_keygate_chal_minigame; m_cost=4 | 活动/赛事/节日世界（不在 26 世界内） |
| 38 | `thirdanniversary_keygate_chal_preset` | key_gate | `thirdanniversary` | `thirdanniversary` | null | null | 4 | m_name=thirdanniversary_keygate_chal_preset; m_cost=4 | 活动/赛事/节日世界（不在 26 世界内） |
| 39 | `thirdanniversary_keygate_chal_protect` | key_gate | `thirdanniversary` | `thirdanniversary` | null | null | 3 | m_name=thirdanniversary_keygate_chal_protect; m_cost=3 | 活动/赛事/节日世界（不在 26 世界内） |
| 40 | `thirdanniversary_stargate_exit` | star_gate | `thirdanniversary` | `thirdanniversary` | `thirdanniversary_level_8` | 8 | null | m_name=thirdanniversary_stargate_exit; m_cost=8; m_unlockedFrom=thirdanniversary_level_8 | 活动/赛事/节日世界（不在 26 世界内） |
| 41 | `thirdanniversary_stargate_start` | star_gate | `thirdanniversary` | `thirdanniversary` | null | 0 | null | m_name=thirdanniversary_stargate_start; m_cost=0 | 活动/赛事/节日世界（不在 26 世界内） |
| 42 | `thymedevent_stargate_start` | star_gate | `thymedevent` | `thymedevent` | `egypt_level_7` | 0 | null | m_name=thymedevent_stargate_start; m_cost=0; m_unlockedFrom=egypt_level_7 | 活动/赛事/节日世界（不在 26 世界内） |
| 43 | `worldgate_cerydra` | worldgate | `thymedevent` | `thymedevent` | `cerydra` | null | null | m_name=worldgate_cerydra; m_dataString=cerydra-thymed_event_unlock-true | 活动/赛事/节日世界（不在 26 世界内） |
| 44 | `worldgate_collab1` | worldgate | `thymedevent` | `thymedevent` | `collab1` | null | null | m_name=worldgate_collab1; m_dataString=collab1-thymed_event_unlock-true | 活动/赛事/节日世界（不在 26 世界内） |
| 45 | `worldgate_collab2` | worldgate | `thymedevent` | `thymedevent` | `collab2` | null | null | m_name=worldgate_collab2; m_dataString=collab2-thymed_event_unlock-true | 活动/赛事/节日世界（不在 26 世界内） |
| 46 | `worldgate_element` | worldgate | `thymedevent` | `thymedevent` | `element` | null | null | m_name=worldgate_element; m_dataString=element-thymed_event_unlock-true | 活动/赛事/节日世界（不在 26 世界内） |
| 47 | `worldgate_fifthanniversary` | worldgate | `thymedevent` | `thymedevent` | `fifthanniversary` | null | null | m_name=worldgate_fifthanniversary; m_dataString=fifthanniversary-thymed_event_unlock-true | 活动/赛事/节日世界（不在 26 世界内） |
| 48 | `worldgate_firefly` | worldgate | `thymedevent` | `thymedevent` | `firefly` | null | null | m_name=worldgate_firefly; m_dataString=firefly-thymed_event_unlock-true | 活动/赛事/节日世界（不在 26 世界内） |
| 49 | `worldgate_fourthanniversary` | worldgate | `thymedevent` | `thymedevent` | `fourthanniversary` | null | null | m_name=worldgate_fourthanniversary; m_dataString=fourthanniversary-thymed_event_unlock-true | 活动/赛事/节日世界（不在 26 世界内） |
| 50 | `worldgate_funtime` | worldgate | `thymedevent` | `thymedevent` | `funtime` | null | null | m_name=worldgate_funtime; m_dataString=funtime-thymed_event_unlock-true | 活动/赛事/节日世界（不在 26 世界内） |
| 51 | `worldgate_hysilens` | worldgate | `thymedevent` | `thymedevent` | `hysilens` | null | null | m_name=worldgate_hysilens; m_dataString=hysilens-thymed_event_unlock-true | 活动/赛事/节日世界（不在 26 世界内） |
| 52 | `worldgate_lny` | worldgate | `thymedevent` | `thymedevent` | `lny` | null | null | m_name=worldgate_lny; m_dataString=lny-thymed_event_unlock-true | 活动/赛事/节日世界（不在 26 世界内） |
| 53 | `worldgate_secondanniversary` | worldgate | `thymedevent` | `thymedevent` | `secondanniversary` | null | null | m_name=worldgate_secondanniversary; m_dataString=secondanniversary-thymed_event_unlock-true | 活动/赛事/节日世界（不在 26 世界内） |
| 54 | `worldgate_sixthanniversary` | worldgate | `thymedevent` | `thymedevent` | `sixthanniversary` | null | null | m_name=worldgate_sixthanniversary; m_dataString=sixthanniversary-thymed_event_unlock-true | 活动/赛事/节日世界（不在 26 世界内） |
| 55 | `worldgate_tes12` | worldgate | `thymedevent` | `thymedevent` | `tes12` | null | null | m_name=worldgate_tes12; m_dataString=tes12-thymed_event_unlock-true | 活动/赛事/节日世界（不在 26 世界内） |
| 56 | `worldgate_tes13` | worldgate | `thymedevent` | `thymedevent` | `tes13` | null | null | m_name=worldgate_tes13; m_dataString=tes13-thymed_event_unlock-true | 活动/赛事/节日世界（不在 26 世界内） |
| 57 | `worldgate_thirdanniversary` | worldgate | `thymedevent` | `thymedevent` | `thirdanniversary` | null | null | m_name=worldgate_thirdanniversary; m_dataString=thirdanniversary-thymed_event_unlock-true | 活动/赛事/节日世界（不在 26 世界内） |
| 58 | `tower_level_intro1` | star_gate | `tower` | `tower` | `chinesegarden_level_12` | null | null | m_name=tower_level_intro1; m_unlockedFrom=chinesegarden_level_12 | 活动/赛事/节日世界（不在 26 世界内） |
| 59 | `tutorial_stargate_exit` | star_gate | `tutorial` | `tutorial` | null | 1 | null | m_name=tutorial_stargate_exit; m_cost=1 | 活动/赛事/节日世界（不在 26 世界内） |
| 60 | `yourhouse_stargate_start` | star_gate | `yourhouse` | `yourhouse` | null | null | null | m_name=yourhouse_stargate_start | 活动/赛事/节日世界（不在 26 世界内） |
| 61 | `yourhousex_stargate_start` | star_gate | `yourhousex` | `yourhousex` | `yourhouse_revenge` | 0 | null | m_name=yourhousex_stargate_start; m_cost=0; m_unlockedFrom=yourhouse_revenge | 活动/赛事/节日世界（不在 26 世界内） |
| 62 | `worldgate_rainbowmarket` | worldgate | `yourhousex` | `yourhousex` | `rainbowmarket` | null | null | m_name=worldgate_rainbowmarket; m_dataString=rainbowmarket-rainbowmarket_stargate_start-true | 活动/赛事/节日世界（不在 26 世界内） |

### 1.4 不是缺陷的「target 悬空」

`target` 侧另有 38 条不是世界 id（`beach_level_16`、`kongfu_level_8`、`skycity_level_8` 等）。这不是悬空：`star_gate`/`key_gate` 的 `target` 取自 `m_unlockedFrom`，语义是**关卡引用**；只有 `worldgate` 的 `target` 才是世界段（形如 `kungfu-kungfu_stargate_start-true` 的第一段）。统计悬空时只能看 `world`，不能把 `target` 算进来——否则会多报 38 条。

## 二、`kungfu` / `kongfu` 拼写分叉

### 2.1 四路口径

| 位置 | `kongfu` | `kungfu` | 证据 |
| --- | --- | --- | --- |
| `world_gates.json` 的 `world` | 8 条门 | 1 条门 | 本文件 1.3 节 |
| `content/worlds.json` | 有（id `kongfu`，83 关） | 无 | `python -c` 读取 |
| `content/worldmap.json` | 有（键 `kongfu`） | 无 | 26 个键里只有 `kongfu` |
| `content/levels/*.json` 的 `world` 字段 | 83 个文件 | 0 | 1809 关按 world 计数 |
| 关卡 JSON 内文本 `KUNGFU`（大写） | — | 44 个文件 | `content/levels` 25 + `levels_before_v2` 19，都是 `[KUNGFU_LEVEL_NAME]` 之类的 name_key，不是世界 id |

### 2.2 相关门明细（实测 9 条，不是 24 条）

| event | kind | world | target | 说明 |
| --- | --- | --- | --- | --- |
| `kongfu_keygate_chal_protect` | key_gate | `kongfu` | null | 拼写正确 |
| `kongfu_keygate_chal_preset` | key_gate | `kongfu` | null | 拼写正确 |
| `worldgate_kungfu` | worldgate | `kongfu` | `kungfu` | worldgate 的 target 拼写错 |
| `kongfu_keygate_chal_laststand` | key_gate | `kongfu` | null | 拼写正确 |
| `kongfu_keygate_chal_minigame` | key_gate | `kongfu` | null | 拼写正确 |
| `kongfu_keygate_chal_0` | key_gate | `kongfu` | null | 拼写正确 |
| `kongfu_stargate_start` | star_gate | `kongfu` | null | 拼写正确 |
| `kongfu_stargate_exit` | star_gate | `kongfu` | `kongfu_level_8` | 拼写正确 |
| `kungfu_stargate_start` | star_gate | `kungfu` | `kongfu_level_boss` | 世界名拼写错（应为 kongfu） |

合计 **9 条**：`kongfu` 世界 8 条（6 key_gate + 2 star_gate），`kungfu` 世界 1 条（1 star_gate），其中 `worldgate_kungfu` 的 `target` 也是 `kungfu`。

任务书写的「24 条门」无法复现：按 `world == 'kongfu'/'kungfu'` 或 raw 文本含拼写统计都得 9 条。复现命令：`python -c` 读 `world_gates.json` 统计 `world` 值与 raw 文本命中（见附录 A）。若 24 指的是别的集合（例如含 `KUNGFU` 的关卡 name_key 文件数），需要给出定义才能复核。

### 2.3 判决与受影响文件（本任务不改）

**判决：统一用 `kongfu`。** 理由：客户端三处（worlds.json、worldmap.json、83 个关卡）一致用 `kongfu`；C++ 按 `world.id + "_"` 前缀统计 cleared，若门挂在 `kungfu` 而世界 id 是 `kongfu`，这条门永远匹配不到任何关卡，`requiredStars`/`requiredKeys` 会被静默忽略。`kungfu` 是原表里重复登记的变体世界（`world_diff.md` 已把它列为原版独有），不是客户端世界。

| 文件 | 位置 | 现状 | 需要的改动 |
| --- | --- | --- | --- |
| `native/generated/world_gates.json` | 第 456–457 行 | `target`/`targetClient` = `kungfu` | 重生成前先修数据源或加别名 |
| `native/generated/world_gates.json` | 第 1008–1009 行 | `world`/`worldClient` = `kungfu` | 同上 |
| `tools/contentc/worlds.py` | 第 53–57 行 `ALIASES` | 只有 skycity/gta/rainbowmarket | 加 `"kungfu": "kongfu"`，并在 `render_gates_markdown` 的别名表里自动多一行 |
| `native/src/*.cpp` | — | 不需要改 | 归一发生在导出层 |

注意：`kungfu` 的 1 条 star_gate 的 `target` 是 `kongfu_level_boss`（正确拼写），所以只有世界名与 `worldgate_kungfu` 的 target 两处要改。

## 三、cleared 统计口径

### 3.1 两处代码

`native/src/main.cpp:276-283`（`--worldmap`）：

```cpp
int cleared = 0;
for (const auto& [levelId, record] : progress.levels) {
    if (record.cleared && levelId.rfind(world.id + "_", 0) == 0) {
        ++cleared;
    }
}
const pvz::map::WorldStatus status = map.status(world.id, progress.totalStars(), progress.keys, cleared);
```

`native/src/worldmap_view.cpp:152-157`（屏幕路径）：

```cpp
int cleared = 0;
for (const auto& entry : progress.levels) {
    if (!entry.second.cleared) continue;
    if (entry.first.rfind(world.id + "_", 0) == 0) ++cleared;
}
statuses.push_back(map.status(world.id, progress.totalStars(), progress.keys, cleared));
```

两段是同一算法（遍历 `progress.levels`，按 `world.id + "_"` 前缀数 `cleared`），差别只有写法；`result.completed` 由 `statuses` 里 `state == completed` 计数（`worldmap_view.cpp:159-162`）。

### 3.2 夹具与实测

夹具：`frontyard_1..175` 各 `cleared: true, stars: 3`，`keys: 50`，无其它关卡。

```powershell
PvZ2SHUTTLE.exe --worldmap content --progress frontyard175.json
PvZ2SHUTTLE.exe --worldmap-screen content --progress frontyard175.json --assets <assets> --frames 1 --snapshot wm.png
```

`--worldmap` 原始输出（节选：顶层计数 + frontyard 行）：

```json
{"clearedLevels": 175, "gates": 97, "stars": 525, "keys": 50, "worlds": 26}
{"gates": 0, "id": "frontyard", "levels": 175, "order": 1, "requiredKeys": 0, "requiredStars": 1, "starsSource": "client", "state": "completed"}
```

`--worldmap-screen --frames 1 --snapshot` 原始输出：

```json
{"completed":1,"entered":"","keys":50,"level":"","selected":"frontyard","stars":525,"unlocked":25,"worlds":26}
```

### 3.3 结论

| 指标 | `--worldmap` | `--worldmap-screen` | 一致 |
| --- | --- | --- | --- |
| completed | 1（frontyard） | 1 | 是 |
| 可进入 | 25 | 25 | 是 |
| 顶层已通关 | 175 | —（屏幕不输出总数） | — |

**两处 completed 数字一致（都是 1）**，`available`/`unlocked` 也一致（25），说明 S6 的屏幕路径与 `--worldmap` 没有各算各的。

### 3.4 最小修法建议（只写建议，不改代码）

1. 在 `progress.hpp` 增加 `int clearedLevelsFor(const std::string& worldId) const`（或自由函数），把 `world.id + "_"` 前缀统计收进一处；两处调用点各删 5 行循环。
2. 顺带在 `worldmap_test.cpp` 加一条回归：`sum(clearedLevelsFor(world)) == clearedLevels()`（当存档里所有关卡 id 都能被某个世界前缀认领时成立），把「顶层 175 与逐世界之和不一致」这类漂移变成测试红灯。
3. 不建议改语义：顶层 `clearedLevels` 来自 `Progress::clearedLevels()`（数全部 cleared 条目），与逐世界之和在存在「无主关卡 id」时会天然不等；这是两个不同问题，别用一个数字硬对齐。

## 四、边界

- 未改任何 C++、`content/**`、`native/generated/world_gates.json` 与 `tools/contentc/worlds.py`；本文件是唯一新增产物。
- 未跑 `obb_art.py`；未 commit。
- 第 3 节用的是 `build/desktop-gate/Release/PvZ2SHUTTLE.exe`（10:02 构建，晚于 `main.cpp` 9:50 与 `worldmap_view.cpp` 8:54 的改动），不是旧二进制。

## 附录 A：分类脚本（临时，%TEMP% 下，不随仓库提交）

```python
import json, pathlib
gates = json.loads(pathlib.Path('native/generated/world_gates.json').read_text(encoding='utf-8'))
ids = {w['id'] for w in json.loads(pathlib.Path('content/worlds.json').read_text(encoding='utf-8'))}
print(sum(1 for g in gates['gates'] if g['world'] not in ids))  # 62
```
