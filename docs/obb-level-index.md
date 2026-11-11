# OBB 关卡来源索引

`tools/obb/level_index.py` 从 SHUTTLE v4 OBB 的 `PACKAGES` 子组恢复完整文件名，
再关联既有 `pkg_NNNN_*.json`、`WorldData` 地图入口和 `content/levels` 的旧包引用。
它只生成索引，不改写游戏内容。运行结果保存在被 Git 忽略的 `build/obb-index/`。

## 重现

从仓库根目录运行；需要 Python 3.10+，该 OBB 的压缩流另需 `zstandard`。
已有 Python 环境可先安装该依赖，也可用 uv 临时提供：

```powershell
uv run --with zstandard python tools/obb/level_index.py `
  --obb 'D:/OneDrive/文档/pvz_shuttle/main.460.com.ea.game.pvz2_shu.obb' `
  --packages 'D:/OneDrive/文档/pvz_shuttle/work/obb_packages' `
  --output build/obb-index

uv run python -m unittest tools.obb.test_level_index
```

`--legacy-levels` 默认读取仓库的 `content/levels`。`--packages` 必须是
`split_packages.py` 按数据流偏移升序解码出的完整目录，并包含其 `_index.json`。
缺失、重复、不连续的包编号，提取失败，或目录偏移与 4 KiB 对齐 RTON 起点不一致，
都会使生成失败。JSON 内容与原始 RTON 的对应沿用提取器的编号约定；工具不重新解码 RTON。

文件名表使用 32 位字：位 1–7 保存字符编码，位 0 保存分支地址最低位，
位 8–31 保存剩余分支地址。分支保留当前字符之前的前缀，地址以字为单位，
包括奇数地址。目录中的偏移和长度指向解压后的流，不能当作 OBB 文件绝对偏移。

## 2026-11-11 全量核验

输入 OBB：`main.460.com.ea.game.pvz2_shu.obb`，2,095,579,136 字节。
`PACKAGES` 为子组 684，文件偏移 386,752,512，解压数据流 23,191,552 字节。
目录的 2,116 个偏移与提取器使用的全部对齐 RTON 起点逐个一致。

| 核验项 | 数量 |
| --- | ---: |
| 原始包路径 / 已解码 JSON | 2,116 |
| LevelDefinition / 旧目录关卡 | 1,809 / 1,809 |
| 旧 `extra.package` 可关联 | 1,809 |
| WorldData 对象 | 46 |
| 精确匹配的地图 level 事件 / 不重复关卡 | 1,247 / 1,247 |
| 未匹配地图 level 事件 | 1 |
| 全部 RTID：resolved / missing / ambiguous | 54,902 / 130 / 88 |
| 全部 RTID：未建立索引的外部作用域 | 145,698 |
| Modules：resolved / missing / ambiguous / 外部作用域 | 14,811 / 106 / 19 / 1 |

唯一未匹配入口位于 `PACKAGES/WORLDMAPDATA.RTON`，
`/objects/30/objdata/m_eventList/1`：world=`thymedevent`，
event=`thymedevent_level_1`，完整 key=`thymedevent1`。
剩余 562 个关卡没有匹配的 WorldData level 入口；这不表示它们不可从其他模式进入。

目录 SHA-256：`dc4d97d0587af1ce92a48bec0f28b051d031c81f856f366b675ebd0b645c30fc`。
解压 PACKAGES 流 SHA-256：`1811fffebf2a2d894cb55801e63228429c844eab1a0c02e5ebeff66e31dc1140`。
完整 JSON 集合的摘要及每包 JSON 摘要保存在输出中，用于识别输入变化。
全量工具独立运行两次，六个输出文件的 SHA-256 全部一致；六项索引单元测试、
项目的 `tests/test_engine.py` 和 `tests/test_new_screens.py` 均通过。

## 已核实的代表关卡

| 包 | 完整路径 | 模块 / 入口证据 | 旧目录关联 |
| --- | --- | --- | --- |
| `pkg_1996` | `PACKAGES/LEVELS/YOURHOUSE1.RTON` | `SeedBank@CurrentLevel`、`DayStage@LevelModules`；WorldData 实际为 `yourhousex` / `yourhousex_level_1` | `frontyard_1`，`obb` |
| `pkg_0241` | `PACKAGES/LEVELS/APRILFOOLS11.RTON` | `ConveyorBelt@CurrentLevel` → ConveyorSeedBankProperties；`Rails@CurrentLevel` → RailcartProperties；入口 `aprilfools_level_11` | `carnival_17`，`obb` |
| `pkg_0325` | `PACKAGES/LEVELS/BEACH1.RTON` | `Tide@CurrentLevel` → TideProperties，StartingWaveLocation=5；入口 `beach_level_1` | `beach_1`，`obb` |
| `pkg_0290` | `PACKAGES/LEVELS/ARCADE/VASEBREAKER_BEACH1.RTON` | `VaseBreakerProps@.` → VaseBreakerPresetProperties；`Tide@CurrentLevel`，StartingWaveLocation=4；未找到 WorldData level 入口 | `beach_69`，`obb-synth` |

`pkg_0241` 的注释是 “Cowboy 24”，但 archive path 与 `aprilfools_level_11` 一致。
该关的传送带包含 8 个 InitialPlantList 条目、Delay 值为 5/8/9 的 DropDelayConditions，
轨道包含 9 辆 Railcarts；完整参数保存在相应 mechanic 记录中。
`pkg_0290` 的旧转换标记为 `obb-synth`，关联成功只证明旧记录指向这个包，
不能证明旧转换保留了砸罐玩法。

| 本地类定义的机制线索 | 含该线索的关卡 | 其中被 Modules 直接引用 |
| --- | ---: | ---: |
| Conveyor | 350 | 346 |
| Railcart | 199 | 196 |
| Tide | 90 | 76 |
| VaseBreaker | 47 | 47 |

机制按本地对象的类名筛选，并标记 `direct_module` 或 `local_definition`。
仅有定义不保证运行时启用；直接引用也不能替代原版实机行为验证。

## 输出与边界

| 输出 | 内容 |
| --- | --- |
| `summary.json` | 数量、来源摘要、共享重复别名与证据边界 |
| `packages.json` | 全包的精确路径、数据流偏移/长度、JSON 文件名和 SHA-256 |
| `levels.json` | 关卡 key、原始注释、StageModule、Modules、全部 RTID、JSON Pointer、机制参数、WorldData 入口 |
| `unresolved_references.json` | missing、ambiguous、unindexed_scope、malformed；保留原始 RTID 和定位 |
| `unmatched_world_events.json` | 无完整关卡 key 匹配的原始地图事件 |
| `legacy_links.json` | 旧关卡 ID、world、source、extra.package 与精确路径的关联 |

只解析 `CurrentLevel`、`.` 和 `LevelModules` 作用域，保留大小写与原始引用。
未索引的 ZombieTypes 等作用域不等于引用缺失。
例如缺失项包括 `ChooseLilypadsTip@LevelModules`、`Gravestones@CurrentLevel`；
同包重名的 `CA2@CurrentLevel` 等保持 ambiguous，不替调用方选择对象。
共享 LevelModules 有四个重复别名：`PaddysStage`、`LostCityNightsUBStage`、
`LostCityNightsDMGStage`、`RoofNightStage`。

地图匹配只统一路径分隔符和大小写，以 `PACKAGES/LEVELS/` 后的完整相对路径为 key；
不按 basename、注释、StageModule 或 LevelNumber 猜测。
索引不会推断共享模块的动态展开、入口可见性、关卡排序或运行时的重复别名优先级。
