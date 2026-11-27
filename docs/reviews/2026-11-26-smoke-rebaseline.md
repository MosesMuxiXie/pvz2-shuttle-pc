# D2 冒烟基线重锚工具（`tools/smoke_rebaseline.py`）

日期：2026-11-26　范围：`tools/smoke_rebaseline.py`、`tools/tests/test_smoke_rebaseline.py`、
`native/generated/engine_smoke.json`（仅 `--accept`）、`docs/PARITY_BASELINE.md`（仅追加记录表）、本文。

## 0 结论

冒烟基线从「哈希是硬约束，变了就靠 `-AllowMatrixChange` 一把梭重写」改成「**漂了必须点名 + 写原因**」：

- `--check` 把今天跑出来的 32 个场景与基线逐条比对，打印 `+ added` / `- missing` / `~ changed`，
  变化项带 `hash 旧 -> 新` 与 `tick/status/killed/spawned/leaked/mowerKills` 的差异，有漂移 exit **1**；
- `--accept <id>[,<id>] --reason "…"` 只把**点名的**场景写回基线，并在
  `docs/PARITY_BASELINE.md` 的「冒烟基线变更记录」表里追加 `时间 / 场景 / 旧 hash / 新 hash / 原因`；
- 基线用 `engine_smoke.render`（产生它的那个 dumper）重写，`--accept` 之后同一份快照再 `--check` **exit 0**；
- `--list` 并排给基线/当前 hash；`--from <report.json>` 复用别人已经跑好的报告（`check_all.ps1` 就有现成的
  `build/engine_smoke.fresh.json`），不重复跑 32×2 次。

真机实测（`C:\pvzbuild\rail1\Release\PvZ2SHUTTLE.exe`）：`--check` 报 1 条漂移（`world cowboy`），
`--accept "world cowboy"` 后记录表多一行，`--check --from build/engine_smoke.now.json` **exit 0**。

## 1 接口

```
python tools/smoke_rebaseline.py --check  [--exe PATH] [--content DIR] [--pack FILE] [--boards FILE]
                                          [--baseline FILE] [--from REPORT.json]
python tools/smoke_rebaseline.py --accept "<id>[,<id>…]" --reason "<why>"
                                          [--timestamp 2026-11-26T12:00:00Z] [--from REPORT.json]
python tools/smoke_rebaseline.py --list   [--exe PATH | --from REPORT.json]
```

| 参数 | 含义 | 缺省 |
| --- | --- | --- |
| `--check` | 跑门禁并与基线比对；有漂移 exit 1 | — |
| `--accept` | 重锚点名场景，可重复、可逗号分隔（场景名里带空格，整串加引号即可） | — |
| `--reason` | **必填**；写进记录表的「原因」列 | 空 → exit 2 |
| `--list` | 并排列出 `baseline=` / `current=`，不一致的行前加 `!` | — |
| `--exe` | 被测可执行文件 | `build/native/Release/PvZ2SHUTTLE.exe` |
| `--content` / `--pack` / `--boards` | 同 `engine_smoke.py` | 仓库内 path |
| `--baseline` | 基线文件 | `native/generated/engine_smoke.json` |
| `--log` | 变更记录所在文档 | `docs/PARITY_BASELINE.md` |
| `--from` | 用已有报告当「当前结果」，不跑门禁 | 空（跑门禁） |
| `--timestamp` | 记录行的时间戳（**ISO-8601 UTC**，不取 mtime） | 运行时 `%Y-%m-%dT%H:%M:%SZ` |

退出码：

| 码 | 含义 |
| --- | --- |
| 0 | `--check` 无漂移 / `--accept` 成功（并已自校验）/ `--list` 正常 |
| 1 | `--check` 有漂移；或 `--accept` 自校验失败（写入后点名的场景仍不一致） |
| 2 | 用法或输入错误：缺 `--reason`、点名的场景没变、基线缺失/不是 JSON/没有 `scenarios` 数组 |

## 2 为什么需要它：`-AllowMatrixChange` 是「一把梭」

`tools/check_all.ps1` 现在的第 330–341 行：

