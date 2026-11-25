# 商店产物落地（P1-9 / t76）实施与验证记录

日期：2026-11-25 · 只改 `native/src/shop.{hpp,cpp}`、`native/src/progress.{hpp,cpp}`、`native/src/main.cpp`（仅 `--shop` 分支）、`native/tests/shop_test.cpp`、本报告。未改 `content/**`、`native/generated/**`、未 commit。

## §0 结论

商店 585 行里，此前只有 `payload.plant_id`（种子包）能真正发放，`buyable=21`。本轮把 `coins`、`gems`、`world_key`、`costume_id`、`plantfood_slots`、`plantfood_refresh`、`setting`（开关型）六类产物接到 `Progress` 上，并给每次成功购买加一条可复核回执。

- `buyable` **21 → 72**：seed 21 + costume 45 + world_key 1 + plantfood_slots 2 + plantfood_refresh 1 + gems 2。
- `unmodelledCurrency` **仍 479**：gem / mint 计价的行依旧不能花（本轮只新增产出侧的 `Progress::gems`，没有开放消费侧）。
- `shop_test` 由 13 段扩到 **25 段**，六类产物各有「扣款 + 存档增量 + 回执」三重断言，并各自做了「删掉存档写入 → 测试必须红」的反向探针（§4.3，六条全红，原文见下）。
- 三处**如实登记的不可达**见 §7：出厂数据里 `coins`/`gems` 产物行全是 gem/mint 计价（先被币种拒），`setting` 的 16 行全是资源计数器（`mints`/`event_energy`/`sprouts`，按设计拒），因此「开关型 setting」与「coins/gems 产物」只有测试夹具能走到。

## §1 快照（sha256 前 12 · 字节 · 行数 · mtime）

| 文件 | sha12 | 字节 | 行 | mtime |
|---|---|---|---|---|
| `native/src/shop.cpp` | `C6050316AA43` | 16817 | 435 | 11-25 15:09:55 |
| `native/src/shop.hpp` | `1114DF1C9FFE` | 7528 | 154 | 11-25 15:09:16 |
| `native/src/progress.cpp` | `6551D61D1F91` | 18918 | 570 | 11-25 15:22:34 |
| `native/src/progress.hpp` | `921D27E5BE4E` | 9671 | 206 | 11-25 15:18:24 |
| `native/src/main.cpp` | `2B5CB34CA2AA` | 44536 | 782 | 11-25 18:30:32 |
| `native/tests/shop_test.cpp` | `275BD5F80201` | 37798 | 769 | 11-25 18:26:01 |

`native/src/main.cpp` 在 18:30:32 被并发编辑过一次（不是本轮改动）；`--shop` 分支的 `writeInventory` 与 `granted` 仍在：`main.cpp:564-596`（`out["gems"]`、`out["plantfoodRefresh"]`、`out["granted"]`）。CLI 实测（§5）打印的正是这两段，说明并发编辑没有覆盖本轮代码。

## §2 数据事实（`native/generated/shop_unlock.json` 585 行 + `content/shop.json`，独立复算）

payload 键分布：`costume_id` 447（407 个不同 id）、`plant_id` 81、`seed_pack` 24、`setting` 16（`mints` 4 / `event_energy` 9 / `sprouts` 3）、`sun_shovel` 3、`coins` 3、`plantfood_slots` 2、`sun_start_bonus` 2、`seed_slots` 2、`gems` 2、`world_key` 1、`mower_charges` 1、`plantfood_refresh` 1、`collectible` 1；另有 1 行是 `{seed_pack, coins}` 组合。

本轮真正接通的六类，出厂可买行与证据行：

| 类别 | 代表行 | 币种/价 | 一次性 | 产物 |
|---|---|---|---|---|
| `world_key` | `obb_worldkey.rainbowmarket` | coin 2026 | 是 | `{world_key:"rainbowmarket"}` |
| `costume_id` | `obb_com.pvz2.costume.272` | coin 500 | 是 | `{costume_id:"272"}` |
| `costume_id`（免费） | `obb_Tonywrite.Costume.370` | free 0 | 是 | `{costume_id:"370"}` |
| `plantfood_slots` | `obb_com.popcap.pvz2.gameupgrade.pfslot.nonconsume.t1` / `...pfslot2...` | coin 15000 | 是 | `{plantfood_slots:1}` |
| `plantfood_refresh` | `obb_com.popcap.pvz2.gameupgrade.pfrefresh.nonconsume.t1` | coin 15000 | 是 | `{plantfood_refresh:1}` |
| `gems` | `obb_com.popcap.pvz2.gems.1.consume` | coin 3000 | 否 | `{gems:1}` |
| `coins`（产物） | `obb_com.pvz2.coins.3000.consume` | **gem** 3000 | 否 | `{coins:3000}` |
| `setting`（开关） | 出厂 0 行 | — | — | `{setting:"muted"}` 形态只出现在夹具 |
| `setting`（计数器） | `obb_com.popcap.pvz2.mints.1.consume` | coin 30000 | 是 | `{setting:"mints",amount:1}` → 拒 |

