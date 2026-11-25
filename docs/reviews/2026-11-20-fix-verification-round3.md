# Round-3 复审：五条「必须先修」的关闭情况（t20 / reviewed: t19）

- 复审人：auditor（只读）
- 时间：2026-11-21 10:10–10:35（北京时间）
- 复审对象：`docs/reviews/2026-11-20-audit-fixes.md`（t19 交付，sha `67974DCCC7E0`，mtime 11-20 23:00:14，自那以后未再改动）与 t19 的验收声明
- 只读承诺：除本文件外未写真仓任何文件。所有反向探针/篡改都在**副本仓库**（`C:\pvzbuild\aud5repo`、`C:\pvzbuild\aud6repo`）里做；真仓 `native/src/engine/world.cpp`、`native/generated/engine_smoke.json` 的 sha 与复审开始时一致（后者 `95B0156A1850` 未变）。真仓在这 25 分钟里被其他成员改动过（S5.8 boss 落地，见 §1.2），那是他们的写作用域，非我改动。

## 0. 结论摘要

| # | 条目 | 判定 | 一句话依据 |
| --- | --- | --- | --- |
| 1 | B1 跳跃（`World::tryVault`） | **真关** | 落点 `centre-0.55` 在触发窗口外且不啃被跳过的株；反向探针（落点改回 `centre+1.05`）令 `engine` 用例红：`the vaulted plant must survive`，另 13 例全绿 |
| 2 | H4 门禁自愈（`Sync-Baseline`） | **真关** | 篡改基线 → `[keep] … left untouched` + `[fail] … changed` + exit 1，基线 sha 保持篡改值（687B3E0A…）不变 |
| 3 | 双静默降级（`--pack` / `--boards`） | **真关** | 两条 CLI 均 exit 1 且错误文本点名阶段；`catalog_test` 旧 fallback 断言已换成抛错断言 |
| 4 | L2 击杀计数（`countsAsKill` + 账目守恒） | **真关** | 推车传 `false`；26 个无防守世界 `killed == mowerKills` 的行数 26 → **0**；脚本局 killed 30 → **15**；`won` 局 `killed+mowerKills+leaked == spawned` 严格成立 |
| 5 | 台账数字与现树一致 | **未关** | 台账写 audit 13 / desktop 18 / python 259；现树 **15 / 20 / 263**，`check_all` 的 `== test ledger ==` 因此报 `[fail]` 并 exit 1；`PARITY_BASELINE.md:161` 仍写「退出码 **0**」 |

**verdict：needs_revision。** 5 条里 4 条真关（含 acceptance 要求的反向探针与 H4 实证），第 5 条未关，而且**在复审期间越差越远**：台账停在 13/18，S5 期间新加的 `s5_runtime`、`replay_s5` 把 audit 推到 15、desktop 推到 20。

## 1. 快照

### 1.1 复审基准（10:10，`git HEAD 24a2493`，工作区 22 行未跟踪）

| 文件 | sha256(12) | mtime | 字节 |
| --- | --- | --- | ---: |
| `native/src/engine/world.cpp` | `88DA04278C9E` | 11-20 23:26:28 | 36213 |
| `native/src/catalog.cpp` | `D9B47351BF42` | 11-20 21:47:31 | 17686 |
| `native/src/catalog.hpp` | `3AC1CA00610A` | 11-20 22:38:57 | 4030 |
| `native/tests/engine_test.cpp` | `CD3390325A2D` | 11-20 22:24:47 | 32864 |
| `native/tests/s5_runtime_test.cpp` | `DA95BF2F2AF1` | 11-20 23:14:15 | 16838 |
| `native/CMakeLists.txt` | `F135895D1DEB` | 11-20 23:21:50 | 12081 |
| `tools/check_all.ps1` | `8158197608F4` | 11-20 22:57:45 | 12916 |
| `tools/engine_smoke.py` | `5E95AAADAC58` | 11-20 21:54:42 | 9091 |
| `docs/PARITY_BASELINE.md` | `68DF98C286CE` | 11-20 22:57:07 | 18266 |
| `docs/reviews/2026-11-20-audit-fixes.md` | `67974DCCC7E0` | 11-20 23:00:14 | 20949 |
| `native/generated/engine_smoke.json` | `95B0156A1850` | 11-20 21:57:08 | 11496 |

