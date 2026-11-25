"""把 460.9 相对 460.1 **新增的三块数据**编译成客户端可读的一份补丁表（T64）。

运行::

    python tools/contentc/newin4609.py            # 生成产物
    python tools/contentc/newin4609.py --check    # 只校验产物是否最新（逐字节）
    python tools/contentc/newin4609.py -n         # 只打印摘要，不写盘
    python tools/contentc/newin4609.py --baseline # 额外打印与 460.1 包树的差异（不写盘）

口径
----
1. **只读 OBB**：包目录取 ``PVZ2_OBB_DIR``，回退到
   ``<repo>/../../work/obb_packages``（与 ``tools/contentc/mechanics.py`` 同一写法）。
   产物里不写绝对路径 —— 换机器 ``--check`` 不该因此变红。
2. **三块钱数据**（460.9 才有，460.1 里没有）：

   * ``RlConfig``：``pkg_0234_DisableSkipLevelModuleProperties.json`` 的 objects 第 495 项
     （0 基），objclass ``RlConfig``，16 个字段的 roguelike 配置。
     产物里把原字段**原样铺平**（一个都不丢）再挂 ``package``/``file``/``objectIndex``
     与 ``raw``（同一份 objdata，供下游要原始形状时直接用）。
   * ``SuppressFlagZombie``：**不是** 460.9 独有的键 —— 全库 271 关的
     ``WaveManagerProperties`` 都有它（460.9 只是把元素第 8 关从"缺键"改成 ``true``）。
     所以 ``levelFlags`` 记录**全部 271 关**，值可能是 ``true`` 也可能是 ``false``
     （215 / 56），不假设它一定是 ``true``。
   * ``ThymedEventSchedule``：``pkg_2101`` 的 ``Events`` 从 27 条涨到 30 条。

3. **identity 用客户端 id**：``content/levels/*.json`` 的 ``extra.package`` 把
   ``pkg_0416`` 映射到 ``memorytour_2``，实测 1809 个包与 1809 个关卡是双射
   （0 个包对应多个关卡）。映射不到的包**不猜**，进 ``unknowns[]`` 并说明原因。
   ``LevelDefinition.Name`` 是本地化键（如 ``[ELEMENT_LEVEL_NAME]``），不是身份，
   只作为 ``levelName`` 附带记录。
4. **"新增 3 条"怎么定**：与 460.1 包树（``work/obb_packages_460_1``）逐条比
   ``UniqueID`` 得出 —— 新增的是 ``UniqueID`` 29/30/31，三条都是
   ``[EVENT_TIMESPACEECHOES_BACK]`` 回流，关卡前缀分别为
   ``timespaceechoes_0003/0004/0009``。这条判定写成常量
   ``NEW_THYME_UNIQUE_IDS``，不依赖 460.1 包树是否存在，``--check`` 才不会
   因为换了台机器就翻脸；``--baseline`` 现场重算只为复核。
5. **不推测填充**：拿不到就是 ``null``；类型不对的字段不硬转（时间戳只在是数字时
   才折成 ISO8601）。``ThymedEventSchedule`` 的 ``Action`` 是嵌套的
   ``{'LevelThymedEventActionData': {'Levels': [...]}}``，取不到就记 ``levels: []``
   并把这一条计入 ``unknowns``。

产物（确定性：``sort_keys``、紧凑 ``separators``、utf-8、末尾换行、固定日期）::

    native/generated/patch_460_9.json

顶层键：``format / source / counts / rlConfig / levelFlags / thymeEvents / unknowns``。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TOOLS = Path(__file__).resolve().parent.parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from contentc import sheets as sheets_mod  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LEVELS = ROOT / "content" / "levels"
DEFAULT_OBB = Path(
    os.environ.get("PVZ2_OBB_DIR") or (ROOT.parent.parent / "work" / "obb_packages"))
DEFAULT_OUT = ROOT / "native" / "generated" / "patch_460_9.json"

FORMAT = 1
#: 固定日期，不取运行时时钟 —— 否则 ``--check`` 永远失败。
GENERATED = "2026-11-24"

RL_PKG = "pkg_0234"
RL_PKG_FILE = "pkg_0234_DisableSkipLevelModuleProperties.json"
RL_ALIAS = "RlConfig"
LEVEL_GLOB = "pkg_*_LevelDefinition.json"
LEVEL_CLS = "LevelDefinition"
FLAG_KEY = "SuppressFlagZombie"
THYME_PKG = "pkg_2101"
THYME_PKG_FILE = "pkg_2101_ThymedEventSchedule.json"
THYME_CLS = "ThymedEventSchedule"
THYME_NEW_IDS = (29, 30, 31)
THYME_BASELINE_DIR = "obb_packages_460_1"

#: ``RlConfig`` 的字段顺序（报告与测试用；产物本身按键名排序）。
RL_FIELDS = (
    "Version",
    "LevelCount",
    "ChoiceCount",
    "StartingSunBase",
    "StartingSunPerLevel",
    "StartingSunMax",
    "ZombieHealthPctPerLevel",
    "ZombieDamagePctPerLevel",
    "ZombieSpeedPctPerLevel",
    "EliteChance",
    "EliteEvery",
    "EliteHealthBonusPct",
    "EliteDamageBonusPct",
    "FinalLevelIsElite",
    "DefaultOwnedFactionWeight",
    "TemplateLevelNames",
    "ZombiePool",
)


# --------------------------------------------------------------------------- io

def load_doc(path: Path) -> dict:
    """读一个 RTON 导出包。``utf-8-sig``：包文件带 BOM。"""
    return sheets_mod.load_sheet(path)


def objects(path: Path) -> list[dict]:
    return list(sheets_mod.iter_objects(load_doc(path)))


def alias_list(obj: dict) -> list[str]:
    return sheets_mod.aliases(obj)


def data_of(obj: dict) -> dict:
    data = obj.get("objdata")
    return data if isinstance(data, dict) else {}


def package_index(obb: Path) -> dict[str, Path]:
    """包 stem -> 路径，一次 glob 全覆盖（2116 个包 + ``_index.json``）。"""
    index: dict[str, Path] = {}
    for path in sorted(obb.glob("pkg_*.json")):
        index[path.name.split("_Level")[0] if "_Level" in path.name else path.stem] = path
        index.setdefault(path.stem, path)
        # ``pkg_0416_LevelDefinition`` -> ``pkg_0416``
        parts = path.stem.split("_")
        if len(parts) >= 2:
            index.setdefault("_".join(parts[:2]), path)
    return index


def iso_utc(value: Any) -> str | None:
    """epoch 秒 -> ``YYYY-MM-DDTHH:MM:SSZ``；不是数字就 ``None``（不硬转）。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (OverflowError, OSError, ValueError):
        return None


