"""把 Python 基线的元素系统编译成显式标为自创（authored）的数据层。

三份证据表明元素不是原版 SHUTTLE 机制（见 `docs/reviews/2026-11-20-elements-authored.md`）：

1. `ElementReactionModuleProperties` 在 obb 里有 21 条 objdata，全部是空对象 `{}`；
2. `pkg_2073_PlantPropertySheet.json` 的 1075 个字段里没有任何 element 字段；
3. 1809 个关卡 JSON 的 `extra` 里没有任何 element 键。

因此本模块把 `game/engine/elements.py` 的元素与反应表编译成可选数据层，并给每个元素、
每条反应都打上 `source: "authored"` 与 `rationale`（引用基线里的具体规则），避免被当成
原版数据使用。

数据形状（`native/generated/elements.json`）::

    {
      "format": 1,
      "source": "authored",
      "note": "not an original SHUTTLE mechanic",
      "marker": "elements-authored-v1",
      "elements": [{"id", "name_zh", "color", "attachSeconds", "source", "rationale"}],
      "reactions": [{"a", "b", "name_zh", "mult", "clear", "effects",
                     "source", "rationale", "directional"?}]
    }

约定：

- 反应按无序对存储，`a`/`b` 依基线 `ELEMENTS` 的先后排序，同一对只出现一次；
- 基线里「融化」的倍率依赖方向（火打冰 ×2.0、冰打火 ×1.5，后者写死在 `resolve_hit`
  而不是反应表里），数据层用 `directional` 字段如实记录，不静默选一个；
- 未知元素（不在基线 `ELEMENTS` 里的 id）一律不生成，并在 `skipped` 里统计，
  留给报告说明，不做推测；
- 输出确定：`sort_keys`、`indent=1`、UTF-8、LF、末尾换行，无时间戳。

运行::

    python tools/contentc/elements_authored.py
    python tools/contentc/elements_authored.py --check
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_BASELINE = ROOT / "game" / "engine" / "elements.py"
DEFAULT_JSON = ROOT / "native" / "generated" / "elements.json"
DEFAULT_REPORT = ROOT / "docs" / "reviews" / "2026-11-20-elements-authored.md"

FORMAT = 1
SOURCE = "authored"
NOTE = "not an original SHUTTLE mechanic"
MARKER = "elements-authored-v1"

# 基线里写死方向差异的反应（`resolve_hit` 第 148-150 行）。
DIRECTIONAL_RULES = {
    "融化": {"attack": "ice", "attached": "fire", "mult": 1.5},
}


def load_baseline(path: Path):
    """按文件路径加载基线模块（绕开 `game.engine.__init__` 的 pygame 依赖）。"""
    spec = importlib.util.spec_from_file_location("elements_baseline", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"无法加载基线模块：{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _color(value) -> list[int]:
    return [int(value[0]), int(value[1]), int(value[2])]


def _jsonable(value):
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return float(value) if isinstance(value, float) else value
    return value


def _element_rationale(index: int, eid: str, name: str, color: list[int], seconds: float) -> str:
    return (
        f"基线 `ELEMENTS` 第 {index + 1} 位 `{eid}`：中文名「{name}」、"
        f"颜色 RGB{tuple(color)}、附着 {seconds} 秒（`ELEMENT_NAME` / `ELEMENT_COLOR` / "
        f"`ATTACH_SECONDS`）；该机制是 SHUTTLE 26.10.1 的自创规则，原版数据无对应表。"
    )


def _reaction_rationale(a: str, b: str, name: str, mult: float, clear: list[str], effects) -> str:
    cleared = "、".join(clear) if clear else "无"
    payload = json.dumps(_jsonable(effects), ensure_ascii=False, sort_keys=True)
    return (
        f"基线 `_REACTIONS[frozenset(({a!r}, {b!r}))]`：反应「{name}」、倍率 {mult}、"
        f"清除 {cleared}、effects={payload}；按基线原样编译，未做平衡性调整。"
    )


def compile_payload(elements, names, colors, attach, reactions) -> tuple[dict, list[str]]:
    """把基线表编译成数据层；未知元素不进输出，进 skipped 列表。"""
    known = [str(eid) for eid in elements]
    order = {eid: index for index, eid in enumerate(known)}

    out_elements = []
    for eid in known:
        color = _color(colors[eid])
        seconds = float(attach.get(eid, 5.0))
        name = str(names.get(eid, eid))
        out_elements.append(
            {
                "id": eid,
                "name_zh": name,
                "color": color,
                "attachSeconds": seconds,
                "source": SOURCE,
                "rationale": _element_rationale(order[eid], eid, name, color, seconds),
            }
        )

    rows: list[dict] = []
    skipped: list[str] = []
    seen: set[frozenset] = set()
    for pair, spec in reactions.items():
        ids = sorted(pair, key=lambda value: order.get(str(value), len(order)))
        unknown = [str(value) for value in ids if str(value) not in order]
        if len(ids) != 2 or unknown:
            skipped.append("+".join(str(value) for value in ids) or "<empty>")
            continue
        key = frozenset(ids)
        if key in seen:
            skipped.append("+".join(ids) + "（重复对）")
            continue
        seen.add(key)
        a, b = ids[0], ids[1]
        name = str(spec.get("name", ""))
        mult = float(spec.get("mult", 1.0))
        clear = sorted((str(value) for value in spec.get("clear", ())), key=lambda v: order[v])
        effects = [_jsonable(effect) for effect in spec.get("effects", ())]
        row = {
            "a": a,
            "b": b,
            "name_zh": name,
            "mult": mult,
            "clear": clear,
            "effects": effects,
            "source": SOURCE,
            "rationale": _reaction_rationale(a, b, name, mult, clear, effects),
        }
        rule = DIRECTIONAL_RULES.get(name)
        if rule is not None and {rule["attack"], rule["attached"]} == {a, b}:
            row["directional"] = dict(rule)
        rows.append(row)

    rows.sort(key=lambda row: (order[row["a"]], order[row["b"]]))
    payload = {
        "format": FORMAT,
        "source": SOURCE,
        "note": NOTE,
        "marker": MARKER,
        "elements": out_elements,
        "reactions": rows,
    }
    return payload, skipped


def build(baseline_path: Path) -> tuple[dict, list[str]]:
    module = load_baseline(baseline_path)
    return compile_payload(
        module.ELEMENTS,
        module.ELEMENT_NAME,
        module.ELEMENT_COLOR,
        module.ATTACH_SECONDS,
        module._REACTIONS,
    )


def render_json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def _table(header: list[str], rows: list[list[str]]) -> list[str]:
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    for row in rows:
        out.append("| " + " | ".join(row) + " |")
    return out


def render_report(payload: dict, skipped: list[str]) -> str:
    elements = payload["elements"]
    reactions = payload["reactions"]
    element_rows = [
        [
            f"`{item['id']}`",
            item["name_zh"],
            f"RGB{tuple(item['color'])}",
            f"{item['attachSeconds']:g} 秒",
        ]
        for item in elements
    ]
    reaction_rows = []
    for item in reactions:
        clear = "、".join(f"`{value}`" for value in item["clear"]) or "—"
        effects = json.dumps(item["effects"], ensure_ascii=False, sort_keys=True)
        mult = f"{item['mult']:g}"
        if "directional" in item:
            mult += f"（反向 {item['directional']['mult']:g}）"
        reaction_rows.append(
            [
                f"`{item['a']}` + `{item['b']}`",
                item["name_zh"],
                mult,
                clear,
                f"`{effects}`" if item["effects"] else "—",
            ]
        )
    directional = [item for item in reactions if "directional" in item]

    lines: list[str] = []
    lines.append("# 元素层：显式标为自创（authored）")
    lines.append("")
    lines.append(
        "**结论：元素与元素反应不是原版 SHUTTLE 机制。** 本数据层把 Python 基线的元素系统"
        "编译成可选层，每个元素与每条反应都带 `source: \"authored\"` 与 `rationale`，"
        "**不计入原版复刻口径**，只作为可选玩法开关。"
    )
    lines.append("")
    lines.append("## 一、三份证据（原版没有这套机制）")
    lines.append("")
    lines.append("### 1.1 `ElementReactionModuleProperties` 全是空壳")
    lines.append("")
    lines.append(
        "obb 中引用该类名的文件 21 个，`objclass == \"ElementReactionModuleProperties\"` 的 "
        "objdata 恰好 21 条，**非空 0 条**（全部是 `{}`）。探针："
    )
    lines.append("")
    lines.append("```powershell")
    lines.append("cd work/obb_packages")
    lines.append("Select-String -Pattern 'ElementReactionModuleProperties' -List *.json | Measure-Object")
    lines.append("```")
    lines.append("")
    lines.append("```python")
    lines.append("# objdata 计数（21 条，全部为空）")
    lines.append("for p in sorted(OBB.glob('*.json')):")
    lines.append("    text = io.open(p, encoding='utf-8-sig').read()")
    lines.append("    if 'ElementReactionModuleProperties' not in text:")
    lines.append("        continue")
    lines.append("    for cls, data in walk_objects(json.loads(text)):")
    lines.append("        if cls == 'ElementReactionModuleProperties':")
    lines.append("            total += 1; nonempty += bool(data)")
    lines.append("```")
    lines.append("")
    lines.append("实测：`objdata=21, nonempty=0`。模块存在，参数一个都没有。")
    lines.append("")
    lines.append("### 1.2 `PlantPropertySheet` 没有 element 字段")
    lines.append("")
    lines.append(
        "`work/obb_packages/pkg_2073_PlantPropertySheet.json` 共 398 个属性对象、**1075 个不同字段名**，"
        "字段名中含 `lement` 的 0 个。植物属性里没有「攻击元素」这一维。"
    )
    lines.append("")
    lines.append("### 1.3 关卡 `extra` 没有 element 键")
    lines.append("")
    lines.append(
        "`content/levels/*.json` 共 1809 个关卡，`extra` 的键里含 `element` 的 0 个；"
        "关卡数据也没有按元素配置任何东西。"
    )
    lines.append("")
    lines.append(
        "补充：`content/plants.json` 里有 2 条自创字段（`helioscabbage`、`fireflerry` 的顶层 "
        "`element: \"fire\"`），它们同样是本项目自创，不是原版数据，也不在本次编译范围。"
    )
    lines.append("")
    lines.append("## 二、数据层内容")
    lines.append("")
    lines.append(
        f"共 {len(elements)} 个元素、{len(reactions)} 条无序反应对；`source` 统一为 `authored`，"
        "输出 `native/generated/elements.json`"
        f"（`format: {FORMAT}`）。"
    )
    lines.append("")
    lines.append("### 2.1 元素")
    lines.append("")
    lines.extend(_table(["id", "中文名", "颜色", "附着时长"], element_rows))
    lines.append("")
    lines.append("### 2.2 反应矩阵")
    lines.append("")
    lines.extend(_table(["元素对（无序）", "反应", "倍率", "清除", "effects"], reaction_rows))
    lines.append("")
    lines.append("## 三、与 Python 基线的差异")
    lines.append("")
    diff_rows = [
        [
            "物理（`None`）",
            "基线的 `ELEMENT_NAME` / `ELEMENT_COLOR` 里有 `None: 物理` / 灰色",
            "不生成元素行",
            "物理不是元素，只作为「无元素攻击」的占位；数据层只收 5 个真元素",
        ],
        [
            "融化方向",
            "反应表里一对一个 `mult: 2.0`，但 `resolve_hit` 里冰打火被改成 1.5",
            "`mult: 2.0` + `directional: {attack: ice, attached: fire, mult: 1.5}`",
            "两个倍率都如实保留，由引擎按攻击方向选择",
        ],
        [
            "感电范围伤害",
            "`effects[0].damage` 是字符串 `\"attack\"`，运行时才替换为本次攻击力（上限 1000）",
            "原样保留字符串 `\"attack\"` 与 `cap`/`radius`",
            "字符串是动态占位，编译期无法算出具体数值",
        ],
        [
            "默认植物元素",
            "`DEFAULT_PLANT_ELEMENT` 15 个键（含 `winter_melon` 等 8 个本版不存在的 id）",
            "不编译",
            "本任务只编译元素与反应矩阵；默认归属属于植物侧数据，未纳入",
        ],
    ]
    lines.extend(_table(["项", "Python 基线", "本数据层", "理由"], diff_rows))
    lines.append("")
    lines.append("## 四、基线的自相矛盾（保留基线行为，不静默改）")
    lines.append("")
    lines.append(
        "1. **融化倍率与反应表不一致**：`_REACTIONS[frozenset((FIRE, ICE))]` 写 `mult: 2.0`，"
        "但 `resolve_hit` 用 `spec[\"name\"] == \"融化\" and element == ICE and other == FIRE` 把"
        "反向改成 1.5。表本身是无方向的，方向差只存在于代码分支里 → 数据层用 `directional` 记录，"
        "同时保留表值 2.0，不替基线选边。"
    )
    lines.append(
        "2. **超导的 `mult: 0.75` 语义含糊**：文档说「目标受到物理伤害 +75%」，而字段名 `mult` 的"
        "取值 0.75 读起来像「承伤 ×0.75」。两种解释方向相反（更痛 / 更抗打），基线没有进一步的"
        "注释；数据层原样保留 0.75，不擅自改成 1.75。"
    )
    lines.append(
        "3. **扩散的附着时长不在数据里**：模块文档说「按元素附着 5 秒（冰为 2 秒减速）」，"
        "但 `effects` 只有 `{\"type\": \"spread\", \"element\": …}`，没有秒数字段；时长实际由 "
        "`ATTACH_SECONDS` 隐含。数据层保留该形状，并在元素表里给出 `attachSeconds` 供引擎取用。"
    )
    lines.append("")
    lines.append("## 五、口径声明")
    lines.append("")
    lines.append(
        "- 本数据层的元素与反应**全部为自创**，`source` 一律 `authored`，**不计入原版复刻口径**；"
        "任何「原版有元素系统」的说法都与 1.1–1.3 的实测不符。"
    )
    lines.append(
        "- 是否启用由运行时开关决定；不启用时，攻击元素一律按物理处理（基线 `element_of_plant` "
        "对未知元素返回 `None` 的行为）。"
    )
    lines.append(
        "- 生成器 `tools/contentc/elements_authored.py` 的 `--check` 会逐字节校验 `native/generated/elements.json` 与本报告，过期即失败。"
    )
    if skipped:
        lines.append("")
        lines.append("## 六、被跳过的输入")
        lines.append("")
        for item in skipped:
            lines.append(f"- `{item}`（含未知元素或重复对，未生成）")
    lines.append("")
    return "\n".join(lines)


def write_outputs(payload: dict, json_path: Path, report_text: str, report_path: Path) -> None:
    from tools.contentc import emit

    emit.write_text(json_path, render_json(payload))
    emit.write_text(report_path, report_text)


def summarize(payload: dict, skipped: list[str]) -> str:
    names = "、".join(item["name_zh"] for item in payload["reactions"])
    return (
        f"elements={len(payload['elements'])} reactions={len(payload['reactions'])} "
        f"skipped={len(skipped)} names={names}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="编译自创元素层（authored）")
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--check", action="store_true", help="只校验产物是否最新")
    parser.add_argument("-n", "--dry-run", action="store_true", help="只打印摘要，不写盘")
    args = parser.parse_args(argv)

    baseline = Path(args.baseline)
    if not baseline.is_file():
        print(f"基线模块不存在：{baseline}", file=sys.stderr)
        return 2

    payload, skipped = build(baseline)
    report_text = render_report(payload, skipped)
    summary = summarize(payload, skipped)

    if args.check:
        expected = {
            Path(args.json): render_json(payload).encode("utf-8"),
            Path(args.report): report_text.encode("utf-8"),
        }
        stale = [path for path, data in expected.items() if not path.is_file() or path.read_bytes() != data]
        if stale:
            print("产物过期：" + "、".join(str(path) for path in stale), file=sys.stderr)
            return 2
        print(f"产物已是最新：{summary}")
        return 0

    if args.dry_run:
        print(f"dry-run：{summary}")
        return 0

    write_outputs(payload, Path(args.json), report_text, Path(args.report))
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
