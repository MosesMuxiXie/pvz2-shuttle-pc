# 植物行为族 → 原版表证据（S3.4a）

日期：2026-11-20 · 任务：t6 [S3.4a family-numbers-from-pack]
范围：`native/src/engine/registry.cpp` 的 11 个植物行为族、`native/tests/engine_test.cpp` 的新测试。
本文只记录**测量到的证据**与据此做的取舍；`action_runner.cpp`（槽位执行器）已定稿，本轮不动。

## 1. 怎么量的

- 行为族归属不在 pack 里：`native/generated/content.pack` 的 `plants[].families` 是薄荷（Spearmint / StarFruit）分组，不是行为族。族名只存在于 `content/plants.json` 的 `behavior` 字段（147 株）。
- 数值只在 pack 的 `Actions` 里：`plants[].properties` 只有 `{name, sheet}` 指针，没有 objdata 数值；`Actions` 由 contentc 从 `pkg_2073_PlantPropertySheet.json` 逐字段抄来，缺失字段就是原表缺失，不是抽取时丢掉。
- 因此量法是把 `content/plants.json` 的 `id → behavior` 与 pack 的 `id → actions` 连接（两侧 id 由 S3.0 的 `native/generated/id_mapping.csv` 对齐，这里直接用同名的 content id 匹配）。
- 复核命令（仓库根）：

```
python - <<'PY'
import json, collections
plants = json.load(open('content/plants.json', encoding='utf-8'))
pack = json.load(open('native/generated/content.pack', encoding='utf-8'))
by_id = {p['id']: p for p in pack['plants']}
fam = collections.defaultdict(list)
for p in plants: fam[p.get('behavior', '(none)')].append(p)
for name in sorted(fam):
    rows = fam[name]
    resolved = [p for p in rows if p['id'] in by_id]
    withact = [p for p in resolved if by_id[p['id']]['actions']]
    print(name, len(rows), len(resolved), len(withact),
          dict(collections.Counter(a['kind'] for p in withact for a in by_id[p['id']]['actions'])))
PY
```

## 2. 族 → pack 证据表

| 族 | content 株数 | pack 命中 | 带 Actions | Action Type 计数 | 出现过的字段 | 代表植物（带 Actions） |
| --- | --- | --- | --- | --- | --- | --- |
| shoot | 42 | 14 | 14 | projectile 30 / special 2 / unknown 1 / plantfood 1 / explode 1 | CooldownTimeMin/Max 25、SpawnOffset 31、InitialMin 24、RectTriggerRange 7、Damage 7、ExplodeRadius 1 | peashooter, snowpea, repeater, threepeater, starfruit, magnifyinggrass, splitpea, homingthistle |
| lob | 28 | 7 | 7 | projectile 12 / special 6 | CooldownTimeMin/Max 10、SpawnOffset 17、InitialMin 10、Damage 3、RectTriggerRange 5 | cabbagepult, kernelpult, melonpult, wintermelon, begonia, missiletoast, paradoxpult |
| produce | 16 | 3 | 3 | sun 2 / special 4 | CooldownTimeMin/Max 2、SpawnOffset 2 | sunflower, sunshroom, jasmine |
| wall | 14 | 4 | 1 | projectile 2 / special 1 | CooldownTimeMin/Max 2、RectTriggerRange 3 | yuccaguardian |
| instant | 13 | 7 | 7 | explode 5 / special 1 / projectile 3 | CooldownTimeMin/Max 6、Damage 5、RectTriggerRange 5、ExplodeRadius 1、InitialMin 2 | cherry_bomb, jalapeno, squash, iceburg, potatochip, frozenpear, solarflare |
| spike | 11 | 2 | 2 | special 3 | Damage 3、CooldownTimeMin/Max 2、RectTriggerRange 3 | spikeweed, bonkchoy |
| support | 10 | 2 | 2 | special 2 / explode 1 / projectile 2 | Damage 2、CooldownTimeMin/Max 3、RectTriggerRange 3 | torchwood, taraxacum |
| chomp | 5 | 1 | 1 | projectile 1 | CooldownTimeMin/Max 1、Damage 1、RectTriggerRange 1、InitialMin 1 | chomper |
| mine | 4 | 2 | 2 | explode 2 | CooldownTimeMin/Max 2、RectTriggerRange 2 | potatomine, seapotatomine |
| boomerang | 3 | 1 | 1 | projectile 4 | CooldownTimeMin/Max 4、SpawnOffset 4、InitialMin 4 | bloomerang |
| fume | 1 | 1 | 1 | projectile 1 / special 1 | Damage 2、CooldownTimeMin/Max 1、RectTriggerRange 2、SpawnOffset 2 | fumeshroom |