```powershell
$smoke = Join-Path $repo 'native/generated/engine_smoke.json'
$smokeFresh = Join-Path $repo 'build/engine_smoke.fresh.json'
$beforeSmoke = if (Test-Path $smoke) { Get-Content $smoke -Raw } else { '' }
Step 'engine smoke' {
    python tools/engine_smoke.py --out $smokeFresh
}
$afterSmoke = Get-Content $smokeFresh -Raw
$smokeChanged = -not (Compare-Report $beforeSmoke $afterSmoke)
Sync-Baseline -Fresh $smokeFresh -Baseline $smoke -Changed $smokeChanged -Label 'native/generated/engine_smoke.json'
if ($smokeChanged -and -not $AllowMatrixChange) {
    Write-Host "[fail] native/generated/engine_smoke.json changed; review the diff or pass -AllowMatrixChange" -ForegroundColor Red
    $failures.Add('engine smoke changed')
}
```

它能告诉你「**有变化**」，但不能告诉你「**哪一条、为什么**」，也不留记录：

1. `Compare-Report` 是整文件字符串比较 —— 一个场景变了和十个场景变了，报出来一模一样；
2. 转绿的唯一开关是 `-AllowMatrixChange`，一按就把**当轮全部**漂移一次性接收，包括队友半成品造成的那部分；
3. 接收之后没有任何台账，下次再看到 `world cowboy` 变了，没人知道上次是谁为什么改的；
4. 后果是大家开始不信任这条门禁：反正一按就绿，于是把它当噪音跳过 —— 这才是要把「哈希当硬约束」换掉的原因。

`--accept` 就是补上「点名 + 记录」这两件事，`--check` 保留「必须是 0 才算过」的硬度。

## 3 本轮已经发生过的 4 个场景变化（为什么基线一直在漂）

| 场景 | 旧 → 新 hash | 实质变化 | 原因 |
| --- | --- | --- | --- |
| `world cowboy`（`cowboy_1`） | `0xeb036737659cbc46` → `0xcb83dd8dcba537f5` | `killed 0 → 2`，`tick` 不变 | **A2 铁轨**：`cowboy_1` 的 `extra.minecarts=[2]`，第 2 行现在有一辆 RailCart，滚动途中碾死 2 只僵尸（`rail_hit` 走既有 `damageZombie` 通道）。这是本轮我自己的改动，已按新流程 `--accept` 并写入记录表 |
| `kongfu_1 5x9` / `world kongfu` | `0xe7a3d0ec0ace28e4`（S2）→ `0x072c993b96804fdf`（S2 修复轮）→ `0x741d5fb1a7a7408f`（当前） | 只 hash 变，`tick 8785`、`status lost` 不变 | 开局**初始场地**（`layInitialField`）落地 + 棋盘几何/命中批次：PARITY_BASELINE 第 374–376 行记的那一轮里「8 个世界 index-1 关卡开局有初始场地（只 hash 变）」就含它。注意 `kongfu_1` 同时是 `world kongfu` 与 `kongfu_1 5x9` 两个场景 —— 一次引擎改动会让两条同时红，`--accept` 必须两条都点名 |
| `beach_23 win` | `0xde03536c990dee92`（S2）→ … → `0xb2a22229f25b92e6`（当前，`tick 1599`，仍 `won`） | 结束 tick 前移（先 4 tick，后来 `initialPlants=4` 到 1536） | 豌豆速度 `5.2 → 5.55 cols/s`（原版直线弹 333 px/s）让命中提前；再加上胜利局开局有 4 株初始植物。**胜利分支的 tick 会随射击数值浮动**，这是它反复漂的根因 |
| `world renai`（`renai_1`） | 上一版 `playing` → 当前 `lost`，`tick 3364` | `status playing → lost` | 该关是「5 株全保」任务；空脚本下僵尸啃掉保护植物 → `protect_failed` 判负。这是**语义**变化，不是数值抖动 —— 也是四者里最需要写进台账的一条 |

共同点：四次都不是「不确定性」，而是引擎真的变了。缺的从来不是更硬的哈希，而是**谁改了哪一条、为什么**。

## 4 写入的确定性

- **同一个 dumper**：`smoke_rebaseline.render` 直接调 `engine_smoke.render`
  （`json.dumps(report, ensure_ascii=False, indent=1, sort_keys=True) + "\n"`），测试里用
  `assertIs(R.engine_smoke, importlib.import_module("engine_smoke"))` + 字节串比对钉死 —— 不存在「第二套 JSON 写法」。
- **形状不变**：`--accept` 只替换被点名场景的那条记录、按基线原顺序输出；新增场景追加到末尾；接受的删除从列表里去掉；
  场景对象的字段集合与基线完全一致（测试用 `set(entry)` 比对）。实测写成后 10,911 B / 32 条 / `CR=0`。
