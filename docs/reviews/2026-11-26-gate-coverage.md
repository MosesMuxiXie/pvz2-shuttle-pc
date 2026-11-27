# 门禁覆盖守卫（D4）——产物 ↔ `check_all` 步骤的契约

- 任务：t101（D4），attempt 2
- 日期：2026-11-26
- 作者：geometer
- 写作用域：`tools/check_all.ps1`、`tools/tests/test_gate_coverage.py`、本报告
- 没有改 `native/src/**`、`native/generated/**`、`content/**`，也没有动任何编译器的逻辑或输出字节

## 0. 一句话结论

`tools/check_all.ps1` 从 **19 个 Step 加到 36 个**（新增 16 个数据编译器的 `--check` + 1 个交接中的守卫 Step），
并新增 `tools/tests/test_gate_coverage.py`（**20 例**）把「`native/generated/` 里每个产物 ↔ 声明它的编译器 ↔
`check_all` 里那个 Step」三方对齐成可执行契约：**新加一个表却忘了加 Step，测试会点名报红，而不是等下周
有人发现产物过期但门禁是绿的。**

守卫第一次运行就抓到 **18 条缺口**，其中 1 条是我自己的检测器误判（`plant_levels.py` 用手写 argv 循环，
不是 argparse），修掉检测器后实际缺 **17 个 Step**——现已全部补上。

## 1. 为什么需要这道守卫

`check_all` 的每个 Step 只看 `$LASTEXITCODE`：非零就 throw，整个门禁红。这本身没问题，问题是**没有任何
东西保证「有产物」就等于「有 Step」**。本轮的实际后果：

- `level_extra_rules.json`、`lawn_strings.json` 有编译器、有产物、有 `--check`，但 check_all 里没有 Step →
  产物落后于源表时，门禁照样全绿。
- 本轮已出现两次「产物过期但门禁绿」，都是人肉发现的，不是门禁发现的。

这类缺口靠复查发现不了第二次：`check_all` 的 Step 列表是一串手写字符串，产物是一堆 `DEFAULT_OUT` 常量，
两边只有命名上的巧合连接。所以本任务的做法不是「再补几个 Step」（那只是这一次），而是**让两者的不一致
变成测试失败**。

## 2. 契约（R01–R07）

| 规则 | 内容 | 失败时谁报红 |
| --- | --- | --- |
| R01 | 注册表是唯一事实：`native/generated/` 的每个文件都必须在 `PRODUCTS` 里有一条，写清模块与门禁方式；**不许靠文件名猜模块** | `test_registry_covers_every_generated_file` |
| R02 | 盘上有、注册表没有 = 孤儿 → 红，并点名文件名 | `test_a_new_unregistered_product_is_reported` |
| R03 | 注册表里的 `role="compiler"` 必须有 Step，且那个 Step 必须**在同一行**调用该模块并带 `--check` | `test_every_compiler_product_has_a_check_step`、`test_each_gated_module_runs_its_own_check` |
| R04 | 报告类（`.md`）永不进守护：它们跟着编译器一起重生成，单独设 Step 只会变成噪声 | `test_reports_are_never_gated` |
| R05 | 不是所有产物都能逐字节守：`pinned-only` / `no-check` / `external` / `step` 四类必须**显式写出理由或替代验证**，不能留白 | `test_pinned_only_products_say_why`、`test_no_check_products_name_the_test_that_pins_them`、`test_external_products_name_their_step` |
| R06 | 交接中的表（另一位成员还在写）它的 Step 必须是 `Test-Path` 守卫 + 打印 `[skip]` + 把 `$LASTEXITCODE` 归零；表一落地就自动变成真门禁 | `PendingHandoffTests` 4 例 |
| R07 | 为了过测试去改编译器输出字节是不允许的：本任务对 `native/generated/**` **零改动** | 人工（`git status` 无该目录改动） |

为什么 R03 要卡「同一行」：`build_content.py --generated 2026-11-20 --check` 是合法门禁，
而「只调编译器、`--check` 出现在上一行注释里」不是。守卫先剥掉行注释再判断，`test_a_comment_is_not_a_gate`
钉住这一点——这是第一版实现里的真 bug（注释也能骗过检测）。

## 3. 新增的 17 个 Step

`tools/check_all.ps1` 第 317 行起（`Step 'plant levels'` 之后）。耗时是 2026-11-26 在本机**温跑**
（解释器与文件缓存已热）实测的 `--check` 单跑时间，每个 Step 行尾注释里也写了同样的数字。

