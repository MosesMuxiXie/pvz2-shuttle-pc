# 原生客户端基线（S0.1）

生成时间：2026-11-20
仓库：`repo/pvz2-shuttle-pc` @ `24a2493`（未提交变更见文末）
用途：后续每个阶段都与本文档对比。数字变化必须能在计划里找到对应条目，否则就是回归。

## 构建与测试

| 配置 | 命令 | 测试 | 产物 |
|---|---|---|---|
| audit（无图形） | `tools/build_native.ps1 -AuditOnly` | **7/7 通过**（S1 后 **8/8**） | `build/native/Release/PvZ2SHUTTLE.exe` |
| desktop（SDL3） | `tools/build_native.ps1` | **12/12 通过**（S1 后 **13/13**） | `build/native-desktop/Release/PvZ2SHUTTLE.exe` |

- audit 八项：`catalog`、`content`、`cli_audit`、`cli_missing_content`、`cli_unknown_command`、
  `simulation`、`save_import`、`cli_desktop_disabled`。
- desktop 追加：`launcher`、`dragonbones`、`assets`、`text_render`、`battle_render`。
- 日志：`build/baseline_audit.log`、`build/baseline_desktop.log`、`build/s1_audit.log`、`build/s1_desktop.log`。
- desktop 可执行文件（S1 后）：3,511,808 字节，SHA-256
  `304F42CD225E3BA3BE5CA6834395C35B4831CFE1B9DD8F0FF7BC145A875003D0`
  （S0.1 基线为 3,457,024 字节 / `C38C97D2…F30778`）。
- 工具链：CMake 3.31.6（随 VS 2022 BuildTools），生成器 `Visual Studio 17 2022`，x64。
  `cmake` 不在用户 PATH 上，构建必须经脚本。

## 内容审计（`--audit-content content`）

```
worlds=26
plants=409
zombies=55
levels=1809
original=1646
synthesized=163
unknown_source=0
vasebreaker=47
synthesized_vasebreaker=44
```

退出码 0。原始输出保存在 `build/audit_content.txt`。读数按 2026-11-26 复跑刷新：
`plants=409` = 手工 147 + pack 派生 262（t83），`vasebreaker=47` 是 T53 派生后的口径
（旧读数 147 / 45 / 42 已作废；复现 `PvZ2SHUTTLE.exe --audit-content content`）。

## 原版数据规模（`work/obb_packages/`）

| 表 | 文件 | 对象数 | 说明 |
|---|---|---|---|
| PlantType | `pkg_2074_PlantType.json` | 339 | 235 个 distinct PlantFramework，329 个 PopAnim |
| PlantPropertySheet | `pkg_2073_PlantPropertySheet.json` | 398 | Actions.Type：projectile 410 / special 200 / explode 33 / sun 16 / plantfood 6 / manual 1 |
| ZombieType | `pkg_2115_ZombieType.json` | 1127 | 183 个 distinct ZombieClass，539 个 PopAnim |
| ZombiePropertySheet | `pkg_2112_ZombiePropertySheet.json` | 932 | 含 Hitpoints/Speed/EatDPS/WavePointCost |
| ProjectilePropertySheet | `pkg_2082_ProjectilePropertySheet.json` | — | RTID 目标 675 次 |
| PlantFusionConfig | `pkg_2083_PlantFusionConfig.json` | **85**（217 objects / 199 带 objdata / 1 张配置表） | content 85 条与之一一对应，配方键 48 两侧零差集 |
| WorldData | `pkg_2107_WorldData.json` | 46 | 26 个可玩世界 |
| LevelDefinition | `pkg_2000..2047_*` | 48 份 | 合并来源 |

## RTID 覆盖基线（S1.1）

- 别名归一化后，植物 339 条的 `Properties` 引用 **全部解析成功**。
- 僵尸 1127 条：`CurrentLevel` 类 32 条属关卡局部脚本（外部），3 条为原版悬空引用，已钉死：
  `fairy_tale_cavalry_summoned → ZombieFairyTaleCavarySummonedDefault`、
  `renai_armor2_statue → ZombieRenaiArmor2StatueDefault`、
  `renai_perfumer_statue → ZombieRenaiPerfumerStatueDefault`。
- 表尾词法变体：`$ZombieProperties` 25 次、`.` 28 次、`RTID(0)` 10 次、`PropertySheets` 313 次，
  一律经 `normalize_sheet` 归并。
- 未映射 sheet：`GridItemTypes`（`armrack_blade` 不在 `pkg_0024` 里），`ItemGroups`、`EffectObjectTypes`、
  `HeroTypes`、`LevelModules` 同属外部，等 S3 用到时再定位。

## 一致性矩阵

`docs/PARITY_MATRIX.md`（`tools/parity_report.py` 生成）：植物 339/147、僵尸 1127/55、
融合 **85/85**（原记 199 是把带 objdata 的 object 数当对数，已更正）、关卡 1809、世界 26、Boss 26、砸罐子 45、小游戏 45，playable 与 calibrated 全为 0。

## S1 完成后的增量（2026-11-20 晚）

### 内容包（`tools/contentc/` → `native/generated/content.pack`）

- 产物 1,443,766 字节量级，SHA-256 `DF2EE1EFB0AAC2934121D5E72FC0D60B27A729F3525A7EC530CA030F15E84AFF`。
  两次构建字节一致（`--check` 断言）。
- 摘要：`plants=339 zombies=1127 plantActions=668 zombieActionRefs=717 plantsMissingProps=0
  zombiesMissingProps=3 danglingRefs=3 externalRefs=32 unknownActionKinds={'<none>':2}`。
- 动作分类：projectile 410 / special 200 / explode 33 / sun 16 / plantfood 6 / manual 1 /
  无 Type 2（保留 `rawType`，不拒启动）。
- **重复 id**：`heavy_shield`、`kongfu_gargantuar` 各两条（原表 1127 对象 / 1125 唯一 id）。
  游戏用 `ZombieClass` 区分（两条 `heavy_shield` 共用 IntegerID 538），因此打包保留全部记录、
  只统计冲突数（`duplicatePlantIds=0 duplicateZombieIds=2`），C++ 侧索引"首个胜出"并把 id 收进
  `plantDuplicates`/`zombieDuplicates`。
- **词汇表分歧（S3-A 的输入）**：pack 与 `content/*.json` 植物 exact shared 44/147，僵尸 20/55。
  `content` 里 103 个植物 id 在本版 OBB 表中不存在（`twinsunflower/gatling/umbrellaleaf/iris/
  rosemary/snowlotus/wildflower/olivewood/astrofruit/chrysanthea/doominator/helioscabbage` 等），
  归一化规则匹配 0 命中，需手工映射表。

