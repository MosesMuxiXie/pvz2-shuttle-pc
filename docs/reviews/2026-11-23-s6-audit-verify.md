# S6.2 商店 + t35 修复复审（round 2）

- 复审对象：t35 报告的 2 条 high（H1/H2）、7 条 medium（M1–M7）+ 本轮新落地的 S6.2 商店（`native/src/shop.{hpp,cpp}`、`native/tests/shop_test.cpp`、`--shop`）
- 复审人：auditor（只读；未改任何源文件，未 commit）
- 日期：2026-11-23
- **verdict: needs_revision**（①②③④⑥ 五条真关；⑤ 契约数字与实现不符需更正；商店 2 条新 medium；t35 的 3 条遗留未修但已确认属 S6.3 范围）

---

## 0. 结论摘要

| 判据 | 结论 | 一句话 |
| --- | --- | --- |
| ① H1 世界地图按前缀 + `record.cleared` 统计 | **真关** | 175/175 存档 → `frontyard state=completed`；只通 1 关 → `available` |
| ② M1 `requiredStars` 走 `hasEntryGate` | **真关** | `cowboy` → `requiredStars=0 src=sheet`；`egypt`（无 gate）→ `src=none` |
| ③ M4 负 tick / NaN tick 抛错 | **真关（行为）** | 负 tick 与越界值都非零退出；残留 low：校验作用在 `number()` 的 `int` 截断之后，报错里的数值失真（1e12 / 2³²+1 都印成 `-2147483648`），小数 tick 静默 floor |
| ④ M5 `parseSeconds` 三值 | **真关** | `-5`/`nan`/`1e9` 全部 `exit=1` 且打印契约文本 |
| ⑤ M6 `rows()`/`size()`/`withSplash()` | **契约数字有误，实现更诚实** | 出厂表 **602 行 / 602 个 case-sensitive 唯一 id**，`size()==602`（不是 601）；t35 的「601 唯一」是我用 PowerShell 默认大小写不敏感聚合造成的**测量假象**，本报告更正 |
| ⑥ H2 `Get-TreeStamp` | **真关** | 静树 `exit=0`；跑动中 metadata-only touch → `exit=2` + `[inconclusive]`，被 touch 文件 sha 不变 |
| ⑦ S6.2 商店 | **大体可用，2 条新 medium** | fail-closed、无重复记账、gem 拒绝、free 发放、缺表抛错都成立；但（a）43 行 `one_time=false` 被当一次性，（b）11 条「用 coin 买 gem/mint/energy」的行可购买且**花钱无产出** |
| ⑧ t35 三条遗留是否被扩大/缩小 | **未修也未扩大** | `worldmap_view.cpp` 自 08:54 起未改；`world_gates.json` 62 条悬空 world、`kungfu`×1 / `kongfu`×8 拼写分叉原样 |

**必须先修（blocker/high）**：无 blocker。high 级 0 条 —— 本轮 2 条 high 已真关。
**必须在下个提交修（medium）**：N2 `oneTime` 未实现（⑦a）、N3 coin 买非 coin 产物（⑦b）。
**文档级更正**：⑤ 的 602 与 t36 契约里的 601；`shop_test.cpp:109` 的「每条 free 行都未实现」与数据不符。

---

## 1. 范围与快照

git HEAD `24a2493`（`native/`、`tools/`、`docs/` 仍全部未跟踪）。以下为复审时刻（2026-11-23 09:37，Asia/Shanghai）的指纹：

| 文件 | sha256 前 12 | mtime | 字节 |
| --- | --- | --- | --- |
| `native/src/main.cpp` | `4B09CDFB46FC` | 09:17:27 | 22854 |
| `native/src/worldmap.cpp` | `FA7324578953` | 09:17:14 | 10631 |
| `native/src/worldmap.hpp` | `F75D7B616E0E` | 08:48:25 | 5100 |
| `native/src/worldmap_view.cpp` | `88B104C873D0` | **08:54:41（未改）** | 14318 |
| `native/src/engine/replay.cpp` | `5C70B9295776` | 09:17:27 | 7565 |
| `native/src/engine/projectile_table.hpp` | `6C561B133C97` | 09:17:43 | 3315 |
| `native/src/engine/projectile_table.cpp` | `DC6B03BD59B4` | 09:17:50 | 6723 |
| `native/src/shop.hpp` | `CF19DAF34868` | 09:08:41 | 4559 |
| `native/src/shop.cpp` | `A0E3BEF5F3B6` | 09:10:22 | 9059 |
| `native/tests/shop_test.cpp` | `2DEC111F131B` | 09:12:01 | 11013 |
| `native/src/progress.hpp` | `BF13042BE257` | 09:04:09 | 6737 |
| `native/src/progress.cpp` | `3D89D294880A` | 09:04:09 | 14550 |
| `tools/check_all.ps1` | `321C7C1EC8CD` | 09:33:14 | 19439 |
| `docs/PARITY_BASELINE.md` | `F7EE526DF35B` | 09:35:54 | 27567 |
| `native/generated/world_gates.json` | `7E04A81CE13B` | 09:35:35 | — |