| # | Step 名 | 模块 | 产物 | 温跑 |
| --- | --- | --- | --- | --- |
| 1 | `level extra rules` | `level_extra_rules.py` | `level_extra_rules.json` | 5.5 s |
| 2 | `lawn strings` | `loc.py` | `lawn_strings.json` | 2.6 s |
| 3 | `level modules` | `levelextra.py` | `level_modules.json` | 3.2 s |
| 4 | `elements` | `elements_authored.py` | `elements.json` | 0.7 s |
| 5 | `bosses` | `bosses.py` | `bosses_from_pack.json` | 3.1 s |
| 6 | `projectiles` | `projectiles.py` | `projectiles_from_pack.json` | 4.1 s |
| 7 | `fusions` | `fusions.py` | `fusions_from_pack.json` | 0.6 s |
| 8 | `plant roster` | `expand.py` | `plants_from_pack.json` | 0.5 s |
| 9 | `plant food` | `plantfood.py` | `plantfood_from_pack.json` | 0.5 s |
| 10 | `plant families json` | `pfamilies.py` | `plant_families.json` | 0.6 s |
| 11 | `plant merge` | `plants_merge.py` | `plant_blocked.json` | 1.7 s |
| 12 | `shop unlock` | `shop_unlock.py` | `shop_unlock.json` | 3.2 s |
| 13 | `spawn offsets` | `spawn_offsets.py` | `spawn_offsets.json` | 1.4 s |
| 14 | `patch 460.9` | `newin4609.py` | `patch_460_9.json` | 4.0 s |
| 15 | `rails` | `rails.py` | `rails_report.json` + `content_fix_candidates.json` | 4.4 s |
| 16 | `zombie family gaps` | `zgaps.py` | `zombie_family_gaps.json` | 0.8 s |
| 17 | `mechanic entity resolution` | `mechanic_entity_resolution.py` | `mechanic_entity_resolution.json` | 交接守卫（0 s，未落地时） |

第 17 条的形状（`tools/check_all.ps1:341`）：

```powershell
Step 'mechanic entity resolution' {
    if (Test-Path 'tools/contentc/mechanic_entity_resolution.py') {
        python tools/contentc/mechanic_entity_resolution.py --check
    } else {
        Write-Host '[skip] tools/contentc/mechanic_entity_resolution.py has not landed yet' -ForegroundColor Yellow
        $global:LASTEXITCODE = 0
    }
}
```

`$global:LASTEXITCODE = 0` 不是装饰：Step 只看 exit code，上一个 Step 留下的非零值会把「跳过」判成「失败」。

**这条交接 Step 在我写报告期间已经从 skip 变成真门禁**：artifex 的
`tools/contentc/mechanic_entity_resolution.py`（40,554 B，20:10:51）与
`native/generated/mechanic_entity_resolution.json`（19,937 B，20:11:55）落地了。
它刚落地时 `--check` 返回 **exit 2**：

```
[fail] D:\OneDrive\文档\pvz_shuttle\repo\pvz2-shuttle-pc\docs\reviews\2026-11-26-mechanic-entity-resolution.md is stale
产物需要重新生成：python tools/contentc/mechanic_entity_resolution.py
```

——不是我的 Step 写错，而是对方自己的报告文档还没重生成。十几分钟后对方重生成，
同一个命令变成 `[ok] mechanic_entity_resolution.json and report are current`（见 §11 的实跑记录）。
这段时序正好演示了 R06 想要的效果：**我没有为该表写任何截止逻辑，它自己从「跳过」长成了「真门禁」**。

## 4. 本轮 11 个产品 × 门禁状态

| 产物 | 编译器 | t101 之前 | t101 之后 |
| --- | --- | --- | --- |
| `vasebreaker.json` | `vasebreaker.py` | 有 Step `vasebreaker` | 不变 |
| `minigames.json` | `minigames.py` | 有 Step `minigames` | 不变 |
| `minigame_rules.json` | `minigame_rules.py` | 有 Step `minigame rules` | 不变 |
| `loot_binding.json` | `loot_binding.py` | 有 Step `loot binding` | 不变 |
| `metagame.json` | `metagame.py` | 有 Step `metagame` | 不变 |
| `plant_playable.json` | `plant_playable.py` | 有 Step `plant playable` | 不变 |
| `plant_levels.json` | `plant_levels.py` | 有 Step `plant levels` | 不变 |
| `level_playability.json` | `level_playability.py` | 有 Step `level playability` | 不变 |
| `level_extra_rules.json` | `level_extra_rules.py` | **无 Step** | 新增 `level extra rules` |
| `lawn_strings.json` | `loc.py` | **无 Step** | 新增 `lawn strings` |
| `mechanic_entity_resolution.json` | `mechanic_entity_resolution.py` | **无 Step（文件还没交）** | 新增守卫 Step，落地即生效 |

