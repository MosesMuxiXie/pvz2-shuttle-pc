# B5 商店屏（t97）实施与验证报告

> 任务：把 `--shop` 的 CLI 输出变成一个 1280×720 的商店屏，585 行里 `buyable` 的 72 行可见可买，
> 不可买的行必须写明**具体原因**而不是画成灰色。只读代码与跑测试之外，本轮的写入范围是
> `native/src/shop_layout.{hpp,cpp}`、`native/src/shop_view.{hpp,cpp}`、`native/tests/shop_ui_test.cpp`、
> `native/CMakeLists.txt`（只加两个测试目标）与本报告。
>
> **没有**改 `native/src/main.cpp`、`native/src/menu_view.cpp`，也没有把两个源文件加进
> `PvZ2SHUTTLE` 的源列表——本轮多人同时改那两个文件，按队长的要求，菜单项与 `--shop-screen`
> 分发由队长接线，我只交纯入口（§5、§10）。

## 0. 结论

| 项 | 结果 |
| --- | --- |
| 五个分页 | `buyable 72 / coin 100 / gem 469 / mint 10 / free 6`，后四个相加 **= 585**（划分，不重不漏） |
| 可买 72 的构成 | `costume 45 / plant 21 / gameupgrade 4 / gem 2`（按行自己的 `itemType`） |
| 全库 585 行的拒绝文案 | **10 个桶，合计 585**；`(buyable) 72` + 9 条具体句子（§3） |
| 文案与 `purchase()` 是否一致 | **585/585 行逐条相同**（`testRefusalSentencesMatchPurchase`，用的是真实的 `purchase()` 副本存档） |
| 购买 | 走同一个 `pvz::purchase()`；只在给了 `--progress` 时写回，预览从不落盘（字节比对） |
| 确定性 | 同一状态渲染两次字节相同；重跑生成的 PNG 与上一轮 **sha256 一致** |
| audit 测试 | `ctest -R ^shop_ui$` → **1/1 Passed**（Test #36，0.37 s） |
| desktop 测试 | `ctest -R ^shop_render$` → **1/1 Passed**（Test #50，1.66 s） |
| 全量 audit 门禁 | 36 项 **35 绿 1 红**：红的 `rewards`（`all 293 unlock_plant rows must land, got 244`）与商店无关，我不改它 |
| 截图 | 两张 1280×720：`build/t97/shots/shop-buyable.png` 78,538 B、`shop-gem.png` 87,131 B（§7） |

**一句话**：屏幕能显示 585 行、能买那 72 行、能对每一行说出它为什么不能买；说不出的地方
（宝石/薄荷币的支付、服务器结算）在屏幕上明说，没有编造。

## 1. 落地文件

| 文件 | sha256 前 12 | 大小 | 行数 | 说明 |
| --- | --- | --- | --- | --- |
| `native/src/shop_layout.hpp` | `6DBA405C8F88` | 4,238 B | 87 | 数据半：分页、行、拒绝句、JSON，无 SDL |
| `native/src/shop_layout.cpp` | `2AC0AE2E2291` | 7,200 B | 158 | 纯函数实现 |
| `native/src/shop_view.hpp` | `0B43A108C647` | 2,678 B | 51 | 绘制半：两个入口 + options |
| `native/src/shop_view.cpp` | `2DCA492C66E7` | 17,250 B | 351 | SDL3 绘制、按键、购买回执 |
| `native/tests/shop_ui_test.cpp` | `77489DEC1281` | 21,160 B | 408 | 8 段 audit + 1 段 desktop |
| `native/CMakeLists.txt` | `14638E4A3198` | 38,118 B | 562 | 只加了 `shop_ui_test` 与 `shop_render_test` 两个目标 |

`git status` 里这些都是新增/修改的未提交内容；HEAD 已被队长推进到 `784e7d6`，本报告写作时
`native/generated/**`、`content/plants.json`、几个 `docs/` 也有别人的改动，**不属于本轮**。

## 2. 分页口径（Tab / q / e）

`shopTabs()` 是写死的五页，顺序即绘制顺序：

| # | key | 标签 | 行数 | 规则 |
| --- | --- | --- | --- | --- |
| 0 | `buyable` | 可购买 | **72** | `implemented && payloadModelled && unlock ∉ {stars, unknown} && (免费 或 金币价 > 0)`，与 `Shop::buyable_`（`native/src/shop.cpp:285-293`）逐字同义 |
| 1 | `coin` | 金币 | 100 | `currency == "coin"` |
| 2 | `gem` | 宝石 | 469 | `currency == "gem"` |
| 3 | `mint` | 薄荷币 | 10 | `currency == "mint"` |
| 4 | `free` | 免费 | 6 | `currency == "free"` |

