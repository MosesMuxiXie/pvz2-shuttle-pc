"""从 OBB 的 StoreProductProps 生成 content/shop.json（商店 2.0）。

数据源：
  work/obb_packages/pkg_2081_StoreProductProps.json   566 件商品
  work/obb_packages/pkg_0232_LawnStringsData.json     中文本地化
  work/obb_packages/pkg_0231_LawnStringsData.json     英文本地化（回退）

同时保留旧版 20 个「金雀花王朝」种子包，保证这些植物仍能从商店解锁。
OBB 中另有 58 个植物没有对应的 content/plants.json 数据，标记为
``implemented: false``，商店会显示但不可购买。

用法：
  <python> tools/build_shop.py
  <python> tools/build_shop.py --obb <目录> --out content/shop.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# OBB 商店内部的兑换比例：1 钻石 ≈ 3000 金币，1 金金茶券 ≈ 30000 金币。
GEM_TO_COIN = 3000
MINT_TO_COIN = 30000

CATEGORIES = [
    {"id": "seeds", "name_zh": "种子包", "order": 0},
    {"id": "items", "name_zh": "道具", "order": 1},
    {"id": "currency", "name_zh": "货币", "order": 2},
    {"id": "bundles", "name_zh": "礼包", "order": 3},
]

# 旧版商店里的 20 个种子包（价格沿用旧 shop.json）。
LEGACY_SEEDS = [
    ("iris", 500), ("rosemary", 520), ("snowlotus", 540),
    ("wildflower", 560), ("olivewood", 580), ("astrofruit", 600),
    ("chrysanthea", 620), ("doominator", 640), ("helioscabbage", 660),
    ("paradoxpult", 680), ("tubiflora", 700), ("vortexmelon", 720),
    ("cheesestrawberry", 740), ("oolongpeach", 760),
    ("succulentgrape", 780), ("doublepassion", 800), ("fireflerry", 820),
    ("frozenpear", 840), ("solarflare", 860), ("taraxacum", 880),
]

TYPE_CATEGORY = {
    "plant": "seeds",
    "costume": "items",
    "gameupgrade": "items",
    "coin": "currency",
    "gem": "currency",
    "mint": "currency",
    "sprout": "currency",
    "eventenergy": "currency",
    "bundle": "bundles",
    "pinata": "bundles",
    "action": "bundles",
}


def _parse_int(value, default=0):
    try:
        if isinstance(value, bool):
            return int(value)
        return int(float(str(value).strip() or default))
    except (TypeError, ValueError):
        return default


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
    env = None
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
        if path and (path / "pkg_2081_StoreProductProps.json").is_file():
            return path
    return None


def load_loc_strings(obb: Path):
    """返回 {key: 中文}；英文表只作为中文缺失时的回退。"""
    def _read(name):
        data = _load_json(obb / name, {}) or {}
        out = {}
        objects = data.get("objects") if isinstance(data, dict) else None
        for obj in objects or []:
            if not isinstance(obj, dict):
                continue
            od = obj.get("objdata") or {}
            values = od.get("LocStringValues")
            if not isinstance(values, list):
                continue
            for i in range(0, len(values) - 1, 2):
                key, val = values[i], values[i + 1]
                if isinstance(key, str) and isinstance(val, str):
                    out.setdefault(key, val)
        return out

    zh = _read("pkg_0232_LawnStringsData.json")
    en = _read("pkg_0231_LawnStringsData.json")
    en.update({k: v for k, v in zh.items() if v})
    return en


def resolve_loc(strings, value, fallback=""):
    if value is None:
        return fallback
    text = str(value).strip()
    if not text:
        return fallback
    translated = strings.get(text)
    if translated and translated != text:
        return translated
    return fallback or text


def load_plants():
    data = _load_json(ROOT / "content" / "plants.json", [])
    by_id = {}
    if isinstance(data, list):
        for p in data:
            if isinstance(p, dict) and p.get("id"):
                by_id[str(p["id"])] = p
    return by_id


def _price_and_currency(od, item_type, count):
    """把 OBB 的三种价格字段折算成金币价，并保留原币种。"""
    coins = _parse_int(od.get("PriceCoins"))
    gems = _parse_int(od.get("PriceGems"))
    mints = _parse_int(od.get("PriceMints"))
    price = _parse_int(od.get("Price"))

    # 少数礼包只填了通用的 Price 字段（99999 代表“极贵/占位”）。
    if coins <= 0 and price > 0:
        coins = price

    # 「用金币买钻石」：按钻石数量折算，避免金币套利。
    if item_type == "gem":
        coins = max(1, count) * GEM_TO_COIN

    if coins > 0:
        return coins, "coin", gems, mints
    if gems > 0:
        return gems * GEM_TO_COIN, "gem", gems, mints
    if mints > 0:
        return mints * MINT_TO_COIN, "mint", gems, mints
    if od.get("IsFree"):
        return 0, "free", 0, 0
    return 0, "free", 0, 0


def _payload(item_type, od, item_id, count):
    key = str(od.get("ObjectItem") or "")
    if item_type == "plant":
        return {"plant_id": key}
    if item_type == "costume":
        return {"costume_id": key}
    if item_type == "gameupgrade":
        mapping = {
            "pf_slots_lvl1": {"plantfood_slots": 1},
            "pf_slots_lvl2": {"plantfood_slots": 1},
            "starting_sun_lvl1": {"sun_start_bonus": 25},
            "startingsun2": {"sun_start_bonus": 50},
            "7_slots": {"seed_slots": 1},
            "seedslot2": {"seed_slots": 1},
            "sunshovel_lvl1": {"sun_shovel": 1},
            "sunshovel_lvl2": {"sun_shovel": 1},
            "sunshovel3": {"sun_shovel": 1},
            "manual_mowers_1": {"mower_charges": 1},
            "pf_refresh": {"plantfood_refresh": 1},
            "rainbowmarket_stargate_start": {"world_key": "rainbowmarket"},
        }
        return dict(mapping.get(key, {"upgrade": key or item_id}))
    if item_type == "pinata":
        return {"seed_pack": max(1, count)}
    if item_type == "bundle":
        return {"seed_pack": 1, "coins": 1000}
    if item_type == "coin":
        return {"coins": max(1, count)}
    if item_type == "gem":
        return {"gems": max(1, count)}
    if item_type == "mint":
        return {"setting": "mints", "amount": max(1, count)}
    if item_type == "sprout":
        return {"setting": "sprouts", "amount": max(1, count)}
    if item_type == "eventenergy":
        return {"setting": "event_energy", "amount": max(1, count),
                "color": key or "energy"}
    if item_type == "action":
        return {"collectible": key or item_id}
    return {"collectible": item_id}


def _implemented(item_type, payload, plants):
    if item_type == "plant":
        return str(payload.get("plant_id") or "") in plants
    return True


def _plant_name(payload, od, strings, plants):
    pid = str(payload.get("plant_id") or "")
    p = plants.get(pid)
    if p and p.get("name_zh"):
        return str(p["name_zh"])
    short = od.get("LawnShortDescription")
    name = resolve_loc(strings, short, "")
    if name and name != str(short):
        return name
    raw = str(od.get("Name") or pid).strip()
    raw = re.sub(r"^Plant\s*-\s*", "", raw, flags=re.I)
    return raw or pid


def _display_name(item_type, od, strings, plants, payload, index):
    name_raw = od.get("Name")
    short_raw = od.get("LawnShortDescription")
    short_zh = resolve_loc(strings, short_raw, "")
    name_zh = resolve_loc(strings, name_raw, "")

    if item_type == "plant":
        return "种子包·" + _plant_name(payload, od, strings, plants)
    if item_type == "costume":
        if short_zh and short_zh != str(short_raw):
            return "装扮·" + short_zh
        num = str(od.get("ObjectItem") or index)
        return "限定装扮 #" + num
    if item_type == "gameupgrade":
        label = short_zh if short_zh and short_zh != str(short_raw) else name_zh
        if not label or label == str(short_raw):
            label = "商店强化"
        return "强化·" + label
    if item_type == "pinata":
        label = short_zh if short_zh and short_zh != str(short_raw) else name_zh
        return label or "抽奖礼包"
    if item_type == "bundle":
        label = short_zh if short_zh and short_zh != str(short_raw) else name_zh
        return "礼包·" + (label or "限定组合")
    if item_type == "action":
        return "限定测试礼包"
    if item_type == "coin":
        return f"金币 ×{_parse_int(od.get('ObjectCount'), 1)}"
    if item_type == "gem":
        return f"钻石 ×{_parse_int(od.get('ObjectCount'), 1)}"
    if item_type == "mint":
        return f"金金茶券 ×{_parse_int(od.get('ObjectCount'), 1)}"
    if item_type == "sprout":
        return f"幼芽 ×{_parse_int(od.get('ObjectCount'), 1)}"
    if item_type == "eventenergy":
        color = str(od.get("ObjectItem") or "").replace("energy_", "")
        color_label = {"pink": "粉", "green": "绿", "red": "红"}.get(color, color)
        return (f"活动能量（{color_label}）"
                f" ×{_parse_int(od.get('ObjectCount'), 1)}")
    return name_zh or str(name_raw or "商店商品")


def _description(item_type, od, payload, name, plants):
    count = _parse_int(od.get("ObjectCount"), 1)
    if item_type == "plant":
        pid = str(payload.get("plant_id") or "")
        if pid in plants:
            return f"解锁植物「{name.replace('种子包·', '')}」，可在花园中种植培育。"
        return (f"限定档案植物「{name.replace('种子包·', '')}」。"
                "该植物暂未实装战斗数据，购买后记入植物图鉴。")
    if item_type == "costume":
        return "植物外观装扮，购买后永久加入衣橱收藏。"
    if item_type == "gameupgrade":
        details = {
            "pf_slots_lvl1": "战斗开始时植物养料槽 +1。",
            "pf_slots_lvl2": "植物养料槽再 +1（可与上一档叠加）。",
            "starting_sun_lvl1": "每场战斗开局阳光 +25。",
            "startingsun2": "每场战斗开局阳光再 +25。",
            "7_slots": "关卡选卡槽位 +1。",
            "seedslot2": "关卡选卡槽位再 +1。",
            "sunshovel_lvl1": "铲除植物时返还少量阳光。",
            "sunshovel_lvl2": "铲除返还阳光提高。",
            "sunshovel3": "铲除返还阳光进一步提高。",
            "manual_mowers_1": "获得手动触发小推车的能力。",
            "pf_refresh": "战斗中可刷新养料槽。",
            "rainbowmarket_stargate_start": "解锁月虹市场的星门入口。",
        }
        key = str(od.get("ObjectItem") or "")
        return details.get(key, f"永久强化：{name.replace('强化·', '')}。")
    if item_type == "pinata":
        return f"打开后获得 {max(1, count)} 份随机种子包或养料。"
    if item_type == "bundle":
        return "限定组合礼包，内含种子包与额外金币。"
    if item_type == "coin":
        return f"兑换 {max(1, count)} 金币。"
    if item_type == "gem":
        return f"兑换 {max(1, count)} 钻石。"
    if item_type == "mint":
        return f"兑换 {max(1, count)} 张金金茶券。"
    if item_type == "sprout":
        return f"兑换 {max(1, count)} 株幼芽。"
    if item_type == "eventenergy":
        return f"兑换 {max(1, count)} 点活动能量。"
    if item_type == "action":
        return "测试用商品容器，购买后获得一份收藏品。"
    return "来自 OBB 商店的商品。"


def _icon(item_type, payload, plants):
    if item_type == "plant":
        pid = str(payload.get("plant_id") or "")
        p = plants.get(pid)
        if p and str(p.get("art") or ""):
            return "plant:" + pid
        return "type:seed"
    return "type:" + item_type


def _rarity(price):
    if price <= 0:
        return "free"
    if price < 2000:
        return "common"
    if price < 15000:
        return "rare"
    if price < 60000:
        return "epic"
    return "legendary"


def build(obb: Path, out_path: Path):
    store = _load_json(obb / "pkg_2081_StoreProductProps.json", {})
    objects = store.get("objects") if isinstance(store, dict) else None
    if not isinstance(objects, list) or not objects:
        raise SystemExit("未找到 StoreProductProps 数据：%s" % (obb / "pkg_2081_StoreProductProps.json"))
    strings = load_loc_strings(obb)
    plants = load_plants()

    items = []
    for index, obj in enumerate(objects):
        if not isinstance(obj, dict):
            continue
        od = obj.get("objdata")
        if not isinstance(od, dict):
            continue
        item_type = str(od.get("ObjectType") or "").strip()
        if item_type not in TYPE_CATEGORY:
            continue
        count = _parse_int(od.get("ObjectCount"), 1)
        payload = _payload(item_type, od, "", count)
        name = _display_name(item_type, od, strings, plants, payload, index)
        desc = _description(item_type, od, payload, name, plants)
        price, currency, price_gems, price_mints = _price_and_currency(
            od, item_type, count)
        implemented = _implemented(item_type, payload, plants)
        sku = str(od.get("Sku") or "").strip()
        item_id = "obb_" + (re.sub(r"[^A-Za-z0-9_.-]+", "_", sku) if sku
                           else "item_%03d" % index)
        item = {
            "id": item_id,
            "sku": sku,
            "name_zh": name,
            "desc_zh": desc,
            "price": max(0, int(price)),
            "currency": currency,
            "price_gems": max(0, int(price_gems)),
            "price_mints": max(0, int(price_mints)),
            "original_price": max(0, int(count if item_type in
                                          ("coin", "gem", "mint", "sprout",
                                           "eventenergy") else
                                          (price_gems or price_mints or price))),
            "item_type": item_type,
            "payload": payload,
            "icon": _icon(item_type, payload, plants),
            "tab": TYPE_CATEGORY[item_type],
            "category": TYPE_CATEGORY[item_type],
            "rarity": _rarity(price),
            "one_time": bool(od.get("IsOneTimePurchase")) or item_type in
                        ("plant", "costume", "gameupgrade", "bundle", "action"),
            "implemented": bool(implemented),
            "source": "obb",
        }
        items.append(item)

    # 旧版 20 个种子包：全部是 plants.json 中 43-62 号植物，保留可购买。
    for pid, price in LEGACY_SEEDS:
        p = plants.get(pid)
        if not p:
            continue
        name = str(p.get("name_zh") or pid)
        items.append({
            "id": "seed_" + pid,
            "sku": "legacy.seed." + pid,
            "name_zh": "种子包·" + name,
            "desc_zh": f"解锁植物「{name}」，可在花园中种植培育。",
            "price": int(price),
            "currency": "coin",
            "price_gems": 0,
            "price_mints": 0,
            "original_price": int(price),
            "item_type": "plant",
            "payload": {"plant_id": pid},
            "icon": "plant:" + pid,
            "tab": "seeds",
            "category": "seeds",
            "rarity": _rarity(price),
            "one_time": True,
            "implemented": True,
            "source": "legacy",
        })

    order = {c["id"]: c["order"] for c in CATEGORIES}
    items.sort(key=lambda it: (order.get(it["tab"], 9),
                               not it["implemented"],
                               it["price"],
                               it["name_zh"]))

    counts = {}
    for it in items:
        counts[it["tab"]] = counts.get(it["tab"], 0) + 1

    data = {
        "version": 2,
        "source": "OBB StoreProductProps + 金雀花王朝种子包",
        "exchange": {"gem_to_coin": GEM_TO_COIN,
                     "mint_to_coin": MINT_TO_COIN},
        "categories": [dict(c, count=counts.get(c["id"], 0))
                       for c in CATEGORIES],
        "seed_pool": [pid for pid, _p in LEGACY_SEEDS if pid in plants],
        "items": items,
        "meta": {
            "total": len(items),
            "from_obb": sum(1 for it in items if it["source"] == "obb"),
            "legacy": sum(1 for it in items if it["source"] == "legacy"),
            "implemented": sum(1 for it in items if it["implemented"]),
            "categories": len(CATEGORIES),
            "counts": counts,
            "unimplemented_plants": sorted({
                it["payload"].get("plant_id") for it in items
                if it["item_type"] == "plant" and not it["implemented"]}),
        },
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    return data


def main(argv=None):
    parser = argparse.ArgumentParser(description="生成 content/shop.json")
    parser.add_argument("--obb", default=None, help="OBB 解包目录")
    parser.add_argument("--out", default=str(ROOT / "content" / "shop.json"))
    args = parser.parse_args(argv)
    obb = find_obb_dir(args.obb)
    if obb is None:
        raise SystemExit("未找到 OBB 目录（work/obb_packages）")
    data = build(obb, Path(args.out))
    meta = data["meta"]
    print("OBB:", obb)
    print("商品:", meta["total"],
          "（OBB", meta["from_obb"], "+ 旧版", meta["legacy"], "）")
    print("分类:", ", ".join(f"{c['name_zh']}={c['count']}"
                             for c in data["categories"]))
    print("可购买:", meta["implemented"],
          "；未实装植物:", len(meta["unimplemented_plants"]))
    print("输出:", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