### C++ 装载

- `native/src/content/{model.hpp,loader.cpp,loader.hpp}`：339/1127 严格校验、未知动作 kind 保留、
  `format` 版本校验、错误消息带条目名；`content_test` 8 类用例（含非 ASCII 路径、重复 id 容忍）。
- `native/src/catalog.cpp`：新增 `CatalogOptions{contentPack}`；打包成功时 `Catalog::rules` 指向
  该包并记 `rules=pack … plants=339 zombies=1127 duplicate_ids=2`；打包失败只降级不中断，记
  `rules=json (fallback: …)`。CLI：`--audit-content <content> [rules.pack]`。
- 关卡/世界/卡组仍读 `content/*.json`（id 词汇表未统一前不能替换）。
- 冷启动耗时（`--audit-content content native/generated/content.pack`，三次）：593 / 599 / 964 ms，
  含 147 植物 + 55 僵尸 + 1809 关 JSON 与 339/1127 规则包；在 Review Focus 的 ≤1.5s 预算内。

### 世界差异（`native/generated/world_diff.md`）

- WorldData 46 条 ↔ client 26 个世界：已匹配 **22**，client 独有 4（`frontyard` 由 tutorial+yourhouse
  合并；`future`/`iceage`/`renai` 本版无 WorldData，关卡为合成），WorldData 独有 24（事件/变体世界：
  `tutorial`、`yourhouse`、`yourhousex`(50 关)、`kungfu`(80，与 `kongfu` 不同条目)、三/四/五周年、
  `epicquest` 154 关、`tower` 100 关、`thymedevent`、`lny`、`collab1/2`、`guntime` 等）。
- 事件总数：level 1248、plant 231、star_gate 53、key_gate 27、worldgate 17、giftbox 8、costume 7、
  doodad 6、upgrade 2；门共 97 条，`m_unlockedFrom` 全部指向 `*_stargate_start` 形式。
- 回归测试：`tools/tests/test_worlds.py`（5 例，钉死 46/26/22 与事件计数）。

### 一键闸门（S0.4）

`pwsh -File tools/check_all.ps1 [-Desktop] [-NoContent] [-AllowMatrixChange]`：
内容包 `--check` → audit 构建 + CTest → Python 工具测试（17 例）→ 矩阵生成 → 世界差异生成，
末尾 `[ok]/[fail]` 摘要，退出码 0/1。矩阵与世界差异用"渲染结果对比"而不是 `git status`
（两者都未跟踪），变化即失败，除非显式 `-AllowMatrixChange`。

补充：`tools/parity_report.py` 的 `--obb` 改为默认值（向上查找 `work/obb_packages`），
`tools/contentc/worlds.py` 同样自适应查找；两处都不再要求手写绝对路径。

## 工作树状态

未跟踪：`native/`、`tools/build_native.ps1`、`tools/contentc/`、`tools/parity_report.py`、
`docs/NATIVE_PROGRESS.md`、`docs/PARITY_MATRIX.md`、`docs/media/`、本计划。
已修改：`CHANGELOG.md`、`NOTICE.md`、`README.md`、`docs/superpowers/plans/2026-11-10-native-foundation.md`。
按房规不 commit、不 push。

## S2 增量（引擎内核 v2）

- **构建矩阵**：audit **9/9**（新增 `engine`，0.6–0.9s）、desktop **14/14**。
  - audit exe：495,104 字节，SHA-256 `D530B3CFFCF147E1FE6EDAF0FA77CA266F7274378F551D51F35C7E24FC70FE96`
  - desktop exe：3,613,696 字节，SHA-256 `FA3392C1A78D87649BC705BC54CA1C5704E46052A917555CF80E0AC79FBF2F97`
- **新内核**：`native/src/engine/`（world/director/registry/action_runner/projectile/replay）。
  `simulation.cpp` 的四植物白名单与 `frontyard` 判定只留在旧 `Battle`（桌面视图暂用），
  `--run-level` 走新内核，任意关卡可跑。
- **CLI**：`--run-level <content> <level> [--pack P] [--script S] [--seconds N] [--rows N] [--cols N]`，
  输出一行 `{level,status,tick,hash,spawned,killed,waves,rows,cols,sun,unwiredPlants,unwiredZombies}`。
- **确定性**：同种子同脚本三次 hash 相同；`advance(90)` 与 180 次 `advance(0.5)` 到达同 tick 同 hash。
- **冒烟基线**（`native/generated/engine_smoke.json`，双跑比对，无人操作时必然 `lost`）：

  | 场景 | 棋盘 | tick | hash | 备注 |
  | --- | --- | ---: | --- | --- |
  | frontyard_1 | 5×9 | 8038 | `0x17bdb328fadcdf25` | 放置 0 植物 |
  | frontyard_1 | 6×10 | 9544 | `0x2304afe54f4034a7` | `--rows 6 --cols 10` |
  | frontyard_1 + 脚本 | 5×9 | 10019 | `0xc90501d0a626fc12` | 杀 30/33，最后两面旗漏 3 只 |
  | frontyard_6 | 5×9 | 8029 | `0xa0c0d4b0cc15b42b` | |
  | kongfu_1 | 5×9 | 8785 | `0xe7a3d0ec0ace28e4` | 异世界关 |

- **接线口径变更**：`tools/parity_report.py` 的“接线”不再是 `registerPlant` 调用，而是
  `content/*.json` 的 `behavior` 族是否出现在 `native/src/engine/registry.cpp` 的行为族表里。
  当前：植物接线 **147/147**、僵尸接线 **55/55**（族都在，行为细节待 S3 按 `PlantFramework` 细化）。
  “可玩”仍为 0：S2 只证明跑得动、可复现，不证明能赢。
- **新发现的数据缺口（S3.1 已解）**：`content/levels/*.json` 完全没有棋盘尺寸字段（无 `rows`、`cols`、
  `extra.board_rows`），1809 关在核心里一律 5×9。原版的 6×10 / 6×9 必须从
  `WorldData.m_mapPieces` 或 `LevelDefinition` 重新解出，已列为 S3 的独立工作项。

## S2 缺陷修复轮（2026-11-20 20:40）

审计报告：`docs/reviews/2026-11-20-s2-audit.md`（19 条）；修复台账：`docs/reviews/2026-11-20-audit-fixes.md`。
本轮把 1 blocker + 5 high + 全部 low 修完，medium 修了 4 条、剩 3 条有明确归属（M6 测试收紧、M7 legacy 冻结、M3 语义澄清）。

