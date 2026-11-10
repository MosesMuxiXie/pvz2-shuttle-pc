"""植物融合实验室：配方加载、合成判定、扣费与解锁。

数据来自 ``content/fusions.json``（由 ``tools/build_fusions.py`` 从 OBB 生成）。
本模块是纯逻辑层，不依赖 pygame；界面见 :mod:`game.screens.fusion`。

典型用法::

    lab = FusionLab(app)
    ok, msg = lab.can_craft(lab.recipes[0])
    if ok:
        ok, msg = lab.craft(lab.recipes[0])
"""
from __future__ import annotations

import json
from pathlib import Path

from ..config import CONTENT_DIR

RECIPE_FILE = "fusions.json"


def _to_int(value, default: int = 0) -> int:
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return int(default)


def _to_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _as_id_list(value) -> list[str]:
    out = []
    for item in value or []:
        text = str(item or "").strip()
        if text and text not in out:
            out.append(text)
    return out


class FusionRecipe:
    """一条融合配方（材料 + 产物 + 解锁花费）。"""

    def __init__(self, raw: dict):
        data = dict(raw or {})
        self.raw = data
        self.id = str(data.get("id") or "")
        self.ingredients = [str(x) for x in (data.get("ingredients") or [])]
        self.ingredient_names = [str(x) for x in (data.get("ingredient_names") or [])]
        result = data.get("result")
        self.result = dict(result) if isinstance(result, dict) else {}
        self.unlock_cost = max(0, _to_int(data.get("unlock_cost"), 0))
        self.plantfood_cost = max(0, _to_int(data.get("plantfood_cost"), 0))
        self.unlock_condition = str(data.get("unlock_condition") or "")

    # ---------------------------------------------------------- 便捷属性
    @property
    def result_id(self) -> str:
        return str(self.result.get("id") or "")

    @property
    def name_zh(self) -> str:
        return str(self.result.get("name_zh") or self.result_id or self.id)

    @property
    def name_en(self) -> str:
        return str(self.result.get("name_en") or "")

    @property
    def desc_zh(self) -> str:
        return str(self.result.get("desc_zh") or "")

    @property
    def family(self) -> str:
        return str(self.result.get("family") or "")

    @property
    def behavior(self) -> str:
        return str(self.result.get("behavior") or "")

    @property
    def almanac_no(self):
        return self.result.get("almanac_no")

    def ingredient_name(self, index: int) -> str:
        if 0 <= index < len(self.ingredient_names):
            return self.ingredient_names[index]
        if 0 <= index < len(self.ingredients):
            return self.ingredients[index]
        return ""

    def short_ingredients(self) -> str:
        return " + ".join(self.ingredient_name(i) for i in range(len(self.ingredients)))

    def to_dict(self) -> dict:
        return dict(self.raw)

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        return f"<FusionRecipe {self.id} {self.name_zh}>"


