# 铁轨语义与砸罐子缺口（证据轮，不改 content）

**结论：三个标记已与原版对齐，且由 `tools/obb_build_content_v2.py` 现场派生。** 原版 204 关带 rail 模块或 rail 对象，其中 192 关有明确车位参数（functional）、6 关只有轨道点（decorative）、6 关拿不准（unknown）；客户端标了 192 关，误标 0、漏标 0；`vasebreaker` 47/47，差集 0。

## 零、口径（与他轮对齐，先看这节）

1. **关卡身份键 = `StageModule` 的 stage 名 + `LevelNumber`。** 原版每个 `pkg_*_LevelDefinition.json` 通常只有 1 个 `LevelDefinition` 且**没有 alias**，拿客户端关卡 id（如 `pirate_41`）在原表里字面搜索会 0 命中；本工具一律用 package 关联，再回读 stage 名与关卡号核对。
   但这对键**不唯一**：1809 个原版文件只有 1385 个不同组合，246 个组合重复、多出 424 个文件（例如 `(DarkStage, 1)` 有 20 个 package、`(DinoStage, 1)` 14 个、`(BeachStage, 1)` 12 个），所以按 (stage, LevelNumber) 反查必须再叠加 package —— 客户端 `extra.package` 是唯一可靠锚点。实证：`kongfu_30` 的 `extra` 是 `pkg_1415 / KongfuStage / level_number 5`，与 `kongfu_5` 的 `pkg_1390 / KongfuStage / 5` 同 stage 同号但是两个不同 package。
2. **Boss 关按 `ZombossBattle` 模块统计**：原版 71 关，与客户端的 71 关对齐；按 `*BossStage` 名只有 18 关，因为混合关（Boss + 砸罐子/其它玩法）的 stage 名不带 Boss 或只对应一个模块。

## 一、判据与为什么单开一个工具

判据（按对象实测字段，字段名以数据为准）：

- `RailcartProperties.Railcarts` 非空（每项含 `Column`/`Row`）→ **functional**；
- `RailcartProperties` 只有 `Rails`（`Column`/`RowStart`/`RowEnd` 路径点）→ **decorative**；
- `DangerRoomRailcartDesigner` 带 `BaseRailcartCount`/`MaxGeneratedRailcarts`/`Layouts` → **functional**；
- 空对象（如 `RailcartTutorialIntroProperties`）→ **decorative**（只有入场标记）；
- 只有模块名没有对象，或对象既无车也无轨 → **unknown**（附探针）。

没有改 `tools/contentc/levelextra.py`：t22 的 `level_modules.json` 与评审文档被 `--check` 逐字节锁定，是别的任务在用的「关卡模块清单」；铁轨语义是关卡内对象的粒度，塞进去会让那份产物被动变化。所以新增 `tools/contentc/rails.py`，只读同一批输入，不碰 t22 的输出。

## 二、结论表一：功能矿车关卡（functional）

| 世界 | 功能矿车关卡数 |
|---|---|
| beach | 6 |
| carnival | 17 |
| chinesegarden | 4 |
| cowboy | 39 |
| dark | 1 |
| dino | 4 |
| egypt | 19 |
| eighties | 8 |
| fairy | 5 |
| frontyard | 16 |
| future | 5 |
| heian | 2 |
| iceage | 3 |
| kongfu | 17 |
| losantosvice | 1 |
| lostcity | 5 |
| lunarrainbowmarket | 13 |
| mausoleum | 1 |
| memorytour | 2 |
| modern | 2 |
| pirate | 12 |
| plantagenet | 4 |
| renai | 2 |
| sky | 2 |
| steam | 2 |
| **合计** | **192** |

抽样（前 20 关，括号内为车位/轨道数）：

- `beach_8`（2 车 / 2 轨）—— 模块 无（对象内嵌）
- `beach_9`（2 车 / 2 轨）—— 模块 无（对象内嵌）
- `beach_10`（2 车 / 2 轨）—— 模块 无（对象内嵌）
- `beach_11`（3 车 / 3 轨）—— 模块 无（对象内嵌）
- `beach_16`（1 车 / 1 轨）—— 模块 无（对象内嵌）
- `beach_37`（2 车 / 2 轨）—— 模块 `Rails`
- `carnival_10`（3 车 / 3 轨）—— 模块 `Rails`
- `carnival_17`（9 车 / 9 轨）—— 模块 `Rails`
- `carnival_18`（4 车 / 4 轨）—— 模块 `Rails`
- `carnival_23`（3 车 / 3 轨）—— 模块 `Rails`
- `carnival_27`（3 车 / 3 轨）—— 模块 `Rails`
- `carnival_46`（3 车 / 2 轨）—— 模块 `Railcart`
- `carnival_51`（1 车 / 3 轨）—— 模块 `Rails`
- `carnival_62`（2 车 / 2 轨）—— 模块 `CowboyRails`
- `carnival_73`（2 车 / 2 轨）—— 模块 `CowboyRails`
- `carnival_75`（4 车 / 4 轨）—— 模块 `CowboyRails`
- `carnival_79`（7 车 / 7 轨）—— 模块 `CowboyRails`
- `carnival_80`（4 车 / 4 轨）—— 模块 `Rails`
- `carnival_81`（1 车 / 1 轨）—— 模块 `Rails`
- `carnival_84`（5 车 / 5 轨）—— 模块 `CowboyRails`