- **构建矩阵**：audit **13/13**（`engine`、`world_outcome`、`art_audit`、`progress`）、desktop **18/18**、Python **259 tests OK**（下界口径）、`tools/check_all.ps1` 退出码 **0**。
  （本行在 2026-11-20 22:2x 按 round-3 实测改写：audit 11/11 → **12/12**（新增 `art_audit`）→ **13/13**（`progress`）、desktop 16/16 → 17/17 → **18/18**（`progress` 也进了桌面配置）；Python 136 → 172 → 203 → 217 → **259**（`tools/tests` 持续并入 S4/S5 与 armors 用例）。机器可读台账见文末「测试例数台账」一节，由 `tools/check_all.ps1` 的 `== test ledger ==` 步骤逐次比对，写错即红。）
  （本行在 2026-11-20 22:20 按 S4/S5 交付后的现树改写；Python 例数随 `test_fusions.py`(12)、`test_decks.py`(14)、`test_pfamilies.py`(22)、`test_mapping.py`(33+) 增长到 136；早前写 106/60 是当日中间状态；此前记录的 10/10、15/15、50 tests 属当日 20:40 的中间状态，已不可复现——见 `docs/reviews/2026-11-20-audit-fixes.md` 的「第二轮修复」节。）
  - audit exe：512,512 字节，SHA-256 `0AEB3A3A2078F61D6BAE8F96F8EFFDBED3AE1EC4A129445813B0B76AD403DB24`
  - desktop exe：3,630,592 字节，SHA-256 `5630D60B06BB05923648721112069AEE788E944A2DB20B91406D113F09CFDA79`
- **棋盘几何接线**：`tools/contentc/geometry.py` → `native/generated/board_sizes.json`（26 世界）；
  `CatalogOptions::boardSizes` + CLI `--boards` 让 `Catalog` 按世界改写 `LevelDefinition::rows/cols`。
  beach / modern 实测 **6×9**，其余 24 个世界 5×9 —— 冒烟逐世界比对文件值，不符即失败。
  证据：六道模块的 `InitialGridItemPlacements` 恰好 54 格（GridX 0..8 × GridY 0..5），
  其余世界单元格一律落在 GridX 0..8 / GridY 0..4（与 302/302 个 `BoardGridMapProps` 吻合）。
- **冒烟基线**（`native/generated/engine_smoke.json`，32 场景 = 26 世界 + 5 定点 + 1 胜利，全部双跑比对）：
  - 26 个世界各取最低关卡跑 120s：25 个 `playing`（tick 7200），`memorytour` 在 tick 7000 判 `lost`（推车已用仍被突破）；
  - `frontyard_1` 5×9：tick 8038 `0x810daeae75e6004a`；6×10：tick 9544 `0xa7eecce8cd9df22d`；
  - `frontyard_1` + 脚本：tick 9220 `0x54d0952e5f1df175`；`frontyard_6`：tick 8029 `0x6c36c1eb2fe8c506`；`kongfu_1`：tick 8785 `0x072c993b96804fdf`；
  - **`beach_23` + 脚本：tick 1538 `0xde03536c990dee92`，`status=won`** —— 胜利分支现在由 CLI 门禁覆盖（此前只在单测里）。
- **CLI**：`--run-level` 增加 `--boards <json>`；输出新增 `removed / mowerKills / leaked / rejectedSpawns`。
- **矩阵口径**：`playable` 不再是常量 0，改为「被至少一张关卡引用 + 族有实现」的推导值 →
  植物 **41/147**、僵尸 **47/55**；`engine_families` 解析为空即抛错（fail-closed）。
- **工具链**：`tools/build_native.ps1 -BuildDir <path>` 支持隔离构建目录（多智能体并行时不再撞 `.tlog` 锁）；
  `tools/check_all.ps1` 的三个基线改为**生成器之前**读取，门禁不再自愈。
- **仍未修（已登记，不是遗忘）**：
  - M6：`testTwentySixWorlds` 的恒真断言、`testShotsAndEating` 未测啃食 —— 归 S3 测试收紧；
  - M7：legacy `Battle` 与 engine 数值分叉（天空阳光 8s vs 4.5s+24s、推车 -0.25 vs -0.7）—— 归 S4 桌面迁移；
  - M3：有槽位植物整段跳过族行为属设计（槽位执行器优先），矩阵文字已澄清，未改分派；
  - wirer 登记的两条：`SpawnOffset.y` 未应用（需 `spawnSun` 签名变更）、unknown 动作只有事件没有计数 API。


## S3 增量（行为族对接，2026-11-20 21:00）

- **构建矩阵**：audit **11/11**、desktop **16/16**、Python **60 tests**（当时；现树 259）、`tools/check_all.ps1 -Desktop -AllowMatrixChange` 与紧随其后的严格重跑均 **EXIT=0**。
  - audit exe：525,824 字节，SHA-256 `D7BE9EF12FAB52FA6683BC5F9967E42179AE581022697A448D7B69CB6B899532`
  - desktop exe：3,642,880 字节，SHA-256 `532C28CA013939AE1830D7428227D893843E98807508DAFB6DB46963E4954D39`
- **183 个 `ZombieClass` 全部有族**（`docs/…` 台账见 `native/generated/zombie_classes.json` 与 `mapping` 报告）：
  walk 129、gargantuar 29、summon 10、fly 8、jump 6、steal 1；13 条人工覆盖（`ZombieBull` / `ZombieBullVeteran` /
  `ZombieModernPoleVaulting` / `ZombieModernPogo` / `ZombieModernDolphinRider` / `ZombieParkour` → jump；
  `ZombieCakeTank` / `ZombieZombossMech_Goon` / `ZombieZCorpGargantuar` → gargantuar；
  `ZombieZCorpImp` / `ZombieFireball` / `ZombieMausoleumOrb` → walk；`ZombieCarnieMagician` → summon），
  每条都写清依据；判不出的 class 为 0。
- **族解析顺序**（`World::spawnZombie`）：原版 `ZombieClass` 表 > `content` 的 `behavior` > `walk`。
  生成的 `native/generated/zombie_family_table.inc`（183 行，排序、二分查找）由 `tools/contentc/zclasses.py` 维护，
  `tools/check_all.ps1` 的 `zombie classes` 步骤会 `--check` 它是否漂移。
- **植物族数值改为 pack 优先**（`native/src/engine/registry.cpp`）：11 族统一按 **pack 槽位 > content JSON > tuning 常量**；
  有证据的变化——shoot/lob 节奏取 `CooldownTimeMin/Max` 中值、`SpawnOffset.x`；produce 取太阳槽 32–36 s；
  instant 半径取 `ExplodeRadius`；mine 布防窗口取 `RectTriggerRange`（potatomine `[-0.50, +0.583]` 列）；
  chomp 距离 1.42 列（窗右沿）；fume 20 伤害 / 2.425 s / 5 列；boomerang 1.425 s；
  spike 从「每 tick 分摊」改为「每次开火全额」。
  证据表：`docs/reviews/2026-11-20-family-numbers.md`。
