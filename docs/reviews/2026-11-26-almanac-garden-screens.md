# B3 图鉴屏与花园屏（t86）实现与验证报告

日期：2026-11-26
任务：t86（B3 图鉴屏 + 花园屏，队长追加约束版：不改 `main.cpp` / `menu_view.cpp`）
数据源：`native/generated/metagame.json`（t73 产物）+ 只读 `content/**`

## 一、方法与边界

* 两屏都是**纯函数入口**，不经过 `main.cpp`：
  * `pvz::renderAlmanacHeadless(contentRoot, kind, index, frames, snapshot, progressFile, assetRoot) -> Json`
  * `pvz::renderGardenHeadless(contentRoot, frames, snapshot, assetRoot) -> Json`
  队长只需在 `main.cpp` 里各加一行即可接线；测试也是直接调这两个入口，所以「无头 JSON」与「CLI JSON」是同一份代码路径。
* 未修改 `native/src/main.cpp`、`native/src/menu_view.cpp`（菜单项与 `--almanac`/`--garden` 分发由队长统一接线）。
* 未修改 `content/**`、`native/generated/**`、`tools/**`；未 commit。
* 渲染沿用既有桌面屏骨架（`sdl_support.hpp` 的 `sdl::Display`、`text.hpp` 的 `TextRenderer`、`saveScreenSnapshot`）：headless 走 `SDL_CreateSurface(1280,720)` + 软件渲染器，与 `menu`/`level_select`/`worldmap` 完全同构，所以 `--frames N` 的语义、截图格式、ink 判据一致。
* 两屏各读一次 `metagame.json` 与 `content/*.json`，无网络、无动态执行被测内容。

### 构建环境（踩坑记录）

* `cmake` 不在 PATH，实际位置：`C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe`（由 `tools/build_native.ps1` 里 `vswhere` 解析得到）。
* 本机环境存在**大小写重复的代理变量**（`HTTP_PROXY/http_proxy`、`NO_PROXY/no_proxy`、`HTTPS_PROXY/https_proxy`）。直接调 `cmake`/`MSBuild` 时 CL.exe 启动会在 `System.Diagnostics.ProcessStartInfo.get_EnvironmentVariables()` 抛
  `error MSB6001: Invalid command line switch for "CL.exe". System.ArgumentException: Item has already been added. Key in dictionary: 'NO_PROXY' Key being added: 'no_proxy'`。
  规避：调用前对每一组大小写重复变量全部 `set "NAME="` 清空（或直接走 `tools/build_native.ps1`，它在自己进程里先清再调）。

## 二、交付文件

| 文件 | 行数 | 字节 | 说明 |
| --- | --- | --- | --- |
| `native/src/almanac_view.hpp` | 168 | 7,795 | 图鉴屏数据类型 + 纯函数入口 |
| `native/src/almanac_view.cpp` | 674 | 30,778 | 载入/置灰/分页/渲染/JSON |
| `native/src/garden_view.hpp` | 148 | 5,654 | 花园屏数据类型 + 纯函数入口 |
| `native/src/garden_view.cpp` | 515 | 23,888 | Zen 表/掉落物/定价/渲染/JSON |
| `native/tests/almanac_test.cpp` | 299 | 15,784 | 8 节断言 |
| `native/tests/garden_test.cpp` | 262 | 13,831 | 8 节断言 |
| `docs/media/s6-almanac-screen.png` | — | 91,873 | 1280×720 图鉴屏截图 |
| `docs/media/s6-garden-screen.png` | — | 114,496 | 1280×720 花园屏截图 |
| `native/CMakeLists.txt` | — | — | 三处编辑：`pvz_launcher` 加两个 `.cpp`；`pvz_launcher` PUBLIC 加 `pvz_progress`；注册 `almanac_render_test` / `garden_render_test`（TIMEOUT 120） |

## 三、图鉴屏（almanac）

### 数据来源与字段

`metagame.json` 的 `almanac` 块**只给本地化键，没有任何文案**：

* `almanac.plants` 167 条，键为 `id / nameKey / descKey / tooltipKey / world / worldSource / almanacBackdrop / inPlantTypes / levels / stats / resolved`；`resolved` 是布尔字典（`name/desc/tooltip/nameZh/descZh`），不是文案。
* `almanac.zombies` 428 条，键为 `id / nameKey / descKey / descHeaderKey / world / worldSource / zombieClass / levels / rosterSource / resolved`。
* `stats[]` 元素：`statType / statName / statNameAlias / typeKey / valueKey / levelToUnlock / numberFormat`。`valueKey` 也是键（例如 `STAT_TOUGHNESS_ARMOR0`、`STAT_DAMAGE_DAMAGE2`），**不是数值**。