`buyable` 的构成（`shop_test.cpp` 的 `testCatalogueCounts` 逐项断言，运行时也打印）：

```
catalogue rows=585 buyable=72 unmodelledCurrency=479 seeds=21 costumes=45 keys=1 slots=2 refresh=1 gems=2
```

另：`implemented && coin && 产物不可交付` 的行共 **15** 行（首版按 4 行写死，实测 15 后改正），这些行被拒的理由是 payload 而不是币种。

## §3 六项逐条

### 3.1 `coins` / `gems` 产物写进 Progress；`mint` 继续拒绝

- `Progress` 新增 `int gems = 0;`（`progress.hpp`，与 `coins` 同段）；`parseProgress` / `progressToJson` 只在非默认值时写这五个新键（pristine 存档逐字节不变，`testGrantsSurviveSaveRoundTrip` 断言）。
- 交付：`shop.cpp:413-418` `case GrantKind::coins: progress.coins += llround(...)` / `case GrantKind::gems: progress.gems += ...`。
- `mint` 计价仍在 `shop.cpp:354-358` 走 `currency ... is not modelled yet`；`payload.mint`（1 行）进 `undeliverable`，整行拒绝。

### 3.2 `world_key` → `Progress::keys`

`shop.cpp:410-411` `case GrantKind::key: ++progress.keys;`。一次性由既有 `one_time` 规则保证（`shop.cpp:329-332` `already owned`），`testWorldKeyIsGrantedOnce` 断言第二次购买不改 keys 也不扣钱。

### 3.3 `plantfood_slots` / `plantfood_refresh`

`shop.cpp:419-424`：slots 累加、refresh 置位。数据形状是 `{plantfood_slots:1}` / `{plantfood_refresh:1}`（数字），所以 slots 用 `int`、refresh 用 `bool`。两行 slots 是两个不同的 row id，可叠加到 2（`testPlantfoodUpgrades`）。CLI 回显 `plantfoodSlots` / `plantfoodRefresh`（§5）。

### 3.4 `costume_id` → `Progress::costumes`（排序去重，不接表现层）

`shop.cpp:403-409` 用 `std::find` 去重后 `push_back` + `std::sort`。旧实现把 payload 一律塞进 `Progress::seeds`，`testCostumeIsRecordedOnce` 里专门有一条 `check(progress.seeds.empty(), "a costume must never be written into Progress::seeds (the old bug)")` 钉住回归。`testCostumeListStaysSortedAndUnique` 用两行同 id 的目录断言列表仍只有一项。

### 3.5 `setting`：开关型写 `settings`，计数器型拒绝

`isSwitchSetting`（`shop.cpp:79`）白名单 `muted | music | sfx | volume`；值可为 bool/number/string，缺 `value` 视为 on（`testSettingSwitchIsStored` 三条：无值=on、`0.5` 保留数字、显式 `false` 不被丢弃）。非白名单（`mints`/`event_energy`/`sprouts`）进 `undeliverable`，拒绝文案 `payload setting is not modelled yet`（`testSettingResourceCounterIsRefused` 断言文案与「存档未变」）。

### 3.6 回执 `BuyResult::granted`

`Grant { GrantKind kind; std::string text; Json value; double number() }`，交付循环里每个 grant 都 `result.granted.push_back(grant)`（`shop.cpp:429`），与写入同一分支，所以「回执说有」与「存档有」是同一段代码的两侧。CLI `out["granted"]` 元素形如 `{"kind":"world_key","id":"rainbowmarket"}` / `{"kind":"gems","value":1}`。

### 3.7 payload 全有或全无

`buildGrants`（`shop.cpp:86`）把每个键分派成 grant 或 `undeliverable`，末尾 `payloadModelled = !grants.empty() && undeliverable.empty()`；`purchase()` 在扣款前判 `!payloadModelled` 并拒绝，文案按名字列出（`payload seed_pack is not modelled yet`）。`testBundleWithUnknownHalfIsRefused` 用 `{seed_pack:1, coins:1000}` 夹具断言「既不扣钱也不发币」。

