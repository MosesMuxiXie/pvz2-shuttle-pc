# 商店解锁分类（`content/shop.json` → `native/generated/shop_unlock.json`）

由 `tools/contentc/shop_unlock.py` 生成。源 `content/shop.json`（`generatedAt` = 该文件 mtime 的 UTC 时间 `sha256:fdfb6e9f564d60ec`，不是「运行时刻」，所以两次生成逐字节相同）。

```
python tools/contentc/shop_unlock.py            # 写 json + 本报告
python tools/contentc/shop_unlock.py --check    # 产物是否仍与源一致（0/1）
python tools/contentc/shop_unlock.py --needle   # 复现「哪些门槛字段不存在」
```

## 0. 585 是否成立

| 口径 | 值 | 说明 |
|---|---:|---|
| `shop.json` 的 `items` 行数 | 585 | 本表 `counts.total` 就是它 |
| `shop.json` 的 `meta.total` | 585 | 与行数 一致 |
| `categories[].count` 求和 | 585 | bundles=25 / currency=20 / items=459 / seeds=81 |
| 编译出的条目 | 585 | 每行一条，无静默丢弃 |
| 缺失 id 的条目 | 0 | 源里 没有这种行 |
| 重复 id | 0 | 源里没有重复 |

**585 成立**：`items` 行数、`meta.total`、四个 tab 的 `count` 求和三者相等，所以本表不做任何数字修正。

## 1. 分类规则与命中数

规则按顺序取首个命中，命中规则写进每条的 `rawKeys`（`R01:`…`R06:`）。

| 规则 | 条件 | 类 | 命中 |
|---|---|---|---:|
| R01 | `payload.world_key` 存在 | `world_key` | 1 |
| R02 | `item_type == costume` 或 `payload.costume_id` | `costume` | 447 |
| R03 | `item_type == plant` 或 `payload.plant_id` | `seed` | 81 |
| R04 | `item_type == gameupgrade`（R01 已先摘走世界钥匙） | `upgrade` | 11 |
| R05 | `item_type in {eventenergy, pinata}` 或 `payload.setting == event_energy` 或 id 命中 `pinata\|anniversary\|_show\|lte_\|event` | `event` | 32 |
| R06 | 其余（`coin/gem/mint/sprout/bundle/action`） | `unknown` | 13 |

R01 必须排在 R04 前面：世界钥匙本身是 `item_type: gameupgrade`（`obb_worldkey.rainbowmarket`），顺序反了它会被当成普通道具强化。

## 2. 六类计数与样例

| 类 | 数量 | 样例 id |
|---|---:|---|
| `seed` | 81 | `seed_iris` |
| `upgrade` | 11 | `obb_com.popcap.pvz2.gameupgrade.seedslot.nonconsume.t1` |
| `world_key` | 1 | `obb_worldkey.rainbowmarket` |
| `costume` | 447 | `obb_Tonywrite.Costume.1` |
| `event` | 32 | `obb_com.popcap.pvz2.3rdanniversary` |
| `unknown` | 13 | `obb_action_container_product` |
| **合计** | **585** | |

## 3. `unknown` 逐条点名

六类里没有 `currency` 与 `bundle`，所以**货币充值（11 条）与礼包（2 条）进 `unknown`**，不是「忘了分类」。

| 原因（`item_type`） | 条数 | id |
|---|---:|---|
| `item_type=action` | 1 | `obb_action_container_product` |
| `item_type=bundle` | 1 | `obb_com.pvz2.bundle.starreed` |
| `item_type=coin` | 2 | `obb_com.popcap.pvz2.coins.3000.consume`、`obb_com.popcap.pvz2.coins.30000.consume` |
| `item_type=gem` | 2 | `obb_com.popcap.pvz2.gems.1.consume`、`obb_com.popcap.pvz2.gems.10.consume` |
| `item_type=mint` | 4 | `obb_com.popcap.pvz2.mints.1.consume`、`obb_com.popcap.pvz2.mints.1.consume2`、`obb_com.popcap.pvz2.mints.10.consume`、`obb_com.popcap.pvz2.mints.10.consume2` |
| `item_type=sprout` | 3 | `obb_com.popcap.pvz2.sprout.10.consume`、`obb_com.popcap.pvz2.sprout.25.consume`、`obb_com.popcap.pvz2.sprout.5.consume` |

合计 `13` 条，与 `counts.unknownCategory` 相等。

## 4. `unlock` 三格的语义与由来

`content/shop.json` **没有任何购买门槛字段**，所以三格只填数据能支撑的部分，每格来源写进 `rawKeys`。

