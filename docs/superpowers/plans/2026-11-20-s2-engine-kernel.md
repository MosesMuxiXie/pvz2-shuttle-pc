# S2 引擎内核 v2 — 阶段详细计划

> 上级计划：`2026-11-20-full-native-replica.md` §4。本阶段只做**无图形内核**；渲染迁移属于 S4。

**Goal:** 把 `native/src/simulation.cpp` 里「4 张卡 + frontyard」的战斗替换为数据驱动内核 `native/src/engine/*`，
使**任意** 1809 关中的一关都能 headless 从开局跑到结算，同一输入脚本三次运行状态哈希一致，5×9 与 6×10
场地都能跑，且未注册行为不阻断启动（回落到框架默认并计入覆盖统计）。

**Architecture:** 四个不依赖 SDL 的编译单元组：
`world`（几何/实体池/经济/胜负/hash）→ `director`（波次与权重抽取）→ `action_runner`（把
`content::Action` 翻译成运行时效果）+ `projectile`（弹道积分与命中）→ `registry`（字符串→行为函数，
同时是覆盖矩阵数据源）。`replay` 提供输入脚本与哈希复现。全部通过 `World` 的公共接口驱动，
不暴露内部容器指针给调用方（`Snapshot` 是值拷贝）。

**Tech Stack:** C++20 · 现有 `pvz_catalog` / `pvz_content` · CTest。无新增第三方依赖。

**Spec:** `docs/2026-11-10-native-client-design.md`（三层结构、固定 60Hz、种子+输入可复现）。

## Global Constraints

- 运行期不得依赖 Python/Android；`engine/` 不得 include SDL 头。
- 固定步长 `1/60`，`World::step()` 是唯一时间推进；`advance(seconds)` 只做累加切分。
- 随机只走 `World` 内部的 `std::mt19937`（种子来自关卡 + 可选覆盖），禁止 `rand()`/`std::random_device`。
- 数值来源优先级：`content.pack`（OBB 权威）> `content/*.json`（广度参考）> `engine/tuning.hpp` 常量。
  常量只能出现在 `tuning.hpp`，其它文件不得写字面量调参。
- 未知行为不得抛异常：注册表查不到 → 框架默认行为 + `coverage` 记 `unwired`。
- 关卡引用但 `catalog` 里没有的植物/僵尸类型：`plant()` 返回错误串、生成时跳过并计数，不崩。
- 全部路径 UTF-8（`pathUtf8`），不假设 ANSI 代码页。
- 不 commit / 不 push。

## Review Focus

1. **确定性**：实体遍历顺序、`unordered_map` 迭代、浮点累积都不得影响哈希。哈希前按 id 排序。
2. **几何**：列坐标连续量（列 0 左边界 = 0.0，格心 = col+0.5）；行/列数来自 `LevelDefinition.rows/cols`，
   6×10 关卡的行数与 5×9 一致处理，不得写死 5/9。
3. **越界与负值**：僵尸 x 可为负；`int` 列号与 `double` 列坐标的转换集中在 `World::columnOf/centerOf`。
4. **死亡与清理**：一帧内同一僵尸被多颗子弹命中只结算一次；死亡实体在步末统一清理，避免悬垂 id。
5. **不破坏现有 13 个桌面测试**：`simulation.cpp` 冻结（不再加功能），S4 由 `World` + 新 `BattleView` 取代。

## 任务

### T1 实体与调参表
**Files:** `native/src/engine/tuning.hpp`、`native/src/engine/entity.hpp`

- `tuning.hpp`：`namespace pvz::engine::tuning` 常量组——`kShotSpeedColsPerSec=5.2`、`kShotHitRadius=0.25`、
  `kFirstSkySunTick=270`、`kSkySunIntervalTicks=1440`、`kSkySunValue=25`、`kEatRangeCols=1.15`、
  `kEatStartCols=0.35`、`kMowerTriggerX=-0.25`、`kMowerSpeedColsPerSec=8.0`、`kLoseX=-0.7`、
  `kZombieDeathFadeTicks=18`、`kMaxVictoryGraceTicks=1800`（最后一波后仍无僵尸 30s 判胜）。
