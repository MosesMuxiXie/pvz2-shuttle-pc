# 植物名册合并：`339` 在本数据上不可达（合并器已落地，数据未切换）

日期：2026-11-25 · 任务：t68 / P0-4「 plantas.json 147 → 339」 · 状态：**合并器完成，切换被阻塞**

## 结论摘要

1. 合并机制已实现并通过测试：`tools/contentc/plants_merge.py`（纯函数 + CLI）、`tools/obb_build_content_v2.py` 的构建期接线（`build_plants_roster()` / `write_plants_roster()` / `--plants-only` / `--content-report`）、`tools/tests/test_plants_merge.py`（**28 例**）。
2. **`339` 复现不出来。** 本版 OBB 的 `PlantType` 名册是 339 条，手工 `content/plants.json` 是 147 条，两者同名的只有 **44** 条；手工独有的 **103** 条（融合植物、中式花园、活动植物）在原版里**没有对应项**。因此「保留全部手工行」的合并结果是 147 + 295 = **442**，不是 339。要凑 339 只能删掉 103 条手工行 —— 与任务硬规则「手工 147 行一个字都不许改写」直接冲突。
3. 试过把 442 条写进 `content/plants.json`：引擎 `--audit-content` 通过（`plants=442`），但 Python 套件红 **20 failures + 2 errors / 10 个模块**（见 §5），都是把 147 写死的产物与断言。已把 `content/plants.json` **恢复为 147 条**，仓库回到 518 tests OK。
4. 因此本次交付的是「可复现的合并器 + 硬数字 + 切换前必须做的下游重建清单」，切换动作留给队长裁决（§6）。

## 一、算术：`147 + 192 = 339` 的前提不成立

| 量 | 实测 | 来源 |
| --- | --- | --- |
| 手工名册 | **147** | `content/plants.json`（list，id 全唯一） |
| 原版 PlantType 名册 | **339** | `native/generated/plants_from_pack.json` → `counts.pack`；`native/generated/content.pack` → `plants` 长度 |
| 两边同名 | **44** | `plants_from_pack.json` → `skipped_existing`（44 条，理由「content/plants.json 已有同 id 条目」） |
| 手工独有 | **103** | `147 − 44` |
| pack 独有 | **295** | `plants_from_pack.json` → `plants` |
| **并集** | **442** | `147 + 295` |

`147 + 192` 里的 192 只能由 `339 − 147` 得出，而那个减法假设 **147 ⊂ 339**；实测只有 44 条满足。把 103 条手工独有行摊开看，它们不是「原版里有、只是 id 不同」的近亲，而是本版 OBB 根本没有的植物：

```text
twinsunflower, gatling, umbrellaleaf, iris, rosemary, snowlotus, wildflower,
olivewood, astrofruit, chrysanthea, doominator, helioscabbage, vortexmelon,
cheesestrawberry, oolongpeach, succulentgrape, doublepassion, fireflerry,
fused_wintergeddon, fused_paradoxpult …
```

少数名字在原版里存在但确实是不同植物（`chrysanthea` vs `chrysantheautumn`、`olivewood` vs `olivepit`），按 id/art/framework 三种归一化都比不上：art 交叉命中 **0**（客户端 art 是 `plants/*PLANT` 与 `art/<world>/*.png`，原版 art 大多为 null），framework 猜测只命中 36 条。

复现：

```text
> py tools\contentc\plants_merge.py -n
plants-merge-v1: plants=442 authored=147 pack=295 conflicts=44 packRoster=339
conflicts (authored wins): begonia, birdofparadise, bloomerang, bonkchoy, cabbagepult, cherry_bomb, chomper, elderbarrier, frozenpear, fumeshroom, gardenia, homingthistle …
```

## 二、合并规则（已实现，可重复执行）

- **手工行**：`source` 缺省，按原顺序、原字段**逐字面输出**；测试断言 147 行与盘上完全相等（`test_authored_rows_are_emitted_verbatim_in_order`）。
- **pack 行**：`source: "pack"`，按 id 排序追加；`clean_pack_row` 丢掉 `null`/`""`/`[]`/`{}` 的字段（「缺字段不写空串」），`id` 提到最前。
- **冲突**：id 同时出现在手工行与 pack 名册（含 `skipped_existing`）时手工行胜，冲突数 = 44，名单见上。
- **幂等**：`load_manual` 会跳过 `source == "pack"` 的行，所以反复运行不会叠加；`--check` 逐字节比对，`--out` 指向临时文件时 `-n` 不落盘。
- **错误**：手工或 pack 内 id 重复、缺 id、出现未知 `source` 一律 `MergeError`（CLI 退 2），宁可停下也不写半份名册。

## 三、逐族分布（合并后 442 条）

手工 147 条用**中文族名**（23 族），pack 295 条用**行为族**（11 族），两套词表并存，不强行归一：

| 手工族 | 数量 | | pack 族 | 数量 |
| --- | --- | --- | --- | --- |
| Peashooter | 32 | | shoot | 113 |
| Lobber | 20 | | instant | 48 |
| Cold | 18 | | lob | 38 |
| Sun | 14 | | support | 31 |
| Defence | 13 | | wall | 21 |
| Sharp | 10 | | produce | 19 |
| Support | 8 | | spike | 15 |
| Melee | 7 | | boomerang | 3 |
| Explosive | 5 | | fume | 3 |
| Fire / Jasmine / Mine | 3 each | | chomp / mine | 2 each |
| 其余 12 族各 1（Begonia、Bird、Chip、Dragonfruit、Gardenia、Poison、Poppy、Toast、Torpedo、Wall、Yucca、Sun） | | | | |

