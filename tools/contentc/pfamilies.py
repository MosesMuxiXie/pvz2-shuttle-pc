"""Assign one engine behaviour family to every plant type of the pack.

The engine has exactly eleven families - ``shoot``, ``lob``, ``produce``,
``wall``, ``instant``, ``mine``, ``chomp``, ``fume``, ``boomerang``,
``support``, ``spike`` (``native/src/engine/registry.cpp``, ``plantFamilies()``)
- and nothing outside them. ``native/generated/content.pack`` describes 339
plant types, but only 147 of them also exist in ``content/plants.json`` and only
44 of those share an id with the pack. Those 44 ``behavior`` fields are the only
supervised labels in the repository, so the other 295 types have no family at all
until the pack data itself is read.

What the pack does and does not say
-----------------------------------
``content.pack`` carries, per plant, ``framework`` / ``animRig`` / ``popAnim``
names, ``properties.name`` (the original ``PlantPropertySheet`` object), the
flattened ``actions`` list, ``hitpoints``, ``cost``, ``sunProducer``, ``height``
and ``gridType``. It does **not** carry a behaviour class: ``framework`` is an
implementation class and it is reused across behaviours (``PlantPeashooter``
covers ``repeater``, ``tubiflora`` *and* ``taraxacum``; ``PlantPotatomine``
covers ``potatomine``, ``seapotatomine`` *and* ``potatochip``). Family therefore
has to be *derived* from the shape of the action list plus a few original-sheet
fields that the flattening dropped.

Two original sheets restore exactly the fields that decide the hard cases:

* ``pkg_2073_PlantPropertySheet.json`` (``PlantProperties``) - ``IsInstant``,
  ``IsConsumable``, ``CanLiveOnWaves``, ``ProjectileLobHeight``,
  ``Actions[].ExplodeType`` / ``TriggerType`` / ``NeedNumOfEatingToUse``.
  ``IsInstant`` + ``IsConsumable`` is what separates a one-shot plant from a
  repeating one; neither flag survives into the pack.
* ``pkg_2082_ProjectilePropertySheet.json`` (``ProjectileTypes``) - the real
  launch vector of every projectile the plant fires. Lobbed shots carry a
  vertical velocity (``InitialVelocity`` ~[300, +-10, 500..700] with a constant
  -10 vertical acceleration) while straight lane shots are ``[333, 0, 0]`` and
  seed-rain style projectiles are ``[0, 0, -500]``. That vector is the only
  honest way to tell ``lob`` from ``shoot``: the names do not (``wintermelon``
  and ``missiletoast`` lob without any ``Pult``/``Cata`` in the name, while
  ``framework`` for pults is shared with straight shooters).

The OBB is optional: when ``work/obb_packages`` is not next to the repository,
the original-sheet lookups degrade to name/action-shape rules and every affected
evidence string says so (``obb=absent``) instead of pretending to have read them.

Rules (ordered, first match wins)
---------------------------------
Each plant gets exactly one family and an ``evidence`` string naming the rule
that fired. Rules are deliberately ordered strongest-first:

R01 ``produce/sun-action``      a ``sun`` action exists.
R02 ``produce/sun-producer``    ``sunProducer`` is true and there is no attack
                                action at all (a sun producer that also shoots
                                keeps its attack family).
R03 ``chomp/named``             id/props/anim name contains ``chomp``, or an
                                action asks for ``needEating``. A chomper models
                                its bite as a rect projectile, so shape alone
                                would call it ``shoot``.
R04 ``fume/named``              name contains ``fume``. Fume is a short cone
                                attack modelled with a rect_grid projectile.
R05 ``boomerang/named``         name contains ``boomerang``, or a projectile
                                class name does.
R06 ``mine/named``              an attack explosion plus a name containing
                                ``potatomine``. The name - id and
                                ``properties.name`` only - matters:
                                ``potatochip`` shares the framework
                                ``PlantPotatomine`` *and* the art rig
                                ``PlantAnimRig_PotatoMine`` with the mines, and
                                its family is ``instant``.
R07 ``instant/flagged``         ``IsInstant`` is set (and it is not a producer).
R08 ``instant/consumable``      ``IsConsumable`` is set - every one-shot plant in
                                the sheets carries it, including the ones that
                                skip ``IsInstant``.
R09 ``instant/explosion``       an attack explosion is left and the plant fires
                                no projectile. A shooter whose shot explodes on
                                impact (``gardenia``, ``grapeshot``) stays a
                                shooter. ``trigger=manual`` explosions are
                                plant-food effects, not families (``torchwood``).
R10 ``wall/no-actions-high-hp`` no action at all and ``hitpoints >= 1000``.
R11 ``wall/defensive-name``     a defensive name (``*guard*``, ``wallnut``,
                                ``tallnut``, ``pumpkin``, ``endurian``,
                                ``blockoli``, ``hollybarrier``) that still owns
                                an action rig. ``yuccaguardian`` is a barrier
                                that also lobs a 50-damage shot.
R12 ``wall/no-attack-high-hp``  ``hitpoints >= 1000`` and no attack damage at
                                all (``kiwibeast``, ``land``).
R13 ``spike/named``             name contains ``spike``, ``bonk``, ``wasabi`` or
                                ``celery``.
R14 ``spike/melee-special``     no projectile action, a positive ``special``
                                damage and low HP: the pack models melee as a
                                rect special (``bonkchoy``, ``spikeweed``).
R15 ``support/seed-rain``       the primary projectile is a falling seed with no
                                base damage (``taraxacum``).
R16 ``lob/arc``                 the primary projectile is lobbed (arc vector or
                                ``ProjectileLobHeight``).
R17 ``shoot/projectile``        a projectile action is left, with or without a
                                projectile reference (``poppinpoppies`` fires
                                unnamed rect shots).
R18 ``instant/no-action-oneshot`` an explosion/special one-shot with tiny HP.
R19 ``support/no-attack``       no projectile, no explosion and no special
                                damage: pure utility (``hypnoshroom``,
                                ``lilypad``, ``blover``, ``thymewarp`` ...).
R20 ``support/buff-explosion``  the only explosion is plant-food triggered
                                (``torchwood``, ``burnade``).
R21 ``support/catch-all``       nothing above fired. Kept explicit so the output
                                never has a gap; the report counts how many
                                plants fall here.

Usage:
    python tools/contentc/pfamilies.py                      # writes native/generated/plant_families.json
    python tools/contentc/pfamilies.py --check               # verify file + labels, exit code 0
    python tools/contentc/pfamilies.py --out build/fam.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from contentc import worlds  # noqa: E402

REPO = worlds.REPO
DEFAULT_PACK = REPO / "native" / "generated" / "content.pack"
DEFAULT_CONTENT = worlds.DEFAULT_CONTENT
DEFAULT_OBB = worlds.DEFAULT_OBB
DEFAULT_OUT = REPO / "native" / "generated" / "plant_families.json"

FORMAT = "pvz2-shuttle/plant-families@1"

#: The engine's families, in the order `plantFamilies()` lists them.
FAMILIES = (
    "shoot",
    "lob",
    "produce",
    "wall",
    "instant",
    "mine",
    "chomp",
    "fume",
    "boomerang",
    "support",
    "spike",
)

#: The 44 pack plants that also have a `behavior` label in content/plants.json
#: are the supervisable subset of the whole table.
MIN_LABEL_AGREEMENT = 0.90

PROJECTILE_SHEET = "pkg_2082_ProjectilePropertySheet.json"
PLANT_SHEET = "pkg_2073_PlantPropertySheet.json"

# --- name lexicons -----------------------------------------------------------
# Matching is done on a lower-cased, punctuation-stripped blob of the plant's
# *own* names (id, properties.name, animRig, popAnim) and, where a behaviour is
# a property of the implementation class, on a blob that also has `framework`.
# The distinction matters exactly once: `potatochip` shares the framework
# `PlantPotatomine` with the mines but is an instant.
MINE_NAME_RE = re.compile(r"potatomine|teleportatomine")
CHOMP_NAME_RE = re.compile(r"chomp")
FUME_NAME_RE = re.compile(r"fume")
BOOMERANG_NAME_RE = re.compile(r"bloomerang|boomerang")
SPIKE_NAME_RE = re.compile(r"spike|bonk|wasabi|celery")
WALL_NAME_RE = re.compile(
    r"wallnut|tallnut|pumpkin|endurian|blockoli|hollybarrier|"
    r"kelpguarded|kelpguard|chardguard|yuccaguardian"
)
BOOMERANG_CLASS_RE = re.compile(r"boomerang")

#: Velocity classifier for the original projectile sheet.
TRAJ_ARC = "arc"
TRAJ_DROP = "drop"
TRAJ_STRAIGHT = "straight"
TRAJ_NONE = "none"
TRAJ_UNKNOWN = "unknown"


def _strip(name: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(name or "").lower())


@dataclass(frozen=True)
class Projectile:
    """One entry of the original projectile sheet."""

    name: str
    traj: str
    damage: float
    splash: float
    klass: str


@dataclass
class Plant:
    """A pack plant plus the original-sheet facts that decide its family."""

    id: str
    framework: str
    prop_name: str
    anim_rig: str
    pop_anim: str
    hitpoints: float | None
    cost: float | None
    sun_producer: bool
    height: str | None
    grid: str | None
    kinds: tuple[str, ...]
    projectiles: tuple[str, ...]
    explode_actions: tuple[dict, ...]
    special_damage: float
    sun_action: bool
    manual_action: bool
    unknown_action: bool
    needs_eating: bool
    has_projectile_action: bool = False
    projectile_action_damage: float = 0.0
    props: dict = field(default_factory=dict)

    @property
    def own_blob(self) -> str:
        return "|".join(
            _strip(x) for x in (self.id, self.prop_name, self.anim_rig, self.pop_anim) if x
        )

    @property
    def id_blob(self) -> str:
        """The plant's own names only - the art rig is shared by several plants
        (``potatochip`` wears ``PlantAnimRig_PotatoMine``) and must not decide a
        family on its own."""

        return "|".join(_strip(x) for x in (self.id, self.prop_name) if x)

    @property
    def all_blob(self) -> str:
        return self.own_blob + "|" + _strip(self.framework)

    @property
    def attack_explosions(self) -> tuple[dict, ...]:
        """Explosions that model an attack.

        `trigger=manual` explosions are plant-food effects: `torchwood` carries a
        900-damage manual explosion and is still a support plant, and `burnade`
        carries a 900000-damage one.
        """

        return tuple(
            a for a in self.explode_actions if str(a.get("trigger") or "").lower() != "manual"
        )

    @property
    def plantfood_explosions(self) -> tuple[dict, ...]:
        return tuple(
            a for a in self.explode_actions if str(a.get("trigger") or "").lower() == "manual"
        )


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def index_objects(doc: dict) -> dict[str, dict]:
    """Index a sheet by objectclass and by every alias."""

    out: dict[str, dict] = {}
    for entry in doc.get("objects") or []:
        data = entry.get("objdata") or {}
        for name in [entry.get("objclass")] + list(entry.get("aliases") or []):
            if name:
                out.setdefault(name, data)
    return out


def _number(value, default: float = 0.0) -> float:
    if isinstance(value, dict):
        lo = _number(value.get("Min"), default)
        hi = _number(value.get("Max"), lo)
        return (lo + hi) / 2.0
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    return default


def classify_trajectory(data: dict) -> str:
    """Turn an original launch vector into a delivery class.

    Lobbed shots keep a vertical velocity and a constant downward
    acceleration; straight lane shots are horizontal only; seed rain falls
    straight down.
    """

    vector = data.get("InitialVelocity")
    if not isinstance(vector, list) or len(vector) != 3:
        return TRAJ_UNKNOWN
    vx, vy, vz = (_number(v) for v in vector)
    if abs(vz) > 1.0 and abs(vx) > 1.0:
        return TRAJ_ARC
    if abs(vz) > 1.0:
        return TRAJ_DROP
    if abs(vx) > 1.0:
        return TRAJ_STRAIGHT
    return TRAJ_NONE


def load_obb(obb_dir: Path | None) -> tuple[dict[str, Projectile], dict[str, dict], str]:
    """Read the two original sheets that the pack flattening dropped."""

    if obb_dir is None or not (obb_dir / PROJECTILE_SHEET).exists():
        return {}, {}, "absent"
    projectiles: dict[str, Projectile] = {}
    for name, data in index_objects(load_json(obb_dir / PROJECTILE_SHEET)).items():
        projectiles[name] = Projectile(
            name=name,
            traj=classify_trajectory(data),
            damage=_number(data.get("BaseDamage")),
            splash=_number(data.get("SplashDamage")),
            klass=str(data.get("ClassName") or ""),
        )
    plants: dict[str, dict] = {}
    if (obb_dir / PLANT_SHEET).exists():
        plants = index_objects(load_json(obb_dir / PLANT_SHEET))
    return projectiles, plants, "pkg_2073+pkg_2082"


def build_plants(pack: dict, projectiles: dict[str, Projectile], sheets: dict[str, dict]) -> list[Plant]:
    out: list[Plant] = []
    for raw in sorted(pack.get("plants") or [], key=lambda p: p["id"]):
        actions = raw.get("actions") or []
        kinds = tuple(sorted({str(a.get("kind") or "<none>") for a in actions}))
        proj_names: list[str] = []
        explodes: list[dict] = []
        special_damage = 0.0
        projectile_actions = 0
        projectile_action_damage = 0.0
        for action in actions:
            kind = action.get("kind")
            if kind == "projectile":
                projectile_actions += 1
                # Some shots carry their damage on the action instead of on a
                # projectile sheet entry (`minishroom`: 200 in a rect).
                projectile_action_damage = max(
                    projectile_action_damage, _number(action.get("damage"))
                )
                ref = action.get("projectile") or {}
                name = ref.get("name") if isinstance(ref, dict) else None
                if name:
                    proj_names.append(str(name))
            elif kind == "explode":
                explodes.append(action)
            elif kind == "special":
                special_damage = max(special_damage, _number(action.get("damage")))
        props_name = (raw.get("properties") or {}).get("name") or ""
        out.append(
            Plant(
                id=raw["id"],
                framework=str(raw.get("framework") or ""),
                prop_name=str(props_name),
                anim_rig=str(raw.get("animRig") or ""),
                pop_anim=str(raw.get("popAnim") or ""),
                hitpoints=raw.get("hitpoints"),
                cost=raw.get("cost"),
                sun_producer=bool(raw.get("sunProducer")),
                height=raw.get("height"),
                grid=raw.get("gridType"),
                kinds=kinds,
                projectiles=tuple(proj_names),
                explode_actions=tuple(explodes),
                special_damage=special_damage,
                sun_action="sun" in kinds,
                manual_action="manual" in kinds,
                unknown_action="unknown" in kinds,
                needs_eating=any(a.get("needEating") for a in actions),
                has_projectile_action=projectile_actions > 0,
                projectile_action_damage=projectile_action_damage,
                props=sheets.get(props_name) or {},
            )
        )
    return out


def primary_projectile(plant: Plant, projectiles: dict[str, Projectile]) -> Projectile | None:
    """The shot that describes the plant, skipping plant-food / secondary shots."""

    for name in plant.projectiles:
        entry = projectiles.get(name)
        if entry is not None:
            return entry
    return None


def attack_damage(plant: Plant, projectiles: dict[str, Projectile]) -> float:
    """Largest damage the plant can deal with its own actions."""

    best = max(plant.special_damage, plant.projectile_action_damage)
    for action in plant.attack_explosions:
        best = max(best, _number(action.get("damage")))
    for name in plant.projectiles:
        entry = projectiles.get(name)
        if entry is None:
            continue
        best = max(best, entry.damage, entry.splash)
    return best


def _hp(plant: Plant) -> float:
    return _number(plant.hitpoints)


def decide(plant: Plant, projectiles: dict[str, Projectile]) -> tuple[str, str, str]:
    """Return ``(family, rule_id, evidence)`` for one plant.

    Rules fire in the documented order; the evidence string records the values
    that made the rule fire so a reviewer can re-derive the answer.
    """

    obb = "obb" if projectiles else "obb=absent"
    primary = primary_projectile(plant, projectiles)
    traj = primary.traj if primary else TRAJ_UNKNOWN
    dmg = attack_damage(plant, projectiles)
    facts = [
        f"kinds={','.join(plant.kinds) or '-'}",
        f"hp={plant.hitpoints}",
        f"cost={plant.cost}",
        f"traj={traj}",
        f"atk={dmg:g}",
    ]
    if plant.sun_producer:
        facts.append("sunProducer=true")
    if plant.props.get("IsInstant"):
        facts.append("IsInstant=true")
    if plant.props.get("IsConsumable"):
        facts.append("IsConsumable=true")
    if plant.props.get("ProjectileLobHeight") is not None:
        facts.append(f"LobHeight={plant.props.get('ProjectileLobHeight')}")
    facts.append(obb)
    tail = " ".join(facts)

    # R01 produce: a sun action is the pack-level marker of a producer.
    if plant.sun_action:
        return "produce", "R01-produce/sun-action", tail

    # R02 produce: a sun producer with no attack at all.
    if (
        plant.sun_producer
        and not plant.has_projectile_action
        and not plant.attack_explosions
        and plant.special_damage == 0
    ):
        return "produce", "R02-produce/sun-producer", tail

    # R03 chomp: the bite is modelled as a rect projectile with damage 0.
    if CHOMP_NAME_RE.search(plant.all_blob) or plant.needs_eating:
        return "chomp", "R03-chomp/named", tail

    # R04 fume: short cone attack, modelled with a tiny rect_grid projectile.
    if FUME_NAME_RE.search(plant.all_blob):
        return "fume", "R04-fume/named", tail

    # R05 boomerang: only the name/class reveals the return flight.
    if BOOMERANG_NAME_RE.search(plant.all_blob) or (
        primary is not None and BOOMERANG_CLASS_RE.search(_strip(primary.klass))
    ):
        return "boomerang", "R05-boomerang/named", tail

    # R06 mine: buried mine = own name *and* a rect explosion. `potatochip`
    # shares the framework and the art rig (`PlantAnimRig_PotatoMine`) with the
    # mines but not the name, and is an instant instead.
    if plant.attack_explosions and MINE_NAME_RE.search(plant.id_blob):
        return "mine", "R06-mine/named", tail

    # R07 instant: the original sheet's own one-shot flag.
    if plant.props.get("IsInstant"):
        return "instant", "R07-instant/flagged", tail

    # R08 instant: every one-shot plant carries IsConsumable, including the
    # ones that never set IsInstant (`potatochip`, `solarflare`).
    if plant.props.get("IsConsumable"):
        return "instant", "R08-instant/consumable", tail

    # R09 instant: an attack explosion is left. When the plant also fires
    # projectiles the explosion is the impact/splash of those shots
    # (`gardenia`, `grapeshot`), so it does not make the plant a one-shot.
    if plant.attack_explosions and not plant.has_projectile_action:
        return "instant", "R09-instant/explosion", tail

    # R09b instant: the plant-food explosion is the whole payload, so the plant
    # detonates instead of standing in the lane (`hotdate`, 1200 damage on a
    # `trigger=manual` explosion). `torchwood`'s 900-damage buff explosion is
    # below the bar and stays support.
    if not plant.has_projectile_action and any(
        _number(a.get("damage")) >= 1000 for a in plant.plantfood_explosions
    ):
        return "instant", "R09b-instant/manual-detonation", tail

    # R10 wall: no behaviour at all, and enough HP to be a barrier.
    if not plant.kinds and _hp(plant) >= 1000:
        return "wall", "R10-wall/no-actions-high-hp", tail

    # R11 wall: a defensive rig that still owns an attack/aura (`yuccaguardian`).
    if WALL_NAME_RE.search(plant.own_blob):
        return "wall", "R11-wall/defensive-name", tail

    # R12 wall: tanky, and no damage-producing action at all (`kiwibeast`,
    # `land`). A plant that fires is never a barrier, even when the pack does
    # not carry the damage number (`draftodil`, `citron1`).
    if _hp(plant) >= 1000 and dmg == 0 and not plant.has_projectile_action:
        return "wall", "R12-wall/no-attack-high-hp", tail

    # R13 spike: named melee/spike plants.
    if SPIKE_NAME_RE.search(plant.own_blob):
        return "spike", "R13-spike/named", tail

    # R14 spike: melee modelled as a rect special, no projectile action.
    if not plant.has_projectile_action and plant.special_damage > 0 and _hp(plant) < 1000:
        return "spike", "R14-spike/melee-special", tail

    # R15 support: seed rain - a falling projectile with no base damage.
    if primary is not None and primary.traj == TRAJ_DROP and primary.damage == 0:
        return "support", "R15-support/seed-rain", tail

    # R16 lob: the original launch vector arcs.
    if primary is not None and (primary.traj == TRAJ_ARC or plant.props.get("ProjectileLobHeight") is not None):
        return "lob", "R16-lob/arc", tail

    # R17 shoot: any projectile action left is a lane shot. The action counts
    # even without a projectile reference (`poppinpoppies`, `birdofparadise`
    # fire unnamed rect shots).
    if plant.has_projectile_action:
        return "shoot", "R17-shoot/projectile", tail

    # R18 instant: a one-shot special/explosion on a throwaway body.
    if _hp(plant) <= 100 and (plant.special_damage > 0 or plant.attack_explosions):
        return "instant", "R18-instant/frail-oneshot", tail

    # R19 support: pure utility, no damage of any kind.
    if not plant.has_projectile_action and not plant.attack_explosions and plant.special_damage == 0:
        return "support", "R19-support/no-attack", tail

    # R20 support: the only explosion is a plant-food effect (`torchwood`).
    if plant.plantfood_explosions and not plant.attack_explosions:
        return "support", "R20-support/buff-explosion", tail

    # R21 support: explicit catch-all, counted in the report.
    return "support", "R21-support/catch-all", tail


def generate(pack_path: Path = DEFAULT_PACK, obb_dir: Path | None = DEFAULT_OBB, content_dir: Path = DEFAULT_CONTENT) -> dict:
    """Build the whole table in memory (deterministic, no timestamps)."""

    pack = load_json(pack_path)
    projectiles, sheets, obb_state = load_obb(obb_dir)
    plants = build_plants(pack, projectiles, sheets)
    labels = {
        p["id"]: str(p.get("behavior") or "")
        for p in load_json(content_dir / "plants.json")
        if p.get("source") != "pack"  # 派生行的 behavior 就来自本表，不能当监督标签
    }

    entries = []
    rule_counts: Counter[str] = Counter()
    family_counts: Counter[str] = Counter()
    disagreements = []
    for plant in plants:
        family, rule, evidence = decide(plant, projectiles)
        label = labels.get(plant.id) or ""
        note = ""
        if label:
            note = " label=%s(%s)" % (label, "agree" if label == family else "disagree")
            if label != family:
                disagreements.append(
                    {"id": plant.id, "family": family, "label": label, "rule": rule}
                )
        entries.append(
            {
                "id": plant.id,
                "framework": plant.framework,
                "family": family,
                "evidence": f"rule={rule} {evidence}{note}",
                "source": "content" if label else "pack",
                "rule": rule,
            }
        )
        rule_counts[rule] += 1
        family_counts[family] += 1

    unknown_kinds = [
        {
            "id": e["id"],
            "family": e["family"],
            "handling": "unknown action ignored; family from the plant's own known actions",
        }
        for e in entries
        if any(
            "unknown" in p.kinds
            for p in plants
            if p.id == e["id"]
        )
    ]

    labelled = sum(1 for e in entries if e["source"] == "content")
    return {
        "format": FORMAT,
        "sources": {
            "pack": "native/generated/content.pack",
            "labels": "content/plants.json",
            "obb": obb_state,
            "projectiles": len(projectiles),
            "plantSheets": len(sheets),
        },
        "counts": {
            "plants": len(entries),
            "labelled": labelled,
            "unlabelled": len(entries) - labelled,
            "byFamily": {k: family_counts[k] for k in FAMILIES},
            "byRule": dict(sorted(rule_counts.items())),
        },
        "labels": {
            "compared": labelled,
            "agreement": round((labelled - len(disagreements)) / labelled, 4) if labelled else 0.0,
            "disagreements": disagreements,
        },
        "unknownKinds": unknown_kinds,
        "plants": entries,
    }


def render(table: dict) -> str:
    return json.dumps(table, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def check(table: dict, out_path: Path) -> int:
    """Verify coverage, label agreement and that the committed file is current."""

    problems = []
    entries = table["plants"]
    ids = [e["id"] for e in entries]
    if len(ids) != 339:
        problems.append(f"expected 339 plants, got {len(ids)}")
    if len(set(ids)) != len(ids):
        problems.append("duplicate plant ids")
    if ids != sorted(ids):
        problems.append("entries are not sorted by id")
    missing = [e["id"] for e in entries if e["family"] not in FAMILIES]
    if missing:
        problems.append(f"{len(missing)} plants without a known family: {missing[:5]}")
    agreement = table["labels"]["agreement"]
    if agreement < MIN_LABEL_AGREEMENT:
        problems.append(
            f"label agreement {agreement:.3f} < {MIN_LABEL_AGREEMENT:.2f} "
            f"({len(table['labels']['disagreements'])} disagreements)"
        )
    if not table["unknownKinds"]:
        problems.append("unknown-kind plants were not listed")

    if not out_path.exists():
        problems.append(f"{out_path} is missing; run without --check")
    else:
        current = out_path.read_text(encoding="utf-8")
        if current != render(table):
            problems.append(f"{out_path} is stale; regenerate it")

    print(f"plants={len(ids)} families={len(table['counts']['byFamily'])} "
          f"labelled={table['counts']['labelled']} agreement={agreement:.3f}")
    for family in FAMILIES:
        print(f"  {family:<10} {table['counts']['byFamily'][family]:3d}")
    if table["labels"]["disagreements"]:
        print("disagreements with content/plants.json:")
        for item in table["labels"]["disagreements"]:
            print(f"  {item['id']:<20} pack={item['family']:<9} content={item['label']:<9} {item['rule']}")
    if problems:
        print("FAILED:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("OK")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pack", type=Path, default=DEFAULT_PACK)
    parser.add_argument("--content", type=Path, default=DEFAULT_CONTENT)
    parser.add_argument("--obb", type=Path, default=DEFAULT_OBB)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--check", action="store_true", help="verify without writing")
    args = parser.parse_args(argv)

    table = generate(args.pack, args.obb, args.content)
    if args.check:
        return check(table, args.out)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(render(table))
    print(f"wrote {args.out} ({table['counts']['plants']} plants)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