环境：Windows + VS2022 BuildTools（`ctest` 不在 PATH，需 `...\BuildTools\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\ctest.exe`）；仓库路径含非 ASCII 字符，构建必须落到 ASCII 目录（`-BuildDir C:\pvzbuild\...`），否则 `json-src` 的 `CONFIGURE_FILE` 直接失败——t19 记录过，本轮复核仍成立。

### 1.2 复审期间树在动（影响取证方式，不是被审对象的缺陷）

10:19–10:26 有成员在同一工作区落地 S5.8 boss：`native/src/engine/{boss.cpp,boss.hpp,entity.hpp,tuning.hpp,replay.cpp,world.hpp,world.cpp}` 逐个改写，`world.hpp` 10:23:42 / `world.cpp` 10:23:49 / 10:25:26，并新增 `native/tests/replay_s5_test.cpp`、`s5_boss_test.cpp`。

后果（附录 A 有原文）：同一次门禁运行里 `== audit build ==` 是 14/14 绿（10:12），10 分钟后的 `== desktop build ==` 却红在 `world.hpp(107,49): error C2065: 'bossDefinition_': undeclared identifier`——因为访问器先落、成员变量（`:269-273`）后落。第二次运行（10:24）连 audit build 都红：`LNK2019 unresolved external symbol BossStage::fireActions / BossTable::shared / selectBoss`。

**这直接决定了取证纪律**：任何门禁结论都必须用「运行前后的源码 sha」夹住；本轮我保留了两端的 sha，凡树在中间移动的运行只用于「现状说明」，不用于判定被审对象。§2–§5 的判定基于 1.1 的稳定快照。

## 2. 第 1 条：B1 跳跃 —— 真关

### 2.1 代码（1.1 快照；行号为 S5.8 落地后，括号内为探针时的旧行号）

- 调用点在啃食扫描**之前**：`world.cpp:182`（旧 157）`if (zombie.family == "jump") tryVault(zombie);`，啃食扫描从 `:185`（旧 160）`if (zombie.family != "fly") {` 开始；注释明说「只有 fly 忽略植物，jump 跳过后正常吃」。
- `World::tryVault` 全文 `world.cpp:243-262`（旧 218-240）：
  - `:244` 冷却门 `if (static_cast<double>(tick_) < zombie.nextSpecialTick) return false;`
  - `:248` `spike` 地面植物不阻挡
  - 触发窗口 `if (ahead < -0.05 || ahead > tuning::kEatRangeCols + 0.05) continue;`
  - **`:256`（旧 231）`const double landing = centre - 0.55;`** → 写回 `zombie.x`，复位 `walking`/`target=0`，`:260` 冷却 `tick_ + ticksOf(2.0)`，`:261` 发 `zombie_hop`
- `native/src/engine/registry.cpp` 的 `zombieJump` 是空实现，只留指向 `World::tryVault` 的注释。

### 2.2 语义核对

- **(a) 不会对同一株二次触发**：落点后 `ahead = x - centre = -0.55`，窗口下界 `-0.05`，`-0.55 < -0.05` ⇒ `continue`；僵尸继续向左走，`ahead` 只会更负。
- **(b) 不啃被跳过的株**：落点后啃食上界 `centre <= x + kEatStartCols` 变成 `centre <= centre - 0.20` ⇒ 假；上下界是 `&&`，故不锁定该株（`world.cpp:190`，旧 165）。

### 2.3 反向探针（acceptance 要求项）

在副本 `C:\pvzbuild\aud6repo`（robocopy 真仓，排除 `build/.git/work/node_modules/.agent-teams`）上做，真仓未触碰：

```
copy world.cpp orig sha=88DA04278C9EAB81C2095FAF34F3C4A0B931CC718979618450AA4944F9E0E00A
landing pattern hits=1
patched line 231: const double landing = centre + 1.05;          # 回退成旧落点
== build (patched) ==  pwsh -File tools/build_native.ps1 -AuditOnly -BuildDir C:\pvzbuild\aud6build
 8/14 Test  #8: engine ...........................***Failed    1.16 sec
engine test failed: the vaulted plant must survive: a vaulter must not eat it
93% tests passed, 1 tests failed out of 14
The following tests FAILED:  8 - engine (Failed)
== restore ==
restored sha=88DA04278C9EAB81... identical=True
```

