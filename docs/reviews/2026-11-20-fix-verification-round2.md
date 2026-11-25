# 第二轮修复复核（t13）— 5 条「必须先修」是否真关闭

审核对象：`docs/reviews/2026-11-20-fix-verification.md` 列出的 5 条必须先修项，以及
`docs/reviews/2026-11-20-audit-fixes.md` 里「队长追加」段与代码的一致性。
审核方式：只读，逐条读码 + 实跑 CLI/构建/冒烟 + **一次反向探针**（把修复改回去，确认测试会变红，再还原）。
本报告是唯一写入的文件；源码、测试、生成物均未改动（临时改动全部在 `build/` 或 `C:\pvzbuild\` 的副本里，见 §7）。

## 0. 结论

**verdict = needs_revision**：5 条里 4 条真关，第 5 条（台账数字）部分关闭；另有 2 个新发现的「红窗」阻断项（§5），
两处都是同一类缺陷（用 `ContentPack` 的成员却没有 include `content/model.hpp`），12 分钟内出现两次，建议合并成一个阻断项跟踪。

| # | 条目 | 判定 | 一句话证据 |
|---|------|------|-----------|
| 1 | B1 跳跃（`World::tryVault`） | **真关** | 单次跳跃 + 被跳植物零伤害；把落点改回 `centre+1.05` 后 `engine` 用例立刻红（`the vaulted plant must survive`），已还原 |
| 2 | H4 门禁自愈（`Sync-Baseline`） | **真关** | 篡改基线 → `check_all` exit 1、打印 `[keep] … left untouched`、基线 sha256 前后不变；还原后严格重跑 exit 0 |
| 3 | 双静默降级（`--pack` / `--boards`） | **真关** | 两条 CLI 均 exit 1 且错误文本带阶段名 `rules pack:` / `board sizes:`；`catalog_test` 旧 fallback 断言已换成抛错断言 |
| 4 | L2 击杀计数（`countsAsKill`） | **真关** | 26 个无防守世界 `killed==mowerKills` 的条数由 26 降为 **0**；脚本局 `killed` 30 → **15**；`minKilled` 25→10 有注释 |
| 5 | 台账数字 | **部分** | 历史值已加注（诚实），但「现树值」本身过期：写 11/11、16/16、Ran 106，实测 **12/12、17/17、Ran 136** |
| 附 | 「队长追加」段 vs 代码 | **真关** | tryVault 调用点/落点/窗口、`Sync-Baseline`、`countsAsKill`、`killed` 30→15、`--play-script` 桌面守卫、`sun_` 的 `llround` 逐条对上 |

## 1. 复现环境与快照

工作目录 `D:\OneDrive\文档\pvz_shuttle\repo\pvz2-shuttle-pc`，git HEAD `24a2493`（`native/`、`tools/`、两份台账全部未跟踪）。
审核期间源码被并发修改，下表是**本报告所有行号对应的字节**（2026-11-20 22:16:54 取样，sha256 前 12 位）：

| 文件 | mtime | bytes | sha256/12 |
|---|---|---|---|
| `native/src/engine/world.cpp` | 21:52:00 | 29772 | 99195F557A9C |
| `native/src/engine/world.hpp` | 21:49:07 | 7707 | 363C02F897D0 |
| `native/src/engine/registry.cpp` | 21:48:52 | 23240 | 58D826217B51 |
| `native/src/engine/tuning.hpp` | 20:16:41 | 2244 | 4BC48DF501E2 |
| `native/src/engine/director.cpp` | 19:48:17 | 3451 | 837B3181A6FA |
| `native/src/engine/action_runner.cpp` | 20:24:43 | 11957 | FB92874BF2F1 |
| `native/src/engine/projectile.cpp` | 20:16:48 | 1914 | 982D16DD5ADE |
| `native/src/engine/replay.cpp` | 20:18:33 | 5831 | 9450E9C3AF19 |
| `native/src/engine/entity.hpp` | 20:20:25 | 4363 | EFDFF5689F32 |
| `native/src/catalog.cpp` | 21:47:31 | 17686 | D9B47351BF42 |
| `native/src/main.cpp` | 22:08:22 | 10392 | CCA5923FC933 |
| `native/src/battle_view.cpp` | 22:17:13 | 35856 | 905C61855F94 |
| `native/tests/engine_test.cpp` | 21:50:19 | 32864 | CD3390325A2D |
| `native/tests/catalog_test.cpp` | 21:47:46 | 10294 | 3BD6C008D2DC |
| `native/tests/art_audit_test.cpp` | 22:07:51 | 14874 | 6A82F837F96A |
| `native/CMakeLists.txt` | 22:05:01 | 9865 | A9E2CAC8E4A4 |
| `tools/check_all.ps1` | 21:49:39 | 7308 | A89AA828835B |
| `tools/engine_smoke.py` | 21:54:42 | 9091 | 5E95AAADAC58 |
| `tools/parity_report.py` | 22:16:03 | 17148 | 199D0B738076 |
| `native/generated/engine_smoke.json` | 21:57:08 | 11496 | 95B0156A1850 |

构建全部落在 ASCII 目录，避免 CJK 路径的 mojibake：
`C:\pvzbuild\aud2`（首轮审计构建）、`C:\pvzbuild\aud3`（复审构建）、`C:\pvzbuild\aud4-desktop`（桌面配置）、
`C:\pvzbuild\aud2repo` + `C:\pvzbuild\aud2r`（反向探针的仓库副本与构建）。

## 2. 第 1 条 B1 跳跃 —— 真关

**代码**：`native/src/engine/world.cpp:148` 在 `tickZombies` 里 `if (zombie.family == "jump") tryVault(zombie);`，
位置在 `world.cpp:151` 的啃食扫描（`if (zombie.family != "fly") …`）**之前**，所以跳跃不再被「先啃食、速度归零」吃掉。
`World::tryVault` 在 `world.cpp:209-231`：

- `world.cpp:219` 触发窗口 `ahead = zombie.x - centre` 落在 `[-0.05, kEatRangeCols+0.05]`（≈`[-0.05, 1.20]`）；
- `world.cpp:222` 落点 `const double landing = centre - 0.55;`（植物占位 `[centre-0.5, centre+0.5]` 的外侧）；
- `world.cpp:226` 二次保险 `nextSpecialTick = tick_ + ticksOf(2.0)`；`world.cpp:227` 发 `zombie_hop`。

(a) 落点 `ahead = -0.55` 不满足 `world.cpp:219` 的下界 `-0.05` ⇒ **结构上不可能对同一株重复起跳**（冷却只是第二道保险）。
(b) 落点处啃食条件 `world.cpp:151` 是 `centre <= x+0.35 && centre >= x-1.15`；`x = centre-0.55` 时上界变为 `centre+0.35-0.55 = centre-0.20`，不成立 ⇒ **不啃被跳过的植物**。
(c) `native/src/engine/registry.cpp:375-381` 的 `zombieJump` 已是空实现（注释说明「Vaulting moved into World::tryVault」），族表仍引用它，无双重触发。

**测试**：`native/tests/engine_test.cpp:251-289` `testVaultSkipsPlantAndMowerIsNotAPlantKill`：`beach_23` 清空 wave、墙坚果 (2,4)、
`spawnZombie(jumpId,2)`、跑 180 s，断言 `!plants().empty()`（L283）、墙坚果 hp 不变（L284）、`zombie_hop` 恰好 1 次（L285）、
关卡结算（L286）、`mowerKills()==1`（L287）、`killedZombies()==0`（L288）。

**反向探针（要求 (c) 的硬证据）**：把 `world.cpp:222` 改回 `centre + 1.05` 重建 ——

```
# 副本里改 L222，未触碰共享树
robocopy 整仓 -> C:\pvzbuild\aud2repo  (排除 build/.git/work/node_modules/docs)
(Get-Content …world.cpp -Raw) -replace 'centre - 0.55', 'centre + 1.05' | Set-Content …
pwsh -File C:\pvzbuild\aud2repo\tools\build_native.ps1 -AuditOnly -BuildDir 'C:\pvzbuild\aud2r'
→ REVERSE_EXIT=1
  8/11 Test  #8: engine ...***Failed 0.96 sec
  engine test failed: the vaulted plant must survive: a vaulter must not eat it
  91% tests passed, 1 tests failed out of 11
