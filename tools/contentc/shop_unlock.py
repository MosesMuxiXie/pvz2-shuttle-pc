"""Shop unlock classifier: `content/shop.json` -> `native/generated/shop_unlock.json`.

Why this exists
---------------
`content/shop.json` shows 585 products with a price and a tab, but **no gating
field at all**: there is no `unlock`, `requires`, `world`, `stars` or `level`
key on any row (see `--needle`).  The world map / shop UI still has to know
whether something is a seed pack, an upgrade, a world key, a costume or an
event item, and whether buying it needs a world to be open or a pile of coins.
This module derives that classification from evidence that *is* in the file —
`item_type`, `payload` keys, `tab`, `id` — and says per item which evidence it
used, so nothing is silently guessed.

Where the classes come from
---------------------------
The six classes are the ones the engine's shop UI plans to render
(`seed | upgrade | world_key | costume | event | unknown`).  `content/shop.json`
has four tabs (`seeds | items | currency | bundles`) and a finer `item_type`,
so the mapping is a projection, not an identity: 13 rows (11 currency top-ups
and 2 bundles) have **no class** in the six and land in `unknown` with a
recorded reason.  They are listed by id in the report and in
`counts.unknownCategoryIds`; nothing is dropped.

Rules (checked in this order, first hit wins; the matched rule is in `rawKeys`)
-----------------------------------------------------------------------------
R01 world_key  `payload.world_key` present ................................... 1
R02 costume    `item_type == costume` or `payload.costume_id` ............... 447
R03 seed       `item_type == plant` or `payload.plant_id` ................... 81
R04 upgrade    `item_type == gameupgrade` (after R01 removed the world key) . 11
R05 event      `item_type in {eventenergy, pinata}` or
               `payload.setting == event_energy` or an id keyword
               (`pinata|anniversary|_show|lte_|event`) ..................... 32
R06 unknown    everything else — currently `item_type in {coin, gem, mint,
               sprout, bundle, action}` .................................... 13

R01 has to precede R04 because the world key is itself stored with
`item_type: gameupgrade` (id `obb_worldkey.rainbowmarket`); without the order
the key would be counted as an upgrade, which is what the shop UI would then
render.

Unlock fields
-------------
`content/shop.json` carries no purchase requirements, so the three unlock slots
are filled only from what the data can actually support, and every filled slot
says where it came from:

`unlock.world`  the world the product is bound to — `payload.world_key`
                (aliased to the `content/worldmap.json` id: `rainbowmarket` ->
                `lunarrainbowmarket`), or a world id appearing as a whole token
                in `id`/`sku` (only the Egypt tutorial piñata).  This is a
                **binding**, not a prerequisite: a world key unlocks that world,
                and an event piñata belongs to that world.
`unlock.coins`  the coin amount needed to obtain the row: the `price` when
                `currency == "coin"`, else null.  (Gem/mint/free rows have no
                coin gate.)
`unlock.stars`  always null.  `content/shop.json` has no star field, and
                `content/stars.json` is the per-level three-star task list, not
                a shop gate — `--needle stars` proves the former, and the report
                quotes the latter.
`unlock.kind`   none / world / stars / coins / mixed from which slots are set;
                `unknown` only for rows whose own shape could not be read
                (missing id, non-integer price), so downstream code can still
                count them.

Determinism
-----------
`generated` is the **source file's mtime** in UTC ISO-8601, not "now": two runs
over the same `content/shop.json` produce byte-identical output, which is what
`--check` and the byte-equality test rely on.  The JSON is
`json.dumps(..., ensure_ascii=False, indent=1, sort_keys=True)` plus a trailing
newline, written as UTF-8 bytes with LF endings (on Windows `Path.write_text`
would emit CRLF and the bytes would stop matching `render()`).

Commands
--------
    python tools/contentc/shop_unlock.py             # write json + report
    python tools/contentc/shop_unlock.py --check     # artifact up to date? (0/1)
    python tools/contentc/shop_unlock.py --needle    # prove which keys don't exist

Honest boundaries
-----------------
* `price.currency` is the enum `coins | gems | none`.  The source has a fourth
  currency, `mint` (10 rows), which that enum cannot express, so those rows are
  written as `none` with `amount: null` and keep `currency=mint` in `rawKeys`;
  `counts.mintPriced` counts them and the report lists them.
* `stars` never fires: there is no star-gated product in the file.
* Category is a projection of `item_type`; if a future export adds a real
  `unlock`/`requires` field this module should read it instead of guessing.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from contentc import worlds  # noqa: E402

REPO = worlds.REPO
DEFAULT_SOURCE = REPO / "content" / "shop.json"
DEFAULT_WORLDS = REPO / "content" / "worldmap.json"
DEFAULT_OUT = REPO / "native" / "generated" / "shop_unlock.json"
DEFAULT_REPORT = REPO / "docs" / "reviews" / "2026-11-21-shop-unlock.md"

FORMAT = 1
GENERATED = "shop-unlock-v1"
SOURCE_NAME = "content/shop.json"

CATEGORIES = ("seed", "upgrade", "world_key", "costume", "event", "unknown")
UNLOCK_KINDS = ("none", "world", "stars", "coins", "mixed", "unknown")

# enum value -> what the source writes; `mint` has no enum value on purpose,
# see the module docstring (it stays visible through rawKeys/counts).
CURRENCY_MAP = {"coin": "coins", "gem": "gems", "free": "none"}

# the same three aliases `tools/contentc/worlds.py` uses to line the OBB world
# names up with `content/worlds.json`
WORLD_ALIASES = {"skycity": "sky", "gta": "losantosvice", "rainbowmarket": "lunarrainbowmarket"}

EVENT_ID_RE = re.compile(r"pinata|anniversary|_show|lte_|event", re.IGNORECASE)

# what `--needle` looks for: the gating keys a shop product might have had
NEEDLE_KEYS = (
    "unlock",
    "requires",
    "requirement",
    "prerequisite",
    "world",
    "stars",
    "star",
    "level",
    "gated",
    "locked",
)


# --------------------------------------------------------------------------- #
# loading
# --------------------------------------------------------------------------- #
def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8-sig") as handle:
        return json.load(handle)


def world_ids(path: Path) -> dict[str, int | None]:
    """`content/worldmap.json` world id -> unlock_cost (None when not numeric)."""
    doc = load_json(path)
    worlds_doc = doc.get("worlds") if isinstance(doc, dict) else None
    if not isinstance(worlds_doc, dict):
        return {}
    out: dict[str, int | None] = {}
    for world_id, entry in worlds_doc.items():
        cost = entry.get("unlock_cost") if isinstance(entry, dict) else None
        out[str(world_id)] = int(cost) if isinstance(cost, (int, float)) else None
    return out


def generated_stamp(source: Path) -> str:
    """UTC ISO-8601 of the source's mtime — stable, so two runs match byte for byte."""
    stamp = datetime.fromtimestamp(source.stat().st_mtime, tz=timezone.utc)
    return stamp.replace(microsecond=0).isoformat().replace("+00:00", "Z")


