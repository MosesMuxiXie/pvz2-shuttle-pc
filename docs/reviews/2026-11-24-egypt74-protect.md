# egypt_74 保护目标重复坐标取证（T57）

> 只读任务：未改 `content/**`、未改 `native/src/**`。唯一新增的探针是 `work/t56_probe_protect.py`，报告里的每个数字都由它打印。

## 零、结论摘要

1. **原表就是这样，不是编译丢字段**：`egypt_74`（`pkg_1051`）的 `ProtectThePlantChallengeProperties` 原文就是 `MustProtectCount=4` + **5 条** `Plants`，坐标确实只有 **3 个格子**（`(3,2)` 出现 3 次：`unused_43`、`fairymushroom`、`pvine1`）。除 `GridX`/`GridY` 之外**没有别的定位字段**（没有 index，也没有按顺序定位的键）。
2. **编译是忠实的，原版语义更可能是「按条目计数、同格可放多株」**：全部 287 个 protect 模块里 `MustProtectCount ≤ len(Plants)` **无一例外**（`must == plants` 268，`must < plants` 19，`must > plants` **0**）；而 `must > distinct` 恰好 5 关。两组事实只在「同格多株各自独立计数」这一种语义下同时成立 —— 若按格子去重，那 5 关在原版里就是数学上不可赢的关卡，`sky_46`（10 株 / 5 格 / must 10）这种设计也无从实现。
3. **另有一条更严重的同类缺陷不在 egypt_74，而在编译侧**：`pkg_0965` 有**两个** protect 模块，`tools/contentc/mechanics.py` 的 `extract_protect` 只取第一个，`lostcity_46` 因此只剩 2 株（丢掉的那个模块是 7 株）。这条要交给 `mechanics.py` 的负责人。
4. **`egypt_74` 当前的表现不是「打不赢」，而是「零容错」**：引擎只在植物死亡路径判负（`native/src/engine/world.cpp:1106-1119`），开局/胜利路径不校验存活数，所以 3 株只要都不死就能通关；`native/tests/mechanics_test.cpp:232-234` 注释里的 “the mission is unwinnable by data” 属措辞过头（同段的行为断言本身是对的）。

## 一、问题 1：原始表里到底是什么

### 1.1 原文（逐字）

`work/obb_packages/pkg_1051_LevelDefinition.json` `objects[6]`，`aliases=['ProtectThePlant']`，`objclass=ProtectThePlantChallengeProperties`：

```json
{
 "MustProtectCount": 4,
 "Plants": [
  {"GridX": 3, "GridY": 2, "PlantType": "unused_43"},
  {"GridX": 3, "GridY": 2, "PlantType": "fairymushroom"},
  {"GridX": 3, "GridY": 2, "PlantType": "pvine1"},
  {"GridX": 1, "GridY": 2, "PlantType": "sapfling"},
  {"GridX": 0, "GridY": 2, "PlantType": "icebloom"}
 ]
}
```

对应的关卡定义：`StageModule=RTID(EgyptNightsDMGStage@LevelModules)`、`LevelNumber=10`，`Modules` 里包含 `RTID(ProtectThePlant@CurrentLevel)`（同列还有 `ChallengeModule`、`GridItems`、`NewWaves`、`Rails`、`SeedBank`、`Tide` 等，共 11 项）。

### 1.2 有没有 GridX/GridY 之外的定位字段

全量扫 287 个 protect 模块（覆盖 286 个包）：

| 层级 | 字段组合 | 出现 |
| --- | --- | --- |
| 模块级 | `MustProtectCount`, `Plants` | **287 / 287**（只有这一种组合） |
| plant 级 | `GridX`, `GridY`, `PlantType` | 833 |
| plant 级 | `GridX`, `GridY`, `Level`, `PlantType` | 124 |
| plant 级 | `Condition`, `GridX`, `GridY`, `PlantType` | 6（`Condition` 全为 `icecubed`） |

