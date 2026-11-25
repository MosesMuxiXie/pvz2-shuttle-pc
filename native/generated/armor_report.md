# 护甲数据编译报告（ArmorTypes + 僵尸护甲映射）

由 `tools/contentc/armors.py` 生成；数据源 `pkg_0002_ArmorPropertySheetUtils.json` + `pkg_2115_ZombieType.json`，产物 `native/generated/armors_from_pack.json`。

```
python tools/contentc/armors.py            # 写 json + 本报告
python tools/contentc/armors.py --check    # 校验落盘文件
python tools/contentc/armors.py --needle   # 复现「哪些字段名不存在」
```

## 0. 计数

| 项 | 值 | 说明 |
|---|---:|---|
| 编译出的护甲 | 102 | 按 alias 去重 |
| 原表（pkg_0002）护甲 | 97（97 行） | 原表里 97 行、97 个 alias |
| 其它包内嵌护甲 | 9 行 / 5 个 id | 只在内嵌副本里存在的 id 见 §1 |
| 能定 HP 的护甲 | 101 | `BaseHealth` 有值 |
| 定不出 HP 的护甲 | 1 | 模板行 / 无 `BaseHealth`，输出 null |
| HP 为哨兵 2147483647 | 4 | 「无敌/秒杀」，保留原值并标记 |
| 带美术块的护甲 | 102（有骨骼主层 89） | `ArmorLayers[0]` 即护甲骨骼层名；没有骨骼层的 13 条见 §9 第 6 条 |
| 僵尸类型 | 1127 | `pkg_2115_ZombieType`（其中 2 个 TypeName 重复出现：heavy_shield、kongfu_gargantuar） |
| **挂护甲的僵尸** | **276** | `ZombieArmorProps` 非空 |
| 无护甲僵尸 | 804 | props 解析成功且 `ZombieArmorProps` 为空/缺失 |
| 护甲状态未知的僵尸 | 47 | props 对象在 2117 个包里找不到，**不能算作无甲** |
| 被引用到的护甲 id | 91 | 其余 14 个从未被任何僵尸类型引用（§5） |
| 悬空护甲引用 | **3** 个 id / 13 处 | 僵尸引用了表里不存在的护甲（§5 逐条） |
| props alias 撞名 | 66 个僵尸 | 同一 props 名在多包里出现，已按优先级取值并记 variants |
| 扫描的包 | 2117（失败 0） | 坏包跳过并计数 |

## 1. 护甲表：字段与样例

`python tools/contentc/armors.py --needle` 在 `pkg_0002_ArmorPropertySheetUtils.json` 的 97 个对象上统计任务点名的字段：

| 字段名 | 原表命中 | 本表怎么取 |
|---|---:|---|
| `Hitpoints` | 0 | **表中不存在 → 输出 `null`** |
| `HitPoints` | 0 | **表中不存在 → 输出 `null`** |
| `Health` | 0 | **表中不存在 → 输出 `null`** |
| `Droppable` | 0 | **表中不存在 → 输出 `null`** |
| `BreaksInto` | 0 | **表中不存在 → 输出 `null`** |
| `NextArmor` | 0 | **表中不存在 → 输出 `null`** |
| `Armature` | 0 | **表中不存在 → 输出 `null`** |
| `PopAnim` | 0 | **表中不存在 → 输出 `null`** |
| `ResourceGroups` | 0 | **表中不存在 → 输出 `null`** |

原版真实拼法：

| 输出键 | 原版字段 | 覆盖 |
|---|---|---:|
| `armorType` | `ArmorType` | — |
| `hitpoints` | `BaseHealth` | — |
| `flags` | `ArmorFlags` | — |
| `art.armorLayer` | `ArmorLayers[0]` | — |
| `art.layers` | `ArmorLayers` | — |
| `art.layerHealth` | `ArmorLayerHealth` | — |
| `art.className` | `ClassName` | — |
| `sounds.impact` | `ImpactSoundEvent` | — |
| `sounds.drop` | `DropSoundEvent` | — |
| `breaksInto` | （无） | 0/102 |

样例（三只最常被引用的护甲）：

| id | armorType | HP | flags | 主层 | 掉落后 |
|---|---|---:|---|---|---|
| `ConeDefault` | Cone | 370 | damageable, droppable, helm | `zombie_armor_cone_norm` | 见 §4（pack 无 breaksInto 字段） |
| `BucketDefault` | Bucket | 1100 | metallic, damageable, droppable, helm | `zombie_armor_bucket_norm` | 见 §4（pack 无 breaksInto 字段） |
| `BrickDefault` | Brick | 2200 | damageable, droppable, helm | `zombie_armor_brick_norm` | 见 §4（pack 无 breaksInto 字段） |