## §4 测试

### 4.1 25 段清单（`shop_test.cpp` 的 `run()`）

`testCatalogueCounts`、`testKnownRows`、`testPurchaseSpendsCoins`、`testFreeRowCostsNothing`、`testGemRowIsRefused`、`testSeedPayloadIsDeliveredOnce`、`testCoinsPayloadIsCredited`、`testGemsPayloadIsCredited`、`testWorldKeyIsGrantedOnce`、`testPlantfoodUpgrades`、`testCostumeIsRecordedOnce`、`testCostumeListStaysSortedAndUnique`、`testSettingSwitchIsStored`、`testSettingResourceCounterIsRefused`、`testBundleWithUnknownHalfIsRefused`、`testUnknownPayloadKindsAreRefused`、`testWalletGateRunsBeforePayload`、`testReceiptMatchesSaveDelta`、`testGrantsSurviveSaveRoundTrip`、`testRepeatableRowIsNotAlreadyOwned`、`testNotEnoughCoins`、`testWorldRowNeverMintsAKey`、`testRoundTripThroughSave`、`testUntabulatedRowIsRefused`、`testRejections`。

每类产物至少一条「回执 == 存档增量」的断言，集中在 `testReceiptMatchesSaveDelta`（六行一次买齐，逐项对 delta）与各类自己的段里。

### 4.2 三个真实数据快照断言

```
catalogue rows=585 buyable=72 unmodelledCurrency=479 seeds=21 costumes=45 keys=1 slots=2 refresh=1 gems=2
```

（这行是测试自己打印的；`testCatalogueCounts` 里对应 `check`。首版把「coin 计价但产物不可交付」写成 4 行，实测 15 行后改正——这正是断言该做的事。）

### 4.3 反向探针（故意删除存档写入 → 必须红）

做法：在**副本** `C:\pvzbuild\t76src` 里把 `shop.cpp` 交付分支的某一行换成注释（保留 `result.granted.push_back`，即回执仍声称已发），重建 `shop_test` 并运行；每次跑完从仓库复制回来。脚本 `build/probe76.ps1`。原文：

```
PROBE coins: exit=1 :: shop test failed: 1000 - 100 + 250 must leave 1150, got 900
PROBE gems: exit=1 :: shop test failed: 1 gem must be credited, got 0
PROBE key: exit=1 :: shop test failed: exactly one key must be granted, got 0
PROBE costume: exit=1 :: shop test failed: the free costume must land in Progress::costumes
PROBE slots: exit=1 :: shop test failed: one slot must be added
PROBE refresh: exit=1 :: shop test failed: the refresh upgrade must set the flag
restored_identical=True sha=C6050316AA43
```

六个类别六条，全部按预期变红，且红在「存档增量」而不是「ok 标志」上——回执与存档是两处独立事实，测试钉的是后者。

**一个真实的坑**：`Copy-Item` 会保留源文件的 mtime，把副本还原成「旧于产物」的时间戳，MSBuild 因此判定无需重编，继续用被篡改的目标文件（探针脚本最后一次 `final_exit=1` 就是这个原因）。还原后必须 `(Get-Item $f).LastWriteTime = Get-Date` 再重建：

```
shop test failed: ... →（touch 后）shop tests passed (25 sections)
sha src=C6050316AA43 repo=C6050316AA43
```

### 4.4 编译与运行

```
$ cmake --build C:\pvzbuild\shop76live --config Release --target shop_test
  shop_test.vcxproj -> C:\pvzbuild\shop76live\Release\shop_test.exe
$ ctest -C Release -R '^shop$' --output-on-failure
1/1 Test #29: shop .............................   Passed    1.81 sec
100% tests passed, 0 tests failed out of 1
```

（`shop` 在 `native/CMakeLists.txt:428-432` 注册，`TIMEOUT 120`。）

## §5 CLI 原文（`C:\pvzbuild\t76build\Release\PvZ2SHUTTLE.exe --shop content --unlock native/generated/shop_unlock.json --progress <存档>`）

