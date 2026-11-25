# 铁轨 / 砸罐子标记：从手写残留改成可重算产物

日期：2026-11-24 ｜ 轮次：t52（T53） ｜ 作用域：`tools/obb_build_content_v2.py`、`tools/contentc/rails.py`、
`content/levels/*.json`（只 `extra.vasebreaker` / `extra.minecarts` / `extra.rail` 三个键）、
`tools/tests/test_rails.py`、本文件

## 零、结论摘要

1. **原来的问题不是数字错，是重跑构建就会丢。** `tools/obb_build_content_v2.py` 只处理
   `SPECIAL_FLAGS=("IsVasebreaker","IsBeghouled","IsBowling")` 里的 `vasebreaker`，
   **完全不生成 `minecarts` / `rail`**（改动前全仓 `grep minecarts tools/` 0 命中）。
   `content/levels/*.json` 里那 10 关的标记都是手写残留，`build_levels()` 一跑就没了。
2. 现在三个标记都是 builder 的**派生产物**：`load_rail_facts()` 现场扫原版 1809 个
   `pkg_*_LevelDefinition.json`，`derive_flags()` 出单关结果，`apply_rail_flags()` 写进 `extra`。
   重建与盘上逐关一致（`content_flag_report()` → `mismatches: none`）。
3. 数字变化：`vasebreaker` 45 → **47**，`minecarts` 10 → **190**，`rail` 10 → **192**；
   撤标 7 关（kongfu 系列误标，原版既无 rail 模块也无对象），补标 189 关，
   另有 3 关的车道值被原版 `Railcarts[].Row` 纠正（原来一律手写 `[0, 2, 4]`）。
4. 32 个冒烟场景逐字段比对 **0 变化**（含改后新增标记的 `cowboy_1`），世界哈希不变。

## 一、派生规则（写进 builder，不再手填）

| 标记 | 来源 | 成立条件 |
| --- | --- | --- |
| `rail` | `rail_facts.level_verdict()` | `RailcartProperties` 有 `Railcarts`（车位 `Column`/`Row`），或 `DangerRoomRailcartDesigner` 有 `BaseRailcartCount`/`Layouts` → **functional**。decorative（只有 `Rails` 轨道点）与 unknown（只有模块名 / 空对象）一律**不出标记** |
| `minecarts` | `Railcarts[].Row` | 车道号去重升序；DangerRoom 这类「有车但没写车道」的关**只出 `rail`、不出 `minecarts`** |
| `vasebreaker` | `Modules` | 命中 `VaseBreakerArcade` / `VaseBreakerProps` / `TestVaseBreaker` 任一即置真（原来只看 `IsVasebreaker`） |

`rail` 与 `minecarts` 的判定直接复用 `tools/contentc/rails.py` 的 `object_verdict()` /
`level_verdict()`，口径与 t28 报告完全一致，没有另立一套。

## 二、改前 / 改后计数（`--content-report` 原文）

改前（手写残留）：

```
content-report: levels=1809 vasebreaker=45 minecarts=10 rail=10 derivedVasebreaker=47 derivedMinecarts=190 derivedRail=192
mismatches (first 10):
  beach_10: minecarts None -> [0, 2]
  beach_10: rail None -> True
  ...
```

改后（与派生一致）：

```
content-report: levels=1809 vasebreaker=47 minecarts=190 rail=192 derivedVasebreaker=47 derivedMinecarts=190 derivedRail=192
mismatches: none
```

逐键变化（对比 `HEAD` 的 `content/levels`，201 个文件有差异，全部落在三个键上）：

| 键 | 新增 | 删除 | 改值 |
| --- | --- | --- | --- |
| `vasebreaker` | 2（`pirate_41`、`plantagenet_18`） | 0 | 0 |
| `minecarts` | 187 | 7（`kongfu_5/10/15/20/25/30/40`） | 3 |
| `rail` | 189 | 7（同上） | 0 |

- `rail` 比 `minecarts` 多出的 2 关是 `cowboy_41`、`cowboy_42`（`pkg_0435`/`pkg_0466`）：
  原版只有 `DangerRoomRailcartDesigner` 的车数参数、没有 `Railcarts[].Row`，因此「有车无车道」。
- 3 关改值：`cowboy_6` `[0,2,4] → [2]`、`kongfu_35` `[0,2,4] → [2]`、
  `cowboy_12` `[0,2,4] → [0,1,2,3]`。原来三关共用同一串手写数字，与各自原版表格不符。
- 差分脚本核对：201 个改动文件里，除 `extra` 外**没有任何顶层键**变化，
  `extra` 内除这三个键外也没有别的键变动。

## 三、只改 `extra` 的证据

`git diff --stat -- content/levels` = `201 files changed, 1112 insertions(+), 257 deletions(-)`；
用脚本逐文件对比 `HEAD` 与盘上 JSON，得到的改动键集合恰是：

```
['extra', 'extra.minecarts', 'extra.rail', 'extra.vasebreaker']
```

`id` / `world` / `waves` / `deck` / `sun` / `flags` / `extra.package` 等全部未动。
落盘格式保持 `json.dumps(..., ensure_ascii=False, indent=1)`、无末尾换行（与 builder 一致，
`egypt_1.json` 重排后逐字节等于原文件）。

## 四、32 个冒烟场景

`python tools/engine_smoke.py --out build/engine_smoke.fresh.json` 后逐条比对
`native/generated/engine_smoke.json`：**32/32 完全相同，变化 0 条**（hash、tick、status、
spawned/killed/leaked 全等）。

