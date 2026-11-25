# 逐关掉落绑定（T72 / P1-C56）

补上 C56：`native/generated/rewards_from_pack.json` 只有**按表**的计数（`LootTable` 25 行、`PresentTable` 8 张各多少条），没有「这一关用哪个掉落 key / 哪张 lunckbox 表」的绑定。引擎读那份表只能拿 `default` 结算每一关，于是 13 个 danger room、1 个 whack 关、26 个 `NoLoot` 关全被当成普通关。

本文档描述 `tools/contentc/loot_binding.py` 把上述绑定从原版 `LevelDefinition` 包里编译成 `native/generated/loot_binding.json` 的口径：字段映射、1809 关的覆盖率、悬空表名的处置、以及哪些关卡**原版本身就没有掉落指向**。

生成物是**数据**，不含任何判定逻辑；引擎按 `levels[levelId]` 取用。

---

## 一、身份映射

客户端 `content/levels/*.json` 的 `extra.package` 形如 `"pkg_0325"`，对应 `work/obb_packages/pkg_0325_LevelDefinition.json`。

| 项 | 值 |
|---|---|
| 客户端关卡 | 1809 |
| 用到的 `LevelDefinition` 包 | 1809（一关一包，共用包 0 例、缺包 0 例） |
| OBB 里 `LevelDefinition` 包总数 | 1809 |
| 绑定的主键 | `levels` 的 key 与 `level_mechanics.json` 的 `levels` key **完全一致**（1809 对 1809，测试断言相等） |

`package` 字段写的是**包文件名**（`pkg_0325_LevelDefinition.json`），与 `level_mechanics.json` 的 `source.package` 同口径；`content/levels` 里的 `extra.package` 是 stem（`pkg_0325`），脚本自己做映射。

---

## 二、类名与字段映射

全部绑定信息都在 `LevelDefinition.objdata` 与同包的 module 对象上，没有独立表。

| 输出字段 | 原版来源 | 说明 |
|---|---|---|
| `lootRtid` | `LevelDefinition.Loot` | 原样保留，例 `RTID(DefaultLoot@LevelModules)` |
| `lootKey` | `Loot` 的 RTID 名 → `LootConfig.LevelLootKey` 词表 | `DefaultLoot→default`、`DangerRoomLoot→danger`、`WhackLoot→whack`、`NoLoot→null` |
| `presentTable` | `LevelDefinition.NormalPresentTable` | 名字，例 `egypt_normal_01`；缺失为 `null` |
| `shinyPresentTable` | `LevelDefinition.ShinyPresentTable` | 只在原版声明时输出该键 |
| `presentSource` | 解析来源 | `level` / `world` / `default`，见第三节 |
| `presentTableDangling` | 名字不在 `pkg_2079` 的 8 张里 | 只在 true 时输出该键 |
| `danger` | `Loot == DangerRoomLoot` 或 `IsDangerRoom is true` | 只在 true 时输出；两者实测 13 关完全重合 |
| `whack` | `Loot == WhackLoot` | 只在 true 时输出，1 关 |
| `noLoot` | `Loot == NoLoot` | 只在 true 时输出，26 关 |
| `modules` | 包内 loot 模块的 `objclass` | 排序去重；判定见下 |
| `lootOverrides` | `LootOverrideModuleProperties.objdata.Overrides[]` | 逐条 `{zombieType, lootOverride, alias?}`，`RTID(x@ZombieTypes)` 只留 `x` |
| `package` / `world` | 包文件名 / `content/levels` 的 `world` | 便于按世界聚合 |

`modules` 的判定不是「类名里带 Loot」——`ZombieDropZombiesOnBoardActionDefinition`（106 个）、`ZombossDropZombieActionDefinition`（16 个）之类是**生成怪**的动作类，不是掉落。规则是：

```python
LOOT_MODULE_CLASSES = {"LootOverrideModuleProperties",
                       "LootOverrideZombossRiftModuleProps",
                       "ZombieDeathSeedDropModuleProperties"}
# 或 objclass 以 "Loot" 开头且含 "Module"
```

实测只有两类命中：

| 模块类 | 关卡数 | 作用 |
|---|---|---|
| `LootOverrideModuleProperties` | 11 | 按僵尸类型改写掉落（`Overrides[]`，共 53 行） |
| `ZombieDeathSeedDropModuleProperties` | 15 | 僵尸死亡时掉种子（`objdata` 为空，行为在引擎侧） |

`LootOverrideZombossRiftModuleProps` 只在 3 个非关卡包里，关卡内 0 例。

