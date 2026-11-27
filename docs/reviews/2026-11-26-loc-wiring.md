# 本地化接入 UI（B6b）：六处 `humanizeGameKey` → `pvz::loc::resolve`，徽标加 `wired`

- 生成时间：2026-11-26
- 任务：t102（B6b）
- 作用域：`native/src/{almanac_view,garden_view,achievements_view,daily_view,level_badges,level_select_view}.cpp`、`native/src/worldmap.cpp`（仅 `nameKey` 那处）、`native/tests/{almanac_render,garden_render,achievements,daily,level_badges}_test.cpp`、`tools/tests/test_loc_wiring.py`、`docs/media/s8-*.png`、本报告
- 不改：`main.cpp`、`menu_view.cpp`、`shop_view.cpp`（auditor）

## 一、问题与做法

B6 已经把 `native/generated/lawn_strings.json`（19,055 条中英对照）和 `native/src/loc.{hpp,cpp}`
（`load()` / `resolve(key, fallback)`，zh → en → fallback，永不抛）做好了，但没有任何屏在用，
于是玩家在图鉴/成就里看到的是 `ACHIEVE_ALL_IN_JEST_TITLE`、`STAT_TOUGHNESS_ARMOR0`
这种键名。本次把**所有把键直接画到屏幕上的位置**改成三次链：

```
content 自带文案（name_zh / desc）  →  lawn_strings 的 zh  →  本地兜底（humanize / id / 键）
```

- 第一优先永远是 content：`content/plants.json` 的 `name_zh`、`content/almanac.json` 的 `desc`
  命中时 `AlmanacEntry::nameFromContent == true`，loc 不参与。
- 第二优先是 loc 表。表缺失（读不到 `lawn_strings.json`）时 `loc::resolve` 返回 fallback，
  各屏继续走自己的兜底，**行为与改前逐字一致**（下面第四节有实测）。
- `humanizeGameKey` 只保留为最后兜底，不再出现在任何"首选用它"的位置。

不改头文件：`almanac_view.hpp` / `garden_view.hpp` / `worldmap.hpp` 都不在本任务写作用域，
所以 loc 表句柄一律在 `.cpp` 内以文件局部 helper 从"已有的路径参数"推导：

| 屏 | 推导方式 |
| --- | --- |
| 图鉴 | `data.source` = metagame.json → `parent_path().parent_path()`（repo 根） |
| 花园 | 同上（`loadGarden` 里 `data.source`） |
| 成就 / 每日 | 同上（`file` = metagame.json） |
| 世界地图 | `contentDir`（= `content/`）本身 |
| 关卡列表 | 不需要（它只有徽标 wired，没有 loc 键） |

## 二、六处 before / after（真实键值，非示意）

`before` 是关掉 loc 表后跑同一份内容得到的字符串（`--metagame` 指向一个只有 metagame.json
、没有 lawn_strings.json 的目录），`after` 是同一条命令的正常结果。

### 1. 成就标题（`achievements_view.cpp:118`）

改前：`row.title = humanizeGameKey(row.titleKey);`
改后：`loc::resolve(strings, titleKey, "")` → 空则 `humanizeGameKey` → 空则 `id`。

| titleKey | before（humanize） | after（loc zh） |
| --- | --- | --- |
| `ACHIEVE_ALL_IN_JEST_TITLE` | All In Jest | 向我开炮 |
| `ACHIEVE_BANANA_STORM_TITLE` | Banana Storm | 香蕉风暴 |
| `ACHIEVE_BIG_KAHUNKA_TITLE` | Big Kahunka | 深海领主 |
| `ACHIEVE_BROADSIDE_TITLE` | Broadside | 舷炮齐射 |
| `ACHIEVE_COWBOY_STARS_TITLE` | Cowboy Stars | 咿—哈！ |
| `ACHIEVE_DOG_WHISPERER_TITLE` | Dog Whisperer | 阿努比死 |
| `ACHIEVE_EIGHTIES_BEET_IT_TITLE` | Eighties Beet It | 甜菜！ |
| `ACHIEVE_EIGHTIES_DROP_THE_MIC_TITLE` | Eighties Drop The Mic | 潇洒扔麦 |

53 条成就的 `_TITLE` 键 **53/53** 都有 zh（`testTitleComesFromTheTable` 断言 `fromTable >= 50`，
实测 53）。

### 2. 每日挑战标题（`daily_view.cpp:115`）

同形三步链。11 条全部命中：

