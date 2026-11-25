# S3 阶段计划：行为族与原版表格对接

**Goal**：把 S2 的通用内核接到原版数据上——339 个 `PlantType` / 1127 个 `ZombieType` 逐一找到归属，
每个行为族按 `PlantPropertySheet.Actions` 的真实字段重写，1809 关按原版棋盘尺寸成局。

**Architecture**：`tools/contentc/` 产出「映射表 + 行为参数」，`native/src/engine/` 只读产物；
行为族仍是 C++ 函数，但族内取值全部来自 `ContentPack`，不再有写死在代码里的 1800/20/1.4 之类常数。

**Tech Stack**：Python 3.14（编译器与映射）、C++20/CMake/CTest（内核）、SDL3（视图，S4 才动）。

**Spec**：`docs/superpowers/specs/2026-11-10-native-client-design.md`；上一阶段：`2026-11-20-s2-engine-kernel.md`。

## Global Constraints

- 不 commit、不 push。
- 映射表必须可审阅（`native/generated/id_mapping.csv`），每一行都要有来源证据（表名 + 别名 + `IntegerID`）。
- 找不到对应物的 client id 与找不到 client 的 OBB type 都要**显式列名单**，不许静默丢弃。
- 族内数值优先级：`PlantPropertySheet.Actions` > `content/plants.json` > `tuning.hpp` 常数。
- 未知 `Actions.Type` 仍按 `unknown` 保留并计数，不阻断启动。
- 每批行为族落地都要有 CTest 断言 + 至少 1 个冒烟场景；门禁脚本必须保持 `[ok]`。

## Review Focus

1. 映射是否把「美术复用」误判成「同一植物」（`gatling` 借用 `hollyknight` 的 PopAnim 是反例）。
2. 每个族是否真的按 pack 取数，而不是把 S2 的常数换个名字继续写死。
3. 棋盘尺寸推导是否对 26 个世界都成立，且不破坏已有 5×9 关。
4. `Actions.Type` 里 `special`（200 条）不是一族能覆盖的，需按 `SpecialName` 分类，漏掉的必须进未接线计数。
5. 三星/胜负是否仍只在 `World::resolveOutcome` 一处判定。

## 任务

### S3.0 映射表（先做，其他任务都依赖它）

**Files**：`tools/contentc/mapping.py`、`tools/tests/test_mapping.py`、`native/generated/id_mapping.csv`、
`native/generated/mapping_report.md`

- 输入：`pkg_2074_PlantType`（339）/ `pkg_2115_ZombieType`（1127）与 `content/plants.json`（147）/
  `content/zombies.json`（55）。
- 匹配顺序：① `TypeName` 与 client id 完全相同；② `PopAnim` 去掉 `POPANIM_PLANT_`/`POPANIM_ZOMBIE_`
  前缀后相同；③ `IntegerID` 命中 `almanac.json` 的图鉴号；④ 人工表 `tools/contentc/manual_mapping.csv`。
- 已确认：103 个 client 植物 id 在本版表里不存在（`umbrella/snowlotus/iris/rosemary/wildflower` 子串亦无命中），
  必须写进 `mapping_report.md` 的「client 独有」区，不能靠归一化规则硬凑。
- `NativeId` 产出：`{plant_id → [pack_type...]}`，一对多（如 `heavy_shield` 两条）保留全部。

**Verification**：`test_mapping.py` 断言 147/55 每个 client id 都有归属或落在「client 独有」名单里；
CSV 行数 = 339 + 1127；两次生成字节相同。

### S3.1 棋盘几何

**Files**：`tools/contentc/worlds.py`、`tools/contentc/geometry.py`、`native/generated/board_sizes.json`

- 现状：1809 个关卡 JSON 没有任何 `rows`/`cols` 字段，核心一律 5×9（S2 记录在案）。
- 从 `pkg_2107_WorldData` 的 `m_mapPieces`（每世界 26 条）与各世界关卡定义解出列数；
  行数按世界规则（前院 5、六路 6、矿车关沿用 `extra.minecarts`/`extra.rail` 的 10 关）。