```

失败点正是「被跳的植物必须存活」，而不是别的断言 —— 说明这条用例钉的确实是跳跃几何，而不是顺手碰到其它条件。
机制：`centre+1.05` 时啃食下界 `centre >= x-1.15 = centre-0.10` 与上界 `centre <= x+0.35` 同时成立，跳完立刻啃同一株（就是旧 B1 的症状）。

**还原**：副本 `world.cpp` 复原后 sha256 = `99195F557A9CC2DEFD3A7E2BFDC35A058D46B886135EE59FBE47BE8CA2858F32`，
与仓库当前同文件 sha **完全相同**（`restored-identical=True`）；副本目录 `C:\pvzbuild\aud2repo` 位于仓库外，共享树全程未被写。

**残留（low，不阻断）**：① 触发窗口上界 1.2 列远大于接触点 0.35 列（`kEatStartCols`）⇒ 僵尸离植物还有 1.2 列时就瞬移过去，
9 列棋盘上 col8 的植物等于「出生即被跳」；② `jump_distance`（`content/zombies.json` 的 pole_vaulter `extra.jump_distance=1`）仍未使用；
③ 没有用例钉「起跳时的 x」与「跳跃距离」，只钉了「恰好 1 次 + 不被啃」。

## 3. 第 2 条 H4 门禁自愈 —— 真关

**代码**：`tools/check_all.ps1:72-86` `Sync-Baseline`：`if (-not $Changed) return;` → 基线缺失才 `Copy` + `[ok] seeded`
→ 显式 `-AllowMatrixChange` 才 `Copy` + `[ok] refreshed` → 否则只打 `[keep] … left untouched` 并**不写盘**。
`tools/check_all.ps1:116` 在任何生成器之前读旧基线，`122` 调 `Sync-Baseline`，`123-126` 才登记失败；smoke / 矩阵 / world_diff 三处同构。

**篡改实测**（基线当时已还原为 `95B0156A…`，先备份再改）：

```
$base = 'native/generated/engine_smoke.json'
BEFORE_RUN_SHA = 6AE368A032F1B0CBA7F47E18C30BAD2F163C777C2B5C94EB5A20485D8E33E8C4   # 已把首个 hash 改成 0xdeadbeef…
pwsh -File <check_all 副本> -NoContent
→ [keep] native/generated/engine_smoke.json left untouched; fresh render: …\build\engine_smoke.fresh.json
  [fail] native/generated/engine_smoke.json changed; review the diff or pass -AllowMatrixChange
  [fail] engine smoke changed
  CHECKALL_COPY_EXIT=1