机制：落点 `centre+1.05` 时，啃食上界 `centre <= x+0.35`（= `centre+1.40`）与下界 `centre >= x-1.15`（= `centre-0.10`）同时成立 ⇒ 跳完立刻啃同一株，`engine_test.cpp:283` 的 `check(!world.plants().empty(), "the vaulted plant must survive: a vaulter must not eat it")` 失败。

信号是**定向**的：只有 `engine` 一例红，其余 13 例（含 `s5_runtime`、`art_audit`、`progress`）全绿。**第 1 条真关。**

### 2.4 残留（不否决本条，登记为 N2）

- 窗口上界 `kEatRangeCols + 0.05 = 1.20` 列，而接触点在 `kEatStartCols = 0.35`：僵尸离植物中心还有 1.2 列时就跳，一 tick 位移 1.2+0.55 ≈ **1.75 列**（`pole_vaulter` 速度 0.3 列/秒，正常要走 ~5.8 秒）。
- 冷却 2 秒 + 株距 1.0 列 + 速度 0.3 列/秒 ⇒ 密集防线可以被**连跳多株**；真机撑杆僵尸只跳一次。
- 用例只断言单株 `hops == 1`（`engine_test.cpp:285`），没有任何用例钉住「一排多株只跳一株」「跳跃距离」「跳跃时机」。

## 3. 第 2 条：H4 门禁自愈 —— 真关

### 3.1 代码

`tools/check_all.ps1:85-99` `function Sync-Baseline`：`if (-not $Changed) { return }`；基线缺失才 `Copy + [ok] seeded`（`:90`）；`-AllowMatrixChange` 才 `Copy + [ok] refreshed`（`:95`）；否则 `[keep] $Label left untouched; fresh render: $Fresh`（`:98`），**不写盘**。三个调用点各跟一条 `[fail] … changed; review the diff or pass -AllowMatrixChange`：`:184`+`:186`（smoke）、`:208`+`:210`（PARITY_MATRIX）、`:222`+`:224`（world_diff），失败登记进 `$failures`，末尾 `exit 1`（`:275`）。

### 3.2 实证（副本，避免污染真仓基线）

```
# 篡改：native/generated/engine_smoke.json 所有 0x[0-9a-f]{16} -> 0xdeadbeefdeadbeef
# 95B0156A18500C8D... -> 687B3E0AC77BC1FA...
pwsh -File tools/check_all.ps1 -NoContent -NoDesktop
[keep] native/generated/engine_smoke.json left untouched; fresh render: C:\pvzbuild\aud5repo\build\engine_smoke.fresh.json
[fail] native/generated/engine_smoke.json changed; review the diff or pass -AllowMatrixChange
PROBE_EXIT=1
smoke_after=687B3E0AC77BC1FA46438A6ED492D30992E4F23C68652FD5FF75C040017B5B08    # == 篡改值 = 未被覆盖
```

三件事都成立：exit 1、基线 sha 不变、明确告知 fresh render 路径。**第 2 条真关。**

### 3.3 说明

- 副本里用 `-NoContent -NoDesktop` 是因为副本缺仓库外的 `C:\work\obb_packages`（`zombie classes`/`plant families`/`armors` 三个 Step 会硬失败）与 SDL 资产；真仓的对应运行见附录 A。
- 机制仍是「一次性」的：基线都在 `native/generated/` 且未入库，一旦有人手工覆盖就无从恢复。建议 `Sync-Baseline` 写盘前留 `*.prev`，或把基线纳入 git。

## 4. 第 3 条：双静默降级 —— 真关

代码：`native/src/catalog.cpp` 对**显式** `--pack` / `--boards` 失败抛异常（`"rules pack: " + e.what()` / `"board sizes: " + e.what()`），不再打印 note 后静默退到 JSON 默认。

CLI 实测（`build/native/Release/PvZ2SHUTTLE.exe`，mtime 11-20 22:42:07）：

