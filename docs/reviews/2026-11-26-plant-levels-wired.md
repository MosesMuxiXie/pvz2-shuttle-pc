# B1（T90）植物等级接进战斗数值

状态：实现完成，`plant_level` 测试通过（ctest `1/1 Passed`），默认运行零差异；反向探针见 §7.3。
作用域：`native/src/engine/plant_levels.{hpp,cpp}`（新增）、`world.{hpp,cpp}`、`action_runner.cpp`、
`native/src/progress.{hpp,cpp}`、`native/src/main.cpp`、`native/tests/plant_level_test.cpp`（新增）、
`native/CMakeLists.txt`。未改 `content/**`、`native/generated/**`、`tools/**`。

---

## 0 结论

1. **等级真的进了战斗**。植物的 `Hitpoints` / `Cost` / `PacketCooldown` 与攻击伤害都在**查表之后**按等级取
   该级绝对值，四条路径各有一个接线点（§2）。伤害这条同时覆盖普通射击与爆炸两条调用链（`packDamage()` 是共用入口）。
2. **默认运行逐字节不变**。不设等级时 `plantStatsOf()` 与 `levelDamage()` 在**任何一行**上都不返回新值，
   因为守卫要求「梯子第 1 级 == 引擎当前值」才动手（§3）。这条不是「碰巧没触发」，是可核对的假设。
3. **133 株有等级的植物里，106 株能被等级改动，20 株被守卫拒绝，7 株不在 content 里**。拒绝不是 bug：
   这 20 株的梯子第 1 级与 `content/plants.json` 的数字不一样（沿用来的 pack 数字来自另一列，见 §1.3）。
   把「哪 20 株」写成清单，比假装全都支持更有用。
4. **`levelCount` 取数组长度，不取 `levelCap`**。99 株的 `levelCap` 与 `levels[]` 长度不一致（`sapfling1` 报 cap 1 却有 10 层），
   数组才是可用的那一维（§4）。
5. 等级来源本轮只有 `--set-plant-level <id>=<n>` 一个显式入口 + `Progress::plantLevels` 存档字段；**没有**花盆掉落、
   升级材料、UI（§8）。

---

## 1 数据形状

### 1.1 表

`native/generated/plant_levels.json`（821,708 B，T78 交付，本次只读）：

```
顶层键：counts / format / generated / levelupOffer / mechanism / plants / searches / sources / unknowns / upgradeHooks
plants：323 株；其中有等级（levels 非空）的 133 株
plants.<id>：{ levelCount, levelCap, levelCountSource, statsLevelCount,
               statNames:[...], levels:[{level, stats:{<statName>: number}}] }
```

### 1.2 是逐级绝对值，不是曲线

`Values[i]` 就是第 `i+1` 级的值，没有插值、没有百分比。三株原样（`levels[].stats` 摊平）：

| plant | levelCount | 关键列 |
| --- | --- | --- |
| `peashooter` | 3 | Hitpoints `[300, 300, 500]`、Cost `[100, 75, 75]`、PacketCooldown `[5, 5, 5]`、`ActionDamageNormal@2` `[30, 35, 45]` |
| `sunflower` | 3 | Hitpoints `[300, 350, 500]`、Cost `[50, 40, 30]`、PacketCooldown `[5, 4.5, 4.5]`，**没有阳光产出列** |
| `blockoli` | 10 | Hitpoints `[6000, 7000, 8000, 9000, 10000, 11000, 12000, 13000, 14500, 16000]`、Cost `[150, 125, 125, 125, 100, 100, 100, 100, 100, 75]` |

`peashooter` 的第二级 HP 仍是 300、Cost 反而下降 —— 这正是「绝对值」的形态；任何「每级 +X%」的实现都会算错。

### 1.3 `@<SubType>` 是什么

同一个 stat 名可以有多列，列号来自 OBB 的 `FloatStats[].SubType`。`peashooter` 在 `pkg_2069_PlantLevelStats.json` 里：

```
Cost               [100, 75, 75]
PacketCooldown     [5, 5, 5]
Hitpoints          [300, 300, 500]
ActionDamageNormal | SubType 0  [20, 25, 40]
ActionDamagePF     | SubType 1  [20, 25, 40]
ActionDamageNormal | SubType 2  [30, 35, 45]
ActionDamagePF     | SubType 3  [30, 35, 45]
ActionXVelocity    | SubType 0  [333, 533, 733]
PlantTier          [1, 2, 3]
```

`tools/obb_build_content.py:657-666` 的 `refresh_plant_stats()` 是 `flat[Name] = Values[0]`，同名后写覆盖 →
`content/plants.json` 里 `peashooter.damage = 30` 来自 **SubType 2** 那一列。加载器因此把「伤害列」选为
**最大数字后缀**那一列（`plant_levels.cpp` 的 `damageColumn()`），与 content 的实际取值一致；
`leveledValue("peashooter", "ActionDamageNormal@2", 3, 30)` 才会返回 45。

---

## 2 插值公式与接线点

公式（`leveledValue()`，`plant_levels.cpp`）：

```
value(type, stat, level, current) =
    if level <= 1:                 nullopt            （1 级不动，默认运行零差异的来源）
    if 表里没有 type:               nullopt
    if 梯子没有 stat 列:            nullopt
    if 梯子第 1 级 != current:      nullopt            （身份守卫，§3）
    else:                          ladder[min(level, levelCount) - 1][stat]
```

四个接线点，全部在**查表之后**（先拿到 pack/content 的原值，再按等级覆盖）：

| 数值 | 接线点 | 说明 |
| --- | --- | --- |
| HP | `native/src/engine/world.cpp:803` | `plantStatsOf()` 里覆盖 `stats.hp`，`constructPlant()` 用它设 `hp`/`maxHp` |
| Cost | `native/src/engine/world.cpp:804` | 同上，覆盖 `stats.cost`（`plant()` 与融合配方共用） |
| 冷却 | `native/src/engine/world.cpp:805-807` | 同上，覆盖 `stats.recharge` |
| 伤害 | `native/src/engine/world.cpp:817`（`World::levelDamage`）+ `native/src/engine/action_runner.cpp:135` | `packDamage()` 在 plant-food 倍率**之前**调用；射击与爆炸都从 `packDamage()` 出发 |