AFTER_RUN_SHA  = 6AE368A032F1B0CBA7F47E18C30BAD2F163C777C2B5C94EB5A20485D8E33E8C4   # 未被覆盖
```

即：变了 → exit 1、基线字节不动、fresh 留在 `build/`。还原后 `RESTORED_SHA = 95B0156A18500C8D9D9E89CEB16D535D43583B4813B29CF73D727123B4A86E54`（与原值相同，`restored-identical=True`）。

**正向实测**（当前树绿时跑真脚本）：`pwsh -File tools/check_all.ps1 -NoContent` → `[ok] content, build, tests and parity are consistent`，
`CHECKALL_REAL_EXIT=0`，且三份基线 sha256 前后一致（`95B0156A…` / `PARITY_MATRIX.md=D3A93B9D57E5…` / `world_diff.md=B51172EFA247…`）⇒ 内容未变时也不写盘。

> 说明：`-NoContent` 是为了不重写 `native/generated/content.pack`（生成物，超出我的写作用域）。
> 那次「篡改态」的实测用的是 `tools/check_all.ps1` 的**逐字副本** `build/aud-checkall.ps1`，唯一差异是把 `L98 Step 'audit build'` 一行注释掉，
> 原因是当时 audit 构建正处于红窗（§5.1），否则脚本在第二步就中断、走不到 smoke。副本跑完已删除。

## 4. 第 3 条 双静默降级 —— 真关

**代码**：`native/src/catalog.cpp:350` `throw std::runtime_error("board sizes: " + e.what());`、
`native/src/catalog.cpp:370` `throw std::runtime_error("rules pack: " + e.what());`（旧的 `boardsNote = …fallback` 分支已删）。

**CLI 实测**（`C:\pvzbuild\aud2\Release\PvZ2SHUTTLE.exe`；用 `$out = & $sb 2>&1; $code = $LASTEXITCODE` 取码，避免 `| Select-Object -First 1` 提前截断管道导致假 exit 1）：

```
--audit-content content does-not-exist.pack
→ error: rules pack: content pack: cannot open does-not-exist.pack           EXIT=1
--run-level content frontyard_1 --boards does-not-exist.json --seconds 1
→ error: board sizes: does-not-exist.json: cannot open JSON file
  (check that the content directory is complete and readable)                EXIT=1