```
survey: exit=0 :: {"buyable":72,...,"coins":0,"costumes":0,"gems":0,"items":585,"keys":0,"missingRows":0,
  "plantfoodRefresh":false,"plantfoodSlots":0,"purchases":0,"seeds":0,"settings":0,"unmodelledCurrency":479}
buy-key(5000): exit=0 :: {...,"coins":2974,"coinsSpent":2026,"granted":[{"id":"rainbowmarket","kind":"world_key"}],
  "keys":1,...,"purchases":1,"ok":true}
buy-costume: exit=0 :: {...,"coins":2474,"coinsSpent":500,"costumes":1,"granted":[{"id":"272","kind":"costume"}],
  "keys":1,...,"purchases":2,"ok":true}
buy-gems: exit=0 :: {...,"coins":1000,"coinsSpent":3000,"gems":1,"granted":[{"kind":"gems","value":1}],...,"ok":true}
buy-slot1: exit=0 :: {...,"coins":35000,"coinsSpent":15000,"granted":[{"kind":"plantfood_slots","value":1}],
  "plantfoodSlots":1,...,"ok":true}
buy-slot2: exit=0 :: {...,"coins":20000,"coinsSpent":15000,"granted":[{"kind":"plantfood_slots","value":1}],
  "plantfoodSlots":2,...,"ok":true}
buy-refresh: exit=0 :: {...,"coins":5000,"coinsSpent":15000,"granted":[{"kind":"plantfood_refresh"}],
  "plantfoodRefresh":true,"plantfoodSlots":2,...,"ok":true}
buy-free-costume: exit=0 :: {...,"coins":5000,"coinsSpent":0,"costumes":2,"granted":[{"id":"370","kind":"costume"}],...}
refuse-gem-costume: exit=1 :: {...,"coins":5000,"coinsSpent":0,"costumes":2,"gems":1,"granted":[],"ok":false,
  "reason":"currency gem is not modelled yet",...}
refuse-mints: exit=1 :: {...,"granted":[],"ok":false,"reason":"payload setting is not modelled yet",...}
refuse-key-again: exit=1 :: {...,"granted":[],"ok":false,"reason":"already owned",...}
```

（`--coins` 会先设置钱包再看成交价，所以 gems 那一跳从 4000 起算；三次拒绝都保持 `coins`/`costumes`/`keys` 不变。）

落盘存档：

```json
{
 "coins": 5000, "costumes": ["272","370"], "gems": 1, "keys": 1, "levels": {},
 "plantfoodRefresh": true, "plantfoodSlots": 2,
 "purchases": ["obb_Tonywrite.Costume.370","obb_com.popcap.pvz2.gameupgrade.pfrefresh.nonconsume.t1",
  "obb_com.popcap.pvz2.gameupgrade.pfslot.nonconsume.t1","obb_com.popcap.pvz2.gameupgrade.pfslot2.nonconsume.t1",
  "obb_com.popcap.pvz2.gems.1.consume","obb_com.pvz2.costume.272","obb_worldkey.rainbowmarket"],
 "seeds": [], "updated": 0, "version": 1
}
```

`costumes` 与 `purchases` 都是排序后的集合；`settings` 未出现，因为本轮没有买到开关型行（§7）。

## §6 实现要点（便于复审时对着看）

- `shop.hpp`：`GrantKind` 八值 + `grantKindName`；`Grant{kind,text,value,number()}`；`ShopItem::grants` / `undeliverable`；`BuyResult::granted`（保留 `grantedSeed` 兼容旧调用）。
- `shop.cpp`：`buildGrants`（`payload` → grants + undeliverable），`purchase()` 顺序 = 未知 id → 一次性已拥有 → 未实装 → 星级门 → 未知门 → 币种/价格 → payload 可交付性 → 余额 → 扣款 → 记录 → 逐 grant 交付 → 回执。
- `progress.{hpp,cpp}`：五个新字段 + 只在非默认时序列化。
- `main.cpp`：`--shop` 的 `writeInventory`（survey 与 buy 共用）+ `out["granted"]`。

## §7 诚实限制与未覆盖