`plantStatsOf()` 原本是两个出口（content 命中 / pack 命中），本次改成单出口，等级覆盖写在出口前 —— 这样两条数据来源
都不会绕过去。`World::plantLevel()`（`world.cpp:812`）返回 clamp 后的请求值，`World::levelDamage()`（`world.cpp:817`）
是伤害侧的同一个守卫。

表本身：`PlantLevelTable`（`plant_levels.hpp`）与 `RailTable` 同款 —— `kFileName = "plant_levels.json"`、
`shared()` 缓存、`load(path)` 用 `std::ifstream` + `<nlohmann/json.hpp>`，坏文件抛
`"plant level table: <path>: <reason>"`。**唯一的刻意差异**：`generatedDir()` 为空或文件不存在时 `shared()`
返回**空表而不抛**，因为每次建植物都会读它，单元测试用手工 catalog 时不能被 generated tree 绑死；文件存在但解析失败仍然抛。

---

## 3 身份守卫（本任务最重要的设计）

规则：`leveledValue()` 只有「梯子第 1 级的值 == 引擎此刻持有的值」时才返回该级值，否则放弃。
理由：`obb_build_content.py` 的 flatten 是「同名后写覆盖」，所以**今天的 pack 数字就是第 1 级数字**。
把这条当成可核对的假设，等于给「等级接线」加了一个自动断言：

* 假设成立 → 该植物的梯子可用，`level=2..N` 直接取绝对值；
* 假设不成立 → 说明这株的 pack 数字来自别的列（多数是 `@SubType` 的另一列），此时**保持原值**而不是套一个错的梯子。

副产品：`levelDamage()` 因此是**幂等**的。`slot.damage` 一旦被改成第 3 级的值，再传进来时守卫会拒绝（因为不再是第 1 级），
所以射击链和爆炸链可以各自调用一次而不会叠加。

### 3.1 三类分账（133 株）

| 类别 | 株数 | 含义 |
| --- | --- | --- |
| guard accepts | **106** | 梯子第 1 级与 content 一致，设等级即生效 |
| guard rejects | **20** | 梯子第 1 级与 content 冲突，设等级**不改变数值**（原因在下表） |
| pack-only | **7** | 不在 `content/plants.json`（只存在于 pack），守卫生效但无 content 数字可比 |

### 3.2 被拒绝的 20 株（逐株原因，全部来自实测）

| plant | 冲突列（content 值 ≠ 梯子第 1 级） |
| --- | --- |
| `akee1` | cost 150 ≠ 175 |
| `boomflower` | cost 350 ≠ 425 |
| `buttercup` | hp 900 ≠ 300、cost 50 ≠ 25、cd 10 ≠ 15 |
| `chillypepper` | hp 250 ≠ 300 |
| `firepeashooter` | hp 300 ≠ 600 |
| `gloombara` | hp 300 ≠ 3000 |
| `heathseeker` | cd 20 ≠ 25 |
| `hocus` | cost 200 ≠ 75、cd 20 ≠ 60 |
| `maybee` | cost 300 ≠ 250、cd 20 ≠ 15 |
| `meteorflower` | hp 300 ≠ 250 |
| `minipeashooter` | hp 300 ≠ 800、cost 200 ≠ 250 |
| `olivepit` | hp 300 ≠ 2000 |
| `olivepit1` | cost 175 ≠ 50、cd 7 ≠ 5 |
| `powervine1` | hp 250 ≠ 300、cost 150 ≠ 125 |
| `puffball1` | cd 20 ≠ 35 |
| `pvine1` | cost 125 ≠ 150 |
| `solarsage` | cd 25 ≠ 30 |
| `waterrabbit` | hp 200 ≠ 175 |
| `witchhazel1` | cd 30 ≠ 25 |
| `xshot` | hp 300 ≠ 500 |

这些冲突**不是**本任务能修的：修它要么改 `content/plants.json`（本任务禁改），要么改 `obb_build_content.py` 的 flatten
规则（`tools/**`，本任务禁改）。所以本轮的做法是**照实拒绝并列出清单**，等 B1 的下一个任务决定「以哪一列为准」。
伤害侧不受影响：这 20 株的伤害仍走 §2 的接线，只要 `damageStat` 那一列的 L1 与 content 的 `damage` 相等。

### 3.3 7 株 pack-only

`cutebubuseed`、`headbutterlettuce`、`imitater`、`marigold`、`noctarinecloud`、`seashroom`、`slingpea`。
它们不在 content，`plantStatsOf()` 走 pack 分支；守卫拿 pack 值比对，能比对就能生效，比对不上就保持原值。

---

## 4 clamp

`levelCount` 的分布（133 株，**取 `levels[]` 长度**）：
`2 → 36`、`3 → 20`、`4 → 5`、`10 → 68`、`15 → 1`、`20 → 3`。

* 请求大于 `levelCount` → 用 `levelCount` 那一级（`blockoli` 设 99 → 用第 10 级 16000 HP）。
* 请求小于 1 → 当作 1；表里没有这株 → 也是 1。
* `--set-plant-level` 阶段就拒绝 `n < 1`（报错，不静默修正），engine 侧再 clamp 一次上界。
* `plantLevelsApplied` / `Progress::plantLevels` 只记录 `> 1` 的项，被 clamp 到 1 的株不会出现在输出里。
* `levelCap` **不参与**判定：`sapfling1` 的 `levelCap` 是 1 而数组有 10 层，以数组为准。

---

## 5 存档

* `Progress` 新增 `std::map<std::string,int> plantLevels`（`native/src/progress.hpp:197`）；map 自带排序，无需额外去重。
* 读：`native/src/progress.cpp:421-428`，只接受整数值、`< 1` 的项跳过、显式写的 `1` 保留（这样往返稳定）。
* 写：`native/src/progress.cpp:560-565`，`if (!progress.plantLevels.empty())` 才输出该键 —— 默认存档**不长新键**，
  既有的字节级存档往返测试不受影响。