- **LF 守卫**：`write_baseline` 见到 `\r` 直接抛 `smoke baseline: …: refusing to write CRLF`
  —— 门禁写的是 LF，混了 CRLF 会让 `Compare-Report` 永远「有变化」。
- **自校验**：`--accept` 写盘后立刻重读基线，再对同一份当前结果做一次 diff；点名的场景若仍不一致 → exit 1，
  否则打印 `self-check: baseline matches this run; --check now exits 0`。

## 5 变更记录表

追加到 `docs/PARITY_BASELINE.md` 末尾（文档里没有这张表时自动建）：

```
## 冒烟基线变更记录

| 时间（UTC） | 场景 | 旧 hash | 新 hash | 原因 |
| --- | --- | --- | --- | --- |
| 2026-11-26T12:01:08Z | `world cowboy` | `0xeb036737659cbc46` | `0xcb83dd8dcba537f5` | rail carts: cowboy_1 now spawns one RailCart on row 2; … (killed 0->2) |
```

- **时间戳**是 ISO-8601 UTC（`--timestamp` 可覆盖，测试用它固定输出），**不是文件 mtime** —— 内容可复现。
- **幂等**：去重键是 `(场景, 新 hash)`。同一目标状态再 `--accept` 一次不会写第二行，只打印
  `already recorded, baseline unchanged`；基线字节也不变。
- **EOL 保持**：`docs/PARITY_BASELINE.md` 是 CRLF 文档，读时用 `newline=""` 关掉换行翻译，写入时沿用文档自己的
  EOL。实测追加后 `LF=533 / CRLF=533`（完全一致，没有半行裸 LF）；纯 LF 文档则写出纯 LF（两种情况各有一条测试）。
- 插行位置：表头/分隔行之后、该表最后一行之后；文档后面还有别的 `##` 小节时，插入不会破坏后续内容
  （`test_record_appended_to_existing_table` 断言 `## 下一节` 仍在）。

## 6 `--accept` 的使用纪律

1. **先 `--check`，看清是哪一条**。一条都不认识就先去问改这块的人，不要为了转绿而 accept。
2. **只点名你造成的**。`--accept` 拒绝未出现在 diff 里的名字（exit 2），也拒绝把别人的漂移顺手带走。
3. **`--reason` 写「机制」不写「更新基线」**。合格：`rail carts: cowboy_1 now spawns one RailCart on row 2, crushes 2`；
   不合格：`baseline refresh`、`fix test`、`misc`。
4. **一个语义改动一次 accept**，别把三轮改动攒成一条，否则记录表失去可追溯性。
5. **同一次提交**里基线 + 记录表一起走；两个文件都是本工具的写作用域。
6. `--accept` 打印 `remaining drift not accepted: N` 时，说明**还有别人的漂移**，此时 `--check` 仍是 1 —— 这是预期，不是 bug。

## 7 与 `check_all.ps1` 的关系（要不要挂）

**建议挂，但不是现在这样挂**，而且本轮不改 `tools/check_all.ps1`（不在本任务写作用域）。两条路：

- **最小改动（推荐）**：`check_all.ps1` 已经在第 331 行写了 `build/engine_smoke.fresh.json`，
  把第 336–341 行换成

  ```powershell
  Step 'engine smoke baseline' {
      python tools/smoke_rebaseline.py --check --from $smokeFresh
  }
  ```

  它天然复用同一份 fresh 报告（**不重复跑**），失败时直接打印哪几条变了；`-AllowMatrixChange` 的
  「整文件覆盖」语义就被 `--accept <id> --reason` 取代。`Sync-Baseline` 那三行可以只保留「fresh 报告留档」。
- **过渡期**：保留 `-AllowMatrixChange`，但让它额外打印 `--accept` 建议行（`--check` 的输出已经带了这一行），
  并要求 PR/review 里贴出记录表新增的行。

不建议的做法：把 `--check` 塞在 `engine smoke` 同一步里跑第二遍 —— 32 场景 × 双跑要几分钟，纯浪费。

## 8 测试（`tools/tests/test_smoke_rebaseline.py`，27 例全过 0.35 s）

门禁本身用 `smoke_rebaseline.collect` 这个模块级接缝打桩（替换成假报告），所以每个用例只测**记账**：