# ------------------------------------------------------------------ collectors

def collect_rl_config(obb: Path, unknowns: list[dict]) -> dict | None:
    path = obb / RL_PKG_FILE
    if not path.is_file():
        unknowns.append({
            "kind": "rl-config-missing",
            "count": 1,
            "detail": "%s 不存在，RlConfig 无从取" % RL_PKG_FILE,
            "probe": "确认 %s 是否随 460.9 一起解出" % RL_PKG_FILE,
            "samples": [RL_PKG_FILE],
        })
        return None
    for index, obj in enumerate(objects(path)):
        if RL_ALIAS not in alias_list(obj):
            continue
        data = data_of(obj)
        missing = [key for key in RL_FIELDS if key not in data]
        if missing:
            unknowns.append({
                "kind": "rl-config-field",
                "count": len(missing),
                "detail": "RlConfig 缺字段：%s" % ", ".join(missing),
                "probe": "打印 objdata 全部键，确认是否改名",
                "samples": missing[:6],
            })
        row: dict[str, Any] = dict(data)  # 原样铺平，一个键都不丢
        row.update({
            "package": RL_PKG,
            "file": RL_PKG_FILE,
            "objectIndex": index,
            "objclass": obj.get("objclass"),
            "aliases": alias_list(obj),
            "raw": data,
        })
        return row
    unknowns.append({
        "kind": "rl-config-missing",
        "count": 1,
        "detail": "%s 里没有 alias=%s 的对象" % (RL_PKG_FILE, RL_ALIAS),
        "probe": "grep RlConfig 看 alias 拼写",
        "samples": [RL_ALIAS],
    })
    return None