其中 `cowboy_1` 是改后新增了 `minecarts: [2]` / `rail: true` 的场景，它的
`hash=0x0c35e801c317bb20`、`tick=7200`、`spawned=15` 与改前完全一致 —— 说明 headless
`--run-level` 不消费这三个标记，标记只影响关卡规则判定与展示层。

遗留（本轮不改）：`native/src/simulation.cpp:22-24` 的旧战斗预览会对 truthy 的
`boss`/`vasebreaker`/`night`/`minecarts` 直接报「does not support level rule」，
所以标记一旦为真，旧预览路径会拒绝这些关卡；`rail` 在整个 `native/src` 里仍是零引用。
这两条属于引擎接线，不在本轮作用域。

## 五、可复现性（这是本条任务的核心）

`tools/tests/test_rails.py::BuilderDerivationTest` 新增 8 个用例，其中两条是走火/走绿的成对断言：

- `test_disk_flags_are_the_derived_ones`：盘上 1809 关的三个标记与派生结果逐关相同，
  `counts` 断言 47 / 190 / 192，`mismatches == []`。
- `test_removing_the_derivation_makes_the_content_stale`：把 `builder.derive_flags` 临时换成
  返回 `{}`（等价于「删掉 builder 里的派生逻辑」），同一个 `content_flag_report()` 立刻
  报出大量 `rail` / `vasebreaker` 差异 —— 也就是说重建成「无标记」版本一定会红。
  这条对应用户要求 4，且不需要真的重写 1809 个文件就能验证。

其余用例：`test_every_original_package_has_facts`（1809 包一一对应）、
`test_bogus_kongfu_flags_are_gone`（7 关三键皆无）、
`test_decorative_and_unknown_packages_stay_unflagged`（`pkg_0853`、`pkg_1687`）、
`test_danger_room_gets_rail_without_lanes`（`cowboy_41`/`cowboy_42`）、
`test_vasebreaker_comes_from_the_module_list`（`pirate_41`、`plantagenet_18`）、
`test_module_names_are_parsed_not_character_stripped`（见下节）、
`test_builder_emits_the_same_flags_it_derives`（真的跑一遍 `build_levels()`，只在内存里，
返回 1809 关、`vasebreaker 47 / minecarts 190 / rail 192` —— 与盘上逐个相等，
证明「重跑构建会带上标记」不是只靠 `content_flag_report` 的自我印证）。

验证命令与结果：

```
python -m unittest tools.tests.test_rails -v      → Ran 28 tests, OK
python tools/contentc/rails.py --check            → exit 0（三个产物已是最新）
python tools/obb_build_content_v2.py --content-report → mismatches: none
python tools/obb_build_content_v2.py --dry-run    → levels: 1809 / worlds: 26
```

## 六、本轮顺手修掉的两个坑

1. **`PKG_DIR` 指向不存在的目录会让派生静默归零。** `tools/obb_build_content.py` 里
   `PKG_DIR = ROOT.parent / "work" / "obb_packages"` 在本机解析成
   `<repo>/work/obb_packages`，该目录**不存在**（真实原版表在仓库外
   `…/pvz_shuttle/work/obb_packages`）。第一版 `load_rail_facts()` 因此返回 0 条、
   `derived*` 全 0。现在 `obb_dir()` 先试 `PKG_DIR`，没有再退回
   `tools/contentc/rails.DEFAULT_OBB`，并在报告里打印实际使用的目录。
2. **`str.strip("RTID(")` 是按字符集剥两端。** 第一版把
   `RTID(DefaultSunDropper@LevelModules)` 解析成 `efaultSunDropper`、
   `RTID(DangerRoomIntro@…)` 成 `angerRoomIntro`、`Rails` 成 `ails`。
   现在 `_module_name()` 用 `split("RTID(",1)[1].split("@",1)[0]`，并有回归断言。
3. **同一个 `PKG_DIR` 还会让整个构建读到 0 关并清库。** `build_levels()` 原先直接调
   `base.load_all_levels()`，它只认 `base.PKG_DIR`；那个路径不存在时构建拿到 0 个关卡，
   而写盘流程是「先 `copytree` 备份、再删掉 `content/levels` 全部文件、逐个重写」——
   于是会把 1809 个关卡文件删空。现在 builder 有 `load_all_levels()`：`obb_dir()` 与
   `base.PKG_DIR` 不一致时临时改全局再恢复，`--dry-run` 实测 `levels: 1809 / worlds: 26`。
   这是本轮唯一一处「不改就会毁数据」的修复，`test_builder_emits_the_same_flags_it_derives`
   顺带把这条路径跑了一遍。

## 七、复现

```powershell
python tools/obb_build_content_v2.py --content-report   # 盘上标记 vs 原版派生
python tools/obb_build_content_v2.py --dry-run          # 构建侧是否读到 1809 关
python tools/contentc/rails.py                          # 重新生成 rails_report / candidates / 报告
python tools/contentc/rails.py --check                  # 逐字节校验三个产物
python tools/contentc/levelextra.py --check             # 关卡模块清点产物（t52 后随之更新）
python tools/engine_smoke.py --out build/engine_smoke.fresh.json
python -m unittest tools.tests.test_rails tools.tests.test_levelextra -v
```

原版表位置：`work/obb_packages`（BUILD.md 第 3 节：`python tools/obb/split_packages.py work/obb_raw work/obb_packages`）。
本报告所有计数都是现场算出来的，没有手写常数。
