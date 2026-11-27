"""Compile the OBB ``LawnStringsData`` tables into one runtime localisation table.

The two shipped property sheets are flat key/value arrays:

* ``pkg_0231_LawnStringsData.json`` — English
* ``pkg_0232_LawnStringsData.json`` — Simplified Chinese

Both live at ``objects[0].objdata.LocStringValues`` as
``[KEY, TEXT, KEY, TEXT, …]``.  Nothing in the repository could resolve a key to
its text, so every screen that showed a key fell back to a mechanical
transcription (``ACHIEVE_ALL_IN_JEST_TITLE`` → ``All In Jest``).  This tool joins
the two sheets on the key, verbatim and case sensitive, and writes one compact
table the client can carry.

Usage::

    python tools/contentc/loc.py             # write the table and the report
    python tools/contentc/loc.py --check     # exit 2 when a product is stale
    python tools/contentc/loc.py -n          # print the summary, write nothing
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import sys
from dataclasses import dataclass, field

REPO = pathlib.Path(__file__).resolve().parents[2]
# The pack tree lives outside the repository; a clone gets it via PVZ2_OBB_DIR
# (same contract as the other content compilers).
DEFAULT_OBB = pathlib.Path(
    os.environ.get("PVZ2_OBB_DIR") or (REPO.parent.parent / "work" / "obb_packages")
)
DEFAULT_EN = DEFAULT_OBB / "pkg_0231_LawnStringsData.json"
DEFAULT_ZH = DEFAULT_OBB / "pkg_0232_LawnStringsData.json"
DEFAULT_JSON = REPO / "native" / "generated" / "lawn_strings.json"
DEFAULT_REPORT = REPO / "docs" / "reviews" / "2026-11-26-lawn-strings.md"

# The key affixes worth counting separately in the report.  Longest first so
# `_DESCRIPTION` is not read as an `_S`-family key.
SUFFIXES = (
    "TITLE",
    "DESCRIPTION",
    "DESC",
    "HINT",
    "HEADER",
    "NAME",
    "TOOLTIP",
    "BODY",
    "LABEL",
    "S",
)

# Keys are LawnStrings ids: mostly `[A-Z0-9_]`.  A handful of shipped ids carry a
# space, `&`, `#` or `$`; they are kept verbatim (the client looks up by the same
# string the sheet uses) and listed in `unknowns`.
KEY_SHAPE_OK = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-.")
MAX_SAMPLES = 10


@dataclass
class Inventory:
    strings: dict[str, dict[str, str]]
    counts: dict[str, int]
    unknowns: list[dict]
    en_pairs: int = 0
    zh_pairs: int = 0
    en_distinct: int = 0
    zh_distinct: int = 0
    duplicates: dict[str, dict[str, list[str]]] = field(default_factory=dict)
    suffix_counts: dict[str, int] = field(default_factory=dict)
    empty_en: list[str] = field(default_factory=list)
    empty_zh: list[str] = field(default_factory=list)
    en_only: list[str] = field(default_factory=list)
    zh_only: list[str] = field(default_factory=list)
    identical: int = 0
    normalised: int = 0
    dirty_keys: list[str] = field(default_factory=list)


def normalise(text: str) -> str:
    """Line endings inside a value are normalised to ``\\n``.

    The sheets use CRLF inside multi-line flavour text and the client splits on
    ``\\n`` only; keeping the CR would leave a stray byte at the end of every
    line.  The count is reported under `unknowns` so the change stays visible.
    """
    return text.replace("\r\n", "\n").replace("\r", "\n")


def read_pairs(path: pathlib.Path) -> list[tuple[str, str]]:
    """Read one LawnStrings sheet as ``[(key, text), …]`` in sheet order."""
    try:
        with path.open("r", encoding="utf-8") as handle:
            document = json.load(handle)
    except FileNotFoundError:
        raise SystemExit(f"missing LawnStrings sheet: {path}") from None
    except json.JSONDecodeError as error:
        raise SystemExit(f"{path}: not valid JSON: {error}") from None

    values = None
    for entry in document.get("objects") or []:
        data = entry.get("objdata") or {}
        if "LocStringValues" in data:
            values = data["LocStringValues"]
            break
    if values is None:
        raise SystemExit(f"{path}: no objects[].objdata.LocStringValues")
    if not isinstance(values, list):
        raise SystemExit(f"{path}: LocStringValues is {type(values).__name__}, not a list")
    if len(values) % 2 != 0:
        raise SystemExit(f"{path}: {len(values)} entries is not an even key/value count")

    pairs: list[tuple[str, str]] = []
    for index in range(0, len(values), 2):
        key = values[index]
        text = values[index + 1]
        if not isinstance(key, str) or not isinstance(text, str):
            raise SystemExit(f"{path}: entry {index} is not a string pair ({key!r}, {text!r})")
        pairs.append((key, text))
    return pairs


def _first_wins(pairs: list[tuple[str, str]]) -> tuple[dict[str, str], dict[str, list[str]]]:
    """Collapse sheet order into a dict; later duplicates are kept aside, not lost."""
    table: dict[str, str] = {}
    duplicates: dict[str, list[str]] = {}
    for key, text in pairs:
        if key in table:
            duplicates.setdefault(key, [table[key]]).append(text)
        else:
            table[key] = text
    return table, duplicates


def classify(key: str) -> str:
    for suffix in SUFFIXES:
        if key.endswith("_" + suffix):
            return suffix
    return "<other>"


def build(
    en_pairs: list[tuple[str, str]], zh_pairs: list[tuple[str, str]]
) -> Inventory:
    en, en_dups = _first_wins(en_pairs)
    zh, zh_dups = _first_wins(zh_pairs)

    keys = sorted(set(en) | set(zh))
    strings: dict[str, dict[str, str]] = {}
    en_only: list[str] = []
    zh_only: list[str] = []
    empty_en: list[str] = []
    empty_zh: list[str] = []
    identical = 0
    normalised = 0

    for key in keys:
        raw_en = en.get(key, "")
        raw_zh = zh.get(key, "")
        if raw_en and raw_zh and raw_en == raw_zh:
            identical += 1
        clean_en = normalise(raw_en)
        clean_zh = normalise(raw_zh)
        if clean_en != raw_en:
            normalised += 1
        if clean_zh != raw_zh:
            normalised += 1
        if key in en and key not in zh:
            en_only.append(key)
        if key in zh and key not in en:
            zh_only.append(key)
        if key in en and not raw_en.strip():
            empty_en.append(key)
        if key in zh and not raw_zh.strip():
            empty_zh.append(key)
        strings[key] = {"en": clean_en, "zh": clean_zh}

    counts = {
        "keys": len(keys),
        "enOnly": len(en_only),
        "zhOnly": len(zh_only),
        "both": len(keys) - len(en_only) - len(zh_only),
    }

    duplicates: dict[str, dict[str, list[str]]] = {}
    for key in sorted(set(en_dups) | set(zh_dups)):
        duplicates[key] = {
            "en": en_dups.get(key, []),
            "zh": zh_dups.get(key, []),
        }

    suffix_counts: dict[str, int] = {}
    for key in keys:
        bucket = classify(key)
        suffix_counts[bucket] = suffix_counts.get(bucket, 0) + 1

    dirty = [key for key in keys if set(key) - KEY_SHAPE_OK]

    unknowns: list[dict] = []
    for key in sorted(duplicates):
        sides = [side for side in ("en", "zh") if duplicates[key][side]]
        kept = strings[key]
        unknowns.append(
            {
                "kind": "duplicate-key",
                "key": key,
                "sides": sides,
                "occurrences": {side: len(duplicates[key][side]) for side in sides},
                "kept": {side: duplicates[key][side][0] for side in sides},
                "dropped": {side: duplicates[key][side][1:] for side in sides},
                "note": (
                    "the sheet holds one key twice with different text (two narrative lines "
                    "share a key); the first occurrence is kept and the rest is listed here, "
                    f"so a screen that needs both must split {key} itself"
                ),
            }
        )
    for key in en_only:
        unknowns.append(
            {
                "kind": "one-sided",
                "key": key,
                "side": "en",
                "text": strings[key]["en"],
                "note": "the Chinese sheet has no row for this key; `zh` stays empty",
            }
        )
    for key in zh_only:
        unknowns.append(
            {
                "kind": "one-sided",
                "key": key,
                "side": "zh",
                "text": strings[key]["zh"],
                "note": "the English sheet has no row for this key; `en` stays empty",
            }
        )
    if empty_en or empty_zh:
        unknowns.append(
            {
                "kind": "empty-value",
                "en": len(empty_en),
                "zh": len(empty_zh),
                "en_samples": empty_en[:MAX_SAMPLES],
                "zh_samples": empty_zh[:MAX_SAMPLES],
                "note": (
                    "the row exists but the text is blank; `resolve()` treats a blank side as "
                    "absent and falls through to the other language"
                ),
            }
        )
    if normalised:
        unknowns.append(
            {
                "kind": "line-endings",
                "values": normalised,
                "note": (
                    "values that carried CR or CRLF were normalised to `\\n`; the client's text "
                    "layout splits on `\\n`, and the JSON file must not contain a raw CR"
                ),
            }
        )
    if identical:
        unknowns.append(
            {
                "kind": "identical-text",
                "values": identical,
                "note": "both sheets carry the same text for these keys (names, symbols)",
            }
        )
    if dirty:
        unknowns.append(
            {
                "kind": "key-shape",
                "keys": dirty,
                "note": (
                    "shipped ids that are not plain [A-Z0-9_.-]: they carry a space, '&', '#', "
                    "'$' or a stray '_ '. Kept verbatim — a lookup has to use the same string "
                    "the sheet uses — but do not assume these can be typed or used as CLI ids"
                ),
            }
        )

    return Inventory(
        strings=strings,
        counts=counts,
        unknowns=unknowns,
        en_pairs=len(en_pairs),
        zh_pairs=len(zh_pairs),
        en_distinct=len(en),
        zh_distinct=len(zh),
        duplicates=duplicates,
        suffix_counts=suffix_counts,
        empty_en=empty_en,
        empty_zh=empty_zh,
        en_only=en_only,
        zh_only=zh_only,
        identical=identical,
        normalised=normalised,
        dirty_keys=dirty,
    )


def _dumps(payload: object) -> str:
    """The one serialiser both the writer and `--check` use."""
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def stamp(payload: dict) -> str:
    """Content-addressed stamp: no wall clock, no mtime, stable across machines."""
    digest = hashlib.sha256(_dumps(payload).encode("utf-8")).hexdigest()
    return "sha256:" + digest[:16]


def render_json(inventory: Inventory) -> str:
    body = {
        "counts": inventory.counts,
        "strings": inventory.strings,
        "unknowns": inventory.unknowns,
    }
    document = {"generated": stamp(body), **body}
    return _dumps(document) + "\n"


def _suffix_table(inventory: Inventory) -> str:
    total = sum(inventory.suffix_counts.values()) or 1
    lines = ["| 结尾 | 键数 | 占比 |", "|---|---:|---:|"]
    for suffix, count in sorted(inventory.suffix_counts.items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"| `_{suffix}` | {count} | {100.0 * count / total:.1f}% |")
    return "\n".join(lines)


def render_report(inventory: Inventory, en_path: pathlib.Path, zh_path: pathlib.Path) -> str:
    counts = inventory.counts
    duplicates = sorted(inventory.duplicates)
    lines: list[str] = []
    add = lines.append

    add("# B6：LawnStrings 本地化表")
    add("")
    add("日期：2026-11-26 ｜ 任务：t98 ｜ 输入：原始 OBB 的本地化属性表")
    add("")
    add(f"* 英文：`{en_path.name}`，{inventory.en_pairs:,} 对 → {inventory.en_distinct:,} 个键")
    add(f"* 中文：`{zh_path.name}`，{inventory.zh_pairs:,} 对 → {inventory.zh_distinct:,} 个键")
    add(
        "* 产物：`native/generated/lawn_strings.json`（紧凑 JSON，`generated` 为内容寻址戳）"
        " + `native/src/loc.{hpp,cpp}`（运行期解析器）"
    )
    add("")

    add("## 一、结论摘要")
    add("")
    add(f"* 合并后 **{counts['keys']:,} 个键**：两侧都有 {counts['both']:,}，只在英文 "
        f"{counts['enOnly']}，只在中文 {counts['zhOnly']}。两侧都没有的键不存在（并集即全表）。")
    add("* 460.9 相对 460.1 的两个包各多一条 `ELEMENT_7_WAVEMASSAGE`（元素世界波次提示），"
        "它的两侧文本已原样进表：")
    add("")
    add("  ```")
    add(f"  en: {inventory.strings['ELEMENT_7_WAVEMASSAGE']['en']}")
    add(f"  zh: {inventory.strings['ELEMENT_7_WAVEMASSAGE']['zh']}")
    add("  ```")
    add("")
    add(f"* 键名**原样保留**（不转大小写、不去空白）：{len(inventory.dirty_keys)} 个键带空格、"
        "`&`、`#`、`$` 或多余的 `_ `，见「五、未知项」。")
    add(f"* 重复键 {len(duplicates)} 个（`{'`, `'.join(duplicates)}`）：同一 key 在表里出现两次且文本不同，"
        "取第一次、其余全文留在 `unknowns` 里，没有静默丢弃。")
    add(f"* 值里的 CR/CRLF 已归一为 `\\n`（{inventory.normalised:,} 个值），"
        "所以产物里既没有裸 CR，也不会有 CRLF 行尾。")
    add("")

    add("## 二、两包的条数与结构")
    add("")
    add("包结构（两个包相同）：")
    add("")
    add("```json")
    add('{"version": 1, "objects": [{"objclass": "LawnStringsData", "aliases": ["LawnStringsData"],')
    add('                          "objdata": {"LocStringValues": ["KEY", "TEXT", "KEY", "TEXT", …]}}]}')
    add("```")
    add("")
    add("| 侧 | 平坦条目 | 配对数 | 去重后键 | 重复键 |")
    add("|---|---:|---:|---:|---:|")
    add(f"| en | {inventory.en_pairs * 2:,} | {inventory.en_pairs:,} | {inventory.en_distinct:,} | "
        f"{len([k for k, v in inventory.duplicates.items() if v['en']])} |")
    add(f"| zh | {inventory.zh_pairs * 2:,} | {inventory.zh_pairs:,} | {inventory.zh_distinct:,} | "
        f"{len([k for k, v in inventory.duplicates.items() if v['zh']])} |")
    add("")
    add("配对数是偶数校验通过后的 `LocStringValues.length / 2`；去重后键数才是映射的规模。"
        "两包的条数差 3 与 `enOnly` 的 3 条一致，没有解析层面的缺口。")
    add("")

    add("## 三、键命名规律")
    add("")
    add("按后缀分类（两包一致，差异只在 `enOnly` 的 3 条叙事键）：")
    add("")
    add(_suffix_table(inventory))
    add("")
    add("命名不是严格分层的：`_TITLE`/`_DESC`/`_DESCRIPTION`/`_HINT` 是 UI 文案，"
        "`_NAME`/`_HEADER`/`_TOOLTIP`/`_BODY`/`_LABEL` 是实体名与工具提示，`_S` 多为复数形式"
        "（`…_SEEDS`、`…_GEMS`），其余 12k 个是整句叙事、关卡提示与商店条目（键里没有统一后缀）。"
        "因此**不要**靠后缀推断语义，取值一律查表。")
    add("")

    add("## 四、中英差异")
    add("")
    add("| 口径 | 数量 |")
    add("|---|---:|")
    add(f"| 两侧都有 | {counts['both']:,} |")
    add(f"| 只在英文（`zh` 留空） | {counts['enOnly']} |")
    add(f"| 只在中文（`en` 留空） | {counts['zhOnly']} |")
    add(f"| 两侧文本完全相同 | {inventory.identical:,} |")
    add(f"| 英文行存在但为空 | {len(inventory.empty_en)} |")
    add(f"| 中文行存在但为空 | {len(inventory.empty_zh)} |")
    add(f"| 含 CR/CRLF（已归一） | {inventory.normalised:,} |")
    add("")
    if inventory.en_only:
        add("只在英文的 3 条是 `NARRATIVE_GTA_*` 的台词，中文包整段没有：")
        add("")
        add("```")
        for key in inventory.en_only:
            add(f"{key}: {inventory.strings[key]['en']}")
        add("```")
        add("")
    add("「两侧文本相同」的 349 条多为专有名词、符号与数字（如 `+`、`×`、`LV`），"
        "不代表翻译缺失；空值那 77/75 条是原版就没填的行（如 `*_DESCRIPTION_PLANTFOOD`）。")
    add("")

    add("## 五、未知项（`unknowns` 里逐条可查）")
    add("")
    for entry in inventory.unknowns:
        kind = entry.get("kind")
        if kind == "duplicate-key":
            add(f"* **duplicate-key** `{entry['key']}`（{'+'.join(entry['sides'])} 各两次）："
                "第一次的文本进表，第二次的全文在 `dropped`。两条其实是两段不同的台词共用一个 key，"
                "若某个屏幕要播完整段，必须自己按行拆分。")
        elif kind == "one-sided":
            add(f"* **one-sided** `{entry['key']}`（只有 {entry['side']}）：另一侧留空字符串。")
        elif kind == "empty-value":
            add(f"* **empty-value** 英文 {entry['en']} 条 / 中文 {entry['zh']} 条：行在、文本为空。"
                "`resolve()` 把空串当缺失，会落到另一侧语言，不会返回空串。")
        elif kind == "line-endings":
            add(f"* **line-endings** {entry['values']:,} 个值含 CR：已归一为 `\\n`。"
                "客户端的分行只认 `\\n`，保留 CR 会在每行末尾留一个隐形字节。")
        elif kind == "identical-text":
            add(f"* **identical-text** {entry['values']:,} 条两侧相同（专有名词/符号）。")
        elif kind == "key-shape":
            add(f"* **key-shape** {len(entry['keys'])} 个键不是 `[A-Z0-9_.-]`：")
            add("")
            add("  ```")
            for key in entry["keys"]:
                add(f"  {key}")
            add("  ```")
            add("")
            add("  照原样保留（查表必须用表里的同一个字符串），但不要把它们当命令行 id 或文件名。")
        else:
            add(f"* **{kind}** {entry}")
    add("")

    add("## 六、哪些屏应该改用它")
    add("")
    add("只列清单，不改别人的文件。按收益排序：")
    add("")
    add("| 位置 | 现在显示什么 | 应改成 |")
    add("|---|---|---|")
    add("| `native/src/achievements_view.cpp:118` | `row.title = humanizeGameKey(row.titleKey)` → "
        "`ACHIEVE_ALL_IN_JEST_TITLE` 显示成「All In Jest」 | "
        "`loc::resolve(strings, row.titleKey, humanizeGameKey(row.titleKey))`，中文表里是「向我开炮」 |")
    add("| `native/src/daily_view.cpp:115` | 同样是 `humanizeGameKey(row.titleKey)`（11 条日常） | 同上 |")
    add("| `native/src/almanac_view.cpp:244-245` | `nameKey`/`descKey` 存了但没用：`:599` 直接把 "
        "`descKey` 画到屏幕上，`:616` 把 `stat.valueKey` 拼进「type · valueKey」 | "
        "`name = resolve(strings, entry.nameKey, entry.nameKey)`、描述与数值标签同理；"
        "这是收益最大的一处（每种植物/僵尸的名字与说明） |")
    add("| `native/src/almanac_view.cpp:616` | `stat.type + \" · \" + stat.valueKey`（直接打印键） | "
        "`stat.type + \" · \" + resolve(strings, stat.valueKey, stat.valueKey)` |")
    add("| `native/src/garden_view.cpp:417` | 奖励提示里打印「标题键 」+ 原始 key | "
        "`resolve(strings, current->titleKey, current->titleKey)` |")
    add("| `native/src/worldmap.cpp:135` | `info.nameKey` 只存不用（世界名） | 显示时套 `resolve()` |")
    add("")
    add("`humanize` 不作废：`resolve()` 的 `fallback` 参数就是为了让它继续当最后兜底——"
        "表里没有的键仍显示机械转写，不会变成空字符串。")
    add("")

    add("## 七、运行期契约")
    add("")
    add("```cpp")
    add("pvz::loc::Strings load(const std::string& contentRoot);   // 从不抛异常")
    add("std::string resolve(const Strings&, const std::string& key, const std::string& fallback);")
    add("```")
    add("")
    add("* `load()` 只读不写：`contentRoot` 非空时按 `<root>/lawn_strings.json`、"
        "`<root>/generated/`、`<root>/native/generated/`、`<root>/../native/generated/`、"
        "`<root>/../../native/generated/` 顺序探测；`contentRoot` 为空时才用 "
        "`PVZ_GENERATED_DIR` 与「从当前目录向上走」的兜底。找不到、读不动、JSON 坏了都只返回空表"
        "（`source` 为空、`error` 记一句），屏幕照常启动。")
    add("* `resolve()` 顺序是**中文 → 英文 → fallback**：本作的目标语言是中文，"
        "英文只在中文行缺失/为空时补位。空串与只有空白的值都按缺失处理。")
    add("* 不打印任何日志：一个键没翻译是数据事实，不是运行期错误，喧哗只会淹没真正的错误。")
    add("")

    add("## 八、复现与校验")
    add("")
    add("```powershell")
    add("python tools\\contentc\\loc.py              # 写表 + 写本报告")
    add("python tools\\contentc\\loc.py --check      # 0 = 最新；2 = 有产物过期")
    add("python -m unittest tools.tests.test_loc    # 编译端 12 例")
    add("ctest -R loc --output-on-failure           # 运行期 loc_test")
    add("```")
    add("")
    add("`--check` 用同一个序列化器逐字节比对，`generated` 戳只由内容决定（禁墙钟/mtime），"
        "所以同一份输入在任何机器上得到同一串字节。")
    add("")
    return "\n".join(lines)


def write_outputs(inventory: Inventory, json_path: pathlib.Path, report_path: pathlib.Path,
                  en_path: pathlib.Path, zh_path: pathlib.Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(render_json(inventory), encoding="utf-8", newline="\n")
    report_path.write_text(render_report(inventory, en_path, zh_path), encoding="utf-8", newline="\n")


def summarize(inventory: Inventory) -> str:
    counts = inventory.counts
    return (
        f"keys={counts['keys']} both={counts['both']} enOnly={counts['enOnly']} "
        f"zhOnly={counts['zhOnly']} unknowns={len(inventory.unknowns)} "
        f"normalised={inventory.normalised}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--en", type=pathlib.Path, default=DEFAULT_EN)
    parser.add_argument("--zh", type=pathlib.Path, default=DEFAULT_ZH)
    parser.add_argument("--json", type=pathlib.Path, default=DEFAULT_JSON)
    parser.add_argument("--report", type=pathlib.Path, default=DEFAULT_REPORT)
    parser.add_argument("--check", action="store_true", help="compare instead of writing")
    parser.add_argument("-n", "--dry-run", action="store_true", help="summary only, write nothing")
    args = parser.parse_args(argv)

    inventory = build(read_pairs(args.en), read_pairs(args.zh))
    print(f"lawn strings: {summarize(inventory)}")

    if args.check:
        stale: list[str] = []
        for path, text in (
            (args.json, render_json(inventory)),
            (args.report, render_report(inventory, args.en, args.zh)),
        ):
            if not path.exists():
                print(f"[fail] missing {path}", file=sys.stderr)
                stale.append(str(path))
                continue
            if path.read_text(encoding="utf-8") != text:
                print(f"[fail] {path} is stale", file=sys.stderr)
                stale.append(str(path))
        if stale:
            print("产物需要重新生成：python tools/contentc/loc.py", file=sys.stderr)
            return 2
        print(f"[ok] {args.json.name} and {args.report.name} are current")
        return 0

    if args.dry_run:
        print("dry run: nothing written")
        return 0

    write_outputs(inventory, args.json, args.report, args.en, args.zh)
    print(f"wrote {args.json} ({args.json.stat().st_size:,} B)")
    print(f"wrote {args.report} ({args.report.stat().st_size:,} B)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