构建（独立目录，避开 `build/native` 的 .tlog 争用）：

```
pwsh -File tools/build_native.ps1 -AuditOnly -BuildDir C:\pvzbuild\aud36
  -> 100% tests passed, 0 tests failed out of 20
  -> Built and tested: C:\pvzbuild\aud36\Release\PvZ2SHUTTLE.exe (2026-11-23 09:40:15, 833024 B)
```

下文所有 CLI 探针都用这个 exe。

---

## 2. 八条判据逐条

### ① H1 世界地图 clearedLevels —— 真关

代码（`native/src/main.cpp:276-283`）：

```cpp
int cleared = 0;
for (const auto& [levelId, record] : progress.levels) {
  if (record.cleared && levelId.rfind(world.id + "_", 0) == 0) ++cleared;
}
...
map.status(world.id, progress.totalStars(), progress.keys, cleared)
```

用例 A（175/175 全通关存档 `build\wm-probe\progress-full.json`，33928 B）：

```
PvZ2SHUTTLE.exe --worldmap content --progress build\wm-probe\progress-full.json
exit=0
{"worlds":26,"gates":97,"stars":350,"keys":0,"clearedLevels":175,...}
frontyard: levels=175 state=completed requiredStars=1 starsSource=client
states: available=0, completed=1, locked=25
```

用例 B（只通 1 关 `build\t36-probe\progress-one.json`）：

```
exit=0   clearedLevels=1
frontyard: levels=175 state=available
states: available=1, completed=0, locked=25
```

t35 的原症状（`clearedLevels:175` 与 `state=available` 并存）已消失。

### ② M1 `requiredStars` 走 `hasEntryGate` —— 真关

`native/src/worldmap.cpp:216-221`：

```cpp
if (world->hasEntryGate) return world->entryStars;
if (!world->keyRequired) return unlockCost(id);
return 0;
```

`:244-251`：

```cpp
status.requiredStars = requiredStars(world.id);
if (world->hasEntryGate) status.starsSource = "sheet";
else if (!world->keyRequired) status.starsSource = "client";
else status.starsSource = "none";
```

实测（`--worldmap content` 的输出行）：

```
cowboy:  requiredStars=0 starsSource=sheet   （0 星 start gate，sheet 明确写 0）
egypt:   requiredStars=0 starsSource=none    （无 gate）
beach:   requiredStars=0 starsSource=none    （无 gate）
frontyard: requiredStars=1 starsSource=client （starter 无 gate，客户端标价不生效）
```

三种来源现在能分开，「sheet 写 0 星」不再被当成「没有 gate」。

### ③ M4 负 tick / NaN tick —— 真关（行为层面），残留 low

`native/src/engine/replay.cpp:32-39`：

```cpp
const double rawTick = number(entry, "tick", 0);
if (!(rawTick >= 0.0) || rawTick > 1.0e9) throw std::runtime_error(
    "replay script: input tick " + std::to_string(rawTick) + " is outside [0, 1e9]");
input.tick = static_cast<std::uint64_t>(rawTick);
```

但 `replay.cpp:13-17` 仍是：

```cpp
int number(const Json& entry, const char* key, int fallback) { ... return static_cast<int>(it->get<double>()); }
```

即 `rawTick` 已经是 `int`。实测：