结论：11 个里有 8 个本来就挂了、3 个是缺口——和「门禁里只有一部分」的印象一致，但缺口不是随机的：
**缺的三个都是最近两天新加的表**，说明「新表最容易漏 Step」这个判断成立，也正是守卫要解决的部分。

## 5. 全量 50 个产物 × 门禁账

`PRODUCTS` 49 条 + 1 条已落地的交接表（`landed_pending()` 自动折入），共 **50 个产物**：
34 个 `compiler`、9 个 `.md` 报告、3 个 `no-check`、2 个 `pinned-only`、1 个 `external`、1 个 `step`。
按扩展名：37 个 `.json`、9 个 `.md`、2 个 `.inc`、1 个 `.pack`、1 个 `.csv`。

### 5.1 由 Step 守的 34 个 compiler 产物

| 产物 | 模块 | Step |
| --- | --- | --- |
| `armors_from_pack.json` | `armors` | `armors` |
| `bosses_from_pack.json` | `bosses` | `bosses`（新） |
| `content.pack` | `build_content` | `content`（`build_content.py --generated 2026-11-20 --check`） |
| `content_fix_candidates.json` | `rails` | `rails`（新） |
| `elements.json` | `elements_authored` | `elements`（新） |
| `fusions_from_pack.json` | `fusions` | `fusions`（新） |
| `lawn_strings.json` | `loc` | `lawn strings`（新） |
| `level_extra_rules.json` | `level_extra_rules` | `level extra rules`（新） |
| `level_mechanics.json` | `mechanics` | `level mechanics` |
| `level_modules.json` | `levelextra` | `level modules`（新） |
| `level_playability.json` | `level_playability` | `level playability` |
| `loot_binding.json` | `loot_binding` | `loot binding` |
| `mechanic_entity_resolution.json` | `mechanic_entity_resolution` | `mechanic entity resolution`（新，交接） |
| `metagame.json` | `metagame` | `metagame` |
| `minigame_rules.json` | `minigame_rules` | `minigame rules` |
| `minigames.json` | `minigames` | `minigames` |
| `original_gaps.json` | `original_gaps` | `original gaps` |
| `patch_460_9.json` | `newin4609` | `patch 460.9`（新） |
| `plant_blocked.json` | `plants_merge` | `plant merge`（新） |
| `plant_families.json` | `pfamilies` | `plant families json`（新） |
| `plant_family_table.inc` | `plant_family_inc` | `plant families` |
| `plant_levels.json` | `plant_levels` | `plant levels` |
| `plant_playable.json` | `plant_playable` | `plant playable` |
| `plantfood_from_pack.json` | `plantfood` | `plant food`（新） |
| `plants_from_pack.json` | `expand` | `plant roster`（新） |
| `projectiles_from_pack.json` | `projectiles` | `projectiles`（新） |
| `rails_report.json` | `rails` | `rails`（新） |
| `rewards_from_pack.json` | `rewards` | `rewards` |
| `shop_unlock.json` | `shop_unlock` | `shop unlock`（新） |
| `spawn_offsets.json` | `spawn_offsets` | `spawn offsets`（新） |
| `vasebreaker.json` | `vasebreaker` | `vasebreaker` |
| `zombie_classes.json` | `zclasses` | `zombie classes` |
| `zombie_family_gaps.json` | `zgaps` | `zombie family gaps`（新） |
| `zombie_family_table.inc` | `zclasses` | `zombie classes` |

### 5.2 刻意不守的 16 个（见 §8）

9 个 `.md` 报告 + `pinned-only` 2 + `no-check` 3 + `external` 1 + `step` 1。

## 6. 守卫测试（`tools/tests/test_gate_coverage.py`，20 例）

### 6.1 怎么判断「有门禁」

- **模块声明了哪些产物**：AST 扫模块级常量里的 `ROOT / "native" / "generated" / "x.json"` 链
  （`_tail_of_div_chain`），所以 `DEFAULT_OUT`、`DEFAULT_JSON`、`DEFAULT_INC`、`OUTPUT` 都能认，不靠命名约定。