`pkg_2079_PresentTable.json` 的表名在 `objdata.TypeName`（不是 `aliases` —— 那 8 个对象**没有** `aliases`，`objdata.Shiny: true` 标记 shiny 变体）。这是本轮第一个坑，用 `aliases` 取名字会让 8 张表全部"不存在"，悬空数从 68 虚报成 3269。

---

## 三、`presentSource` 的解析链

三级，按顺序取第一个命中：

1. `level` —— 该关自己的 `NormalPresentTable` 有值。**1635 关**。
2. `world` —— 关卡没声明，由 world 级表补。`collect_world_present_tables()` 会扫非 `LevelDefinition` 包里 `World*` 类的 `NormalPresentTable` / `PresentTable` 键。**460.9 里命中 0 个**：`pkg_2107_WorldData.json` 的 46 个对象没有任何 loot / present 键（`--grep PresentTable` 在非关卡包里只有 `pkg_2079` 自己）。
3. `default` —— 两级都没有，**174 关**，`presentTable: null`，引擎用自家默认盒子。

**所以 `presentSource` 实测只出现 `level` 与 `default`**。`world` 分支写成真代码 + 单测（注入 `world_tables={"beach": "..."}` 断言能命中），不是注释；`unknowns` 里有一条 `present-source-world-unused`（count 0）把这个事实钉住，免得下游以为漏扫。

`lootKey` 与 `presentTable` 是**两条独立链**：`NoLoot` 关的是 `LootTable` 那条（`LootConfig.Disable: true`），不影响 `NormalPresentTable` 字段是否存在。26 个 `NoLoot` 关里 19 关仍然声明了 lunckbox 表，记录里两个事实都保留，**是否发放由引擎侧决定，本轮不替引擎裁**。

---

## 四、覆盖率（实测计数）

`levels` 1809 条，逐关 `package` / `lootKey` / `lootRtid` / `presentTable` / `presentSource` / `modules` 齐备。

**按掉落 key**

| `lootKey` | 关数 | 备注 |
|---|---|---|
| `default` | 1762 | |
| `danger` | 13 | 同时带 `danger: true` |
| `whack` | 1 | `beach_20`，带 `whack: true` |
| `null` | 33 | `NoLoot` 26 + 无 `Loot` 字段 7 |

**按 lunckbox 表来源**

| `presentSource` | 关数 |
|---|---|
| `level` | 1635 |
| `world` | 0 |
| `default` | 174 |

**按表名**（`presentTable`，共 11 个取值）

| 表 | 关数 | 是否在 `pkg_2079` |
|---|---|---|
| `egypt_normal_01` | 1313 | 是 |
| `pirate_normal_01` | 152 | 是 |
| `future_normal_01` | 87 | 是 |
| `cowboy_normal_01` | 49 | 是 |
| `lostcity_normal_01` | 19 | **否（悬空）** |
| `dark_normal_01` | 6 | **否** |
| `eighties_normal_01` | 4 | **否** |
| `beach_normal_01` | 2 | **否** |
| `heian_normal_01` | 2 | **否** |
| `kongfu_normal_01` | 1 | **否** |
| `(none)` | 174 | — |

`shinyPresentTable` 13 个取值、175 关缺失；`egypt_shiny_01` 1302 关，另有 **10 个 heian 关把普通表 `egypt_normal_01` 填在 shiny 槽**（`heian_1/2/3/7/8/9/10/12/13` 与 `carnival_72`）——原版数据如此，照抄不修正。

**其它**

| 项 | 值 |
|---|---|
| `withLootKey` | 1776 |
| `lootFieldMissing` | 7 |
| `lootOverrides` 行数 | 53（11 关） |
| `byWorld` | 26 个世界，合计 1809 |

---

## 五、47 关非 `default` 明细

| 类 | 关数 | 关卡 |
|---|---|---|
| `danger` | 13 | `beach_95`、`chinesegarden_72`、`cowboy_41`、`cowboy_42`、`dino_63`、`egypt_81`、`eighties_72`、`future_71`、`iceage_72`、`lostcity_69`、`lunarrainbowmarket_126`、`modern_129`、`pirate_67` |
| `whack` | 1 | `beach_20` |
| `noLoot` | 26 | `carnival_41`、`dark_36/49/50`、`egypt_5`、`frontyard_14/22/28/34/40/41/93/102/114/121/127`、`heian_25`、`lunarrainbowmarket_123`、`mausoleum_40`、`modern_108`、`pirate_24`、`plantagenet_20/21/22/23/48` |
| 无 `Loot` 字段 | 7 | `frontyard_86/87/88`、`lunarrainbowmarket_114`、`mausoleum_1/2`、`modern_58` |