- `entity.hpp`：`using EntityId=std::uint64_t`；`struct PlantEntity{id,type,family,row,col,hp,maxHp,born,alive,
  std::vector<ActionSlot> slots}`；`ActionSlot{kind,cooldownTicks,remainingTicks,initialTicks,projectileType,
  damage,count}`；`struct ZombieEntity{id,type,className,row,x,hp,maxHp,armorHp,speed,eatDps,state,alive,
  deathTick,spawnTick}`；`enum class ZombieState{walking,eating,dying}`；`struct ShotEntity{id,row,x,damage,
  speed,pierce,splash,slow,owner,lobTarget}`；`struct SunEntity{id,x,y,row,value,expires,target}`；
  `struct MowerEntity{row,x,state}`；`struct Snapshot{...}`（值拷贝，字段名与 `simulation.hpp` 的
  `Battle*` 保持一致以便 S4 复用视图）。

**Verification:** `ctest -R engine` 编译通过；`entity.hpp` 不 include SDL。

### T2 行为注册表
**Files:** `native/src/engine/registry.hpp`、`native/src/engine/registry.cpp`

- `struct World;`（前向声明）+ `using PlantBehavior=void(*)(World&,EntityId)`、
  `using ZombieBehavior=void(*)(World&,EntityId)`。
- `class Registry{ registerPlant(name,fn); registerZombie(name,fn); plant(name)->fn|default; zombie(...);
  coverage() -> Json }`。
- 通用植物族（字符串即 `content/plants.json` 的 `behavior` 字段）：`shoot`、`lob`、`produce`、`wall`、
  `instant`、`mine`、`chomp`、`fume`、`boomerang`、`support`。每族先用最小可信语义（射速/伤害取植物参数），
  细节留 S3 按 235 个 `PlantFramework` 细化——**族函数内部用注册表二次分派是允许的**。
- 通用僵尸族（`content/zombies.json` 的 `behavior`）：`walk`、`jump`、`steal`、`summon`、`gargantuar`、`fly`。
- 未注册 → `defaultPlant`（有动作则按动作跑，无动作视为 wall）/`defaultZombie`（walk）。

**Verification:** `registry_test` 断言 10 植物族 + 6 僵尸族全部可查、未知名字回落到默认且 `coverage()` 记 `unwired`。

### T3 World 核心
**Files:** `native/src/engine/world.hpp`、`native/src/engine/world.cpp`

- `class World { static constexpr double stepSeconds=1.0/60.0; World(const Catalog&, const LevelDefinition&,
  std::uint32_t seed=1); void step(); void advance(double); std::string plant(type,row,col); bool shovel(row,col);
  bool collect(EntityId); void spawnZombie(type,row); void setSun(int); void pause(bool);
  ... status/tick/sun/wave/cooldown/level/plants/zombies/shots/suns/mowers/snapshot/hash }`。
- `columnOf(col)`、`centerOf(col)` 集中列换算；`rows()/cols()` 取自关卡。
- 阳光：开局 `level.sun`；天空阳光按 `tuning` 节奏落在随机列；`collect` 校验过期与 id。
- 胜负：最后一波生成完且场上无活僵尸 → `won`；僵尸 `x < kLoseX` 且该行小推车已用 → `lost`。
- `hash()`：按 id 升序把 `(kind,id,row,quantized x,quantized hp,...)` 喂 FNV-1a 64；`quantize(v)=llround(v*1000)`。

**Verification:** `engine_test` 的 `testDeterminism`（同脚本三次跑，hash 相同）；`testGeometry`（5×9 与 6×10 各建一关，`rows/cols` 与 `plant()` 边界正确）。

### T4 波次导演
**Files:** `native/src/engine/director.hpp`、`native/src/engine/director.cpp`

- 把 `LevelDefinition.waves` 展平成 `std::vector<ScheduledSpawn{tick,type,row}>`（构造时一次性完成，
  行号 `row` 优先，否则从 `rows` 里按种子抽）。
