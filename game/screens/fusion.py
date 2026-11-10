"""植物融合实验室：左侧配方列表、中间材料/产物预览、右侧详情与合成按钮。"""
from __future__ import annotations

import pygame

from .base import Screen
from . import widgets as ui
from ..engine.fusion import FusionLab

WIN_W, WIN_H = 1280, 720
TOP_H = 96

LIST_RECT = pygame.Rect(24, 112, 372, 524)
MID_RECT = pygame.Rect(408, 112, 440, 524)
SIDE_RECT = pygame.Rect(860, 112, 396, 524)

ROW_H = 52
ROW_GAP = 6
ROWS_PER_PAGE = 8
LIST_TOP = 168

BEHAVIOR_ZH = {
    "shoot": "射手", "lob": "投手", "produce": "生产", "wall": "防御",
    "support": "辅助", "spike": "近战尖刺", "chomp": "吞咽",
    "fume": "喷毒", "instant": "一次性", "mine": "地雷", "boomerang": "回旋",
}


def _font(app, size, bold=False):
    try:
        return app.font(size, bold)
    except Exception:
        try:
            return app.assets.font(size, bold)
        except Exception:
            return pygame.font.Font(None, int(size))


class FusionScreen(Screen):
    name = "fusion"

    def __init__(self, app):
        super().__init__(app)
        self._fonts = {}
        self._bg = None
        self.toast = ui.Toast(app)
        self.lab = FusionLab(app)
        self.page = 0
        self.selected = 0
        self.btn_back = ui.Button(app, (24, 22, 110, 46), "返回",
                                  on_click=self._back, style="cream", font_size=18)
        self.btn_prev = ui.Button(app, (40, 642, 92, 32), "上一页",
                                  on_click=self._prev_page, style="cream", font_size=15)
        self.btn_next = ui.Button(app, (288, 642, 92, 32), "下一页",
                                  on_click=self._next_page, style="cream", font_size=15)
        self.btn_craft = ui.Button(app, (884, 556, 348, 52), "合成",
                                   on_click=self._craft, style="gold", font_size=21)
        self._page_count = 1

    # ------------------------------------------------------------ 生命周期
    def enter(self):
        super().enter()
        self.lab = FusionLab(self.app)
        self.page = 0
        self.selected = 0
        self._page_count = max(1, (len(self.lab) + ROWS_PER_PAGE - 1) // ROWS_PER_PAGE)
        self._sync_button()
        try:
            self.app.audio.play_menu()
        except Exception:
            pass

    def exit(self):
        self._bg = None
        self.lab = None

    def _back(self):
        self.app.switch("modes")

    # ------------------------------------------------------------ 选择/翻页
    def _page_count_now(self) -> int:
        return max(1, (len(self.lab) + ROWS_PER_PAGE - 1) // ROWS_PER_PAGE)

    def _prev_page(self):
        if self.page > 0:
            self.page -= 1
            self._sync_button()

    def _next_page(self):
        if self.page + 1 < self._page_count_now():
            self.page += 1
            self._sync_button()

    def _select(self, index):
        recipes = self.lab.recipes if self.lab is not None else []
        if not recipes:
            return
        self.selected = max(0, min(int(index), len(recipes) - 1))
        self.page = self.selected // ROWS_PER_PAGE
        self._sync_button()

    def _selected_recipe(self):
        recipes = self.lab.recipes if self.lab is not None else []
        if not recipes:
            return None
        self.selected = max(0, min(self.selected, len(recipes) - 1))
        return recipes[self.selected]

    def _sync_button(self):
        recipe = self._selected_recipe()
        if recipe is None:
            self.btn_craft.set_enabled(False)
            self.btn_craft.set_text("暂无配方")
            return
        if self.lab.is_unlocked(recipe):
            self.btn_craft.set_enabled(False)
            self.btn_craft.set_text("已解锁")
            return
        ok, _reason = self.lab.can_craft(recipe)
        self.btn_craft.set_enabled(ok)
        self.btn_craft.set_text(f"合成 · {recipe.unlock_cost} 金币")

    # ------------------------------------------------------------ 事件
    def handle(self, event):
        super().handle(event)
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self._back()
                return
            if event.key in (pygame.K_LEFT, pygame.K_PAGEUP):
                self._prev_page()
                return
            if event.key in (pygame.K_RIGHT, pygame.K_PAGEDOWN):
                self._next_page()
                return
            if event.key == pygame.K_UP:
                self._select(self.selected - 1)
                return
            if event.key == pygame.K_DOWN:
                self._select(self.selected + 1)
                return
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                self._craft()
                return
        if self.btn_back.handle(event):
            return
        if self.btn_prev.handle(event):
            return
        if self.btn_next.handle(event):
            return
        if self.btn_craft.handle(event):
            return
        if event.type == pygame.MOUSEWHEEL:
            if self.mouse[0] < LIST_RECT.right:
                if event.y > 0:
                    self._prev_page()
                elif event.y < 0:
                    self._next_page()
            return
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if LIST_RECT.collidepoint(event.pos):
                start = self.page * ROWS_PER_PAGE
                for slot in range(ROWS_PER_PAGE):
                    index = start + slot
                    if index >= len(self.lab):
                        break
                    rect = self._row_rect(slot)
                    if rect.collidepoint(event.pos):
                        self._select(index)
                        return

    def update(self, dt):
        super().update(dt)
        self.toast.update(dt)
        self.btn_back.update(dt)
        self.btn_prev.update(dt)
        self.btn_next.update(dt)
        self.btn_craft.update(dt)
        self._sync_button()

    # ------------------------------------------------------------ 合成
    def _craft(self):
        recipe = self._selected_recipe()
        if recipe is None:
            return
        ok, message = self.lab.craft(recipe)
        self.toast.show(message, 2.4)
        if ok:
            try:
                self.app.audio.play_jingle("victory")
            except Exception:
                pass
        self._sync_button()

    # ------------------------------------------------------------ 绘制
    def _font_cached(self, size, bold=False):
        key = (int(size), bool(bold))
        font = self._fonts.get(key)
        if font is None:
            font = _font(self.app, size, bold)
            self._fonts[key] = font
        return font

    def _row_rect(self, slot):
        return pygame.Rect(LIST_RECT.x + 12,
                           LIST_TOP + slot * (ROW_H + ROW_GAP),
                           LIST_RECT.w - 24, ROW_H)

    def _build_bg(self):
        surf = pygame.Surface((WIN_W, WIN_H))
        img = None
        try:
            img = ui.load_cover(self.app, "lawn/frontyard.png", (WIN_W, WIN_H))
        except Exception:
            img = None
        if img is not None:
            surf.blit(img, (0, 0))
        else:
            ui.draw_gradient(surf, (0, 0, WIN_W, WIN_H), (64, 84, 58), (22, 28, 20))
        ui.draw_dim(surf, None, 198, (12, 14, 10))
        return surf

    def draw(self, surf):
        if self._bg is None:
            self._bg = self._build_bg()
        surf.blit(self._bg, (0, 0))

        # 顶部标题栏
        ui.draw_gradient(surf, (0, 0, WIN_W, TOP_H), (80, 58, 34), (52, 38, 24))
        pygame.draw.line(surf, ui.GOLD, (0, TOP_H - 1), (WIN_W, TOP_H - 1), 2)
        ui.text(surf, self._font_cached(30, True), "植物融合",
                (160, 18), ui.CREAM, shadow=(24, 16, 10))
        ui.text(surf, self._font_cached(15),
                "两株植物合二为一 · 解锁更强的融合植物",
                (162, 60), (232, 220, 190))
        self.btn_back.draw(surf)
        self._draw_coins(surf)

        self._draw_list(surf)
        self._draw_preview(surf)
        self._draw_details(surf)

        ui.text(surf, self._font_cached(13),
                "点击列表选择配方 · 滚轮/左右键翻页 · 回车合成 · ESC 返回",
                (WIN_W // 2, WIN_H - 20), (206, 212, 186), anchor="center")
        self.toast.draw(surf)
        self.draw_fade(surf)

    def _draw_coins(self, surf):
        coins = self.lab.coins if self.lab is not None else 0
        food = self.lab.plantfood if self.lab is not None else 0
        chip = pygame.Rect(WIN_W - 250, 26, 226, 44)
        ui.draw_panel(surf, chip, fill=(36, 28, 18), border=(150, 116, 56),
                      radius=22, border_width=2, shadow=False)
        ui.draw_coin(surf, (chip.x + 26, chip.centery), 15)
        ui.text(surf, self._font_cached(18, True), f"{coins}", (chip.x + 46, chip.centery),
                ui.GOLD, anchor="midleft")
        ui.text(surf, self._font_cached(13), "金币", (chip.x + 100, chip.centery),
                (196, 180, 150), anchor="midleft")
        ui.text(surf, self._font_cached(13), f"养料 {food}", (chip.right - 14, chip.centery),
                (188, 214, 168), anchor="midright")

    # ------------------------------------------------------------ 列表
    def _draw_list(self, surf):
        ui.draw_panel(surf, LIST_RECT, fill=(30, 38, 26), border=(118, 96, 54),
                      radius=14, border_width=2)
        recipes = self.lab.recipes if self.lab is not None else []
        ui.text(surf, self._font_cached(17, True), "融合配方",
                (LIST_RECT.x + 16, LIST_RECT.y + 12), ui.CREAM)
        ui.text(surf, self._font_cached(13), f"{len(recipes)} 条",
                (LIST_RECT.right - 16, LIST_RECT.y + 16), ui.GOLD, anchor="topright")

        start = self.page * ROWS_PER_PAGE
        for slot in range(ROWS_PER_PAGE):
            index = start + slot
            if index >= len(recipes):
                break
            self._draw_row(surf, self._row_rect(slot), index, recipes[index])

        page_count = self._page_count_now()
        self.btn_prev.set_enabled(self.page > 0)
        self.btn_next.set_enabled(self.page + 1 < page_count)
        self.btn_prev.draw(surf)
        self.btn_next.draw(surf)
        ui.text(surf, self._font_cached(14, True),
                f"{self.page + 1} / {page_count}",
                (LIST_RECT.centerx, 658), (226, 220, 196), anchor="center")

    def _draw_row(self, surf, rect, index, recipe):
        active = index == self.selected
        hover = rect.collidepoint(self.mouse)
        body = rect
        if active:
            ui.draw_gradient(surf, body, (96, 76, 42), (66, 52, 30), radius=10)
            pygame.draw.rect(surf, ui.GOLD, body, 2, border_radius=10)
        elif hover:
            pygame.draw.rect(surf, (52, 62, 44), body, border_radius=10)
        else:
            pygame.draw.rect(surf, (38, 48, 34), body, border_radius=10)

        unlocked = self.lab.is_unlocked(recipe)
        name = ui.fit_text(self._font_cached(16, True), recipe.name_zh, rect.w - 96)
        ui.text(surf, self._font_cached(16, True), name,
                (rect.x + 12, rect.y + 7), ui.CREAM if active else (226, 228, 210))
        note = recipe.short_ingredients()
        note = ui.fit_text(self._font_cached(12), note, rect.w - 96)
        ui.text(surf, self._font_cached(12), note,
                (rect.x + 12, rect.y + 29), (176, 188, 160))
        if unlocked:
            ui.draw_check(surf, (rect.right - 24, rect.centery), 10)
        else:
            ui.draw_coin(surf, (rect.right - 26, rect.centery), 8)
            ui.text(surf, self._font_cached(13, True), f"{recipe.unlock_cost}",
                    (rect.right - 12, rect.centery + 1), ui.GOLD, anchor="midright")

    # ------------------------------------------------------------ 中栏
    def _plant_art(self, recipe, size):
        if recipe is None:
            return None
        art = str(recipe.result.get("art") or "")
        try:
            if art.endswith(".png"):
                img = self.app.assets.static_sprite(art, size[1])
            else:
                img = self.app.assets.db_thumb(art, size[0], size[1])
            if img is not None:
                return ui.scale_image(img, size)
        except Exception:
            pass
        try:
            return self.app.assets.placeholder(recipe.name_zh[:2], size[0], size[1])
        except Exception:
            return None

    def _draw_preview(self, surf):
        ui.draw_panel(surf, MID_RECT, fill=(34, 42, 30), border=(118, 96, 54),
                      radius=14, border_width=2)
        ui.text(surf, self._font_cached(17, True), "配方预览",
                (MID_RECT.x + 16, MID_RECT.y + 12), ui.CREAM)
        recipe = self._selected_recipe()
        if recipe is None:
            ui.text(surf, self._font_cached(16), "还没有可用的融合配方",
                    MID_RECT.center, (200, 200, 180), anchor="center")
            return

        # 材料卡
        card_a = pygame.Rect(MID_RECT.x + 16, MID_RECT.y + 52, 188, 118)
        card_b = pygame.Rect(MID_RECT.x + 236, MID_RECT.y + 52, 188, 118)
        for card, plant_id, name in ((card_a, recipe.ingredients[0] if recipe.ingredients else "",
                                      recipe.ingredient_name(0)),
                                     (card_b, recipe.ingredients[1] if len(recipe.ingredients) > 1 else "",
                                      recipe.ingredient_name(1))):
            self._draw_plant_card(surf, card, plant_id, name)
        ui.text(surf, self._font_cached(26, True), "+",
                (MID_RECT.centerx, card_a.centery), ui.GOLD, anchor="center")

        # 箭头
        ui.text(surf, self._font_cached(14, True), "融 合",
                (MID_RECT.centerx, MID_RECT.y + 190), (224, 200, 140), anchor="center")
        pygame.draw.line(surf, (150, 126, 70),
                         (MID_RECT.centerx, MID_RECT.y + 202),
                         (MID_RECT.centerx, MID_RECT.y + 216), 2)

        # 产物卡
        res = pygame.Rect(MID_RECT.x + 16, MID_RECT.y + 222, MID_RECT.w - 32, 176)
        ui.draw_gradient(surf, res, (78, 62, 36), (50, 40, 26), radius=12)
        pygame.draw.rect(surf, ui.GOLD, res, 2, border_radius=12)
        art = self._plant_art(recipe, (104, 104))
        if art is not None:
            surf.blit(art, (res.x + 18, res.centery - art.get_height() // 2))
        tx = res.x + 138
        ui.text(surf, self._font_cached(21, True),
                ui.fit_text(self._font_cached(21, True), recipe.name_zh, res.w - 152),
                (tx, res.y + 14), ui.CREAM)
        ui.text(surf, self._font_cached(12),
                ui.fit_text(self._font_cached(12), recipe.name_en, res.w - 152),
                (tx, res.y + 44), (206, 200, 178))
        chips = [recipe.family or "未分类",
                 BEHAVIOR_ZH.get(recipe.behavior, recipe.behavior or "未知")]
        cx = tx
        for label in chips:
            rect = ui.draw_chip(surf, self.app, label, (cx, res.y + 66), size=12,
                                bg=(30, 26, 18), fg=ui.GOLD, pad_x=8, pad_y=3)
            cx = rect.right + 8
        stats = [
            f"花费 {recipe.result.get('cost', 0)}",
            f"冷却 {recipe.result.get('cooldown', 0)}s",
            f"生命 {recipe.result.get('hp', 0)}",
            f"编号 No.{recipe.almanac_no or '-'}",
        ]
        ui.text(surf, self._font_cached(12), " · ".join(stats),
                (tx, res.y + 96), (208, 204, 184))

        # 底部材料/解锁说明
        materials = " + ".join(recipe.ingredient_name(i)
                               for i in range(len(recipe.ingredients)))
        ui.text(surf, self._font_cached(13),
                ui.fit_text(self._font_cached(13), f"材料：{materials}", MID_RECT.w - 48),
                (MID_RECT.x + 18, MID_RECT.y + 418), (204, 210, 186))
        ui.draw_coin(surf, (MID_RECT.x + 22, MID_RECT.y + 450), 9)
        ui.text(surf, self._font_cached(13, True), f"解锁花费 {recipe.unlock_cost} 金币",
                (MID_RECT.x + 38, MID_RECT.y + 443), ui.GOLD)
        if recipe.plantfood_cost:
            ui.text(surf, self._font_cached(13),
                    f"另需养料 ×{recipe.plantfood_cost}",
                    (MID_RECT.x + 18, MID_RECT.y + 470), (186, 214, 168))
        ui.text(surf, self._font_cached(12),
                "重复产物可多次合成，获得不同式样",
                (MID_RECT.x + 18, MID_RECT.y + 494), (150, 158, 138))

    def _draw_plant_card(self, surf, rect, plant_id, name):
        ui.draw_panel(surf, rect, fill=(46, 58, 40), border=(96, 116, 76),
                      radius=10, border_width=2, shadow=False)
        art = None
        try:
            plant = (getattr(self.app.data, "plants", {}) or {}).get(plant_id)
            if plant is not None:
                key = str(getattr(plant, "art", "") or "")
                if key.endswith(".png"):
                    art = self.app.assets.static_sprite(key, 54)
                else:
                    art = self.app.assets.db_thumb(key, 54, 54)
        except Exception:
            art = None
        if art is not None:
            surf.blit(art, (rect.centerx - art.get_width() // 2, rect.y + 8))
        else:
            ui.text(surf, self._font_cached(22, True), str(name or "?")[:1],
                    (rect.centerx, rect.y + 34), (196, 210, 176), anchor="center")
        ui.text(surf, self._font_cached(13, True),
                ui.fit_text(self._font_cached(13, True), str(name or plant_id),
                            rect.w - 12),
                (rect.centerx, rect.bottom - 12), ui.CREAM, anchor="midbottom")

    # ------------------------------------------------------------ 右栏
    def _draw_details(self, surf):
        ui.draw_panel(surf, SIDE_RECT, fill=(38, 34, 24), border=(118, 96, 54),
                      radius=14, border_width=2)
        ui.text(surf, self._font_cached(17, True), "详情",
                (SIDE_RECT.x + 16, SIDE_RECT.y + 12), ui.CREAM)
        recipe = self._selected_recipe()
        if recipe is None:
            return
        x = SIDE_RECT.x + 20
        ui.text(surf, self._font_cached(23, True),
                ui.fit_text(self._font_cached(23, True), recipe.name_zh,
                            SIDE_RECT.w - 40),
                (x, SIDE_RECT.y + 44), ui.CREAM)
        ui.text(surf, self._font_cached(12),
                ui.fit_text(self._font_cached(12), recipe.name_en, SIDE_RECT.w - 40),
                (x, SIDE_RECT.y + 76), (200, 196, 176))

        rows = [
            ("金币花费", str(recipe.result.get("cost", 0))),
            ("冷却", f"{recipe.result.get('cooldown', 0)} 秒"),
            ("生命", str(recipe.result.get("hp", 0))),
            ("伤害", str(recipe.result.get("damage", 0))),
            ("攻击间隔", f"{recipe.result.get('interval', 0)} 秒"),
            ("家族 / 类型", f"{recipe.family or '-'} / "
                            f"{BEHAVIOR_ZH.get(recipe.behavior, recipe.behavior or '-')}"),
            ("图鉴编号", f"No.{recipe.almanac_no or '-'}"),
        ]
        top = SIDE_RECT.y + 104
        for i, (label, value) in enumerate(rows):
            yy = top + i * 24
            ui.text(surf, self._font_cached(13), label, (x, yy), (172, 170, 148))
            ui.text(surf, self._font_cached(13, True),
                    ui.fit_text(self._font_cached(13, True), value, 200),
                    (SIDE_RECT.right - 20, yy), (232, 226, 204), anchor="topright")

        desc_rect = pygame.Rect(x, SIDE_RECT.y + 286, SIDE_RECT.w - 40, 92)
        ui.draw_wrapped(surf, self._font_cached(12), recipe.desc_zh or "融合植物的详细资料。",
                        desc_rect, (204, 204, 184), line_height=17, max_lines=5)

        # 解锁状态
        unlocked = self.lab.is_unlocked(recipe)
        if unlocked:
            status = "已解锁 · 可在关卡牌组中使用"
            color = (150, 216, 132)
        else:
            ok, reason = self.lab.can_craft(recipe)
            status = "可以合成" if ok else (reason or "材料不足")
            color = (238, 200, 110) if ok else (206, 150, 120)
        ui.text(surf, self._font_cached(13, True), status,
                (SIDE_RECT.centerx, SIDE_RECT.y + 398), color, anchor="center")

        self.btn_craft.draw(surf)
        ui.text(surf, self._font_cached(12),
                f"已解锁 {self.lab.unlocked_count()} / {len(self.lab)}",
                (SIDE_RECT.centerx, SIDE_RECT.bottom - 16),
                (190, 186, 164), anchor="center")