合计 13 + 1 + 26 + 7 = 47。

`danger` 的两种判据（`Loot == DangerRoomLoot` 与 `IsDangerRoom is true`）在 13 关上**完全重合**，测试里逐包复核过：既没有「有 DangerRoomLoot 但不是 danger room」的关，也没有反例。

---

## 六、`PresentTable` 悬空 13 张的处置口径

`pkg_2079` 只定义 8 张表（egypt / pirate / cowboy / future 各 normal + shiny），关卡引用到的名字有 12 个不在这 8 张里，按「名字 × 槽位」算 13 条，合计 **68 次引用**：

| 表名 | 槽位 | 关数 |
|---|---|---|
| `lostcity_normal_01` | normal | 19 |
| `lostcity_shiny_01` | shiny | 19 |
| `dark_normal_01` | normal | 6 |
| `dark_shiny_01` | shiny | 6 |
| `eighties_normal_01` | normal | 4 |
| `eighties_shiny_01` | shiny | 4 |
| `heian_normal_01` | normal **+** shiny | 2 + 1 |
| `beach_normal_01` | normal | 2 |
| `beach_shiny_01` | shiny | 2 |
| `heian_shiny_01` | shiny | 1 |
| `kongfu_normal_01` | normal | 1 |
| `kongfu_shiny_01` | shiny | 1 |

（`heian_normal_01` 是唯一跨槽位的名字：`beach_88`、`heian_17` 拿它当 normal，另有 1 关拿它当 shiny，所以 12 个名字、13 条。）

**口径**：本表**保留关卡原本声明的名字**，并给这些关打 `presentTableDangling: true`，同时把 13 条的名单、槽位、关数汇总进 `unknowns[kind=present-table-dangling]`。

**不做的**：不替引擎挑替代表。可选的两个方向都留给引擎侧（这是产品决定，不是数据问题）：

- 按世界回退：`egypt_normal_01` 是全球范围最常用的表（1313 关），但**表名与世界的相关性很弱**（beach 世界里 81 关用 `egypt_normal_01`、只有 2 关用 `beach_normal_01`），拿世界当回退键没有数据支撑。
- 按 `LootConfig` / `LootTable` 的 `LevelLootKey` 选行：那是**硬币掉落**那条链，与 lunckbox 表无关，不能互相替代。

注意这 13 张的名字里 `egypt/pirate/cowboy/future` 之外的 6 个世界（beach/dark/eighties/heian/kongfu/lostcity）正好是 `rewards_from_pack.json` 里 `keyLootWorlds` 之外的组合 —— 即「有专属世界表名但表本身没随包发出」，不是解析错误。

---

## 七、原版确实没有掉落指向的关卡

| 情形 | 关数 | 说明 |
|---|---|---|
| 没有 lunckbox 表（`presentSource == "default"`） | 174 | 其中 167 关 `lootKey == "default"`、7 关 `NoLoot` |
| 没有 `Loot` 字段 | 7 | `frontyard_86/87/88`、`lunarrainbowmarket_114`、`mausoleum_1/2`、`modern_58`；其中 `frontyard_86/87/88` + `modern_58` **连 lunckbox 表也没有**（两层都空，4 关） |
| `NoLoot` | 26 | 硬币那层显式关掉；其中 19 关仍声明了 lunckbox 表 |

「两层都空」的 4 关（`frontyard_86/87/88`、`modern_58`）是本轮唯一**原版确实没有任何掉落指向**的关卡：`Loot` 字段缺失、`NormalPresentTable` / `ShinyPresentTable` 也没有。其余 170 关至少有一层有指向。

`NoLoot` 的 26 关里有 7 关没有 lunckbox 表（`frontyard_14/22/28/34/40/41`、`modern_108`）—— 这 7 关与「无 `Loot` 字段」的 7 关**只有 4 关重叠**，不是同一批，别混。

---

## 八、踩坑