- `flag` 波：把该波僵尸压缩在 60 tick 内分批入场（原版旗帜波节奏）；最后一批打 `final` 标记供胜负判定。
- 巨型/精英（`behavior` 含 `gargantuar`）额外 +0.5s 出场延迟，避免同帧堆叠。

**Verification:** `testDirector`：1809 关全部可构造 `Director` 且展平后 spawn 数 > 0（含合成关）；
`frontyard_1` 的 spawn 数与 `content/levels/frontyard_1.json` 的 `waves` 求和一致。

### T5 动作执行与弹道
**Files:** `native/src/engine/action_runner.cpp`、`native/src/engine/projectile.cpp`

- `action_runner`：遍历植物 `ActionSlot`，按 `kind` 分派——`projectile`（生成 `ShotEntity`）、
  `sun`（生成 `SunEntity`）、`explode`（范围伤害，支持 `triggerRect`/`radius`）、`special`（转 `registry`）、
  `plantfood`/`manual`/`unknown`（S3 之前只计冷却不产生效果）。
- `projectile`：`x += speed/60`，命中条件 `|shot.x - zombie.x| <= kShotHitRadius` 且同行；
  `pierce` 允许穿透（命中后 `--pierce`），`splash>0` 对相邻行 50% 伤害，`slow>0` 给僵尸减速标记。

**Verification:** `testShotHitsZombie`（单发命中后血量差 == 伤害）、`testPierce`（pierce=2 命中两只）。

### T6 回放与 CLI
**Files:** `native/src/engine/replay.hpp`、`native/src/engine/replay.cpp`、`native/src/main.cpp`

- `replay`：脚本 JSON `{"level":"frontyard_1","seed":1,"inputs":[{"tick":0,"op":"plant","type":"sunflower",
  "row":2,"col":0}, ...]}`；`runScript(World&, script)` 把输入排进 tick 队列；`recordTrace` 输出每 60 tick 的
  `hash`。
- CLI：`--run-level <content> <levelId> [--pack <pack>] [--script <file>] [--seconds <n>] [--trace <file>]`
  → 标准输出一行 JSON `{"level":...,"status":...,"tick":...,"hash":"0x...","spawned":n,"killed":n}`。
- `--simulate` 保留（旧 `Battle`），新增 CLI 不影响它。

**Verification:** `--run-level content frontyard_1 --seconds 240` 退出码 0 且输出含 `"hash"`；同一命令两次 hash 相同。

### T7 门禁脚本与覆盖矩阵接线
**Files:** `tools/check_all.ps1`、`tools/parity_report.py`、`native/tests/engine_test.cpp`

- `engine_test` 增加 `testTwentySixWorlds`：对 26 世界各取 1 关（世界内 `index` 最小者）跑 600s 或至结算，
  断言不抛、`status ∈ {playing,won,lost}`、`hash != 0`。
- `parity_report.py`：`wired` 改从 `engine/registry.cpp` 的注册表符号推导，`playable` 从 `engine_test` 的
  通过关卡数推导（用 `build/engine_matrix.json` 作为输入，缺失按 0）。
- `check_all.ps1`：新增 `--engine` 步骤跑 `--run-level` 冒烟（26 关，单关 ≤2s）。

**Verification:** `pwsh -File tools/check_all.ps1 -Desktop` 退出码 0，输出含 `engine ok`。

### T8 文档与勾选
- `docs/PARITY_BASELINE.md` 增「S2 增量」：内核 26 关冒烟结果、hash 样例、5×9/6×10 证据、未注册行为计数。
- `docs/NATIVE_PROGRESS.md` 增 S2 段；上级计划 S2 步骤勾选；本文件全部任务勾选。

## 门禁（阶段完成判据）

- [x] 1. audit 构建全绿（9/9，含 `engine`），desktop 14/14 不回归。
- [x] 2. 26 世界各 1 关 headless 跑到结算或 120s，无需白名单（`testTwentySixWorlds`）。
- [x] 3. 同一脚本三次 hash 一致（`testDeterminism` + 冒烟双跑比对）。
- [x] 4. 5×9 与 6×10 各 1 关跑通（`testGeometry` + 冒烟 `frontyard_1 6x10`）。
- [x] 5. 未注册行为被计数且不阻断启动（`unwiredPlants/unwiredZombies` 进 snapshot 与 CLI 输出，现存 0）。
- [x] 6. `tools/check_all.ps1 -Desktop` 退出码 0。