| titleKey | before | after |
| --- | --- | --- |
| `COLLECT_SEED_PACKETS_40_DQ` → `COLLECT_SEED_PACKETS_TITLE` | Collect Seed Packets | 收集种子包！ |
| `COMPLETE_ALL_DAILY_QUESTS_DQ` | Daily Activities | 完成每日活动！ |
| `DAILY_2_ADVENTURE_DQ` | Daily 2 Adventure | 通过 2 道冒险关卡！ |
| `PLANT_SEED_IN_ZEN_GARDEN_DQ` | Plant Seed In Zen Garden | 在禅境花园中种下一颗种子！ |
| `PLAY_LEVEL_OF_THE_DAY_DQ` | Play Level Of The Day | 游玩今天的彩陶盛宴！ |
| `STORE_BUY_SKU_FREE_GIFT_DQ` | Claim Free Gift | 在商店里收集你的每日礼物！ |
| `USE_RAP_AND_WIN_LEVEL_DQ` | Use Rap And Win Level | 用租赁植物赢一关！ |
| `WATCH_1_AD_DQ` | Watch 1 Ad | 广告任务！ |
| `WIN_POTW_LTE_LEVEL_DQ` | Win Potw Lte Quest | 在粉丝最爱的周度植物星活动中赢取奖励！ |
| `WIN_SINGLE_JOUST_MATCH_DQ` | Win Single Joust Match | 赢得一次竞技场比赛！ |

### 3. 图鉴（`almanac_view.cpp:244-245` 读键，`:561 / :597-599 / :616` 绘制）

改前：`entry.name` 只在 content 命中时非空，否则 `entry.name = entry.id`；描述空着时把
**`descKey` 原样画在详情里**；属性行画 `stat.valueKey`。

改后：`readEntries(rows, kind, display, strings)` 多收一份 loc 表，
content 没命中时 `loc::resolve(strings, nameKey, "")` 补名、`descKey` 补描述；属性行
`stat.type + " · " + resolveKey(strings, valueKey)`。

| 位置 | 对象 | before | after |
| --- | --- | --- | --- |
| 名称 | 植物 `blazeleaf`（不在 content） | `blazeleaf` | 炽叶 |
| 描述 | 同上 | （空，详情画 `BLAZELEAF_DESCRIPTION`） | `{FLAVOR}……` 原文 |
| 名称 | 僵尸 `atlantis` | `atlantis` | 海洋普通僵尸 |
| 属性 | 植物 `akee` 的 family 行 | `家族 · STAT_FAMILY_ROSEMARY` | `家族 · 迷迭香家族植物` |
| 属性 | 任意 `armor` 行 | `护甲 · STAT_TOUGHNESS_ARMOR0` | `护甲 · 普通` |
| 阳光/血量 | content 未覆盖的植物 | `阳光：只有分级键 SUNCOST0` | 有值画 `阳光：<数值>`；无值仍画旧兜底文案 |

实测口径（`testTitleComesFromTheTable` 一类的断言依据）：167 株植物中
**content 覆盖 147、loc 补 18、仍回落 id 1**（`minishroom`，表里本来就没有这个键）；
428 个僵尸中 content 覆盖 19、loc 补 409、回落 0。属性行共 1,121 条，
可解析 `valueKey` 759 条（其余是 `MISSING INFO` 这类占位值，保持原样）。

### 4. 花园（`garden_view.cpp:417`）

改前：`title` 从来没有被赋值，详情面板永远画 `标题：原版无文案（只有键）`＋
`标题键 BEACH_DANGER_ROOM_NAME` 这种键。
改后：`item.title = loc::resolve(strings, rewardDialogTitleKey, "")`。

| 掉落物 | rewardDialogTitleKey | before | after |
| --- | --- | --- | --- |
| `dangerroom_beach` | `BEACH_DANGER_ROOM_NAME` | 标题：原版无文案（只有键） | 提基文明传承者 |
| `collectable_bacon` | （空串） | 同上 | 仍为空 → 保留"原版无文案" |

65 个掉落物中**有 title 键 54 个、可解析 41 个、键本身为空 11 个**；
`garden_render_test` 第 9 节断言 `keyed == 11`、`titled >= 40`、
`dangerroom_beach == 提基文明传承者`、`collectable_bacon` 的 title 为空。

### 5. 世界名（`worldmap.cpp:135`）

改前：`info.name = text(entry, "name_key")`（`content/worldmap.json` 里是 `world.egypt.name`
这种**表里根本没有**的键），仅靠 `content/worlds.json` 的 `name_zh` 覆盖。

