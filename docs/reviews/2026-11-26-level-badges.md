# A7：关卡徽标 + 世界地图图鉴入口提示

日期：2026-11-26　任务：t95　作者：analyst

本轮把「玩家能不能看见玩法」这件事补上：关卡列表屏在选中关卡时显示该关的玩法徽标（砸罐子 / 铁轨×2 / 传送带 / 墓碑…），世界地图屏在右下角显示图鉴入口（`图鉴 167+428 · 花园 65`），并给已通关的世界画勾。徽标计算被抽成不依赖 SDL 的纯函数 `level_badges.{hpp,cpp}`，可以脱离窗口单测。

**边界**：只读 `native/generated/*.json`；未改 `content/**`、`native/generated/**`、`tools/**`、`main.cpp`、`menu_view.cpp`；未提交 commit。两屏的 CLI 分发与菜单项由队长统一接线，本轮只提供 `levelSelectJson()` / `worldMapScreenJson()` 两个纯函数供其一行调用。

---

## 一、方法与边界

1. 先读两份产物表的结构，确认「徽标」能从哪来：
   - `native/generated/minigames.json`（1,222,686 B）：`levels` 是 813 关的 dict，每关有 `kinds[]`（20 种玩法 kind）与 `extra{minecarts, rail, vasebreaker, special[]}`；
   - `native/generated/level_mechanics.json`（4,827,308 B）：`levels` 是 1809 关的 dict，`conveyor` 非空表示有传送带，`initialGridItems.placements[].item` 里出现 `gravestone*` / `tombstone*` 表示有墓碑；
   - `native/generated/metagame.json`：`almanac.counts.{plants,zombies}` 与 `garden.counts.collectables` 供世界地图右下角那一行用。
2. 表里没有的东西不猜：`minigames.json` 的 `kinds` 之外不推断玩法；`level_mechanics.json` 里没有 `gravestone` 语义字段，只能靠 `initialGridItems` 的 item 名判定，这条是**约定**而不是表结构（见未知项 U2）。
3. 所有读取都不抛：目录不存在、文件缺失、JSON 坏掉都只记一条 `note` 并让屏上「什么都不显示」，不允许因为一张可选表把整屏弄崩。
4. 两屏都按既有 render 测试的口径验证：帧尺寸 1280×720、同一命令两次运行 PNG 字节相同、缺字体抛错。

## 二、交付物

| 路径 | 字节 | 行数 | 作用 |
| --- | --- | --- | --- |
| `native/src/level_badges.hpp` | 4,141 | 85 | 徽标纯函数 API（无 SDL） |
| `native/src/level_badges.cpp` | 10,463 | 275 | 词典 + 两张表的合并 + `+N` 截断 |
| `native/src/level_select_view.hpp` | 3,014 | 73 | 结果结构加 `badges`/`badgeLine`，新增 `levelSelectJson()` |
| `native/src/level_select_view.cpp` | 16,496 | 356 | 行内「玩法 N」+ 详情面板「玩法」区 |
| `native/src/worldmap_view.hpp` | 2,809 | 72 | `MetagameCounts`、`clearedWorlds`、`worldMapScreenJson()` |
| `native/src/worldmap_view.cpp` | 18,615 | 412 | 右下角图鉴入口行 + `✓ 已通关` |
| `native/tests/level_badges_test.cpp` | 13,916 | 243 | 10 节测试（见第七节） |
| `native/CMakeLists.txt` | 38,118 | 603 | `pvz_launcher` 加 `src/level_badges.cpp`；注册 `level_badges` 测试（TIMEOUT 120） |
| `docs/media/s7-level-select-badges.png` | 95,864 | — | 关卡列表屏截图（1280×720） |
| `docs/media/s7-worldmap-almanac.png` | 120,465 | — | 世界地图屏截图（1280×720） |

## 三、badge 词典（kind → 中文名）

顺序即 rank：同一关的徽标永远按这张表排列，**不随数据文件顺序变化**；未知 kind（未来表里才有的玩法）排在所有已知项之后（`kUnknownRank = 1000`），这样新数据不会把「砸罐子」挤出首位。