`breaksInto` 是**唯一一个 pack 不回答的字段**：原版没有「这个甲破掉之后变成什么」的字段。原版把这件事写在僵尸侧 —— `ZombieArmorProps` 是有序的 `RTID(<armor>@ArmorTypes)` 列表，所以本表把顺序放在 `zombies[].armorIds`（以及 `armorOrderNote` 标明「外层优先」是推断），护甲行里只给 `breaksInto: null` + 说明，不凭空造一个后继。

只存在于内嵌副本的护甲 id：`ImpStatueDefault`、`PerfumerStatueDefault`、`PogoStickDefault`、`RenaiStatueDefault`、`StatueOriginalDefault`。

## 2. ArmorFlags 分布与引擎含义

| flag | 护甲数 | 引擎要注意什么 |
|---|---:|---|
| `damageable` | 72 | 可以被伤害削；没有它的甲不能靠打掉 |
| `droppable` | 62 | 打掉后护甲掉落消失（否则是「打死才消失」的甲） |
| `invincible` | 16 | **不能计入可打掉的护甲血池**（`world.cpp:433` 现在的求和模型对这种甲是错的） |
| `passdamage` | 33 | 伤害穿透护甲打本体 |
| `metallic` | 20 | 金属甲（电磁/磁力类攻击需要它） |
| `helm` | 49 | 头部甲 |
| `body` | 20 | 躯干/整体甲（护盾、雨衣、棺材） |
| `visibleondestroy` | 4 | 破坏时仍有可见表现 |
| `absorboverflow` | 1 | 溢出伤害被吸收 |

哨兵：`BaseHealth = 2147483647` 的 4 条（`PassDamageDefault`、`ArmBoneDefault`、`ArmDefault`、`HeadDefault` 等）是「无敌/秒杀」标记，保留原值 + `hitpointsSentinel: true`，统计时排除。

`ArmorLayerHealth` 混了两种语义：破甲阈值（`0.666`/`0.333`，如 `ConeDefault`）与负层索引（`-1..-37`，如 `ArmBoneDefault` 用来隐藏每一层），原样透传，不做解释。

## 3. 僵尸 → 护甲：组合分布

| 护甲数 | 僵尸类型数 |
|---|---:|
| 0 | 851 |
| 1 | 260 |
| 2 | 9 |
| 3 | 5 |
| 5 | 2 |

单甲 260、双甲 9、三甲 5、五甲 2；多甲合计 16。

还要注意 47 个僵尸类型的 props 对象在 2117 个包里**找不到**（多为 `@$ZombieProperties` / `@CurrentLevel` 内联定义），它们的护甲状态是 `unknown`，不是「无甲」——`counts.zombiesUnknownProps` 单独计数，`zombies[].propsMissing` 逐条标记。

## 4. 多甲僵尸：掉一层之后剩什么

| 僵尸 | 护甲链（pack 顺序） | HP 链 |
|---|---|---|
| `mausoleum_drunk` | `DrunkardWineJar` → `DrunkardWineJar1` → `DrunkardWineJar2` → `DrunkardWineJar3` → `DrunkardWineJar4` | 1000 → 1000 → 1000 → 1000 → 1000 |
| `mausoleum_spirit_drunk` | `DrunkardWineJar` → `DrunkardWineJar1` → `DrunkardWineJar2` → `DrunkardWineJar3` → `DrunkardWineJar4` | 1000 → 1000 → 1000 → 1000 → 1000 |
| `kongfu_armor3` | `KongfuHelmetClothDefault` → `KongfuHelmetCloth2Default` → `KongfuHelmetDefault` | 1650 → 1650 → 1650 |
| `kongfu_basic_armor3` | `KongfuHelmetClothDefault` → `KongfuHelmetCloth2Default` → `KongfuHelmetDefault` | 1650 → 1650 → 1650 |
| `kongfu_monk_armor3` | `KongfuHelmetClothDefault` → `KongfuHelmetCloth2Default` → `KongfuMonkHelmetDefault` | 1650 → 1650 → 1650 |
| `kongfu_monk_helmet` | `KongfuHelmetClothDefault` → `KongfuHelmetCloth2Default` → `KongfuMonkHelmetDefault` | 1650 → 1650 → 1650 |
| `nutcracker` | `NutCrackerBody` → `NutCrackerArm` → `NutCrackerWindUpKey` | 2178 → 11 → 11 |
| `beach_surfer` | `SurfboardSurfingDefault` → `SurfboardDefault` | 700 → 700 |
| `dark_armor3` | `ShoulderArmorDefault` → `CrownDefault` | 1600 → 1600 |
| `eighties_armor4` | `EightiesHair` → `BrickDefault` | 220000 → 2200 |
| `eighties_armor4_ballad` | `EightiesHair` → `BrickDefault` | 220000 → 2200 |
| `eighties_armor4_pop` | `EightiesHair` → `PopBrickDefault` | 220000 → 2200 |

