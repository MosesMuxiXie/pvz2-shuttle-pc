# B4 成就屏 + 每日挑战屏（t87）

日期 2026-11-26 · 执行 auditor (t87, attempt `94649255-a58c-4a11-bca8-43eff3e0ff76`) · 只读报告，未提交

## 0. 结论

两屏按队长收窄后的范围落地：`achievements_view.{hpp,cpp}` 与 `daily_view.{hpp,cpp}` 各自暴露一个纯入口
（`renderAchievementsHeadless` / `renderDailyHeadless`）产出无头 JSON 与 PNG；`main.cpp` 与
`menu_view.cpp` **一行未改**，菜单入口与 `--achievements` / `--daily` 分发留给队长接线；`PvZ2SHUTTLE`
的源列表未动，CMake 只新增四个测试目标。

数据口径上有两处必须讲清楚的减法，都写进了 UI 与本文：

1. **成就奖励一律不可发**。`metagame.json` 的 53 条全是 `serverOnly:true` + `rewards:null`，
   编译器自己的 `unknowns[U4]` 已声明「没有奖励表，未编造任何数值」；截图右下角固定写
   「这些成就由服务器结算，本地只展示条件」。
2. **进度只有三条能算**。53 条里只有 `COWBOY_STARS` / `EGYPT_STARS` / `PIRATE_STARS` 能在本地
   用存档的星数推出数字（`Progress::levels` 的 `stars` 求和），其余 50 条没有阈值可比，显示 `-`。
3. **每日挑战没有日期**。11 条 `params` 里唯一的排期字段是 `Disabled`（全为 `false`），
   没有起止时间、没有轮换表，所以 open = `Disabled == false`，截图右下角写明这一点，
   不画倒计时。

证据全部是实跑输出，见 §6–§8。

## 1. 快照（本轮新增/修改的文件）

| 文件 | sha256 前 12 | 字节 | 行 |
| --- | --- | --- | --- |
| `native/src/achievements_view.hpp` | `FB5422ED314D` | 5,740 | 103 |
| `native/src/achievements_view.cpp` | `1E049E228A48` | 14,660 | 317 |
| `native/src/daily_view.hpp` | `99C1251979BF` | 3,794 | 77 |
| `native/src/daily_view.cpp` | `212920F01FD2` | 13,036 | 284 |
| `native/tests/achievements_test.cpp` | `1BDD2FDE46D2` | 15,156 | 321 |
| `native/tests/daily_test.cpp` | `9F5239E1DE42` | 12,259 | 255 |
| `native/CMakeLists.txt` | `C93A85C14C70` | 35,013 | 520 |

数据源 `native/generated/metagame.json`（他人 18:30 重生成，`318F088ED859` / 732,730 B）——
本轮只读，未改；重生成后两屏测试仍全绿（§6）。

## 2. 数据事实（`metagame.json`，只读）

- `achievements.entries` 53 条：`{id, titleKey, descKey, resolved{title,titleZh,desc,descZh},
  serverOnly:true, rewards:null, rewardSource:"serverOnly"}`；`achievements.serverOnly` 53 个 `true`；
  `counts.achieveKeys = 114`（title 53 + desc 53 + 8 个别名键）。
- `quests.daily` 11 条：`{id, nameKey, targetType, params, rewards[{amount,type,subtype}],
  slot:"DailyActivities", rewardSource:"QuestData.CompletionAwards"}`；`params` 键并集
  `ActionsToPerform / CountRemainingLabel / Disabled / OverrideQuestTheme / Priority /
  QuestCategory / Repeatable / Slot`；**11 条 `Disabled` 全为 `false`，`Repeatable` 全为 `true`，
  没有任何日期或轮换字段**。
- `quests.tabs` 2 条（`DailyActivities` showTimer=true / `EpicQuests` showTimer=false），
  `tabOrder = ["DailyActivities","EpicQuests"]`。
- 仓库内**没有**本地化文本表（`content/` 无 loc 文件；`resolved.titleZh:true` 只表示 OBB 里查到了
  这个键）。因此屏幕上显示的名字是从 key 机械转写来的，不是翻译 ——
  `humanizeGameKey("ACHIEVE_ALL_IN_JEST_TITLE") == "All In Jest"`，
  `humanizeGameKey("ACHIEVE_EIGHTIES_BACK_FROM_THE_FUTURE_3_TITLE") == "Eighties Back From The Future 3"`。