## 与后续阶段的接口

- S3 在 `registry.cpp` 里按 `PlantFramework`/`ZombieClass` 增补族实现，不动 `world.cpp`。
- S4 用 `World::snapshot()` 重写 `battle_view.cpp`，随后删除 `simulation.cpp` 与旧 `Battle`。
- S5 音频/美术只读 `Snapshot`，不反向依赖 `engine/` 内部。

## 落成记录（2026-11-20）

全部任务完成。与原计划的偏差（都更小更直接，接口不变）：

- **T1**：`tuning.hpp` 用秒为单位（`kFirstSkySunSeconds=4.5`、`kSkySunIntervalSeconds=24.0`、
  `kZombieDeathFadeSeconds`、`kVictoryGraceSeconds`），由调用点乘 `kStepSeconds` 换算，不另存 tick 常量。
- **T2**：没有 `registerPlant` 动态注册；`registry.cpp` 里是两张静态表（`plantTable()` 11 族、
  `zombieTable()` 6 族）加 `plantFamilies()/zombieFamilies()` 名单，`Registry::shared()` 返回单例。
  比计划多一族 **`spike`**（`content/plants.json` 里有 11 个 spike 植物，否则会落到未接线计数）。
- **T5**：`--trace` 未实现；改为 `--rows/--cols` 覆盖棋盘尺寸（6×10 门禁与 S3 地形试跑要用），
  轨迹用 `hash()` 加 `snapshot()` 代替逐 tick dump。
- **T7**：`playable` 仍为 0（S2 只证明能跑，不证明能赢，胜负平衡留给 S4 校准）；冒烟不是 26 关，
  而是 5 个固定场景（2 个 5×9、1 个 6×10、1 个脚本局、1 个异世界关），26 世界覆盖放在 `engine_test`。

落地文件：

- `native/src/engine/` `tuning.hpp` `entity.hpp` `world.hpp` `world.cpp` `director.hpp` `director.cpp`
  `registry.hpp` `registry.cpp` `action_runner.hpp` `action_runner.cpp` `projectile.hpp` `projectile.cpp`
  `replay.hpp` `replay.cpp`
- `native/tests/engine_test.cpp`（8 组断言）、`native/tests/scripts/frontyard_1_basic.json`
- `native/src/main.cpp` 新增 `--run-level`；`native/CMakeLists.txt` 新增 `pvz_engine` 库与 `engine` 测试
- `tools/engine_smoke.py` 加 `native/generated/engine_smoke.json`；`tools/check_all.ps1` 接入冒烟并改为
  去掉时间戳后比对报告
- `tools/parity_report.py` 的 `wired` 改为解析 `registry.cpp` 行为族表

冒烟哈希（均为 `status=lost`：无人操作时僵尸必然推到底，这正是基线）：

| 场景 | 棋盘 | tick | hash |
| --- | --- | ---: | --- |
| frontyard_1 | 5×9 | 8038 | `0x17bdb328fadcdf25` |
| frontyard_1 扩板 | 6×10 | 9544 | `0x2304afe54f4034a7` |
| frontyard_1 脚本局 | 5×9 | 10019 | `0xc90501d0a626fc12`（杀 30/33） |
| frontyard_6 | 5×9 | 8029 | `0xa0c0d4b0cc15b42b` |
| kongfu_1 | 5×9 | 8785 | `0xe7a3d0ec0ace28e4` |

数据缺口（S3 必须先解决）：`content/levels/*.json` 没有任何棋盘尺寸字段（`rows/cols/board_rows` 全无），
所以 1809 关在核心里一律按 5×9 开。原版 6×10/6×9（海滩、天空、六路等）必须从 OBB 的
`WorldData.m_mapPieces` 或 `LevelDefinition` 里重新解出，S3 的任务表里要为它单列一项。
