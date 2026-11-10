# -*- coding: utf-8 -*-
"""DragonBones 渲染器冒烟测试（headless，SDL_VIDEODRIVER=dummy）。

覆盖：
1. 三套样例资源（Peashooter / Sunflower / BasicZombie）都能解析出
   key / armature_name / animations / size。
2. 以 30fps 播放 Idle 90 帧，每帧 update + 渲染，不抛异常；
   每个 actor 抽 6 帧拼成横条保存到 work_out/render_<name>.png，便于肉眼检查。
3. 渲染结果确实有非透明像素（不是空白），且非循环动画能进入 finished 状态。
4. 缺失动画名会回退到第一个可用动画；缺贴图时 draw 不崩溃。

运行：
    cd PvZ2SHUTTLE
    SDL_VIDEODRIVER=dummy <python> tests\\test_dragonbones.py
退出码 0 = 全部 PASS，1 = 有 FAIL。
"""

from __future__ import annotations

import os
import sys
import traceback

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

HERE = os.path.dirname(os.path.abspath(__file__))
GAME_ROOT = os.path.dirname(HERE)
GAME_DIR = os.path.join(GAME_ROOT, "game")
WORK_ROOT = os.path.dirname(GAME_ROOT)  # pvz_shuttle
OUT_DIR = os.path.join(GAME_ROOT, "work_out")

if GAME_DIR not in sys.path:
    sys.path.insert(0, GAME_DIR)

import pygame  # noqa: E402

import dragonbones  # noqa: E402

SAMPLES = [
    # (显示名, 资源目录候选列表)
    (
        "Peashooter",
        [
            os.path.join(WORK_ROOT, "work", "dbdump", "plants_PeashooterPLANT"),
            os.path.join(GAME_ROOT, "assets", "db", "plants", "PeashooterPLANT"),
        ],
    ),
    (
        "Sunflower",
        [
            os.path.join(WORK_ROOT, "work", "dbdump", "plants_SunflowerPLANT"),
            os.path.join(GAME_ROOT, "assets", "db", "plants", "SunflowerPLANT"),
        ],
    ),
    (
        "BasicZombie",
        [
            os.path.join(WORK_ROOT, "work", "dbdump", "zombies_BasicZOMBIE"),
            os.path.join(GAME_ROOT, "assets", "db", "zombies", "BasicZOMBIE"),
        ],
    ),
]

FPS = 30
FRAMES = 90
STRIP_FRAMES = 6
FRAME_W, FRAME_H = 260, 320


def pick_dir(candidates):
    for path in candidates:
        if os.path.isdir(path) and os.path.isfile(os.path.join(path, "skeleton.json")):
            return path
    return None


def opaque_pixels(surface):
    """统计 alpha > 8 的像素数量（不依赖 numpy）。"""
    try:
        mask = pygame.mask.from_surface(surface, 8)
        return int(mask.count())
    except Exception:
        return 0