## 三、结论表二：装饰铁轨关卡（decorative）

| 关卡 | 世界 | 对象类 | 轨道点数 |
|---|---|---|---|
| `egypt_46` | egypt | RailcartProperties | 3 |
| `frontyard_98` | frontyard | RailcartProperties | 1 |
| `frontyard_143` | frontyard | RailcartProperties | 28 |
| `lunarrainbowmarket_93` | lunarrainbowmarket | RailcartProperties | 3 |
| `muji_27` | muji | RailcartProperties | 15 |
| `pirate_67` | pirate | RailcartProperties | 19 |

这些关卡的原版文件里搜不到任何 `*Cart*` 记号（没有波次生成矿车的痕迹），轨道只是装饰；另有 1 个 `RailcartTutorialIntroProperties` 空对象挂在 `cowboy_1` 上，该关本身有车位，所以关卡判为 functional。

## 四、结论表三：拿不准（unknown）

| 关卡 | 世界 | 对象类 | 缺什么 |
|---|---|---|---|
| `fairy_31` | fairy | —（只有模块名） | 只有模块名，原版该关没有 rail 对象可读 |
| `future_66` | future | —（只有模块名） | 只有模块名，原版该关没有 rail 对象可读 |
| `future_69` | future | —（只有模块名） | 只有模块名，原版该关没有 rail 对象可读 |
| `future_70` | future | —（只有模块名） | 只有模块名，原版该关没有 rail 对象可读 |
| `iceage_65` | iceage | `RailcartProperties` | 对象里既没有 `Railcarts` 也没有 `Rails`，没有任何位置参数 |
| `plantagenet_47` | plantagenet | —（只有模块名） | 只有模块名，原版该关没有 rail 对象可读 |

## 五、客户端标记对账

- 客户端标了 `minecarts` 的关卡：192 关；其中原版确有车位参数的 192 关，原版完全没有 rail 数据的 0 关（``）。
- 原版有车位、客户端没标：**0 关**（完整名单见 `native/generated/content_fix_candidates.json` 的 `minecarts`）。
- 模块名与对象错配：只有模块名、没有对应对象的 5 关（`fairy_31`、`future_66`、`future_69`、`future_70`、`plantagenet_47`）；有对象、但 `Modules` 里没有 rail 模块名的 19 关（`beach_8`、`beach_9`、`beach_10`、`beach_11`、`beach_16`、`cowboy_20`、`cowboy_41`、`cowboy_42`、`egypt_19`、`frontyard_143`、`future_54`、`iceage_65`、`kongfu_44`、`lunarrainbowmarket_93`、`memorytour_4`、`muji_27`、`pirate_67`、`plantagenet_40`、`plantagenet_45`）。

撤标证据：（无）——原版没有 rail 数据的关卡都没有被标（t52 已把 `rail`/`minecarts` 改成派生值）。

## 六、砸罐子标记（pirate_41、plantagenet_18）

原版带 VaseBreaker 模块的关卡 47 关，客户端标了 `vasebreaker` 的 47 关；差集 0 关。

证据：两关的原版 `Modules` 都含 `VaseBreakerArcade` + `VaseBreakerProps`（花瓶布局参数在同名对象里）。**这里只关砸罐子标记，不存在玩法标签错位**：`pirate_41` 的 stage 是 `PirateBossStage`、LevelNumber 26，原版 `Modules` 同时含 `ZombossIntro` 与 `ZombossBattle`，所以客户端 `boss: true` / `boss_zombie: zomboss` 是对的（Boss + 砸罐子混合关）；`plantagenet_18`（`PlantagenetDaylightDMGStage` #19）原版没有 Boss 模块，客户端也没有 boss 标记，同样正确。
t52 已把 `vasebreaker` 写成 builder 的派生产物（原版 Modules 命中即置真），两关都已补上，boss 字段未动。

## 七、两件遗留事项的处置建议

1. **4 关原版没有 `Modules`**（`egypt_50`、`frontyard_86`、`frontyard_87`、`frontyard_88`）：按「无模块关卡」处理，S7 加载器遇到空模块表直接跳过模块解析、只保留关卡本体，不要假设每关都有波次管理器。
2. **13 关 `night` 与 `stage` 名冲突**：以原版 `*StageProperties` 为准，客户端 `night` 只当提示位；下一轮加一个校验器，把冲突写进报告而不是静默改正。

## 八、候选（给下一轮改 content，本任务不落 content）

- 已无候选：`vasebreaker_add` / `minecarts` / `minecarts_remove` 全为空 —— t52 已把三个标记改成 `tools/obb_build_content_v2.py` 的派生产物，重跑构建不会丢。

## 九、复现

```powershell
python tools/contentc/rails.py           # 重新生成 JSON + 本报告
python tools/contentc/rails.py --check   # 逐字节校验三个产物
python -m unittest tools.tests.test_rails -v
```

所有计数都由 `work/obb_packages` 与原 `content/levels` 现场计算，没有手写常数；`rails_report.json` 里保留了逐关的对象、字段与证据计数，报告中的表格可直接回查。