| 字段 | 取值 | 来源 | 命中 |
|---|---|---|---:|
| `unlock.world` | 世界 id 或 null | `payload.world_key`（经 `rainbowmarket→lunarrainbowmarket` 别名） 或 id/sku 里带完整世界 token | 2 |
| `unlock.coins` | 整数或 null | `currency == coin` 时的 `price` | 100 |
| `unlock.stars` | 恒为 null | 源里没有星级门槛（见 §5） | 0 |

`unlock.kind` 由三格是否为空推导：`none` / `world` / `stars` / `coins` / `mixed`，只有「这一行本身读不出来」（缺 id、价格非整数）才是 `unknown`。分布：`none` 484、`world` 1、`stars` 0、`coins` 99、`mixed` 1、`unknown` 0。

- `obb_com.popcap.pvz2.pinata.egypt.consume.tutorial` → world `egypt`、coins —、kind `world`
- `obb_worldkey.rainbowmarket` → world `lunarrainbowmarket`、coins 2026、kind `mixed`

世界钥匙 `obb_worldkey.rainbowmarket` 的 `world` 是 `lunarrainbowmarket`（`content/worldmap.json` 里没有 `rainbowmarket` 这个 id），这条别名来自 `tools/contentc/worlds.py` 的 `ALIASES`，不是猜的。

## 5. 为什么 `stars` 全是 null

`--needle` 在 `585` 条商品上找门槛类键名：

| 键名 | 命中 |
|---|---:|
| `gated` | 0（不存在） |
| `level` | 0（不存在） |
| `locked` | 0（不存在） |
| `prerequisite` | 0（不存在） |
| `requirement` | 0（不存在） |
| `requires` | 0（不存在） |
| `star` | 0（不存在） |
| `stars` | 0（不存在） |
| `unlock` | 0（不存在） |
| `world` | 0（不存在） |

`content/stars.json` 是**每关的三星任务定义**（键形如 `frontyard_1`，值是 `beat/mowers/kill` 三条任务），不是商店门槛；`content/worldmap.json` 的 `unlock_cost` 每个世界都是 `1`（钥匙数），也不带星级。因此本表 `unlock.stars` 一律 null，`kind` 永远不会是 `stars`——需要星级门槛时必须先在导出侧加字段。

## 6. 价格与货币

`price.currency` 只允许 `coins | gems | none`，而源里有第四种货币 `mint`（金金茶券，10 条）。枚举装不下，这 10 条写成 `currency: none`、`amount: null`，并把真相留在 `rawKeys` 的 `currency=mint` 与 `counts.mintPriced` 里。

| 币种（源） | 条数 | 本表 `price.currency` |
|---|---:|---|
| `coin` | 100 | `coins` |
| `gem` | 469 | `gems` |
| `free` | 16 | `none` |
| `mint` | 10 | `none`（枚举缺值，已计入 `priceCurrencies.none`） |

mint 计价的具体条目：`obb_com.popcap.pvz2.suntower`、`obb_com.popcap.pvz2.suntower5`、`obb_com.pvz2.plant.CheeseStrawberry`、`obb_com.pvz2.plant.SucculentGrape`、`obb_com.pvz2.plant.holonut`、`obb_com.pvz2.plant.jasmine`、`obb_com.pvz2.plant.tombtangler`、`obb_lte_energy_jinjin_green`、`obb_lte_energy_jinjin_pink`、`obb_lte_energy_jinjin_red`。

## 7. 复现

```
python tools/contentc/shop_unlock.py --needle      # 门槛键名 0 命中
python tools/contentc/shop_unlock.py               # 重写 json + 本报告
python tools/contentc/shop_unlock.py --check       # 逐字节比对，过期即非零退出
python -m unittest tools.tests.test_shop_unlock -v
```

本报告里的每个数字都可以用上面第二、三条命令重新得到；分类计数在 json 的 `counts.byCategory`，逐条依据在 `items[].rawKeys`。

## 8. 诚实边界

1. **没有购买前置条件可读**：源里没有 `unlock/requires/stars` 之类的字段，本表的 `unlock` 只表达「绑定世界」与「金币门槛」，不是完整的商店解锁逻辑。
2. **`unknown` 是投影缺口不是数据错误**：货币充值 11 条、礼包 2 条在六类里无处可放。要消除它们，得先在 `content/shop.json` 或这套六类里加一个 `currency`/`bundle` 类。
3. **`mint` 货币装不进 `coins|gems|none`**：10 条按 `none` 输出，靠 `rawKeys` 区分。
4. **`stars` 恒 null**：见 §5，不是漏读而是源里没有。
5. **`generatedAt` 是源 mtime**：为了让两次生成逐字节相同，这是刻意的取舍；如果想让产物随导出时间变化，需要另加一个非确定性字段并放弃字节比对。