结论（测量本身说明的三件事）：

1. **覆盖面很薄**：147 株里只有 44 株能在 pack 里按同名 id 找到，其中 41 株带 `Actions`。`wall`(14)、`lob`(28)、`produce`(16)、`spike`(11)、`support`(10) 等族绝大多数植株**没有 pack 证据**，只能走 content JSON 或常量。这也是为什么本轮保留常量并把它们逐条标注为 fallback，而不是把常量删掉。
2. **族与 Type 不是一对一**：`shoot` 族里混着 `special`/`unknown`/`plantfood`/`explode`；`fume` 的 1 株同时有 `projectile`(20 伤害) 和 `special`(1500 伤害)。因此驱动槽位的选取规则必须是「本族自然的 Type 优先，没有就取第一个 `special`」，而不是「取第一个 action」。
3. **原表与 content 的简化值确实冲突**，冲突处一律以表为准：fumeshroom 表 20 / content 40；bloomerang 表 1.35–1.5s / content 2.7s；chomper 的触发窗 110px 宽（≈1.42 列）/ 旧常量 1.0 列。spikeweed 的 10 伤害两侧一致（真正的问题在节奏，见下）。

## 3. 每个族现在取哪个数（pack > content JSON > 常量）

统一解析顺序写在 `registry.cpp` 顶部：`driverAction()` 取驱动槽位 → `damageOf()` / `cadenceOf()` / `radiusOf()` / `windowOf()` / `spawnOffsetOf()` 逐个字段按「pack > content > 常量」解析。

| 族 | 节奏 | 伤害 | 范围 / 几何 | 依据 |
| --- | --- | --- | --- | --- |
| shoot | `CooldownTimeMin/Max` 中值 → content `interval` → 1.4s（**改**：此前只有 content/常量） | pack `Damage` → content `damage` → 20 | 发射点 `SpawnOffset.x`（px/60）→ `kShotStartOffsetCols` 0.35（**改**） | peashooter 1.35–1.5s、+35px |
| lob | 同上 → 2.0s（**改**） | 同 → 40 | 同上；溅射 content `splash` → 0.5 | cabbagepult 2.85–3s |
| produce | `sun` 槽 `CooldownTimeMin/Max` → content `sun_interval` → 24s（**改**） | 阳光值 content `sun_value` → 25（不变） | 植株中心 | sunflower 32–36s；jasmine 只有 `special`，仍走自己的定时器 |
| instant | content `delay` → 1.0s | pack `Damage` → content `damage` → 1800 | `ExplodeRadius` → 触发窗半径 → 1.5（**改**） | cherry_bomb 1800 @2.5；squash 1800、窗 215×70px |
| mine | content `delay` → 14s（布防） | 同上 → 1800 | **`RectTriggerRange` 换成布防窗**（**改**：potatomine −30..+35px ≈ [−0.50, +0.583] 列，替换旧的 `centre−0.55 … +0.55`）；半径 `ExplodeRadius` → 窗半径 → 1.0 | potatomine 表里无 Damage/无 Radius，故伤害与半径仍取 content |
| chomp | content `interval` → 40s（咀嚼）；**不用** pack 的 1.75–2s（那是该 action 自身的重复，不是吞咽） | pack `Damage`(0→跳过) → content 1800 | 触发窗右沿 1.42 列（**改**：旧常量 1.0） | chomper 窗 110×70px、Damage 0 |
| fume | `CooldownTimeMin/Max` 中值 2.425s → content 2.4 → 1.5（**改**） | **pack 20** 优先于 content 40（**改**） | 触发窗 5 列（rect_grid）→ 4.0（**改**） | fumeshroom Damage 20、rect_grid 5×1 |
| boomerang | 1.35–1.5s → content 2.7 → 3.0（**改**） | pack `Damage`(无) → content 40 → 20 | 触发窗 → 4.0 | bloomerang 4× projectile |
| spike | `special` 槽 `CooldownTimeMin/Max` → content `interval` → 0.5（**改**） | pack `Damage` → content → 20；**每次开火结算一次全额**（**改**：旧代码每 tick 只给 `damage/60`） | 触发窗半宽 0.533 列 → 0.55（**改**） | spikeweed 10 @0.5s、窗 64×60px |
| support | — | — | — | 仍是空实现（torchwood 的 20 伤害/1s 与 explode 900 已记录，等 S3.5 光环） |
| wall | — | — | — | 只是挨打，无动作 |

