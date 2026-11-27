# D6 文档数字同步（2026-11-26）

任务：t104 / D6。把 `docs/COMPLETENESS.md`、`docs/PROGRESS.md`、`docs/PARITY_BASELINE.md`、
`docs/superpowers/plans/2026-11-20-full-native-replica.md` 里「植物名册 / 可玩子集 / 关卡可玩性 /
新表尺寸与测试数」的数字换成当前实测值，**只改数字与口径句，不加新结论**。

## 结论摘要

- 本轮口径走完了 `147 行 → 293 可玩 → 304 可玩 → 名册 409 行 / 35 阻断`，四份文档里凡是
  「当前值」意义的数字都已改成 **409 / 304 / 35**，每处附产物名与复现命令。
- 任务书给的四个产物尺寸与盘上实测**不一致**（队友与我在本轮都重生成过），文档一律按盘上实测落笔，
  差值在下表「仍然存疑的数字」里逐条列出。
- 测试数按实跑落笔：Python `Ran 891 tests`，ctest `audit 36` / `desktop 38`。台账块原来写
  `audit 29 / python 680 / desktop 38`，已过期。
- 新增守卫 `tools/tests/test_doc_numbers.py`（10 例）：产物内部闭合 + 文档词组与产物对齐，
  数字过期时点名到文件。

## 一、权威读数（本次命令输出）

| 口径 | 读数 | 命令 |
| --- | --- | --- |
| 名册 | `plants=409 authored=147 pack=262 playable=304 blocked=35 conflicts=44 merged=409 packRoster=339` | `python tools/obb_build_content_v2.py --content-report` |
| 可玩 / 阻断 | `total=339 playable=304 new=262 blocked=35 missingCost=23(null 2/zero 21) missingFamily=0 missingArt=15 both=3` | `python tools/contentc/plant_playable.py --check` |
| 关卡可玩性 | `levels=1809 playable=1340 blockedDataOnly=454 blockedMinigame=16 blockedBoth=1 playableInEngine=1225` | 读 `native/generated/level_playability.json` 的 `counts` |
| 美术索引 | `bases_total 1135 / ok 1134 / failed 0 / skipped 1 / popanim_matched 591 / popanim_null 543` | 读 `PvZ2SHUTTLE/assets/db/shuttle/index.json` 的 `counts` |
| 美术命中 | `contentPlants {total 409, webHit 134, missing 275, shuttleHit 0}`（exit 1） | `PvZ2SHUTTLE.exe --art-audit content` |
| 卡组注册表 | `registry=134/409`、`plants=41`、`slots=7194` | `python tools/contentc/decks.py` |
| Python 测试 | `Ran 891 tests in 723.555s — OK (skipped=2)`，exit 0 | `python -m unittest discover -s tools/tests -p "test_*.py"` |
| C++ 测试数 | `audit 36` / `desktop 38` | `ctest --test-dir build/native -N`、`ctest --test-dir build/desktop-gate -N` |
| 商店可购买 | `catalogue rows=585 buyable=72 unmodelledCurrency=479` | `docs/reviews/2026-11-25-shop-payloads.md:48` |

产物尺寸（`Get-Item ... | Select Length`，2026-11-26 实测）：

| 产物 | 盘上实测 | 任务书给的 |
| --- | ---: | ---: |
| `vasebreaker.json` | 186,021 B | 186,116 B |
| `minigames.json` | 1,222,686 B | 1,222,781 B |
| `minigame_rules.json` | 41,496 B | 41,496 B |
| `loot_binding.json` | 537,332 B | 537,332 B |
| `metagame.json` | 732,730 B | 730,277 B |
| `plant_playable.json` | 200,287 B | 200,236 B |
| `plant_levels.json` | 821,708 B | 821,708 B |
| `level_extra_rules.json` | 359,996 B | 359,996 B |
| `level_playability.json` | 1,394,571 B | 1,394,571 B |
| `lawn_strings.json` | 2,877,130 B | 2,877,130 B |
| `plant_blocked.json`（新） | 9,893 B | — |

## 二、逐处改动（文件:行 / 旧 → 新 / 依据）

