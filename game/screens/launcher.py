"""SHUTTLE 启动器界面（中心界面，尽量还原官方启动器）。

布局（1280x720）：
- 背景：assets/ui/bg_home.jpg，cover 铺满后轻压暗
- 居中白色面板 1000x600，顶部 #454c5c 标题栏「通知中心」
- 左侧 130px 标签栏：通知内容 / 最新版本热点
- 右侧：版本提示、可滚动新闻列表、版本信息行
- 面板底部：功能设定（高视角 / 高画质 / 游戏速度）、前往更新、开始游戏
"""
from __future__ import annotations

import pygame

from ..config import BUILD_URL, SITE, VERSION
from .base import Screen
from . import widgets as ui

WHITE_WARM = (253, 250, 245)
TAB_BG = (235, 231, 222)
NEWS_BG = (255, 252, 247)

# 滚动区中的新闻条目（参考官方 26.x 更新内容）
LATEST_NEWS = [
    {
        "kicker": "复刻版 · 2026-11-10 · 完整扩充",
        "title": "26 世界 · 1809 关 · 植物融合 · Boss 三阶段",
        "body": "全部 1809 个普通关与 26 个世界开放；新增植物融合实验室（85 配方、147 植物）、"
                "26 个僵尸博士（三阶段 66%/33%）、商店 2.0（585 件商品）、禅境花园 2.0（四阶段/浇水/收获）、"
                "6×10 动态战场与矿车，以及 26 世界轮播地图。",
    },
    {
        "kicker": "复刻版 · 2026-11-10",
        "title": "P0：18 世界 · 615 关 · 世界轮播与钥匙解锁",
        "body": "世界扩充到 18 个（含冰河、功夫、恐龙、摇滚、摩登、天空之城），"
                "关卡总数 615；世界轮播界面支持左右切换、世界详情 5 列关卡网格与分页；"
                "每 10 颗星获得 1 把钥匙，可解锁顺序链上的下一个世界。",
    },
    {
        "kicker": "复刻版 · 2026-11-10 · 更多玩法",
        "title": "特殊模式、王朝世界与完整图鉴",
        "body": "新增「更多玩法」入口：砸罐子 45 关、生存无尽、僵尸博士、商店与"
                "禅境花园；12 个世界 120 关、62 植物 55 僵尸、360 枚星章；"
                "新世界「王朝」含白天/夜晚关卡与专属 Boss。",
    },
    {
        "kicker": "复刻版 · 2026-11-09 · 新世界",
        "title": "中国园林 / 洛城风云 / 月虹市场开放",
        "body": "三个全新世界各 10 关：栀子花、茉莉、鱼雷果、接骨木屏障等 11 种"
                "新植物，园林/帮派/发条/飞人等 24 种新僵尸，并配有专属原声。"
                "图鉴扩充至 62 植物 / 55 僵尸，世界地图新增 3 个节点。",
    },
    {
        "kicker": f"{VERSION} · 2026-10-01 · 最新",
        "title": "元素？很奇妙吧！全新任务开放",
        "body": "20 个全新关卡，体验「元素反应」机制：蒸发、融化、冻结、感电、"
                "超导、超载、扩散。完成关卡可领取原始豌豆射手装扮、天使星星果装扮"
                "与暗物质火龙果。",
    },
    {
        "kicker": f"{VERSION} · 2026-10-01 · 新植物",
        "title": "暗物质火龙果登场",
        "body": "来自虚空的全新植物，以暗物质能量攻击整行僵尸，并有一定概率触发"
                "元素反应。收集阳光，种下它，感受湮灭的力量。",
    },
    {
        "kicker": f"{VERSION} · 2026-10-01 · 新僵尸",
        "title": "四位植物僵尸加入战场",
        "body": "冰西瓜投手僵尸、闪电芦苇僵尸、气流水仙花僵尸、莲藕射手僵尸将"
                "带着植物们的力量向你的草坪发起进攻，请提前布置防线。",
    },
    {
        "kicker": "26.9.1 · 2026-09-01 · 新世界",
        "title": "全新世界「海底世界」",
        "body": "16 关普通关卡，6 行 10 列战场。氧气、潜艇、洋流与深海鱼等全新"
                "机制登场。新植物：灯萤果、祥云飞莲、迷你双重射手、氧气海藻。",
    },
    {
        "kicker": "26.6.14 · 2026-06-14 · 版本更新",
        "title": "平衡性调整与体验优化",
        "body": "调整了部分植物的阳光消耗与冷却时间，优化关卡加载速度，修复若干"
                "已知问题。感谢各位园丁的反馈。",
    },
    {
        "kicker": "26.5.1 · 2026-05-01 · 活动",
        "title": "五一登录活动",
        "body": "活动期间登录游戏可领取钻石、金币与限定装扮。祝各位园丁劳动节快乐。",
    },
]

