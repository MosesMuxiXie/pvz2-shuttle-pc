"""战斗实体：植物 / 僵尸 / 子弹 / 阳光 / 小推车 / 简单特效。

渲染策略：优先使用 DragonBones 播放器（``assets.dbplayer``）；
模型缺失（美术尚未就绪）时画带名字的彩色占位块，保证任何阶段都不崩溃。

动画状态：
    植物  "Idle" / "Shoot"（部分行为使用 "Attack"）
    僵尸  "Walk" / "Eat" / "Die"
"""
from __future__ import annotations

import math

import pygame

from ..config import BOARD_ROWS, CELL_W, WIN_W
from . import combat
from . import elements
from .board import cell_center, row_ground_y


def _cell_w(level) -> float:
    """当前关卡的格宽（支持 6x10 等特殊战场）。"""
    return float(getattr(level, "cell_w", CELL_W) or CELL_W)


def _rows(level) -> int:
    return int(getattr(level, "rows", BOARD_ROWS) or BOARD_ROWS)


# ---------------------------------------------------------------- 绘制小工具
def _make_player(assets, art: str, anim: str, armature: str | None = None):
    """尝试创建 DragonBones 播放器；失败返回 None。"""
    if not assets or not art:
        return None
    try:
        return assets.dbplayer(art, anim, armature=armature)
    except TypeError:
        try:
            return assets.dbplayer(art, anim)
        except Exception:
            return None
    except Exception:
        return None


def _fit_scale(player, fallback: float = 0.62) -> float:
    """按模型 root_scale 与格子尺寸换算绘制比例（原版格子 81×108）。"""
    try:
        rs = getattr(player.model, "root_scale", None)
        if rs and float(rs[0]) > 0:
            return float(rs[0]) * (CELL_W / 81.0)
    except Exception:
        pass
    return fallback


def _load_static(assets, art: str, target_h: int):
    """加载导入的静态 PNG 立绘（无骨骼动画时使用）。"""
    if not assets or not art:
        return None
    try:
        return assets.static_sprite(art, target_h)
    except Exception:
        return None


def _placeholder_surface(assets, label: str, w: int, h: int) -> pygame.Surface:
    """带名字的占位块（优先用 Assets.placeholder，失败则纯色块）。"""
    try:
        if assets is not None:
            surf = assets.placeholder(str(label)[:10], w, h)
            if surf is not None:
                return surf
    except Exception:
        pass
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    surf.fill((150, 150, 160, 215))
    pygame.draw.rect(surf, (255, 255, 255, 220), surf.get_rect(), 2)
    return surf


def _blit_alpha(surf, img: pygame.Surface, pos, alpha: int):
    """按 alpha 绘制（仅死亡淡出等少量场景使用）。"""
    alpha = max(0, min(255, int(alpha)))
    if alpha >= 255:
        surf.blit(img, pos)
        return
    tmp = img.copy()
    tmp.set_alpha(alpha)
    surf.blit(tmp, pos)


def _hp_bar(surf, x: int, y: int, w: int, h: int, ratio: float,
            color=(90, 220, 90), back=(40, 40, 40)):
    ratio = max(0.0, min(1.0, ratio))
    pygame.draw.rect(surf, back, (x, y, w, h), border_radius=2)
    if ratio > 0:
        pygame.draw.rect(surf, color, (x, y, max(1, int(w * ratio)), h), border_radius=2)