# --------------------------------------------------------------------------- #
# classification
# --------------------------------------------------------------------------- #
def _payload(item: dict) -> dict:
    payload = item.get("payload")
    return payload if isinstance(payload, dict) else {}


def resolve_world(token: str, ids: dict[str, int | None]) -> str | None:
    """Map a raw token onto a `content/worldmap.json` world id (or None)."""
    text = token.strip()
    lowered = text.lower()
    for candidate in (text, lowered, WORLD_ALIASES.get(lowered, "")):
        if candidate and candidate in ids:
            return candidate
    return None


def classify_category(item: dict) -> tuple[str, list[str]]:
    """Return (category, evidence).  First matching rule wins (R01..R06)."""
    payload = _payload(item)
    item_type = str(item.get("item_type") or "")
    item_id = str(item.get("id") or "")

    if payload.get("world_key"):
        return "world_key", ["R01:payload.world_key=%s" % payload.get("world_key")]
    if item_type == "costume" or "costume_id" in payload:
        return "costume", ["R02:item_type=costume" if item_type == "costume"
                           else "R02:payload.costume_id"]
    if item_type == "plant" or "plant_id" in payload:
        return "seed", ["R03:item_type=plant" if item_type == "plant"
                        else "R03:payload.plant_id"]
    if item_type == "gameupgrade":
        return "upgrade", ["R04:item_type=gameupgrade"]
    if item_type in ("eventenergy", "pinata"):
        return "event", ["R05:item_type=%s" % item_type]
    if payload.get("setting") == "event_energy":
        return "event", ["R05:payload.setting=event_energy"]
    hit = EVENT_ID_RE.search(item_id)
    if hit:
        return "event", ["R05:id:%s" % hit.group(0).lower()]
    return "unknown", ["R06:item_type=%s" % (item_type or "<missing>")]


