"""项目自检：内容 JSON、引用关系、素材文件、模块可导入性。

用法：
  <python> tools/validate_all.py          # 全部检查
  <python> tools/validate_all.py --quick  # 跳过 pygame 导入/渲染检查
退出码：0 = 全部通过；1 = 有错误（会打印 ERROR 行）。
"""
from __future__ import annotations

import json
import os
import sys
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
errors: list[str] = []
warnings: list[str] = []


def err(msg: str):
    errors.append(msg)
    print("ERROR:", msg)


def warn(msg: str):
    warnings.append(msg)
    print("WARN :", msg)


def load_json(rel: str):
    path = os.path.join(ROOT, rel)
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        err(f"缺少文件 {rel}")
    except Exception as e:
        err(f"{rel} JSON 解析失败: {e}")
    return None


def check_content():
    plants = load_json("content/plants.json")
    zombies = load_json("content/zombies.json")
    worlds = load_json("content/worlds.json")
    almanac = load_json("content/almanac.json")

    plant_ids: set[str] = set()
    if isinstance(plants, list):
        if len(plants) != 147:
            warn(f"plants.json 数量 {len(plants)}（期望 147 = 基础 62 + 融合 85）")
        for p in plants:
            for key in ("id", "name_zh", "cost", "hp", "art", "behavior"):
                if key not in p:
                    err(f"plant {p.get('id')} 缺少字段 {key}")
            plant_ids.add(p.get("id", ""))
            art = p.get("art", "")
            if art:
                db_ok = os.path.exists(os.path.join(ROOT, "assets", "db", art, "skeleton.json"))
                static_ok = art.lower().endswith(".png") and os.path.exists(
                    os.path.join(ROOT, "assets", art.replace("/", os.sep)))
                if not (db_ok or static_ok):
                    warnings.append(f"plant {p.get('id')} 素材未就绪: {art}")
    else:
        err("plants.json 不是 list")

    zombie_ids: set[str] = set()
    if isinstance(zombies, list):
        if len(zombies) != 55:
            warn(f"zombies.json 数量 {len(zombies)}（期望 55）")
        for z in zombies:
            for key in ("id", "name_zh", "hp", "speed", "art"):
                if key not in z:
                    err(f"zombie {z.get('id')} 缺少字段 {key}")
            zombie_ids.add(z.get("id", ""))
    else:
        err("zombies.json 不是 list")

    world_ids: list[str] = []
    if isinstance(worlds, list):
        if len(worlds) != 26:
            warn(f"worlds.json 数量 {len(worlds)}（期望 26）")
        for w in worlds:
            for key in ("id", "name_zh", "order", "map"):
                if key not in w:
                    err(f"world {w.get('id')} 缺少字段 {key}")
            world_ids.append(w.get("id", ""))
            mp = w.get("map", "")
            if mp and not os.path.exists(os.path.join(ROOT, "assets", mp)):
                warnings.append(f"world {w.get('id')} 地图未就绪: {mp}")
    else:
        err("worlds.json 不是 list")

    # 关卡
    lvl_dir = os.path.join(ROOT, "content", "levels")
    lvl_files = sorted(f for f in os.listdir(lvl_dir) if f.endswith(".json")) if os.path.isdir(lvl_dir) else []
    if len(lvl_files) != 1809:
        warn(f"关卡数量 {len(lvl_files)}（期望 1809）")
    for f in lvl_files:
        data = load_json(os.path.join("content", "levels", f))
        if not isinstance(data, dict):
            continue
        for key in ("id", "world", "index", "deck", "waves"):
            if key not in data:
                err(f"关卡 {f} 缺少字段 {key}")
        for pid in data.get("deck", []):
            if pid not in plant_ids:
                err(f"关卡 {f} deck 引用未知植物 {pid}")
        for wi, wave in enumerate(data.get("waves", [])):
            for zs in wave.get("zombies", []):
                zid = zs.get("type")
                if zid not in zombie_ids:
                    err(f"关卡 {f} 第{wi+1}波引用未知僵尸 {zid}")
        if data.get("world") not in world_ids:
            err(f"关卡 {f} world 未知: {data.get('world')}")

    if isinstance(almanac, dict):
        for pid in plant_ids:
            if pid not in almanac.get("plants", {}):
                warn(f"图鉴缺少植物 {pid}")
        for zid in zombie_ids:
            if zid not in almanac.get("zombies", {}):
                warn(f"图鉴缺少僵尸 {zid}")
    print(f"内容：{len(plant_ids)} 植物 / {len(zombie_ids)} 僵尸 / {len(world_ids)} 世界 / {len(lvl_files)} 关卡")


def check_assets():
    ui = os.path.join(ROOT, "assets", "ui")
    for name in ("bg_home.jpg", "launcher.png", "font_zh.ttc"):
        if not os.path.exists(os.path.join(ui, name)):
            err(f"缺少 assets/ui/{name}")
    db = os.path.join(ROOT, "assets", "db")
    if os.path.isdir(db):
        ready = plants = zombies = 0
        for root, _dirs, files in os.walk(db):
            if "skeleton.json" not in files:
                continue
            if "texture.png" not in files:
                warn(f"db 模型缺贴图：{root}")
                continue
            ready += 1
            rel = os.path.relpath(root, db)
            if rel.startswith("plants"):
                plants += 1
            elif rel.startswith("zombies"):
                zombies += 1
        print(f"素材：db 角色模型 {ready} 个（植物 {plants} / 僵尸 {zombies} / 其他 {ready - plants - zombies}）")
        if plants < 30:
            warn(f"植物 db 模型仅 {plants} 个（目标 >= 30）")
        if zombies < 15:
            warn(f"僵尸 db 模型仅 {zombies} 个（目标 >= 15 个基础 prefab）")
    else:
        warn("assets/db 不存在（角色素材未生成）")
    for folder, minimum, label in (("world", 8, "世界地图"), ("lawn", 8, "草坪"), ("audio", 15, "音频")):
        d = os.path.join(ROOT, "assets", folder)
        n = len([f for f in os.listdir(d)]) if os.path.isdir(d) else 0
        if n < minimum:
            warn(f"assets/{folder} 仅 {n} 个文件（{label}，目标 >= {minimum}）")


def check_imports(quick: bool):
    sys.path.insert(0, ROOT)
    if not quick:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    for mod in ("game.config", "game.data", "game.assets", "game.save", "game.audio",
                "game.dragonbones", "game.engine.board", "game.engine.entities",
                "game.engine.level", "game.screens.launcher", "game.screens.menu"):
        try:
            __import__(mod)
        except Exception as e:
            if quick and isinstance(e, ImportError) and "pygame" in str(e):
                warn(f"{mod} 导入跳过（--quick）")
            else:
                err(f"{mod} 导入失败: {e}")
                traceback.print_exc()


def main():
    quick = "--quick" in sys.argv
    print("== 内容检查 ==")
    check_content()
    print("== 素材检查 ==")
    check_assets()
    print("== 模块导入检查 ==")
    check_imports(quick)
    print()
    print(f"结果：{len(errors)} 错误 / {len(warnings)} 警告")
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