关于 `spike` 为什么只有它按「每次开火」结算：`action_runner.cpp` 只对 `spikeweed`/`bonkchoy` 这两个族真正以「每次 firing 调一次族函数」的方式进入（`special` 槽 → `familyCoveredBySheet`）。其余族的带槽植株从不进族函数，族函数只在每 tick 的兜底路径上被调用，所以它们保留自己的定时器，只把定时器的**数值**换成表里的 `CooldownTimeMin/Max`。`produce` 尤其不能改成每 firing 一次：`jasmine` 只有无名 `special` 槽（缺省 1s 冷却），那样会变成每秒产一次阳光。

## 4. 仍然依赖 fallback 常量的清单

所有常量都在 `registry.cpp` 里带 `// fallback: tuning constant, no pack evidence` 注释：

| 族 | 仍在用的常量 | 何时才会用到 |
| --- | --- | --- |
| shoot | 1.4s / 20 | 既无 pack 槽也无数值字段的无证书株 |
| lob | 2.0s / 40 / 0.5 | 同上（28 株里 21 株无 pack 证据） |
| produce | 24s / 25 | 无 pack 且无 `sun_interval`/`sun_value` |
| instant | 1.0s / 1800 / 1.5 / 0.5 | 13 株中 6 株无 pack 证据 |
| mine | 14s / 1800 / 1.0 / ±0.55 | pack 无 Damage / 无 Radius / 无触发窗时 |
| chomp | 40s / 1800 / 1.0 | 咀嚼时长与伤害在原表里没有对应字段（`Damage: 0`） |
| fume | 1.5s / 20 / 4.0 | 只有 fumeshroom 一株，且三样都有证据，实际不触发 |
| boomerang | 3.0s / 20 / 4.0 | 伤害与范围无证据（表里无 Damage、无窗） |
| spike | 20 / 0.5 / ±0.55 | 9 株无 pack 证据的尖刺 |
| support / wall | — | 无动作 |

`explode` 的 `SplashDamage` 一律取 content（表里没有该字段），保留 `kInstantSplash` / `kLobSplash` 作兜底。

## 5. 新测试断言了什么

`native/tests/engine_test.cpp` 新增 `testFamilyNumbers`（4 个族，直接调 `Registry::shared().plantBehavior(族)(world, plantId)`，绕开 `World::tick`，让族函数本身负责取值）：

1. **fume**：fumeshroom，同一行放一只僵尸。断言首次造成伤害的那次族调用落在 `CooldownTimeMin/Max` 中点（2.425s，即 `tickOffset` = 146；调用序号 0 基，实测 145，偏差 −1，容差 ±2），且**掉血恰好 20**（表里的 Damage），不是 content 的 40。
2. **spike**：spikeweed 上一次族调用必须**恰好扣 10 点**（表里的 Damage 一次结算），而不是旧的每 tick `10/60`。
3. **mine**：potatomine 跳过布防后，僵尸停在触发窗左侧 0.02 列外时**不得**引爆（旧 ±0.55 扫掠会引爆），停在右侧窗沿内 0.02 列时**必须**引爆并带走僵尸——证明布防窗来自 `RectTriggerRange`（[−0.50, +0.583]）而不是裸 1.1 列。
4. **chomp**：chomper 吞掉 1.2 列外的僵尸（表里的触发窗 1.42 列，旧常量 1.0 只能看到 1.0 列），且断言 pack 里 `Damage: 0`。

反向验证（`registry.cpp` 里逐个改回旧行为，跑 `engine_test` 必红，随后恢复并复核 sha256 与恢复前一致）：

| 探针 | 改动 | 失败信息 |
| --- | --- | --- |
| A | fume 伤害改用 content | `one fume blast must deal the pack's Damage (20.000000), not content's 40, got 40.000000` |
| B | spike 改回每 tick 结算 | `one spike firing must deal the pack's Damage (10.000000), got 0.333333` |
| C | mine 改回 `centre−0.55 … +0.55` 扫掠 | `a zombie 0.02 columns outside RectTriggerRange must not set the mine off` |
| D | chomp 距离改回常量 1.0 | `a zombie 1.2 columns away is inside the pack's chomp window and must be swallowed` |

## 6. 已知缺口

- `support` 族仍是空实现（10 株，含 torchwood）：光环不是数值问题，留给 S3.5。
- `wall` 族 14 株里只有 `yuccaguardian` 带 Actions，且它的 `projectile` 属于射击式防守，语义待 S3.5 再定。
- 阳光的 `SpawnOffset.y` 未落地：`World::spawnSun` 只接行号不接高度，属视图层，已记在 `action_runner.cpp` 的注释里。
- `bonkchoy` 两个 `special` 槽（15 无冷却 / 60 @0.1s）按「本族自然 Type → 第一个 special」取到 15，与 content 的 15 一致；60 那一槽判为强化/植物食品变体，未采用。