- **仍靠 fallback 常量的族**（26 处，均带 `// fallback: tuning constant, no pack evidence`）：
  shoot 1.4 s/20、lob 2.0 s/40/0.5、produce 24 s/25、instant 1.0 s/1800/1.5/0.5、mine 14 s/1800/1.0、
  chomp 40 s/1800、boomerang 3.0 s/20/4.0、spike 20/±0.55。根因是覆盖：147 株里只有 44 株按同名 id 命中 pack、
  41 株带 `Actions`，`wall` 14 株只有 `yuccaguardian` 有动作；`support` 仍是空实现（光环加成属机制，不是数值）。
- **新增测试**：`zombie_family`（183 行表 + 生成优先级 + 客户端独有 id 保留 content 族）与
  `testFamilyNumbers`（fume 首伤 146 tick、spike 单次 10、mine 窗边界 ±0.02 列、chomp 1.2 列外必吞）。
- **矩阵**：新增「僵尸 class 族」行（183/183）；植物 playable 41/147、僵尸 47/55。
- **构建坑（记下来）**：用 `Copy-Item` 还原探针会保留源文件旧 mtime，MSBuild 会跳过重编、拿旧 `.obj` 跑出假结果；
  判据是源码 hash 已回但行为没变，修法是把 `LastWriteTime` 刷新或删 `.obj`。

## S5.9 + S6 数据侧增量（2026-11-21 11:20）

- **弹道接线（t26）**：`native/src/engine/projectile_table.*`（602 条）+ `ShotEntity{trajectory,hitRadius,splashRadius,splashDamage,landX,lobbed}`；
  `spawnShot` 按 `Action.projectile` 名查表，未命中保留 5.2/0.25 并发 `projectile_unknown`（按 id 去重）。
  直接效果：豌豆 5.2 → **5.55 cols/s**（原版直线弹主峰 333 px/s），所有子弹不再偏慢 6.7%。
- **Boss 运行时（t25）**：`native/src/engine/boss.*`，`WorldOptions::boss` 默认开；71 个带 `ZombossBattle` 的关卡里
  `spawned + unavailable == 71`，4 关（`frontyard_67/74/165`、`muji_16`）因为数据里没有 boss，如实计 `bossUnavailable`。
  105 个 fire 类动作只有 58 条带列窗口，其余只计 `boss_action_unwired`；`hash()` 只在有 boss 时追加 `B<…>`，其余世界哈希不变。
- **进度落盘（t33）**：`--run-level … --progress <file>` 终局写档；不传该参数输出**逐字节不变**
  （冒烟 32 场景 sha 前后 `95B0156A1850`）。`beach_23` 干净胜局 = **2 星**（第三颗要 `kill count=10`，该关只 1 只僵尸 = C35），
  这不是实现缩水，是数据事实。
- **S6 数据侧三张表**：`world_gates.json`（97 条门：星门 53 / 钥匙门 27 / 世界门 17，钥匙数 1..5 与星数分离，
  别名 `gta/skycity/rainbowmarket` 归一并列 `worldClient`）、`shop_unlock.json`（585 件；解锁 `none` 484 / `coins` 99 / `world` 1 / `mixed` 1，
  源表无门槛字段，门槛由 price/upgrade 结构推导）、`level_modules.json`（1809 关 14 键，boss 71 与原版 71 完全一致）。
- **冒烟基线刷新**：t26 造成预期内 2/32 条变化（豌豆命中提前、`beach_23` 提前 4 tick 结束），已用
  `check_all -AllowMatrixChange -UpdateLedger` 一次性写入；其余 30 条不变（那些场景没种植物、没子弹）。
- **门禁实证（重要）**：11:18 的 `-AllowMatrixChange -UpdateLedger` 跑 **EXIT=0**（audit 17/17、desktop 22/22、
  `Ran 296 tests`、ledger 三项一致）；紧接着 11:19 严格跑 **EXIT=2**——所有步骤绿，只有
  `[warn] the source tree changed while the gate ran (99903D4DABC4D205 -> 38674AFEE86E8832)`。
  这正是 C44 想要的语义：**别人的半成品在跑门禁期间进了树，所以这一轮不对任何单棵树作结论**。
- **矩阵新增 6 行**（`tools/parity_report.py::compiled_rows`）：弹道 602（接线 593）、护甲 102（接线 0，t29 待做）、
  Boss 71 关 / 50 boss（可上场 49）、世界门 97、商店 585、关卡模块 1809。缺表时不出行，而不是出一行 0。
- **可执行指纹**：`build/native/Release/PvZ2SHUTTLE.exe` 723,968 B SHA-256
  `C53BEA612E406430BC5D07CADABF996C0D204E5FC85641DEBD7C679BFBAF77EA`；
  `build/desktop-gate/Release/PvZ2SHUTTLE.exe` 3,887,616 B SHA-256
  `86B739D30327BC51DAE09DC8702D01AD427B8A1184FAC3E8F4B05D9E8D40E1A6`。

## 测试例数台账（机器可读）

`tools/check_all.ps1` 的 `== test ledger ==` 步骤读取本次运行实测的用例数，与此块逐行比对，
不一致即退出码 1。2026-11-20 一天内数字漂移过两次（11/11 vs 12/12、16/16 vs 17/17：新增测试文件
改了实数、文档留在旧值），所以这里换成可被脚本解析的块，而不是散文里的一句话。

<!-- test-counts -->

| run | tests |
| --- | --- |
| audit | 38 |
| python | 925 |
| desktop | 54 |
<!-- /test-counts -->
## 恢复轮：护甲接线落地 + 构建环境 blocker（2026-11-23 08:10）

- **S5.11 护甲接线（t29）完成**：`native/src/engine/armor.{hpp,cpp}`（102 条，权威层顺序/HP/flags），
  `world.cpp` 的 `armorHp` 改由它建池，`battle_view.cpp:297` 的硬编码 `buckethead?"Bucket":"Cone"`
  改为按 `armors[].art.armorLayer` 取骨骼名。冒烟 **0/32 变化**（32 场景逐条与基线一致）。
- **接住了一个真 bug**：20 个 content 僵尸 id 在 sheet `zombies[]` 有同名行、6 行带甲（`cowboy → CowboyHatDefault`），
  第一版"先查桥、空了再按 id 查 sheet"让 content 僵尸读到 pack 行，冒烟出现 `world cowboy`、`world muji`
  两条变化。改为按 id 空间分流后回到基线；回归用例 `armor_test.cpp::testContentZombieKeepsContentArmor`。