因此屏上的可读文案全部从只读 content 侧补齐：

| 显示项 | 来源 | 覆盖率 |
| --- | --- | --- |
| 名称 | `content/plants.json[].name_zh`（回退 `name_en`）→ `content/zombies.json` → 再回退 id | 植物 166/167 有 `nameKey`，content 覆盖 140 株；缺 `minishroom` |
| 描述 | `content/almanac.json.plants[id].desc`（回退 `content/plants.json[].desc_zh`） | 140 株 |
| 族 | `stats[]` 里 `statType=="family"` 的 `valueKey`，去掉 `STAT_FAMILY_` 前缀并小写 | 63 条有 family |
| 类型（僵尸） | `zombieClass` | 428/428 |
| cost / hp | `content/plants.json[].cost` / `.hp` | 140 株；其余显示分级键 |
| 出场关卡 | `levels`（**关卡包引用计数**，不是「首次出场关卡」） | 植物 149/167、僵尸 383/428 |
| 所属世界 | `world`（内部 token，如 `beach`/`skycity`） | 植物 116/167，僵尸 428/428 |

### 置灰规则（按 `--progress`）

* 无 progress 或 `progress->clearedLevels()==0` → **全部可见**（首次进入不会是一片灰）。
* 否则取已通关关卡 id 的**世界前缀**（`beach_1` → `beach`，截到首个数字/`_`/`/` 之前并小写），得到「已解锁世界集合」；条目的 `world` 属于该集合、或 `world` 为空 → 可见，否则置灰。
* 两个别名：`tutorial → frontyard`、`skycity → sky`（metagame 用内部 token，`content/levels` 用 `frontyard_*`/`sky_*`）。
* 未识别的 token **保持可见**：宁可误显，也不会把没通的关卡区误灰。

### 版式与交互

* 画布 1280×720；左列分类（植物 / 僵尸）x=32 w=200，行高 34；中列列表 x=248 w=520，行高 28、步距 30、起点 y=96，**每页 12 行**；右详情 x=792 w=456 y=88 h=560；页脚 y=664 提示、y=690 数据路径、y=706 备注。
* 按键：`Esc` 退出、`↑/↓` 单步、`PgUp/PgDn` 整页、`←/→/Tab` 切分类（切后 `index=0`）、`Enter` 选定；鼠标可点分类行与列表行。
* 分页：`almanacPage(entries, index, 12)` → 167 条植物 = 14 页（末页 `first=156 last=167 visible=11`），`index` 越界被 clamp 到 `total-1`。

### 无头 JSON 契约

```json
{"kind":"plant","index":0,"page":0,"pages":14,"screen":"almanac","total":167}
```

`kind` 归一：`zombie`/`zombies` → 僵尸，其余 → 植物；`index=99999` 时输出 `index=166`（clamp 后取值，与画面一致）。

## 四、花园屏（garden）

### 数据来源

* `garden.collectables` 65 条：`typeName / collectableClass / image / popAnim / rewardDialogTitleKey / rewardDialogTitleResolved / soldAs / storeCategory / dropSources`。
* `garden.zenGarden`：`props / slotProps / bee / floatingText`（**四张表齐 = 4/4**）+ `pots`（**12 盆**）+ `plantRewards`（3 张植物奖励表）。
  Zen 参数实测：`PlantGrowDurationInSeconds=18000`、`NormalPlantCoinRewardAmount=50`、`TreasurePlantSpawnRate=3`、`GrowingSpeedupCalcMultiplyFactor=2`、`GrowingSpeedupCalcAddFactor=1.7413`、`GrowingSpeedupCalcMaxTimeSeconds=28800`、`PotCosts` 各 20 宝石、`BackgroundImageID=IMAGE_BACKGROUNDS_ZEN_GARDEN`。
* 定价口径（严格匹配，不猜）：只有能对上 `StoreProductProps` 才给价 ——
  * `pinata_egypt`：按 sku 记号匹配到 `com.popcap.pvz2.pinata.egypt.consume.tutorial`，但价格字段全空 → 记为匹配但**未标价**；
  * `sprout`：按 `ObjectItem` 匹配到 `com.popcap.pvz2.sprout.5.consume`，`priceGems="30"` → **已标价**；
  * 裸 `pinata` 只记 `storeCategory="pinata"`，不给价。
  合计：**65 条里 2 条有商品匹配、1 条真正带价** —— 覆盖率低是原版数据的事实（`StoreProductProps` 565 条的品类是 costume 447/plant 61/pinata 23/…，掉落物与商品本就不同构）。
* 掉落来源：`dropSources` 与任务表/商店表反查，65 条里 **6 条有来源**（例：`pinata_beach` ← `QuestRewardTablesProps`，`difficulty=5`）。