| rank | kind | 中文名 | 数据来源 | 合并后关卡数 |
| --- | --- | --- | --- | --- |
| 0 | `vasebreaker` | 砸罐子 | `minigames.kinds` | 47 |
| 1 | `rail` | 铁轨 | `minigames.kinds`（`extra.minecarts` 作 ×N） | 196 |
| 2 | `conveyor` | 传送带 | `minigames.kinds` ∪ `mechanics.conveyor` | 355 |
| 3 | `tide` | 潮汐 | `minigames.kinds` | 77 |
| 4 | `protecttheplant` | 保卫植物 | `minigames.kinds` | 197 |
| 5 | `gravestone` | 墓碑 | `mechanics.initialGridItems` 的 item 名 | 45 |
| 6 | `laststand` | 最后防线 | `minigames.kinds` | 73 |
| 7 | `bowling` | 保龄球 | `minigames.kinds` | 15 |
| 8 | `beghouled` | 三消 | `minigames.kinds` | 11 |
| 9 | `column` | 立柱 | `minigames.kinds` | 8 |
| 10 | `cannon` | 火炮 | `minigames.kinds` | 8 |
| 11 | `camel` | 骆驼 | `minigames.kinds` | 2 |
| 12 | `cowboy` | 西部 | `minigames.kinds` | 10 |
| 13 | `seeingstars` | 追星 | `minigames.kinds` | 3 |
| 14 | `sproutplanting` | 播种 | `minigames.kinds` | 2 |
| 15 | `whackazombie` | 打僵尸 | `minigames.kinds` | 1 |
| 16 | `invisighoul` | 隐形僵尸 | `minigames.kinds` | 8 |
| 17 | `deathexplosion` | 死亡爆炸 | `minigames.kinds` | 17 |
| 18 | `joust` | 长矛对决 | `minigames.kinds` | 4 |
| 19 | `bigtrouble` | 大麻烦 | `minigames.kinds` | 6 |
| 20 | `bonuschallenge` | 奖励关 | `minigames.kinds` | 2 |

合并结果：**846 关**至少有一个徽标（1809 关里 46.8%）；`conveyor` 的 355 关是 332（`minigames.kinds`）+ 23 关只在 `level_mechanics.conveyor` 里出现（例如 `frontyard_10`）；`gravestone` 的 45 关只能从 `level_mechanics.initialGridItems` 认出来，`minigames.json` 里没有这个 kind。

**铁轨的 ×N**：`minigames.json` 的 `extra.minecarts` 是矿车数，190 关有值。`railCount()` 只在 `>0` 时用它，否则算 1，所以显示 `铁轨×2`（`beach_10`）或 `铁轨`。`extra.rail` 是布尔标记，不作为数量来源——避免把「有铁轨」当成「两辆矿车」。

**最多 5 个**：`badgesFor()` 的截断规则是 `shown = size <= 5 ? size : 4`，超额时末尾补 `+N`（`N = size - shown`）。留出最后一格放 `+N` 而不是把 `+N` 挤掉，是因为「还有更多」比第 5 个具体名字更能提示玩家这关很花。

## 四、为什么未接线的机制也显示

徽标描述的是**原版数据**里的玩法标签，不是「本复刻已实现」的清单。`vasebreaker`、`beghouled`、`joust` 这些玩法在 `minigames.json` 里有定义，但 S3 阶段的模拟核心未必都已接线；如果只显示已实现的，玩家看到的关卡表就会与 `content/` 数据不一致，A7 的「入口可见」目标反而达不到。

因此本轮的取舍是：**全部 21 种 kind 照表显示**，把「渲染/模拟是否已支持」留作下游判断（未接线的玩法在进入关卡后由 battle 层决定表现）。这条需要在审核时被确认——如果队长希望区分「已接线/未接线」（例如给未接线的画成灰色），只需在 `LevelBadge` 上再加一个 `bool wired`，词典表里一个字段就能改。

## 五、数据读取顺序

`LevelBadges load(const std::filesystem::path& generatedDir)` 的顺序是固定的：