- **构建环境 blocker（不是代码问题）**：恢复后所有构建报
  `CMake Error: No CMAKE_CXX_COMPILER could be found`。真正原因在 `CMakeConfigureLog.yaml`：
  `MSB6001: Item has already been added. Key: 'NO_PROXY' Key being added: 'no_proxy'` ——
  宿主环境块里大小写重复的代理变量让 MSBuild 的 Hashtable 直接抛异常。
  修法：`tools/build_native.ps1` 先把只差大小写的变量名收敛成一份，再用 `ProcessStartInfo`
  以干净环境启动 cmake/msbuild/ctest（PowerShell 的 `&` 会原样传原始环境块）。
- **实测（现树）**：`-AuditOnly -BuildDir 'C:\pvzbuild\resume-audit'` **18/18**（23 s）；
  `-BuildDir 'C:\pvzbuild\resume-desktop'` **23/23**（293 s，desktop 配置此前从未编译过，
  `zombieArmorArmature()` 一次编过）；`check_all.ps1 -NoContent -AllowMatrixChange -UpdateLedger`
  → **EXIT=0**（265 s，audit 18 / python 296 / desktop 23，ledger 三项一致）。
- **矩阵**：护甲行接线数 0 → **91**（102 条里被至少一只僵尸引用的数量）。

## S6.1 世界地图模型 + S5.12 跳跃闭合（2026-11-23 08:35）

**世界地图（队长，S6.1）**
- `native/src/worldmap.{hpp,cpp}`（无 SDL，挂 `pvz_catalog`）：把 `native/generated/world_gates.json`
  （97 条门 = 星门 53 / 钥匙门 27 / 世界门 17）与 `content/worldmap.json`（26 世界）合成
  `WorldInfo{entryStars, hasEntryGate, gateCount, levels}` / `WorldStatus{state, requiredStars,
  requiredKeys, starsSource, reason}`。关卡数从 `content/stars.json` 键前缀数出。
- 三条口径：①`key_gate.m_cost` 是**钥匙把数 1..5**，与星数不同域；②门的名字取 pack world id
  （`rainbowmarket_stargate_start`），匹配同时接受 `<client>_stargate_start`；③"没有门"与"门要求 0 星"
  分开记（`hasEntryGate`），`starsSource` 取 `sheet`/`client`/`none`——实测只有 frontyard 是 client 回落。
- CLI：`--worldmap <content> [--progress <file>]` 输出 26 个世界的 state。存在的理由是避免 C41 重演：
  模型必须有真实调用方，否则单测绿灯只证明它能算。
- 测试：`native/tests/worldmap_test.cpp`（26 世界 / 97 门 / 钥匙≠星 / 三来源 / 状态流 / 三别名）。
- 矩阵新增/更新行：**世界门 97 | 97 | 97**（接线 = `worldmap.cpp`）。

**跳跃证据闭合（wirer，t30）**
- `tuning.hpp` 新增 `kVaultTriggerMaxCols = kEatStartCols + 0.05`（0.40）、`kVaultLandingCols = 0.55`；
  `world.cpp` 窗口改用前者，`zombie_hop` 事件补 `from/to/distance/jump`。
- **反向探针原文**（把窗口改回 `kEatRangeCols + 0.05` → 重建）：
  `engine test failed: a hop must only start at contact: from 5.698667 is outside the 0.400000-column window around 4.500000`。
  收窄后同一跳 `from=4.898667`（窗口内第一个 tick），实测 `hops=1 tick=1764 from=4.89867 to=3.95 distance=0.948667 jump=1`。
- **连带真 bug（已修）**：只收窄窗口会让 `the vaulted plant must survive` 变红——`tickZombies` 的啃食扫描用
  `kEatRangeCols`（1.15）且排在 `tryVault` 之后，旧窗口 1.20 恰好宽 0.05 才让起跳总能抢先；收窄后僵尸在 1.15 列
  被判 eating 停住。处置：**仅 `family=="jump"`** 的啃食 reach 收到 `kEatStartCols`，其它族不变。
- 冒烟 32 场景 **0 diff**（`frontyard_6` 虽含 `pole_vaulter` 但不种植物、无触发目标），基线未刷新。
- 门禁：audit **19/19**、desktop **24/24**、Python **296**；`check_all -NoContent -AllowMatrixChange -UpdateLedger`
  → EXIT=0，随后严格 `check_all -NoContent` → **EXIT=0**。

**指纹（现树）**：`build/native/Release/PvZ2SHUTTLE.exe` 797,184 B
`66AC2504D4AE6E1DB70E9489474FB825C68F1512482CBEC9A1F815DCFF8F5010`；
`build/desktop-gate/Release/PvZ2SHUTTLE.exe` 3,964,928 B
`CD0ED73E0D9605290B6433B0D98F82202BDA5A3CF3C0B0EEEF6E356DCBC6DED2`。

## S6.3 桌面世界地图 screen（2026-11-23 08:55）

- 新文件：`native/src/worldmap_view.{hpp,cpp}`（仅桌面构建）、`native/tests/worldmap_render_test.cpp`。
- CLI：`--worldmap-screen <content> [--progress <file>] [--assets <dir>] [--snapshot <out.png>] [--frames <n>]`。
- 空存档实测输出：

```
{"completed":0,"entered":"","keys":0,"level":"","selected":"frontyard","stars":0,"unlocked":1,"worlds":26}
```

- 测试：`worldmap_render` 断言 26 世界 / `selected=="frontyard"` / `unlocked>=1` / `completed==0` /
  截图恰 1280×720 且采样色 ≥300 / 两跑字节一致 / 缺 `ui/font_zh.ttc` 抛错。
- 门禁：`C:\pvzbuild\wm1` audit **19/19**；`C:\pvzbuild\wm-desktop` desktop **25/25**；
  `check_all -NoContent -AllowMatrixChange -UpdateLedger` 与严格 `check_all -NoContent` 均 **EXIT=0**
  （台账 `audit 19 / python 296 / desktop 25`）。
- 产物指纹（`build/native` 与 `build/desktop-gate`）：

| 配置 | 字节 | SHA-256 |
| --- | --- | --- |
| audit | 798,720 | `F1AAD0FEFD063B8E693608E9731890E659B0E9162ED580D59567FEAD37D0C038` |
| desktop | 3,994,624 | `7E17CE2E11631DCD585A228ABE1CFCFA791DD8ECD85BCC52292F832FCDE9CB01` |

## S6.2 商店模型（2026-11-23）