- **模块有没有 `--check`**：AST 判据两条——`add_argument` 的第一个位置参数是 `"--check"`，
  或任意比较表达式里出现常量 `"--check"`。第二条是为 `plant_levels.py` 那种**手写 argv 循环**准备的，
  用 argparse 正则会把它误判成「没有 --check」。
- **Step 是否真在守**：`Step '<name>' { ... }` 正则 + 忽略引号内与 `#` 之后花括号的花括号配平；
  Step 体里必须有一行（剥掉注释后）同时含 `tools/contentc/<模块>.py` 与 `--check`。

### 6.2 20 例清单

`ShippedGateTests`（9 例）：check_all 能解析出 ≥30 个 Step 且含关键名字；Step 名唯一；
注册表覆盖盘上每个文件；注册表条目都能被它的模块声明；每个 compiler 产物有 Step；每个 Step 同行调用自己的
`--check`；**删掉 `level extra rules` 必须恰好报 1 条并点名**；盘上多一个表必须被孤儿检查抓到；`.md` 从不进守护。

`ShippedGateTests`（5 例，R05）：`level mechanics` ↔ `level_mechanics.json` ↔ `mechanics.py` 三方归一；
`pinned-only` 必须写理由；`no-check` 必须指到存在的测试文件；`external`/`step` 必须指到存在的 Step 名。

`PendingHandoffTests`（5 例）：交接 Step 存在且 `Test-Path` 包裹、打印 skip；同一段只有 Python 调用没有
`Test-Path` 时 `guarded == False`；未落地的表不产生缺口；落了地的表进注册表且必须有 Step；
**只有注释里写 `--check` 不算门禁**。

`SyntaxTests`（1 例）：用 `pwsh` 的 AST `ParseFile` 证明 `check_all.ps1` 仍可解析（`parse_errors` 为空），
避免我加 Step 时把 PowerShell 语法写坏而只有真跑才发现。

### 6.3 失败样例（现在可复现的原文）

删掉 `level extra rules` 那条 Step 后：

```
level_extra_rules.json: tools/contentc/level_extra_rules.py --check is not a Step in tools/check_all.ps1
```

往盘上多放一个未登记的表：

```
brand_new_table.json
```

（`orphans()` 只回文件名，测试的断言消息再把「加进 PRODUCTS 并写明门禁」这句补上。）

### 6.4 首次运行抓到的 18 条缺口

```
bosses_from_pack.json / content_fix_candidates.json / elements.json / fusions_from_pack.json /
lawn_strings.json / level_extra_rules.json / level_modules.json / patch_460_9.json /
plant_blocked.json / plant_families.json / plant_levels.json / plantfood_from_pack.json /
plants_from_pack.json / projectiles_from_pack.json / rails_report.json / shop_unlock.json /
spawn_offsets.json / zombie_family_gaps.json
```

其中 `plant_levels.json` 是**我的检测器误判**：那个模块用手写 argv 循环接受 `--check`，
argparse 正则看不见它。改成 AST 判据后这条消失，实际缺 17 条——正好对应 §3 的 16 个 compiler Step
加 1 个交接 Step。

### 6.5 实现过程中修掉的三个真缺陷

1. **注释能骗过门禁判定**：第一版 `step_invokes_check` 只看「同一行同时含模块名与 `--check`」，
   于是「`# python tools/contentc/x.py --check`」这种注释行也算数。已改成先剥注释再判断，
   并补 `test_a_comment_is_not_a_gate`。
2. **样板断言太死**：`test_each_gated_module_runs_its_own_check` 原来断言字符串
   `"tools/contentc/build_content.py --check"` 必须连续出现，但 `content` Step 实际是
   `--generated 2026-11-20 --check`，中间隔了参数 → 误报。已改成「同一行里模块名与 `--check` 都在」。
3. **交接表落地后注册表没跟上**：`mechanic_entity_resolution.json` 一落地，孤儿检查立刻红——
   这正是 R02 想要的行为，但我的注册表只有静态 `PRODUCTS`。已加 `landed_pending()`：
   `PENDING` 里的模块一旦存在就自动折进注册表并要求 Step，同时保留「未落地不算缺口」的语义
   （由 `test_an_absent_handoff_table_is_not_required` 钉住）。

## 7. 耗时账