--run-level content frontyard_1 --boards native/generated/board_sizes.json --seconds 1
→ {"level":"frontyard_1", …}                                                EXIT=0
--audit-content content native/generated/content.pack
→ worlds=26 … plants=147                                                    EXIT=0
```

**测试**：`native/tests/catalog_test.cpp:82` 断言 `what.find("rules pack:")`、`:85` `check(packThrew, "broken pack is fatal, not a silent fallback")`、
`:95` `what.find("board sizes:")`、`:97` `check(boardsThrew, "broken board sizes are fatal, not 5x9 everywhere")` —— 旧的「坏 pack 回落到 JSON」断言已不存在。

**顺带收益确认**：`tools/check_all.ps1` / `engine_smoke.py` 里 26 条世界几何断言现在是有意义的（读 `--boards`），
`check_all` 的 parity 段打印 `worlds obb=46 content=26 matched=22`，与 `native/generated/world_diff.md` 一致。

## 5. 第 4 条 L2 击杀计数 —— 真关

**代码**：`native/src/engine/world.hpp:100` `void damageZombie(EntityId id, double amount, bool ignoreArmor = false, bool countsAsKill = true);`；
`native/src/engine/world.cpp:247` 推车 `damageZombie(zombie.id, 100000, false, false);`，随后 `world.cpp:248` `if (aliveBefore && !zombie.alive) ++mowerKills_;`；
`world.cpp:498` 是 `damageZombie` 定义，死亡分支在 `world.cpp:514` `if (countsAsKill) ++killed_;`；
`world.cpp:545`（`World::explode`，`:538` 起）调 `damageZombie(zombie.id, damage * factor);` 走默认 `countsAsKill=true`（爆炸击杀算击杀，正确）。

**冒烟实测**（`python tools/engine_smoke.py --exe 'C:\pvzbuild\aud2\Release\PvZ2SHUTTLE.exe' --out build/aud-round2-smoke.json`，SMOKE_EXIT=0，32 场景）：

| 场景 | spawned | killed | mowerKills | leaked | 说明 |
|---|---|---|---|---|---|
| 26 个 `world *`（全部） | 6–15 | **0** | 6–8 | 0 | `killed == mowerKills` 的条数 = **0**（修前 26/26 相等） |
| `frontyard_1 5x9` | 32 | 0 | 19 | 1 | leaked=1 ⇒ lost |
| `frontyard_1 script` | 33 | **15** | 13 | 1 | 旧值 30，正好差 15 个推车击杀 |
| `beach_23 win` | 1 | 1 | 0 | 0 | won 时严格相等 |

**断言**：`tools/engine_smoke.py:102` 注释「Every spawn must end up in exactly one bucket: shot down, mowed, or leaked」，
`:105-110` 只挡 `accounted > spawned`，`:111-113` 在 `status=="won"` 时要求 `accounted == spawned`；`:149` 无 `won` 即抛。
`minKilled=10` 与「killed 曾含推车击杀、故本探针曾报 30」的说明在 `tools/engine_smoke.py:35-39`，理由写在注释里。

> 口径提醒（非缺陷）：`lost`/`playing` 结算时不要求 `accounted == spawned`，因为场上还有活僵尸；`leaked` 只记「越线且推车已用完」的那一只。

## 6. 第 5 条 台账数字 —— 部分关闭

历史值的处理是诚实的：`docs/reviews/2026-11-20-audit-fixes.md:50`、`:52` 与 `docs/PARITY_BASELINE.md:162` 都明确写了
「10/10、15/15、Ran 50 属 20:40 的中间状态，已不可在现树复现，保留原文以示改动轨迹」。

问题在「现树值」本身已经过期 —— 现树比台账多一个用例（`art_audit`，`native/CMakeLists.txt:137-141`，22:05 注册）和一批 Python 用例：

| 台账声称 | 位置 | 现树实测 | 复现 |
|---|---|---|---|
| audit **11/11** | `docs/reviews/2026-11-20-audit-fixes.md:143`、`docs/PARITY_BASELINE.md:161` | **12/12** | `pwsh -File tools/build_native.ps1 -AuditOnly -BuildDir 'C:\pvzbuild\aud3'` → `100% tests passed, 0 tests failed out of 12`，AUDIT_FINAL_EXIT=0 |
| desktop **16/16** | `docs/reviews/2026-11-20-audit-fixes.md:144`、`docs/PARITY_BASELINE.md:161` | **17/17** | `pwsh -File tools/build_native.ps1 -BuildDir 'C:\pvzbuild\aud4-desktop'` → `… out of 17`，DESKTOP_FINAL_EXIT=0 |
| Python **Ran 106** | `docs/reviews/2026-11-20-audit-fixes.md:145` | **Ran 136, OK** | `python -m unittest discover -s tools/tests -p 'test_*.py'` |
| （历史段）Python **60 tests** | `docs/PARITY_BASELINE.md:189` | 历史段，已带 21:00 日期 | 可保留，但建议加「现树 136」的括注，与 161 行口径一致 |

判定：**部分关闭**。不是「只在文档里关了」，而是「口径方法对了、数字又落后一轮」。修法是一条命令的事：
把上述三处改成 12/12、17/17、Ran 136（或改成「11/11 + art_audit = 12/12」这种可加式表述），并在 `PARITY_BASELINE.md:161` 同步。

## 7. 「队长追加」段 vs 代码 —— 一致

| 追加段声称 | 位置 | 代码核对 |
|---|---|---|
| 跳跃搬进 `World::tryVault`、在啃食扫描之前调用、落点 `centre-0.55`、窗口 `[-0.05, 1.2]` | `audit-fixes.md:101-104` | `world.cpp:148` / `:209-231` / `:219` / `:222` ✅ |
| `Sync-Baseline` 三处同构、变了不写盘 | `:112-114` | `check_all.ps1:72-86`、`:122`、`:…`（矩阵/world_diff 同构）+ 本报告 §3 实测 ✅ |
| `damageZombie` 增 `countsAsKill`、推车传 false 并自增 `mowerKills_` | `:125` | `world.hpp:100`、`world.cpp:247-248`、`:498` ✅ |
| 脚本局 `killed` 30→15、`minKilled` 25→10 且注释在 `PROBES` | `:127-128` | 实测 15 ✅、`engine_smoke.py:35-39` 注释 ✅ |
| `--play-script` 整体移入桌面守卫、非桌面构建抛 `desktop support is disabled; rebuild with -DPVZ_ENABLE_DESKTOP=ON` | `:135-136` | `main.cpp:46-56`（`#ifdef PVZ_ENABLE_DESKTOP` 包住 `runBattlePreview`，`#else` 抛同文本）✅ |
| `sun_ -= cost` 的 C4244 已改 `static_cast<std::int64_t>(std::llround(cost))` | `:137-138` | `world.cpp:370` ✅ |
| M7「桌面已迁到 `engine::World`，只剩 `--simulate`」 | `:152-153` | 部分成立：`battle_view.cpp:150` 已用 `engine::World::stepSeconds`；`Battle` 仍是 `--simulate` 的路径 ✅（表述可接受） |