```
> PvZ2SHUTTLE.exe --audit-content content does-not-exist.pack
error: rules pack: content pack: cannot open does-not-exist.pack            code=1

> PvZ2SHUTTLE.exe --run-level content frontyard_1 --boards does-not-exist.json --seconds 1
error: board sizes: does-not-exist.json: cannot open JSON file (check that the content directory is complete and readable)   code=1

> PvZ2SHUTTLE.exe --run-level content frontyard_1 --boards native/generated/board_sizes.json --seconds 1
{"status":"playing", ...}                                                   code=0   # 对照组
```

测试侧：`native/tests/catalog_test.cpp:82-85`（`"pack error names the stage"` / `"broken pack is fatal, not a silent fallback"`）、`:95-97`（board 两条，含 `"broken board sizes are fatal, not 5x9 everywhere"`）；旧的「fallback 也接受」断言已被替换。**第 3 条真关。**

## 5. 第 4 条：L2 击杀计数 —— 真关

### 5.1 代码

- `world.cpp:839` `void World::damageZombie(EntityId, double, bool ignoreArmor, bool countsAsKill)`，`:859` `if (countsAsKill) ++killed_;`（`damageBoss` 另有一处同形 `:715`）
- 推车主路径 `:281` `damageZombie(zombie.id, 100000, false, false);`，随后 `:282` `if (aliveBefore && !zombie.alive) ++mowerKills_;`
- `:877-879` 保留「despawn 不是 kill」口径（`++removed_`）
- `tools/engine_smoke.py:102-113` 账目守恒：`accounted = killed + mowerKills + leaked`；`accounted > spawned` 一律 raise；`status == "won"` 时要求 `accounted == spawned`；`:149` 要求至少一局 `won`；`:39` `"minKilled": 10`，`:35-37` 注释写明「旧值 25 是因为 `killed` 含推车击杀，脚本局实际只打死约 15 个」。

### 5.2 实测（`python tools/engine_smoke.py --exe build/native/Release/PvZ2SHUTTLE.exe`，32 行）

| 场景 | status | spawned | killed | mowerKills | leaked |
| --- | --- | ---: | ---: | ---: | ---: |
| world beach（代表 26 个无防守世界） | playing | 15 | **0** | 8 | 0 |
| frontyard_1 5x9 | lost | 32 | **0** | 19 | 1 |
| frontyard_1 6x10 | lost | 33 | **0** | 21 | 1 |
| frontyard_1 script | lost | 33 | **15** | 13 | 1 |
| beach_23 win | won | 1 | 1 | 0 | 0 |

- 「非 won 且 `killed == mowerKills > 0`」的行数：**0**（t13 时 26 行全部如此）。
- 脚本局 `killed` 30 → **15**，与台账说法一致；剩余 13 由推车清掉，1 个 `leaked`（推车已用掉后越线）是真实失败而非计数错。
- `beach_23 win` 严格守恒 1 = 1+0+0。

**第 4 条真关。**

## 6. 第 5 条：台账数字 —— 未关

### 6.1 台账怎么写

- `docs/PARITY_BASELINE.md:227-229`（`<!-- test-counts -->` 块）：`| audit | 13 |`、`| desktop | 18 |`、`| python | 259 |`
- `docs/PARITY_BASELINE.md:161`：「audit **13/13** … desktop **18/18**、Python **259 tests OK**（下界口径）、`tools/check_all.ps1` 退出码 **0**」

### 6.2 现树实测（三轮，数字一路涨）

| 时刻 | audit | desktop | python | 与台账 |
| --- | ---: | ---: | ---: | --- |
| t19 交付（11-20 23:00） | 13 | 18 | 259 | 一致 ✓ |
| 本轮 10:10（`ctest -N`，含 `s5_runtime`） | **14** | **19** | **263**（门禁 `== tool tests ==` `Ran 263 tests in 101.215s`） | 全部不符 |
| 本轮 10:26（`replay_s5` 落地后） | **15** | **20** | 263+ | 差距继续扩大 |

差集来源都清楚：`native/CMakeLists.txt:162-165` 的 `s5_runtime`（11-20 23:14）、`:166` 一带的 `replay_s5`（11-21 10:24）以及 `s5_boss`，它们同时进了 audit 与 desktop 配置，台账自 23:00 起没再动过。

### 6.3 后果：干净树上门禁也 exit 1

