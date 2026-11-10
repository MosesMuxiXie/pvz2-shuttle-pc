"""从 OBB 的 ZenGardenPropertySheet 生成 content/garden.json（禅境花园 2.0）。

数据源：
  work/obb_packages/pkg_2083_PlantFusionConfig.json
      objclass == "ZenGardenPropertySheet"（别名 ZenGardenProps）
  work/obb_packages/pkg_0004_AwardConfigPropertySheet.json
      ZenGardenPlantRewardsPropertySheet
  work/obb_packages/pkg_2073_PlantPropertySheet.json
      每株植物的 ZenGardenDurationOverrideSeconds / SproutWeight

生成内容：
  * 8 个花盆的 4×2 布局（游戏要求 8 盆；OBB 的 12 个位置只取前 8 个）
  * 18000 秒生长周期与 4 个阶段
  * 浇水花费 / 减少时间 / 最多次数
  * 收获金币、养料、种子包掉落与稀有度权重
  * 可种植植物池（基础 42 株）与种子包掉落池（金雀花王朝 20 株）

用法：
  <python> tools/build_garden.py
  <python> tools/build_garden.py --obb <目录> --out content/garden.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DEFAULT_GROW = 18000
DEFAULT_COINS = 50
DEFAULT_POT_COST = 20
POT_COUNT = 8
POT_COLS, POT_ROWS = 4, 2

RARITIES = [
    {"id": "common", "name_zh": "普通", "weight": 60,
     "coin_mult": 1.0, "plantfood": 1},
    {"id": "rare", "name_zh": "稀有", "weight": 30,
     "coin_mult": 1.5, "plantfood": 2},
    {"id": "epic", "name_zh": "史诗", "weight": 10,
     "coin_mult": 2.5, "plantfood": 3},
]


def _load_json(path: Path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def find_obb_dir(explicit=None):
    candidates = []
    if explicit:
        candidates.append(Path(explicit))
    try:
        import os
        env = os.environ.get("PVZ2_OBB_DIR")
    except Exception:
        env = None
    if env:
        candidates.append(Path(env))
    candidates.extend([
        ROOT.parent / "work" / "obb_packages",
        ROOT / "work" / "obb_packages",
        ROOT.parent / "obb_packages",
    ])
    for path in candidates:
        if path and (path / "pkg_2083_PlantFusionConfig.json").is_file():
            return path
    return None


def _iter_objects(path: Path):
    data = _load_json(path, {})
    objects = data.get("objects") if isinstance(data, dict) else None
    return objects if isinstance(objects, list) else []


def find_zen_sheet(obb: Path):
    for obj in _iter_objects(obb / "pkg_2083_PlantFusionConfig.json"):
        if not isinstance(obj, dict):
            continue
        if obj.get("objclass") == "ZenGardenPropertySheet":
            od = obj.get("objdata")
            if isinstance(od, dict):
                return od
    return {}


def find_rewards(obb: Path):
    for obj in _iter_objects(obb / "pkg_0004_AwardConfigPropertySheet.json"):
        if not isinstance(obj, dict):
            continue
        if obj.get("objclass") == "ZenGardenPlantRewardsPropertySheet":
            od = obj.get("objdata")
            if isinstance(od, dict):
                return od
    return {}


def load_plant_rows():
    rows = _load_json(ROOT / "content" / "plants.json", [])
    return rows if isinstance(rows, list) else []


def load_shop_seed_pool():
    """种子包掉落池优先跟随商店的 seed_pool（金雀花王朝 20 株）。"""
    data = _load_json(ROOT / "content" / "shop.json", {})
    if isinstance(data, dict):
        pool = data.get("seed_pool")
        if isinstance(pool, list):
            return [str(pid) for pid in pool if pid]
    return []


def load_duration_overrides(obb: Path):
    """从 PlantPropertySheet 收集 OBB 的 ZenGardenDurationOverrideSeconds。"""
    out = {}
    for obj in _iter_objects(obb / "pkg_2073_PlantPropertySheet.json"):
        if not isinstance(obj, dict):
            continue
        od = obj.get("objdata")
        if not isinstance(od, dict):
            continue
        pid = od.get("ObjectItem") or od.get("Alias") or od.get("Name")
        if not pid:
            continue
        dur = od.get("ZenGardenDurationOverrideSeconds")
        weight = od.get("ZenGardenSproutWeight")
        if dur is None and weight is None:
            continue
        entry = {}
        try:
            if dur is not None:
                entry["grow_seconds"] = int(dur)
        except (TypeError, ValueError):
            pass
        try:
            if weight is not None:
                entry["sprout_weight"] = int(weight)
        except (TypeError, ValueError):
            pass
        if entry:
            out[str(pid)] = entry
    return out


def build(obb: Path, out_path: Path):
    zen = find_zen_sheet(obb)
    rewards = find_rewards(obb)
    plants = load_plant_rows()
    overrides = load_duration_overrides(obb)

    grow = int(zen.get("PlantGrowDurationInSeconds") or DEFAULT_GROW)
    grow = max(60, grow)
    coins = int(zen.get("NormalPlantCoinRewardAmount") or DEFAULT_COINS)
    pot_cost = DEFAULT_POT_COST
    raw_costs = zen.get("PotCosts") or {}
    if isinstance(raw_costs, dict):
        try:
            pot_cost = int(raw_costs.get("GemCostDefault", pot_cost) or pot_cost)
        except (TypeError, ValueError):
            pot_cost = DEFAULT_POT_COST

    # 四阶段：0 幼芽 / 1 生长 / 2 含苞 / 3 成熟（成熟即 stage 3）
    stage_seconds = [0, grow // 4, grow // 2, grow]
    stage_names = ["幼芽", "生长", "含苞", "成熟"]

    base_pool = []
    seed_pool = []
    for p in plants:
        if not isinstance(p, dict):
            continue
        pid = str(p.get("id") or "")
        if not pid:
            continue
        try:
            no = int(p.get("almanac_no", 999) or 999)
        except (TypeError, ValueError):
            no = 999
        if no <= 42:
            base_pool.append(pid)
        else:
            seed_pool.append(pid)

    # 商店的 20 个金雀花王朝种子优先作为掉落池；避免把融合植物等
    # 后续扩充内容误当成种子包。
    shop_pool = load_shop_seed_pool()
    if shop_pool:
        valid_ids = {str(p.get("id")) for p in plants if isinstance(p, dict)}
        filtered = [pid for pid in shop_pool if pid in valid_ids]
        if filtered:
            seed_pool = filtered

    # OBB 的 12 个花盆位置；游戏固定 8 盆，取前 8 个（4×2 排布）。
    pots = []
    for slot in range(POT_COUNT):
        row, col = divmod(slot, POT_COLS)
        pots.append({
            "slot": slot,
            "col": col,
            "row": row,
            "unlock_index": col * 100 + row,
            "gem_cost": pot_cost,
        })

    water = {
        "cost_coins": 5,
        "reduce_seconds": max(1, grow // 10),
        "max_waters": 5,
        "bonus_per_water": 0.05,
    }
    harvest = {
        "coins": coins,
        "plantfood_min": 1,
        "plantfood_max": 3,
        "seed_chance": 0.12,
        "treasure_chance": 0.03,
        "treasure_coins": 500,
        "treasure_plantfood": 3,
    }

    data = {
        "version": 1,
        "source": "OBB ZenGardenPropertySheet",
        "obb_values": {
            "PlantGrowDurationInSeconds": zen.get("PlantGrowDurationInSeconds"),
            "NormalPlantCoinRewardAmount": zen.get("NormalPlantCoinRewardAmount"),
            "TreasurePlantSpawnRate": zen.get("TreasurePlantSpawnRate"),
            "GrowingSpeedupCalcMultiplyFactor": zen.get(
                "GrowingSpeedupCalcMultiplyFactor"),
            "GrowingSpeedupCalcMaxTimeSeconds": zen.get(
                "GrowingSpeedupCalcMaxTimeSeconds"),
            "PotCosts": raw_costs,
            "pots_total_in_obb": len(zen.get("Pots") or []),
            "marigold_final_rewards": rewards.get(
                "ZenGardenMarigoldFinalRewards", {}),
        },
        "pot_count": POT_COUNT,
        "layout": {"cols": POT_COLS, "rows": POT_ROWS},
        "pots": pots,
        "grow_seconds": grow,
        "stage_count": 4,
        "stage_seconds": stage_seconds,
        "stage_names": stage_names,
        "plant_pool": base_pool,
        "seed_pool": seed_pool,
        "water": water,
        "harvest": harvest,
        "rarities": RARITIES,
        "duration_overrides": overrides,
        "fast_env": "PVZ2_GARDEN_FAST",
        "fast_multiplier": 100,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    return data


def main(argv=None):
    parser = argparse.ArgumentParser(description="生成 content/garden.json")
    parser.add_argument("--obb", default=None, help="OBB 解包目录")
    parser.add_argument("--out", default=str(ROOT / "content" / "garden.json"))
    args = parser.parse_args(argv)
    obb = find_obb_dir(args.obb)
    if obb is None:
        raise SystemExit("未找到 OBB 目录（work/obb_packages）")
    data = build(obb, Path(args.out))
    print("OBB:", obb)
    print("花盆:", data["pot_count"], "；生长:", data["grow_seconds"], "秒")
    print("阶段:", list(zip(data["stage_names"], data["stage_seconds"])))
    print("植物池:", len(data["plant_pool"]), "；种子池:",
          len(data["seed_pool"]))
    print("浇水:", data["water"])
    print("输出:", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