1. 读 `<generatedDir>/minigames.json` → 每关的 `kinds[]` + `rail` 的矿车数；读不到就把 `note` 记成「minigames.json 缺失/解析失败」，继续下一步。
2. 读 `<generatedDir>/level_mechanics.json` → `conveyor` 非空则加 `conveyor`；扫 `initialGridItems.placements[].item`，含 `gravestone`/`tombstone`（小写后）则加 `gravestone`。
3. 合并成 `levels[levelId] = vector<LevelBadge>`，`addBadge()` 去重时**取较大的 count**（同一关数据里出现两次铁轨，取矿车数大的那个）。
4. 只保留「非空」的关卡，避免 1809 个键里塞一堆空数组。
5. `loaded = 至少一张表读成功`；两张都失败时 `loaded == false`，屏上完全不画徽标（`level_select_view` 用 `badges.loaded && count > 0` 把关）。

`generatedDir` 由 `engine::generatedDir()` 给出（`native/src/engine/plantfood.hpp`，`PVZ_GENERATED_DIR` 可覆盖，找不到含 `plantfood_from_pack.json` 的目录时返回空路径）；空路径直接落到「读不到 → 不显示」，不抛异常。

## 六、屏内呈现

**关卡列表屏**（`level_select_view.cpp`）：

- 行内：星数右侧画 `玩法 N`（16 px，muted），只在 `loaded && N > 0` 时出现，让玩家在翻列表时就能看出哪几关不是普通关；
- 详情面板：「已通关」下方加「玩法」小标题 + `wrapChips(..., 18, 352.0f)` 逐行折行；没有徽标时写「无特殊机制」，而不是留白（留白会被误读成加载失败）；
- 徽标每帧按当前选中项重算，`LevelSelectResult.badges` / `badgeLine` 始终反映详情面板正在显示的那一关。

**世界地图屏**（`worldmap_view.cpp`）：

- 右下角 `图鉴 167+428 · 花园 65`（18 px，accent），x 由 `kWidth - 40 - text.width(entry, 18)` 右对齐，只在 `metagame.loaded` 时画；
- 状态文字由「已通关」改成 `✓ 已通关`，给「已通关」这个词一个不会被色觉差异吃掉的符号；
- `result.clearedWorlds = result.completed`，与 `metagame` 一起进入 JSON。

## 七、headless JSON 契约（给队长接线用）

`level_select_view.hpp` 新增：

```cpp
Json levelSelectJson(const LevelSelectResult& result);   // world, levels, cleared, selected, badges[]
```

`worldmap_view.hpp` 新增：

```cpp
struct MetagameCounts { int plants = 0, zombies = 0, drops = 0; bool loaded = false; std::string note; };
MetagameCounts loadMetagameCounts(const std::filesystem::path& generatedDir);
Json worldMapScreenJson(const WorldMapScreenResult& result);  // …既有键…, clearedWorlds, almanac{plants,zombies}, garden{drops}
```

两者都**只加不改**：`levelSelectJson` 保留原有的 `world/levels/cleared/selected`；`worldMapScreenJson` 保留 `worlds/unlocked/completed/stars/keys/selected/entered/level`。`main.cpp` 现在打印的那四个键照旧，队长接线时换成这两个函数就能拿到 `badges` 与 `clearedWorlds`/`almanac`/`garden`。

## 八、截图

| 文件 | 尺寸 | 字节 | sha256 |
| --- | --- | --- | --- |
| `docs/media/s7-level-select-badges.png` | 1280×720 | 95,864 | `AF33A8DA18673253AFE7771935F062EB68480F2B654A94686DD3A431B47225C3` |
| `docs/media/s7-worldmap-almanac.png` | 1280×720 | 120,465 | `DFC07D8DA44CBDEA06A572EEA31F9746D8F1203410530777AEFCDD83160861C4` |

- 关卡列表（`--level-select --world frontyard --frames 2`）：左列前 14 行里 `frontyard_5` 出现「玩法 2」、`frontyard_9` / `frontyard_10` 出现「玩法 1」；右侧详情选中 `frontyard_1`（无徽标）显示「玩法 / 无特殊机制」。
- 世界地图（`--worldmap-screen --frames 2`）：右下角绿色 `图鉴 167+428 · 花园 65` 已绘制。
- **`✓ 已通关` 没有出现在截图里**：截图用的是新存档（`{"completed":0,"unlocked":1,…}`），没有任何世界全关通关，所以勾的分支没被走到。该分支由 `level_badges_test.cpp` 第 10 节（构造 `clearedWorlds=2` 的结果并断言 JSON）与 `worldmap_render` 既有断言共同保证，**不是靠截图证明的**。