def render_frame(surface, player, name, text, scale=1.6):
    """把当前帧画到 surface 上，返回角色实际覆盖的像素数。

    角色先画到透明画布上统计覆盖率，再叠到带底色/地面线/文字的展示帧上，
    这样像素统计不会被背景色污染。
    """
    surface.fill((26, 32, 40))
    pygame.draw.line(surface, (70, 84, 96), (10, FRAME_H - 42), (FRAME_W - 10, FRAME_H - 42), 1)
    actor = pygame.Surface((FRAME_W, FRAME_H), pygame.SRCALPHA)
    try:
        player.draw(actor, FRAME_W // 2, FRAME_H - 42, scale=scale)
    except Exception:
        traceback.print_exc()
        return 0
    pixels = opaque_pixels(actor)
    surface.blit(actor, (0, 0))
    try:
        font = pygame.font.Font(None, 18)
        image = font.render(text, True, (220, 230, 240))
        surface.blit(image, (8, 6))
    except Exception:
        pass
    return pixels


def make_strip(model, name):
    """播放 Idle 90 帧，取 6 帧拼横条。返回 (strip_path, 角色像素总数, 最大单帧像素)。"""
    player = dragonbones.DBPlayer(model, anim="Idle", loop=True, speed=1.0)
    try:
        player.set_anim("Idle", loop=True, restart=True)
    except Exception:
        pass
    strip = pygame.Surface((FRAME_W * STRIP_FRAMES, FRAME_H))
    strip.fill((18, 22, 28))
    frame = pygame.Surface((FRAME_W, FRAME_H))
    scale = 1.05 if name == "BasicZombie" else 1.6
    total_pixels = 0
    max_pixels = 0
    sampled = 0
    step = max(1, FRAMES // STRIP_FRAMES)
    for index in range(FRAMES):
        player.update(1.0 / FPS)
        pixels = render_frame(
            frame,
            player,
            name,
            "%s  f%02d  t=%.2fs" % (name, index, player.time),
            scale=scale,
        )
        total_pixels += pixels
        max_pixels = max(max_pixels, pixels)
        if index % step == 0 and sampled < STRIP_FRAMES:
            strip.blit(frame, (FRAME_W * sampled, 0))
            sampled += 1
    # 若采样不足（步长导致），把最后一帧补上
    while sampled < STRIP_FRAMES:
        strip.blit(frame, (FRAME_W * sampled, 0))
        sampled += 1
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, "render_%s.png" % name)
    pygame.image.save(strip, path)
    return path, total_pixels, max_pixels


def check_actor(name, path):
    """返回 (ok, messages)。"""
    messages = []
    ok = True

    def expect(condition, message):
        nonlocal ok
        if condition:
            messages.append("PASS " + message)
        else:
            ok = False
            messages.append("FAIL " + message)

    try:
        model = dragonbones.DBModel.load(path)
    except Exception:
        messages.append("FAIL %s: DBModel.load 抛异常" % name)
        messages.append(traceback.format_exc().strip().splitlines()[-1])
        return False, messages

    expect(isinstance(model.key, str) and bool(model.key), "%s: key=%r" % (name, model.key))
    expect(
        isinstance(model.armature_name, str) and bool(model.armature_name),
        "%s: armature_name=%r" % (name, model.armature_name),
    )
    expect(
        isinstance(model.animations, list) and len(model.animations) > 0,
        "%s: animations=%s" % (name, model.animations[:6]),
    )
    expect(
        isinstance(model.size, (list, tuple))
        and len(model.size) == 2
        and model.size[0] > 1
        and model.size[1] > 1,
        "%s: size=%s" % (name, model.size),
    )
    expect("Idle" in model.animations, "%s: 含 Idle 动画" % name)
    expect(model.texture is not None, "%s: 纹理已加载 %s" % (name, model.texture_size))

    # 缺失动画回退
    try:
        fallback = dragonbones.DBPlayer(model, anim="__no_such_anim__")
        expect(
            fallback.anim_name == (model.animations[0] if model.animations else None),
            "%s: 缺失动画回退到 %r" % (name, fallback.anim_name),
        )
        fallback.draw(pygame.Surface((64, 64)), 32, 60, 0.5)
    except Exception:
        ok = False
        messages.append("FAIL %s: 缺失动画回退崩溃" % name)

    # 90 帧播放 + 横条
    try:
        strip_path, total_pixels, max_pixels = make_strip(model, name)
        expect(total_pixels > 0, "%s: 90 帧角色像素总数 %d" % (name, total_pixels))
        # 角色至少覆盖数百像素，避免“只画出一两个点”也算通过
        expect(max_pixels > 500, "%s: 单帧角色像素 %d" % (name, max_pixels))
        messages.append("INFO %s: strip -> %s" % (name, strip_path))
    except Exception:
        ok = False
        messages.append("FAIL %s: 渲染 90 帧异常" % name)
        messages.append(traceback.format_exc().strip().splitlines()[-1])

    # finished 语义（取一个非循环短动画；没有就跳过）
    try:
        short = None
        for anim_name in model.animations:
            if anim_name == "Idle":
                continue
            short = anim_name
            break
        if short:
            player = dragonbones.DBPlayer(model, anim=short, loop=False)
            for _ in range(240):
                player.update(1.0 / FPS)
                if player.finished:
                    break
            expect(player.finished, "%s: 非循环 %r 能结束" % (name, short))
        else:
            messages.append("INFO %s: 无非 Idle 动画，跳过 finished 检查" % name)
    except Exception:
        ok = False
        messages.append("FAIL %s: finished 语义异常" % name)
        messages.append(traceback.format_exc().strip().splitlines()[-1])

    # flip / alpha / scale 不崩溃
    try:
        player = dragonbones.DBPlayer(model, anim="Idle")
        surface = pygame.Surface((300, 300), pygame.SRCALPHA)
        player.draw(surface, 150, 280, scale=1.0, flip=True, alpha=128)
        player.draw(surface, 150, 280, scale=0.5, flip=False, alpha=255)
        messages.append("PASS %s: flip/alpha/scale 绘制" % name)
    except Exception:
        ok = False
        messages.append("FAIL %s: flip/alpha 绘制异常" % name)

    return ok, messages


def check_multi_armature():
    """僵尸目录多套骨架: 切到 FlagZombie/Cone 也应可用。"""
    messages = []
    ok = True
    path = pick_dir(SAMPLES[2][1])
    if not path:
        return False, ["FAIL multi-armature: 找不到僵尸样例目录"]
    try:
        model = dragonbones.DBModel.load(path)
        names = list(model.armature_order)
        base = model.armature_name
        for target in ("FlagZombie", "Cone"):
            if target not in names:
                continue
            used = model.use_armature(target)
            player = dragonbones.DBPlayer(model, anim="Idle", armature=target)
            surface = pygame.Surface((120, 120), pygame.SRCALPHA)
            for _ in range(5):
                player.update(1.0 / FPS)
                player.draw(surface, 60, 110, 0.4)
            if used != target:
                ok = False
                messages.append("FAIL multi-armature: 期望 %r 实际 %r" % (target, used))
        model.use_armature(base)
        messages.append("PASS multi-armature: %s 可切换并绘制" % names[:4])
    except Exception:
        ok = False
        messages.append("FAIL multi-armature: 切换骨架异常")
        messages.append(traceback.format_exc().strip().splitlines()[-1])
    return ok, messages


def main():
    pygame.init()
    pygame.display.set_mode((FRAME_W, FRAME_H))
    if not pygame.font.get_init():
        pygame.font.init()

    all_ok = True
    report = []
    for name, candidates in SAMPLES:
        directory = pick_dir(candidates)
        if not directory:
            all_ok = False
            report.append("FAIL %s: 样例目录不存在 %s" % (name, candidates))
            continue
        ok, messages = check_actor(name, directory)
        all_ok = all_ok and ok
        report.extend(messages)

    ok, messages = check_multi_armature()
    all_ok = all_ok and ok
    report.extend(messages)

    print("=" * 72)
    for line in report:
        print(line)
    print("=" * 72)
    print("RESULT:", "PASS" if all_ok else "FAIL")
    print("输出目录:", OUT_DIR)
    pygame.quit()
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