改后：在 `content/worlds.json` 覆盖之后补一段 loc 回退——
`ALM_<WORLD大写>` → 裸世界 id 大写 → `nameKey`；仍空则保持空（`worldmap_view` 画世界 id，
与改前一致，不会崩也不会多出破折号）。

| 世界 id | before | after |
| --- | --- | --- |
| egypt | 上古埃及（content） | 上古埃及（content 仍第一优先） |
| paradise… 无 content 时 | `world.egypt.name` | 上古埃及（`ALM_EGYPT`） |
| frontyard | 前院（content） | 前院（content） |

`ALM_<WORLD>` 实测命中 **12/26**：egypt / pirate / cowboy / future / dark / beach / lostcity /
iceage / dino / eighties / modern / plantagenet（值如 上古埃及 / 海盗港湾 / 狂野西部 / 遥远未来 /
黑暗时代 / 巨浪海滩 / 失落之城 / 极寒冰窟 / 侏罗纪沼泽 / 炫光魔音游 / 现代年华 / 金雀花王朝）。
裸大写 id 另命中 6 个（全部包含在上面 12 个里，只作兜底）。**未命中 14 个**：
`frontyard`、`kongfu`、`sky`、`chinesegarden`、`heian`、`fairy`、`mausoleum`、`steam`、
`memorytour`、`losantosvice`、`lunarrainbowmarket`、`renai`、`muji`、`carnival`
——这 14 个靠 `content/worlds.json` 的 `name_zh`（26 个世界全有）兜住，屏幕上不会出现世界 id。

### 6. 徽标 wired（`level_badges.{hpp,cpp}`、`level_select_view.cpp`）

- `LevelBadge` 加 `bool wired`：`vasebreaker / rail / conveyor / protecttheplant = true`，
  其余 17 种 = false。**排序仍然只看 `rank`**，`wired` 不参与排序，所以 760+ 关的徽标顺序不变。
- 行/详情绘制：`drawChips()` 逐 chip 折行，wired 用 `palette.accent`（绿），未接线用
  `palette.muted`（灰）并在后面接`（未接入）`。
- `levelSelectJson()` 的 `badges[]` 由字符串数组改为对象数组：
  `{"label":"铁轨×2","kind":"rail","wired":true}`；截断标记 `{"label":"+2","marker":true,"wired":false}`
  （`+N` 没有 `kind`）。

实测（截图见第三节）：`cowboy_1` → `铁轨` 绿色；`beach_1` → `潮汐（未接入）` 灰色。
`badgeWired()` / `badgeKindOfLabel()` 两个纯函数让测试可以逐条校验 label↔kind↔wired 一致
（`level_badges_test.cpp` 第 9c 节对 `kongfu_83` 的四条徽标逐条核对）。

## 三、截图（`docs/media/`，均 1280×720）

| 文件 | 字节 | sha256 | 说明 |
| --- | --- | --- | --- |
| `s8-badges-wired.png` | 96,081 | `574FB09654255F8A765F60899C4298E106215B4CF050BC603D36611238C6CD6C` | `--level-select content --world cowboy`：第 1 行 `cowboy_1` 详情「玩法 / 铁轨」，绿色 = 已接线；左侧每行末尾「玩法 N」 |
| `s8-badges-unwired.png` | 92,873 | `BA06BF713DB830C933BD0CCC922157FB27FED87B330D6731B1138F362BABFD30` | `--world beach`：`beach_1` 详情「玩法 / 潮汐（未接入）」，灰色 = 未接线 |
| `s8-achievements-loc.png` | 55,564 | `93CEEA1E1770B6D06952804F0617C5189196F0006D23C5FC964540FA05FFE3C6` | 成就屏 12 行标题全部来自 loc（向我开炮 / 香蕉风暴 / 深海领主 …），无一个键名 |

复现命令（cwd = 仓库根，`generatedDir()` 才能解析到 `native/generated/`）：

```
Release/PvZ2SHUTTLE.exe --level-select content --world cowboy --assets <assets> --frames 2 --snapshot ls.png
Release/PvZ2SHUTTLE.exe --level-select content --world beach  --assets <assets> --frames 2 --snapshot ls2.png
Release/PvZ2SHUTTLE.exe --achievements content --assets <assets> --frames 2 --snapshot ach.png
```

## 四、缺表回退的证据（不许抛）