- 数据：`content/shop.json` 585 条 + `native/generated/shop_unlock.json` 585 条，`missingRows=0`。
- 引擎：`native/src/shop.{hpp,cpp}`（`pvz_shop` ← `pvz_progress`），`Progress::purchases` 持久化。
- 口径：**商店不铸世界钥匙**（唯一 `world` 门是埃及彩罐包）；gem/mint 计价 479 条一律拒绝；
  6 条 free 行出厂均 `implemented=false`，故拒绝而非白送；`one_time=false` 的 43 行不再被
  ownership 拦（N2），但其中非 `plant_id` 产物仍拒绝（N3）。
- CLI：`buyable=21 / unmodelledCurrency=479 / missingRows=0`；`--buy seed_iris` 扣 500 币并授予 `grantedSeed=iris`（`Progress::seeds`）。buyable 只数产物可发放的行（`payload.plant_id`）——收币却发不出东西的行一律拒绝。
- 矩阵：商店行 `wired=585`。
- 指纹：audit `build/native/Release/PvZ2SHUTTLE.exe` 839,168 B
  `42EE9647F13B86042DF0232D3E8A3CA10AD7ECE6F757E3E2B075001FFB8CC821`；
  desktop `build/desktop-gate/Release/PvZ2SHUTTLE.exe` 4,028,928 B
  `5BC6581A81410CD566568BBB2DA7829864715C61E76B63679921DDF9DEF82975`。
- 门禁：audit 20 / python 296 / desktop 26；严格 `check_all -NoContent` **EXIT=0**。

## 关卡机制 / 铁轨 / 经济 / 保护目标（2026-11-24 14:20）

这一轮四件事都落在「原版有、客户端没有」的缺口上，门禁数字随之上移。

- **T51 关卡机制接线**（wirer）：新 `native/src/engine/mechanics.{hpp,cpp}` 读
  `level_mechanics.json`（1809 关，4,827,318 B / sha256 `9F33A09E…0887`），接线传送带（350 声明 /
  348 能建槽 / 349 有槽表）、初始植物（272 关）、初始场地物件（690 声明 / 583 可摆）、墓碑、
  保护植物（286 关，存活 < `mustProtectCount` 才判负）；其余机制发 `mechanic_unknown{kind,count,tier}`。
  矩阵「关卡机制」行 **wired=903**（1245 关至少带一类机制，903 关的机制全部被引擎消费）。
- **T53 铁轨/砸罐子标记可复现化**（mapper）：三个标记改为 `tools/obb_build_content_v2.py` 派生并写回
  content —— vasebreaker **45→47**、minecarts **10→190**、rail **10→192**（`--content-report` 零差异）。
  `native/tests/catalog_test.cpp` 的 `overlapping mode counts` 随数据改为 **47 / 44**。
  矩阵新增「铁轨」行（192/192，`wired=0`：引擎零消费 rail）、「砸罐子」行改按 `extra` 现算（47/47）。
- **T55 经济闭环**（wirer）：新 `native/src/rewards.{hpp,cpp}` 读 `rewards_from_pack.json`
  （575 行 / 336,895 B / sha256 `7F83E66B…8E8C`）—— 击杀周期金币（银 2 杀、金 40/60 杀）、8 条钥匙行
  （按 world + `keysUnlocked()`）、36 张午餐盒（13 张悬空表不发且 `presentTableMissing`）、76 条种子包
  （按 `extra.package` 匹配、`DropChance` × `weight`）。矩阵新增「掉落」行 **575 / 575 / wired=130**
  （金币 46 + 钥匙 8 + 种子 76 已落地，其余 445 行发 `reward_unmodelled`）。逐关绑定缺失见 C56。
- **T57 protect 多模块合并**（artifex）：`extract_protect` 改遍历全部模块，`lostcity_46` 由 2 株变 **9 株 / must 4**；
  `failWhenProtectedPlantDies` 标 `client-default`；新增 `counts.protect` 审计块（287 模块 / `mustGtDistinct` 5 关）。
- **T59 保护容量不足可见**（wirer）：`placed < must` 的 **11 关**在开局发
  `protect_capacity_shortfall{level,placed,must,delta}`，`--run-level` 只在保护关出
  `protectPlaced`/`protectCapacityShortfall`（`egypt_74` → 3/True、`carnival_79` → 0/True、`beach_88` → 5/False、
  `frontyard_1` 两键缺席）。探针改 `<=` → `mechanics test failed: an exact fit is not a shortfall`。

**冒烟**：32 场景相对上一版基线 **13 条变化** —— 8 个世界 index-1 关卡开局有初始场地（只 hash 变）、
`frontyard_6` 只 hash 变、`beach_23 win` 只 hash 变（`initialPlants=4`，tick 1536）、`renai` 变 `lost`
（5 株全保任务，空脚本被啃 → `protect_failed`，tick 3364）。基线已按这一版刷新。

**门禁修复**：`tools/check_all.ps1` 的 `Get-TreeStamp` 之前把 `tools/__pycache__/*.pyc` 也算进树指纹，
而门禁自己会跑 Python 套件 → 每次静树跑都自报 `[inconclusive]`。已加 `__pycache__` / `*.pyc` 过滤，
静树上实测 **EXIT=0**。

**读数**：audit **27/27**、python **426**、desktop **36/36**，三项 ledger 一致；严格 `check_all -NoContent` **EXIT=0**。
指纹：

| 配置 | 字节 | SHA-256 |
| --- | --- | --- |
| audit | 1,151,488 | `3D359952CB564DE0301A775BBB91C77C6837723A52730EB40EBDC0DA7385E332` |
| desktop | 4,413,952 | `0A543A7CFF1CC949943F0A543FB3DE24E0E0147F1E1D603E9AE3E1B6A1EDBFA2` |


## 数据包对齐 460.9（2026-11-24 20:55，P0/P2 完成）

**版本真相**：我们手上 `main.460….obb` 的 MD5 `be21c6f0fe29ff243aaeaad2ca551833` 就是官方 **460.1**（不是 460.9）。
最新三元组 = 游戏 **26.11.1** / 核心库 **460.11** / 数据 **460.9**（`down.pvz2shuttle.cn/manifest.json`）。
全渠道都没有完整 460.9 OBB，官方只供 460.1 基础包 + 两枚 `.rsbpatch`，所以走补丁升级。

| 跳 | 产物 | 字节 | MD5 | 与 manifest |
| --- | --- | --- | --- | --- |
| 460.1→460.2 | `work/versions/460.2.obb` | 2,095,579,136 | `7a219bb7fbfd54b4176aa33e48704b48` | 逐字相同 |
| 460.2→460.9 | `work/versions/460.9.obb` | 2,096,463,872 | `2963d0781e4715522cb12bc2d3bb9f8e` | 逐字相同 |