读法：第一个甲破掉后，僵尸身上的下一个甲继续吃伤害；全破就是裸僵尸（本体 HP 在 `zombieStats` 的 `toughness` 档里，原版不给数值）。顺序 = `ZombieArmorProps` 存储顺序；「外层优先」是从 `beach_surfer`（冲浪板→板）、`eighties_armor4`（头发→砖）、`nutcracker`（身→臂→发条）这几个例子推出来的，原版没有写明，标为推断。

## 5. 悬空引用与未被引用的护甲

| 护甲 id | 被引用次数 | 引用者（props 类） |
|---|---:|---|
| `AngerManagement` | 1 | ZombieGeneralCaesarProps / pkg_2112_ZombiePropertySheet ×1 |
| `HideLayer` | 1 | ZombieModernNewspaperProps / pkg_2112_ZombiePropertySheet ×1 |
| `InvincibleArmor` | 11 | ZombieGeneralTreadmillProps / pkg_2112_ZombiePropertySheet ×11 |

这 3 个名字只作为 `ZombieArmorProps` 的 RTID 出现，**在 2117 个包里没有任何同名的 `ArmorPropertySheet` 对象**（`--needle`-able：按 alias 全库搜 0 命中）——是原版包自身的数据缺口，不是编译漏读。引擎遇到这些僵尸应当当作「无甲/不可破」处理。

从未被任何僵尸类型引用的护甲 14 个：`ArmDefault`、`ArmorPropertySheetTemplate`、`ArmorPropertySheetUtilsTemplate`、`CamelSignBlankDefault`、`CamelSignHeadDefault`、`CamelSignMiddleDefault`、`CamelSignTailDefault`、`HeadDefault`、`HermitCrabDefault`、`MausoleumShieldDefault`、`PonchoDefault`、`PonchoPlateDefault`、`RomanShieldMain`、`RomanShieldTop`。它们可能是靠脚本/关卡动态挂载，本表保留但不猜用途。

## 6. 与 `content/zombies.json` 的差异（重点：HP 差多少）

客户端 55 个僵尸，其中 16 个写了 `armor`。桥接质量分三档：**精确**（`extra.source_codename` / id 命中 pack `ZombieType`）8 个、**世界+甲型推断**（无名可对，用 art 路径里的世界名 + `armature` 唯一命中）2 个、**桥不上**（没有任何 pack 依据，只比数值）6 个。

| content id | 桥接 | pack 僵尸 | pack 护甲链 | pack HP | content HP | HP 差（content−pack） |
|---|---|---|---|---|---|---|
| `conehead` | 精确 | `tutorial_armor1` | `ConeDefault` | 370 | 370 | +0 |
| `buckethead` | 精确 | `tutorial_armor2` | `BucketDefault` | 1100 | 1100 | +0 |
| `mummy_armor1` | 精确 | `mummy_armor1` | `ConeDefault` | 370 | 370 | +0 |
| `mummy_armor2` | 精确 | `mummy_armor2` | `BucketDefault` | 1100 | 1100 | +0 |
| `pirate_armor1` | 精确 | `pirate_armor1` | `ConeDefault` | 370 | 370 | +0 |
| `cowboy_armor1` | 精确 | `cowboy_armor1` | `ConeDefault` | 370 | 370 | +0 |
| `future_armor1` | 精确 | `future_armor1` | `ConeDefault` | 370 | 370 | +0 |
| `dark_armor1` | 精确 | `dark_armor1` | `ConeDefault` | 370 | 370 | +0 |
| `garden_cone` | 世界+甲型推断 | `chinesegarden_armor1` | `ConeDefault` | 370 | 370 | +0 |
| `garden_bucket` | 世界+甲型推断 | `chinesegarden_armor2` | `BucketDefault` | 1100 | 1100 | +0 |
| `gang_cone` | 桥不上 | — | — | — | 370 | ? |
| `gang_bucket` | 桥不上 | — | — | — | 1100 | ? |
| `market_armor1` | 桥不上 | — | — | — | 640 | ? |
| `market_armor2` | 桥不上 | — | — | — | 1600 | ? |
| `royal_noblewoman` | 桥不上 | — | — | — | 160 | ? |
| `royal_winetasting` | 桥不上 | — | — | — | 790 | ? |

### 6a. 能对上的 10 条：HP 差

这 10 条的 HP 与 pack **逐个相同**：`370` 对 `ConeDefault`（7 条）、`1100` 对 `BucketDefault`（3 条）。也就是说 content 的 HP 数值本身没错，错的是它把护甲压成了扁平数字、丢了 flags 与链顺序。

### 6b. 桥不上的 6 条：content 自己编的护甲数值