* clamp 的责任在 engine 读处（`World` 构造时），存档本身不依赖 generated tree 是否存在。
* `--progress <dir>` 分支（`native/src/main.cpp:412-413`）把 `world.plantLevelsApplied()` 合并进 `progress.plantLevels`，
  落盘的就是 clamp 之后的值。

---

## 6 CLI

```
PvZ2SHUTTLE --run-level content <level> [--pack …] --set-plant-level peashooter=3 --set-plant-level wallnut=2
```

* `--set-plant-level <plant id>=<level>`，可重复；`native/src/main.cpp:265-281`。
  缺 `=` → `--set-plant-level takes <plant id>=<level>, got: <spec>`；
  `n < 1` → `--set-plant-level needs a level of at least 1, got: <spec>`；空 id 同样报错。
* stdout 的那一行 JSON 里，只有**真的**有 >1 级时才多出 `plantLevelsApplied`（`main.cpp:368-373`），
  形态 `{"peashooter": 3}`。不传该选项时这一行与此前**逐字节相同**（所以 `engine_smoke.json` 不需要重生成）。

---

## 7 测试与反向探针

### 7.1 测试文件

`native/tests/plant_level_test.cpp`，CMake 注册为 `plant_level`（`TIMEOUT 120`），8 段：

| 段 | 断言 |
| --- | --- |
| `testTableShape` | 表能加载、323 株、`types()` 排序去重、`peashooter.levelCount == 3` 且 `damageStat == "ActionDamageNormal@2"`、`blockoli == 10`、`sunflower == 3` |
| `testAbsoluteLadderIsNotACurve` | 三株逐级值与 JSON 逐项对照（含 `sunflower` **没有**阳光列这件事） |
| `testClampToTheSheetsOwnCap` | `99 → 3`、`0 → 1`、未知株 `→ 1`、`at(99) == at(3)`、`at(-4) == at(1)` |
| `testIdentityGuardKeepsForeignColumnsOut` | `peashooter` hp 300→500 生效；传 999 不返回；level 1 不返回；`buttercup` 不返回；`SunValue` 这种不存在的列不返回 |
| `testProgressRoundTrip` | 写入→`parseProgress` 回读相等；默认 `Progress` 不含该键；`{"peashooter":"3"}`（字符串）与 `{"sunflower":0}` 都被跳过 |
| `testWorldAppliesTheLadder` | `frontyard_1` + `plantLevels{peashooter:3, not_a_plant:9}` → `plantLevel()` 3/1、`plantLevelsApplied().size() == 1`、种下后 `maxHp == 500`；默认世界仍是 300 |
| `testLevelDamageFollowsTheSameGuard` | L3 `levelDamage("peashooter", 30) == 45`、`(20) == 20`、`sunflower` 的 0 仍是 0、默认 30 |
| 入口 | `argc < 3` 时打印 `usage: plant_level_test <content> <pack>` 并返回 2 |

### 7.2 跑法（重要）

**只能用 ctest**，或显式给 `PVZ_GENERATED_DIR`：

```
ctest --test-dir C:\pvzbuild\plv1 -R '^plant_level$' --output-on-failure -C Release
# 1/1 Test #32: plant_level .... Passed  1.14 sec
```

在 `C:\pvzbuild\plv1\Release` 里直接双击/直接运行 exe 会 `0xC0000409`：`generatedDir()` 从工作目录向上找
`native/generated`，找不到就抛 `"plantfood table: … was not found; set PVZ_GENERATED_DIR or run from the repository root"`，
未捕获异常 → `std::terminate` → fastfail，连 stderr 都不一定留下。`native/CMakeLists.txt:100-102` 的注释解释了
为什么不能把仓库绝对路径塞进编译定义（cl.exe 用 ANSI 代码页，路径里的中文会被改写），所以 ctest 靠
`WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/.."` 从 cwd 向上找。

### 7.3 反向探针

把 `leveledValue()` 改成「永远返回第 0 级」后，`plant_level` 必须**红**；随后还原。结果记在这里：

探针：把 `leveledValue()` 的末行从 `return row->value(stat, level);` 改成 `return row->value(stat, 1);`
（即「永远取第 0 级」），只重建 `plant_level_test` 再跑。

```
$ cmake --build C:\pvzbuild\plv1 --config Release --target plant_level_test
$ ctest --test-dir C:\pvzbuild\plv1 -R '^plant_level$' --output-on-failure -C Release
1/1 Test #32: plant_level ......................***Failed    3.46 sec
plant level test failed: peashooter hp at level 3: expected 500.000000, got 300.000000
```

还原后同一命令：

```
1/1 Test #32: plant_level ......................   Passed    9.34 sec
100% tests passed, 0 tests failed out of 1
```

红 → 绿是跑出来的，不是推断的。红句点名 `peashooter` 第 3 级的 HP，正是 §2 表里的第一条接线点。

### 7.4 默认运行零差异

不传 `--set-plant-level` 时：

做法：**用打补丁前后的两个二进制跑同一批场景**，逐字节比对 stdout 那一行 JSON。
补丁前 = `build/native/Release/PvZ2SHUTTLE.exe`（2026-11-26 20:14:03，早于本次改动），
补丁后 = `C:\pvzbuild\plv1\Release\PvZ2SHUTTLE.exe`（22:20:06）。

| 场景 | 命令（相同） | 结果 |
| --- | --- | --- |
| `frontyard_1 script`（33 只僵尸、真的种了豌豆射手） | `--pack … --boards … --seconds 300 --script native/tests/scripts/frontyard_1_basic.json` | **两行 JSON 完全相等**（`hash 0x0a4329d753fa4dc5`、killed 15、mowerKills 13、tick 9220） |
| `beach_23 win` | `--pack … --boards … --seconds 400 --script native/tests/scripts/beach_23_win.json` | **完全相等**（`hash 0xa47bd864b1d332bf`、won、tick 1597） |