```
tick:-5        -> exit=1  error: replay script: input tick -5.000000 is outside [0, 1e9]   ✅ 原缺陷已消除
tick:0         -> exit=0  {"sun":50,"tick":120,...}                                        ✅ 正常扣费
tick:1e12      -> exit=1  error: replay script: input tick -2147483648.000000 is outside [0, 1e9]  ⚠️ 报的是截断后的值
tick:4294967297 (2^32+1) -> exit=1  同一条 INT_MIN 报错                                    ✅ 仍被拒（cast 饱和，不是取模）
tick:4294967301 (2^32+5) -> exit=1  同一条 INT_MIN 报错                                    ✅ 仍被拒
tick:1e400     -> exit=1  error: [json.exception.out_of_range.406] number overflow parsing '1e400'  ✅
tick:0.9       -> exit=0  {"sun":50,...}  ← 小数 tick 被 floor 成 0 后照常执行，无 warn
（对照 tick:5 -> exit=0 {"sun":50,...}，行为与 0.9 不可区分）
```

判定：**「静默丢弃输入」已修**，且没有「非法 tick 反而合法通过」的路径（越界 double 的 `static_cast<int>` 在 MSVC 上饱和成 `INT_MIN`，仍被 `< 0` 拦下）。**残留 low**：校验作用在窄化后的 `int` 上，因此（a）错误信息里的数值是 `-2147483648` 而不是文件里的值，会误导排查；（b）小数 tick 静默 floor（`0.9 → 0`），没有告警。修法：给 `number()` 加一个返回 `double` 的重载供 tick 使用，先校验 double 再窄化，并对非整数 tick 报 warn。

### ④ M5 `parseSeconds` —— 真关

`native/src/main.cpp:127-131` + `:153`。实测：

```
--seconds -5   -> exit=1  error: --seconds needs a finite value in [0, 86400], got -5
--seconds nan  -> exit=1  error: --seconds needs a finite value in [0, 86400], got nan
--seconds 1e9  -> exit=1  error: --seconds needs a finite value in [0, 86400], got 1e9
--seconds 86400 -> exit=0（tick 走到 limit）
--seconds 0    -> exit=0  {"status":"playing","tick":0,...}
```

### ⑤ M6 `rows()` / `size()` / `withSplash()` —— **契约数字有误；实现本身更诚实**

`native/src/engine/projectile_table.hpp:69-71`：`size()=specs_.size()`、`rows()=rows_`；`projectile_table.cpp:135-141` 只对首次插入的 id 加 `withSplash_/withPierce_`，末尾 `rows_ = rows->size()`。

数据（`native/generated/projectiles_from_pack.json`）：

```
行数                        = 602
Sort-Object -Unique -CaseSensitive = 602
Sort-Object -Unique（默认）        = 601
差异两条：index 274 "MangosteenPlantFoodDefault"
          index 275 "MangosteenPlantfoodDefault"   （大写 F 变 f，std::map 视为两个键）
```

因此 `size()==602`、`rows()==602`，`projectile_table_test.cpp:66 check(table.size() == 602, ...)` 通过（20/20 全绿）；`:72 withSplash()==180`、`:74 withPierce()==41`，两者都 ≤ `size()` ✓。

**更正 t35**：t35 报告写的「602 行 / 601 唯一」是 PowerShell `Sort-Object -Unique` / `Group-Object` **默认忽略大小写**造成的测量假象，不是表里有真重复。实际是 602 个大小写敏感唯一 id。因此：

- t36 契约里的 `size()==601` **与实现不符**，正确值是 602；
- `first`（判重）分支在出厂数据上**永不触发**，是纯防御代码，且无任何测试覆盖该分支（要覆盖得用合成夹具塞两条真重复 id）。

### ⑥ H2 `Get-TreeStamp` / 门禁诚实性 —— 真关

代码：`tools/check_all.ps1:196-233`（roots = `native/src`、`native/tests`、`native/CMakeLists.txt`、`native/generated`、`content`、`tools`、`docs/PARITY_BASELINE.md`、`docs/PARITY_MATRIX.md`；`$selfWritten` 含 `native/generated/world_gates.json` 等 5 项）；`:398-402` stamp 不等 → `[inconclusive]` + `exit 2`。

**(a) 静树全绿**（`check_all.ps1 -NoContent`，日志 `build\t36-gateA.log`）：

```
== test ledger ==
[ok] audit ran 20 tests (ledger agrees)
[ok] python ran 296 tests (ledger agrees)
[ok] desktop ran 26 tests (ledger agrees)
[ok] content, build, tests and parity are consistent
GATE_A_EXIT=0
```