| 组 | 用例 |
| --- | --- |
| 无漂移 | `test_check_clean_exits_zero`、`test_check_does_not_touch_baseline` |
| 单条漂移 | `test_check_single_change_names_it_and_exits_one`（断言 `~ changed`、`hash 旧 -> 新`、`tick 7200->7300`、`killed 0->2`） |
| 点名 accept | `test_accept_only_the_named_scenario`（未点名的仍红）、`test_accept_then_check_is_clean`、`test_accept_comma_separated_and_repeated` |
| reason 必填 | `test_accept_without_reason_exits_two_and_writes_nothing`、`test_accept_blank_reason_exits_two` |
| 未知名字 | `test_accept_unknown_name_exits_two` |
| 基线形状 | `test_baseline_keeps_the_gate_shape_and_dumper`（无 `\r`、尾换行、字段集合、`== render(doc)`、缩进 1 的前缀）、`test_render_is_the_gate_dumper`、`test_write_baseline_refuses_crlf` |
| 记录表 | `test_record_row_is_appended`、`test_record_row_is_idempotent`、`test_record_document_created_when_missing`、`test_record_appended_to_existing_table`、`test_record_keeps_crlf_document_crlf`、`test_record_keeps_lf_document_lf` |
| 新增/消失 | `test_added_and_missing_are_reported`、`test_accept_added_and_missing_rewrites_the_list` |
| `--list` | `test_list_shows_baseline_and_current` |
| `--from` | `test_from_reuses_a_report_without_running_the_gate`（断言**没有**调用门禁）、`test_from_reports_drift_from_a_saved_report`、`test_from_missing_file_exits_two` |
| 坏基线 | `test_missing_baseline_exits_two`、`test_malformed_baseline_exits_two`、`test_baseline_without_names_exits_two` |

跑法：`python -m unittest tools.tests.test_smoke_rebaseline`（`tools/tests` 有 `__init__.py`，`discover` 也可）。

## 9 真机实测

```
$ python tools/smoke_rebaseline.py --check --exe C:\pvzbuild\rail1\Release\PvZ2SHUTTLE.exe
~ changed  world cowboy             hash 0xeb036737659cbc46 -> 0xcb83dd8dcba537f5  killed 0->2
smoke baseline: 1 scenario(s) differ from …\native\generated\engine_smoke.json
re-anchor the ones you caused: --accept "<name>[,<name>]" --reason "<why>"
exit 1

$ python tools/engine_smoke.py --exe … --out build/engine_smoke.now.json     # 32/32 双跑一致
$ python tools/smoke_rebaseline.py --accept "world cowboy" \
      --reason "rail carts: cowboy_1 now spawns one RailCart on row 2; it crushes 2 zombies …" \
      --from build/engine_smoke.now.json
accepted 1 scenario(s) into …\engine_smoke.json (1 new record row in …\PARITY_BASELINE.md)
self-check: baseline matches this run; --check now exits 0

$ python tools/smoke_rebaseline.py --check --from build/engine_smoke.now.json
smoke baseline: 32 scenarios, no change
exit 0
```

写后核对：`native/generated/engine_smoke.json` 10,911 B / 32 条 / 无 `CR`；
`docs/PARITY_BASELINE.md` 41,731 B，`LF=533`、`CRLF=533`（无半行裸 LF），新增「冒烟基线变更记录」在文末。

## 10 范围与遗留

- 只写了 `tools/smoke_rebaseline.py`、`tools/tests/test_smoke_rebaseline.py`、
  `native/generated/engine_smoke.json`（仅本次 `--accept` 一条）、`docs/PARITY_BASELINE.md`（仅追加记录表）与本文。
- **没有**改 `native/src/**`、`native/CMakeLists.txt`、`content/**`、其它 generated 产物，**没有** commit。
- 遗留（不在本任务）：
  1. `tools/check_all.ps1` 接入 `--check --from`（第 7 节给了确切替换位置），以及 `-AllowMatrixChange` 的退场；
  2. headless **截图**哈希（`snapshotBytes` / `snapshots/*.png`）还没有对应的重锚工具 —— 本轮它漂过两次都是手工比对的，
     同一套「点名 + 记录」应当复用到这里；
  3. 记录表目前是纯 Markdown，如果要做机器校验（比如「最近 N 条都必须有 reason」），
     下一步可以加一个 `--audit-log` 子命令解析这张表。