**为什么这样分**：`buyable` 是「视图」，后四页是「按币种划分」。100 + 469 + 10 + 6 = 585，
所以屏幕上 585 行全部可达、且不重复出现；`testTabPartition` 把这两条都钉住了
（`tabSizes["coin"] == 100`、`gem == 469`、`mint == 10`、`free == 6`、四者之和 == `shop.size()`）。

**每页 8 行**：`kShopPageSize = 8`（720 px 里钱包条与按键提示之间刚好放 8 行 × 42 px）。
`shopLayout()` 把 `cursor` 夹进当前页（`std::clamp`），`pages = (total + 7) / 8`，空页也算 1 页。

## 3. 可买 72 的分布，以及全库的拒绝文案直方图

按行自己的 `itemType`（`shopSummaryJson()["buyableByType"]`）：

```
{"costume": 45, "plant": 21, "gameupgrade": 4, "gem": 2}
```

按币种：**金币 71 + 免费 1**（免费那行是 `obb_Tonywrite.Costume.370`，`implemented=true`，`price=0`）。
这一点是本轮修过的一个错：最初把 `buyable` 页写成「`currency == "coin"` 且 …」，得到 71 行、
比 `Shop::buyable()` 少 1——因为 `buyable_` 的 `spendable` 定义包含免费行
（`item.currency == "free" || (item.currency == "coin" && item.price > 0)`）。现在两处同义，
`testTabPartition` 直接断言 `rows.size() == shop().buyable()`。

全库 585 行按「它现在会得到的句子」分桶（`shopSummaryJson()["reasons"]`，合计 585）：

| 桶 | 行数 | 说明 |
| --- | --- | --- |
| `(buyable)` | 72 | 现在按 Enter 就会成功 |
| `currency gem is not modelled yet` | 433 | 宝石计价；本客户端没有宝石钱包的扣款通路 |
| `not implemented in this client` | 58 | 行本身标记未实装 |
| `currency mint is not modelled yet` | 6 | 薄荷币计价 |
| `payload setting is not modelled yet` | 5 | 产物是服务器侧开关（`mints`/`event_energy`/`sprouts`） |
| `payload seed_pack is not modelled yet` | 4 | 产物是种子包（金币定价的行） |
| `payload sun_shovel is not modelled yet` | 3 | 阳光铲 |
| `payload sun_start_bonus is not modelled yet` | 2 | 开局阳光加成 |
| `payload collectible is not modelled yet` | 1 | 收藏品 |
| `payload mower_charges is not modelled yet` | 1 | 割草机次数 |

注意 `gem` 有 469 行、但上面只有 433 行落在「币种不支持」：另外 36 行在 `purchase()` 的顺序里
**更早就被拒**（未实装/产物不可发放），屏幕沿用同一顺序，所以它显示的是那条更早、更具体的原因。
`mint` 同理（10 → 6）。这就是「照抄顺序」的实际效果：屏幕上永远是 `purchase()` 会给的那句话。

## 4. 拒绝文案对账

`shopRefusalReason()`（`shop_layout.cpp`）复制 `purchase()`（`native/src/shop.cpp:319-380`）的判断
顺序与措辞，一个字都没有重写：

| # | 条件 | 句子 |
| --- | --- | --- |
| 1 | 目录里没有这个 id | `unknown item <id>` |
| 2 | `one_time` 且已购买 | `already owned` |
| 3 | `!implemented` | `not implemented in this client` |
| 4 | `unlock == stars` | `star-gated: needs <n> stars` |
| 5 | `unlock == unknown` | `unlock kind is unknown for this row` |
| 6 | 金币行价格 ≤ 0 | `item has no coin price` |
| 7 | 其它币种 | `currency <cur> is not modelled yet` |
| 8 | 产物整行不可交付 | `row grants nothing this client models` |
| 9 | 产物部分键不可交付 | `payload <keys> is not modelled yet` |
| 10 | 余额不足 | `not enough coins (need <n>, have <m>)` |
| — | 都不成立 | 空串（可买） |

**对账不是靠读代码看出来的**：`testRefusalSentencesMatchPurchase`（第 6 段）对全部 585 行，把
存档复制一份，先取 `shopRefusalReason(row, progress)`，再真的调一次 `purchase(item, copy)`：
- 句子非空 ⇒ `purchase()` 必须失败，且 `error.what()` **以同一句结尾**；
- 句子为空 ⇒ `purchase()` 必须成功。