- 产出 `board_sizes.json`：`{world: {rows, cols, source}}`，`source` 记录证据来源；关卡级覆盖优先。

**Verification**：`test_geometry.py` 断言 26 世界全部有尺寸、已知反例（前院 5×9、六路 6×10）正确；
`engine_test` 增 `testBoardSizes`：随机 10 关用推导尺寸开，`rows/cols` 与产出文件一致。

### S3.2 植物动作接线（projectile / sun / explode）

**Files**：`native/src/engine/action_runner.cpp`、`native/src/content/model.hpp`

- `ActionSlot` 已带 `damage/splash/slow/pierce/cooldownTicks/initialTicks`；本任务补齐
  `trigger`（`none/instant/column/row/rect`）、`triggerRect`、`spawnOffset`、`projectileType` 的运行时使用。
- `projectile`：按 `ProjectilePropertySheet` 取速度/穿透/溅射；发射点用 `SpawnOffset`。
- `sun`：用 `CooldownTimeMin/Max` 与 `SpawnOffset`，产出阳光值仍取 `ContentPack`/JSON `sun_value`。
- `explode`：`TriggerType=rect` 用 `RectTriggerRange`，`explodeRadius` 与 `splashDamage` 生效；
  `DieAfterExplode` 决定自毁。

**Verification**：`engine_test` 增 `testPackActions`（sunflower 首次产阳光时间落在 `InitialMinCooldownTime`±1 tick、
peashooter 首发间隔落在 `CooldownTimeMin/Max` 区间、potatomine 只在 `RectTriggerRange` 内触发）。

### S3.3 僵尸行走与 183 个 `ZombieClass`

**Files**：`tools/contentc/zombies.py`、`native/src/engine/registry.cpp`

- `pkg_2111_ZombieWalkActionDefinition`（947 对象）解析成 `{clip, frames, speedScale}`，
  按 `class → family` 表落进 `registry.cpp`；`Steal/Summon/Gargantuar/Jump/Fly` 各自按 `ZombieActions` 引用驱动。
- 未匹配的 `ZombieClass` 进 `unwiredZombies` 计数（当前 0，因为 55 个 client 僵尸都在已知族里）。

**Verification**：`test_zombie_classes`：183 个 class 全部有归属或计数；`kongfu_monk_bucket` 的 hp/speed/eatDps
仍与 pack 一致（190/0.185/100）。

### S3.4 行为族细化（11 族，分 4 批）

**Files**：`native/src/engine/registry.cpp`、`native/src/engine/tuning.hpp`

- 批次 A：`shoot`/`lob`（42+28 植物，含 `pierce`/`splash`/`slow` 组合）——先做，覆盖关卡 deck 的 41 种引用。
- 批次 B：`produce`/`sun`/`instant`/`explode`（16+13）——阳光经济与一次性植物。
- 批次 C：`wall`/`mine`/`chomp`/`fume`/`boomerang`/`spike`（14+4+5+1+3+11）。
- 批次 D：`support`（10 个光环，S2 是空实现）与 `special`（200 条 `Actions.Type=special`，按 `SpecialName` 分类）。

**Verification**：每批结束跑 `engine_test` + 冒烟；`unwiredPlants` 保持 0；每批至少 1 个新断言。

### S3.5 覆盖矩阵与门禁

**Files**：`tools/parity_report.py`、`tools/check_all.ps1`

- `playable` 从 S2 的 0 改为「在冒烟场景里出现过且未进未接线计数」的条目数。
- 冒烟场景扩到 8 个：新增 3 个不同世界的脚本局（含 1 个 6×10）。

**Verification**：`check_all.ps1 -Desktop` 退出码 0；矩阵 `wired` 与 `playable` 都有非零进度。

### S3.6 文档

- `docs/NATIVE_PROGRESS.md` 增 S3 段；`docs/PARITY_BASELINE.md` 增 S3 增量；本文件勾选。

## 进展（2026-11-20 20:40）

