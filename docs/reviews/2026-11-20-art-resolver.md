# S4.4 资源解析层：SHUTTLE PopAnim 索引 + `--art-audit` 覆盖报告

日期：2026-11-20 · 执行：wirer（attempt c752cafc）· 仓库：`repo/pvz2-shuttle-pc`

## 1. 范围

| 文件 | 变更 |
| --- | --- |
| `native/src/art_index.hpp` / `native/src/art_index.cpp` | **新增**：`ShuttleArtIndex`（索引模型 + 候选列表）、`resolveArt`、`locateAssetRoot`、`auditArt`。不依赖 SDL，挂进 `pvz_catalog` |
| `native/src/assets.hpp` / `assets.cpp` | `AssetCache::art(art, popAnim)`、`shuttleIndex()`、`missingArt()`：带缓存与 miss 计数的解析入口 |
| `native/src/battle_view.cpp` | 模型查找从写死的 `"db/" + art` 改为 `modelOf()` → 解析层；底部状态栏显示「缺美术 N」；`locateAssets` 与新增的 `locateAssetRoot` 合并为一份探测 |
| `native/src/main.cpp` | 新增 `--art-audit <content> [--pack] [--assets]`，退出码 0/1/2 |
| `native/tests/art_audit_test.cpp` | **新增**：四段断言 + 夹具 |
| `native/CMakeLists.txt` | `art_index.cpp` 进 `pvz_catalog`；`art_audit` 测试（`PVZ_TEST_CONTENT` / `PVZ_CONTENT_PACK` / `PVZ_TEST_TEMP`） |

### 契约偏差（两处，均为必要）

1. **新增 `art_index.*` 而非只改 `assets.*`**：`--art-audit` 必须能在 `-DPVZ_ENABLE_DESKTOP=OFF` 的 AuditOnly 构建里跑，而 `assets.*` 依赖 SDL。于是把「索引 + 解析 + 审计」放在无 SDL 的 `art_index.*`（链进 `pvz_catalog`），`AssetCache` 只是加一层带缓存的包装。
2. **`--art-audit` 的输出键比契约多**：除要求的 `contentPlants/contentZombies/packPlants/packZombies/shuttleIndex/shuttleFailures` 外，追加 `shuttleIndexLoaded`、`shuttleIndexCounts`、`shuttleIndexProgress`、`assetRoot`，`indexError` 仅在有错时出现。理由：`missing` 大是预期（见 §3），不给 `counts/pending` 就无法判断「没抽完」还是「解析坏了」。

## 2. 索引真实结构（实测）

`PvZ2SHUTTLE/assets/db/shuttle/index.json`（artifex 仍在后台写）：

- `items[]`：`{base, popAnim, dir, images, animations, rects, page, bytes, seconds, sha256:{...}}` —— 键名是 `items`；`entries` 作为旧草稿键仍兼容读取。
- `counts`：`{bases_total, ok, failed, pending, popanim_matched, popanim_null}`
- `failures[]`：`{base, reason}`
- `progress`：`{done, total, aborted_at, rank, last_base}`

**`dir` 的相对基准**：本次实测的全部 148 条 `dir` 都写成 **相对 `assets/`** 的路径（例如 `db/shuttle/shuttle_PLANTSUNFLOWER`）。解析层仍然同时接受相对 `db/shuttle/` 的写法（`shuttle_FAKEBASE`）与裸 base 名，因为 artifex 的表还在长，基准不该成为硬约束；`normaliseDir()` 依次试 `dir`、`db/<dir>`、`db/shuttle/<dir>`、`db/shuttle/shuttle_<base>`，取第一个真的带 `skeleton.json` 的目录。

**判定「可用」的准则**：目录存在 **且** `skeleton.json` 是普通文件。空目录（提取失败）不算命中——测试夹具里的 `GHOST` 就是这个形态。

**`pending > 0` 不算失败**：索引存在但 `items` 为空（提取还没产出第一个 base）判为 `loaded=false`、退出码 2；只要 `items` 非空即 `loaded=true`，`pending` 原样抄进 `shuttleIndexCounts`。当前实测：`basesTotal 1087, ok 148, failed 1, pending 938`。