## 3. 成就屏

### 3.1 字段映射

| 屏幕列 | 来源 | 说明 |
| --- | --- | --- |
| 名称 | `titleKey` → `humanizeGameKey` | 去 `ACHIEVE_` 前缀与 `_TITLE` 后缀，下划线转空格并做 Title Case |
| 进度 | `Progress::levels` 的 `stars` 按 `<world>_` 前缀求和 | 仅 `*_STARS` 三行；`0 星（cowboy）` 也算答案，不写成 `-` |
| 其它 50 行 | — | 表里没有阈值，写 `-`；不臆造「击杀 N」「通关 N」 |
| 徽标 | `serverOnly` | 53 行全为真，画 `server` 徽标 |

`PageRange::of(rows, page, perPage)`：53 行 / 每页 12 → 5 页，末页 5 行；页码越界 `std::clamp`
到最后/第一页；0 行仍算一页。测试断言五页 `count` 之和恰为 53（不重不漏）。

### 3.2 无头 JSON

```json
{"screen":"achievements","total":53,"serverOnly":53,"perPage":12,"page":0,"pages":5,
 "visible":[{"id":"ALL_IN_JEST","title":"All In Jest","progress":"-","server":true}, …]}
```

键集与每行键集都在 `testJsonShape` 里逐字断言（`screen/total/serverOnly/perPage/pages/page/visible`
与 `id/title/progress/server`），队长接线时形状不会再漂。

### 3.3 桌面绘制

标题 30 px、副标题 20 px、列头 16 px、行文 20 px、进度 18 px、`server` 徽标 16 px；
右侧固定说明（18 px，accent 色）：

```
这些成就由服务器结算，本地只展示条件
```

键盘：`Esc` 退出、`PgUp`/`PgDn` 翻页、`↑`/`↓` 移动焦点。布局常量集中在
`AchievementsLayout`（1280×720、`kPerPage=12`、行区 `kRowLeft=40 / kRowTop=116 /
kRowWidth=1200 / kRowHeight=42`），测试按这些常量去数像素，不另写一份坐标。

## 4. 每日挑战屏

| 屏幕列 | 来源 |
| --- | --- |
| 名称 | `nameKey` → `humanizeGameKey` |
| 目标 | `targetType`（原样显示，例如 `BeatXAdventureLevelsQuestData`） |
| 奖励 | `rewards[]` 拼字符串：`2000 金币` / `10 宝石` / `2 薄荷币` |
| 状态 | `params.Disabled == false` → `开放`，否则 `关闭` + 原因 `包内标记 Disabled=true` |

`payable`（本客户端能否真的发放）只在**全部** rewards 都是 `coins` 时为真：本作只有金币有来源与去处
（商店），宝石与薄荷币在 `shop.cpp` 里仍是「not modelled yet」。11 条里恰好 5 条 payable
（`COLLECT_SEED_PACKETS_40_DQ`、`PLAY_LEVEL_OF_THE_DAY_DQ`、`STORE_BUY_SKU_FREE_GIFT_DQ`、
`WATCH_1_AD_DQ`、`WIN_POTW_LTE_LEVEL_DQ`），6 条含宝石/薄荷币。屏幕右下角固定写：

```
排期字段只有 Disabled：false 即开放，包里没有日期
```

无头 JSON：

```json
{"screen":"daily","total":11,"open":11,"tabs":2,"perPage":12,"page":0,"pages":1,
 "visible":[{"id":"COLLECT_SEED_PACKETS_40_DQ","title":"Collect Seed Packets",
             "target":"SeedPacketsCollectedQuestData","reward":"2000 金币",
             "open":true,"payable":true}, …]}
```

**「开放」是本轮唯一诚实的判定**：表里 11 条全 `Disabled:false`，所以现在 11 条全部 open。
交付里不写「今天开放哪几条」——那需要一个日期源，仓库里没有。`testDisabledClosesTheRow`
用一张临时 sheet（一条 `Disabled:true`）证明这个标志真的被读、真的会关行，而不是恒真。

## 5. 测试（9 段纯逻辑 + 2 段绘制）

`native/tests/achievements_test.cpp`：