顺带印证：world diff 段 `worlds obb=46 content=26 matched=22 unmatched_obb=24 unmatched_content=4`、`gates star=53 key=27 world=17 total=97 unknown=0`；该段会重写 `native/generated/world_gates.json` 与 `docs/reviews/2026-11-21-world-gates.md`，二者都在 `$selfWritten`/非 roots 路径上，**不会**把成功运行自身判成 inconclusive。

**(b) 跑动中 metadata-only touch → surface 成 inconclusive**（日志 `build\t36-gateB.log`）：

```
BEFORE sha=F2AA3FFC5E02CE82 mtime=2026-11-23T00:49:37.1809175Z
gate started pid=27972 at 09:44:33
touched metadata at 09:45:35 (still running=True)          ← 只改 mtime，不改内容
GATE_B_EXIT=2
AFTER  sha=F2AA3FFC5E02CE82 unchanged=True mtime_restored=True

== test ledger ==  三行仍全 [ok]
[warn] the source tree changed while the gate ran (D886534DC4B1F6CC -> 292C467D83CDCC81)
[warn] this run is inconclusive: someone edited code mid-run, so its verdict is about no single tree
[inconclusive] rerun on a quiet tree before believing any result
```

这是端到端证据（不是函数级替身）：**绿色运行因别人中途改动而被降级为 exit 2**，被 touch 的文件内容哈希不变、mtime 已还原。t35 的 H2 已关闭。

残留（t35 的 L5，仍未修）：`-NoDesktop` 时 `check_all.ps1:313` 不测 desktop 计数，台账的 desktop 行就此不被核对而脚本仍可 exit 0；`$selfWritten` 白名单也意味着有人手改 `world_gates.json` 不会被 stamp 发现（可接受：该文件由生成器写）。

### ⑦ S6.2 商店（`native/src/shop.{hpp,cpp}`、`shop_test.cpp`、`--shop`）

**口径可复算**：我用 `content/shop.json` + `native/generated/shop_unlock.json` 独立重算了三个数字，与 CLI 输出**完全一致**：

```
--shop content
{"buyable":88,"byUnlock":{"coins":99,"mixed":1,"none":484,"stars":0,"unknown":0,"world":1},
 "items":585,"missingRows":0,"unmodelledCurrency":479}
独立复算：buyable=88（coins 85 + mixed 1 + none 2）、missingRows=0、unmodelled=479 ✅
```

**fail-closed / 拒绝路径**（`shop.cpp:11-13 fail()`、`member()` 缺键抛、`text/number()` 类型不符抛、`Shop::load` 打不开即抛）：

```
--shop content --unlock does-not-exist.json
  exit=1  error: shop: build\t36-probe\does-not-exist.json: cannot open     ✅
--buy no_such_item
  exit=1  {"ok":false,"reason":"unknown item no_such_item","purchases":0}   ✅
--buy obb_com.pvz2.plant.torpedofruit      （currency=gem）
  exit=1  {"ok":false,"reason":"currency gem is not modelled yet","coins":5000,"coinsSpent":0}  ✅ 不扣款
--buy obb_Tonywrite.Costume.370            （currency=free, implemented=true）
  exit=0  {"ok":true,"coinsSpent":0,"purchases":1}                          ✅ 不扣款但记名
```

**无重复记账**（`shop.cpp:218 already owned` → `:253-256` 扣款 + `purchases.push_back` + `std::sort`）：

```
第 1 次 --buy seed_iris：exit=0 coins 5000->4500 coinsSpent=500 purchases=1
第 2 次 --buy seed_iris：exit=1 reason="already owned" coins=4500 purchases=1
存档回读：{"coins":4500,"keys":0,"levels":{},"purchases":["seed_iris"],"updated":0,"version":1}
```

`Progress::purchases` 往返稳定（排序 + 落盘 + 回读一致，`progress.cpp:273-280/332-336`）。

**`.at()` 稀疏 map 风险已修**：`byUnlock_` 预置 6 种 kind（`shop.cpp:180` 之前），`shop_test.cpp:51 check(shop.byUnlock().at(UnlockKind::stars) == 0, ...)` 通过；09:06 那次 `invalid map<K, T> key` 已不再复现（20/20 全绿）。

**新发现 N2（medium）：`one_time=false` 的可重复购买行被当成一次性**

`shop.cpp:151 item.oneTime = flag(entry, "one_time");` —— 解析了，**`purchase()` 从未读取**；所有行的唯一性都靠 `owns(progress, id)`（`:218`）。而 `shop.json` 里有 43 行 `implemented=true && one_time=false`，其中 11 行是 coin 定价（因此落在 `buyable=88` 里）。实测：