**一个 `popAnim` 对应多个 base**：`ShuttleArtIndex::candidates(popAnim)` 返回全部候选（文件顺序），`byPopAnim()` 返回其中第一个「目录可用」的。夹具用两个 item 指向同一 `POPANIM_PLANT_SUNFLOWER`（第一个目录无 skeleton）验证了这条规则。

## 3. 解析顺序

1. `db/<art>`（旧 Web 导出的目录，content 侧的 `art` 键，例如 `plants/SunflowerPLANT`）——**优先**，因此装上 SHUTTLE 提取物不会改变已经能画的 actor。
2. SHUTTLE 索引：`popAnim` → `db/shuttle/shuttle_<BASE>`。

都没有 → `ArtResolution{source=none, dir=""}`，`AssetCache` 记一次 miss（`missingArt_`，同一 key 不重复探测），视图仍画原来的占位形状（植物绿圆、僵尸灰方块），并汇报一次，不静默。

`missing` 是**预期存在**的：pack 里 tile / mower / effect 类条目 `popAnim: null`，且提取尚未跑完（覆盖目标是 568/1087 ≈52%）。退出码语义因此保持 0/1/2，不把 missing 当故障。

## 4. 视图改造

- `battle_view.cpp` 的 6 处 `plantModel/zombieModel` 全部改为 `BattleScene::modelOf()`：content id → `art`（content 定义）+ `popAnim`（pack 定义）→ `assets_.art(...)`。
- 解析失败：`reportOnce` 汇报一次（`plant <id>: no artwork for <art> / <popAnim>`），模型串留空 → `firstAnimation`/`drawActor` 走既有占位分支。
- 底部状态栏 `原生战斗内核 · 不写入存档` 在有 miss 时追加 ` · 缺美术 N`，把「资产树没抽完」变成可见状态。

## 5. `--art-audit` 输出（三组实测）

**A. content + pack，默认 asset root**（索引已在，提取进行中）：

```
{"assetRoot":"D:\\OneDrive\\文档\\pvz_shuttle\\PvZ2SHUTTLE\\assets",
 "contentPlants":{"missing":29,"shuttleHit":7,"total":147,"webHit":111},
 "contentZombies":{"missing":33,"shuttleHit":0,"total":55,"webHit":22},
 "packPlants":{"missing":233,"shuttleHit":106,"total":339,"webHit":0},
 "packZombies":{"missing":1127,"shuttleHit":0,"total":1127,"webHit":0},
 "shuttleFailures":1,"shuttleIndex":148,
 "shuttleIndexCounts":{"basesTotal":1087,"failed":1,"ok":148,"pending":938,
                        "popAnimMatched":102,"popAnimNull":46,"usable":148},
 "shuttleIndexLoaded":true,
 "shuttleIndexProgress":{"done":149,"total":1087}}
exit=1
```

**B. 只给 content（不带 pack）**：`packPlants/packZombies` 的 `total` 为 0（没有 pack 就没有 popAnim 通道），其余同 A，`exit=1`。

**C. 资产根里没有 `db/shuttle/index.json`**：

```
warning: D:\Temp\User\art_audit_probe\bare\db/shuttle/index.json: not found (no SHUTTLE artwork is installed)
{"assetRoot":"...bare", "contentPlants":{"missing":139,"shuttleHit":0,"total":147,"webHit":8},
 "contentZombies":{"missing":55,...,"webHit":0}, "packPlants":{"missing":339,...},
 "packZombies":{"missing":1127,...}, "shuttleFailures":0,"shuttleIndex":0,
 "shuttleIndexLoaded":false, "shuttleIndexError":"...index.json: not found ..."}
exit=2
```

退出码：0=全命中、1=有 missing、2=索引缺失/不可用。索引问题同时打到 stderr（`warning:`），JSON 仍是单行标准输出，便于管道消费。

## 6. 测试断言（`native/tests/art_audit_test.cpp`）

夹具全部落在 `PVZ_TEST_TEMP/art_resolver*`，**不读真实 `assets/db/shuttle/`**（那里正在被提取器持续写入，读它会让测试随进度忽红忽绿）。