补丁解码器已复刻为纯 Python：`tools/rsbpatch.py`（35 例，含两窗口自引用回归与 `chain` 跨跳互校），独立 oracle `tools/emulate_rsb.py`（unicorn，13 例）。
容器/报文/VCDIFF/装配算法记在 `docs/superpowers/plans/2026-11-24-obb-460.10-rebase.md` §6.2–§6.5。

**差量**：两棵包树都是 2116 包、零增零删，只有 6 个文件变（`rebase_diff.py`，明细 `work/rebase_diff_460_1_vs_460_9.json`）：
两条 `LawnStringsData` 各 +1 条 `ELEMENT_7_WAVEMASSAGE`、`pkg_0234` 加 `RlConfig`、`pkg_0415` 的
`WaveStartMessage` 键化成 `[ELEMENT_7_WAVEMASSAGE]`、`pkg_0416` 加 `SuppressFlagZombie`、
`pkg_2101` 的 `ThymedEventSchedule` 27→30。**植物 / 僵尸 / 弹道 / 护甲 / 关卡波次一字未变。**

**树切换**：`work/obb_packages` → `obb_packages_460_1`（归档），`obb_packages_460_9` → `obb_packages`；
`PVZ2_OBB_DIR` 为切树开关（12 处统一读）。切换后 12 个 compiler `--check` 全 exit 0，
`obb_build_content_v2.py --content-report` → `mismatches: none`。

**产物重生成**：`level_mechanics.json` 仅 `egypt_25.spawners.spider[0].waveStartMessage` 变化（4,827,318 → 4,827,308 B）；
`rewards_from_pack.json`、`spawn_offsets.json` 只换 `generatedAt` 墙钟戳；
`world_gates.json` 因 `generated` 取 WorldData 的 mtime 必须重生成 → sha256 `7d369cedf5c079be7c830a17e0e8cbea6cfcc763287dbcc72d9fc21dea9e76b8`。

**门禁（本次，含 content 全量）**：`check_all.ps1 -AllowMatrixChange -UpdateLedger` → **EXIT=0**
（audit 27/27、python 439、desktop 36/36、三项 ledger 一致、`[ok] content, build, tests and parity are consistent`）。
C++ 二进制未变（数据侧 rebase）：audit 1,151,488 B `3D359952…E332`；desktop 4,413,952 B `0A543A7C…BFA2`。

### 460.9 消费端接线（2026-11-24 21:25，t64 + t65）

`SuppressFlagZombie` 从数据走到了玩法，这条路完整了：

- **content**：`content/levels/*.json` 的 `extra.suppressFlagZombie` **271 关**（true 215 / false 56），
  每个文件只多一行；`--content-report` → `suppressFlag=271(true 215)` / `mismatches: none`。
  连带 `levelextra.py` 的 `KEY_SPECS` 多一条 → `level_modules.json` 键数 14 → **15**（flagOnly 7）。
- **引擎**：`extra.suppressFlagZombie` 为真时 `flagDropped = spawn.flag && suppressFlagZombie_`，
  波标记被丢掉但僵尸照常生成，每波首次命中发 `flag_wave_suppressed{wave,level}` 并计入 `flagSuppressed()`。
  **内核本来没有旗子僵尸实体**（`flag` 只是波标记 + `director.cpp:38` 的 1.0 s 铺开窗口），
  所以这不是"补一个僵尸"，而是"去掉标记"；铺开窗口本次未动。
- **CLI**：`frontyard_75` → `"flagSuppressed":1,"waves":1,"spawned":1,"status":"playing","tick":1800`；
  `beach_83`（false）与 `frontyard_1`（无键）没有该键。
- **探针**：`flagDropped` 恒 false → `mechanics test failed: each flag wave must be counted exactly once, got 0`。

### 门禁（2026-11-24 21:28，静树，全量含 content）

`pwsh -File tools/check_all.ps1 -AllowMatrixChange -UpdateLedger` → **EXIT=0**

- audit **27/27**、python **469**、desktop **36/36**，三项 ledger 一致；
- `[ok] refreshed docs/PARITY_MATRIX.md`、`worlds obb=46 content=26 matched=22`、`gates star=53 key=27 world=17`、
  `[ok] content, build, tests and parity are consistent`；
- `smoke` 32 场景 **0 变化**（波标记不进 hash）；
- 指纹：`build/native/Release/PvZ2SHUTTLE.exe` 1,152,512 B `48CDEB02AADFA4CB722B5070FA8E706F1F607D8A7BB5BE0DC711C20841A26BF7`；
  `build/desktop-gate/Release/PvZ2SHUTTLE.exe` 4,414,976 B `5ACB9D7027532790AD4FD5182CABDC90172868DA01CB02598AE038DA81DAA2AE`。

## 打包（S7，2026-11-25 19:0x）

七件事的落地状态：

| # | 事项 | 状态 |
| --- | --- | --- |
| 1 | CMake `install()` 树 | ✅ exe / `content/`（2636 文件 12.9 MB）/ `generated/*.json`（31）/ `assets/ui`（12 文件 26.6 MB）/ 文档 |
| 2 | 版本号单一来源 | ✅ `project(... VERSION 0.1.0)` + `PVZ_DATA_VERSION=460.9`，`--version` 打印 `PvZ2SHUTTLE 0.1.0` / `data 460.9` |
| 3 | 资源查找顺序 | ✅ `PVZ_ASSET_ROOT` → exe 目录 `assets/` → 向上搜；生成表 `content` 同级 `generated/` → `native/generated` |
| 4 | 存档目录策略 | ⬜ 仍按 `--progress` 显式路径（默认不写盘），未引入 `%APPDATA%` |
| 5 | `LICENSES.md` 生成 | ✅ 由 `NOTICE.md` 逐字生成（4000 B，含版本行） |
| 6 | README 命令表 | ✅ 十条命令 + 资源查找 + cache 变量坑 |
| 7 | `tools/package.ps1` | ✅ 见下 |

`tools/package.ps1` 实测（`-SkipBuild` 复用已构建目录）：

```
860b011b41e993a537e004109c37e2dcef195c32b6d4c48644cac77b27312751  PvZ2SHUTTLE-0.1.0-win64.zip  20.8 MB
=== 无源码树冒烟（解压到临时目录再跑）
  [ok] --version exit=0
  [ok] --worldmap exit=0
  [ok] --run-level beach_23 exit=0
  [ok] --menu --frames 2 exit=0
  [ok] 主菜单截图 31,949 B
  [ok] generated/ 31 个 json
```

三条踩过的坑（都写进脚本注释）：