`pwsh -File tools/check_all.ps1 -NoContent`（11-20 23:19 实测；那次 audit 14/14、desktop 19/19 全绿，只红在台账）：

```
== test ledger ==
[fail] audit ran 14 tests, the ledger says 13
[warn] python ran 263 tests, the ledger says 259 (+4 since it was written; refresh the block when you touch the docs)
[fail] desktop ran 19 tests, the ledger says 18
[fail] test ledger: audit 14 vs 13
[fail] test ledger: desktop 19 vs 18
GATE_EXIT=1
```

`tools/check_all.ps1:239-258` 的口径：python 是**下界**（`-lt` 才红，多了只 `[warn]`），audit/desktop 是**精确匹配**。所以 python 263 vs 259 只是告警，真正让门禁红的是 audit 与 desktop 两行。

这不是「文档过期」那么轻：`check_all.ps1` 是团队唯一合并门禁，它现在对**任何**改动都返回 1，红灯失去信息量；而 `PARITY_BASELINE.md:161` 还写着「退出码 0」，与现树直接矛盾。

### 6.4 契约自身的数字也过期了

t20 的 acceptance 仍写「与现树（audit **11/11**、desktop **16/16**、Ran **106**）逐项核对」——那是 t13 时代的数字；台账写 13/18/259（t19 时代）；现树是 15/20/263+。**三代数字同时存在于契约、台账、现树**，说明「数字跟着树走」没有机制保障，只靠人抄。

**第 5 条：未关。**

## 7. 「队长追加」段与代码的一致性

`docs/reviews/2026-11-20-audit-fixes.md:58-128` 逐条对代码：

| 台账说法 | 代码实际 | 一致 |
| --- | --- | --- |
| `:101` 跳跃搬进 `World::tryVault`，在啃食扫描之前调用 | `world.cpp:182` 早于 `:185`；`tryVault` 在 `:243-262` | ✅ |
| `:112` `check_all.ps1` 新增 `Sync-Baseline`（内容变了不写盘） | `:85-99`，`[keep]` 分支不写盘（§3.2 实证） | ✅ |
| `:125` `damageZombie` 增 `countsAsKill=true`，`tickMowers` 传 `false` 并自增 `mowerKills_` | `world.cpp:839/859`、`:281-282` | ✅ |
| `:127` 脚本局 killed 30 → 15，`minKilled` 25 → 10（含原因注释） | `engine_smoke.py:39`、`:35-37`；实测 killed=15 | ✅ |
| `:62` `testTwentySixWorlds` 原「恒定可过」，现追加四条断言 | 追加的是 `spawned>0` / 确定性 / board 表 / `ran==26`；**status 断言仍是 `playing‖won‖lost` 恒真** | ⚠️ 部分 |
| （同段）「M6 收紧」 | `engine_test.cpp` 的 `argv[3]`（`<temp>`）仍未被使用；usage 仍要求 `<temp>` | ⚠️ 部分 |

## 8. 新发现

### N1（high）台账与现树不同步 → 门禁常红

即第 5 条。修法二选一：把 `PARITY_BASELINE.md:161` 与 `:227-229` 对齐现树（audit 15 / desktop 20 / python 263），或给 `check_all.ps1` 加 `-UpdateLedger` 让门禁自己写回并打印 diff。**必须在 S5 落地完成之后再对齐一次**，否则当场又过期。

### N2（medium）`tryVault` 的窗口与冷却把「跳过一株」变成「瞬移穿过整排」

`world.cpp` 窗口上界 `kEatRangeCols + 0.05 = 1.20` 远大于接触距离 `kEatStartCols = 0.35`；冷却 2 秒允许连跳。见 §2.4：建议上界收紧到接触距离（或按 `jump_distance`），「只跳一次」改成生命周期布尔位，并补「一排 3 株只跳 1 株」的用例。

### N3（medium）门禁运行期间源码被改，结论不可用

§1.2：同一次运行里 audit 绿、desktop 红（`world.hpp:107-115` 引用尚未落地的 `bossDefinition_` 等成员）；第二次运行红在 `LNK2019 BossStage::fireActions`。建议 `check_all.ps1` 运行前后各记一次「所有被编译源文件的 sha 摘要」，不一致就 `[warn] tree changed during the run — verdict is not trustworthy`；复审者的纪律是「用 sha 夹住运行」（本轮即如此，见 §1.1）。