| 项 | 耗时 |
| --- | --- |
| 16 个新 compiler Step 之和（温跑，无并发编译时） | **36.9 s** |
| 同上（与队友的 native 构建同时跑时复测） | 45.4 s |
| 新 `mechanic entity resolution` Step（未落地时） | 0 s（文件已在则等于它自己的 `--check`） |
| `test_gate_coverage`（落在既有 `tool tests` Step 里） | 4.0 s（首跑含磁盘扫描时 8.6–16 s） |
| **`check_all` 新增总量** | **≈ +41 s（温）/ ≈ +95–115 s（冷）** |

两次实测的逐项数字（秒，第一次 / 加并发后复测）：
`level_extra_rules` 5.5/7.1、`loc` 2.6/3.7、`levelextra` 3.2/7.0、`elements_authored` 0.7/1.4、
`bosses` 3.1/7.1、`projectiles` 4.1/5.4、`fusions` 0.6/1.0、`expand` 0.5/1.3、`plantfood` 0.5/0.8、
`pfamilies` 0.6/0.8、`plants_merge` 1.7/0.8、`shop_unlock` 3.2/1.0、`spawn_offsets` 1.4/0.9、
`newin4609` 4.0/2.8、`rails` 4.4/3.4、`zgaps` 0.8/0.9。
Step 行尾注释写的是第一次（安静机器）的数字。

冷跑估算依据：`level_extra_rules.py --check` 冷跑 15.7 s、内部计算 5.8 s、温跑 5.5 s，比例约 2.9×；
按同一比例外推 36.9 s → ≈107 s。冷跑的主要成本是每个 Python 进程重新 import + OneDrive 读 ODB，
不是编译器本身。

作为参照，原有的 `tool tests` 与 native 构建段本来就是分钟级，所以 +41 s 对一次全量门禁是可接受的；
如果以后要压，优先考虑把多个 compiler 合并进一次进程（会牺牲「哪个表坏了」的定位精度，不建议在门禁里做）。

## 8. 刻意不守的 16 个产物与理由

| 产物 | role | 为什么不设 Step |
| --- | --- | --- |
| `armor_report.md`、`boss_report.md`、`deck_report.md`、`fusion_report.md`、`mapping_report.md`、`pack_roster_report.md`、`plantfood_report.md`、`projectile_report.md`、`world_diff.md` | `report` | 报告跟着编译器一起重生成（R04）；给报告设 Step 只会在改文案时红 |
| `coverage.json`、`id_overlap.json` | `pinned-only` | `build_content.py --check` **只校验 pinned counts，不写盘**（`main()` 里 `if args.check: return` 在写文件之前）→ 现在没有任何逐字节门禁。这是**真实缺口**，见 §9 |
| `board_sizes.json` | `no-check` | `geometry.py` 没有 `--check`（`--check` 会 `error: unrecognized arguments`），由 `tools/tests/test_geometry.py` 钉住 |
| `id_mapping.csv` | `no-check` | `mapping.py` 同上，由 `tools/tests/test_mapping.py` 钉住 |
| `s5_data_gaps.json` | `no-check` | `s5scan.py` 同上，由 `tools/tests/test_s5_inventory.py` 钉住 |
| `engine_smoke.json` | `external` | 由 `tools/engine_smoke.py` 跑出来，`engine smoke` Step 守（它不是 contentc 编译器） |
| `world_gates.json` | `step` | `worlds.py --emit-json` 在 `world diff` Step 里重写并当场比对渲染结果；`worlds.py` 自身没有 `--check` |

`decks.py` 也在这张表的精神里：它只产出 `deck_report.md`（温跑 2.0 s），所以**刻意不挂 Step**——
挂了也只是校验一份文档是否最新。

## 9. 遗留风险与建议（按优先级）

1. **`coverage.json` / `id_overlap.json` 没有逐字节门禁**（`build_content.py --check` 在写盘前就 return）。
   这是本轮最实质的缺口，建议下一轮给 `build_content.py` 加一个真正比对字节的 `--check`，或单独加 `--check-outputs`。
2. **4 个模块没有 `--check`**：`geometry.py`、`mapping.py`、`s5scan.py`、`worlds.py`。它们现在靠单测钉住，
   但单测只验证「读到的数据对不对」，不验证「盘上的产物是否最新」。补 `--check` 后它们可以直接进守护。
3. **`mechanic_entity_resolution` Step 目前是红的**（对方报告文档 stale），落地方重生成后自愈。
   如果一段时间内一直红，应该由对方修产物，而不是放宽 Step。