## 8. 新发现（不在 5 条内，但同级重要）

### N1（blocker）：12 分钟内两次「红窗」，都是同一个缺 include

| 窗口 | 文件:行 | 报错 | 修复 |
|---|---|---|---|
| 22:04:52 → 22:07:51（audit 配置红） | `native/tests/art_audit_test.cpp:142`、`:150` | `error C2027: use of undefined type 'pvz::content::ContentPack'`、`C2039: 'plants' is not a member` | 22:07:51 加 `#include "content/model.hpp"`（现 L8） |
| 22:09:57 → 22:17:13（desktop 配置红） | `native/src/battle_view.cpp:64`、`:70` | 同 `C2027`/`C2039`（`findPlant`/`findZombie`） | 22:17:13 加 `#include "content/model.hpp"`（现 L4，注释写明「catalog.hpp 只有前向声明」） |

后果：`check_all.ps1` 在第一个窗口第二步就中断（`build/_aud2_checkall.log`：`audit build failed with exit code 1` → `[fail] audit build (exit 1)`），
我这次 H4 实测被迫改用副本；第二个窗口由我的桌面构建撞上（`C:\pvzbuild\aud4_desktop.log`）。
两处根因相同：`catalog.hpp:12` 只前向声明 `ContentPack`，任何调用其成员的新代码都必须自己 include `content/model.hpp`。