出厂数据里没有星门/未知门槛/未实装的行（`unlock.stars` 全库 0 条），所以这三句用合成的
`ShopItem` 单独钉住（同一段的末尾），否则它们永远没有绊线。

## 5. 入口与 JSON（给队长接线的形状）

```cpp
// 预览：画 frames 帧（0 = 只算 JSON）、可选写快照，永不写存档
pvz::Json pvz::renderShopHeadless(const std::filesystem::path& contentRoot,
                                  const std::filesystem::path& progressFile, int frames,
                                  const std::filesystem::path& snapshot,
                                  int tab = 0, int cursor = 0);

// 交互：↑↓ 移动，←→/Tab/q/e 切页，Enter 购买，Esc 退出；只有给了 progressFile 才写回
struct pvz::ShopScreenOptions {
    std::filesystem::path contentRoot, progressFile, assetRoot, snapshot;
    int frames = 0, tab = 0, cursor = 0;
};
pvz::Json pvz::runShop(const pvz::ShopScreenOptions& options);
```

`renderShopHeadless()` 返回（键集由 `testJsonShape` 钉住，`items` 只含当前页）：

```json
{"screen":"shop","coins":5000,"gems":4,"buyable":72,"rows":585,
 "tab":"buyable","tabIndex":0,"tabLabel":"可购买","cursor":0,"page":0,"pages":9,
 "summary":{"rows":585,"buyable":72,"unmodelledCurrency":479,"currencyPartition":585,
            "tabSizes":{...},"buyableByType":{...},"reasons":{...}},
 "items":[{"id":"seed_iris","label":"种子包·鸢尾花","price":500,"currency":"coin",
           "affordable":true,"owned":false,"unmodelled":false,"reason":"","selected":true}, ...]}
```

`runShop()` 在同样的字段上加 `lastResult`（最后一次 Enter 的回执或 `null`）。行内的 `reason` 与
`affordable` 互斥：`affordable == true` 时 `reason` 必为空——这条也有断言。

## 6. 测试

`native/tests/shop_ui_test.cpp`，9 段（8 段 audit + 1 段 desktop）：

| # | 段 | 钉住什么 |
| --- | --- | --- |
| 1 | `testTabPartition` | 五页大小、后四页和为 585、`buyable` 页 == `Shop::buyable()`（72）、每行币种为 coin/free |
| 2 | `testBuyableTabIsAffordable` | 72 行全部 `affordable`、`reason` 为空；72 行逐个能在副本上买成 |
| 3 | `testPaging` | 8/页、`pages` 计算、末页不满、`cursor` 上下夹紧、切页后页号跟随 |
| 4 | `testPurchaseFlipsOwned` | 买一次：coins 减少、`owned` 变 true、`purchases` 增加；再买同一条 → `already owned` |
| 5 | `testNotEnoughCoins` | 余额 100 买 500 → `not enough coins (need 500, have 100)`，两个数字都在句子里 |
| 6 | `testRefusalSentencesMatchPurchase` | 585 行逐条对账（§4），外加三条合成行的星门/未知门槛/未实装句子 |
| 7 | `testPreviewDoesNotWriteSave` | 预览前后存档**逐字节**相同、大小相同 |
| 8 | `testRendersAreDeterministic` | 同一状态渲染两次，JSON 字符串相同 |
| 9 | `testScreenshots` | 两张 PNG：1280×720、> 10 KB、不同页像素不同、缺字体抛错且消息含 `font_zh.ttc` |

跑法（两条都在 ctest 里，`WORKING_DIRECTORY` 已是仓库根）：

```
shop_ui_test content native/generated/shop_unlock.json <temp>        # audit，无SDL
shop_render_test content native/generated/shop_unlock.json <temp>    # desktop，写两张png
```

实测输出（本机，exe 直跑）：

```
tabs: {"buyable":72,"coin":100,"free":6,"gem":469,"mint":10}  buyable by type: {"costume":45,"gameupgrade":4,"gem":2,"plant":21}
reasons: {"(buyable)":72,"currency gem is not modelled yet":433,"currency mint is not modelled yet":6,
          "not implemented in this client":58,"payload collectible is not modelled yet":1,
          "payload mower_charges is not modelled yet":1,"payload seed_pack is not modelled yet":4,
          "payload setting is not modelled yet":5,"payload sun_shovel is not modelled yet":3,
          "payload sun_start_bonus is not modelled yet":2}
shop ui tests passed            # audit
shop ui render tests passed     # desktop
```

`ctest`：

```
$ ctest --test-dir C:\pvzbuild\shopui1  -C Release -R '^shop_ui$'     → 1/1 Test #36 shop_ui     Passed 0.37s
$ ctest --test-dir C:\pvzbuild\shopui1d -C Release -R '^shop_render$' → 1/1 Test #50 shop_render Passed 1.66s
```