| 文件:行 | 旧 | 新 | 依据 |
| --- | --- | --- | --- |
| `docs/COMPLETENESS.md:27` | `111/147 有旧美术、7 株走新提取、29 株缺` | `134/409 命中美术、275 株缺` | `--art-audit content` |
| `docs/COMPLETENESS.md:33` | `263 Python 例 + 13/18 C++ 例` | `891 Python 例 + ctest audit 36 / desktop 38 项` | `unittest discover`、`ctest -N` |
| `docs/COMPLETENESS.md:60` | `包内 295 株植物 / 1107 个僵尸行没有任何客户端 id`（无后文） | 同句补 `其中 262 株已由 t83 补进名册`，并给 `409 行 = 手工 147 + pack 派生 262` / `仍在外面的 33 株` | `--content-report` |
| `docs/COMPLETENESS.md:121` | `--art-audit（t14）：content 147 株…` | 标为 `t14 口径；2026-11-26 复跑见 C19/C20` | 版本口径句 |
| `docs/COMPLETENESS.md:124` | `29 株内容植物无任何美术` | 补 `按 409 行名册复跑后是 275 株缺（webHit 134）` | `--art-audit content` |
| `docs/COMPLETENESS.md:125` | `独立形象覆盖 31/147≈21%` | 补 `（手工行口径，未按 409 行重算）` | 口径标注 |
| `docs/COMPLETENESS.md:126` | `提取到 218/1087 base（pending 867…）` | 补 `2026-11-26 索引已是 1135 base / ok 1134 / failed 0 / skipped 1` | `index.json` counts |
| `docs/COMPLETENESS.md:237` | `全量批在跑（1087 个可提取 base）：ok=543 / failed=10 / pending=534` | 标为 `t16 口径`，并给当前 `1135 base / ok 1134` | `index.json` counts |
| `docs/COMPLETENESS.md:826` | `29 株缺美术；独立形象仅 31/147` | `275 株缺美术（409 行里 webHit 134）；独立形象仅 31/147（手工行口径）` | `--art-audit content` |
| `docs/COMPLETENESS.md:881` | `1107 个 pack-only 僵尸 + 295 个 pack-only 植物` | `+ 仍有 33 株 pack-only 植物（原 295 株里 262 株已由 t83 补进名册）` | `plant_blocked.json` |
| `docs/COMPLETENESS.md:924-931` | §2.34 表「六份」；`vasebreaker 186,116` / `minigames 1,222,781` / `metagame 730,277` / `plant_playable 200,236` + `293 可玩 / 46 阻断` | 「七份」；四处尺寸按盘上；`304 可玩（42 同名 + 262 新增）/ 35 阻断（缺成本 23 / 缺美术 15 / 两者 3）`；**新增 `plant_blocked.json` 一行** | `--content-report`、`plant playable --check` |
| `docs/COMPLETENESS.md:964-968` | 「明确不做」第 1 条以 `维持 147` 收尾 | 加 `2026-11-26 改判（t83）`：旧口径作废、名册 409、35 条阻断留在 `plant_blocked.json`、指向 t83 报告 | `--content-report` |
| `docs/COMPLETENESS.md:970` 附近（C57） | 「消费者 0」「三组元素美术未解压」 | 补 `world.cpp:69-77` / `world.cpp:167-180` / `main.cpp:288-290` 与缺层接线点（`flow.cpp:10`、`flow.cpp:59`、`worldmap.cpp:232`）；元素美术改为已由 C61 提取 | t75 追加报告 §六 |
| `docs/COMPLETENESS.md` C62 | `plant 293` 与名册混用风险 | 补 `这里的 293 是掉落行数（rewards_from_pack.json 的 byKind.plant），与名册 409 无关` | `rewards_from_pack.json` |
| `docs/COMPLETENESS.md:981-982`（C61/C62） | 索引规模缺口描述 | C61 的 `1087 → 1135` 与 `ok/failed/skipped=1132/2/1` 保留为观测；C62 补名册无关说明 | 同上 |
| `docs/PROGRESS.md:13` | `audit 29/29、Python 680、desktop 38/38` | `ctest audit 36 / desktop 38 项、Python 891`，并说明三项 ledger 已按 2026-11-26 实测刷新 | `ctest -N`、`discover` |
| `docs/PROGRESS.md:27` | `192 植物、1072 僵尸没有行` | `33 株 pack-only 植物、1072 僵尸没有行；名册已到 409（手工 147 + pack 派生 262）` | `--content-report`、`plant_blocked.json` |
| `docs/PROGRESS.md:29` | `植物 147` | `植物 409（手工 147 + pack 262）`，缺口列补 `registry=134/409、plants=41` | `--content-report`、`decks.py` |
| `docs/PROGRESS.md:31` | 变体玩法行无 `level_playability` 读数 | 补 `可玩 1340 / 仅数据 454 / 小游戏 16 / 引擎可跑 1225` | `level_playability.json` |
| `docs/PROGRESS.md:33` | `1087 base / 1085 提取成功` | `1135 base / 1134 提取成功` | `index.json` counts |
| `docs/PROGRESS.md:53` | `植物/僵尸内容行只有 147/55` | `409/55`，证据列给 409 的分解与 `33 株 pack-only` | `--content-report` |
| `docs/PROGRESS.md:63` | `585 件里可买 21 件` | `585 件里可买 72 件（shop-payloads.md:48）` | `shop-payloads.md` |
| `docs/PROGRESS.md:126-129` | §6「数字来源」无名册/可玩/关卡可玩性/新表尺寸四行 | 增四行，每行给命令 | 见下「三」 |
| `docs/PARITY_BASELINE.md:28-35` | 审计块 `plants=147 / vasebreaker=45 / synthesized_vasebreaker=42` | `plants=409 / vasebreaker=47 / synthesized_vasebreaker=44`，并注明是 2026-11-26 复跑口径 | `--audit-content content` |
| `docs/PARITY_BASELINE.md:257-258` | 台账 `audit 29` / `python 680` / `desktop 38` | `audit 36` / `python 891` / `desktop 38` | `ctest -N`、`discover` |
| `docs/PARITY_BASELINE.md:529-555` | 无这一节 | 新增「名册 409 与可玩 304（2026-11-26）」：读数表 8 行 + 三条口径要点（美术索引重建会改可玩判定、`source:"pack"` 不是手工证据的五处 loader、147 与 339 的关系） | 见「一」 |
| `docs/superpowers/plans/2026-11-20-full-native-replica.md:101` | `audit 27 / Python 469 / desktop 36` | `ctest audit 36 / Python 891 / desktop 38`（指向台账块） | 同上 |
| 同文件:106 | `audit 27/27、Python 469、desktop 36/36，台账三项一致` | `台账三项（audit 36 / Python 891 / desktop 38）与实测一致` | 同上 |
| 同文件:107 | `295 植物 / 1107 僵尸在客户端侧没有 id` | `33 株 pack-only 植物、1107 僵尸行…；名册现为 409 行 = 手工 147 + pack 派生 262` | `--content-report` |
| 同文件:112 | `OBB 1085/1087 base` | `1134/1135 base`（+ `--art-audit` 134/409、缺 275） | `index.json`、`--art-audit` |
| 同文件:113 | `商店 585（可买 21…` | `商店 585（可买 72…` | `shop-payloads.md` |