这 6 条没有任何 pack 僵尸类型可以对应（`source_codename` 缺失、id 也不在 `ZombieType` 里），其中 **3 条的 HP 在 pack 的 102 条护甲里根本不存在**、3 条至少能在 pack 里找到同值护甲。它们是 content 侧 authored 的数，不是从原版抄的。

按（世界 + 甲型）能拿到的**最近候选**（仅作参考，不是身份认定）：

| content id | 世界提示 | content HP | pack 候选（僵尸 / HP 链） | 数值最接近的 pack 护甲 | 差 |
|---|---|---:|---|---|---|
| `gang_cone` | losantosvice | 370 | **无候选** | `ConeDefault`（370） | +0 |
| `gang_bucket` | losantosvice | 1100 | **无候选** | `AtlantisBrickDefault`（1100） | +0 |
| `market_armor1` | lunarrainbowmarket | 640 | `lunar_armor1`（370）；`lunar_armor2`（1100） | `BalloonDefault`（650） | -10 |
| `market_armor2` | lunarrainbowmarket | 1600 | `lunar_armor1`（370）；`lunar_armor2`（1100） | `CrownDefault`（1600） | +0 |
| `royal_noblewoman` | plantagenet | 160 | `plantagenet_armor1`（370）；`plantagenet_armor2`（1100） | `AtlantisConeDefault`（170） | -10 |
| `royal_winetasting` | plantagenet | 790 | `plantagenet_armor1`（370）；`plantagenet_armor2`（1100） | `NewspaperDefault`（800） | -10 |

最典型的一条：`market_armor1` 写着齿轮护罩 640，而 pack 里名字/甲型带 clock|gear 的护甲只有 `ClockworkPlateDefault`（560，`steam_clockwork` 在用），差 **+80**；`royal_noblewoman` 的 160 与 `royal_winetasting` 的 790 在全部 102 条护甲里也没有同值项。

另外两类差异不是数值而是**形状**：

- content 用 `armature: "Cone"/"Bucket"` 与 `art: "armors/BasicConeARMOR"` 表达外观，这两个字段名在 pack 里都不存在（`--needle` 0 命中）；pack 给的是 `ArmorLayers` 的骨骼层名（如 `zombie_armor_cone_norm`）。本表 `art.armorLayer` 就是那个层名，可直接喂给 `actor_view` 的 armature 查找，不需要 `battle_view.cpp:297` 那种 `buckethead ? "Bucket" : "Cone"` 的硬编码。
- content 的 `armor` 是扁平 `[{hp, art, armature, metal}]`，pack 是**有序链 + flags**：`metal` 对应 `metallic` flag、`droppable` 决定破甲后是否移除、`invincible` 的甲不能进血池。

## 7. 这张表替换掉的两处写死

| 位置 | 现状 | 本表对应字段 |
|---|---|---|
| `native/src/engine/world.cpp:433` | `for (double armor : def.armor) zombie.armorHp += armor;` | `zombies[].armorIds` + `armors[].hitpoints`/`flags`（`invincible`、`passdamage`、`droppable` 分别处理） |
| `native/src/battle_view.cpp:297` | `gear.armature = z.type == "buckethead" ? "Bucket" : "Cone";` | `armors[].art.armorLayer`（102 条各自的骨骼层名） |

## 8. 复现

```
python tools/contentc/armors.py --check      # §0 的计数一行
python tools/contentc/armors.py --needle     # §1 的字段命中列
python -c "import json;d=json.load(open('native/generated/armors_from_pack.json',encoding='utf-8'));print(d['counts'])"   # §0/§2/§3 的全部数字
```

## 9. unknown（诚实边界）

1. `breaksInto` 原版没有对应字段（§1 已说明）：护甲→后继的关系只存在于僵尸侧的链顺序里。
2. `ZombieArmorProps` 的顺序语义（外层优先）是从 3 个多甲僵尸推出来的推断，不是 pack 字段。
3. `ArmorLayerHealth` 的两种语义（破甲阈值 vs 负层索引）没有文档，本表透传不做解释。
4. 47 个僵尸类型的 props 对象缺失 → 护甲状态 `unknown`，无法判定有无护甲。
5. 护甲与 `content` 的 `art`（`armors/BasicConeARMOR`）之间没有 pack 侧的对应关系，本表只给骨骼层名，模型文件路径仍需 authored。
6. 13 个护甲的 `ArmorLayers` 是空列表或缺失，只有 `ArmorType` 与 HP，没有可挂的骨骼层，`art.armorLayer` 输出 null：`ArmorPropertySheetTemplate`、`ArmorPropertySheetUtilsTemplate`、`BalloonDefault`、`BalloonTutorial`、`HeadDefault`、`ModernPogoStickDefault`、`NunchakuDefault`、`PassDamageDefault`、`RaincoatDefault`、`RocketDefault`、`RomanGargantuarHelm`、`StiltsDefault`、`ZombiePhotographerHeadLayer`。