之所以能这么比：不设等级时 `plantLevels_` 是空表 → `plantLevel()` 恒返回 1 → `plantStatsOf()` 里
`if (level > 1)` 整段不进入、`levelDamage()` 第一行就 `return current`。所以「零差异」不是运气，是**结构上的**。

`python tools/engine_smoke.py --exe … --out work/_smoke_t90.json` 本身跑到底、`exit 0`（确定性、盘面几何、
`minKilled`、胜利分支这些内部闸门都过了），但它的**整表**与仓库里提交的基线**不一致**，差在两个场景，且都能证明与本改动无关：

* `beach_23 win`：**补丁前的二进制就已经和基线不同**（基线记 `0xb2a22229f25b92e6` / tick 1599，
  补丁前二进制给 `0xa47bd864b1d332bf` / tick 1597，补丁后完全一样）→ 差异早于本次改动。
* `world memorytour`：补丁后多出 `frostWinds: 2`、`tideChanges: 0`、`tideColumn: 0` 三个 summary 键，
  未知机制从 `events` 变成 `events.tide.unscheduled`，status 从 `lost` 变 `playing`。
  这三个键是**队友的 frost/tide 接线**在 20:14–22:20 之间落地的，不是本次改动新增的（本次只新增
  `plantLevelsApplied`，而且只在设了等级时出现）。
* 顺带一提：工作树里的 `native/generated/engine_smoke.json` **本身就是半成品**，队友刚刚把
  `world cowboy` 那条从 `killed 0` 改成 `2`（`git diff` 可见）——这张基线此刻正在被别人重刷。

### 7.5 传了 `--set-plant-level` 时到底变了什么

同一关、同一脚本，只加 `--set-plant-level peashooter=3`（`frontyard_1` + `frontyard_1_basic.json`）：

```
plain   : {"hash":"0x00eb20207350a5ac", "sun":25, "tick":9220, "killed":9,  ...}
level 3 : {"hash":"0xf2decd60ee403463", "sun":0,  "tick":9628, "killed":9,  ...,
           "plantLevelsApplied":{"peashooter":3}}
```

* `plantLevelsApplied` 出现，且只有 >1 级的株（`wallnut=2` 也传了但本关没种，就不在输出里）。
* `hash` 变了 —— 战斗轨迹真的不同。
* `sun` 25 → 0：第 3 级豌豆射手 `Cost` 是 75 而不是 100（§1.2 的绝对值阶梯），脚本因此多买了一张。
* `tick` 9220 → 9628：同样的击杀数，但节奏不同。
* 另一个更直白的例子：`--set-plant-level peashooter=3` 时 `levelDamage("peashooter", 30)` = **45**（§2），
  即 30 伤害的豌豆变成 45 —— 这是 `plant_level` 测试里 `testLevelDamageFollowsTheSameGuard` 钉住的那条。

### 7.6 全量 ctest（同一次构建）

```
96% tests passed, 2 tests failed out of 54      Total Test time (real) = 380.57 sec
 32/54 Test #32: plant_level ......................   Passed    5.60 sec
  1/54 Test  #1: catalog ..........................***Failed     (FAIL real catalog counts)
 17/54 Test #17: progress ........................***Failed     (no mower was used, so the mower goal must pass)
```

两条红都不是本次改动，证据：

* `catalog` 的断言是 `s.worlds == 26 && s.plants == 409 && s.zombies == 55 && s.levels == 1809`，
  而盘上现在是 `worlds 26 / plants 409 / zombies **111** / levels 1809` —— `content/zombies.json` 被队友
  在本次窗口里从 55 条扩到 111 条（`git diff --stat` 显示 +2547 行）。content 不在本任务作用域，我一个字没改。
* `progress` 失败句在 star goals（`beach_23` 的「无割草机」目标），依赖 `evaluateStars`（`rewards.cpp`，队友正在改，
  半小时前还有 `error C2059` 语法错）与同一份 content；而 `beach_23` 的世界推演在本次改动前后**逐字节相同**（§7.4），
  所以不是等级接线引起的。

---

## 8 没做的（明确边界）

1. **升级材料 / UI**：`plant_levels.json` 里有 `levelupOffer`（MaxCoins 100000 / MaxGems 500 / MaxMints 500）与
   `ConversionInfo` 六档，但「用什么升、界面在哪」本轮不碰，等级只能由 CLI / 存档给出。
2. **阳光产出没有列**：`sunflower` 的 4 个 stat 是 Cost / Hitpoints / PacketCooldown / PlantTier，
   **没有** `SunValue` 之类。所以「等级提高每产阳光」这件事在数据里不存在，不能靠猜。
3. **451 个 stat 名只用了 4 个**（Hitpoints / Cost / PacketCooldown / 伤害列）。剩下的是各株专属参数
   （`Blockoli_ShieldSmashCooldown`、`Cactus_BonusDamage`、`SeaShroom_PFLifespan`…），要接需要先有对应的行为实现。
4. **`PlantTier` 未使用**：它在梯子里是升阶金币/档位（T78 已认定），不是战斗数值。
5. **被守卫拒绝的 20 株**（§3.2）实际不受等级影响 —— 修它要动 content 或 flatten 规则，两者都在本任务作用域外。
6. **26 株 stats 为空**（`ailmint`、`appeasemint`、`pokra` 等纯 mint/无参数植物）：有 levelCount 没有可用列，
   等级对它们暂时无意义。

---

## 9 133 株全表

列名缩写：`dmg`/`pf` = 普通/plant-food 伤害列；`dmg@N`/`pf@N` = 带 SubType 的伤害列；`vel` = 弹速；
`cost`/`hp`/`cd` = Cost/Hitpoints/PacketCooldown；`pfdur` = PlantFoodDurationSeconds；`tier` = PlantTier。
「stats」列是该株梯子里出现的字段数。