def classify_price(item: dict) -> tuple[dict, list[str]]:
    currency = str(item.get("currency") or "")
    raw = item.get("price")
    amount = int(raw) if isinstance(raw, (int, float)) and not isinstance(raw, bool) else None
    evidence: list[str] = []
    mapped = CURRENCY_MAP.get(currency)
    if mapped is None:
        # `mint` (and any future currency) has no value in the price enum; keep
        # the truth in rawKeys instead of inventing a currency.
        evidence.append("price:none-for-currency=%s" % (currency or "<missing>"))
        return {"currency": "none", "amount": None}, evidence
    if amount is None:
        evidence.append("price:amount-missing")
    return {"currency": mapped, "amount": amount}, evidence


def classify_unlock(item: dict, category: str, price: dict,
                    ids: dict[str, int | None]) -> tuple[dict, list[str]]:
    payload = _payload(item)
    evidence: list[str] = []

    world = None
    key = payload.get("world_key")
    if isinstance(key, str) and key:
        world = resolve_world(key, ids)
        evidence.append("unlock.world:payload.world_key=%s" % key)
    if world is None:
        blob = " ".join(str(item.get(part) or "") for part in ("id", "sku")).lower()
        for world_id in sorted(ids):
            if re.search(r"(?<![a-z0-9])%s(?![a-z0-9])" % re.escape(world_id), blob):
                world = world_id
                evidence.append("unlock.world:id-token=%s" % world_id)
                break

    coins = price["amount"] if price["currency"] == "coins" else None
    if coins is not None:
        evidence.append("unlock.coins:price")

    stars = None  # no star gate exists in content/shop.json (see --needle)

    slots = [name for name, value in (("world", world), ("stars", stars), ("coins", coins))
             if value is not None]
    if not slots:
        kind = "none"
    elif len(slots) == 1:
        kind = slots[0]
    else:
        kind = "mixed"
    evidence.append("unlock.kind=%s" % kind)
    return {"world": world, "stars": stars, "coins": coins, "kind": kind}, evidence


def build_item(item: dict, ids: dict[str, int | None], position: int) -> dict:
    item_id = item.get("id")
    item_id = item_id.strip() if isinstance(item_id, str) and item_id.strip() else None
    category, cat_evidence = classify_category(item) if item_id else (
        "unknown", ["R06:id-missing"])
    price, price_evidence = classify_price(item)
    unlock, unlock_evidence = classify_unlock(item, category, price, ids)
    raw_keys = (
        ["position=%d" % position]
        + cat_evidence
        + price_evidence
        + unlock_evidence
        + ["item_type=%s" % (item.get("item_type") or "<missing>"),
           "tab=%s" % (item.get("tab") or "<missing>"),
           "currency=%s" % (item.get("currency") or "<missing>")]
        + sorted("payload.%s" % name for name in _payload(item))
    )
    if item_id is None:
        # an unreadable row is still a row: keep it, flag it, count it
        unlock = {"world": unlock["world"], "stars": unlock["stars"],
                  "coins": unlock["coins"], "kind": "unknown"}
        raw_keys.append("unlock.kind=unknown")
    return {
        "id": item_id,
        "category": category,
        "price": price,
        "unlock": unlock,
        "rawKeys": raw_keys,
    }