def load_recipes(path=None) -> list[FusionRecipe]:
    """读取 fusions.json；文件缺失/损坏时返回空列表（不抛异常）。"""
    target = Path(path) if path is not None else Path(CONTENT_DIR) / RECIPE_FILE
    try:
        raw = json.loads(target.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return []
    if isinstance(raw, dict):
        items = raw.get("recipes")
    elif isinstance(raw, list):
        items = raw
    else:
        items = None
    recipes = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        recipe = FusionRecipe(item)
        if recipe.id and recipe.result_id:
            recipes.append(recipe)
    return recipes


class FusionLab:
    """融合实验室逻辑：查询配方、判断能否合成、扣费并写入存档。"""

    def __init__(self, app=None, recipes=None, save=None, data=None):
        self.app = app
        self.save = save if save is not None else getattr(app, "save", None)
        self.data = data if data is not None else getattr(app, "data", None)
        self.recipes = list(recipes) if recipes is not None else load_recipes()
        self._by_id = {r.id: r for r in self.recipes}

    # ---------------------------------------------------------- 容器接口
    def __len__(self) -> int:
        return len(self.recipes)

    def __iter__(self):
        return iter(self.recipes)

    def __getitem__(self, index):
        return self.recipes[index]

    def get(self, recipe_id) -> FusionRecipe | None:
        return self._by_id.get(str(recipe_id or ""))

    def recipes_for(self, plant_id) -> list[FusionRecipe]:
        """查询某株植物作为材料的全部配方。"""
        plant = str(plant_id or "")
        return [r for r in self.recipes if plant in r.ingredients]

    def plant_def(self, recipe):
        """配方产物对应的 PlantDef（数据未加载时为 None）。"""
        rec = self._resolve(recipe)
        if rec is None:
            return None
        plants = getattr(self.data, "plants", None) or {}
        return plants.get(rec.result_id)

    # ---------------------------------------------------------- 资源
    @property
    def coins(self) -> int:
        return max(0, _to_int(getattr(self.save, "coins", 0), 0))

    @property
    def plantfood(self) -> int:
        return max(0, _to_int(getattr(self.save, "plantfood", 0), 0))

    def owned_plants(self) -> set[str]:
        owned = getattr(self.save, "unlocked_plants", None) or []
        return {str(x) for x in owned}

    def is_unlocked(self, recipe) -> bool:
        rec = self._resolve(recipe)
        if rec is None:
            return False
        if rec.result_id in self.owned_plants():
            return True
        owns = getattr(self.save, "owns_plant", None)
        if callable(owns):
            try:
                return bool(owns(rec.result_id))
            except Exception:
                return False
        return False

    # ---------------------------------------------------------- 合成
    def can_craft(self, recipe):
        """返回 ``(ok, reason)``；ok 为 False 时 reason 是中文提示。"""
        rec = self._resolve(recipe)
        if rec is None:
            return False, "配方不存在"
        if self.is_unlocked(rec):
            return False, "该融合植物已解锁"
        if self.coins < rec.unlock_cost:
            return False, f"金币不足（需要 {rec.unlock_cost}）"
        if self.plantfood_cost_for(rec) > self.plantfood:
            return False, f"养料不足（需要 {self.plantfood_cost_for(rec)}）"
        return True, ""

    def plantfood_cost_for(self, recipe) -> int:
        rec = self._resolve(recipe)
        return 0 if rec is None else rec.plantfood_cost

    def craft(self, recipe):
        """执行合成：扣金币/养料并解锁产物。返回 ``(ok, message)``。"""
        rec = self._resolve(recipe)
        ok, reason = self.can_craft(rec)
        if not ok:
            return False, reason
        save = self.save
        if save is None:
            return False, "存档不可用"

        cost = rec.unlock_cost
        spend = getattr(save, "spend_coins", None)
        if callable(spend):
            try:
                paid = bool(spend(cost))
            except Exception:
                paid = False
            if not paid:
                return False, "金币不足"
        else:
            coins = _to_int(getattr(save, "coins", 0), 0)
            if coins < cost:
                return False, "金币不足"
            save.coins = coins - cost

        pf_cost = rec.plantfood_cost
        if pf_cost:
            food = _to_int(getattr(save, "plantfood", 0), 0)
            try:
                save.plantfood = max(0, food - pf_cost)
            except Exception:
                pass

        unlock = getattr(save, "unlock_plant", None)
        if callable(unlock):
            try:
                unlock(rec.result_id)
            except Exception:
                self._fallback_unlock(save, rec.result_id)
        else:
            self._fallback_unlock(save, rec.result_id)

        if pf_cost:
            self._persist(save)
        return True, f"合成成功：{rec.name_zh}"

    def _fallback_unlock(self, save, plant_id: str) -> None:
        try:
            owned = getattr(save, "unlocked_plants", None)
            if owned is None:
                owned = []
                save.unlocked_plants = owned
            if plant_id not in owned:
                owned.append(plant_id)
        except Exception:
            pass

    def _persist(self, save) -> None:
        save_fn = getattr(save, "save", None)
        if callable(save_fn):
            try:
                save_fn()
            except Exception:
                pass

    def _resolve(self, recipe):
        if isinstance(recipe, FusionRecipe):
            return recipe
        if isinstance(recipe, dict):
            recipe = FusionRecipe(recipe)
            return recipe if recipe.result_id else None
        return self.get(recipe)

    # ---------------------------------------------------------- 统计
    def unlocked_count(self) -> int:
        return sum(1 for r in self.recipes if self.is_unlocked(r))

    def affordable_count(self) -> int:
        return sum(1 for r in self.recipes if self.can_craft(r)[0])

    def summary(self) -> dict:
        return {
            "recipes": len(self.recipes),
            "unlocked": self.unlocked_count(),
            "affordable": self.affordable_count(),
            "coins": self.coins,
            "plantfood": self.plantfood,
        }