- **坐标字段只有 `GridX`/`GridY` 两个**，没有 index、没有 `PlantRow`/`PlantColumn` 之外的任何位置键。
- `Level` 不是位置，是层/子关卡标记：取值分布 `1`×59、`-1`×33、`'1'`×15、`0`×11、`2`×6（同一关里 `initialPlants` 也带同名字段，`lostcity_67` 就是「protect 的 peashooter `Level=-1`」与「initial 的 peashooter `Level=1`」同格）。
- egypt_74 这条**没有** `Level`、也没有 `Condition`，就是最朴素的「三条同格 + 两条异格」。
- 别名分布（同一 objclass 的不同写法）：`ProtectThePlant` 276、`PTP` 8、`ProtectThePlant1` 1、`stallias` 1、`FogInit` 1。后两个虽挂这个 objclass，`objdata` 里也只有 `MustProtectCount`/`Plants`，按数据当普通保护关处理即可。
- 注意别混淆：`GridItemProtectorShieldProps`（10 个对象，字段 `GridExtents`/`Height`/`HitRectOffset*`/`PopAnim*`）是给格挡物套护盾的**美术参数**，不是保护植物模块。

### 1.3 编译产物和原文的对照

`native/generated/level_mechanics.json` 里 `egypt_74.protectThePlant`：

- `mustProtectCount: 4` —— 与原文一致；
- `plants`: **5 条**，坐标与 `PlantType` 逐条一致，另带两个编译侧补的键 `level: null`、`condition: null`；
- `failWhenProtectedPlantDies: true` —— **编译侧硬编码**（原文模块只有 `MustProtectCount`/`Plants` 两键，没有这个开关；见 `tools/contentc/mechanics.py:604` 附近的注释）。

全量对照（286 个编译出的 protect 关 vs 287 个原版模块）里，**被采用的模块逐字段差异为 0 条**（模块别名、条目数、`mustProtectCount` 全部一致）。唯一的结构差异是 `pkg_0965` 的一个模块被丢弃，见第二节 2.3。

## 二、问题 2：是我们编译错了，还是原版就这样

### 2.1 egypt_74 本身：编译忠实

见 1.3 —— 5 条、3 格、`must=4` 全部来自原文，`unused_43` 这种占位符也是原文写的（`unused_43` 在本版 `PlantType` 里确实存在）。

### 2.2 原版语义判据：按条目计数，不是按格子去重

| 判据 | 实测 | 说明 |
| --- | --- | --- |
| `must > len(Plants)` | **0 / 287** | 原版从没要求「比目标条目更多的存活数」 |
| `must == len(Plants)` | 268 / 287 | 绝大多数关是「一条都不能死」 |
| `must < len(Plants)` | 19 / 287 | 少数关允许死几株（容错设计） |
| `must > distinct(cells)` | **5 / 287** | 只有这 5 关的格子数撑不起 `must` |
| 坐标重复的模块 | 8 / 287 | 重复本身并不罕见，见 3.1 |

关键推论：`must ≤ len(Plants)` 在 287/287 成立，说明 `must` 的分母是**条目**；而 5 关 `must > distinct` 说明「条目」不等于「格子」。两者同时成立只有一个解释：**同一格可以放多条目标，各自独立计数**。若原版按格子去重，则这 5 关的 `must` 永远达不到 —— 原版不会自带 5 个不可赢关卡，而且 `sky_46`（10 条 / 5 格 / `must=10`，每格 `sunflower`+`shinevine` 各一株）这种「每格两株、十株都要活」的设计就只能按株数解释。

同一判据下还能读出反例边界：`carnival_90`、`lunarrainbowmarket_45`、`lunarrainbowmarket_109` 这三关也有坐标重复，但 `must ≤ distinct`，所以**重复本身不致命**；致命的只是那 5 关的 `must` 超过了格子数。

### 2.3 我们这一侧确实存在的两处偏差（不在 egypt_74，但同族）