## 九、验证

| 命令 | 结果 |
| --- | --- |
| `t95_cfg.ps1 -BuildDir C:\pvzbuild\badge1 -Targets level_badges_test` | CONFIGURE OK / BUILD OK（其余五个库目标同轮编过） |
| `… -Targets level_select_render_test` / `worldmap_render_test` / `PvZ2SHUTTLE` | 全部 BUILD OK |
| `ctest --test-dir C:\pvzbuild\badge1 -C Release -R 'level_badges|level_select|worldmap_render'` | **3/3 Passed**：worldmap_render 3.88 s、level_select 5.29 s、level_badges 1.79 s |
| `PvZ2SHUTTLE --menu content --assets … --frames 2 --snapshot menu.png` | 31,949 B，sha256 `37F75744…AB7B1`，与基线**逐字节一致** |
| `PvZ2SHUTTLE --battle-snapshot content <assets> battle.png` | 1,584,774 B，sha256 `A75979B5…0CF5E`，与 t86 实测同值 |
| `python tools/engine_smoke.py --exe … --out smoke.json` | 32 条 scenario 与 `native/generated/engine_smoke.json` 基线 **0 差异**（changed=0、only-base=[]、only-new=[]） |

`level_badges_test.cpp` 的 10 节：① 词典 21 条且首条 `vasebreaker=砸罐子`、`badgeLabel` 对未知 kind 返回空；② 真实表规模 `minigameLevels==813`、`mechanicLevels>0`、`size()>800`；③ 关键关（`beach_69` 砸罐子、`beach_10` 铁轨×2、`beach_12` 传送带、`frontyard_61` 墓碑、`frontyard_10` 只有传送带）；④ 普通关（`frontyard_1`）返回空且不报错；⑤ `kongfu_83` 四徽标顺序 `砸罐子·铁轨·保卫植物·最后防线`；⑥ 六 kind fixture → 5 个 chip、末位 `+2`、行文本 `砸罐子 · 铁轨 · 传送带 · 潮汐 · +2`；⑦ 未知 kind 保留原名并进 `unknownKinds`；⑧ 缺目录 / 空目录 / 坏 JSON 都不抛且 `note` 含线索；⑨ `levelSelectJson` 的 `badges` 保序且旧键不变；⑩ `loadMetagameCounts` 得 167/428/65 且 `worldMapScreenJson` 的旧键不变、新键正确。

## 十、未知项

- **U1（中）**：`gravestone` 靠 item 名子串判定（`gravestone*`/`tombstone*`），不是表里的语义字段。实测命中 20 种 token、45 关；若后续 `level_mechanics.json` 改字段（例如给出 `gridItemKinds[]`），应改成读字段而不是匹配名字。
- **U2（中）**：`rail` 的数量取 `extra.minecarts`，`>0` 才用。190 关有值；余下 6 关 `rail=true` 但没有矿车数，显示成 `铁轨` 而不是 `铁轨×N`——原版是「单轨」还是「数据缺失」未确认。
- **U3（低）**：`minigames.json` 的 `kinds` 只有 20 种，但表里还有 `categories` / `modules` / `relatedModules` 未参与判定；是否有玩法只体现在后三者里（导致少显示徽标）未逐关核对。
- **U4（低）**：徽标不区分「模拟已实现 / 未实现」（见第四节）。若下游需要区分，需在 `LevelBadge` 上加字段，并在词典里标注实现状态。
- **U5（低）**：世界地图的勾按「世界全关通关」（`map::status(...) == completed`）判定，与「解锁」不是同一条件；截图用的新存档走不到该分支，只能靠单测覆盖。
- **U6（低）**：`图鉴 167+428 · 花园 65` 的数字直接来自 `metagame.json` 的 counts，不校验与列表长度是否一致；`metagame.json` 重新生成后数字会跟着变（这正是想要的行为），但若 counts 与列表不同步，屏上不会报警。
