# B6：LawnStrings 本地化表

日期：2026-11-26 ｜ 任务：t98 ｜ 输入：原始 OBB 的本地化属性表

* 英文：`pkg_0231_LawnStringsData.json`，19,057 对 → 19,055 个键
* 中文：`pkg_0232_LawnStringsData.json`，19,054 对 → 19,052 个键
* 产物：`native/generated/lawn_strings.json`（紧凑 JSON，`generated` 为内容寻址戳） + `native/src/loc.{hpp,cpp}`（运行期解析器）

## 一、结论摘要

* 合并后 **19,055 个键**：两侧都有 19,052，只在英文 3，只在中文 0。两侧都没有的键不存在（并集即全表）。
* 460.9 相对 460.1 的两个包各多一条 `ELEMENT_7_WAVEMASSAGE`（元素世界波次提示），它的两侧文本已原样进表：

  ```
  en: The resentment of the dead makes you tremble!
  zh: 亡魂的怨念令你们震颤！
  ```

* 键名**原样保留**（不转大小写、不去空白）：10 个键带空格、`&`、`#`、`$` 或多余的 `_ `，见「五、未知项」。
* 重复键 2 个（`NARRATIVE_ATLANTIS_17_INTRO_1`, `NARRATIVE_ATLANTIS_17_INTRO_2`）：同一 key 在表里出现两次且文本不同，取第一次、其余全文留在 `unknowns` 里，没有静默丢弃。
* 值里的 CR/CRLF 已归一为 `\n`（682 个值），所以产物里既没有裸 CR，也不会有 CRLF 行尾。

## 二、两包的条数与结构

包结构（两个包相同）：

```json
{"version": 1, "objects": [{"objclass": "LawnStringsData", "aliases": ["LawnStringsData"],
                          "objdata": {"LocStringValues": ["KEY", "TEXT", "KEY", "TEXT", …]}}]}
```

| 侧 | 平坦条目 | 配对数 | 去重后键 | 重复键 |
|---|---:|---:|---:|---:|
| en | 38,114 | 19,057 | 19,055 | 2 |
| zh | 38,108 | 19,054 | 19,052 | 2 |

配对数是偶数校验通过后的 `LocStringValues.length / 2`；去重后键数才是映射的规模。两包的条数差 3 与 `enOnly` 的 3 条一致，没有解析层面的缺口。

## 三、键命名规律

按后缀分类（两包一致，差异只在 `enOnly` 的 3 条叙事键）：

| 结尾 | 键数 | 占比 |
|---|---:|---:|
| `_<other>` | 12619 | 66.2% |
| `_DESCRIPTION` | 1369 | 7.2% |
| `_S` | 1179 | 6.2% |
| `_DESC` | 1108 | 5.8% |
| `_HEADER` | 883 | 4.6% |
| `_TITLE` | 792 | 4.2% |
| `_NAME` | 646 | 3.4% |
| `_TOOLTIP` | 326 | 1.7% |
| `_BODY` | 54 | 0.3% |
| `_LABEL` | 49 | 0.3% |
| `_HINT` | 30 | 0.2% |

命名不是严格分层的：`_TITLE`/`_DESC`/`_DESCRIPTION`/`_HINT` 是 UI 文案，`_NAME`/`_HEADER`/`_TOOLTIP`/`_BODY`/`_LABEL` 是实体名与工具提示，`_S` 多为复数形式（`…_SEEDS`、`…_GEMS`），其余 12k 个是整句叙事、关卡提示与商店条目（键里没有统一后缀）。因此**不要**靠后缀推断语义，取值一律查表。

## 四、中英差异

| 口径 | 数量 |
|---|---:|
| 两侧都有 | 19,052 |
| 只在英文（`zh` 留空） | 3 |
| 只在中文（`en` 留空） | 0 |
| 两侧文本完全相同 | 300 |
| 英文行存在但为空 | 77 |
| 中文行存在但为空 | 75 |
| 含 CR/CRLF（已归一） | 682 |

只在英文的 3 条是 `NARRATIVE_GTA_*` 的台词，中文包整段没有：

```
NARRATIVE_GTA_1_INTRO_18: {SAY:carljohnson}Tacos? I wouldn't suggest going to Cluckin' Bell right now.
NARRATIVE_GTA_1_INTRO_19: {SAY:carljohnson}'cause look over there, those zombie fools are coming!
NARRATIVE_GTA_6_INTRO_7: {SAY:carljohnson}I actually jacked a fire truck earlier, but... never mind.
```

「两侧文本相同」的 349 条多为专有名词、符号与数字（如 `+`、`×`、`LV`），不代表翻译缺失；空值那 77/75 条是原版就没填的行（如 `*_DESCRIPTION_PLANTFOOD`）。

## 五、未知项（`unknowns` 里逐条可查）