- **S3.0 完成**：`tools/contentc/mapping.py` + `manual_mapping.csv` → `native/generated/id_mapping.csv`（1596 行）
  与 `mapping_report.md`。植物 exact 44 / none 295 / client 独有 103；僵尸 exact 20 / manual 8 / none 1099 /
  client 独有 27（其中 2 条代号指向本版不存在的条目）。8 条手工采信均为 `extra.source_codename` 精确命中。
  测试 `tools/tests/test_mapping.py` 覆盖四级匹配与报告分区。
- **S3.1 完成**：`tools/contentc/geometry.py` → `native/generated/board_sizes.json`（26 世界，5778 字节）。
  beach / modern = 6×9，其余 5×9；证据是六道模块 `InitialGridItemPlacements` 的 54 格与
  302/302 个 `BoardGridMapProps`。C++ 侧已接：`CatalogOptions::boardSizes`、CLI `--boards`，
  冒烟逐世界比对文件值（`test_geometry.py` 17 例）。
- **S3.2 完成（首轮）**：`action_runner.cpp` 改为从 `catalog().rules` 读回权威 `Action`，
  应用 `SpawnOffset.x`、`RectTriggerRange`、`CooldownTimeMin/Max`、`InitialMin`、`DieAfterExplode`；
  修掉向日葵双发阳光。未应用：`SpawnOffset.y`（`spawnSun` 无高度参数）、unknown 无计数 API。
- **S3.3 完成**：`tools/contentc/zclasses.py` → `native/generated/zombie_classes.json`（183 条，64130 B）+
  `zombie_family_table.inc`（183 行，6331 B），族分布 walk 129 / gargantuar 29 / summon 10 / fly 8 / jump 6 / steal 1，
  13 条人工覆盖逐条写依据，判不出 0 条。C++ 侧 `engine/zombie_family.cpp` 二分查表，
  `World::spawnZombie` 顺序改为 **class 表 > content behavior > walk**，新测试 `zombie_family` 覆盖表与优先级。
- **S3.4 批次 A 完成**：`registry.cpp` 11 族统一 **pack 槽位 > content JSON > tuning 常量**，
  证据表 `docs/reviews/2026-11-20-family-numbers.md`；26 处仍是带注释的兜底常量，
  `wall`/`support` 因几乎无包内数值，登记为缺口而非造数；新测试 `testFamilyNumbers`（4 族 + 4 条反向探针）。
- **S3.5 完成**：矩阵新增「僵尸 class 族」行，`check_all.ps1` 增加 `zombie classes --check` 步骤；
  冒烟 32 场景（26 世界 + 5 定点 + `beach_23` 胜利）。audit 11/11、desktop 16/16、Python 60 例、门禁 EXIT=0。
- **S3.6 完成**：`CHANGELOG.md` 增「native engine kernel S0–S3」条目；README 原生进度段改写为「数据驱动内核（S0–S3）」并链到 `PARITY_BASELINE.md`/`PARITY_MATRIX.md`。

## 门禁（阶段完成判据）

- [x] 1. 339/1127 全部有归属或显式列入独有名单，CSV 可审阅。
- [x] 2. 26 世界棋盘尺寸有证据来源，`testBoardSizes` 通过。
- [~] 3. 11 个植物族全部按 pack 取数 —— **部分**：机制已改，26 处兜底常量带 `// fallback: tuning constant, no pack evidence`；`wall`/`support` 无包内数值，见 `docs/reviews/2026-11-20-family-numbers.md` 第 4 节。
- [x] 4. `unwiredPlants/unwiredZombies` 均为 0 或全部有名有姓。
- [x] 5. audit 与 desktop 全绿，`check_all.ps1 -Desktop` 退出码 0。
- [x] 6. 冒烟 8 场景双跑哈希一致（实际 32 场景）。

## 与后续阶段的接口

- S4 拿 `board_sizes.json` 开 6×10 视图，拿 `ActionSlot.projectileType` 播投射物动画；
- S5 用 `id_mapping.csv` 定位 235 个 `PlantFramework` 的美术资源缺口（本地只有 32 个 model dir）；
- S6 的挑战/星门直接读 `world_diff.md` 的 97 道门。