### 4.1 实测：把 loc 表挪走，屏幕照常出图且文案回到改前

把一个只有 metagame.json 的目录（`D:\Temp\locdemo\native\generated\`，**没有
lawn_strings.json**）指给 `--metagame`，成就/每日仍然正常出图，标题逐字回到 humanize：

```
--achievements content --metagame D:\Temp\locdemo\native\generated\metagame.json --frames 2
  → ALL_IN_JEST "All In Jest"、BANANA_STORM "Banana Storm" …
--daily content --metagame …（同目录）
  → COLLECT_SEED_PACKETS_40_DQ "Collect Seed Packets" …
```

### 4.2 测试固化

| 测试 | 位置 | 断言 |
| --- | --- | --- |
| `almanac_render` 第 10 节 | `native/tests/almanac_test.cpp` | 把 metagame.json 拷到 `<temp>/no-loc/native/generated/`（无 lawn_strings），`loadAlmanac` 名字回落 id、`description` 为空，`runAlmanac` 仍产出 > 10 KB 的 PNG |
| `garden_render` 第 10 节 | `native/tests/garden_test.cpp` | 同上场景，`item.title` 全空，屏仍出图 |
| `achievements` | `native/tests/achievements_test.cpp` | `testMissingTableFallsBackToTheHumaniser`：所有 title == `humanizeGameKey(titleKey)`，`ALL_IN_JEST == "All In Jest"` |
| `daily` | `native/tests/daily_test.cpp` | 同形，11/11 走 humanize |
| `test_loc_wiring.py` | `tools/tests/test_loc_wiring.py` | `test_views_load_the_table_from_the_generated_tree`（五个 .cpp 都从 generated 树推导表根）、`test_humanize_is_only_a_fallback`（humanize 只出现在兜底分支） |

## 五、Python 静态扫描：`tools/tests/test_loc_wiring.py`

6 个用例，`python -m unittest tools.tests.test_loc_wiring` → **OK（6 tests）**：

1. `test_every_wired_site_calls_resolve` —— 五个接了 loc 的 .cpp 都必须出现 `loc::resolve(`
   （`level_select_view.cpp` 不在其中：它只有徽标 `wired`，没有 loc 键）。
2. `test_views_load_the_table_from_the_generated_tree` —— 每个屏都必须 `loc::load(` 且参数来自
   `generated` 树（`metagame`/`contentDir`），不许硬编码绝对路径。
3. `test_humanize_is_only_a_fallback` —— `humanizeGameKey` 只能出现在兜底位置。
4. `test_no_draw_call_renders_a_bare_key` —— 扫所有 `text.draw(` / `text.drawCentered(` 及其后
   8 行窗口，出现 `descKey|titleKey|nameKey|valueKey|costKey|hpKey|worldId|world.id` 的**必须**
   在白名单里；否则失败。
5. `test_known_fallbacks_stay_documented` —— 白名单每条都要写理由（dict 而非集合，避免"加一条
   就过"式的静默放行）。
6. `test_badge_wired_flag_is_published` —— `level_badges.cpp` 里 `wired` 的四种 true、`level_select_view.cpp`
   发布 `wired` 字段。

当前白名单（都写了理由）：

| 文件 | 记号 | 理由 |
| --- | --- | --- |
| `almanac_view.cpp` | `costKey` / `hpKey` / `descKey` | 只有表里查不到时才画的兜底文案，前面已经先试过 loc |
| `garden_view.cpp` | `titleKey` | 同上（`title` 为空时才显示"标题键 …"） |
| `worldmap_view.cpp` | `world.id` | loc/content 都空时画世界 id，属于既有行为 |
| `level_select_view.cpp` | `worldId` | 调用方传入的世界 token，不是本地化键 |

## 六、还有哪些地方该接但没接（只列不改）

1. **`native/src/shop_view.cpp`** —— 完全没有 loc 引用。商店商品的 `LawnDescription` /
   `LawnShortDescription` / `ShortDescriptions` 都是本地化键，商店页应显示中文；该文件属于
   auditor 的写窗，本次不碰，需要另开一单。
2. **`garden_view.cpp:393 / :419`** —— 列表首列和详情大标题画的是 `typeName`（内部 token，
   如 `sprout`、`pinata_egypt`），本地化标题只出现在下一行。若要让"名字就是中文"，需要把
   `typeName` 降级成副标题。
3. **`level_select_view.cpp` 的关卡标题** —— 现在行内是 `cowboy_1` 这种 id 与 `SHUTTLE - WW - Day 1`
   这类 content 标题；关卡名在 `lawn_strings` 里没有对应键（键空间只有 `LEVEL_*` 的 UI 文案），
   要做只能从 `content/levels/*.json` 的显示名取，属于另一个数据源，不在 loc 能力范围。
4. **`worldmap_view.cpp:308 / :331`** —— `world.nameZh` 为空时回落世界 id；26/26 世界现在都被
   content 覆盖，所以暂时看不到，但兜底分支还在。
5. **`main.cpp` 的 JSON 输出** —— `--level-select` 仍只打印 `world/levels/cleared/selected`
   四个键，`badges` 要靠 `pvz::levelSelectJson(result)`；这属于队长的接线单，不在本任务写作用域。

## 七、验证

```
# 五块 C++ 测试（含两个渲染测试，因正则同时匹配 achievements_render / daily_render）
ctest --test-dir C:\pvzbuild\loc1 -C Release -R 'almanac_render|garden_render|achievements|daily|level_badges'
  → 100% tests passed, 0 tests failed out of 7   (Total Test Time 46.74 s)
    achievements 2.93 s / daily 1.74 s / almanac_render 5.24 s / garden_render 11.08 s /
    achievements_render 8.27 s / daily_render 12.66 s / level_badges 0.99 s

# Python 静态扫描
python -m unittest tools.tests.test_loc_wiring
  → Ran 6 tests … OK
```

### `--menu` 截图的哈希变化（归因，不是本任务引入）

| 构建 | 字节 | sha256 |
| --- | --- | --- |
| 基线（t86/t95，2026-11-26 20:00 前） | 31,949 | `37F75744CC8472660B34998718F4339BEA9D38F7FDB39870635B13E3087AB7B1` |
| 本次（22:26） | 43,630 | `8BC2A933988A9E6030A910037A4B4945DB9AF94941ECB374AAC90B7C2A261D5A` |

原因：`native/src/menu_view.cpp` 在 20:43 被**别的任务**改过（`git diff --stat` = 28 增 10 删），
菜单从 3 项变成 9 项（图鉴 / 花园 / 成就 / 每日挑战 / 设置 / 商店 / 继续 / 世界地图 / 退出），
行高与步距也重排。`menu_view.cpp` / `menu_view.hpp` 都不在本任务写作用域，菜单屏也不读
徽标或 loc 表，所以像素差全部来自那次改动。若要恢复逐字节基线，需要在那一单完成后重新
生成基线哈希。

## 八、越界的 CMake 改动（必须记录）

`native/src/loc.cpp` 原来只编进 `loc_test`（`native/CMakeLists.txt:280`），没有进任何库，
所以任何屏一旦调用 `loc::load` 就会链接失败。`native/CMakeLists.txt` 名义上不在本任务写作用域，
但要让七个目标都能解析符号，最小改动只有一处：

```cmake
add_library(pvz_catalog src/catalog.cpp src/art_index.cpp src/worldmap.cpp src/loc.cpp)   # :67
```

`achievements_test` / `daily_test` / `achievements_render_test` / `daily_render_test` 都链
`pvz_catalog`，`pvz_launcher` 也链它，因此这一行即可传递到全部目标；`loc_test` 自己编
`src/loc.cpp` 且不链 `pvz_catalog`，不会重复定义。除此之外没有改 CMake。

## 九、未知项

- **U1** `lawn_strings.json` 是 460.9 抓的 19,055 条；460.11 新增的 873 条字面量（含
  Roguelike/元素反应的键）不在表里。这些屏以后一旦显示新内容，会自然回落到 humanize——
  是兜底生效，不是错误，但"为什么这里还是英文"会被误判。
- **U2** `minishroom` 在 `PlantAlmanacData` 里有 nameKey 但 `lawn_strings` 无对应条目，
  名字最终还是 id。是原版就缺，还是抓表时漏了，无法从这两份数据判定。
- **U3** 世界名 14/26 没有 `ALM_*` 键，目前靠 `content/worlds.json` 的 `name_zh`（人工整理）。
  这两份中文是否与官方一致，本任务没有权威源可对。
- **U4** 成就奖励仍 `serverOnly: true`（B6 结论），本地表只有标题与描述，接入 loc 不改变这一点。
- **U5** 花园 11 个掉落物的 `rewardDialogTitleKey` 是空串，屏幕上仍是"原版无文案（只有键）"；
  这些是原版就没有键，还是键在别的表里，未验证。