* **duplicate-key** `NARRATIVE_ATLANTIS_17_INTRO_1`（en+zh 各两次）：第一次的文本进表，第二次的全文在 `dropped`。两条其实是两段不同的台词共用一个 key，若某个屏幕要播完整段，必须自己按行拆分。
* **duplicate-key** `NARRATIVE_ATLANTIS_17_INTRO_2`（en+zh 各两次）：第一次的文本进表，第二次的全文在 `dropped`。两条其实是两段不同的台词共用一个 key，若某个屏幕要播完整段，必须自己按行拆分。
* **one-sided** `NARRATIVE_GTA_1_INTRO_18`（只有 en）：另一侧留空字符串。
* **one-sided** `NARRATIVE_GTA_1_INTRO_19`（只有 en）：另一侧留空字符串。
* **one-sided** `NARRATIVE_GTA_6_INTRO_7`（只有 en）：另一侧留空字符串。
* **empty-value** 英文 77 条 / 中文 75 条：行在、文本为空。`resolve()` 把空串当缺失，会落到另一侧语言，不会返回空串。
* **line-endings** 682 个值含 CR：已归一为 `\n`。客户端的分行只认 `\n`，保留 CR 会在每行末尾留一个隐形字节。
* **identical-text** 300 条两侧相同（专有名词/符号）。
* **key-shape** 10 个键不是 `[A-Z0-9_.-]`：

  ```
  #OF#
  BF23_GOLD BLOOM_UNLOCK
  BF23_POWER LILY_UNLOCK
  EPICQUEST_BUFFZ&BRUISEZ01_DESC
  EPICQUEST_BUFFZ&BRUISEZ02_DESC
  EPICQUEST_BUFFZ&BRUISEZ03_DESC
  EPICQUEST_BUFZ&BRUISEZ_TITLE
  FF23_ULTIMATE_GEMS_ PACK
  LFD23_ULTIMATE_GEMS_ PACK
  PRODUCT_ CHILLYPEPPER _SHORT_DESCRIPTION
  ```

  照原样保留（查表必须用表里的同一个字符串），但不要把它们当命令行 id 或文件名。

## 六、哪些屏应该改用它

只列清单，不改别人的文件。按收益排序：

| 位置 | 现在显示什么 | 应改成 |
|---|---|---|
| `native/src/achievements_view.cpp:118` | `row.title = humanizeGameKey(row.titleKey)` → `ACHIEVE_ALL_IN_JEST_TITLE` 显示成「All In Jest」 | `loc::resolve(strings, row.titleKey, humanizeGameKey(row.titleKey))`，中文表里是「向我开炮」 |
| `native/src/daily_view.cpp:115` | 同样是 `humanizeGameKey(row.titleKey)`（11 条日常） | 同上 |
| `native/src/almanac_view.cpp:244-245` | `nameKey`/`descKey` 存了但没用：`:599` 直接把 `descKey` 画到屏幕上，`:616` 把 `stat.valueKey` 拼进「type · valueKey」 | `name = resolve(strings, entry.nameKey, entry.nameKey)`、描述与数值标签同理；这是收益最大的一处（每种植物/僵尸的名字与说明） |
| `native/src/almanac_view.cpp:616` | `stat.type + " · " + stat.valueKey`（直接打印键） | `stat.type + " · " + resolve(strings, stat.valueKey, stat.valueKey)` |
| `native/src/garden_view.cpp:417` | 奖励提示里打印「标题键 」+ 原始 key | `resolve(strings, current->titleKey, current->titleKey)` |
| `native/src/worldmap.cpp:135` | `info.nameKey` 只存不用（世界名） | 显示时套 `resolve()` |

`humanize` 不作废：`resolve()` 的 `fallback` 参数就是为了让它继续当最后兜底——表里没有的键仍显示机械转写，不会变成空字符串。

## 七、运行期契约

```cpp
pvz::loc::Strings load(const std::string& contentRoot);   // 从不抛异常
std::string resolve(const Strings&, const std::string& key, const std::string& fallback);
```

* `load()` 只读不写：`contentRoot` 非空时按 `<root>/lawn_strings.json`、`<root>/generated/`、`<root>/native/generated/`、`<root>/../native/generated/`、`<root>/../../native/generated/` 顺序探测；`contentRoot` 为空时才用 `PVZ_GENERATED_DIR` 与「从当前目录向上走」的兜底。找不到、读不动、JSON 坏了都只返回空表（`source` 为空、`error` 记一句），屏幕照常启动。
* `resolve()` 顺序是**中文 → 英文 → fallback**：本作的目标语言是中文，英文只在中文行缺失/为空时补位。空串与只有空白的值都按缺失处理。
* 不打印任何日志：一个键没翻译是数据事实，不是运行期错误，喧哗只会淹没真正的错误。

## 八、复现与校验

```powershell
python tools\contentc\loc.py              # 写表 + 写本报告
python tools\contentc\loc.py --check      # 0 = 最新；2 = 有产物过期
python -m unittest tools.tests.test_loc    # 编译端 12 例
ctest -R loc --output-on-failure           # 运行期 loc_test
```

`--check` 用同一个序列化器逐字节比对，`generated` 戳只由内容决定（禁墙钟/mtime），所以同一份输入在任何机器上得到同一串字节。