## 三、复现命令（新增到 PROGRESS §6）

```powershell
# 植物名册 / 可玩子集
python tools/obb_build_content_v2.py --content-report   # plants=409 authored=147 pack=262 playable=304 blocked=35
python tools/contentc/plant_playable.py --check          # total=339 playable=304 blocked=35 missingArt=15

# 关卡可玩性
python -c "import json;print(json.load(open('native/generated/level_playability.json'))['counts'])"

# 新表尺寸
Get-ChildItem native/generated/vasebreaker.json,native/generated/minigames.json,native/generated/plant_blocked.json | Select-Object Name,Length

# 测试数
python -m unittest discover -s tools/tests -p "test_*.py"
ctest --test-dir build/native -N
ctest --test-dir build/desktop-gate -N
```

## 四、守卫测试 `tools/tests/test_doc_numbers.py`（10 例）

| 用例 | 断言 |
| --- | --- |
| `ArtifactFacts::test_playable_and_blocked_come_from_the_same_roster` | `playable == playableAuthored + playableNew`、`playable + blocked == total(339)` |
| `ArtifactFacts::test_blocked_artifact_matches_the_playable_tally` | `len(rows) == playable.blocked`，`missingCost/missingArt/both` 三项与 playable counts 逐项相等，`23 + 15 − 3 == 35` |
| `ArtifactFacts::test_roster_rows_are_authored_plus_pack` | 147 / 262 / 409 且 id 唯一 |
| `CompletenessDoc::test_completeness_quotes_the_current_playable_and_blocked_counts` | 文档含 `**304 可玩**` 与 `**35 阻断**`，值取自产物 |
| `CompletenessDoc::test_completeness_lists_plant_blocked_as_an_artifact` | 产物表有 `plant_blocked.json` 且尺寸等于 `stat().st_size` |
| `CompletenessDoc::test_completeness_does_not_repeat_the_retired_decisions` | 不得再出现 `维持 147` / `293 可玩` / `46 阻断` 三个作废口径 |
| `ProgressDoc::test_progress_states_the_roster_split` | 含 `手工 147 + pack 派生 262` 与 `409` |
| `ProgressDoc::test_progress_quotes_the_level_playability_counts` | 含「可玩 1340 / 仅数据 454 / 小游戏 16 / 引擎可跑 1225」四个当前值 |
| `BaselineDoc::test_baseline_section_quotes_the_artifacts` | 有「名册 409 与可玩 304（2026-11-26）」节，且 304 / 35 / 35 条与产物一致 |
| `BaselineDoc::test_baseline_ledger_matches_the_tree` | `<!-- test-counts -->` 块含 audit / python / desktop 三行 |

