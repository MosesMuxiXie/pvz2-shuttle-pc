# 更新记录

## 0.1.0 — 首次可打包发行（2026-11-25）

- 打包链路：`native/CMakeLists.txt` 增加 install 树（exe + `content/` + `generated/*.json` + `assets/ui/` +
  `PROGRESS.md`/`LICENSES.md`）与 **静态 CRT**（`CMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded`，目标机不需要
  vc_redist）；版本号单一来源 = `project(PvZ2SHUTTLE VERSION 0.1.0)`，数据版本 `PVZ_DATA_VERSION=460.9`，
  `--version` 打印两者。
- `tools/package.ps1`（新）：cmake 发现（PATH → vswhere）→ 干净构建 → install 到 `dist/<name>/` →
  从 `NOTICE.md` 生成 `LICENSES.md` → zip + `sha256.txt` → **解压到 `%TEMP%` 后冒烟四条命令**
  （`--version` / `--worldmap` / `--run-level beach_23` / `--menu --frames 2` 含截图）并断言
  `generated/` 至少 30 个 json。实测产物 `PvZ2SHUTTLE-0.1.0-win64.zip` 20.9 MB（sha256 随构建变化，PE 时间戳进二进制；要认构建请看 `--version`）。清空 `build/package` 后的全量跑同样 exit 0，并用包里的 exe + `PVZ_ASSET_ROOT` 实拍战斗截图确认真实美术能加载。
- 资源查找顺序：`PVZ_ASSET_ROOT` → exe 同目录的 `assets/` → 向上搜 `native/generated`；
  生成表按 `content` 同级 `generated/` 再回落 `native/generated`（装好的树与源码树都能跑）。
- `assets/ui/`（26.6 MB，含 19.7 MB 中文字体）进包，四屏无头渲染才能在没有素材树的机器上跑；
  4.6 GB 提取美术仍不进包。
- 修掉一个真 bug：`main.cpp` 用 `content.parent/"native"/"generated"` 找生成表，装好的树里表在
  `generated/`，装完必读不到——新增 `generatedTable()` 两处候选 + `engine::generatedDir()` 兜底。
- 门禁新增三步：`vasebreaker` / `minigames` / `loot binding` 的 `--check`。

## Unreleased — native engine kernel S0–S3 (2026-11-20)

- 新增数据驱动内核 `native/src/engine/`：60 Hz 固定步长、种子化随机、FNV-1a 状态哈希，任意关卡可 `--run-level` 无头跑完并复现。
- 内容编译器把原版属性表编成 `native/generated/content.pack`（339 植物类型 / 1127 僵尸类型，含重复 id 保留与悬空引用计数），
  `Catalog` 优先读 pack、失败回落 JSON 并把口径写进 `rulesNote`。
- 原版 183 个 `ZombieClass` 全部映射到 6 个行为族（含 13 条人工覆盖）；`World::spawnZombie` 按 **class 表 > content > walk** 解析。
- 26 个世界的棋盘尺寸从关卡定义解出并接线（beach/modern 6×9，其余 5×9），`--boards` 可覆盖。
- 植物 11 个行为族改为 **pack 槽位 > content JSON > tuning 常量**；26 处兜底常量带注释，`wall`/`support` 缺口已登记。
- 审计修复：跳跃僵尸结构性不可胜、deck 校验、推车判负时机、召唤队列悬垂引用、门禁自愈、减速秒/tick 混用、大 dt 冻结、回放校验。
- 门禁：audit 11/11、desktop 16/16、Python 60 例、32 场景冒烟双跑一致（含 `beach_23` 胜利局）。
- 仍未完成：147 株植物的美术与 26 Boss、元素/养料/融合/小游戏、桌面视图迁移到新内核、macOS 验证。Python 发行入口暂不变。

## Unreleased — native rebuild preview (2026-11-11)

- Add independent C++20 content audit, SDL3 launcher, deterministic first-level battle preview and Python v2/v3 safe save importer.
- Add strict-schema, Unicode-path, render, combat/replay and no-overwrite save tests.
- Keep Python releases unchanged; native visuals, full campaign, online services and macOS release verification remain incomplete.
- See `docs/NATIVE_PROGRESS.md` for evidence and remaining work.

## 26.10.1 (2026-11-10)

- 世界地图重制为真实 SHUTTLE 风格的电影感轮播：夜空、中央岛、难度辣椒、关卡气泡、钥匙解锁。
- 商店按真实截图重绘：奶白大卡、彩色标题条、蓝色价格条、585 件商品分 4 类。
- 图鉴改为深蓝种子包网格 + 绿色标题详情条。
- 从 OBB Wwise 音效库还原 21 首真实 SHUTTLE 音乐并接入对应世界。
- 完整 26 世界 / 1809 关 / 147 植物 / 55 僵尸 / 85 融合 / 26 Boss / 花园 2.0。
- 修复打包版动态导入导致的启动失败（`--collect-submodules game` + `crash.log`）。
- Windows 安装程序、免安装包、macOS 通用包重新构建。