完整 audit 门禁 `tools/build_native.ps1 -AuditOnly -BuildDir C:\pvzbuild\shopui1`：36 项里
**35 绿、1 红**——`rewards`（`rewards test failed: all 293 unlock_plant rows must land, got 244`），
与商店屏无关，属于别人正在做的奖励接线；`shop`、`shop_ui` 均 Passed。

## 7. 截图

| 文件 | 尺寸 | 大小 | sha256（前 32） |
| --- | --- | --- | --- |
| `build/t97/shots/shop-buyable.png` | 1280×720 | 78,538 B | `5579D7CA713538F093B01C82EE902561` |
| `build/t97/shots/shop-gem.png` | 1280×720 | 87,131 B | `181FA9408D0707DF42E49044A2BD547C` |

- **默认页（可购买，cursor=0）**：标题「商店」，右上「金币 5000 / 宝石 4」，第一页 8 行
  种子包（`种子包·鸢尾花 500 coin` …），右侧详情给出名称、id、价格与「现在可以购买」，
  底部按键提示 + 两行口径说明：「宝石与薄荷币由服务器结算，本客户端不能支付；不可购买的行
  都会写明原因」「目录 585 行 · 可购买 72 行」。
- **宝石页（tab=2，cursor=0）**：469 行里的第一页，价格后缀是原样的 `gem`（与 CLI 一致，不
  翻译币种代码），每一行第二行是红字「不可购买」，右侧写「现在不能购买 / 原因 /
  `currency gem is not modelled yet`」——这正是要求 ③ 的「不许只画灰」。
- 两次运行生成的 PNG **sha256 与上一轮完全相同**，说明绘制没有隐藏的时间/随机来源。

## 8. 未做 / 语义边界（都在屏幕上明说，不假装能做）

1. **宝石与薄荷币仍然不能花**：469 行宝石、10 行薄荷币全部拒绝，句子是
   `currency <cur> is not modelled yet`。本轮只画、不加钱包——`unmodelledCurrency 479` 是
   `COMPLETENESS.md:428/451/455`、`PARITY_BASELINE.md:341`、`PROGRESS.md:57` 写死的数字（t76 的结论）。
2. **服务器结算的产物不落地**：`setting`/`collectible`/`mower_charges` 等 16 行按
   `payload … is not modelled yet` 拒绝，屏幕照抄。
3. **价格只按整数显示**：`Shop` 的 `number()` 把 double 截断成 int（t36 M6 记录过），出厂数据里
   没有小数价，所以不显示不存在的精度。
4. **没有限时/折扣/刷新的概念**：出厂数据没有这些字段，屏幕不编。
5. **没有滚轮与拖拽**：只有键盘（↑↓/PgUp/PgDn/Tab/←→/q/e/Enter/Esc），一页 8 行。

## 9. 复现命令

```powershell
# audit（无 SDL）
pwsh tools\build_native.ps1 -AuditOnly -BuildDir C:\pvzbuild\shopui1
ctest --test-dir C:\pvzbuild\shopui1 -C Release -R '^shop_ui$'

# desktop（有 SDL，出两张图）
pwsh tools\build_native.ps1 -Desktop ON -BuildDir C:\pvzbuild\shopui1d
ctest --test-dir C:\pvzbuild\shopui1d -C Release -R '^shop_render$'
```

## 10. 交给队长的接线（三处，都在你的写入范围内）

1. **源文件**：把 `src/shop_layout.cpp` 与 `src/shop_view.cpp` 加进 `pvz_launcher`
   （`native/CMakeLists.txt` 的 `add_library(pvz_launcher …)` 列表），或直接加进 `PvZ2SHUTTLE`。
   桌面测试目标是自带这两个源 + `src/text.cpp` 编译的，**不依赖** `pvz_launcher`，所以那条
   列表怎么排都不会影响测试。
2. **`main.cpp`**：`--shop-screen` 走 `pvz::renderShopHeadless(content, progress, frames, snapshot, tab, cursor)`，
   交互模式走 `pvz::runShop(ShopScreenOptions{…})`。两者都只返回 JSON，打印由你决定。
3. **`menu_view.cpp`**：加一项「商店」，选中时返回字符串 `shop`（与 `achievements`/`daily` 同一套）。

字体查找：`assetRoot` 留空时按 `PVZ_ASSET_ROOT` → 向上三层找 `assets/ui/font_zh.ttc` 或
`PvZ2SHUTTLE/assets/ui/font_zh.ttc`，本机命中的是后者。