### N4（medium）`LNK1104` 撞一次就打断整个门禁

11-21 10:12 的运行红在 `LINK : fatal error LNK1104: cannot open file '...\build\native\Release\PvZ2SHUTTLE.exe'`——同一时刻没有别的构建在写该产物（我的探针用独立目录 `C:\pvzbuild\aud6build`），最可能是仓库位于 OneDrive 同步目录、同步进程短暂持有刚生成的可执行文件。建议 `build_native.ps1` 对 `LNK1104`/`C1041` 做一次 2 秒重试，或把 `build/` 移出同步（`.gitignore` 管不住 OneDrive）。

### N5（low）`tools/check_all.ps1:136` 含 2 个 0x08 控制字符

字节偏移 5597、5646，渲染成 `# files under test. <BS>uild/desktop-gate is deliberately separate from <BS>uild/native.`。全仓 2833 个源/文档文件只有这一个含控制字符 ⇒ 某次写入把 `\b` 当转义吃了。功能无影响（在注释里），但是「文本被程序改写过」的痕迹；建议重打该行并加一条「源文件禁 0x00-0x08/0x0B/0x0C/0x0E-0x1F」的 lint。

### N6（low）副本里 `s5_runtime` 曾绿变红，未能复现

11-20 23:31 在旧副本 `C:\pvzbuild\aud5repo` 的干净构建上，`s5_runtime` 报 `the second plant must be consumed`（`native/tests/s5_runtime_test.cpp:224`），而同一测试在真仓和今天的新副本里都绿。没有拿到可复现条件，登记为「对该副本环境敏感」；若根因是融合表/pack 的加载顺序，那是一个真实的环境依赖。

### N7（low）`Measure-CtestCount` 读的是上一轮 `LastTest.log`

`check_all.ps1:103-115` 从 `<build>/Testing/Temporary/LastTest.log` 取 `N/M Testing:` 的最大分母。目前 `Step 'audit build'` 每次都会跑 ctest，所以不陈旧；但一旦有人给 Step 加「跳过构建」开关（现在没有），台账会读到上一轮计数而不报错。建议解析前校验日志 mtime 晚于本次运行开始时间。

## 9. 必须先修（按顺序）

1. **（high, N1）** 台账对齐现树（audit 15 / desktop 20 / python 263，且 python 行仍写下界口径），删掉 `PARITY_BASELINE.md:161` 的「退出码 0」或改成真实值；建议同时给 `check_all.ps1` 加 `-UpdateLedger`，把写数字的活儿从人手拿走。
2. **（medium, N3）** 门禁记录运行前后的源码 sha，树动了就降级为 `[warn]` 并不出 verdict；否则每轮复审都要人肉判断「这次红算不算」。
3. **（medium, N2）** 收紧 `tryVault` 的触发窗口、把「跳一次」做成生命周期布尔位，补「一排多株只跳一株」用例。
4. **（medium, N4）** `build_native.ps1` 对 `LNK1104` 类瞬时占用重试一次，或把 `build/` 移出 OneDrive 同步。
5. **（low, N5）** 重写 `check_all.ps1:136`，清掉 2 个 0x08。
6. **（low, M6 残留）** `engine_test.cpp` 的 `<temp>` 参数要么删要么用；`testTwentySixWorlds` 的 status 断言仍恒真，建议改成「26 个世界里至少 N 个不是 lost」这类可失败的断言。

## 10. 未覆盖 / 说明

- 本报告不评审 S5 新功能（`s5_runtime`、`replay_s5`、`s5_boss`、boss 运行时）本身的正确性，只在门禁/计数层面涉及它们。
- `check_all.ps1` 的 `zombie classes` / `plant families` / `armors` 三个 Step 依赖仓库外的 `C:\work\obb_packages`；副本里跑不通（`error: property sheets not found: C:\work\obb_packages`），故 §3.2 的 H4 实证用 `-NoContent -NoDesktop` 并在副本里跳过这些 Step；真仓完整运行见附录 A。
- 真仓全程只读；`native/generated/engine_smoke.json` 的 sha（`95B0156A1850`）与复审开始时一致，可自证我未改基线。