### 版式与交互

* 左 Zen 面板 x=32 w=360 y=88 h=560：四表 ✓/✗、9 条关键数值、12 盆 3 列格子、植物奖励表数。
* 中列表 x=412 w=480 y=88 h=560：每页 12 行（行高 28/步距 30/起点 y=104），显示 `typeName`、`来源 N 条`、价格或「未标价」；右详情 x=912 w=336。
* 键鼠与分页同图鉴屏（`Esc`/`↑↓`/`PgUp/PgDn`）。

### 无头 JSON 契约

```json
{"drops":65,"pots":12,"screen":"garden","zen":4}
```

## 五、验证结果

### 1. 两个测试目标（ctest）

```
1/2 Test #43: almanac_render ...................   Passed    4.45 sec
2/2 Test #44: garden_render ....................   Passed    3.09 sec
100% tests passed, 0 tests failed out of 2
```

两测试各 8 节，均**不经 main**：

* `almanac_test`：① 表规模（167/428、每行有 `nameKey`、按 id 有序）② 分页（14 页、末页 156–167、clamp）③ 文案（`nameFromContent` 计数、`name != nameKey`、`minishroom` 缺键不打印）④ 置灰（无存档全可见；只通关 `beach_1` 时 beach 可见、skycity 灰、空 world 可见）⑤ JSON 键集与 clamp ⑥ 帧 1280×720 + ink≥120 + 两跑字节相同 ⑦ 缺字体抛错含 `font_zh.ttc` ⑧ 缺表抛错含 `metagame.json`。
* `garden_test`：① drops 65 / tables 4 / pots 12 / plantRewards 3 / 按 typeName 有序 ② Zen 数值（18000 / 50 / 3 / 20）③ 价格（匹配 2、带价 1、`sprout` gems、`pinata_egypt` 未标价、裸 `pinata` 不给价但有品类）④ 来源（6 条、`pinata_beach` 的 table 与 `difficulty=` 前缀）⑤ JSON 键集 ⑥ 分页（65 条 6 页、末页 60–65）+ 帧 ⑦ 缺字体 ⑧ 缺表。

### 2. 截图

| 文件 | 尺寸 | 字节 | sha256 |
| --- | --- | --- | --- |
| `docs/media/s6-almanac-screen.png` | 1280×720 | 91,873 | `496677D157BF9F6629A4D05E76E3ED732D68A5AADE18056DFC0B0F993E4B7C10` |
| `docs/media/s6-garden-screen.png` | 1280×720 | 114,496 | `0B087EC045E0778D988C1A278BF320DF9DD549464CE66FC80588C26F35406A3A` |

同一入口连跑两次字节完全相同（测试第 ⑥ 节断言），截图不是「抽一次运气」。

### 3. 既有屏回归对照

| 对照项 | 基线 | 本次（alm3 全新构建） | 结论 |
| --- | --- | --- | --- |
| `--menu` 截图 | `37F75744…AB7B1`（31,949 B） | `37F75744CC8472660B34998718F4339BEA9D38F7FDB39870635B13E3087AB7B1`（31,949 B） | **一致** |
| `--battle-snapshot` | `D56A3D6A…79A90` | `A75979B5EE37E1289E02C046C3F709E65E3FE598ED646E0EED9AAD5225D0CF5E`（1,584,774 B） | **不一致，但非本任务造成**（见下） |
| `tools/engine_smoke.py` | `9E9D9237…E2AC0C`（10,911 B） | `C346C8FD…88F278`（10,911 B） | **1 例有差异，非本任务造成**（见下） |

`--battle-snapshot` 与 smoke 差异的归因（可复核）：

* 我的改动只新增两个 `.cpp` 到 `pvz_launcher`，**没有触碰** `src/engine/**`、`battle_view.cpp`、`main.cpp`。
* 同期其他任务的编辑时间戳：`src/engine/vase.cpp` 18:03、`src/engine/rail.cpp` 18:04、`src/battle_view.cpp` 18:12、`src/engine/world.cpp` 18:38（今日），都在本轮并行任务窗口内。
* 作为交叉验证，用**仓库里已有的 11-25 构建**（`build/package` 与 `build/desktop-gate`）跑同一命令，得到 `3FBF8848…D4EC`（1,585,046 B），与任务书基线 `D56A3D6A…` 也不同 —— 说明战斗截图的基线早于这两个构建，本次差异不是我这个分支引入的。
* smoke 的唯一差异例是 `cowboy_1`：`killed 0 → 2`、`hash 0xeb036737659cbc46 → 0xcb83dd8dcba537f5`（`status`、`tick`、`spawned` 等其余字段不变），属模拟层（`world.cpp`）改动，与我这两屏无关。

