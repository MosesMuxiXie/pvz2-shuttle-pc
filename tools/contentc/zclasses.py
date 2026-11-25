"""Map the shipped ZombieClass values onto the engine's six behaviour families.

Usage:
    python tools/contentc/zclasses.py            # write both generated artifacts
    python tools/contentc/zclasses.py --check    # verify the artifacts match the sheets
    python tools/contentc/zclasses.py -n         # print the family table, write nothing

Why this exists: the original build names 183 distinct ``ZombieClass`` values across
its 1127 zombie types, while ``native/src/engine`` only implements six behaviour
families (``walk / jump / steal / summon / gargantuar / fly``). The C++ side needs a
class -> family table it can include, and a reviewer needs to see why each class was
put where it is. So every decision is derived from the shipped sheets, not from the
class name:

1. ``jump``      -- the properties of the class's types reference a ``*Jump*`` /
                    ``*Vault*`` action in ``ZombieActions``.
2. ``steal``     -- the types use a ``..._BUNGEE`` animation (the only plant-stealing
                    behaviour this build ships); ``ZombieActions`` has no steal verb.
3. ``walk``      -- ``IsBasicZombie`` is true for at least half of the class's types,
                    or nothing below applies.
4. ``gargantuar``-- at least half of the types use a PopAnim containing
                    ``GARGANTUAR`` / ``ZOMBOSS`` / ``MECH``.
5. ``fly``       -- at least half of the types set ``IsSpawnedFlying`` on their
                    ``ZombieProperties``.
6. ``summon``    -- at least half of the types reference a ``*Spawn*`` / ``*Summon*``
                    action, or the class name is one of the known minion families
                    (Chicken / Weasel / Statue), which only exist as summons.
7. everything else is ``walk`` with the evidence that nothing special was found.

Thresholds are "at least half of the class's own types", because a ZombieClass is a
shared base: ``ZombieBasic`` owns 240 types and a handful of them (a fairy imp, a
cavalry gun) carry spawn actions. Judging by any-single-type would turn the whole
basic family into a summoner.

``OVERRIDES`` records the handful of classes where the shipped data and the real
behaviour disagree (art reuse, boss vehicles, jump behaviours that only exist as
animation). Each one is written as ``human override: <reason>`` in the record note, so
a reviewer can grep for them.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.contentc import emit, sheets  # noqa: E402
from tools.contentc.rtid import parse_rtid  # noqa: E402
import os

DEFAULT_OBB = Path(os.environ.get("PVZ2_OBB_DIR") or (ROOT.parent.parent / "work" / "obb_packages"))
DEFAULT_JSON = ROOT / "native" / "generated" / "zombie_classes.json"
DEFAULT_INC = ROOT / "native" / "generated" / "zombie_family_table.inc"

FAMILIES = ("walk", "jump", "steal", "summon", "gargantuar", "fly")

GARGANTUAR_TOKENS = ("GARGANTUAR", "ZOMBOSS", "MECH")
MINION_TOKENS = ("Chicken", "Weasel", "Statue")

# className -> (family, reason). Only for classes where the shipped data and the
# behaviour the engine implements disagree; every reason is shown in the JSON.
OVERRIDES: dict[str, tuple[str, str]] = {
    "ZombieBull": (
        "jump",
        "2 of its 3 types are pole vaulters (modern_polevaulting, pool_polevaulting with "
        "POPANIM_ZOMBIE_ZOMBIE_MODERN_POLE_VAULTING); ZombieActions carries no Jump entry for them",
    ),
    "ZombieBullVeteran": (
        "jump",
        "bull rider veteran shares the charging jump of ZombieBull; PopAnim WEST_BULLRIDER_VETERAN",
    ),
    "ZombieModernPoleVaulting": (
        "jump",
        "PopAnim POPANIM_ZOMBIE_ZOMBIE_POLE_VAULTING; the vault is an animation, not a ZombieActions entry",
    ),
    "ZombieModernPogo": (
        "jump",
        "PopAnim POPANIM_ZOMBIE_ZOMBIE_POGO; pogo hopping is animation-only in this build",
    ),
    "ZombieModernDolphinRider": (
        "jump",
        "PopAnim POPANIM_ZOMBIE_ZOMBIE_MODERN_DOLPHINRIDER; the dolphin leaps over plants",
    ),
    "ZombieParkour": (
        "jump",
        "PopAnim POPANIM_ZOMBIE_ZOMBIE_PARKOUR_RUNNER; the runner vaults obstacles",
    ),
    "ZombieZCorpGargantuar": (
        "gargantuar",
        "type zcorp_gargantuar reuses the POPANIM_..._CORPORATE_IMP art (art reuse), it is a gargantuar",
    ),
    "ZombieZCorpImp": (
        "walk",
        "type zcorp_imp reuses the POPANIM_..._CORPORATE_GARGANTUAR art (art reuse), it is an imp",
    ),
    "ZombieZombossMech_Goon": (
        "gargantuar",
        "market Zomboss mech (zombossmech_market) keeps the boss-vehicle behaviour",
    ),
    "ZombieCakeTank": (
        "gargantuar",
        "boss/vehicle base class: its 43 types include caketank, nian_beast, wealth_god, "
        "steam_train and the renai statues, and bosses stay in the gargantuar family",
    ),
    "ZombieCarnieMagician": (
        "summon",
        "18 of 37 types reference Spawn actions (carnie_magician, fairy_tale_imp, "
        "fairy_tale_knight_spawner); the ratio misses the 0.5 threshold by one type",
    ),
    "ZombieFireball": (
        "walk",
        "its only type is an effect/projectile (fireball) whose PopAnim happens to start with "
        "EFFECTS_ZOMBOSS; it is not a gargantuar",
    ),
    "ZombieMausoleumOrb": (
        "walk",
        "both types are projectiles (mausoleum_fireball/iceball) with EFFECTS_ZOMBOSS art, not gargantuars",
    ),
}


@dataclass(frozen=True)
class ClassRecord:
    class_name: str
    family: str
    evidence: list[str]
    sample_types: list[str]
    count: int
    note: str

    def as_json(self) -> dict:
        return {
            "className": self.class_name,
            "family": self.family,
            "evidence": list(self.evidence),
            "sampleTypes": list(self.sample_types),
            "count": self.count,
            "note": self.note,
        }


@dataclass
class TypeFacts:
    type_name: str
    pop_anim: str
    is_basic: bool
    is_flying: bool
    jump_actions: list[str]
    summon_actions: list[str]
    properties_missing: bool


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _property_lookup(loaded: sheets.Sheets) -> dict[str, dict]:
    table = loaded.get("ZombieProperties")
    lookup: dict[str, dict] = {}
    if table is None:
        return lookup
    for obj in table.objects:
        for name in [obj.get("objclass")] + list(obj.get("aliases") or []):
            if name and name not in lookup:
                lookup[name] = obj.get("objdata") or {}
    return lookup


def _action_names(property_data: dict) -> list[str]:
    names: list[str] = []
    for raw in property_data.get("Actions") or []:
        parsed = parse_rtid(raw)
        names.append(parsed[0] if parsed else str(raw))
    return names


def load_facts(obb_dir: Path) -> dict[str, list[TypeFacts]]:
    loaded = sheets.load_sheets(obb_dir)
    zombie_types = loaded.get("ZombieTypes")
    if zombie_types is None:
        raise SystemExit(f"error: ZombieTypes sheet not found under {obb_dir}")
    properties = _property_lookup(loaded)

    by_class: dict[str, list[TypeFacts]] = defaultdict(list)
    for obj in zombie_types.objects:
        data = obj.get("objdata") or {}
        class_name = str(data.get("ZombieClass") or "")
        if not class_name:
            continue
        parsed = parse_rtid(data.get("Properties"))
        property_data = properties.get(parsed[0]) if parsed else None
        missing = property_data is None
        actions = _action_names(property_data) if property_data else []
        lowered = [action.lower() for action in actions]
        by_class[class_name].append(
            TypeFacts(
                type_name=str(data.get("TypeName") or ""),
                pop_anim=str(data.get("PopAnim") or ""),
                is_basic=bool(data.get("IsBasicZombie")),
                is_flying=bool(property_data.get("IsSpawnedFlying")) if property_data else False,
                jump_actions=[a for a, low in zip(actions, lowered) if "jump" in low or "vault" in low],
                summon_actions=[a for a, low in zip(actions, lowered) if "spawn" in low or "summon" in low],
                properties_missing=missing,
            )
        )
    return dict(by_class)


def _ratio(count: int, total: int) -> str:
    return f"{count}/{total}"


def classify(class_name: str, facts: list[TypeFacts]) -> ClassRecord:
    total = len(facts)
    evidence: list[str] = []
    samples = [fact.type_name for fact in facts[:3]]
    missing = sum(1 for fact in facts if fact.properties_missing)

    def count_where(predicate) -> int:
        return sum(1 for fact in facts if predicate(fact))

    jump = count_where(lambda fact: bool(fact.jump_actions))
    steal = count_where(lambda fact: "BUNGEE" in fact.pop_anim.upper())
    basic = count_where(lambda fact: fact.is_basic)
    gargantuar = count_where(
        lambda fact: any(token in fact.pop_anim.upper() for token in GARGANTUAR_TOKENS)
    )
    flying = count_where(lambda fact: fact.is_flying)
    summon = count_where(lambda fact: bool(fact.summon_actions))

    family = ""
    note = ""
    if jump * 2 >= total:
        family = "jump"
        example = next(fact.jump_actions[0] for fact in facts if fact.jump_actions)
        evidence.append(f"{_ratio(jump, total)} types reference a Jump/Vault action in ZombieActions (e.g. {example})")
        note = "Jump/Vault action present on at least half of the class's types"
    elif steal * 2 >= total:
        family = "steal"
        evidence.append(f"PopAnim of {_ratio(steal, total)} types contains BUNGEE (the only plant-stealing behaviour shipped)")
        note = "bungee-style animation on at least half of the class's types"
    elif basic * 2 >= total:
        family = "walk"
        evidence.append(f"{_ratio(basic, total)} types have IsBasicZombie=true in the ZombieTypes sheet")
        note = "basic walker per IsBasicZombie"
    elif gargantuar * 2 >= total:
        family = "gargantuar"
        evidence.append(
            f"PopAnim of {_ratio(gargantuar, total)} types contains one of {', '.join(GARGANTUAR_TOKENS)}"
        )
        note = "gargantuar/zomboss/mech animation on at least half of the class's types"
    elif flying * 2 >= total:
        family = "fly"
        evidence.append(f"{_ratio(flying, total)} types set IsSpawnedFlying=true in their ZombieProperties")
        note = "flying zombie per IsSpawnedFlying"
    elif summon * 2 >= total:
        family = "summon"
        example = next(fact.summon_actions[0] for fact in facts if fact.summon_actions)
        evidence.append(f"{_ratio(summon, total)} types reference a Spawn/Summon action (e.g. {example})")
        note = "spawner per ZombieActions"
    else:
        token = next((word for word in MINION_TOKENS if word in class_name), None)
        if token is not None:
            family = "summon"
            evidence.append(
                f"class name contains the minion token `{token}`; this family only exists as a summon "
                f"and no walker evidence was found ({_ratio(basic, total)} basic, "
                f"{_ratio(summon, total)} spawn actions)"
            )
            note = "minion-summon family name, no walker evidence"
        else:
            family = "walk"
            evidence.append(
                f"no Jump/Vault, Spawn/Summon, flying or gargantuar evidence in the properties of the {total} type(s)"
            )
            note = "no special actions in ZombieActions"

    if missing:
        evidence.append(f"{_ratio(missing, total)} types reference a ZombieProperties entry missing from this build")

    override = OVERRIDES.get(class_name)
    if override is not None:
        override_family, reason = override
        if override_family != family:
            evidence.append(f"rule evidence alone said {family}; human review disagrees")
        family = override_family
        note = f"human override: {reason}"

    return ClassRecord(
        class_name=class_name,
        family=family,
        evidence=evidence,
        sample_types=samples,
        count=total,
        note=note,
    )


def build(obb_dir: Path) -> dict:
    by_class = load_facts(obb_dir)
    records = [classify(name, by_class[name]) for name in sorted(by_class)]

    counts: dict[str, int] = {family: 0 for family in FAMILIES}
    for record in records:
        counts[record.family] += 1

    notes = [
        "className -> engine family, derived from the shipped sheets (pkg_2115 ZombieType, "
        "pkg_2112 ZombieProperties, pkg_2111 ZombieActions).",
        "A class is judged by at least half of its own types, because ZombieClass is a shared base "
        "(ZombieBasic owns 240 types, a few of which carry spawn actions).",
        "steal has no ZombieActions verb in this build; it is detected from the ..._BUNGEE animation. "
        "ZombieLostCityRelicHunter is the only class that reaches it (2 of its 3 types are bungees), "
        "so the ordinary relic-hunter type shares that base class.",
        "generated is a fixed marker, not a timestamp, so two runs are byte-identical.",
    ]
    if OVERRIDES:
        notes.append(f"{len(OVERRIDES)} classes carry a human override; every one is marked in its note.")

    return {
        "format": 1,
        "generated": "tools/contentc/zclasses.py (deterministic; no timestamp)",
        "source": {
            "sheet": "pkg_2115_ZombieType.json",
            "sha256": _sha256(obb_dir / "pkg_2115_ZombieType.json"),
            "propertySheet": "pkg_2112_ZombiePropertySheet.json",
            "propertySha256": _sha256(obb_dir / "pkg_2112_ZombiePropertySheet.json"),
            "actionSheet": "pkg_2111_ZombieWalkActionDefinition.json",
            "actionSha256": _sha256(obb_dir / "pkg_2111_ZombieWalkActionDefinition.json"),
        },
        "classes": [record.as_json() for record in records],
        "countsByFamily": counts,
        "notes": notes,
    }


def render_json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def render_inc(payload: dict) -> str:
    lines = ["// generated by tools/contentc/zclasses.py -- do not edit"]
    for record in payload["classes"]:
        lines.append('{"%s", "%s"},' % (record["className"], record["family"]))
    return "\n".join(lines) + "\n"


def summarize(payload: dict) -> str:
    counts = payload["countsByFamily"]
    parts = [f"classes={len(payload['classes'])}"]
    parts.append("families=" + " ".join(f"{family}={counts[family]}" for family in FAMILIES))
    parts.append("overrides=" + str(sum(1 for record in payload["classes"] if record["note"].startswith("human override"))))
    return " ".join(parts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Map ZombieClass values onto engine behaviour families.")
    parser.add_argument("--obb", type=Path, default=DEFAULT_OBB)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--inc", type=Path, default=DEFAULT_INC)
    parser.add_argument("--check", action="store_true", help="fail if the generated files differ")
    parser.add_argument("-n", "--dry-run", action="store_true", help="print the summary, write nothing")
    args = parser.parse_args(argv)

    if not args.obb.is_dir():
        print(f"error: property sheets not found: {args.obb}", file=sys.stderr)
        return 2

    payload = build(args.obb)
    document = render_json(payload)
    table = render_inc(payload)
    print(summarize(payload))

    if args.dry_run:
        return 0

    if args.check:
        problems: list[str] = []
        for path, expected in ((args.json, document), (args.inc, table)):
            if not path.is_file():
                problems.append(f"missing: {path}")
            elif path.read_text(encoding="utf-8") != expected:
                problems.append(f"stale: {path}")
        for problem in problems:
            print(problem, file=sys.stderr)
        return 1 if problems else 0

    emit.write_text(args.json, document)
    emit.write_text(args.inc, table)
    print(f"wrote {args.json}, {args.inc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