| 段 | 断言要点 |
| --- | --- |
| `testShippedModel` | 53 行、`serverOnly==53`、id 唯一、`titleKey` 前后缀、标题不含下划线 |
| `testHumanize` | 三个具名转写 + 空串 |
| `testPageRange` | 5 页 / 末页 5 行 / 越界 clamp / 11 行单页 / 0 行一页 / 五页合计 53 |
| `testOnlyStarRowsCarryNumbers` | 含「星」的行恰为 3；egypt 10×2=20；cowboy 无进度写 `0 星` |
| `testEmptySaveShowsZeros` | 空存档下三条星行仍写 `0 星`，其余 `-` |
| `testJsonShape` | 顶层键集、行键集、末页 5 行、`server==true` |
| `testRenderWritesPng`（desktop） | 写 PNG、>10 KB、1280×720、行区 ink>500、翻页像素不同、缺字体抛 `font_zh.ttc`、失败不留文件 |

`native/tests/daily_test.cpp`：`testShippedModel`（11 / open 11 / tabs 2 / 标题无下划线 / targetType 非空）、
`testRewardLines`（三类币种文案 + 恰好 5 条 payable）、`testDisabledClosesTheRow`（临时 sheet 一条关闭 →
open==1 且 reason 含 `Disabled`）、`testPageRange`（11/12 单页、perPage 4 三页、越界 clamp）、
`testJsonShape`（键集、行键集、`open==11`）、`testRenderWritesPng`（同成就屏，另加 perPage 4 与 11 像素不同）。

**这些断言能变红**：本轮修 bug 时就红过三次 ——
`no cowboy progress in this save, the row must show -, got 0 星（cowboy）`（断言写错，改成 0 星后转绿）、
`'sdl': is not a class or namespace name` 与 `'SDL_RenderDrawRect_renamed_SDL_RenderRect'`
（编译期红灯，见 §9）。翻页、payable、Disabled 三条都各有独立断言，删掉对应实现就会红。

## 6. 构建与门禁

```
pwsh -File tools/build_native.ps1 -AuditOnly -BuildDir C:\pvzbuild\ach1
  18/34 Test #18: achievements .....................   Passed    0.65 sec
  19/34 Test #19: daily ............................   Passed    0.65 sec
  88% tests passed, 4 tests failed out of 34
```

四个红是别人在飞的改动，逐条原文（不是我的文件）：

```
catalog:    (见 §9 的清单)
engine:     engine test failed: ailmint must be pack-only, not in content JSON
art audit:  art audit test failed: eight content plants share the fixture's web art, got 13
s5 boss:    s5 boss test failed: boss level pirate_41 neither spawned a boss nor reported boss_unavailable
```

桌面配置（只编/跑我这两个目标，因为同树的 `audio_test.cpp` 正在被别人编辑）：

```
ctest --test-dir C:\pvzbuild\ach1d -C Release -R "^(achievements_render|daily_render)$"
2/3 Test #45: achievements_render ..............   Passed    2.39 sec
3/3 Test #46: daily_render .....................   Passed    4.23 sec
```

（第三条 `worldmap_render` 是 "Not Run" —— 该目标没有在我的构建目录里编译，与这两屏无关。）

## 7. 截图

| 文件 | 尺寸 | 字节 | sha256 |
| --- | --- | --- | --- |
| `build/t87/shots/achievements.png` | 1280×720 | 63,227 | `EA1AD0AA97B36768F0E7C7D08084C83462B2A751EC0636DCDE63F62941601D29` |
| `build/t87/shots/achievements-page4.png` | 1280×720 | 39,185 | `1FB7C61D51C0883284DFCD8530E7A18329A7D9DE6BAAA265A863A902552EB3F5` |
| `build/t87/shots/daily.png` | 1280×720 | 92,927 | `058DB08AE7E92CCC52C1F6E66736332E572A853D516CEFDB1BAE217053628890` |
| `build/t87/shots/daily-paged.png` | 1280×720 | 48,937 | `10E3BE77EC23864E3307B7A1CAC777FB592CE027FD32DB8045A0D2AA65263233` |

全部 > 10 KB、全部 1280×720（`System.Drawing` 实测）。`page 0` 与 `page 4` 的截图不同像素，
证明翻页真的换了内容而不是重画同一屏。

**`--battle-snapshot` / `--menu` 哈希**：队长明确这两条基线正在被 vase/rail 改动，本轮不当硬约束。
替代证据是 §8 的 smoke 逐场景 diff —— 32 个场景里只有 1 个变，变的那一个是矿车世界。