HOT_NEWS = [
    {
        "kicker": "热点 · 元素反应",
        "title": "元素反应速览",
        "body": "水 + 火 = 蒸发；冰 + 火 = 融化；冰 + 水 = 冻结；雷 + 水 = 感电；"
                "雷 + 冰 = 超导；雷 + 火 = 超载；风 + 元素 = 扩散。",
    },
    {
        "kicker": "热点 · 新世界",
        "title": "新世界解锁顺序",
        "body": "前院 → 神秘埃及 → 海盗港湾 → 狂野西部 → 未来世界 → 黑暗时代 → "
                "神秘海滩 → 失落之城 → 中国园林 → 洛城风云 → 月虹市场。",
    },
    {
        "kicker": "热点 · 海底世界",
        "title": "氧气机制小贴士",
        "body": "海底关卡中植物会持续消耗氧气，请在草坪上保留足够的氧气海藻，"
                "并及时清理潜艇僵尸。",
    },
    {
        "kicker": "热点 · 启动器",
        "title": "启动器设置说明",
        "body": "「高视角」会缩小战场单位并显示更多行；「高画质」启用更精细的"
                "粒子与阴影效果；游戏速度默认为 1.0x，可在 1.0x / 1.5x / 2.0x 间切换。",
    },
]


class LauncherScreen(Screen):
    name = "launcher"

    def __init__(self, app):
        super().__init__(app)
        self.W, self.H = app.screen.get_size()
        self.panel = pygame.Rect(0, 0, 1000, 600)
        self.panel.center = (self.W // 2, self.H // 2)

        self.bg = None
        self._fonts = {}
        self._news_cache = {}
        self._news_rows = []

        self.active_tab = 0
        self.tab_hover = -1
        self.scroll = ui.ScrollPanel(app, pygame.Rect(0, 0, 10, 10), step=46)
        self.popup = None
        self._layout()

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------
    def enter(self):
        super().enter()
        try:
            self.app.audio.play_menu()
        except Exception:
            pass
        self.bg = ui.load_cover(self.app, "ui/bg_home.jpg", (self.W, self.H))
        settings = getattr(self.app.save, "settings", {}) or {}
        self.high_view = bool(settings.get("high_view", False))
        self.high_quality = bool(settings.get("high_quality", True))
        try:
            speed = float(settings.get("speed", 1.0))
        except (TypeError, ValueError):
            speed = 1.0
        self.speed = speed if speed in (1.0, 1.5, 2.0) else 1.0

        self.checkbox_view = ui.Checkbox(
            self.app, (self.fx, self.fy + 52), "高视角", self.high_view,
            on_change=lambda v: self._store("high_view", v), box=22, font_size=17)
        self.checkbox_quality = ui.Checkbox(
            self.app, (self.fx + 118, self.fy + 52), "高画质", self.high_quality,
            on_change=lambda v: self._store("high_quality", v), box=22, font_size=17)
        self.speed_group = ui.ToggleGroup(
            self.app, (self.fx + 64, self.fy + 84, 210, 36),
            ("1.0x", "1.5x", "2.0x"), (1.0, 1.5, 2.0).index(self.speed),
            on_change=self._on_speed, font_size=14, style="segmented")
        self.btn_update = ui.Button(
            self.app, (self.content_right - 232 - 20 - 150, self.fy + 96, 150, 42),
            "前往更新", on_click=self._on_update, style="cream", font_size=16)
        self.btn_start = ui.Button(
            self.app, (self.content_right - 232, self.fy + 82, 232, 68),
            "开始游戏", on_click=self._start_game, style="start", font_size=27)
        self.refresh_icon = ui.scale_image(
            ui.get_image(self.app, "ui/icon_refresh.png"), (18, 18))
        self.btn_refresh = ui.IconButton(
            self.app, (self.header.right - 40, self.header.y + 7, 30, 30),
            self.refresh_icon, on_click=self._on_update, radius=8,
            hover_bg=(255, 255, 255, 46), padding=5)

        self._news_cache = {}
        self._select_tab(self.active_tab, reset_scroll=True)

    def exit(self):
        self.popup = None

    # ------------------------------------------------------------------
    # 布局
    # ------------------------------------------------------------------
    def _layout(self):
        p = self.panel
        self.header = pygame.Rect(p.x + 10, p.y + 10, p.w - 20, 44)
        self.body_top = self.header.bottom
        self.footer_top = p.y + p.h - 224
        self.tabs = pygame.Rect(p.x + 10, self.body_top, 130,
                                self.footer_top - self.body_top)
        self.content_left = p.x + 152
        self.content_right = p.right - 18
        self.news_panel = pygame.Rect(self.content_left, self.body_top + 30,
                                      self.content_right - self.content_left, 250)
        self.news_view = self.news_panel.inflate(-16, -16)
        self.tip_pos = (self.content_left, self.body_top + 14)
        self.below_news_y = self.news_panel.bottom + 14
        self.fx = p.x + 26
        self.fy = self.footer_top
        self.scroll.rect = pygame.Rect(self.news_view.x, self.news_view.y,
                                       self.news_view.w - 10, self.news_view.h)

    def _font(self, size, bold=False):
        key = (size, bold)
        if key not in self._fonts:
            self._fonts[key] = self.app.font(size, bold)
        return self._fonts[key]

    # ------------------------------------------------------------------
    # 设置
    # ------------------------------------------------------------------
    def _store(self, key, value):
        try:
            self.app.save.settings[key] = value
            self.app.save.save()
        except Exception:
            pass

    def _on_speed(self, index):
        self.speed = (1.0, 1.5, 2.0)[index]
        self._store("speed", self.speed)

    def _start_game(self):
        self.app.switch("menu")

    def _on_update(self):
        self.popup = ui.MessagePopup(
            self.app, "检查更新",
            f"当前版本 {VERSION} 已是最新版本。\n无需更新，祝你游戏愉快。",
            button_text="确定", on_close=self._close_popup)
        self.popup.rect.center = (self.W // 2, self.H // 2)
        self.popup.button.rect.centerx = self.popup.rect.centerx

    def _close_popup(self):
        self.popup = None

    # ------------------------------------------------------------------
    # 标签页 / 新闻
    # ------------------------------------------------------------------
    def _tab_rect(self, index):
        return pygame.Rect(self.tabs.x + 4, self.tabs.y + 6 + index * 48,
                           self.tabs.w - 8, 44)

    def _select_tab(self, index, reset_scroll=False):
        self.active_tab = index
        self._rebuild_news()
        if reset_scroll:
            self.scroll.reset()

    def _items(self):
        return LATEST_NEWS if self.active_tab == 0 else HOT_NEWS

    def _rebuild_news(self):
        key = self.active_tab
        if key not in self._news_cache:
            font_body = self._font(13, False)
            width = self.scroll.rect.w - 26
            rows = []
            y = 8
            for item in self._items():
                lines = ui.wrap_text(font_body, item["body"], width)[:6]
                h = 16 + 24 + len(lines) * 19 + 16
                rows.append((item, h, lines, y))
                y += h + 8
            self._news_cache[key] = (rows, y + 4)
        self._news_rows, content_h = self._news_cache[key]
        self.scroll.set_content_height(content_h)

    # ------------------------------------------------------------------
    # 事件
    # ------------------------------------------------------------------
    def handle(self, event):
        super().handle(event)
        if self.popup is not None:
            self.popup.handle(event)
            return

        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self._start_game()
                return
            if event.key == pygame.K_r:
                self._on_update()
                return

        if self.btn_start.handle(event):
            return
        if self.btn_update.handle(event):
            return
        if self.btn_refresh.handle(event):
            return
        if self.checkbox_view.handle(event):
            return
        if self.checkbox_quality.handle(event):
            return
        if self.speed_group.handle(event):
            return

        if event.type == pygame.MOUSEMOTION:
            self.tab_hover = -1
            for i in range(2):
                if self._tab_rect(i).collidepoint(event.pos):
                    self.tab_hover = i
                    break
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for i in range(2):
                if self._tab_rect(i).collidepoint(event.pos):
                    if i != self.active_tab:
                        self._select_tab(i, reset_scroll=True)
                    return

        if event.type == pygame.MOUSEWHEEL:
            if self.news_panel.collidepoint(self.mouse):
                self.scroll.scroll_by(-event.y * 46)
            return
        if self.scroll.handle(event):
            return

    def update(self, dt):
        super().update(dt)
        if self.popup is not None:
            self.popup.update(dt)

    # ------------------------------------------------------------------
    # 绘制
    # ------------------------------------------------------------------
    def draw(self, surf):
        self._draw_background(surf)
        self._draw_panel(surf)
        self._draw_header(surf)
        self._draw_tabs(surf)
        self._draw_content(surf)
        self._draw_footer(surf)
        if self.popup is not None:
            self.popup.draw(surf)
        self.draw_fade(surf)

    def _draw_background(self, surf):
        if self.bg is not None:
            surf.blit(self.bg, (0, 0))
        else:
            ui.draw_gradient(surf, surf.get_rect(), (112, 166, 206), (200, 218, 174))
        ui.draw_dim(surf, alpha=26, color=(12, 14, 10))

    def _draw_panel(self, surf):
        ui.draw_shadow(surf, self.panel, radius=10, alpha=120, offset=(0, 10), spread=12)
        pygame.draw.rect(surf, WHITE_WARM, self.panel, border_radius=9)
        pygame.draw.rect(surf, (214, 202, 184), self.panel, 1, border_radius=9)
        # 顶部一条极淡的高光
        ui.alpha_rect(surf, (self.panel.x + 8, self.panel.y + 1,
                             self.panel.w - 16, 2), (255, 255, 255, 180), radius=1)

    def _draw_header(self, surf):
        h = self.header
        pygame.draw.rect(surf, ui.HEADER_BLUE, h,
                         border_top_left_radius=6, border_top_right_radius=6)
        icon = ui.get_image(self.app, "ui/icon_news.png")
        if icon is not None:
            icon = ui.scale_image(icon, (22, 22))
            surf.blit(icon, (h.x + 16, h.centery - 11))
        ui.text(surf, self._font(20, True), "通知中心",
                (h.x + 48, h.centery), (255, 248, 204), anchor="midleft")
        ui.text(surf, self._font(11, False), "SHUTTLE LAUNCHER",
                (h.x + 48 + self._font(20, True).size("通知中心")[0] + 14, h.centery + 1),
                (176, 184, 200), anchor="midleft")
        self.btn_refresh.draw(surf)

    def _draw_tabs(self, surf):
        pygame.draw.rect(surf, TAB_BG, self.tabs)
        pygame.draw.line(surf, (219, 211, 197), (self.tabs.right - 1, self.tabs.y),
                         (self.tabs.right - 1, self.tabs.bottom), 1)
        icon_sel = ui.get_image(self.app, "ui/icon_select.png")
        icon_news = ui.get_image(self.app, "ui/icon_news.png")
        for i, label in enumerate(("通知内容", "最新版本热点")):
            r = self._tab_rect(i)
            selected = i == self.active_tab
            if selected:
                pygame.draw.rect(surf, WHITE_WARM, r, border_radius=6)
                pygame.draw.rect(surf, (225, 216, 200), r, 1, border_radius=6)
                pygame.draw.rect(surf, ui.GOLD_DARK, (r.x, r.y + 10, 3, r.h - 20),
                                 border_radius=2)
            elif i == self.tab_hover:
                ui.alpha_rect(surf, r, (255, 255, 255, 70), radius=6)
            icon = icon_sel if selected else icon_news
            if icon is not None:
                img = ui.scale_image(icon, (18, 18))
                surf.blit(img, (r.x + 12, r.centery - 9))
            font = self._font(15, selected)
            ui.text(surf, font, label, (r.x + 38, r.centery),
                    ui.BROWN if selected else ui.INK_SOFT, anchor="midleft")

    def _draw_content(self, surf):
        # 提示行
        pygame.draw.circle(surf, ui.GOLD_DARK, (self.tip_pos[0] + 4, self.tip_pos[1] - 3), 3)
        ui.text(surf, self._font(12, False),
                f"当前版本 {VERSION} / 最新版本 {VERSION}",
                (self.tip_pos[0] + 14, self.tip_pos[1]), ui.INK_FAINT, anchor="midleft")

        # 新闻卡片
        ui.draw_panel(surf, self.news_panel, NEWS_BG, (229, 220, 206),
                      radius=7, border_width=1, shadow=False)
        # 卡片顶部细金线
        ui.alpha_rect(surf, (self.news_panel.x + 8, self.news_panel.y + 1,
                             self.news_panel.w - 16, 2), (247, 201, 72, 90), radius=1)

        old_clip = surf.get_clip()
        surf.set_clip(self.news_view)
        rows, _ = self._news_rows, self.scroll.content_h
        view_x = self.news_view.x + 8
        avail_w = self.scroll.rect.w - 26
        for idx, (item, h, lines, top) in enumerate(rows):
            y = self.scroll.rect.y + top - int(self.scroll.offset)
            if y > self.news_view.bottom + 20:
                continue
            if y + h < self.news_view.y - 20:
                continue
            highlight = (self.active_tab == 0 and idx == 0)
            if highlight:
                badge = pygame.Rect(view_x - 6, y - 2, avail_w + 18, h + 2)
                ui.alpha_rect(surf, badge, (252, 243, 219, 210), radius=6)
            # 版本 / 日期
            ui.text(surf, self._font(11, True), item["kicker"], (view_x, y),
                    ui.GOLD_DARK if highlight else ui.INK_FAINT, anchor="topleft")
            # 标题
            ui.text(surf, self._font(16, True), item["title"], (view_x, y + 16),
                    ui.BROWN_DARK, anchor="topleft")
            # 正文
            by = y + 42
            for line in lines:
                ui.text(surf, self._font(13, False), line, (view_x, by),
                        ui.INK_SOFT, anchor="topleft")
                by += 19
            # 分割线
            if idx < len(rows) - 1:
                pygame.draw.line(surf, (234, 227, 214),
                                 (view_x, y + h - 8), (view_x + avail_w, y + h - 8), 1)
        surf.set_clip(old_clip)
        self.scroll.draw_scrollbar(surf)

        # 内容区底部版本信息
        ui.text(surf, self._font(11, False), f"当前版本  {VERSION}",
                (self.content_left, self.below_news_y), ui.INK_FAINT, anchor="topleft")
        ui.text(surf, self._font(11, False), f"最新版本  {VERSION}",
                (self.content_right, self.below_news_y), ui.INK_FAINT, anchor="topright")

    def _draw_footer(self, surf):
        p = self.panel
        pygame.draw.line(surf, (228, 219, 204), (p.x + 16, self.footer_top),
                         (p.right - 16, self.footer_top), 1)

        gear = ui.get_image(self.app, "ui/ic_settings.png")
        if gear is not None:
            gear = ui.scale_image(gear, (20, 20))
            surf.blit(gear, (self.fx, self.fy + 12))
        ui.text(surf, self._font(16, True), "功能设定",
                (self.fx + 28, self.fy + 22), ui.BROWN, anchor="midleft")
        ui.text(surf, self._font(11, False), "设置会自动保存",
                (self.fx + 28 + self._font(16, True).size("功能设定")[0] + 12,
                 self.fy + 23), ui.INK_FAINT, anchor="midleft")

        self.checkbox_view.draw(surf)
        self.checkbox_quality.draw(surf)

        ui.text(surf, self._font(13, False), "游戏速度",
                (self.fx, self.fy + 102), ui.INK_SOFT, anchor="midleft")
        self.speed_group.draw(surf)
        ui.text(surf, self._font(11, False),
                "高视角会扩大视野，高画质会启用更精细的特效。",
                (self.fx, self.fy + 140), ui.INK_FAINT, anchor="midleft")

        self.btn_update.draw(surf)
        self.btn_start.draw(surf)

        ui.text(surf, self._font(10, False),
                f"{VERSION}  {BUILD_URL}  {SITE}",
                (self.content_right, self.fy + 190), ui.INK_FAINT, anchor="bottomright")
        ui.text(surf, self._font(10, False), "PvZ 2 SHUTTLE · 粉丝复刻版",
                (self.fx, self.fy + 192), ui.INK_FAINT, anchor="bottomleft")