```
obb_com.popcap.pvz2.gems.1.consume (one_time=false, implemented=true, currency=coin, price=3000)
  第 1 次：exit=0 coins 20000->17000 coinsSpent=3000 purchases=1
  第 2 次：exit=1 reason="already owned" coins=17000
```

可重复购买的商品第二次被拒。修法：`purchase()` 用 `item.oneTime` 决定是否走 `owns()` 检查（`one_time=false` 允许重复），并在 `shop_test` 里加一条「同一 `one_time=false` 行买两次都成功」的断言。

**新发现 N3（medium）：用 coin 买非 coin 产物 —— 花钱无产出**

上面那条 `obb_com.popcap.pvz2.gems.1.consume` 的产物是 **gems**，但它的定价货币是 coin，所以 `spendable=true` ⇒ 计入 `buyable`。购买返回 `ok=true`、扣 3000 币、`purchases` 记名，而 `Progress` 不跟踪 gems ⇒ **玩家付币后什么都没拿到**。`shop.hpp:10-11` 的注释只处理了「gem 定价的行」（报为 unmodelled），没有处理「coin 定价、gem 产物的行」。同类行 11 条（`obb_lte_energy_*`、`*.gems.1.consume` 等）。修法：`buyable` 增加「产物可交付」判据（payload/`item_type` 属于 Progress 能记的东西），或在输出里单列 `buyableButUndeliverable`，并让 `purchase()` 对这类行返回明确拒绝理由。

**其余（low）**

- L-A：`ShopItem::unlockCoins/unlockStars/unlockWorld`（`shop.cpp:161-163`）解析后无消费者。`shop.hpp:8-11` 已声明「sheets 没有价格闸列，`unlock.kind` 是唯一被承认的闸」，故属**文档一致的死字段**，但 99 条 `coins` 行里的 `unlock.coins`（如 12000）从不校验，读者容易误解；建议注释说明或删字段。
- L-B：`shop_test.cpp:109` 注释「Every shipped free row is also unimplemented」与数据不符 —— 6 条 free 行里 2 条 `implemented=true`（`obb_Tonywrite.Costume.370`、`obb_action_container_product`），实测前者能成功领取。断言本身（`!shipped.ok`）仍成立（它挑的是未实现的那条），但注释会误导下一个人。
- L-C：`index_`/`unlockById` 都用 `emplace`，重复 id 静默保留首个，无计数也无告警（出厂数据 `duplicate_ids=2` 是既知问题，商店侧没有暴露）。
- L-D：`number()` 把 price 截断成 int（`1.5 -> 1`）。出厂 585 行 price 全是 `Int64`，当前零损失；一旦源表出现小数价会静默取整。
- 数据面：`stars` 类解锁行在出厂数据里 **0 条**（`byUnlock.stars=0`），该拒绝分支只能靠合成夹具覆盖；`missingRows=0`（每一行都有 unlock 记录）。

### ⑧ t35 三条遗留 —— 未修，也未扩大

```
native/src/worldmap_view.cpp  sha12=88B104C873D0  mtime=11-23 08:54:41   （本轮未改）
  L155: if (entry.first.rfind(world.id + "_", 0) == 0) ++cleared;        ← 仍信任存档键，不校验关卡存在
  L204: const WorldInfo& world = map.worlds()[selected];                 ← 仍无空保护
  L237: const WorldInfo& world = map.worlds()[row.index];
  L264: const WorldInfo& world = map.worlds()[selected];
  L320: result.selectedWorld = map.worlds()[selected].id;
```

门数据（`native/generated/world_gates.json`，97 条，全部带 `world`）：

```
26 个客户端世界（--worldmap 实测）：frontyard,egypt,pirate,cowboy,future,dark,beach,lostcity,
  iceage,kongfu,dino,eighties,modern,sky,chinesegarden,heian,fairy,mausoleum,steam,memorytour,
  losantosvice,lunarrainbowmarket,renai,muji,carnival,plantagenet
world 不在上述集合的 gate = 62
  其中 thymedevent×16, thirdanniversary×7, fourthanniversary×6, gtax×6, sixthanniversary×3,
       yourhousex×2, skycity×2, tutorial×1 ...
kungfu 的 gate = 1     （拼写分叉仍在）
kongfu 的 gate = 8
```