# ================================================================ 植物
class Plant:
    """一株已种下的植物。

    behavior（来自 PlantDef）：
        shoot / lob / boomerang  远程攻击（pdef.rows 为行偏移，可多行）
        produce                  产阳光（sun_value / sun_interval）
        wall                     纯阻挡
        instant                  落地延时爆炸（delay / damage / extra.radius）
        fume                     近程穿透
        chomp                    吞噬（击杀前方僵尸后长冷却）
        mine                     埋雷（武装后接触爆炸）
        support                  占位（暂无 buff 实现）
    """

    def __init__(self, pdef, row: int, col: int, assets):
        self.pdef = pdef
        self.row = int(row)
        self.col = int(col)
        self.assets = assets

        self.max_hp = float(max(1, int(getattr(pdef, "hp", 300) or 300)))
        self.hp = self.max_hp
        self.alive = True
        self.eatable = str(getattr(pdef, "behavior", "") or "") not in ("mine",)

        self.behavior = str(getattr(pdef, "behavior", "shoot") or "shoot")
        self.damage = float(getattr(pdef, "damage", 20) or 0.0)
        self.interval = float(getattr(pdef, "interval", 1.4) or 1.4)
        rows = list(getattr(pdef, "rows", [0]) or [0])
        if not rows:
            rows = [0]
        self.rows = [int(r) for r in rows]
        self.pierce = bool(getattr(pdef, "pierce", False))
        self.splash = float(getattr(pdef, "splash", 0.0) or 0.0)
        self.slow = float(getattr(pdef, "slow", 0.0) or 0.0)
        self.sun_value = int(getattr(pdef, "sun_value", 25) or 25)
        self.sun_interval = float(getattr(pdef, "sun_interval", 24.0) or 24.0)
        self.delay = float(getattr(pdef, "delay", 0.0) or 0.0)
        self.melee_range = float(getattr(pdef, "melee_range", 1.0) or 1.0)

        self.x, self.y = cell_center(self.row, self.col)
        self.ground_y = row_ground_y(self.row)

        self.player = _make_player(assets, str(getattr(pdef, "art", "") or ""), "Idle")
        self.static = _load_static(assets, str(getattr(pdef, "art", "") or ""), 112)
        self.clock = 0.0
        self.anim = "Idle"
        self.anim_hold = 0.0
        self.scale = _fit_scale(self.player) if self.player is not None else 1.0

        self.attack_timer = 0.35          # 首次攻击/产阳光延迟
        self.sun_timer = min(6.0, self.sun_interval)
        self.fuse_timer = (self.delay or 0.35) if self.behavior == "instant" else 0.0
        self.mine_timer = 0.0
        self.mine_armed = False
        self.boost_t = 0.0
        self.chomp_timer = 0.0
        self.shots = 0
        self.hit_flash = 0.0
        self._fallback: pygame.Surface | None = None

    # ------------------------------------------------------------ 属性
    @property
    def rect(self) -> pygame.Rect:
        w, h = 76, 84
        return pygame.Rect(int(self.x - w // 2), int(self.ground_y - h), w, h)

    hitbox = rect

    @property
    def hp_ratio(self) -> float:
        return self.hp / self.max_hp if self.max_hp > 0 else 0.0

    # ------------------------------------------------------------ 更新
    def update(self, dt: float, level):
        if not self.alive:
            return
        dt = max(0.0, float(dt))
        self.clock += dt
        if self.boost_t > 0.0:
            self.boost_t = max(0.0, self.boost_t - dt)
        self.hit_flash = max(0.0, self.hit_flash - dt)
        self._update_anim(dt)

        if self.chomp_timer > 0:
            self.chomp_timer = max(0.0, self.chomp_timer - dt)

        if self.behavior == "produce":
            self.sun_timer -= dt
            if self.sun_timer <= 0.0:
                self.sun_timer = max(1.0, self.sun_interval)
                if level is not None:
                    level.spawn_sun(self.x, self.ground_y - 42,
                                    self.ground_y - 16, self.sun_value, "plant")
                    level.spawn_burst(self.x, self.ground_y - 46,
                                      (255, 232, 120), 5, 70)
                self._play("Shoot", 0.25)
            return

        if self.behavior == "instant":
            self.fuse_timer -= dt
            if self.fuse_timer <= 0.0:
                self._explode(level)
            return

        if self.behavior == "mine":
            if not self.mine_armed:
                self.mine_timer += dt
                if self.mine_timer >= 2.0:
                    self.mine_armed = True
                return
            target = level.nearest_zombie(self.row, self.x - 45, self.x + 60) \
                if level is not None else None
            if target is not None:
                self._mine_explode(level)
            return

        if self.behavior == "chomp":
            if self.chomp_timer > 0:
                return
            target = level.nearest_zombie(self.row, self.x - 10, self.x + 95) \
                if level is not None else None
            if target is not None:
                combat.damage_zombie(target, 99999.0, level)
                self.chomp_timer = 18.0
                self._play("Attack", 0.5)
                if level is not None:
                    level.spawn_text(target.x, target.ground_y - 80,
                                     "咀嚼！", (255, 210, 120), 16)
            return

        if self.behavior == "fume":
            if self.attack_timer > 0:
                self.attack_timer -= dt
                return
            targets = combat.zombies_in_row(
                level, self.row, x_min=self.x,
                x_max=self.x + self.melee_range * _cell_w(level) + 40) if level else []
            if targets:
                for z in targets:
                    combat.damage_zombie(z, self.damage, level, pierce_armor=True)
                self.attack_timer = max(0.15, self.interval)
                self._play("Shoot", 0.3)
            return

        if self.behavior in ("shoot", "lob", "boomerang"):
            if self.attack_timer > 0:
                self.attack_timer -= dt
                return
            rows = self._target_rows(level)
            if not rows:
                # 没目标时保持快速轮询，僵尸一进入射程立刻开火
                self.attack_timer = 0.08
                return
            self.attack_timer = max(0.2, self.interval * (0.32 if self.boost_t > 0 else 1.0))
            self.shots += 1
            self._play("Shoot", 0.3)
            if level is not None:
                if self.behavior == "lob":
                    kind = "lob"
                elif self.behavior == "boomerang":
                    kind = "boomerang"
                else:
                    kind = str(getattr(self.pdef, "projectile", "pea") or "pea")
                    if kind not in ("pea", "lob", "boomerang"):
                        kind = "pea"
                for r in rows:
                    level.spawn_projectile(self, row=r, kind=kind)
            return

        # wall / support：纯占位，不主动做事

    def _target_rows(self, level) -> list[int]:
        if level is None:
            return []
        out = []
        for off in self.rows:
            r = self.row + int(off)
            if not (0 <= r < _rows(level)):
                continue
            if combat.has_zombie_in_row(level, r, x_min=self.x - 20):
                out.append(r)
        return out

    # ------------------------------------------------------------ 爆炸/特效
    def _explode(self, level):
        extra = getattr(self.pdef, "extra", {}) or {}
        try:
            radius = float(extra.get("radius", _cell_w(level) * 1.35))
        except (TypeError, ValueError):
            radius = _cell_w(level) * 1.35
        if level is not None:
            level.area_damage(self.x, self.ground_y - 40, radius,
                              max(1.0, self.damage), pierce_armor=True)
            level.spawn_burst(self.x, self.ground_y - 44, (255, 150, 60), 22, 200)
            level.shake = max(level.shake, 7.0)
            level.spawn_text(self.x, self.ground_y - 90, "轰！", (255, 190, 90), 22)
        self.hp = 0.0
        self.alive = False

    def _mine_explode(self, level):
        if level is not None:
            level.area_damage(self.x, self.ground_y - 30, 72.0,
                              max(1200.0, self.damage), pierce_armor=True)
            level.spawn_burst(self.x, self.ground_y - 30, (230, 200, 90), 18, 170)
            level.shake = max(level.shake, 5.0)
        self.hp = 0.0
        self.alive = False

    # ------------------------------------------------------------ 动画/绘制
    def _play(self, anim: str, hold: float = 0.0):
        self._set_anim(anim)
        self.anim_hold = max(self.anim_hold, hold)

    def _set_anim(self, name: str):
        if name == self.anim:
            return
        self.anim = name
        if self.player is None:
            return
        try:
            self.player.set_anim(name, loop=True, restart=True)
        except Exception:
            pass

    def _update_anim(self, dt: float):
        if self.player is not None:
            try:
                self.player.update(dt)
            except Exception:
                self.player = None
        for _p in getattr(self, "armor_players", []):
            try:
                _p.update(dt)
            except Exception:
                pass
        if self.anim_hold > 0.0:
            self.anim_hold = max(0.0, self.anim_hold - dt)
            if self.anim_hold <= 0.0 and self.anim != "Idle":
                self._set_anim("Idle")

    def _fallback_surf(self) -> pygame.Surface:
        if self._fallback is None:
            label = (getattr(self.pdef, "name_zh", "")
                     or getattr(self.pdef, "name_en", "")
                     or getattr(self.pdef, "id", "植物"))
            self._fallback = _placeholder_surface(self.assets, label, 78, 82)
        return self._fallback

    def draw(self, surf):
        if not self.alive:
            return
        if getattr(self, "boost_t", 0.0) > 0.0:
            try:
                pygame.draw.circle(surf, (120, 230, 255),
                                   (int(self.x), int(self.ground_y) - 40), 44, 2)
            except Exception:
                pass
        x, y = int(self.x), int(self.ground_y)
        if self.player is not None:
            try:
                self.player.draw(surf, x, y, scale=self.scale)
            except Exception:
                self.player = None
        if self.player is None and self.static is not None:
            dy = int(round(math.sin(self.clock * 2.1 + self.x * 0.01) * 1.6))
            img = self.static
            surf.blit(img, img.get_rect(midbottom=(x, y + dy)))
        elif self.player is None:
            img = self._fallback_surf()
            surf.blit(img, img.get_rect(midbottom=(x, y)))
            # 占位块上补一个行为符号，方便调试
            sym = {"shoot": "▪", "produce": "☀", "wall": "▮",
                   "instant": "✹", "mine": "◎", "fume": "≈",
                   "chomp": "▼", "boomerang": "↩"}.get(self.behavior)
            if sym:
                try:
                    f = self.assets.font(13, True) if self.assets else None
                    if f:
                        t = f.render(sym, True, (255, 255, 255))
                        surf.blit(t, (x + 22, y - 74))
                except Exception:
                    pass

        if self.hp < self.max_hp:
            _hp_bar(surf, x - 23, y - 90, 46, 5, self.hp_ratio,
                    (110, 210, 110) if self.hp_ratio > 0.35 else (230, 170, 70))
        if self.behavior == "mine" and not self.mine_armed:
            pygame.draw.circle(surf, (230, 200, 90), (x, y - 6), 10, 2)

    # ------------------------------------------------------------ 受伤
    def take_damage(self, amount: float, level=None) -> float:
        return combat.damage_plant(self, amount, level)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Plant {getattr(self.pdef, 'id', '?')} r{self.row}c{self.col}>"


# ================================================================ 僵尸
class Zombie:
    """一只僵尸。x 为脚底中心的屏幕 x；向左行走。"""

    def __init__(self, zdef, row: int, x: float, assets, armature=None):
        self.zdef = zdef
        self.row = int(row)
        self.x = float(x)
        self.assets = assets
        self.armature = armature if armature is not None else getattr(zdef, "armature", None)
        # 护甲层使用同一骨架的独立 armature（Cone/Bucket/...），需要与本体叠画
        self.armor_armatures = [
            str(tier["armature"]) for tier in list(getattr(zdef, "armor", []) or [])
            if isinstance(tier, dict) and tier.get("armature")
        ]

        self.max_hp = float(max(1, int(getattr(zdef, "hp", 190) or 190)))
        self.hp = self.max_hp
        self.speed = max(0.0, float(getattr(zdef, "speed", 0.185) or 0.0))  # 格/秒
        self.eat_dps = float(getattr(zdef, "eat_dps", 100) or 0.0)
        self.behavior = str(getattr(zdef, "behavior", "walk") or "walk")
        self.ground_y = row_ground_y(self.row)

        # 护甲：外层 -> 内层
        self.armor: list[dict] = []
        for tier in list(getattr(zdef, "armor", []) or []):
            if isinstance(tier, dict):
                hp = float(tier.get("hp", 0) or 0)
                if hp > 0:
                    art = str(tier.get("art", "") or "")
                    self.armor.append({"hp": hp, "max_hp": hp, "art": art,
                                       "name": str(tier.get("name", "") or art or "护甲")})
            elif isinstance(tier, (int, float)) and float(tier) > 0:
                self.armor.append({"hp": float(tier), "max_hp": float(tier),
                                   "art": "", "name": "护甲"})
        self.max_armor = sum(t["max_hp"] for t in self.armor)

        self.state = "walk"          # walk / eat / die
        self.alive = True
        self.death_t = 0.0
        self.death_dur = 0.9
        self.slow_timer = 0.0
        self.hit_flash = 0.0
        self.eating = None
        self._counted_dead = False
        self.flip = False
        # SHUTTLE 26.10.1 元素反应状态
        self.elements: dict[str, float] = {}
        self.freeze_t = 0.0
        self.vuln_mult = 1.0
        self.vuln_t = 0.0

        self.player = _make_player(assets, str(getattr(zdef, "art", "") or ""), "Walk",
                                   armature=self.armature)
        # 护甲 armature 是独立部件（Cone/Bucket 仅含护甲本身），
        # 脱离骨骼父子关系直接叠画会错位，故不单独渲染。
        self.armor_players = []
        self.anim = "Walk"
        self.anim_hold = 0.0
        self.scale = _fit_scale(self.player) if self.player is not None else 1.0

        # 静态 PNG 立绘（Renders 导入的新世界角色）：按剩余护甲层切换外观
        ex = getattr(zdef, "extra", None) or {}
        if not isinstance(ex, dict):
            ex = {}
        base_art = str(getattr(zdef, "art", "") or "")
        self.art_flip = bool(ex.get("art_flip", False))
        variants: dict[str, str] = {}
        raw_variants = ex.get("art_variants")
        if isinstance(raw_variants, dict) and raw_variants:
            variants = {str(k): str(v) for k, v in raw_variants.items() if v}
        else:
            if base_art:
                variants["base"] = base_art
            for i, tier in enumerate(self.armor):
                if isinstance(tier, dict) and tier.get("art"):
                    variants["armor%d" % (i + 1)] = str(tier["art"])
        target = 150
        zid = str(getattr(zdef, "id", "") or "").lower()
        if "gargantuar" in zid or "gargantuar" in base_art.lower():
            target = 210
        self.static_h = target
        self.static_map: dict[str, pygame.Surface] = {}
        for key, art in variants.items():
            spr = _load_static(assets, art, target)
            if spr is not None:
                self.static_map[key] = spr
        self.clock = 0.0
        self._fallback: pygame.Surface | None = None
        self._armor_icons: dict[str, pygame.Surface] = {}

    # ------------------------------------------------------------ 属性
    @property
    def rect(self) -> pygame.Rect:
        w, h = 64, 120
        return pygame.Rect(int(self.x - w // 2), int(self.ground_y - h), w, h)

    hitbox = rect

    @property
    def head_y(self) -> int:
        return int(self.ground_y - 104)

    @property
    def total_hp(self) -> float:
        return self.hp + sum(t["hp"] for t in self.armor)

    @property
    def max_total_hp(self) -> float:
        return self.max_hp + self.max_armor

    @property
    def slowed(self) -> bool:
        return self.slow_timer > 0.0

    # ------------------------------------------------------------ 更新
    def update(self, dt: float, level):
        dt = max(0.0, float(dt))
        self.clock += dt
        self.hit_flash = max(0.0, self.hit_flash - dt)
        if self.slow_timer > 0.0:
            self.slow_timer = max(0.0, self.slow_timer - dt)
        if self.freeze_t > 0.0:
            self.freeze_t = max(0.0, self.freeze_t - dt)
        if self.vuln_t > 0.0:
            self.vuln_t = max(0.0, self.vuln_t - dt)
            if self.vuln_t <= 0.0:
                self.vuln_mult = 1.0
        elements.tick(self, dt)
        if getattr(self, "_special_t", 0.0) > 0.0:
            self._special_t = max(0.0, self._special_t - dt)

        if self.state == "die":
            self.death_t += dt
            self._update_anim(dt)
            if self.death_t >= self.death_dur:
                self.alive = False
            return

        if self.freeze_t > 0.0:
            # 冻结：完全停止行动（不啃食、不前进）
            self._update_anim(dt)
            return

        # 远程投掷 / 撑杆跳
        if getattr(self, "behavior", "walk") == "ranged" and level is not None:
            if self._special_t <= 0.0:
                plant = self._plant_ahead(level, 360.0)
                if plant is not None:
                    self._special_t = 4.5
                    combat.damage_plant(plant, 45.0, level)
                    try:
                        level.spawn_burst(plant.x, plant.ground_y - 30,
                                          (255, 140, 60), 9, 100)
                        level.spawn_text(plant.x, plant.ground_y - 80,
                                         "投掷!", (255, 190, 120), 16)
                    except Exception:
                        pass
                    self._update_anim(dt)
                    return

        target = combat.find_eat_target(self, level) if level is not None else None
        if target is not None and getattr(self, "behavior", "walk") == "jump" \
                and self._special_t <= 0.0:
            self._special_t = 7.0
            self.x -= 95.0
            try:
                if level is not None:
                    level.spawn_text(self.x, self.ground_y - 96, "撑杆跳!",
                                     (255, 230, 150), 16)
            except Exception:
                pass
            self._update_anim(dt)
            return
        if target is not None:
            if self.state != "eat":
                self.state = "eat"
                self._set_anim("Eat")
            self.eating = target
            combat.zombie_eat(self, target, dt, level)
            self._update_anim(dt)
            return

        if self.state != "walk":
            self.state = "walk"
            self._set_anim("Walk")
        self.eating = None
        mult = 0.5 if self.slow_timer > 0.0 else 1.0
        self.x -= self.speed * _cell_w(level) * mult * dt
        self._update_anim(dt)

    def _plant_ahead(self, level, reach: float):
        best = None
        for p in getattr(level, "plants", []) or []:
            if int(getattr(p, "row", -1)) != int(self.row):
                continue
            px = float(getattr(p, "x", 0.0))
            if self.x - reach <= px <= self.x - 8:
                if best is None or px > float(getattr(best, "x", 0.0)):
                    best = p
        return best

    # ------------------------------------------------------------ 动画/绘制
    def set_anim(self, name: str):
        if name == self.anim:
            return
        self.anim = name
        if self.player is None:
            return
        try:
            self.player.set_anim(name, loop=(name != "Die"), restart=True)
        except Exception:
            pass
        for _p in getattr(self, "armor_players", []):
            try:
                _p.set_anim(name, loop=(name != "Die"), restart=True)
            except Exception:
                pass

    def _set_anim(self, name: str):
        self.set_anim(name)

    def _update_anim(self, dt: float):
        if self.player is not None:
            try:
                self.player.update(dt)
            except Exception:
                self.player = None

    def _fallback_surf(self) -> pygame.Surface:
        if self._fallback is None:
            label = (getattr(self.zdef, "name_zh", "")
                     or getattr(self.zdef, "name_en", "")
                     or getattr(self.zdef, "id", "僵尸"))
            self._fallback = _placeholder_surface(self.assets, label, 62, 112)
        return self._fallback

    def _armor_icon(self, art: str) -> pygame.Surface:
        key = art or "护甲"
        if key not in self._armor_icons:
            self._armor_icons[key] = _placeholder_surface(
                self.assets, key if key != "护甲" else "护甲", 36, 26)
        return self._armor_icons[key]

    def _static_now(self):
        """按剩余护甲层数选择静态立绘（无护甲=base）。"""
        if not self.static_map:
            return None
        alive = sum(1 for t in self.armor if float(t.get("hp", 0) or 0) > 0)
        for key in ("armor%d" % alive, "base"):
            if key in self.static_map:
                return self.static_map[key]
        return next(iter(self.static_map.values()))

    def draw(self, surf):
        if not self.alive and self.state != "die":
            return
        alpha = 255
        if self.state == "die":
            ratio = min(1.0, self.death_t / max(0.01, self.death_dur))
            alpha = int(255 * (1.0 - ratio))
            if alpha <= 0:
                return
        x, y = int(self.x), int(self.ground_y)

        if self.player is not None:
            try:
                self.player.draw(surf, x, y, scale=self.scale, flip=self.flip, alpha=alpha)
            except Exception:
                self.player = None
        if self.player is None and self.static_map:
            spr = self._static_now()
            if spr is not None:
                if self.art_flip:
                    spr = pygame.transform.flip(spr, True, False)
                if self.state == "die":
                    ratio = min(1.0, self.death_t / max(0.01, self.death_dur))
                    img = pygame.transform.rotozoom(spr, -10.0 * ratio,
                                                    1.0 - 0.06 * ratio)
                    img.set_alpha(int(255 * (1.0 - ratio)))
                    surf.blit(img, img.get_rect(midbottom=(x, y + int(8 * ratio))))
                elif self.state == "eat":
                    dy = math.sin(self.clock * 10.0) * 1.6
                    surf.blit(spr, spr.get_rect(midbottom=(int(x), int(y + dy))))
                else:
                    dy = -abs(math.sin(self.clock * 6.0)) * 2.2
                    dx = math.sin(self.clock * 3.0) * 0.8
                    surf.blit(spr, spr.get_rect(midbottom=(int(x + dx), int(y + dy))))
        elif self.player is None:
            img = self._fallback_surf()
            _blit_alpha(surf, img, img.get_rect(midbottom=(x, y)), alpha)

        if self.armor and self.state != "die":
            tier = self.armor[0]
            if tier["max_hp"] > 0:
                _hp_bar(surf, x - 18, self.head_y - 20, 36, 4,
                        tier["hp"] / tier["max_hp"], (210, 200, 230))

        # 血条
        if self.hp < self.max_hp and self.state != "die":
            _hp_bar(surf, x - 24, y - 136, 48, 5, self.hp / max(1.0, self.max_hp),
                    (220, 90, 80))
        if self.slowed and self.state != "die":
            pygame.draw.circle(surf, (120, 190, 240), (x, y - 60), 5, 2)

        # 元素附着 / 冻结状态
        if self.state != "die":
            if getattr(self, "freeze_t", 0.0) > 0.0:
                ice = pygame.Surface((54, 118), pygame.SRCALPHA)
                ice.fill((150, 215, 255, 56))
                surf.blit(ice, ice.get_rect(midbottom=(x, y)))
            attached = getattr(self, "elements", None) or {}
            if attached:
                i = 0
                for name in list(attached.keys())[:4]:
                    color = elements.ELEMENT_COLOR.get(name, (255, 255, 255))
                    pygame.draw.circle(surf, color, (x - 18 + i * 12, int(self.head_y) - 26), 4)
                    i += 1
            if getattr(self, "vuln_t", 0.0) > 0.0:
                try:
                    f = self.assets.font(12, True) if self.assets else None
                    if f:
                        t = f.render("超导", True, (255, 236, 140))
                        surf.blit(t, t.get_rect(midbottom=(x, int(self.ground_y) + 14)))
                except Exception:
                    pass

    # ------------------------------------------------------------ 受伤/控制
    def take_damage(self, amount: float, level=None, pierce_armor: bool = False) -> float:
        return combat.damage_zombie(self, amount, level, pierce_armor=pierce_armor)

    def apply_slow(self, seconds: float):
        combat.apply_slow(self, seconds)

    def die(self, level=None):
        combat.kill_zombie(self, level)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Zombie {getattr(self.zdef, 'id', '?')} r{self.row} x={self.x:.0f} hp={self.hp:.0f}>"


# ================================================================ 子弹
# ================================================================ 元素反应
def _apply_element_hit(owner, z, level, base_damage: float) -> float:
    """把一次带元素攻击结算到僵尸上，返回实际伤害。"""
    elem = getattr(owner, "element", None)
    if not elem or z is None or level is None:
        return base_damage
    try:
        res = elements.resolve_hit(z, elem, base_damage)
    except Exception:
        return base_damage
    clr = res.get("clear") or ()
    if clr:
        try:
            elements.clear(z, clr)
        except Exception:
            pass
    try:
        elements.attach(z, elem)
    except Exception:
        pass
    mult = float(res.get("mult") or 1.0)
    for eff in res.get("effects") or []:
        try:
            if not isinstance(eff, dict):
                continue
            t = eff.get("type")
            if t == "freeze":
                z.freeze_t = max(getattr(z, "freeze_t", 0.0),
                                 float(eff.get("seconds", 1.5)))
            elif t == "vulnerable":
                z.vuln_mult = 1.0 + float(eff.get("mult", 0.75))
                z.vuln_t = max(getattr(z, "vuln_t", 0.0),
                               float(eff.get("seconds", 10.0)))
            elif t == "aoe":
                dmg = eff.get("damage")
                if dmg == "attack":
                    dmg = min(base_damage, float(eff.get("cap", 1000.0)))
                level.area_damage(z.x, z.ground_y - 50.0,
                                  float(eff.get("radius", 190.0)),
                                  float(dmg or 0.0))
            elif t == "spread":
                for other in getattr(level, "zombies", []):
                    if other is z or not getattr(other, "alive", False):
                        continue
                    if abs(other.x - z.x) <= 130 and abs(other.row - z.row) <= 1:
                        try:
                            elements.attach(other, str(eff.get("element")), 5.0)
                        except Exception:
                            pass
        except Exception:
            continue
    reaction = res.get("reaction")
    if reaction:
        try:
            level.spawn_text(z.x, z.ground_y - 112.0, reaction,
                             color=(255, 232, 128), size=20)
            level.spawn_burst(z.x, z.ground_y - 60.0, (255, 214, 96), 10, 150)
        except Exception:
            pass
    return base_damage * mult


# ================================================================ 子弹
class Projectile:
    """植物子弹。

    kind:
        pea        直线飞行，同行碰撞（pierce 可穿透，splash 可溅射）
        lob        抛物线，落点取最近僵尸位置，落地范围伤害
        boomerang  去程/回程，穿透，同一僵尸只命中一次

    slow 为减速持续时间（秒），0 表示不减速。
    """

    KINDS = ("pea", "lob", "boomerang")

    def __init__(self, kind: str = "pea", x: float = 0.0, y: float = 0.0,
                 row: int = 0, damage: float = 20.0, *, assets=None, plant=None,
                 pierce: bool = False, splash: float = 0.0, slow: float = 0.0,
                 target_x: float | None = None, speed: float = 330.0,
                 element: str | None = None):
        self.kind = kind if kind in self.KINDS else "pea"
        self.x = float(x)
        self.y = float(y)
        self.start_x = self.x
        self.start_y = self.y
        self.row = int(row)
        self.damage = float(damage)
        self.element = element if element in elements.ELEMENTS else None
        self.assets = assets
        self.plant = plant
        self.pierce = bool(pierce)
        self.splash = float(splash or 0.0)
        self.slow = float(slow or 0.0)
        self.speed = float(speed)
        self.target_x = target_x
        self.alive = True
        self.hit_ids: set[int] = set()
        self.hits = 0
        self.pierce_left = 4 if self.pierce else 0
        self.ground_y = row_ground_y(self.row)
        self.t = 0.0
        self.angle = 0.0
        self.arc = 118.0
        self.duration = 0.0
        self.flight_t = 0.0
        self.phase = "out"
        self.max_range = 360.0

    # ------------------------------------------------------------ 属性
    @property
    def rect(self) -> pygame.Rect:
        r = 12 if self.kind != "boomerang" else 16
        return pygame.Rect(int(self.x - r), int(self.y - r), r * 2, r * 2)

    # ------------------------------------------------------------ 更新
    def update(self, dt: float, level):
        if not self.alive:
            return
        dt = max(0.0, float(dt))
        if self.kind == "pea":
            self._update_pea(dt, level)
        elif self.kind == "lob":
            self._update_lob(dt, level)
        else:
            self._update_boomerang(dt, level)

    def _update_pea(self, dt: float, level):
        # 分步推进，避免帧率抖动时一颗豌豆跨过整只僵尸
        move = self.speed * dt
        while move > 1e-9 and self.alive:
            step = min(move, 12.0)
            self.x += step
            move -= step
            if self.x > WIN_W + 60:
                self.alive = False
                return
            if level is None:
                continue
            for z in combat.projectile_hits(self, level):
                self._on_hit(z, level)
                if not self.alive:
                    break

    def _update_lob(self, dt: float, level):
        self.flight_t += dt
        if self.target_x is None:
            target = (combat.nearest_zombie_in_row(level, self.row, self.start_x)
                      if level is not None else None)
            self.target_x = float(target.x) if target is not None \
                else self.start_x + 3 * _cell_w(level)
        dist = max(40.0, float(self.target_x) - self.start_x)
        if self.duration <= 0.0:
            self.duration = max(0.45, min(1.5, dist / 300.0))
        t = min(1.0, self.flight_t / self.duration)
        self.t = t
        self.x = self.start_x + (float(self.target_x) - self.start_x) * t
        land_y = self.ground_y - 42.0
        self.y = (self.start_y + (land_y - self.start_y) * t
                  - self.arc * math.sin(math.pi * t))
        if t >= 1.0:
            self._land(level)

    def _land(self, level):
        radius = max(60.0, self.splash) if self.splash > 0 else 60.0
        if level is not None:
            level.area_damage(self.x, self.ground_y - 40, radius, self.damage,
                              slow=self.slow)
            level.spawn_burst(self.x, self.ground_y - 34, (180, 220, 90), 12, 120)
        self.alive = False

    def _update_boomerang(self, dt: float, level):
        self.angle += dt * 14.0
        remaining = self.speed * dt
        while remaining > 1e-9 and self.alive:
            step = min(remaining, 12.0)
            remaining -= step
            if self.phase == "out":
                self.x += step
                if self.x - self.start_x >= self.max_range:
                    self.phase = "back"
            else:
                self.x -= step * 1.15
                if self.x <= self.start_x - 8:
                    self.alive = False
                    break
            self.y = self.start_y - 40.0 - 12.0 * math.sin(self.angle)
            if level is None:
                continue
            for z in combat.projectile_hits(self, level):
                self.hit_ids.add(id(z))
                self.hits += 1
                combat.damage_zombie(z, _apply_element_hit(self, z, level, self.damage), level)
                if self.slow:
                    combat.apply_slow(z, self.slow)
                level.spawn_burst(z.x, z.ground_y - 50, (220, 200, 120), 4, 70)

    def _on_hit(self, z, level):
        self.hit_ids.add(id(z))
        self.hits += 1
        dmg = _apply_element_hit(self, z, level, self.damage)
        combat.damage_zombie(z, dmg, level)
        if self.slow:
            combat.apply_slow(z, self.slow)
        if self.splash > 0:
            level.area_damage(z.x, z.ground_y - 50, max(40.0, self.splash),
                              self.damage * 0.5, slow=self.slow,
                              exclude={id(z)})
        level.spawn_burst(z.x, z.ground_y - 50, (130, 220, 100), 4, 70)
        if self.pierce_left > 0:
            self.pierce_left -= 1
        else:
            self.alive = False

    # ------------------------------------------------------------ 绘制
    def draw(self, surf):
        if not self.alive:
            return
        x, y = int(self.x), int(self.y)
        if self.kind == "pea":
            pygame.draw.circle(surf, (110, 200, 70), (x, y), 9)
            pygame.draw.circle(surf, (170, 235, 120), (x - 3, y - 3), 4)
        elif self.kind == "lob":
            pygame.draw.circle(surf, (170, 210, 100), (x, y), 11)
            pygame.draw.circle(surf, (205, 235, 150), (x - 3, y - 4), 5)
        else:
            # 回旋镖：旋转的弧
            size = 22
            rect = pygame.Rect(x - size // 2, y - size // 2, size, size)
            start = int(math.degrees(self.angle)) % 360
            try:
                pygame.draw.arc(surf, (225, 200, 120), rect,
                                math.radians(start), math.radians(start + 210), 5)
            except Exception:
                pygame.draw.circle(surf, (225, 200, 120), (x, y), 8, 3)


# ================================================================ 阳光
class Sun:
    """可点击收集的阳光；天降或植物产出。"""

    def __init__(self, x: float, y: float, target_y: float | None = None,
                 value: int = 25, assets=None, kind: str = "sky",
                 lifetime: float = 13.0):
        self.x = float(x)
        self.y = float(y)
        self.target_y = float(y if target_y is None else target_y)
        self.value = int(value)
        self.assets = assets
        self.kind = kind
        self.life = float(lifetime)
        self.t = 0.0
        self.collected = False
        self.alive = True
        self.radius = 24
        self.fall_speed = 90.0
        self.phase = "fall" if self.y < self.target_y - 1.0 else "rest"

    @property
    def collectible(self) -> bool:
        return bool(self.alive) and not self.collected

    @property
    def rect(self) -> pygame.Rect:
        r = 28
        return pygame.Rect(int(self.x - r), int(self.y - r), r * 2, r * 2)

    def update(self, dt: float):
        if not self.alive:
            return
        dt = max(0.0, float(dt))
        self.t += dt
        if self.phase == "fall":
            self.y = min(self.target_y, self.y + self.fall_speed * dt)
            if self.y >= self.target_y - 0.5:
                self.y = self.target_y
                self.phase = "rest"
        else:
            self.life -= dt
            if self.life <= 0.0:
                self.alive = False

    def draw(self, surf):
        if not self.alive or self.collected:
            return
        # 快消失时闪烁
        if self.phase == "rest" and self.life < 3.0 and int(self.life * 8) % 2 == 0:
            return
        x, y = int(self.x), int(self.y)
        r = int(self.radius + 2 * math.sin(self.t * 5.0))
        # 光晕
        glow = pygame.Surface((r * 3, r * 3), pygame.SRCALPHA)
        pygame.draw.circle(glow, (255, 230, 110, 60), (r * 3 // 2, r * 3 // 2), r + 8)
        surf.blit(glow, glow.get_rect(center=(x, y)))
        # 真实阳光贴图（assets/ui/sun.png），缺失时退回程序化绘制
        img = None
        try:
            if self.assets is not None:
                img = self.assets.image("ui/sun.png")
        except Exception:
            img = None
        if img is not None:
            size = int(58 * (0.94 + 0.06 * math.sin(self.t * 4.0)))
            try:
                pic = pygame.transform.smoothscale(img, (size, size))
                surf.blit(pic, pic.get_rect(center=(x, y)))
                return
            except Exception:
                pass
        pygame.draw.circle(surf, (255, 225, 80), (x, y), r)
        pygame.draw.circle(surf, (255, 248, 180), (x - 3, y - 4), max(3, r // 2))
        # 光芒
        for i in range(8):
            a = self.t * 0.8 + i * math.pi / 4
            x1 = x + int(math.cos(a) * (r + 2))
            y1 = y + int(math.sin(a) * (r + 2))
            x2 = x + int(math.cos(a) * (r + 8))
            y2 = y + int(math.sin(a) * (r + 8))
            pygame.draw.line(surf, (255, 240, 140), (x1, y1), (x2, y2), 2)


# ================================================================ 小推车
class LawnMower:
    """每行一台的小推车；僵尸逼近时启动，向右碾碎整行僵尸。"""

    def __init__(self, row: int, x: float = 140.0):
        self.row = int(row)
        self.x = float(x)
        self.start_x = float(x)
        self.state = "ready"      # ready / active / used
        self.alive = True
        self.speed = 520.0
        self.trigger_x = 165.0
        self.wheel = 0.0

    @property
    def used(self) -> bool:
        return self.state == "used"

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x - 30), int(row_ground_y(self.row) - 40), 60, 40)

    def update(self, dt: float, level):
        dt = max(0.0, float(dt))
        if self.state == "ready":
            if level is not None and combat.has_zombie_in_row(
                    level, self.row, x_max=self.trigger_x):
                self.state = "active"
                if level is not None:
                    level.shake = max(level.shake, 4.0)
                    level.spawn_text(self.x, row_ground_y(self.row) - 70,
                                     "小推车启动！", (255, 200, 120), 16)
            return
        if self.state == "active":
            self.x += self.speed * dt
            self.wheel += dt * 22.0
            if level is not None:
                for z in combat.zombies_in_row(level, self.row,
                                               x_min=self.x - 90, x_max=self.x + 90):
                    combat.damage_zombie(z, 999999.0, level, pierce_armor=True)
            if self.x > WIN_W + 80:
                self.state = "used"
                self.alive = False

    def draw(self, surf):
        if self.state == "used":
            return
        x = int(self.x)
        y = int(row_ground_y(self.row))
        if self.state == "active":
            pygame.draw.ellipse(surf, (40, 34, 26), (x - 34, y - 12, 68, 14))
        # 阴影
        pygame.draw.ellipse(surf, (55, 60, 48), (x - 30, y - 6, 60, 10))
        # 草地挡板（前部）
        pygame.draw.rect(surf, (110, 150, 70), (x - 34, y - 20, 14, 14), border_radius=3)
        # 机身：红色梯形 + 高光
        body = [(x - 24, y - 34), (x + 18, y - 34), (x + 26, y - 18),
                (x - 30, y - 18)]
        pygame.draw.polygon(surf, (188, 60, 52), body)
        pygame.draw.polygon(surf, (236, 110, 96), [(x - 22, y - 32),
                                                    (x + 16, y - 32),
                                                    (x + 8, y - 24),
                                                    (x - 24, y - 24)])
        pygame.draw.polygon(surf, (110, 26, 30), body, 2)
        # 发动机罩
        pygame.draw.rect(surf, (196, 198, 200), (x - 8, y - 46, 20, 12),
                         border_radius=3)
        pygame.draw.rect(surf, (150, 152, 156), (x - 8, y - 40, 20, 5))
        pygame.draw.circle(surf, (70, 70, 74), (x + 4, y - 46), 3)
        # 推杆（朝左后）
        pygame.draw.line(surf, (72, 74, 80), (x - 22, y - 30),
                         (x - 42, y - 46), 4)
        pygame.draw.line(surf, (72, 74, 80), (x - 42, y - 46),
                         (x - 48, y - 40), 4)
        # 轮子
        for dx, r in ((-18, 9), (18, 9)):
            pygame.draw.circle(surf, (38, 40, 42), (x + dx, y - 9), r)
            pygame.draw.circle(surf, (96, 98, 102), (x + dx, y - 9), r - 3)
            pygame.draw.circle(surf, (200, 202, 206), (x + dx, y - 9), 2)
            for k in range(4):
                a = self.wheel + k * math.pi / 2 + (0 if dx < 0 else 0.4)
                pygame.draw.line(surf, (140, 142, 146),
                                 (x + dx, y - 9),
                                 (x + dx + int(math.cos(a) * (r - 4)),
                                  y - 9 + int(math.sin(a) * (r - 4))), 1)
        # 旋转刀刃
        if self.state == "active":
            ang = self.wheel
            for k in range(4):
                a = ang + k * math.tau / 4
                x2 = x + 30 + int(math.cos(a) * 15)
                y2 = y - 12 + int(math.sin(a) * 15)
                pygame.draw.line(surf, (225, 228, 230), (x + 30, y - 12), (x2, y2), 3)
        else:
            pygame.draw.polygon(surf, (180, 182, 186),
                                [(x + 26, y - 26), (x + 44, y - 20), (x + 26, y - 12)])


# ================================================================ 简单特效
class FloatingText:
    """上浮文字（伤害 / +25 阳光 / 提示）。"""

    def __init__(self, x: float, y: float, text: str, color=(255, 255, 255),
                 life: float = 0.9, size: int = 18, dy: float = -42.0):
        self.x = float(x)
        self.y = float(y)
        self.text = str(text)
        self.color = color
        self.life = max(0.05, float(life))
        self.size = int(size)
        self.dy = float(dy)
        self.t = 0.0
        self.alive = True

    def update(self, dt: float):
        dt = max(0.0, float(dt))
        self.t += dt
        self.y += self.dy * dt
        if self.t >= self.life:
            self.alive = False

    def draw(self, surf, font=None):
        if not self.alive or font is None:
            return
        alpha = int(255 * max(0.0, 1.0 - self.t / self.life))
        try:
            img = font.render(self.text, True, self.color)
            img.set_alpha(alpha)
            surf.blit(img, img.get_rect(center=(int(self.x), int(self.y))))
        except Exception:
            pass


class Particle:
    """简单粒子（爆炸/命中/收集阳光）。"""

    def __init__(self, x: float, y: float, vx: float, vy: float,
                 color=(255, 220, 120), life: float = 0.5, radius: int = 4):
        self.x = float(x)
        self.y = float(y)
        self.vx = float(vx)
        self.vy = float(vy)
        self.color = color
        self.life = max(0.05, float(life))
        self.t = 0.0
        self.radius = int(radius)
        self.alive = True

    def update(self, dt: float):
        dt = max(0.0, float(dt))
        self.t += dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.vy += 420.0 * dt
        self.vx *= (1.0 - min(0.9, dt * 2.0))
        if self.t >= self.life:
            self.alive = False

    def draw(self, surf, font=None):
        if not self.alive:
            return
        ratio = max(0.0, 1.0 - self.t / self.life)
        r = max(1, int(self.radius * ratio))
        pygame.draw.circle(surf, self.color, (int(self.x), int(self.y)), r)