## 8. smoke 逐场景 diff（我的屏没碰战斗）

```
python tools/engine_smoke.py --exe C:\pvzbuild\ach1\Release\PvZ2SHUTTLE.exe --out build\t87\smoke.json
SMOKE_EXIT=0   rows base=32 new=32
changed=1
world cowboy: hash 0xeb036737659cbc46 -> 0xcb83dd8dcba537f5; status playing -> playing; tick 7200 -> 7200
```

唯一的差异是 `world cowboy`，状态与 tick 都没变，只有 hash 变 —— 与 patcher 的 `rail.cpp` / `world.cpp`
改动（矿车轨道）指向同一个世界，与本轮两个「画屏」文件无关：`PvZ2SHUTTLE` 的目标源列表没有加入
`achievements_view.cpp` / `daily_view.cpp`，二进制里根本没有这两个屏。其余 31 个场景逐字节相同。

## 9. 环境注记（都不是本轮引入）

1. **`audio_test.cpp` 编译错误**（`error C3083: 'Json': the symbol to the left of a '::' must be a type`，
   `native/tests/audio_test.cpp:476`）在 18:2x–19:1x 期间让**整棵树的 audit/desktop 构建**失败。
   我因此只能用 `--target achievements_test,daily_test` 单独验证，并另配一个桌面目录只编两个渲染目标。
2. **`PVZ_TEST_ASSETS` 指向 `native/../../../PvZ2SHUTTLE/assets`**，本机实际资产在
   `D:\OneDrive\文档\pvz_shuttle\PvZ2SHUTTLE\assets`（两个 `..`）。`ctest` 跑我的渲染目标时字体能找到
   （说明该变量在本机的解析结果可用），但手工跑 exe 时必须传真实路径。
3. **MSB6001 `NO_PROXY`/`no_proxy`**：直接调 `cmake --build` 会触发（本机环境块里大小写重复）。
   `tools/build_native.ps1` 自带清理；我另写了 `build/t87/tbuild.ps1`（照抄它的
   `ProcessStartInfo` 环境重建）用于只编单目标。
4. **`C:\pvzbuild\ach1` 目录复用事故**：我第一次直接用 `cmake -S native -B` 时没有编译器环境，
   留下了半初始化的缓存；脚本随后复用该缓存，项目文件停在 18:11 的源列表，缺 `rail.obj`，
   链接报 `RailTable::shared` 未定义。删目录重建后消失。**教训：失败的 configure 必须删目录重来。**

## 10. 未做（明确登记）

- **真实服务器同步**：`serverOnly` 的成就与每日挑战都只展示条件，客户端不发奖、不做对账，
  也没有任何网络代码。
- **成就解锁通知/弹窗**：本轮只有列表屏。
- **本地化文本**：仓库没有 loc 表，标题是 key 的机械转写（§2）；要真中文名需要先落一张 loc 表。
- **每日挑战的日期语义**：表里没有日期字段，所以只做 `Disabled` 开关；“今天开放哪些”需要外部时钟/轮换源。
- **菜单入口与 `--achievements` / `--daily` 分发**：按队长要求留给队长接线（不在本轮写作用域内）。

## 11. 复现命令

```powershell
# 纯逻辑（任意 cwd 都能找到 generated/metagame.json：PVZ_GENERATED_DIR 编译期已定义）
C:\pvzbuild\ach1\Release\achievements_test.exe C:\pvzbuild\ach1\scratch   # achievements tests passed
C:\pvzbuild\ach1\Release\daily_test.exe        C:\pvzbuild\ach1\scratch   # daily tests passed

# 绘制 + 截图（assets 必须指向真实目录）
$assets = 'D:\OneDrive\文档\pvz_shuttle\PvZ2SHUTTLE\assets'
C:\pvzbuild\ach1d\Release\achievements_render_test.exe $assets build\t87\shots
C:\pvzbuild\ach1d\Release\daily_render_test.exe        $assets build\t87\shots

# 只编我的目标（避开别人正在编辑的 audio_test.cpp）
pwsh -File build\t87\tbuild.ps1 -BuildDir C:\pvzbuild\ach1  -Target 'achievements_test,daily_test'
pwsh -File build\t87\tbuild.ps1 -BuildDir C:\pvzbuild\ach1d -Target 'achievements_render_test,daily_render_test' -Desktop ON
```