1. **同包多 protect 模块只取第一个**。`tools/contentc/mechanics.py` 的 `extract_protect` 用 `package.one(PROTECT_CLS)`（`Package.one` = `all_of(...)[0]`），而 `pkg_0965` 有两个模块：

   | 模块别名 | `MustProtectCount` | 条目 | 备注 |
   | --- | --- | --- | --- |
   | `ProtectThePlant1` | 2 | 2（`(2,2)`、`(3,2)`，带 `Level=2`） | 被采用 |
   | `ProtectThePlant` | 2 | **7**（7 个格子） | **被丢弃** |

   结果：`lostcity_46` 编译出来只有 2 株目标，丢掉 5 株。这不是「数据怪相」，是我们的抽取缺陷，修法是**合并同包多个 protect 模块**（按 `Modules` 顺序或别名顺序），合并时把坐标列表拼接、`must` 取模块里的值（若两模块 `must` 不同则需要显式规则，建议按「合并条目、`must` 取最大」并在报告里标注）。
2. **`failWhenProtectedPlantDies` 是编译侧约定**：原文没有这个字段，编译固定写 `true`。它与「保护目标死即失败」的原版行为等价，但要标注成「编译侧约定」而不是「原版字段」，否则以后核对字段级差距时会误判成映射。

（另有一处**不是**缺陷：`frontyard_68` 的 `GridX` 在原文里是字符串 `'3'`，编译强转 `int`，语义一致；`Level` 也有 `'1'` 字符串形态，同样只是 sheet 混用类型。）

## 三、问题 3：还有多少关受同类影响

判定分两层：**数据层**（原表 `distinct < must`）和**引擎层**（按引擎当前的放置顺序模拟，`placed < must`）。第二层才对应「实际打不赢/机制失效」。

### 3.1 数据层：`distinct(cells) < must` —— 5 关

| 关卡 | package | 条目 | 去重格子 | `must` | 夹到格子数后 |
| --- | --- | --- | --- | --- | --- |
| `carnival_23` | `pkg_0245` | 6 | 3 | 6 | 3 |
| `egypt_74` | `pkg_1051` | 5 | 3 | 4 | 3 |
| `frontyard_51` | `pkg_2015` | 6 | 5 | 6 | 5 |
| `lostcity_45` | `pkg_0963` | 8 | 2 | 8 | 2 |
| `sky_46` | `pkg_0705` | 10 | 5 | 10 | 5 |

坐标重复但 `must ≤ distinct` 的另外 3 关（不致命，列出以示口径）：

| 关卡 | package | 条目 | 去重格子 | `must` |
| --- | --- | --- | --- | --- |
| `carnival_90` | `pkg_0362` | 2 | 1 | 1 |
| `lunarrainbowmarket_45` | `pkg_0829` | 2 | 1 | 1 |
| `lunarrainbowmarket_109` | `pkg_0944` | 8 | 7 | 7 |

### 3.2 引擎层：按当前放置顺序模拟，`placed < must`

引擎顺序是 `initialPlants` → `protect.plants` → `initialGridItems`（`native/src/engine/world.cpp:493-497`），一格只放一株（`world.cpp:472-473`），被占就跳过并计 `protect_plant_unplaced`（`world.cpp:477-482`）。按这个顺序模拟：

**（a）`placed == 0`：保护机制静默失效 —— 6 关**

| 关卡 | 条目 | `must` | 机制表现 |
| --- | --- | --- | --- |
| `carnival_79` | 1 | 1 | 目标格先被 `initialPlants` 的 `pvine1` 占 |
| `carnival_81` | 3 | 3 | 目标格先被 `lilypad` 占（荷叶 + 植物是两层） |
| `chinesegarden_57` | 3 | 3 | 同上，`lilypad` 对 `lilypad`（protect 带 `Level=1`） |
| `frontyard_53` | 2 | 2 | 目标格先被 `flowerpot` 占（花盆 + 植物是两层） |
| `lostcity_67` | 1 | 1 | 同格不同 `Level`（protect `-1` / initial `1`） |
| `sky_31` | 5 | 5 | 5 个 `tallnut` 目标格上先摆了 `jalapeno`/`bombardmint`/`thymewarp` |