实测：`python -m unittest tools.tests.test_doc_numbers` → `Ran 10 tests … OK`。

> 守卫的第一次运行为红：`COMPLETENESS.md` 的改判句里写了「不再『维持 147』」，被自己的禁用词命中。
> 改写成「旧口径（只留手工行）作废」后转绿 —— 这条记录留着，提醒改判句不要复述作废口径。

## 五、仍然存疑的数字（无法用产物证实，未猜）

1. **任务书给的四个尺寸**：`vasebreaker 186,116`（实测 186,021）、`minigames 1,222,781`（实测 1,222,686）、
   `metagame 730,277`（实测 732,730）、`plant_playable 200,236`（实测 200,287）。差值来自本轮多次重生成
   （队友改 `rail`/`metagame` 编译，我 18:31 那次跑 playable），文档按盘上落笔。
2. **`test-counts` 台账的语义**：`tools/check_all.ps1` 里 python 是「floor」（低于台账才红、高了只 warn），
   audit/desktop 必须精确。文档写 891 是「当前实测」，不代表门禁会因此变红。
   另：本轮实测期间这个数字在动（我开工时 841，收尾时 891 —— 队友在并行加用例），
   所以文档里的 891 是「2026-11-26 21:00 读数」，不是长期常量；下次全量跑若更大，改台账与据此的三处括注即可。
3. **`C20` 的 `31/147`**：这是手工行的独立形象比例，产物里没有按 409 行重算的对应字段，
   保留原数并标注口径，未推测新比例。
4. **`PARITY_BASELINE` 早段的历史读数**（:67 `植物 339/147`、:84 `exact shared 44/147`、:98/:150/:178/:210/:214 的
   147/41 等）：都是带日期的事件记录（S1/S3/S6 落地时点），不是「当前值」，未改。
5. **plan §0「现状基线（2026-11-20 实测）」与 Task 0.1 的 `Expected: … 147 植物 …`**：属历史快照，
   按「只改 §1.1/§1.2」的要求保留。
6. **`docs/reviews/2026-11-25-plant-*.md` 里的 147/293/46**：那是当天的观测报告，属历史，
   本次未改（写作用域也不含）。

## 六、边界

- 未 commit；未改 `native/**`、`content/**`、`tools/contentc/**`，未改其它 `docs/reviews/*`。
- 改动文件：`docs/COMPLETENESS.md`、`docs/PROGRESS.md`、`docs/PARITY_BASELINE.md`、
  `docs/superpowers/plans/2026-11-20-full-native-replica.md`、`docs/reviews/2026-11-26-doc-number-sync.md`（本文件）、
  `tools/tests/test_doc_numbers.py`。
- 顺手修掉一处自伤：新增 «名册 409» 一节时把 `## 冒烟基线变更记录` 标题吞掉，已插回。