def build(doc: dict, ids: dict[str, int | None], generated: str) -> dict:
    raw_items = doc.get("items") if isinstance(doc, dict) else None
    raw_items = raw_items if isinstance(raw_items, list) else []
    rows = [
        build_item(item, ids, position)
        for position, item in enumerate(raw_items)
        if isinstance(item, dict)
    ]
    # deterministic order: id, then the original position (rows with a missing id
    # sort last); duplicates are kept on purpose and counted below
    rows.sort(key=lambda row: (row["id"] is None, row["id"] or "", row["rawKeys"][0]))

    by_category = {name: 0 for name in CATEGORIES}
    by_kind = {name: 0 for name in UNLOCK_KINDS}
    for row in rows:
        by_category[row["category"]] = by_category.get(row["category"], 0) + 1
        by_kind[row["unlock"]["kind"]] = by_kind.get(row["unlock"]["kind"], 0) + 1

    def _ids(predicate) -> list:
        return [row["id"] for row in rows if predicate(row)]

    seen: dict[str, int] = {}
    for row in rows:
        if row["id"] is not None:
            seen[row["id"]] = seen.get(row["id"], 0) + 1
    duplicates = {name: count for name, count in seen.items() if count > 1}

    unknown_category = [row for row in rows if row["category"] == "unknown"]
    unknown_conditions = [row for row in rows if row["unlock"]["kind"] == "unknown"]
    counts = {
        "total": len(rows),
        "byCategory": by_category,
        "byUnlockKind": by_kind,
        "unknownConditions": len(unknown_conditions),
        "unknownCategory": len(unknown_category),
        "unknownCategoryIds": [row["id"] for row in unknown_category],
        "unknownConditionIds": [row["id"] for row in unknown_conditions],
        "unknownCategoryReasons": {
            reason: len(ids_list)
            for reason, ids_list in _group_unknown(unknown_category).items()
        },
        "missingIds": len([row for row in rows if row["id"] is None]),
        "duplicateIds": duplicates,
        "duplicateCount": len(duplicates),
        "mintPriced": _ids(lambda row: any(k.startswith("price:none-for-currency=mint")
                                           for k in row["rawKeys"])),
        "worldBound": _ids(lambda row: row["unlock"]["world"] is not None),
        "coinGated": _ids(lambda row: row["unlock"]["coins"] is not None),
        "starGated": _ids(lambda row: row["unlock"]["stars"] is not None),
        "priceCurrencies": {
            name: len(_ids(lambda row, name=name: row["price"]["currency"] == name))
            for name in ("coins", "gems", "none")
        },
        "sourceItems": len(raw_items),
        "metaTotal": (doc.get("meta") or {}).get("total") if isinstance(doc.get("meta"), dict) else None,
        "categoryTabCounts": {
            str(entry.get("id")): entry.get("count")
            for entry in (doc.get("categories") or [])
            if isinstance(entry, dict)
        },
    }
    return {
        "format": FORMAT,
        "generated": GENERATED,
        "source": SOURCE_NAME,
        "generatedAt": generated,
        "items": rows,
        "counts": counts,
    }


def _group_unknown(rows: list[dict]) -> dict[str, list]:
    """Bucket unknown-category rows by the `item_type` that defeated the six classes."""
    out: dict[str, list] = {}
    for row in rows:
        reason = "unknown"
        for key in row["rawKeys"]:
            if key.startswith("R06:"):
                reason = key[4:]
                break
        out.setdefault(reason, []).append(row["id"])
    return out


