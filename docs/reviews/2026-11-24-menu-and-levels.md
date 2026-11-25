# S4 主菜单 + 关卡列表两屏（t41）

2026-11-24。计划条目 `docs/superpowers/plans/2026-11-24-s3-s5-completion.md` 的 T39。

这次只做链路里缺的两端：主菜单与关卡列表。世界地图屏（`--worldmap-screen`）之前已经能画，
但它回车之后没有任何地方可去 —— 「世界地图 → 选关 → 开战」这条链条断在第二段。

## 交付

| 文件 | 作用 |
| --- | --- |
| `native/src/menu_view.{hpp,cpp}` | 主菜单：继续游戏 / 世界地图 / 退出 |
| `native/src/level_select_view.{hpp,cpp}` | 关卡列表：按世界过滤、星数、是否通关、选中返回关卡 id |
| `native/src/main.cpp` | `--menu`、`--level-select` 两条分支 + help 两行（其余未动） |
| `native/tests/menu_render_test.cpp` | 主菜单渲染测试 |
| `native/tests/level_select_render_test.cpp` | 关卡列表渲染测试 |
| `native/CMakeLists.txt` | `pvz_launcher` 两个源文件、`menu_render` / `level_select` 两个 ctest |
| `docs/media/s4-menu.png`, `s4-level-select.png` | 两屏实拍 |

## CLI 实测

```
$ PvZ2SHUTTLE --menu content --assets <assets> --snapshot docs/media/s4-menu.png --frames 2
{"choice":"worldmap"}

$ PvZ2SHUTTLE --level-select content --world frontyard --assets <assets> \
      --snapshot docs/media/s4-level-select.png --frames 2
{"cleared":0,"levels":175,"selected":"frontyard_1","world":"frontyard"}
```

`--menu` 的 `choice` 是 `continue` / `worldmap` / `quit` 三者之一；headless 时它等于「回车当下
会选中的那一项」，也就是把「人按回车」这件事交给调用方。`--level-select` 的 `selected` 就是
`catalog.levels` 里该行的关卡 id，可直接喂给 `--run-level` 或 `--play`。

两点使用约束：

* 两屏都需要中文字体，`--assets` 指向仓库外的 `PvZ2SHUTTLE/assets`。省略时按
  `current_path()/PvZ2SHUTTLE/assets`、`current_path()/assets` 两个候选查找，从仓库根跑时都不命中，
  于是得到 `error: ui/font_zh.ttc: cannot open the Chinese font` —— 这条路径要显式给。
* `--frames 0` 走真实窗口，命令行下会等用户按键；非交互场景一律 `--frames > 0`。

## 两屏

主菜单 1280×720，顶栏 76 px：左边标题「植物大战僵尸 2 · SHUTTLE 复刻」与「S4 主菜单 · 回车确认 ·
Esc 退出」，右边是 `★ 星数　钥匙 k　已通关 m 关`。三个条目固定 480×88、间距 112，从 (400, 232) 开始。

* 「继续游戏」只有在存档里有**尝试记录**时才可选（`progress.levels` 非空）。只有钥匙和金币的存档
  不算「可以继续」，所以那一条画成禁用态，并在右侧写「没有可继续的存档」。
* 光标落在第一个可用项：新存档落在「世界地图」，玩过的存档落在「继续游戏」。
* `↑↓` 跳过禁用项，`Enter` 确认，`Esc` 直接退出。

关卡列表：左列 14 行（x=80、宽 720、行高 32、步长 36，从 y=120 起），每行 `#序号` + 关卡 id +
星数 + `已通关/未通关`；右侧 400×500 详情面板写 id、世界与序号、标题、星数、通关状态和
「回车开始这一关」。列表按关卡自己的 `index` 排序（世界播放顺序），再按 id 兜底，所以
`frontyard_1` 一定在第一行。`PgUp/PgDn` 翻页（一次一屏），窗口偏移 `clamp(selected - 7, 0, n-14)`
保证光标不出视野；空世界画「该世界没有关卡：<id>」并让 `selected` 为空。

标题是这屏唯一的自由文本（`Your House - Chapter 1 - Day 1` 在 352 px 的面板里放不下），
所以只有它按宽度折行，最多两行；其余都是数字或 id。

## 验证

| 门禁 | 命令 | 结果 |
| --- | --- | --- |
| audit | `pwsh -File tools/build_native.ps1 -AuditOnly -BuildDir 'C:\pvzbuild\ui1'` | `100% tests passed, 0 tests failed out of 22`，exit 0 |
| desktop | `pwsh -File tools/build_native.ps1 -BuildDir 'C:\pvzbuild\ui-desktop'` | `100% tests passed, 0 tests failed out of 30`，exit 0 |

audit 里没有 `menu_render` / `level_select` —— 两个视图只在 `PVZ_ENABLE_DESKTOP` 下编译，这是
`--worldmap-screen` 早就立下的规矩（见 `native/tests/cli_desktop_disabled`）。

`menu_render` 断言：三条目、新存档不可继续且光标在 1、`choice == worldmap`、1280×720、选中项
标注带墨水、写一份三星两钥匙的存档后 `continued` 且光标回 0、`choice == continue`、顶栏三个数字
等于存档、两次同状态渲染字节完全相同、缺字体抛的错里有 `font_zh.ttc`。

`level_select` 断言：行数等于本世界关卡数（测试里自己从 catalog 数一遍，不复用被测代码的过滤）、
每行的 `world` 都是 `frontyard`、已通关数正确、首行 id 与 `selected` 一致、1280×720、选中行有墨水、
两次字节相同、未知世界返回 0 行但仍出图、缺字体报错。

## 反向探针

两条都是真跑出来的红，跑完已还原并重新绿过（`PROBE_` 残留 0 处）。

1. 字号 0（`menu_view.cpp` 里条目标签的 30 改成 0）：

   ```
   menu render test failed: the selected item must carry glyphs, only 274 ink pixels inside its rectangle
   ```

2. 去掉世界过滤（`buildRows` 的 `if (entry.second.world != world) continue;` 短路成 false）：

   ```
   level select render test failed: the list must hold exactly this world's levels: got 1809, content has 175 (of 1809 total)
   ```

第 2 条之所以能挡住，是因为测试自己数关卡（175），而不是问被测代码「你列了几个」。

## 测试自身的缺陷（这次发现并修掉的）

第一版的墨水断言采样整张选项卡，字号 0 时仍然数出 583 个「墨水」像素 —— 圆角与高亮的边缘就够
把阈值撑过去，也就是**一个完全没有文字的菜单能通过**。改成只采样标签所在的那条 240×46 的带子后：
有文字 583、字号 0 只有 274（带子的圆角边），阈值定在 420，两侧各留 160/146 的余量。上面第 1 条
探针就是按这个新度量跑出来的红。

## 还没有的东西

* 「继续游戏」只返回一个 `choice`，没有返回「续到哪一关」。存档里没有「上次打的关卡」字段，
  要接这一环得先决定写进 `Progress` 的是最近一次尝试还是最近一次通关。
* 两屏都没有声音。T38 的 `pvz_audio_core` 已经能播（`--audio-audit` 在跑），但视图层还没接
  `menu` / `click` 事件。
* 「世界地图 → 关卡列表 → 开战」目前要靠命令行把 `--worldmap-screen`、`--level-select`、
  `--run-level` 串起来；三屏之间还没有一个把它们放进同一个窗口的容器。
* `--assets` 的两个候选目录是按仓库布局猜的，仓库外的发布目录仍要显式传参。