1. **`coins` / `gems` 产物在出厂数据里不可达**：`{coins:...}` 三行、`{gems:...}` 两行所在商品全是 gem 或 mint 计价，`purchase()` 在币种关口先拒。所以这两类的真实链路只有测试夹具能走通；`--shop` 实测能买到的是「用金币买宝石」（`gems` 产物的 2 行确实是 coin 3000/30000），即产出侧可达、消费侧仍封。
2. **开关型 `setting` 出厂 0 行**：16 行 setting 全是 `mints`/`event_energy`/`sprouts`（资源计数器），按设计拒绝，所以 `settings` 段只有测试写过；`testGrantsSurviveSaveRoundTrip` 用它验证了往返。
3. **gem / mint 仍不能花**：本轮只加产出侧。`docs/COMPLETENESS.md:428/451/455`、`PARITY_BASELINE.md:341`、`PROGRESS.md:57` 的 `unmodelledCurrency 479` 因此仍然成立——这也正是把这些文档的数字留着不动的原因。
4. **`mint` 产物的 `reward_unmodelled` 语义**：仓库里没有 `reward_unmodelled` 这个字符串，货币关口用的是 `currency mint is not modelled yet`（与既有文案一致）。若队长要求字面量，属于改名而非新逻辑。
5. **未跑全量 ctest**：只跑了 `shop`（`Test #29 Passed`）。全量审计跑会遇到 `worldmap` 段错误——见 §8，与本轮无关。
6. **表现层未接**：`costumes` / `plantfoodSlots` / `gems` 只是存档字段，没有 UI 消费方（任务明确不接表现层）。

## §8 环境注记（不是本轮改动）

- 15:22 的首次全量构建里 `worldmap` **SEGFAULT**（`ctest -R worldmap` 复现，`worldmap_test.exe content` 直接返回 `0xC0000005`）。`native/src/worldmap.cpp` 是 `0DF57A899F9D`（11-23 10:12）、`worldmap_view.cpp` `CEBBA02751E2`（11-24 09:44），都不是本轮文件；本轮改动不触碰其依赖。留给 S6.4 的所有者。
- 18:03:22 `native/CMakeLists.txt` 被并发编辑成 `5A76C8CBAEBC`，`if(PVZ_ENABLE_DESKTOP)` 与其 `endif()` 缺失，配置直接失败：`CMake Error at CMakeLists.txt:423 (elseif): Flow control statements are not properly nested.` 本轮构建因此在副本 `C:\pvzbuild\t76src` 里补两行（`if(PVZ_ENABLE_DESKTOP)` 与一个 `endif()`，都在副本内、有注释）完成；18:16:13 该文件被其所有者改回可用状态（`26CD5F1BAA21`），随后**在真实树**里配置、构建、跑测试全绿（§4.4）。仓库里的 `native/CMakeLists.txt` 没有被本轮改动。

## §9 文档数字漂移（不在写入范围，需所有者同步）

| 位置 | 现文 | 应为 |
|---|---|---|
| `docs/COMPLETENESS.md:443` | 示例 JSON `"buyable":21` | `72` |
| `docs/COMPLETENESS.md:447` | 示例 JSON `"buyable":21` | `72` |
| `docs/COMPLETENESS.md:451` | 「`buyable 21` 只数…」 | 「`buyable 72`」，并补六类构成 |
| `docs/COMPLETENESS.md:455` | 只描述 `grantedSeed` | 补 `granted[{kind,...}]` 与五类新字段 |
| `docs/PARITY_BASELINE.md:341` | 「`buyable=21 … buyable 只数产物可发放的行（payload.plant_id）`」 | `72`，产物口径改为六类 |
| `docs/PROGRESS.md:27` | 「130 行掉落 + 21 件可购买」 | `72` 件 |
| `docs/PROGRESS.md:57` | 「商品产物只有 `plant_id` 能落地 / 585 件里可买 21 件」 | 已落地六类 / 72 件 |

`COMPLETENESS.md:461` 与 `PARITY_BASELINE.md:342` 的 `wired=585` 不受影响（`--shop` 仍是真实调用方）。

## §10 复现命令

```powershell
# 配置 + 构建（真实树；仓库内 CMakeLists 18:16 之后可用）
cmake -S native -B C:\pvzbuild\shop76live -G "Visual Studio 17 2022" -A x64 -DPVZ_ENABLE_DESKTOP=OFF
cmake --build C:\pvzbuild\shop76live --config Release --target shop_test
C:\pvzbuild\shop76live\Release\shop_test.exe content native\generated\shop_unlock.json C:\pvzbuild\shop76live\Testing\fixtures
ctest --test-dir C:\pvzbuild\shop76live -C Release -R '^shop$' --output-on-failure

# 反向探针（副本内篡改，仓库复制回来；注意 touch）
pwsh -File build\probe76.ps1

# CLI
C:\pvzbuild\t76build\Release\PvZ2SHUTTLE.exe --shop content --unlock native\generated\shop_unlock.json `
  --progress C:\pvzbuild\shop76-cli\存档.json --coins 5000 --buy obb_worldkey.rainbowmarket
```