这 6 关的问题**不是重复坐标**，而是「同格两层」：荷叶/花盆是地面层，植物是植物层；`Level` 不同也是不同层。引擎把两层压成一格，于是保护目标一条都放不进去 —— 保护机制整关空转。注意空转**不是**因为阈值被归零：`requiredSurvivors()`（`native/src/engine/mechanics.cpp:308-317`）只在 `plants` 为空或 `failWhenProtectedPlantDies` 为假时返回 0，这 6 关仍返回原来的 `must`；但既然没有一条受保护植物落地，`world.cpp:1106-1119` 的死亡判定永远没有触发源，所以这一关变成「普通关 + 一条不生效的 must」。

**（b）`0 < placed < must`：阈值零容错（同 egypt_74）—— 5 关**

| 关卡 | 条目 | 实放 | `must` |
| --- | --- | --- | --- |
| `carnival_23` | 6 | 3 | 6 |
| `egypt_74` | 5 | 3 | 4 |
| `frontyard_51` | 6 | 5 | 6 |
| `lostcity_45` | 8 | 2 | 8 |
| `sky_46` | 10 | 5 | 10 |

（`lostcity_46` 因 2.3 的抽取缺陷被压成「2 株 / `must=2`」，不在本表；修好抽取后它会进入重复坐标一族。）

**（c）丢失目标但仍可赢 —— 3 关**：`carnival_90`、`lunarrainbowmarket_45`、`lunarrainbowmarket_109`（`unplaced > 0` 但 `placed ≥ must`）。

### 3.3 `Modules` 点名但原表没有该模块对象 —— 8 关

`plantagenet_47`(`pkg_0753`)、`future_70`(`pkg_0760`)、`kongfu_70`(`pkg_0765`)、`fairy_31`(`pkg_0955`)、`frontyard_80`(`pkg_0958`)、`pirate_8`(`pkg_1547`)、`modern_82`(`pkg_1646`)、`frontyard_99`(`pkg_1699`)。

这 8 关 `Modules` 里有 `RTID(ProtectThePlant@CurrentLevel)`，但包里没有 `ProtectThePlantChallengeProperties` 对象 —— 属原版数据缺失（不是我们丢的），编译侧正确地没产出 `protectThePlant`。列表可复现（探针第 5 节逐关打印关卡 id 与包名）。

## 四、引擎当前行为（只读引用，未改动）

| 位置 | 行为 |
| --- | --- |
| `native/src/engine/world.cpp:468-501` | `layInitialField()`：`initialPlants`(493) → `protect.plants`(496) → `initialGridItems`(497) |
| `native/src/engine/world.cpp:472-473` | `place()` 里 `plantAt(...) || gridItemAt(...)` 视为占用，直接跳过 |
| `native/src/engine/world.cpp:477-482` | 被跳过的保护目标：`++unplacedProtectedPlants_` 并发 `protect_plant_unplaced` |
| `native/src/engine/world.cpp:1106-1119` | **只在植物死亡**时读阈值：`alive < required` → `status_="lost"` |
| `native/src/engine/world.cpp:1122-1124` | `requiredProtectedPlants()` 定义；grep 全仓只有测试调用，开局/胜利路径都没用 |
| `native/src/engine/mechanics.cpp:308-317` | `requiredSurvivors()`：`plants` 空 → 0；`failWhenProtectedPlantDies` 假 → 0；否则用 sheet 的 `mustProtectCount` |
| `native/tests/mechanics_test.cpp:232-247` | `egypt_74` 用例：断言 `protectedPlantCount()==3`、`unplacedProtectedPlants()==2`、`requiredProtectedPlants()==4`、打死一株 → `lost` |

因此 `egypt_74` 的实际表现是：开局 3/4、发 2 条 `protect_plant_unplaced`，**只要 3 株都不死就能通关**；死任何一株立即判负。这是「零容错」，不是「打不赢」。测试注释（`mechanics_test.cpp:232-234`）里的 “the mission is unwinnable by data” 建议改述为「no tolerance: three targets on task for a four-of-five requirement」，断言不用动。

## 五、建议口径（供你裁决，我没有改任何数据）