4. 以后新加表的标准动作只有两步：在 `PRODUCTS` 里登记（或加进 `PENDING` 等它落地），并在 `check_all.ps1`
   里加 Step。**顺序反了也没关系——测试会告诉你漏了哪一半。**

## 10. 复现

```powershell
# 守卫测试
python -m unittest tools.tests.test_gate_coverage -v

# 单个新增 Step 的 --check（都应为 exit 0；mechanic entity resolution 见 §3）
python tools/contentc/level_extra_rules.py --check
python tools/contentc/loc.py --check
python tools/contentc/levelextra.py --check

# 全量门禁（构建段会被并行队友的编译影响，见 §11）
pwsh -NoProfile -File tools/check_all.ps1 -NoContent
```

## 11. 全量门禁实跑记录（`-NoContent -NoDesktop`）

第三次尝试终于越过构建段，**17 个新 Step 全部按序执行**：

```
== plant levels ==
== level extra rules ==
== lawn strings ==
== level modules ==
== elements ==
== bosses ==
== projectiles ==
== fusions ==
== plant roster ==
== plant food ==
== plant families json ==
== plant merge ==
== shop unlock ==
== spawn offsets ==
== patch 460.9 ==
== rails ==
== zombie family gaps ==
== mechanic entity resolution ==
== tool tests ==
```

（`== plant levels ==` 是原有的最后一个数据 Step，用来标定插入位置；从 `level extra rules` 起是本任务新增的 17 个。）

- 每个新 Step 的单跑都是 exit 0（§3 的耗时表就是单跑测的；与并发编译同时跑时复测也全是 exit 0）。
- `mechanic entity resolution` 在这次运行里已经是 `[ok] mechanic_entity_resolution.json and report are current`
  ——artifex 在我写报告期间把 stale 的文档重生成好了，守卫从「交接 skip」自动转成「真门禁」，没有改过一行配置。
- `tool tests` 这一步：**`Ran 841 tests in 298.503s / OK (skipped=1)`**（含本任务的 20 例）。
  日志中间那些 `FAIL:` 行是各模块自带的诊断打印（临时产物比对），不是测试失败。

整轮 `check_all` 最终 exit 1，失败点在**与本任务无关**的两处：

```
[fail] docs/PARITY_MATRIX.md changed; review the diff or pass -AllowMatrixChange
[fail] test ledger: audit 0 vs 29
[warn] python ran 841 tests, the ledger says 680 (+161 since it was written; refresh the block when you touch the docs)
```

前一条是并行队友改动内容/代码后 parity 矩阵需要重算（`docs/PARITY_MATRIX.md` 不在我的写作用域）；
后一条是 `audit` 那一段因为构建段此前被并发编译打断而记 0 个测试，加上 Python 用例数从 680 涨到 841、
`PARITY_BASELINE.md` 的账本该刷新了（同样不在我的写作用域）。这两条都不是新增 Step 引起的。

## 12. 诚实边界

1. 耗时数字是**本机温跑**（OneDrive 目录），并且会随机器负载变化（§7 给了两组数）。所以我把它写成注释
   而不是断言——它不是契约的一部分，写死会让门禁在慢机器上红。
2. 注册表 `PRODUCTS` 是**人工维护**的：它能保证「盘上的文件都被登记过」，但不能保证「登记的理由是对的」。
   §8 那些「刻意不守」的判断是我读代码得出的，其中 `coverage.json` / `id_overlap.json` 的结论已用
   `main()` 里 `if args.check: return` 的位置核对过，其余靠各模块 `--help` 与实测行为。
3. 守卫只覆盖 `native/generated/`。`content/**`、`docs/**` 的产物不在范围内（`content.pack` 是例外，
   因为它由 contentc 生成且有 Step）。
4. `check_all` 全量跑的成败**不能**拿来判断本任务：它包含 native 构建、desktop 构建、parity、账本四条
   与本任务无关的门禁，而仓库此刻有并行队友在改 `native/src/**`。本任务的判据是「新 Step 各自 exit 0 +
   新 Step 在实跑里被执行 + 守卫测试全绿」，这三条都已在 §7/§11 给出证据。
5. 没有跑 `git commit`/`push`，也没有改任何编译器的输出字节（`native/generated/**` 只被 `world diff`
   Step 自身重写过 `world_gates.json`，那不是我的改动）。
