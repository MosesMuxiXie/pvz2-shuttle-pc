"""SHUTTLE 版元素反应系统（26.10.1 版本核心机制）。

参考 SHUTTLE 官方 26.10.1 更新说明：植物/僵尸攻击带有元素（水/火/冰/雷/风），
命中已附着其他元素的实体时触发反应：

- 蒸发（水打火）：伤害 ×2，清除火元素
- 融化（火打冰）：伤害 ×2，清除冰元素
- 融化（冰打火）：伤害 ×1.5，清除火元素
- 冻结（水 + 冰）：冻结 1.5 秒
- 感电（水 + 雷）：清除水/雷，对 3x3 范围造成等同于本次攻击的雷伤（上限 1000）
- 超导（雷 + 冰）：清除雷/冰，目标受到物理伤害 +75%，持续 10 秒
- 超载（雷 + 火）：清除雷/火，3x3 范围 40 点火伤
- 扩散（风打水/火/雷/冰）：清除该元素，3x3 范围 10 点风伤，并按元素附着 5 秒（冰为 2 秒减速）

本模块是纯逻辑：不 import 引擎其他模块，便于单测和替换。
集成方式：攻击命中时调用 :func:`resolve_hit`，用返回的倍率结算伤害，
再按返回的 effects 交给 LevelSession 应用（冻结/范围伤害/易伤）。
"""
from __future__ import annotations

# 元素常量
WATER, FIRE, ICE, THUNDER, WIND = "water", "fire", "ice", "thunder", "wind"
ELEMENTS = (WATER, FIRE, ICE, THUNDER, WIND)

ELEMENT_NAME = {
    WATER: "水", FIRE: "火", ICE: "冰", THUNDER: "雷", WIND: "风",
    None: "物理",
}
ELEMENT_COLOR = {
    WATER: (80, 190, 255), FIRE: (255, 120, 40), ICE: (176, 230, 255),
    THUNDER: (255, 230, 80), WIND: (48, 224, 208), None: (230, 230, 230),
}

# 附着时长（秒）
ATTACH_SECONDS = {WATER: 5.0, FIRE: 5.0, THUNDER: 5.0, ICE: 2.0, WIND: 5.0}

# 反应表：frozenset({攻击元素, 已附着元素}) -> 反应规格
# mult 为伤害倍率，effects 为附加效果（引擎侧解释）
_REACTIONS = {
    frozenset((WATER, FIRE)): {
        "name": "蒸发", "mult": 2.0, "clear": (FIRE,), "effects": [],
    },
    frozenset((FIRE, ICE)): {
        "name": "融化", "mult": 2.0, "clear": (ICE,), "effects": [],
    },
    frozenset((WATER, ICE)): {
        "name": "冻结", "mult": 1.0, "clear": (WATER, ICE),
        "effects": [{"type": "freeze", "seconds": 1.5}],
    },
    frozenset((WATER, THUNDER)): {
        "name": "感电", "mult": 1.0, "clear": (WATER, THUNDER),
        "effects": [{"type": "aoe", "damage": "attack", "cap": 1000.0,
                     "radius": 190.0, "element": THUNDER}],
    },
    frozenset((THUNDER, ICE)): {
        "name": "超导", "mult": 1.0, "clear": (THUNDER, ICE),
        "effects": [{"type": "vulnerable", "mult": 0.75, "seconds": 10.0}],
    },
    frozenset((THUNDER, FIRE)): {
        "name": "超载", "mult": 1.0, "clear": (THUNDER, FIRE),
        "effects": [{"type": "aoe", "damage": 40.0, "radius": 190.0,
                     "element": FIRE}],
    },
    frozenset((WIND, WATER)): {"name": "扩散", "mult": 1.0, "clear": (WATER,),
                               "effects": [{"type": "spread", "element": WATER}]},
    frozenset((WIND, FIRE)): {"name": "扩散", "mult": 1.0, "clear": (FIRE,),
                              "effects": [{"type": "spread", "element": FIRE}]},
    frozenset((WIND, THUNDER)): {"name": "扩散", "mult": 1.0, "clear": (THUNDER,),
                                 "effects": [{"type": "spread", "element": THUNDER}]},
    frozenset((WIND, ICE)): {"name": "扩散", "mult": 1.0, "clear": (ICE,),
                             "effects": [{"type": "spread", "element": ICE}]},
}

# 部分植物的默认元素（content/plants.json 里可用 "element" 字段覆盖）
DEFAULT_PLANT_ELEMENT = {
    "snowpea": ICE, "wintermelon": ICE, "winter_melon": ICE, "iceshroom": ICE,
    "ice_shroom": ICE, "iceberg_lettuce": ICE,
    "jalapeno": FIRE, "cherry_bomb": FIRE, "cherrybomb": FIRE, "torchwood": FIRE,
    "cattail": WATER, "bloomerang": WIND, "blover": WIND,
    "magnifyinggrass": THUNDER, "magnifying_grass": THUNDER,
}


def element_of_plant(pdef) -> str | None:
    """从 PlantDef 推断攻击元素。"""
    if pdef is None:
        return None
    extra = getattr(pdef, "extra", None) or {}
    elem = extra.get("element") or DEFAULT_PLANT_ELEMENT.get(getattr(pdef, "id", ""))
    return elem if elem in ELEMENTS else None


def attached_elements(entity) -> dict:
    """实体当前附着元素 -> 剩余秒数。"""
    d = getattr(entity, "elements", None)
    return d if isinstance(d, dict) else {}


def attach(entity, element: str, seconds: float | None = None) -> None:
    if element not in ELEMENTS:
        return
    d = getattr(entity, "elements", None)
    if not isinstance(d, dict):
        d = {}
        entity.elements = d
    sec = ATTACH_SECONDS.get(element, 5.0) if seconds is None else seconds
    d[element] = max(float(d.get(element, 0.0)), float(sec))


def clear(entity, elements) -> None:
    d = attached_elements(entity)
    for e in elements:
        d.pop(e, None)


def tick(entity, dt: float) -> None:
    """推进附着计时。"""
    d = attached_elements(entity)
    if not d:
        return
    for e in list(d.keys()):
        d[e] = float(d[e]) - float(dt)
        if d[e] <= 0:
            d.pop(e, None)


def resolve_hit(target, element: str, base_damage: float) -> dict:
    """计算一次元素攻击命中。

    返回::

        {"mult": 倍率, "reaction": 反应名|None, "effects": [...], "attached": 当前附着}

    纯计算，不修改目标（除清除反应元素由调用方通过 effects 执行）。
    """
    out = {"mult": 1.0, "reaction": None, "effects": [], "attached": dict(attached_elements(target))}
    if element not in ELEMENTS:
        return out
    present = [e for e in attached_elements(target) if e in ELEMENTS]
    # 选择存在的元素里与攻击元素能反应的一个（优先非风）
    for other in present:
        if other == element:
            continue
        spec = _REACTIONS.get(frozenset((element, other)))
        if spec is None:
            continue
        mult = float(spec["mult"])
        # 融化方向差异：火打冰 ×2，冰打火 ×1.5
        if spec["name"] == "融化" and element == ICE and other == FIRE:
            mult = 1.5
        out["reaction"] = spec["name"]
        out["mult"] = mult
        effects = []
        for eff in spec["effects"]:
            e = dict(eff)
            if e.get("type") == "aoe" and e.get("damage") == "attack":
                e["damage"] = min(float(base_damage), float(e.get("cap", 1000.0)))
            effects.append(e)
        out["effects"] = effects
        out["clear"] = tuple(spec["clear"])
        out["reaction_element"] = element
        return out
    return out