### 4. 全量构建状态

`tools/build_native.ps1 -BuildDir C:\pvzbuild\alm3` 的**桌面全量**当前在他人文件处编译失败：

```
native/src/daily_view.cpp(202,18): error C3861: 'SDL_RenderDrawRect_renamed_SDL_RenderRect': identifier not found
native/src/achievements_view.cpp(233,18): error C3861: 'SDL_RenderDrawRect_renamed_SDL_RenderRect': identifier not found
native/tests/achievements_test.cpp(227,25): error C2065: 'SDL_Surface': undeclared identifier  （连锁 20+ 条）
```

这是 t87（成就/每日）正在写的文件；与本次交付无关。用 `--target almanac_render_test garden_render_test` 单独构建**成功**，两个测试通过（见第五节 1）；`PvZ2SHUTTLE` 目标也单独构建成功（用于跑上面两项回归对照）。

## 六、原版没有 / 数据缺口（明确写出）

* **图鉴文案不在 metagame 表里**：表只有键。屏上的名字/描述全部来自 `content/**`，因此 content 没覆盖的 27 株植物只有 id 与分级键（`STAT_TOUGHNESS_ARMOR0` 之类），没有可读描述。
* **没有「首次出场关卡」字段**：只有 `levels` 计数（关卡包引用数），所以详情面板写的是「出场关卡 N」而不是具体关卡名。
* **成就奖励 serverOnly**：`achievements` 53 条全 `rewards=null` + `serverOnly=true`（奖励只在服务器侧）。
* **掉落物定价基本不存在**：65 条里 1 条可定价、6 条有掉落来源；其余是原版就没有对应商品/掉落行。
* **Zen Garden 没有售价表**：只有 `PotCosts`（20 宝石/盆）与植物奖励（50 金币/次），没有「花园物件售价」这一概念。

## 七、未知项与限制

1. `world` 是内部 token，未与 `content/worlds.json` 的 26 个世界 id 全量对齐；已知别名 `tutorial→frontyard`、`skycity→sky`，其余未识别的 token 一律按「可见」处理（只可能误显，不会误灰）。
2. `levels` 口径是「引用该 id 的关卡包文件数」，`PlantExcludeList` 不计入；与「关卡内出现次数」不是同一件事。
3. Zen「4/4」按 `props/slotProps/bee/floatingText` 四张表判定；`pots`(12) 与 `plantRewards`(3) 另计。
4. 图鉴僵尸侧以「有 `ZombieType` 定义」为准（428），纯 spawn-only 的 120 个不进图鉴（见 metagame `unknowns` U1/U9）。
5. `--battle-snapshot` 与 smoke 的差异需由对应任务的负责人确认（本轮并行改动所致），本报告只做归因，不做修复。

## 八、复现命令

```powershell
# 0) 清掉大小写重复的代理变量（否则 CL.exe 启动报 MSB6001）
$g=@{}; foreach($k in [System.Environment]::GetEnvironmentVariables().Keys){ $u=$k.ToUpperInvariant(); if(-not $g.ContainsKey($u)){$g[$u]=@()}; $g[$u]+=$k }
$unset = (($g.Keys | Where-Object { $g[$_].Count -gt 1 } | ForEach-Object { $g[$_] }) | ForEach-Object { 'set "' + $_ + '="' }) -join ' & '
$cmake = 'C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe'

# 1) 单独构建我的两个测试（全量构建会被 t87 的半成品挡住）
cmd /c ($unset + ' & "' + $cmake + '" --build "C:\pvzbuild\alm3" --config Release --target almanac_render_test garden_render_test')

# 2) 跑测试
& 'C:\...\ctest.exe' --test-dir 'C:\pvzbuild\alm3' -C Release -R 'almanac_render|garden_render' --output-on-failure

# 3) 既有屏回归对照
cmd /c ($unset + ' & "' + $cmake + '" --build "C:\pvzbuild\alm3" --config Release --target PvZ2SHUTTLE')
& 'C:\pvzbuild\alm3\Release\PvZ2SHUTTLE.exe' --menu content --assets ..\..\PvZ2SHUTTLE\assets --snapshot menu.png --frames 2
& 'C:\pvzbuild\alm3\Release\PvZ2SHUTTLE.exe' --battle-snapshot content ..\..\PvZ2SHUTTLE\assets battle.png
python tools/engine_smoke.py --exe 'C:\pvzbuild\alm3\Release\PvZ2SHUTTLE.exe' --out smoke.json
```

截图产物（两张 1280×720）在 `docs/media/s6-almanac-screen.png` 与 `docs/media/s6-garden-screen.png`。