def level_index(levels_dir: Path) -> dict[str, str]:
    """``pkg_NNNN`` -> 客户端关卡 id（实测 1809↔1809 双射）。"""
    mapping: dict[str, str] = {}
    for path in sorted(levels_dir.glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8-sig"))
        package = (doc.get("extra") or {}).get("package")
        level_id = doc.get("id") or path.stem
        if package:
            mapping.setdefault(str(package), str(level_id))
    return mapping


def collect_level_flags(obb: Path, mapping: dict[str, str],
                        unknowns: list[dict]) -> list[dict]:
    rows: list[dict] = []
    unmapped: list[str] = []
    for path in sorted(obb.glob(LEVEL_GLOB)):
        doc = load_doc(path)
        level: dict = {}
        holders: list[tuple[int, dict]] = []
        for index, obj in enumerate(sheets_mod.iter_objects(doc)):
            data = data_of(obj)
            if obj.get("objclass") == LEVEL_CLS and not level:
                level = data
                continue
            if FLAG_KEY in data:
                holders.append((index, obj))
        if not holders:
            continue
        stem = "_".join(path.stem.split("_")[:2])
        level_id = mapping.get(stem)
        for index, obj in holders:
            data = data_of(obj)
            value = data.get(FLAG_KEY)
            if isinstance(value, bool):
                flag = value
            else:  # 原版出现过 null；不硬转成 false
                flag = None
            row = {
                "levelId": level_id,
                "package": stem,
                "stageModule": level.get("StageModule"),
                "levelNumber": level.get("LevelNumber"),
                "suppressFlagZombie": flag,
                "levelName": level.get("Name"),
                "holder": obj.get("objclass"),
                "holderAlias": (alias_list(obj) or [None])[0],
                "objectIndex": index,
            }
            rows.append(row)
            if level_id is None:
                unmapped.append(stem)
    if unmapped:
        unknowns.append({
            "kind": "level-flag-unmapped",
            "count": len(set(unmapped)),
            "detail": "这些包带 %s，但 content/levels/*.json 的 extra.package 没有引用它们，"
                      "拿不到客户端关卡 id（不猜）" % FLAG_KEY,
            "probe": "核对 content/levels 是否漏了这些关卡，或它们属于未实现的 OBB 世界",
            "samples": sorted(set(unmapped))[:8],
        })
    rows.sort(key=lambda row: (str(row["levelId"] or ""), str(row["package"]),
                               int(row["objectIndex"] or 0)))
    return rows


def collect_thyme_events(obb: Path, unknowns: list[dict]) -> list[dict]:
    path = obb / THYME_PKG_FILE
    if not path.is_file():
        unknowns.append({
            "kind": "thyme-missing",
            "count": 1,
            "detail": "%s 不存在" % THYME_PKG_FILE,
            "probe": "确认事件表是否改名",
            "samples": [THYME_PKG_FILE],
        })
        return []
    events: list[dict] = []
    for obj in objects(path):
        data = data_of(obj)
        raw_events = data.get("Events")
        if obj.get("objclass") != THYME_CLS or not isinstance(raw_events, list):
            continue
        for event in raw_events:
            if not isinstance(event, dict):
                continue
            action = event.get("Action")
            action_data = (action or {}).get("LevelThymedEventActionData") if isinstance(action, dict) else None
            levels = (action_data or {}).get("Levels") if isinstance(action_data, dict) else None
            levels = [str(item) for item in levels] if isinstance(levels, list) else []
            events.append({
                "name": event.get("EventName"),
                "uniqueId": event.get("UniqueID"),
                "package": THYME_PKG,
                "startDate": event.get("StartDate"),
                "endDate": event.get("EndDate"),
                "startUtc": iso_utc(event.get("StartDate")),
                "endUtc": iso_utc(event.get("EndDate")),
                "comingSoonEnableTime": event.get("ComingSoonEnableTime"),
                "disabled": event.get("Disabled"),
                "levels": levels,
                "isNew": event.get("UniqueID") in THYME_NEW_IDS,
                "raw": event,
            })
        break
    if not events:
        unknowns.append({
            "kind": "thyme-missing",
            "count": 1,
            "detail": "%s 里没有带 Events 列表的 %s 对象" % (THYME_PKG_FILE, THYME_CLS),
            "probe": "打印该包 objclass 列表",
            "samples": [THYME_CLS],
        })
    empty = [row["uniqueId"] for row in events if not row["levels"]]
    if empty:
        unknowns.append({
            "kind": "thyme-levels-empty",
            "count": len(empty),
            "detail": "这些事件的 Action.LevelThymedEventActionData.Levels 取不到，"
                      "levels 记空数组而不是猜",
            "probe": "打印 Action 的完整键，确认结构有没有变",
            "samples": empty[:8],
        })
    events.sort(key=lambda row: (int(row["uniqueId"] or 0), str(row["name"] or "")))
    return events


# --------------------------------------------------------------------- builder

def compile_data(obb: Path = DEFAULT_OBB, levels_dir: Path = DEFAULT_LEVELS) -> dict:
    unknowns: list[dict] = []
    mapping = level_index(levels_dir) if levels_dir.is_dir() else {}
    if not mapping:
        unknowns.append({
            "kind": "levels-index-empty",
            "count": 1,
            "detail": "%s 下没有可用的 extra.package 映射" % levels_dir,
            "probe": "确认 content/levels 是否已生成",
            "samples": [],
        })
    rl_config = collect_rl_config(obb, unknowns)
    level_flags = collect_level_flags(obb, mapping, unknowns)
    thyme = collect_thyme_events(obb, unknowns)

    flags = Counter(row["suppressFlagZombie"] for row in level_flags)
    packages_scanned = len(list(obb.glob("pkg_*.json"))) if obb.is_dir() else 0
    counts = {
        "rlConfig": 0 if rl_config is None else 1,
        "rlConfigFields": 0 if rl_config is None else len(rl_config.get("raw") or {}),
        "levelFlags": len(level_flags),
        "levelFlagsTrue": flags.get(True, 0),
        "levelFlagsFalse": flags.get(False, 0),
        "levelFlagsNull": flags.get(None, 0),
        "levelFlagPackages": len({row["package"] for row in level_flags}),
        "levelFlagsMapped": sum(1 for row in level_flags if row["levelId"]),
        "thymeEvents": len(thyme),
        "thymeEventsNew": sum(1 for row in thyme if row["isNew"]),
        "thymeEventLevelRefs": sum(len(row["levels"]) for row in thyme),
        "newThymeUniqueIds": sorted(THYME_NEW_IDS),
        "packagesScanned": packages_scanned,
        "clientLevels": len(mapping),
        "unknowns": len(unknowns),
    }
    return {
        "format": FORMAT,
        "source": {
            "generated": GENERATED,
            "obbDirName": obb.name,
            "packagesScanned": packages_scanned,
            "rlConfig": RL_PKG_FILE,
            "thymeEvents": THYME_PKG_FILE,
            "levelDefinition": LEVEL_GLOB,
            "clientLevels": "content/levels",
            "clientLevelsIndexed": len(mapping),
            "flagKey": FLAG_KEY,
            "flagScopeNote": "该键不是 460.9 独有：全库 271 关都有，460.9 只是把 "
                             "pkg_0416（memorytour_2）从缺键改成 true",
            "newThymeEvents": "与 460.1（%s）比对 UniqueID：新增 29/30/31，"
                              "三条都是 [EVENT_TIMESPACEECHOES_BACK] 回流" % THYME_BASELINE_DIR,
        },
        "counts": counts,
        "rlConfig": rl_config,
        "levelFlags": level_flags,
        "thymeEvents": thyme,
        "unknowns": unknowns,
    }


def render(data: dict) -> str:
    """紧凑 JSON：``separators`` 去空格、``sort_keys`` 定序，末尾一个换行。"""
    return json.dumps(data, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")) + "\n"


def dump(data: dict, path: Path) -> None:
    """``write_bytes`` 而不是 ``write_text``：Windows 上后者会写 CRLF，
    与 ``render()`` 的字节不一致，``--check`` 就永远红。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(render(data).encode("utf-8"))


# ----------------------------------------------------------------- validation

def validate(data: dict) -> list[str]:
    problems: list[str] = []
    for key in ("format", "source", "counts", "rlConfig", "levelFlags",
                "thymeEvents", "unknowns"):
        if key not in data:
            problems.append("缺少顶层键 %s" % key)
    counts = data.get("counts") or {}
    flags = data.get("levelFlags") or []
    thyme = data.get("thymeEvents") or []
    if counts.get("levelFlags") != len(flags):
        problems.append("counts.levelFlags=%r 与 levelFlags 长度 %d 不一致"
                        % (counts.get("levelFlags"), len(flags)))
    if counts.get("thymeEvents") != len(thyme):
        problems.append("counts.thymeEvents=%r 与 thymeEvents 长度 %d 不一致"
                        % (counts.get("thymeEvents"), len(thyme)))
    if counts.get("unknowns") != len(data.get("unknowns") or []):
        problems.append("counts.unknowns 与 unknowns 长度不一致")
    if counts.get("levelFlagsTrue", 0) + counts.get("levelFlagsFalse", 0) + \
            counts.get("levelFlagsNull", 0) != len(flags):
        problems.append("levelFlags 的 true/false/null 三分支求和 != 行数")
    for row in flags:
        if not isinstance(row.get("suppressFlagZombie"), (bool, type(None))):
            problems.append("suppressFlagZombie 不是布尔：%r（%s）"
                            % (row.get("suppressFlagZombie"), row.get("levelId")))
        if row.get("levelId") is None:
            problems.append("levelId 为空的行必须进 unknowns：%s" % row.get("package"))
    ids = [str(row.get("levelId")) for row in flags]
    if ids != sorted(ids):
        problems.append("levelFlags 未按 levelId 排序")
    unique = [row.get("uniqueId") for row in thyme]
    if unique != sorted(unique, key=lambda value: int(value or 0)):
        problems.append("thymeEvents 未按 uniqueId 排序")
    if counts.get("thymeEventsNew") != sum(1 for row in thyme if row.get("isNew")):
        problems.append("counts.thymeEventsNew 与 isNew 数量不一致")
    rl = data.get("rlConfig")
    if rl is not None and not isinstance(rl.get("raw"), dict):
        problems.append("rlConfig.raw 必须是对象")
    return problems


def check(data: dict, out_path: Path) -> int:
    problems = validate(data)
    if not out_path.is_file():
        print("产物不存在：%s" % out_path)
        return 1
    raw = out_path.read_bytes()
    if b"\r\n" in raw:
        problems.append("产物含 CRLF（应为 LF）")
    if not raw.endswith(b"\n"):
        problems.append("产物末尾缺换行")
    if raw != render(data).encode("utf-8"):
        problems.append("产物与当前 OBB 重算结果不一致（已过期，重跑不带 --check）")
    counts = data.get("counts") or {}
    print("patch_460_9 rlConfig=%d levelFlags=%d(true %d/false %d) "
          "thymeEvents=%d(new %d) unknowns=%d"
          % (counts.get("rlConfig", 0), counts.get("levelFlags", 0),
             counts.get("levelFlagsTrue", 0), counts.get("levelFlagsFalse", 0),
             counts.get("thymeEvents", 0), counts.get("thymeEventsNew", 0),
             counts.get("unknowns", 0)))
    for problem in problems:
        print("  ! %s" % problem)
    if problems:
        return 1
    print("OK")
    return 0


def baseline_diff(obb: Path, data: dict) -> None:
    """现场与 460.1 包树比对事件 UniqueID（只打印，不进产物）。"""
    base = obb.parent / THYME_BASELINE_DIR / THYME_PKG_FILE
    if not base.is_file():
        print("基线不存在：%s" % base)
        return
    old_ids = set()
    for obj in objects(base):
        raw = data_of(obj).get("Events")
        if isinstance(raw, list):
            old_ids = {event.get("UniqueID") for event in raw if isinstance(event, dict)}
            break
    new_ids = {row["uniqueId"] for row in data.get("thymeEvents") or []}
    print("baseline %s: %d events" % (THYME_BASELINE_DIR, len(old_ids)))
    print("current: %d events" % len(new_ids))
    print("added:", sorted(new_ids - old_ids))
    print("removed:", sorted(old_ids - new_ids))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="460.9 新增数据 -> patch_460_9.json")
    parser.add_argument("--obb", default=str(DEFAULT_OBB), help="OBB 解包目录")
    parser.add_argument("--levels", default=str(DEFAULT_LEVELS), help="content/levels 目录")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="产物路径")
    parser.add_argument("--check", action="store_true", help="只校验产物是否最新")
    parser.add_argument("-n", "--dry-run", action="store_true", help="只打印摘要，不写盘")
    parser.add_argument("--baseline", action="store_true", help="额外打印与 460.1 的事件差异")
    args = parser.parse_args(argv)

    obb = Path(args.obb).expanduser()
    out = Path(args.out)
    if not obb.is_dir():
        print("OBB 目录不存在：%s（可用 PVZ2_OBB_DIR 指定）" % obb, file=sys.stderr)
        return 2

    data = compile_data(obb, Path(args.levels).expanduser())
    if args.check:
        return check(data, out)

    counts = data["counts"]
    print("RlConfig: fields=%d package=%s"
          % (counts["rlConfigFields"], (data.get("rlConfig") or {}).get("package")))
    print("levelFlags: %d 关（true %d / false %d / null %d），包 %d 个，映射到客户端 id %d 个"
          % (counts["levelFlags"], counts["levelFlagsTrue"], counts["levelFlagsFalse"],
             counts["levelFlagsNull"], counts["levelFlagPackages"],
             counts["levelFlagsMapped"]))
    print("thymeEvents: %d 条（新增 %d 条：%s）"
          % (counts["thymeEvents"], counts["thymeEventsNew"],
             sorted(row["uniqueId"] for row in data["thymeEvents"] if row["isNew"])))
    print("unknowns: %d" % counts["unknowns"])
    problems = validate(data)
    if problems:
        for problem in problems:
            print("  ! %s" % problem, file=sys.stderr)
        return 1
    if args.baseline:
        baseline_diff(obb, data)
    if args.dry_run:
        return 0
    dump(data, out)
    print("输出: %s" % out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