| plant | levelCount | stats | 列 | 身份守卫 |
| --- | --- | --- | --- | --- |
| `ailmint` | 10 | 7 | ActionCooldownMax, ActionCooldownMin, ActionSplashDamage, cost, hp, cd, tier | guard accepts |
| `akee1` | 10 | 9 | dmg, ActionDamagePlantfood, vel, Akee_NormalProjectileBounceCount, Akee_PFProjectileBounceCount, cost, hp, cd, tier | guard rejects: cost 150≠175 |
| `appeasemint` | 10 | 0 |  | guard accepts |
| `applemortar` | 3 | 11 | dmg, pf, ActionSplashDamagePF, ActionStunDuration, ActionStunDurationPF, vel, cost, hp, cd, tier, StartingCooldown | guard accepts |
| `armamint` | 10 | 0 |  | guard accepts |
| `birthsunflower` | 3 | 4 | cost, hp, cd, tier | guard accepts |
| `blastberry` | 3 | 6 | dmg, ActionDamagePlantfood, cost, hp, cd, tier | guard accepts |
| `blockoli` | 10 | 9 | ActionDamage, pf, Blockoli_ShieldSmashCooldown, Blockoli_ShieldSmashStunDuration, cost, hp, cd, tier, StartingCooldown | guard accepts |
| `bloomerang1` | 20 | 8 | dmg, vel, Bloomerang_HitCount, Bloomerang_PlantfoodProjectileCount, cost, hp, cd, tier | guard accepts |
| `bloominghearts1` | 2 | 6 | dmg, vel, cost, hp, cd, tier | guard accepts |
| `boingsetta` | 10 | 5 | dmg, pf, cost, hp, cd | guard accepts |
| `bombardmint` | 10 | 0 |  | guard accepts |
| `boomberry` | 10 | 16 | dmg, pf, ActionSplashDamage, ActionSplashDamagePF, ActionStunDuration, Boomberry_Bonus_Max_Damage, Boomberry_Damage_Bonus_Modifier, Boomberry_DelayBetweenShots, Boomberry_SplashArea_Horizontal, Boomberry_SplashArea_Vertical, Boomberry_Splash_Damage_Bonus_Modifier, cost, hp, cd, tier, StartingCooldown | guard accepts |
| `boomflower` | 10 | 9 | BoomFlower_NormalBalloonDamage, BoomFlower_NormalBalloonSplashDamage, BoomFlower_NormalRechargeSeconds, BoomFlower_PFBalloonSplashDamage, cost, hp, cd, tier, StartingCooldown | guard rejects: cost 350≠425 |
| `bramblebush` | 10 | 7 | ActionDamage, pf, BrambleBush_TrapNumber, cost, hp, cd, pfdur | guard accepts |
| `buttercup` | 3 | 11 | dmg, pf, Buttercup_ButterConditionDuration, Buttercup_ButterLifetime, Buttercup_PFButterConditionDuration, Buttercup_PFButterLifetime, cost, hp, cd, tier, StartingCooldown | guard rejects: hp 900≠300, cost 50≠25, cd 10≠15 |
| `buzzbutton` | 3 | 5 | dmg, pf, cost, hp, cd | guard accepts |
| `cabbagepult` | 3 | 10 | ActionCooldownMax, ActionCooldownMin, dmg, ActionDamagePlantfood, vel, cost, hp, cd, PlantFoodPlayCount, tier | guard accepts |
| `cactus1` | 10 | 11 | dmg, ActionDamagePlantfood, vel, ActionXVelocityPlantfood, Cactus_BonusDamage, Cactus_PFSpikeDamage, Cactus_SpikeDamage, cost, hp, cd, tier | guard accepts |
| `chillypepper` | 3 | 9 | ActionChillDuration, ActionDamage, ActionFreezeDuration, ActionFreezeDuration2, ActionSplashDamage, cost, hp, cd, StartingCooldown | guard rejects: hp 250≠300 |
| `chomper` | 2 | 5 | Chomper_ChewTimeSeconds, cost, hp, cd, tier | guard accepts |
| `concealmint` | 10 | 0 |  | guard accepts |
| `containmint` | 10 | 0 |  | guard accepts |
| `cutebubuseed` | 2 | 2 | ActionDamage@0, ActionDamage@1 | pack-only |
| `dartichoke` | 3 | 13 | dmg, ActionDamagePerfect, ActionDamagePerfectPlantfood, vel, cost, Dartichoke_MaxAmmo, Dartichoke_NormalBoostChance, Dartichoke_OutOfAmmoSadSeconds, hp, cd, PerfectXVelocity, tier, StartingCooldown | guard accepts |
| `dazeychain` | 10 | 19 | cost, hp, cd, tier, Reincarnation_PinkActionDamage, Reincarnation_PinkCooldownMax, Reincarnation_PinkCooldownMin, Reincarnation_PinkPuffXVelocity, Reincarnation_PinkResidualStun, Reincarnation_RedActionDamage, Reincarnation_RedCooldownMax, Reincarnation_RedCooldownMin, Reincarnation_RedPuffXVelocity, Reincarnation_RedResidualStun, Reincarnation_WhiteActionDamage, Reincarnation_WhiteCooldownMax, Reincarnation_WhiteCooldownMin, Reincarnation_WhitePuffXVelocity, Reincarnation_WhiteResidualStun | guard accepts |
| `desireflower` | 2 | 8 | ActionDamage@0, ActionDamage@1, pf@2, pf@3, pf@4, cost, cd, StartingCooldown | guard accepts |
| `draftodil` | 10 | 0 |  | guard accepts |
| `draftodil1` | 2 | 2 | ActionDamage@0, ActionDamage@1 | guard accepts |
| `dusklobber` | 10 | 9 | ActionDamage, pf, ActionSplashDamage, ActionSplashDamagePF, vel, cost, hp, cd, tier | guard accepts |
| `electricblueberry` | 10 | 8 | cost, ElectricBlueberry_WeightTargetGargantuarZombie, ElectricBlueberry_WeightTargetNormalZombie, ElectricBlueberry_WeightTargetOtherZombie, hp, cd, tier, StartingCooldown | guard accepts |
| `electriccurrant` | 10 | 8 | dmg, pf, cost, CurrantWallDamage, CurrantWallDamagePF, hp, cd, tier | guard accepts |
| `electricitea` | 10 | 4 | dmg, cost, hp, cd | guard accepts |
| `enchantmint` | 10 | 0 |  | guard accepts |
| `enforcemint` | 10 | 5 | dmg, pf, cost, hp, cd | guard accepts |
| `evilshroom_speed` | 2 | 4 | cost, hp, cd, tier | guard accepts |
| `evilshroom_toughness` | 2 | 6 | dmg, vel, cost, hp, cd, tier | guard accepts |
| `explodeonut` | 3 | 7 | dmg, pf, ActionSplashDamage, ActionSplashDamagePF, cost, hp, cd | guard accepts |
| `explodeonut1` | 10 | 0 |  | guard accepts |
| `fairymushroom` | 2 | 0 |  | guard accepts |
| `firepeashooter` | 2 | 7 | dmg, pf, vel, cost, hp, cd, tier | guard rejects: hp 300≠600 |
| `futurebubuseed` | 2 | 0 |  | guard accepts |
| `gloombara` | 3 | 6 | cost, Gloombara_SpiritWorldDurationSeconds, hp, cd, tier, StartingCooldown | guard rejects: hp 300≠3000 |
| `gloomvine` | 10 | 0 |  | guard accepts |
| `gumnut` | 2 | 0 |  | guard accepts |
| `headbutter` | 10 | 7 | dmg, pf, cost, hp, cd, PlantFoodPlayCount, tier | guard accepts |
| `headbutterlettuce` | 2 | 2 | ActionDamage@0, ActionDamage@1 | pack-only |
| `heathseeker` | 10 | 7 | cost, HeathSeeker_ActionDamagePiercing, HeathSeeker_ActionDamagePrimary, HeathSeeker_MaxTargets, cd, tier, StartingCooldown | guard rejects: cd 20≠25 |
| `hocus` | 10 | 8 | cost, hp, Hocus_PFZombiesTeleported, Hocus_TeleportDamage, Hocus_TeleportRechargeTime, cd, tier, StartingCooldown | guard rejects: cost 200≠75, cd 20≠60 |
| `homingthistle` | 10 | 7 | dmg, vel, cost, hp, cd, tier, StartingCooldown | guard accepts |
| `icebloom` | 10 | 6 | dmg, pf, cost, cd, tier, StartingCooldown | guard accepts |
| `iceweed` | 10 | 13 | ActionChillDuration, dmg, ActionFreezeDuration, cost, hp, Iceweed_HitPointsUpgraded, Iceweed_PFBladeDamage, Iceweed_PFBladeDistance, Iceweed_PFBladeKnockback, Iceweed_PFSpikeDamage, cd, tier, StartingCooldown | guard accepts |
| `imitater` | 20 | 0 |  | pack-only |
| `imppear` | 10 | 19 | ActionDamage@0, ActionDamage@1, ActionDamage@10, ActionDamage@11, ActionDamage@12, ActionDamage@13, ActionDamage@2, ActionDamage@3, ActionDamage@4, ActionDamage@5, ActionDamage@6, ActionDamage@7, ActionDamage@8, ActionDamage@9, vel, cost, hp, cd, tier | guard accepts |
| `intensivecarrot` | 10 | 5 | cost, IntensiveCarrot_TargetHealth, cd, tier, StartingCooldown | guard accepts |
| `jalapeno` | 3 | 4 | ActionDamage, cost, cd, tier | guard accepts |
| `jasmine` | 4 | 2 | cost, cd | guard accepts |
| `lavaguava` | 10 | 7 | pf, cost, hp, LavaGuava_ExplosionDamage, cd, tier, StartingCooldown | guard accepts |
| `magnetshroom` | 2 | 8 | dmg, pf, cost, hp, cd, tier, Turkeypult_PlantfoodTurkeysToLaunch, Turkeypult_TurkeyLevel | guard accepts |
| `magnifyinggrass` | 10 | 8 | ActionDamage, vel, cost, hp, MagnifyingGrass_PlantFoodBeamDPS, MagnifyingGrass_SunMoneyPerShot, cd, tier | guard accepts |
| `marigold` | 4 | 0 |  | pack-only |
| `maybee` | 10 | 16 | cost, hp, Maybee_AttackRechargeTime, Maybee_BeeCount, Maybee_BeeDamage, Maybee_BeeDuration, Maybee_BeeSlowPercentage, Maybee_BeeTriggerRadiusSquares, Maybee_PlantfoodBeeCount, Maybee_PlantfoodBeeDamage, Maybee_PlantfoodBeeStunTime, Maybee_PlantfoodRechargeTime, Maybee_StunTime, cd, tier, StartingCooldown | guard rejects: cost 300≠250, cd 20≠15 |
| `meteorflower` | 2 | 14 | ActionSplashDamage, ActionSplashDamagePF, cost, hp, MeteorFlower_ActionDamagePFRadius, MeteorFlower_ActionDamageRadius, MeteorFlower_DelayBetweenShots, MeteorFlower_MeteorShowerCount, MeteorFlower_MeteorStrikeCount, MeteorFlower_MoltenPoolDamage, MeteorFlower_MoltenPoolDuration, MeteorFlower_TargetingDelay, cd, StartingCooldown | guard rejects: hp 300≠250 |
| `minipeashooter` | 2 | 7 | dmg, ActionDamagePlantfood, vel, cost, hp, cd, tier | guard rejects: hp 300≠800, cost 200≠250 |
| `murkadamia` | 10 | 4 | dmg, cost, hp, cd | guard accepts |
| `noctarine` | 10 | 5 | dmg, ActionDamagePlantfood, cost, cd, StartingCooldown | guard accepts |
| `noctarinecloud` | 10 | 5 | cost, hp, cd, tier, StartingCooldown | pack-only |
| `olivepit` | 10 | 5 | dmg, ActionDamagePlantfood, cost, hp, cd | guard rejects: hp 300≠2000 |
| `olivepit1` | 2 | 8 | cost, hp, OlivePit_ChewTime, OlivePit_OilSpitDuration, OlivePit_OilSpitRecharge, OlivePit_PitCapacity, cd, tier | guard rejects: cost 175≠50, cd 7≠5 |
| `parsnip1` | 10 | 6 | ActionDamage, pf, cost, hp, cd, tier | guard accepts |
| `peashooter` | 3 | 10 | dmg@0, dmg@2, pf@1, pf@3, vel, cost, hp, cd, pfdur, tier | guard accepts |
| `peppermint` | 10 | 5 | dmg, pf, cost, hp, cd | guard accepts |
| `phatbeet1` | 3 | 4 | cost, hp, cd, tier | guard accepts |
| `plantain` | 4 | 8 | dmg, ActionDamagePlantfood, ActionSplashDamagePF, vel, cost, hp, cd, tier | guard accepts |
| `plantern` | 2 | 0 |  | guard accepts |
| `pokra` | 10 | 0 |  | guard accepts |
| `powerplant` | 10 | 0 |  | guard accepts |
| `powervine` | 10 | 0 |  | guard accepts |
| `powervine1` | 10 | 11 | dmg, pf, cost, hp, cd, PlantFoodPlayCount, tier, PowerVine_EmpBurstActivationRadius, PowerVine_NetworkShots, PowerVine_NetworkedPlantfoodPlayCount, StartingCooldown | guard rejects: hp 250≠300, cost 150≠125 |
| `primalpeashooter` | 3 | 8 | dmg, ActionDamagePlantfood, ActionSplashDamagePF, vel, cost, hp, cd, tier | guard accepts |
| `primalsunflower` | 3 | 4 | cost, hp, cd, tier | guard accepts |
| `puffball` | 2 | 6 | dmg, ActionDamagePlantfood, cost, hp, cd, pfdur | guard accepts |
| `puffball1` | 10 | 6 | cost, cd, tier, Puffball_DecayPoisonDPS, StartingCooldown, StunDuration | guard rejects: cd 20≠35 |
| `pumpkin` | 10 | 0 |  | guard accepts |
| `pvine1` | 10 | 9 | dmg, pf, vel, cost, hp, PVine_ActionDamageBonus, cd, pfdur, tier | guard rejects: cost 125≠150 |
| `reinforcemint` | 10 | 0 |  | guard accepts |
| `sapfling` | 2 | 8 | ActionCooldownMax, ActionCooldownMin, ActionDamage, vel, cost, hp, cd, tier | guard accepts |
| `sapfling1` | 10 | 7 | ActionCooldownMax, ActionCooldownMin, vel, cost, hp, cd, tier | guard accepts |
| `seapotatomine` | 4 | 6 | cost, hp, cd, tier, PrimalPotatoMine_ArmingTime, StartingCooldown | guard accepts |
| `seashroom` | 10 | 15 | ActionDamage, pf, ActionSplashDamage, ActionSplashDamagePF, cost, hp, cd, tier, SeaShroom_Lifespan, SeaShroom_NormalAttackRange, SeaShroom_PFCloneCount, SeaShroom_PFProjectileCount, SeaShroom_PFProjectileRange, SeaShroom_SplashRadius, StartingCooldown | pack-only |
| `shadowpeashooter` | 10 | 11 | ActionDamageBoosted, dmg, ActionDamagePlantFood, vel, cost, hp, cd, ShadowPeashooter_PoweredAttackDecayPerZombieHit, ShadowPeashooter_PoweredAttackSlowDuration, ShadowPeashooter_PoweredAttackSlowMinimumDuration, ShadowPeashooter_ShadowBoostedZombieSwallows | guard accepts |
| `shinevine` | 10 | 9 | ActionStunDuration, ActionStunDurationPF, cost, hp, cd, tier, ShineVine_SunProductionModifier, Shinevine_FlashDamage, Shinevine_PFFlashDamage | guard accepts |
| `shrinkingviolet` | 10 | 5 | cost, cd, tier, ShrinkingViolet_DamageMultiplier, StartingCooldown | guard accepts |
| `slingpea` | 3 | 12 | dmg, pf, ActionSplashDamage, ActionSplashDamagePF, ActionStunDuration, ActionStunDurationPF, vel, cost, hp, cd, tier, StartingCooldown | pack-only |
| `snapdragon` | 10 | 4 | cost, hp, cd, tier | guard accepts |
| `snappea1` | 10 | 9 | dmg, ActionDamageZombieHead, vel, cost, hp, cd, tier, SnapPea_ChewTimeSeconds, StartingCooldown | guard accepts |
| `snowdrop` | 2 | 1 | ActionDamage | guard accepts |
| `solarsage` | 10 | 11 | cost, hp, cd, tier, SolarSageEnlightened_Infectivity, SolarSageEnlightened_InfectivityCooldown, SolarSageEnlightened_InfectivityRange, SolarSageEnlightened_SunProductionTimer, SolarSageEnlightened_SunProductionTimerCap, SolarSage_InfectivityPercentagePF, StartingCooldown | guard rejects: cd 25≠30 |
| `solartomato` | 2 | 8 | cost, hp, cd, SolarTomato_ExplosionHeight, SolarTomato_ExplosionWidth, SolarTomato_SolarFlareDamage, SolarTomato_SolarFlareStunDuration, StartingCooldown | guard accepts |
| `spearmint` | 10 | 0 |  | guard accepts |
| `spikerock` | 10 | 5 | ActionDamage, cost, hp, cd, tier | guard accepts |
| `spikeweed` | 10 | 5 | ActionDamage, cost, hp, cd, tier | guard accepts |
| `splitpea` | 20 | 10 | ActionDamage, pf, ActionDamagePFReverse, ActionDamageReverse, vel, cost, hp, cd, pfdur, tier | guard accepts |
| `sporeshroom` | 15 | 7 | dmg, ActionDamagePlantfood, vel, cost, hp, cd, tier | guard accepts |
| `squash` | 10 | 6 | cost, cd, tier, Squash_NormalZombiesToTarget, Squash_PlantfoodZombiesToTarget, StartingCooldown | guard accepts |
| `starfruit` | 2 | 7 | dmg, ActionDamagePlantfood, vel, cost, hp, cd, tier | guard accepts |
| `strawburst` | 10 | 6 | dmg, ActionDamagePlantfood, cost, hp, cd, tier | guard accepts |
| `sunbean1` | 10 | 8 | cost, hp, cd, tier, StartingCooldown, Sunbean_MaxSunPerZombie, Sunbean_MaxSunPerZombieOnPlantfoodBurst, Sunbean_SunPerHitpoint | guard accepts |
| `sunflower` | 3 | 4 | cost, hp, cd, tier | guard accepts |
| `sungun` | 2 | 7 | dmg, vel, cost, hp, cd, tier, StartingCooldown | guard accepts |
| `sunshroom` | 3 | 4 | cost, hp, cd, tier | guard accepts |
| `teleportatomine` | 10 | 0 |  | guard accepts |
| `teleportatomine1` | 10 | 7 | cost, hp, cd, tier, StartingCooldown, TeleportatoMine_ArmTime, TeleportatoMine_TeleportationUnitLimit | guard accepts |
| `tigergrass` | 10 | 14 | cost, hp, cd, tier, StartingCooldown, TigerGrass_GlobalGrowthMultiplier, TigerGrass_GrowthTime, TigerGrass_PounceDamageMultiplier, TigerGrass_TigerHealing, TigerGrass_TigerHealth, TigerGrass_TigerPFHealth, TigerGrass_TigerRegenTime, Tigergrass_TigerAttackDamage, Tigergrass_TigerPFAttackDamage | guard accepts |
| `toadstool` | 2 | 7 | ActionDamageLarge, ActionDamageMedium, ActionDamageSmall, cost, hp, cd, tier | guard accepts |
| `torpedofruit` | 4 | 8 | dmg, pf, ActionSplashDamagePF, vel, cost, hp, cd, pfdur | guard accepts |
| `tumbleweed` | 2 | 0 |  | guard accepts |
| `turkeypult` | 2 | 8 | ActionCooldownMax, ActionCooldownMin, dmg, pf, cost, hp, cd, tier | guard accepts |
| `ultomato` | 3 | 7 | dmg, ActionDamagePlantfood, cost, hp, cd, tier, StartingCooldown | guard accepts |
| `unused_43` | 2 | 2 | ActionDamage@0, ActionDamage@1 | guard accepts |
| `unused_45` | 2 | 3 | ActionDamage@0, ActionDamage@1, ActionDamage@2 | guard accepts |
| `unused_46` | 2 | 0 |  | guard accepts |
| `unused_47` | 2 | 0 |  | guard accepts |
| `unused_48` | 2 | 2 | ActionDamage@0, ActionDamage@1 | guard accepts |
| `unused_49` | 2 | 0 |  | guard accepts |
| `vamporcini1` | 2 | 10 | cost, hp, cd, StartingCooldown, Vamporcini_DamageRate, Vamporcini_GainHealthDuration, Vamporcini_GainHealthTick, Vamporcini_MaxHealthCap, Vamporcini_PfDamageRate, Vamporcini_PfGainHealthTick | guard accepts |
| `wallnut` | 3 | 5 | cost, hp, cd, tier, StartingCooldown | guard accepts |
| `wasabiwhip` | 10 | 7 | dmg, pf, cost, hp, cd, tier, WasabiWhip_TargetCount | guard accepts |
| `waterrabbit` | 2 | 11 | cost, hp, cd, PlantFoodPlayCount, StartingCooldown, WaterRabbit_FinalStrikeDamage, WaterRabbit_KnockbackCells, WaterRabbit_MaxDPS, WaterRabbit_NormalStrikeDamage, WaterRabbit_ThunderClapActionDamage, WaterRabbit_TimeBetweenChains | guard rejects: hp 200≠175 |
| `wintermelon` | 2 | 9 | ActionDamage, pf, ActionSplashDamage, vel, cost, hp, cd, tier, Wintermelon_ChillDuration | guard accepts |
| `witchhazel1` | 2 | 11 | ActionCooldownMax, ActionCooldownMin, ActionDamage, pf, cost, hp, cd, tier, StartingCooldown, WitchHazel_BasicTransformationLevel, WitchHazel_PlantfoodTransformationLevel | guard rejects: cd 30≠25 |
| `xshot` | 10 | 7 | ActionDamage, vel, cost, hp, cd, tier, XShot_PlantFoodProjectileCount | guard rejects: hp 300≠500 |
| `zoybeanpod` | 10 | 6 | dmg, ActionDamagePlantfood, cost, hp, cd, tier | guard accepts |