建议：① 在 `catalog.hpp` 里把前向声明改成直接 `#include "content/model.hpp"`（成本一次编译期耦合，收益是这类错误一次性消失）；
或 ② 保留前向声明，但给 `ContentPack` 的成员访问加一个 `// requires content/model.hpp` 的静态检查（例如在 `art_index.hpp` 这类聚合头里 include）；
③ 无论选哪个，`check_all` 应该跑**两种配置**（audit + desktop），否则桌面专属文件（`battle_view.cpp` 属 `pvz_launcher`）在 audit 门禁里根本不被编译，
只有人手动跑 desktop 才会发现——这就是第二个窗口能活 7 分钟的原因。

### N2（low）：`PARITY_MATRIX` 仍有 5 行 `playable=0` 字面量

`tools/parity_report.py` 的 `playable_plants`/`playable_zombies` 已按「关卡里出现 + 族在表里」推导（本轮 renew 后打印 41/47），
但 `僵尸 class 族`、`植物行为族`、`世界`、`关卡`、`融合` 五行仍写 `playable=0`，与 docstring「Every number is derived from files on disk, never from constants」不符。
这是 t11 的 L5 残留，不在本轮 5 条内，记录备查。

## 9. 逐条复现命令（可整段复制）

```powershell
cd D:\OneDrive\文档\pvz_shuttle\repo\pvz2-shuttle-pc

# 构建（ASCII 目录，避开 CJK mojibake）
pwsh -File tools/build_native.ps1 -AuditOnly -BuildDir 'C:\pvzbuild\aud3'          # 12/12
pwsh -File tools/build_native.ps1 -BuildDir 'C:\pvzbuild\aud4-desktop'             # 17/17
python -m unittest discover -s tools/tests -p 'test_*.py'                          # Ran 136, OK

# 第 3 条：双静默降级必须非零退出
$exe = 'C:\pvzbuild\aud3\Release\PvZ2SHUTTLE.exe'
$out = & $exe --audit-content content does-not-exist.pack 2>&1; "code=$LASTEXITCODE"; $out
$out = & $exe --run-level content frontyard_1 --boards does-not-exist.json --seconds 1 2>&1; "code=$LASTEXITCODE"; $out

# 第 4 条：记账恒等式 + killed 口径
python tools/engine_smoke.py --exe $exe --out build/aud-round2-smoke.json

# 第 2 条：篡改基线 -> 必须 exit 1 且基线 sha 不变（先备份！）
$base = 'native/generated/engine_smoke.json'
Copy-Item $base build/aud-smoke-baseline.bak -Force
(Get-Content $base -Raw) -replace '0x[0-9a-f]{16}', '0xdeadbeefdeadbeef' | Set-Content $base -NoNewline
$before = (Get-FileHash $base -Algorithm SHA256).Hash
pwsh -File tools/check_all.ps1 -NoContent; "exit=$LASTEXITCODE"
$after  = (Get-FileHash $base -Algorithm SHA256).Hash; "baseline_unchanged=$($before -eq $after)"
Copy-Item build/aud-smoke-baseline.bak $base -Force      # 还原

# 第 1 条：反向探针（在仓库副本里做，不碰共享树）
#   把 native/src/engine/world.cpp:222 的 `centre - 0.55` 改成 `centre + 1.05`
#   pwsh -File <副本>\tools\build_native.ps1 -AuditOnly -BuildDir 'C:\pvzbuild\aud2r'
#   期望：engine 用例红，报 "the vaulted plant must survive"
```

## 10. 声明

- 除本文件外未写任何仓库内文件；`native/`、`tools/`、`content/` 与 `native/generated/*` 均未改动（`engine_smoke.json` 的临时篡改已还原到字节级一致）。
- 反向探针在仓库外的副本 `C:\pvzbuild\aud2repo` 上做，改完已还原，`sha256` 与仓库同文件一致。
- `build/aud-checkall.ps1`（H4 探针用的逐字副本，唯一差异是注释掉 `audit build` 一行）跑完已删除；`build/aud-smoke-baseline.bak` 保留作还原证据。
- 未 commit、未 push。