1. **`PresentTable` 的名字在 `objdata.TypeName`，不在 `aliases`**。`pkg_2079` 的 8 个对象没有 `aliases` 键；按 alias 取会把 8 张表全判成不存在，悬空数从 68 变 3269（每个关卡引用都算悬空）。写完第一版就撞上，靠对 `rewards_from_pack.json` 的 `danglingPresentTables: 13 / danglingPresentRefs: 68` 才定位到。
2. **包里混着没有 `objclass` 的注释对象**：8 个，形如 `{"//": "..."}`、`{"######## Z-Mechs Properties #######": ...}`（`chinesegarden_61/65` 等）。直接 `obj["objclass"]` 会 `KeyError`；`objects_of()` 统一过滤掉。
3. **`Loot` 的 RTID 不能直接当 key 用**。`RTID(DangerRoomLoot@LevelModules)` 要映射到 `LootConfig.LevelLootKey` 的 `danger`，`NoLoot` 则**没有**对应 key（`LootConfig` 里那条是 `Disable: true`），写成 `"noloot"` 会造出第四种 key，与 `rewards.py` 的 `levelsByLoot` 对不上。
4. **`presentTable` 与 `noLoot` 不互斥**。19 关既有 lunckbox 表又是 `NoLoot`；早期想「NoLoot 就别记表」会把 19 关的表删掉，丢掉原版事实。
5. **`egypt_normal_01` 会出现在 shiny 槽**（10 关，heian 系）。按「shiny 表名必须以 `_shiny_` 结尾」校验会误判为脏数据，原版就是这样填的。
6. **`modules` 不能按「类名含 Loot」扫**：会收进 106 个 `ZombieDropZombiesOnBoardActionDefinition`（生成怪）、16 个 `ZombossDropZombieActionDefinition`。限定 `Loot*Module*` 后只剩 11 + 15。
7. **`world` 级表在 460.9 里不存在**。`pkg_2107_WorldData.json` 46 个对象一个 loot/present 键都没有；`--grep PresentTable` 在非关卡包里只命中 `pkg_2079`。所以 `presentSource: "world"` 实测恒为 0 —— 这条写进 `unknowns` 而不是静默丢弃，否则下游会以为扫描漏了。
8. **确定性**：`generatedAt` 用输入内容算（`sha256(level_id, package, len, sha256(包字节))` 前 16 位），不取时钟、不取 mtime。两次运行字节相同，`--check` 才有意义（这是 C58 的同一个要求）。

---

## 九、复现与校验

```bat
cd repo\pvz2-shuttle-pc

python tools\contentc\loot_binding.py                  :: 生成 native/generated/loot_binding.json
python tools\contentc\loot_binding.py --check          :: 重算比对，漂移则 exit 1
python tools\contentc\loot_binding.py --grep PresentTable      :: 确认类名/字段名在哪个包
python tools\tests\test_loot_binding.py                :: 23 个用例
```

实测（本机，460.9 的 `work/obb_packages`）：

| 项 | 值 |
|---|---|
| 产物 | `native/generated/loot_binding.json`，537,332 B，MD5 `0bcc67baafe0eb1eca7971914a141461` |
| `generatedAt` | `sha256:9d1da1f8bcf3173f` |
| 编译耗时 | 8.26 s（其中 world 表扫描 0.94 s，只 parse 含 `PresentTable` 的那一个包） |
| `--check` 耗时 | 5.47 s，返回 0 |
| 测试 | 23 passed，40.8 s（`CompileLootBindingTests` 需要 OBB；无 OBB 时整类 skip，`ShippedLootBindingTests` 仍可跑） |

测试覆盖（23 例）：头部常量与 1809 覆盖、逐关字段契约（`presentSource` 枚举、可选标志只能是字面 `true`）、三种掉落关可区分且互斥、计数与记录互相加总（`byLootKey` / `byPresentSource` / 表名分布 / `byWorld` 全部合计 1809）、悬空 68 次 / 12 名 / 每关都有标记且名字都不在已定义表里、`world` 源为 0 且有 unknowns 条目、`lootKey` 只取自已发 `LevelLootKey`、6 关逐字段硬编码对拍、注释对象不进 `modules`；编译侧：两次生成字节相同且等于已发文件、3 关与原包逐字段复核、`danger` 与 `IsDangerRoom` 13 关重合、`lootOverrides` 与 seed 模块计数、`--grep` 命中与未命中、缺包进 `unknowns`、`--check` 幂等且能报漂移。

---

## 十、范围

- 只改 `tools/contentc/loot_binding.py`、`tools/tests/test_loot_binding.py`、`docs/reviews/2026-11-25-loot-binding.md`，产物写 `native/generated/loot_binding.json`。
- 未改 `content/**`、`native/src/**`、`tools/contentc/rewards.py`（另一条链），未 commit。
- 不判定「该不该发 lunckbox」「`NoLoot` 关还发不发盒子」—— 数据两项都给，规则在引擎侧。
- 不含 `LevelOfTheDayRewards` / `RiftFirstClearRewards` / `RiftZombossRewards` / `QuestRewardTablesProps` 这些**非关卡级**奖励表；它们已经由 `rewards.py` 收进 `rewards_from_pack.json`。