1. **缺索引** → `present=false`、`loaded=false`、`error` 含 `index.json`、审计 `exitCode()==2`，同时旧 Web 目录仍有命中（`webHit >= 1`）。
2. **索引可用** → `items.size()==4`、`usable()==3`、`failures==1`、`counts` 五个计数器逐项相等、`progress.done/total` 相等；`candidates("POPANIM_PLANT_SUNFLOWER").size()==2` 且第一个候选不可用、`byPopAnim()` 选中 `FAKEBASE`；`dir` 写成 `db/shuttle/...` 与 `shuttle_...` 两种基准都能解析；`popAnim` 为空串时不解析。
3. **旧路径优先** → 同一个 actor 两边都有时 `source==web`、`dir=="db/plants/SunflowerPLANT"`。
4. **审计计数** → `contentPlants` 覆盖 147（`webHit 8 + shuttleHit 1 + missing 138`，因为 content 里 8 个植物共用 `plants/SunflowerPLANT` 的 art 键）、`contentZombies` 55 全 missing、`packPlants` 339（两条夹具 popAnim 命中 2）、`packZombies` 1127；JSON 键与 `counts/progress` 齐备。

额外一条「索引存在但 `items` 为空」的用例：`loaded=false`、`error` 含 `items`、退出码 2——这是提取器刚启动时的真实形态。

## 7. 验证记录

| 命令 | 结果 |
| --- | --- |
| `pwsh -File tools/build_native.ps1 -AuditOnly -BuildDir 'C:\pvzbuild\art1'` | `100% tests passed, 0 tests failed out of 12`（catalog/content/cli_audit/cli_missing_content/cli_unknown_command/simulation/save_import/engine/world_outcome/zombie_family/**art_audit**/cli_desktop_disabled），exit 0，`Built and tested: C:\pvzbuild\art1\Release\PvZ2SHUTTLE.exe` |
| `C:\pvzbuild\art1\Release\art_audit_test.exe content native\generated\content.pack %TEMP%\pvzengine` | `art audit tests passed`，exit 0 |
| `pwsh -File tools/build_native.ps1 -BuildDir 'C:\pvzbuild\art-desktop'` | `100% tests passed, 0 tests failed out of 17`（含 launcher / cli_missing_artwork / dragonbones / assets / text_render / **battle_render**），exit 0 |
| `--art-audit content --pack native\generated\content.pack` | §5 A 行，exit 1 |
| `--art-audit content`（无 pack） | §5 B 行，exit 1 |
| `--art-audit content --pack … --assets <无 index 的资产根>` | §5 C 行 + stderr `warning: …index.json: not found`，exit 2 |

### 反向探针（每条都改坏一处，确认对应断言真的会红，然后还原）

| 探针 | 改动 | 得到的 FAIL |
| --- | --- | --- |
| A | `resolveArt` 先查 SHUTTLE 再查 `db/<art>` | `art audit test failed: the legacy db/<art> folder must win over the SHUTTLE entry, got shuttle:db/shuttle/shuttle_FAKEBASE` |
| B | 索引文件缺失时也置 `loaded = true` | `art audit test failed: an absent index cannot report loaded` |
| C | `looksLikeArtwork()` 只看目录存在、不要求 `skeleton.json` | `art audit test failed: only bases whose folder exists are usable, got 4` |

还原后 `native/src/art_index.cpp` sha256 = `1778D3C4C4B879E49004BA3F607F39217E029ECF3EA7957B58FEAFD7DF3AE6AD`，源码内无 `PROBE_` / `fprintf` 残留，两个构建门重新全绿。

## 8. 已知差距

- `packZombies` 目前 0 命中：僵尸的 base 绝大多数还在 `pending`，`popAnimMatched` 也主要来自植物。等提取跑完（目标 568/1087）再复核一次即可，不需要改代码。
- content 侧 29 个植物、33 个僵尸仍缺美术：多为 SHUTTLE 提取尚未覆盖的变体，属于提取进度问题，不是解析层问题。
- `dir` 基准目前实测为「相对 `assets/`」，但解析层同时接受「相对 `db/shuttle/`」，等 artifex 定稿后可以把某一种写法删掉以收紧契约。
- 审计不做架构/尺寸校验（`images/animations/rects` 只抄数字），`skeleton.json` 存在即视为可用；若要防「半截目录」，需要额外读 meta 里的 `atlas_rects.matched == total`。