与 t35 一致：**遗留既没有修，也没有被这轮改动扩大**。这三条属于 S6.3+ 的世界地图 UI 范围，建议单独立项而不是留在审核报告里。

---

## 3. 未覆盖 / 无法验证的部分（诚实登记）

1. **桌面世界地图视图的交互**（点击进入关卡、Esc 返回、snapshot 帧）只在 t35 静态读过，本轮未跑 `worldmap_render`（desktop 配置里有该用例，20 个 audit + 26 个 desktop 用例中它绿，但我没有单独复跑它的画面断言）。
2. **`worldmap_view` 的空世界越界**（M3）只能靠构造 `"worlds": {}` 的 map 文件复现；该文件由生成器写，我没有改任何数据文件，故未做活的越界演示 —— 结论仍基于代码阅读（4 处无保护索引）。
3. **`[inconclusive]` 在「构建失败」路径上的优先级**：实测只覆盖了「全部步骤绿 + stamp 变化 → exit 2」。若某步骤先失败，`:353` 的 `exit 1` 会先执行，stamp 不再比较（t35 已登记，本轮未变）。
4. **商店的 gem/mint 货币**：`Progress` 不跟踪，故「买 gem 包」类路径只能验证拒绝面，验证不了发放面。
5. `one_time` 的语义来自 `content/shop.json` 的 `one_time` 字段；我按「字段存在即意图」判断，未去 OBB 原始 sheet 求证（`obb_art.py` 被禁止运行）。

---

## 4. 必须先修清单

**blocker**：无。

**high**：无（本轮 H1/H2 已真关）。

**medium（建议下个提交内修）**

1. **N2 = ⑦a**：`native/src/shop.cpp:218` —— `one_time=false` 的 43 行（11 行在 `buyable` 内）被 `owns()` 强制成一次性，`ShopItem::oneTime` 解析后从未使用。
2. **N3 = ⑦b**：`native/src/shop.cpp:175-181` —— 11 条「coin 定价、gem/mint/energy 产物」的行计入 `buyable` 且购买成功扣币，但产物无处落地，玩家花钱无所得。

**low（随文档/后续提交）**

3. **③ 的残留**：`native/src/engine/replay.cpp:13-17/32-39` —— tick 校验作用在 `int` 上，报错数值失真（`1e12`、`2^32+1` 都印成 `-2147483648`），小数 tick 静默 floor。
4. ⑤ 与 t36 契约里的 `size()==601` 更正为 602（本报告 §2⑤ 已给证据）；`first` 判重分支在出厂数据上永不触发，需合成夹具才能覆盖。**已于 2026-11-23 10:00 更正**（`docs/reviews/2026-11-23-s6-audit.md` 的台账与 `docs/COMPLETENESS.md` §2.14）。
5. `shop_test.cpp:109` 的注释与 6 条 free 行的实际 `implemented` 不符。
6. `shop.cpp:161-163` 的 `unlockCoins/unlockStars/unlockWorld` 是死字段（`shop.hpp` 已声明不承认价格闸，两者择一改）。
7. `tools/check_all.ps1:313`：`-NoDesktop` 下 desktop 台账行不被核对（t35 L5）。
8. `native/src/worldmap_view.cpp:155/204/237/264/320`：前缀数 cleared、`worlds()` 无空保护（t35 M2/M3，属 S6.3 范围）。
9. `world_gates.json` 里 62 条 gate 的 `world` 不属于任何客户端世界，`kungfu`/`kongfu` 拼写分叉（t35 M7，属 S6.3 范围）。

---

## 5. 已核对无问题的点

1. `Shop::load` 打不开 shop.json / unlock 表即抛错（`shop.cpp:11-13`、`fail()` 带 origin 路径）；缺表不会退化成「全都能买」。
2. `buyable` / `unmodelledCurrency` / `missingRows` 与 `byUnlock` 全部由数据推导，我用独立脚本复算得到完全相同的 88 / 479 / 0 与 `coins 99, mixed 1, none 484, world 1`。
3. 重复购买不重复记账：第二次 `already owned` 时不扣币、`purchases` 不增长。
4. gem 定价行被拒且币值不变；free 行发放但不扣币；未知 id 与缺表都是非零退出 + 明确 reason。
5. `Progress::purchases` 往返稳定（`std::sort` 后落盘，回读一致）。
6. `byUnlock()` 现在预置 6 种 kind，`shop_test.cpp:51` 的 `.at()` 不再抛（09:06 的 `invalid map<K, T> key` 已消失）。
7. `Get-TreeStamp` 的 roots 覆盖 `content/`、`native/generated/`、`tools/`、`docs/PARITY_*.md`，`$selfWritten` 覆盖 5 个生成物；静树绿、跑动中改动降级为 exit 2，均实测。
8. `--seconds` 的三个非法值全部非零退出；`--worldmap` 的 clearedLevels 与状态不再自相矛盾；`requiredStars` 的 sheet/client/none 三态可区分。