---

## 附录 A：本轮三次 `tools/check_all.ps1 -NoContent`（真仓）

**A-1（11-20 23:19）**：audit `100% tests passed, 0 tests failed out of 14`；`[ok] plant_family_table.inc: 339 plant families`；`Ran 263 tests in 48.406s`；desktop `0 failed out of 19`；`== test ledger ==` 四条（`[fail] audit 14 vs 13`、`[warn] python 263 vs 259`、`[fail] desktop 19 vs 18`），`GATE_EXIT=1`。**这是第 5 条的证据。**

**A-2（11-21 10:12）**：`== audit build ==` `0 tests failed out of 14` → `== tool tests ==` `Ran 263 tests in 101.215s` → `== desktop build ==` 红：

```
native/src/engine/world.hpp(107,49): error C2065: 'bossDefinition_': undeclared identifier
native/src/engine/world.hpp(108,39): error C2065: 'bossSpawned_': undeclared identifier
native/src/engine/world.hpp(111,52): error C2065: 'bossActionUnwired_': undeclared identifier
native/src/engine/world.hpp(114,50): error C2065: 'bossUnavailable_': undeclared identifier
native/src/engine/world.hpp(115,49): error C2065: 'bossTable_': undeclared identifier
[fail] desktop build (exit 1)          GATE_EXIT=1
```

（`world.hpp` 当时 mtime 10:23:42，成员变量 `:269-273` 尚未写入 —— 与 10:12 已经绿了的 audit build 不矛盾，是树在两次构建之间动了。）

**A-3（11-21 10:24，等 45 秒后重试）**：`== audit build ==` 红在链接期：

```
pvz_engine.lib(world.obj) : error LNK2019: unresolved external symbol
  "BossStage::fireActions(void)const" / "BossTable::shared(void)" / "selectBoss(...)"
  referenced in World::activateBossStage / World::World
world_outcome_test / replay_s5_test / zombie_family_test / s5_runtime_test / engine_test /
PvZ2SHUTTLE / progress_test  -> fatal error LNK1120: 3 unresolved externals
[fail] audit build (exit 1)            GATE_EXIT=1
```

（`boss.cpp` 声明了这些符号、定义尚未落地；6 秒后 `replay.cpp` 仍在写。属 §1.2 的落地窗口，不是 t19 的回归。）

**A-4（11-21 10:12，另一次）**：`LINK : fatal error LNK1104: cannot open file '...\build\native\Release\PvZ2SHUTTLE.exe'` → `[fail] audit build (exit 1)`（N4）。

## 附录 B：关键复现命令

```powershell
# 1. B1 反向探针（副本，勿在真仓改）
robocopy <repo> C:\pvzbuild\aud6repo /E /XD build .git work node_modules .agent-teams
# 把 C:\pvzbuild\aud6repo\native\src\engine\world.cpp 的
#   const double landing = centre - 0.55;   ->   centre + 1.05;
pwsh -File C:\pvzbuild\aud6repo\tools\build_native.ps1 -AuditOnly -BuildDir C:\pvzbuild\aud6build
#   期望：8/14 engine ***Failed / "the vaulted plant must survive: a vaulter must not eat it"

# 2. H4（副本）
# 篡改 C:\pvzbuild\aud5repo\native\generated\engine_smoke.json 的任一 hash
pwsh -File C:\pvzbuild\aud5repo\tools\check_all.ps1 -NoContent -NoDesktop
#   期望：[keep] + [fail] + exit 1，且该文件 sha 不变

# 3. 双静默降级
build\native\Release\PvZ2SHUTTLE.exe --audit-content content does-not-exist.pack                    # exit 1
build\native\Release\PvZ2SHUTTLE.exe --run-level content frontyard_1 --boards missing.json --seconds 1   # exit 1

# 4. L2 账目
python tools/engine_smoke.py --exe build\native\Release\PvZ2SHUTTLE.exe --out build\audit-smoke.json

# 5. 台账 vs 现树
& '<vswhere>\...\ctest.exe' --test-dir build\native -C Release -N            # Total Tests
& '<vswhere>\...\ctest.exe' --test-dir build\desktop-gate -C Release -N
python -m unittest discover -s tools/tests -p 'test_*.py'
```