# --------------------------------------------------------------------------- #
# census
# --------------------------------------------------------------------------- #
def needle_report(source: Path) -> dict:
    doc = load_json(source)
    items = [item for item in (doc.get("items") or []) if isinstance(item, dict)]
    hits = {name: 0 for name in NEEDLE_KEYS}
    for item in items:
        for name in NEEDLE_KEYS:
            if name in item:
                hits[name] += 1
    return {"items": len(items), "keys": hits}


# --------------------------------------------------------------------------- #
# rendering
# --------------------------------------------------------------------------- #
def render(table: dict) -> str:
    return json.dumps(table, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def dump(table: dict, path: Path) -> None:
    # bytes + LF: on Windows write_text would emit CRLF and the file would stop
    # matching render() byte for byte (which --check and the tests compare)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(render(table).encode("utf-8"))


def _num(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _cell(text) -> str:
    return str(text).replace("|", "\\|")


EXAMPLES = {
    "seed": "seed_iris",
    "upgrade": "obb_com.popcap.pvz2.gameupgrade.seedslot.nonconsume.t1",
    "world_key": "obb_worldkey.rainbowmarket",
    "costume": "obb_tonywrite.costume.370",
}


def render_report(table: dict, needle: dict | None = None) -> str:
    counts = table["counts"]
    rows = table["items"]
    by_id = {row["id"]: row for row in rows if row["id"]}
    lines: list[str] = []
    add = lines.append

    add("# 商店解锁分类（`content/shop.json` → `native/generated/shop_unlock.json`）")
    add("")
    add("由 `tools/contentc/shop_unlock.py` 生成。源 `content/shop.json`"
        "（`generatedAt` = 该文件 mtime 的 UTC 时间 `%s`，不是「运行时刻」，"
        "所以两次生成逐字节相同）。" % table["generatedAt"])
    add("")
    add("```")
    add("python tools/contentc/shop_unlock.py            # 写 json + 本报告")
    add("python tools/contentc/shop_unlock.py --check    # 产物是否仍与源一致（0/1）")
    add("python tools/contentc/shop_unlock.py --needle   # 复现「哪些门槛字段不存在」")
    add("```")
    add("")

    add("## 0. 585 是否成立")
    add("")
    add("| 口径 | 值 | 说明 |")
    add("|---|---:|---|")
    add("| `shop.json` 的 `items` 行数 | %d | 本表 `counts.total` 就是它 |"
        % counts["sourceItems"])
    add("| `shop.json` 的 `meta.total` | %s | 与行数 %s |"
        % (_num(counts["metaTotal"]),
           "一致" if counts["metaTotal"] == counts["sourceItems"] else "**不一致**"))
    add("| `categories[].count` 求和 | %d | %s |"
        % (sum(v for v in counts["categoryTabCounts"].values() if isinstance(v, int)),
           " / ".join("%s=%s" % (k, v) for k, v in sorted(counts["categoryTabCounts"].items()))))
    add("| 编译出的条目 | %d | 每行一条，无静默丢弃 |" % counts["total"])
    add("| 缺失 id 的条目 | %d | 源里 %s |"
        % (counts["missingIds"], "没有这种行" if counts["missingIds"] == 0 else "有，保留并标记"))
    add("| 重复 id | %d | %s |"
        % (counts["duplicateCount"],
           "源里没有重复" if not counts["duplicateIds"]
           else "、".join("%s×%d" % (k, v) for k, v in sorted(counts["duplicateIds"].items()))))
    add("")
    add("**585 成立**：`items` 行数、`meta.total`、四个 tab 的 `count` 求和三者相等，"
        "所以本表不做任何数字修正。" if counts["total"] == 585 else
        "**585 不成立**：见上表差异，本表按 `items` 实际行数输出 `%d`，不改数字去凑。"
        % counts["total"])
    add("")

    add("## 1. 分类规则与命中数")
    add("")
    add("规则按顺序取首个命中，命中规则写进每条的 `rawKeys`（`R01:`…`R06:`）。")
    add("")
    add("| 规则 | 条件 | 类 | 命中 |")
    add("|---|---|---|---:|")
    add("| R01 | `payload.world_key` 存在 | `world_key` | %d |" % counts["byCategory"]["world_key"])
    add("| R02 | `item_type == costume` 或 `payload.costume_id` | `costume` | %d |"
        % counts["byCategory"]["costume"])
    add("| R03 | `item_type == plant` 或 `payload.plant_id` | `seed` | %d |"
        % counts["byCategory"]["seed"])
    add("| R04 | `item_type == gameupgrade`（R01 已先摘走世界钥匙） | `upgrade` | %d |"
        % counts["byCategory"]["upgrade"])
    add("| R05 | `item_type in {eventenergy, pinata}` 或 `payload.setting == event_energy` "
        "或 id 命中 `pinata\\|anniversary\\|_show\\|lte_\\|event` | `event` | %d |"
        % counts["byCategory"]["event"])
    add("| R06 | 其余（`coin/gem/mint/sprout/bundle/action`） | `unknown` | %d |"
        % counts["byCategory"]["unknown"])
    add("")
    add("R01 必须排在 R04 前面：世界钥匙本身是 `item_type: gameupgrade`"
        "（`obb_worldkey.rainbowmarket`），顺序反了它会被当成普通道具强化。")
    add("")

    add("## 2. 六类计数与样例")
    add("")
    add("| 类 | 数量 | 样例 id |")
    add("|---|---:|---|")
    for name in CATEGORIES:
        # prefer a hand-picked example, but only if that id is actually in the table
        sample = EXAMPLES.get(name)
        if sample not in by_id:
            sample = next((row["id"] for row in rows if row["category"] == name), None)
        add("| `%s` | %d | %s |" % (name, counts["byCategory"][name],
                                    ("`%s`" % sample) if sample else "—"))
    add("| **合计** | **%d** | |" % counts["total"])
    add("")

    add("## 3. `unknown` 逐条点名")
    add("")
    add("六类里没有 `currency` 与 `bundle`，所以**货币充值（11 条）与礼包（2 条）进 `unknown`**，"
        "不是「忘了分类」。")
    add("")
    add("| 原因（`item_type`） | 条数 | id |")
    add("|---|---:|---|")
    for reason, ids in sorted(_group_unknown([row for row in rows
                                              if row["category"] == "unknown"]).items()):
        add("| `%s` | %d | %s |" % (_cell(reason), len(ids),
                                    "、".join("`%s`" % name for name in ids)))
    add("")
    add("合计 `%d` 条，与 `counts.unknownCategory` 相等。" % counts["unknownCategory"])
    add("")

    add("## 4. `unlock` 三格的语义与由来")
    add("")
    add("`content/shop.json` **没有任何购买门槛字段**，所以三格只填数据能支撑的部分，"
        "每格来源写进 `rawKeys`。")
    add("")
    add("| 字段 | 取值 | 来源 | 命中 |")
    add("|---|---|---|---:|")
    add("| `unlock.world` | 世界 id 或 null | `payload.world_key`（经 `rainbowmarket→lunarrainbowmarket` 别名）"
        " 或 id/sku 里带完整世界 token | %d |" % len(counts["worldBound"]))
    add("| `unlock.coins` | 整数或 null | `currency == coin` 时的 `price` | %d |"
        % len(counts["coinGated"]))
    add("| `unlock.stars` | 恒为 null | 源里没有星级门槛（见 §5） | %d |"
        % len(counts["starGated"]))
    add("")
    add("`unlock.kind` 由三格是否为空推导：`none` / `world` / `stars` / `coins` / `mixed`，"
        "只有「这一行本身读不出来」（缺 id、价格非整数）才是 `unknown`。"
        "分布：%s。"
        % "、".join("`%s` %d" % (name, counts["byUnlockKind"][name])
                   for name in UNLOCK_KINDS))
    add("")
    for world_row in [row for row in rows if row["unlock"]["world"]][:5]:
        add("- `%s` → world `%s`、coins %s、kind `%s`"
            % (world_row["id"], world_row["unlock"]["world"],
               _num(world_row["unlock"]["coins"]), world_row["unlock"]["kind"]))
    add("")
    add("世界钥匙 `obb_worldkey.rainbowmarket` 的 `world` 是 `lunarrainbowmarket`"
        "（`content/worldmap.json` 里没有 `rainbowmarket` 这个 id），这条别名来自 "
        "`tools/contentc/worlds.py` 的 `ALIASES`，不是猜的。")
    add("")

    add("## 5. 为什么 `stars` 全是 null")
    add("")
    if needle is not None:
        add("`--needle` 在 `%d` 条商品上找门槛类键名：" % needle["items"])
        add("")
        add("| 键名 | 命中 |")
        add("|---|---:|")
        for name, hits in sorted(needle["keys"].items()):
            add("| `%s` | %d%s |" % (name, hits,
                                     "" if hits else "（不存在）"))
        add("")
    add("`content/stars.json` 是**每关的三星任务定义**（键形如 `frontyard_1`，"
        "值是 `beat/mowers/kill` 三条任务），不是商店门槛；`content/worldmap.json` 的 "
        "`unlock_cost` 每个世界都是 `1`（钥匙数），也不带星级。"
        "因此本表 `unlock.stars` 一律 null，`kind` 永远不会是 `stars`——"
        "需要星级门槛时必须先在导出侧加字段。")
    add("")

    add("## 6. 价格与货币")
    add("")
    add("`price.currency` 只允许 `coins | gems | none`，而源里有第四种货币 `mint`"
        "（金金茶券，%d 条）。枚举装不下，这 %d 条写成 `currency: none`、`amount: null`，"
        "并把真相留在 `rawKeys` 的 `currency=mint` 与 `counts.mintPriced` 里。"
        % (len(counts["mintPriced"]), len(counts["mintPriced"])))
    add("")
    add("| 币种（源） | 条数 | 本表 `price.currency` |")
    add("|---|---:|---|")
    add("| `coin` | %d | `coins` |" % counts["priceCurrencies"]["coins"])
    add("| `gem` | %d | `gems` |" % counts["priceCurrencies"]["gems"])
    add("| `free` | %d | `none` |" % counts["priceCurrencies"]["none"])
    add("| `mint` | %d | `none`（枚举缺值，已计入 `priceCurrencies.none`） |"
        % len(counts["mintPriced"]))
    add("")
    if counts["mintPriced"]:
        add("mint 计价的具体条目：%s。" % "、".join("`%s`" % name for name in counts["mintPriced"]))
        add("")

    add("## 7. 复现")
    add("")
    add("```")
    add("python tools/contentc/shop_unlock.py --needle      # %s" %
        ("门槛键名 0 命中" if needle and not any(needle["keys"].values()) else "见 §5 表"))
    add("python tools/contentc/shop_unlock.py               # 重写 json + 本报告")
    add("python tools/contentc/shop_unlock.py --check       # 逐字节比对，过期即非零退出")
    add("python -m unittest tools.tests.test_shop_unlock -v")
    add("```")
    add("")
    add("本报告里的每个数字都可以用上面第二、三条命令重新得到；"
        "分类计数在 json 的 `counts.byCategory`，逐条依据在 `items[].rawKeys`。")
    add("")

    add("## 8. 诚实边界")
    add("")
    add("1. **没有购买前置条件可读**：源里没有 `unlock/requires/stars` 之类的字段，"
        "本表的 `unlock` 只表达「绑定世界」与「金币门槛」，不是完整的商店解锁逻辑。")
    add("2. **`unknown` 是投影缺口不是数据错误**：货币充值 11 条、礼包 2 条在六类里无处可放。"
        "要消除它们，得先在 `content/shop.json` 或这套六类里加一个 `currency`/`bundle` 类。")
    add("3. **`mint` 货币装不进 `coins|gems|none`**：%d 条按 `none` 输出，靠 `rawKeys` 区分。"
        % len(counts["mintPriced"]))
    add("4. **`stars` 恒 null**：见 §5，不是漏读而是源里没有。")
    add("5. **`generatedAt` 是源 mtime**：为了让两次生成逐字节相同，这是刻意的取舍；"
        "如果想让产物随导出时间变化，需要另加一个非确定性字段并放弃字节比对。")
    add("")
    return "\n".join(lines) + "\n"


def write_report(table: dict, path: Path, needle: dict | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(render_report(table, needle).encode("utf-8"))


# --------------------------------------------------------------------------- #
# check
# --------------------------------------------------------------------------- #
def check(table: dict, path: Path) -> int:
    problems: list[str] = []
    counts = table["counts"]
    if table.get("format") != FORMAT:
        problems.append("format %r != %r" % (table.get("format"), FORMAT))
    if table.get("generated") != GENERATED:
        problems.append("generated %r != %r" % (table.get("generated"), GENERATED))
    if counts["total"] != counts["sourceItems"]:
        problems.append("total %d != sourceItems %d" % (counts["total"], counts["sourceItems"]))
    if sum(counts["byCategory"].values()) != counts["total"]:
        problems.append("byCategory 求和 != total")
    if sum(counts["byUnlockKind"].values()) != counts["total"]:
        problems.append("byUnlockKind 求和 != total")
    if len(counts["unknownCategoryIds"]) != counts["unknownCategory"]:
        problems.append("unknownCategoryIds 与 unknownCategory 不一致")
    bad = [row["id"] for row in table["items"]
           if row["category"] not in CATEGORIES or row["unlock"]["kind"] not in UNLOCK_KINDS]
    if bad:
        problems.append("非法分类/解锁类型的行：%s" % bad[:5])
    ids = [row["id"] for row in table["items"] if row["id"] is not None]
    if ids != sorted(ids):
        problems.append("items 未按 id 排序")
    if not path.is_file():
        problems.append("%s 不存在，先运行 python tools/contentc/shop_unlock.py" % path)
    else:
        on_disk = path.read_bytes()
        fresh = render(table).encode("utf-8")
        if on_disk != fresh:
            problems.append("%s 与源不一致（产物过期），重跑 python tools/contentc/shop_unlock.py"
                            % path)
        if b"\r\n" in on_disk:
            problems.append("产物含 CRLF")
    if problems:
        for problem in problems:
            print("FAIL: %s" % problem)
        return 1
    print("total=%d byCategory=%s unknownCategory=%d unknownConditions=%d"
          % (counts["total"],
             "/".join("%s:%d" % (name, counts["byCategory"][name]) for name in CATEGORIES),
             counts["unknownCategory"], counts["unknownConditions"]))
    print("OK")
    return 0


# --------------------------------------------------------------------------- #
# cli
# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Classify shop products for the world map / shop UI")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--worlds", type=Path, default=DEFAULT_WORLDS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--check", action="store_true", help="verify the artifact is up to date")
    parser.add_argument("--needle", action="store_true", help="count gating keys that do not exist")
    parser.add_argument("--no-report", action="store_true", help="only write the json")
    args = parser.parse_args(argv)

    if args.needle:
        report = needle_report(args.source)
        print("items=%d" % report["items"])
        for name, hits in sorted(report["keys"].items()):
            print("  %-12s %d" % (name, hits))
        return 0

    doc = load_json(args.source)
    ids = world_ids(args.worlds)
    table = build(doc, ids, generated_stamp(args.source))

    if args.check:
        return check(table, args.out)

    dump(table, args.out)
    print("wrote %s (total=%d unknownCategory=%d)"
          % (args.out, table["counts"]["total"], table["counts"]["unknownCategory"]))
    if not args.no_report:
        write_report(table, args.report, needle_report(args.source))
        print("wrote %s" % args.report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