1. **cmake 不在 PATH**：`package.ps1` 首跑 `The term 'cmake' is not recognized`。补 `build_native.ps1` 的
   同一条搜索链（PATH → vswhere 的 VS 目录），并清 `HTTP(S)_PROXY`/`NO_PROXY`/`ALL_PROXY` 与
   `MSBUILDDISABLENODEREUSE`，否则 FetchContent 走代理、复用节点带旧环境。
2. **`assets/` 缺失导致 `--menu` 失败**：第一版 `install(DIRECTORY .../PvZ2SHUTTLE/assets)` 指向
   `repo/pvz2-shuttle-pc/PvZ2SHUTTLE/assets`，真实素材在**工作区根**（4835 文件 4.62 GB）。决定只装 `ui/`
   （26.6 MB）——四屏都要 `ui/font_zh.ttc`，4.6 GB 美术仍靠 `PVZ_ASSET_ROOT`。
3. **`PVZ_ASSET_SOURCE` 是 cache 变量**：素材树位置变了但 `build/package` 里还是旧值 → 装出来的树没有
   `assets/`。`package.ps1` 现在每次显式传 `-DPVZ_ASSET_SOURCE=...` 并在缺 `ui/font_zh.ttc` 时直接 throw。
4. **冒烟断言写错字面量**：`--menu` 的输出是 `{"choice":...}` 不是 `menu`，第一版把一条本来通过的用例判红；
   现在断言 `"choice"` 并额外校验截图字节数 > 1000。

另一个真 bug（打包才暴露）：`main.cpp` 五处用 `content.parent_path()/"native"/"generated"` 拼生成表路径，
install 树里表在 `generated/`（与 `content/` 同级），**装好的包读不到任何表**。修法见 README 的资源查找顺序。

**未完成**：存档目录策略（第 4 项）仍留 `--progress` 显式路径；`-IncludeAssets` 只做 junction，不验证运行时。

### 打包最终读数（2026-11-25 19:26，清空 `build/package` 后的全量跑）

```
5789cab5db451a2e9f1b21e6b1fbd4ec05e95be5e6d05f7dcc078513dc28c0b9  PvZ2SHUTTLE-0.1.0-win64.zip  20.9 MB
  [ok] --version exit=0
  [ok] --worldmap exit=0
  [ok] --run-level beach_23 exit=0
  [ok] --menu --frames 2 exit=0
  [ok] 主菜单截图 31,949 B
  [ok] generated/ 31 个 json
```

zip 的 sha256 在两次干净构建之间会变（PE 头里的时间戳与 PDB 路径进二进制），**只有 zip 内部的
`content/` 与 `generated/` 是逐字节可复现的**；要校验「是不是同一次构建」，看 `--version` 与
`generated/` 的 json 数，不看 zip 的 sha。

用打包出来的 exe（`dist/PvZ2SHUTTLE-0.1.0/`）+ 本机素材树实测：

| 命令 | 结果 |
| --- | --- |
| `PVZ_ASSET_ROOT=<workspace>/PvZ2SHUTTLE/assets` + `--menu content --frames 2 --snapshot m.png` | `{"choice":"worldmap"}`，1280×720 PNG 31,949 B，中文正常（`font_zh.ttc` 来自包内 `assets/ui/`） |
| 同上 + `--battle-snapshot content <assets> b.bmp` | `battle_preview=ok`，1280×720 RGBA 3,686,538 B，**真实美术**（向日葵/豌豆射手/坚果墙/土豆雷、僵尸、割草机、草坪格子都在） |

门禁（同轮，`check_all.ps1 -AllowMatrixChange -UpdateLedger`，静树）：audit **29** / python **677** /
desktop **38**，三项 ledger 一致，`[ok] content, build, tests and parity are consistent`，EXIT=0。
新增门禁步骤：`vasebreaker` / `minigames` / `loot binding` / `metagame` / `plant playable` / `plant levels`
六条编译器 `--check`。

### 源码树未进 git（阻塞「干净 clone 重建」）

`git rev-parse --short HEAD` = `24a2493`，`git status --porcelain` **788 项**（358 个未跟踪文件、20.2 MB）；
`native/`、`tools/`（含 `contentc/`、`tests/`、`package.ps1`、`rsbpatch.py`）、`docs/`（含 53 篇 review 与全部计划）、
`content/levels/*.json` 全在其中。`.gitignore` 只忽略 `build/ dist/ *.exe *.zip assets/ *.obb`，
所以 20.2 MB 就是可提交体量（最大单件 `level_mechanics.json` 4.60 MB）。**未执行 commit**：等所有者决定。


## 名册 409 与可玩 304（2026-11-26）

名册口径在本轮从 147 走到 409，中间报过 293 可玩 / 46 阻断（美术索引重建前）与 304 可玩 / 35 阻断（重建后）。
**当前值只有一个来源：产物本身，不许手算。**

| 读数 | 值 | 命令 |
| --- | --- | --- |
| `content/plants.json` | **409 行** = 手工 147 + pack 派生 262 | `python tools/obb_build_content_v2.py --content-report` → `plants=409 authored=147 pack=262 playable=304 blocked=35 conflicts=44 merged=409 packRoster=339` |
| `native/generated/plant_playable.json` | 可玩 **304**（42 同名 + 262 新增）、阻断 **35**（缺成本 23 / 缺美术 15 / 两者 3） | `python tools/contentc/plant_playable.py --check` |
| `native/generated/plant_blocked.json` | **35 条**，带中文 `reason`、`inRoster`、`inPackRoster` | `--check` 同一次运行比对（两文件一起校验） |
| `native/generated/level_playability.json` | `levels=1809 playable=1340 dataOnly=454 minigame=16 both=1 inEngine=1225` | `python -c "import json;d=json.load(open('native/generated/level_playability.json',encoding='utf-8'));print(d['counts'])"` |
| 美术索引 | **1135 base / ok 1134 / failed 0 / skipped 1** | `PvZ2SHUTTLE/assets/db/shuttle/index.json` 的 `counts` |
| 内容植物命中美术 | **134 / 409，缺 275** | `PvZ2SHUTTLE.exe --art-audit content` 的 `contentPlants` |
| 卡组注册表覆盖 | **134 / 409**（deck 实际引用 41 株） | `python tools/contentc/decks.py` → `registry=134/409` |
| 测试例数 | 见文首 `<!-- test-counts -->` 块（audit 36 / Python 891 / desktop 38） | `ctest --test-dir build/native -N`、`python -m unittest discover -s tools/tests -p "test_*.py"` |

| run | tests |
| --- | --- |
| audit | 38 |
| python | 925 |
| desktop | 54 |