**A. 不要折叠 `level_mechanics.json` 里的重复条目，也不要据此改 `mustProtectCount`。**
理由：`must ≤ len(Plants)` 在 287/287 成立、`must > distinct` 只有 5 关；折叠会让 `sky_46`/`lostcity_45`/`carnival_23` 的 `must` 变成永远达不到，等于把「零容错」换成「必输」，问题更严重。

**B. 引擎侧两条路线（建议按顺序考虑，彼此不要混用断言）：**

- **B1（贴合原版）**：把「一格一株」的限制限定在**玩家种植**路径，保护目标的初始放置允许同格多株，存活数按株计。这样 5 关 + 6 关都能回到原版语义；代价是需要渲染/命中层能表达同格多株（表现层有工作量）。
- **B2（最小兜底）**：运行时把阈值夹到实放数 `required = min(must, placedProtectedPlants)`，并显式记录一个事件（例如 `protect_requirement_clamped`，带 `must`/`placed`），保证「数学上不可能」不会静默存在。代价是这 5 关比原版宽松（原版要求 4/5 株活，夹后只要求 3 株活）。

**C. 6 个 `placed == 0` 的关卡要单独处理，B1 也修不了。**
它们的病因是「同格两层」（`lilypad`/`flowerpot` 地面层 + 植物层、`Level` 不同层），不是同格多株。可行的方向是给格子加「地面层」槽位（荷叶/花盆先入地面层，植物再放植物层）。若只做 B2，这 6 关的保护机制会**空转**（阈值仍是原 `must`，但没有任何受保护植物可以死亡，判定永不触发）—— 那必须至少把「保护目标全部未落地」作为显式事件/报告项，别让它悄悄变成普通关。

**D. 8 个 declaredOnly 关卡**保持现状（原版数据缺失），在机制报告里标注「点名但无对象」，不要为此造假数据。

**E. 交办 `mechanics.py`**：合并同包多 protect 模块（当前 `pkg_0965` 丢 7 株，`lostcity_46` 会变成 2 株零容错）；顺便把 `failWhenProtectedPlantDies` 标注为编译侧约定。

## 六、复现

```powershell
cd D:\OneDrive\文档\pvz_shuttle\repo\pvz2-shuttle-pc
python work/t56_probe_protect.py
```

输出五节：① `egypt_74` 原文与 Modules 引用；② 287 个模块的字段形态与 `must` 统计；③ 坐标重复模块 + `distinct<must` 清单 + 按引擎顺序的放置模拟（**连每条被挡住的保护目标、以及挡住它的那个已占格植物都会逐条打印**，例如 `目标 citron1 被先占格者 pvine1(LNone) 挡住`）；④ 原版与 `level_mechanics.json` 的逐关对照（含被丢弃的多模块）；⑤ `Modules` 点名但无 protect 对象的 8 关。

只读：脚本只读 `work/obb_packages/pkg_*_LevelDefinition.json`、`native/generated/level_mechanics.json`、`content/levels/*.json`，不写任何文件。

## 七、不确定项（显式标注）

- **未运行原版客户端/引擎**，所以「同格可放多株」是**推断**（依据：`must ≤ len(Plants)` 全量成立 + 5 关 `must > distinct` + `sky_46` 每格两株 `must=10`），不是观察到的运行时行为。
- 原版是否有「同格多株上限」（例如只允许两层）未知；`egypt_74` 在 `(3,2)` 放了 3 株，若原版只有两层，这关本身仍会丢 1 株 —— 那它就和我们的 3/4 一样是原版自带的设计漏洞。
- `Level` 的精确语义（子关卡/波次层/难度层）是推断：取值集中在 `1`/`-1`/`0`/`2`，且 `egypt_74` 无此字段。
- 6 个 `placed == 0` 关卡里「占位者是地面层还是同层冲突」是按 `PlantType` 判读的（`lilypad`/`flowerpot` 归地面层，`pvine1`/`tallnut` 归同层），原版的分层规则未在本版 sheet 里找到显式声明。