## 四、只有 pack 字段的行（如实列出）

295 条 pack 行里：

- **cost / hp 齐全**：295 / 295（`costDefault` 仅 2 条走默认值）。
- **art 缺 270 条**：只有 25 条在原版美术库里命中（`ambershroom`、`bloomerang1`、`citron`、`darktwinsunflower`、`gloomvine`、`headbutter`、`hollybarrierleaf`、`hollyknight`、`kernelpult1`、`lemonaider`、`magnetfruit`、`marigold`、`minigame_music`、`oxygenalgae`、`primalpotatomine`、`primalsunflower`、`primalwallnut`、`reinforcemint`、`repeater1`、`starfruit_barrage`、`sungun`、`unused_43`、`unused_45`、`unused_46`、`birthsunflower`）。
- **name_zh 全缺 295 条**：原版 `PlantType` 只给英文名（`name_en`），合并器**不编造中文**，`name_zh` 留空即不写该键（引擎的 `name_zh` 是可缺省项，audit 通过）。
- 前 12 个无 art 的 id：`ailmint, akee, akee1, aloe, aloes, appeasemint, applemortar, apsarlotus, aquavine, aquaweed, armamint, bamboospartan`。

## 五、把 442 条写进 `content/plants.json` 后的实测影响

（临时写入测得，随后已恢复 147 条）

- 引擎：`PvZ2SHUTTLE.exe --audit-content content` → `plants=442`，其余计数不变，**exit 0**。
- `py tools/contentc/decks.py` → `levels=1809 worlds=26 slots=7194 plants=41 actor=28 png=13 none=0 empty=0 oversized=1 unknown=0 registry=136/442`；切换前是 `registry=136/147`（deck 引用的植物集合没变，分母变大）。
- Python 套件：**20 failures + 2 errors**，涉及 10 个模块：

| 模块 | 数量 | 失败原因（一句话） |
| --- | --- | --- |
| `test_expand` | 5 | 断言 `plants_from_pack` 的 emitted=295 与 content 现存 id 的关系 |
| `test_pfamilies` | 5 | `sources split between pack and content` 等把 44/147 写死 |
| `test_original_gaps` | 4 | 已提交产物里 `plants Cost` 记录数 147、`projectiles` 重叠等 |
| `test_fusions` | 3 | 已提交产物与重算不一致（融合配料按 147 条名册归一） |
| `test_mapping` | 2 | 客户端 147 条 vs pack 归因统计 |
| `test_decks` | 1 | `registry=136/147` 写进报告断言 |
| `test_rewards` | 1 (error) | 空 OBB 夹具下植物名册读取 |
| `test_spawn_offsets` | 1 (error) | 产物过期（依赖 plants.json） |

- 恢复 147 条后：`py -m unittest discover -s tools/tests -p 'test_*.py'` → **Ran 518 tests, OK**。

## 六、决策点（不替队长决定）

| 选项 | 做法 | 代价 |
| --- | --- | --- |
| **A 并集 442** | `py tools\obb_build_content_v2.py --plants-only` | 必须同时重建上表 10 个模块的产物与断言（跨 6 个工具、3 位任务负责人） |
| **B 只留 pack 名册 339** | 合并时丢弃 103 条手工独有行 | 违反「手工 147 行不许改写」，且融合植物（85 条）会整体消失 |
| **C 维持 147** | 只保留合并器作为工具，`--plants-only` 不执行 | 任务目标（339）不达成，但仓库全绿、零副作用 |

合并器已经能在任意选项下工作：A 用缺省参数，B 需要新加一个 `--pack-roster-only`（目前**没有**实现，避免有人误删数据），C 什么都不做。

## 七、复现命令

```text
py tools\contentc\plants_merge.py -n            # 只打印 442/147/295/44/339
py tools\contentc\plants_merge.py --check       # 盘上 147 ≠ 合并 442 → exit 1
py -m unittest tools.tests.test_plants_merge    # Ran 28 tests, OK
py tools\obb_build_content_v2.py --content-report
#   content-report: levels=1809 … suppressFlag=271(true 215) …
#     plants=147 authored=147 pack=295 conflicts=44 merged=442 packRoster=339
#   mismatches: none
py -m unittest discover -s tools/tests -p 'test_*.py'   # Ran 518 tests, OK
```

## 八、边界

- 未 commit；`content/plants.json` 已恢复为切换前的 147 条（字节数 93,209，与备份一致）。
- 本次新增/修改：`tools/contentc/plants_merge.py`、`tools/tests/test_plants_merge.py`、`tools/obb_build_content_v2.py`（新增 `plants_merge` 导入、`build_plants_roster`/`write_plants_roster`、`--plants-only`、报告行、`main(argv)`）。
- 未触碰 `native/src/**`、`native/generated/level_mechanics.json`、`native/generated/patch_460_9.json`、其它工具；`native/generated/plants_from_pack.json` 只读。
- 临时脚本（`%TEMP%\t68_*.py`、`D:\Temp\User\t68_plants_before.json`）在收尾时删除。