---

## 6. 复现命令

```powershell
Set-Location 'D:\OneDrive\文档\pvz_shuttle\repo\pvz2-shuttle-pc'
# 构建（独立目录）
pwsh -File tools/build_native.ps1 -AuditOnly -BuildDir C:\pvzbuild\aud36
$exe = 'C:\pvzbuild\aud36\Release\PvZ2SHUTTLE.exe'
# ① H1
& $exe --worldmap content --progress build\wm-probe\progress-full.json
& $exe --worldmap content --progress build\t36-probe\progress-one.json
# ② M1（看 cowboy / egypt / frontyard 三行）
& $exe --worldmap content
# ③ M4
& $exe --run-level content frontyard_1 --script build\s6audit-probe\tick-neg.json --seconds 2
& $exe --run-level content frontyard_1 --script build\s6audit-probe\tick-zero.json --seconds 2
& $exe --run-level content frontyard_1 --script build\t36-probe\tick-wrap.json --seconds 2      # tick=4294967297
& $exe --run-level content frontyard_1 --script build\t36-probe\tick-frac.json --seconds 2      # tick=0.9
& $exe --run-level content frontyard_1 --script build\t36-probe\tick-5.json --seconds 2         # 对照 tick=5
# ④ M5
foreach ($s in @('-5','nan','1e9','86400','0')) { & $exe --run-level content frontyard_1 --seconds $s }
# ⑤ M6
python -c "import json;d=json.load(open('native/generated/projectiles_from_pack.json'));print(len(d))"
# ⑥ H2（静树 / 跑动中 touch）
pwsh -File tools/check_all.ps1 -NoContent
# ⑦ 商店
& $exe --shop content
& $exe --shop content --coins 20000 --progress build\t36-probe\repeat\progress.json --buy obb_com.popcap.pvz2.gems.1.consume   # 跑两次
& $exe --shop content --coins 5000 --buy obb_com.pvz2.plant.torpedofruit
& $exe --shop content --unlock build\t36-probe\does-not-exist.json
```

---

*本轮为只读复审：未修改任何源文件/测试/生成物，未 commit。被 touch 的 `native/tests/worldmap_test.cpp` 内容哈希已核对未变、mtime 已还原。*

## 队长处置（2026-11-23 10:20）

- **N2 `one_time` 从不读取**：已修。只有 `one_time=true` 的行用 ownership 拦；43 行可重复购买行不再
  第一次买完就报 `already owned`。合成夹具 `testRepeatableRowIsNotAlreadyOwned` 能买两次、`purchases` 保持集合、
  种子不重复入账。
- **N3 收币无产物**：已修，且修法比报告更严——新增 `Progress::seeds`，唯一能真正发放的产物是
  `payload.plant_id`；其余产物（costume/setting/seed_pack/gems/world_key/mower_charges/plantfood_*）
  一律 `payload <kind> is not modelled yet` 拒绝。`buyable` 因此从 88 降到 **21**（coin 计价 + 已实现 +
  门槛已知 + 产物可发放）。CLI：`--buy seed_iris` → `grantedSeed:"iris"`、`seeds:1`。
- **顺带发现的第三个 bug（报告未覆盖）**：`payloadKey` 原先取 `payload.begin()`，而 nlohmann 的 object
  键按字母序排列，`{amount, setting, color}` 会取到 `amount`——产物识别依赖字段名字母序。
  已改为显式优先级表（`plant_id → costume_id → seed_pack → setting → …`）。
- **复核口径**：`buyable=21 / unmodelledCurrency=479 / missingRows=0` 现在由 `shop_test.cpp` 20 条用例钉住；
  门禁 audit 20 / python 296 / desktop 26，严格 `check_all -NoContent` **EXIT=0**。