---

## 10 复现

```
# 构建（隔离目录，避免与队友共用 .tlog）
pwsh -NoProfile -File tools/build_native.ps1 -BuildDir C:\pvzbuild\plv1

# 单测（必须有 ctest 的 WORKING_DIRECTORY）
ctest --test-dir C:\pvzbuild\plv1 -R '^plant_level$' --output-on-failure -C Release

# 手动看等级效果
C:\pvzbuild\plv1\Release\PvZ2SHUTTLE.exe --run-level content frontyard_1 --seconds 5 --set-plant-level peashooter=3

# 默认运行零差异
python tools/engine_smoke.py --exe C:\pvzbuild\plv1\Release\PvZ2SHUTTLE.exe --out work/_smoke_t90.json
# 再与 native/generated/engine_smoke.json 比对（不覆盖提交版）
```

---

## 11 诚实边界

* 106/20/7 是**本轮实测**，取决于 `content/plants.json` 当时的数字；content 一改，分账就会变。守卫是自动的，清单不是。
* 「伤害列取最大 SubType 后缀」是从 `peashooter` 的 flatten 行为推出来的通用规则，**没有逐个 plant 验证**
  `obb_build_content.py` 对其它株是否也恰好取到同一列；守卫在运行时兜住了这个风险（对不上就不改）。
* `--set-plant-level` 的等级不会写回 content，也不会改变关卡难度；它只是「这一局把这株当成 N 级」。
* `plant_level` 测试覆盖的是「表 → 数值 → 世界」这条链，不覆盖渲染、音效、升级动画。
* 报告里的数字都来自本机这一棵工作树；队友同时在改 `native/src/engine/*`（rail/vase/tide/frost 等），
  `git diff --stat` 里的行数**不能**当作本次改动量的证据。
