# -*- coding: utf-8 -*-
"""DragonBones 5.5 (Cocos Creator 3.8.4 导出) 解析与 pygame 渲染。

对应设计契约见 game/DESIGN.md 的「DragonBones 渲染契约」一节：
    DBModel.load(dir_path) -> DBModel       # 一次解析, 可被多个 DBPlayer 共享
    DBPlayer(model, anim="Idle", ...)       # 播放状态 + 每帧绘制
    DBPlayer.draw(surf, x, y, scale, flip, alpha)
    (x, y) 是角色脚底中心（armature aabb 的底边中点）。

数据目录（每套角色）:
    <dir>/skeleton.json   DragonBones 5.5: armature[].bone/slot/skin/animation
    <dir>/atlas.json      图集, SubTexture[] 可带 frameX/frameY/frameWidth/frameHeight 裁剪
    <dir>/texture.png     RGBA 图集（已解码的原图）
    <dir>/meta.json       Cocos 预制体附加信息（可选）

实现要点 / 坐标约定（都按 DragonBones runtime 5.x 的真实语义，已对照
dragonBones-core.js 验证）:

1. 样例数据是 **Y 轴向下**（和 pygame 屏幕一致），不是文档里常说的 Y-up。
   证据：僵尸脚骨 y≈-24，髋骨 y≈-97，髋必须在脚上方 => +y 向下；
   Peashooter aabb 的 y=-122.76 是头顶、y+height=17.97 是脚底。
   因此屏幕映射不需要翻 Y：screen = origin + scale * (db_x - anchor_x, db_y - anchor_y)。

2. 骨骼变换组合: world = parent_world ∘ local（列向量约定，等价于
   runtime 里 globalTransformMatrix.concat(parentMatrix)）。
   local 矩阵来自 Transform.toMatrix():
       a = cos(rot)*scX, b = sin(rot)*scX, c = -sin(skew+rot)*scY, d = cos(skew+rot)*scY
   其中 skeleton 的 skX/skY 是**角度**，rotation = skY, skew = skX - skY。

3. 动画关键帧的数值是**相对绑定姿势的增量**（DragonBones 5.x additive）:
       bone.x = rest.x + anim.x;  rotation = rest.rotation + anim.rotation;
       scaleX = rest.scaleX * anim.scaleX;  ...
   （runtime: global = origin + animationPose，animationPose.scaleX 默认 1）

4. slot 显示变换: skin display 的 transform 是相对骨骼的局部矩阵，贴图偏移由
   pivot + 裁剪信息决定（默认 pivot=(0.5,0.5)）:
       pivot_x = pivot.u * frameWidth  + frameX   （未裁剪时为 image 宽）
       pivot_y = pivot.v * frameHeight + frameY
       贴图左上角在显示坐标系中的位置 = (-pivot_x, -pivot_y)
   即 world_point = bone_world ∘ display_local ∘ (texel - pivot)。

5. tween: 缺省（没有 tweenEasing 也没有 curve）是**阶跃保持**（step），
   tweenEasing==0 线性，<0 QuadIn，>0 QuadOut，curve 为 4 控制点贝塞尔缓动。
   slot 的 displayFrame/colorFrame 是阶跃时间轴。

6. 只做静态四边形（无 mesh 变形/IK 约束），逐 slot 用
   缩放 + 旋转 + blit 近似仿射变换；单个 slot 出错只跳过该 slot，绝不让整帧崩溃。

依赖: 标准库 + pygame（Pillow 只作为 texture.png 解码失败时的兜底）。
"""

from __future__ import annotations

import json
import math
import os

try:  # 游戏运行环境一定有 pygame；单测里也一定先 import pygame
    import pygame
except Exception:  # pragma: no cover - 仅用于静态检查/文档生成
    pygame = None  # type: ignore

DEG = math.pi / 180.0
_IDENTITY = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0)


# ============================================================================
# 小工具
# ============================================================================
def _f(value, default=0.0):
    """尽量转 float；None/非法值/NaN 返回 default。"""
    try:
        if value is None:
            return default
        result = float(value)
        if result != result:  # NaN
            return default
        return result
    except (TypeError, ValueError):
        return default


def _read_json(path):
    """读取 JSON 文件；失败返回 None（调用方决定是否致命）。"""
    try:
        with open(path, "r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


# ============================================================================
# 2D 仿射矩阵 (a, b, c, d, e, f)
#     x' = a*x + c*y + e
#     y' = b*x + d*y + f
# 与 DragonBones Matrix 的字段/语义一致。
# ============================================================================
def _mat_mul(m1, m2):
    """返回 m1 ∘ m2（先应用 m2，再应用 m1）。"""
    a1, b1, c1, d1, e1, f1 = m1
    a2, b2, c2, d2, e2, f2 = m2
    return (
        a1 * a2 + c1 * b2,
        b1 * a2 + d1 * b2,
        a1 * c2 + c1 * d2,
        b1 * c2 + d1 * d2,
        a1 * e2 + c1 * f2 + e1,
        b1 * e2 + d1 * f2 + f1,
    )


def _mat_apply(m, x, y):
    a, b, c, d, e, f = m
    return (a * x + c * y + e, b * x + d * y + f)


def _mat_trs(x, y, rotation, skew, scale_x, scale_y):
    """Transform.toMatrix() 的等价实现（rotation/skew 单位为弧度）。"""
    cos_r = math.cos(rotation)
    sin_r = math.sin(rotation)
    cos_s = math.cos(skew + rotation)
    sin_s = math.sin(skew + rotation)
    return (
        cos_r * scale_x,
        sin_r * scale_x,
        -sin_s * scale_y,
        cos_s * scale_y,
        x,
        y,
    )


def _mat_translate(x, y):
    return (1.0, 0.0, 0.0, 1.0, x, y)


def _mat_conj(m):
    """返回 F·m·F，F = diag(1, -1)。

    DragonBones 运行时把数据里的 y 向下翻成 y 向上（Cocos 等引擎），
    运行时用的局部矩阵正是 F·M·F。绘制时再翻回 y 向下即可。
    """
    a, b, c, d, e, f = m
    return (a, -b, -c, d, e, -f)


def _mat_det(m):
    return m[0] * m[3] - m[1] * m[2]


def _atan_div(y, x):
    """与 JS Math.atan(y / x) 等价（含 x == 0 的极限情况）。"""
    if x == 0.0:
        if y > 0.0:
            return math.pi * 0.5
        if y < 0.0:
            return -math.pi * 0.5
        return 0.0
    return math.atan(y / x)


class _Global(object):
    """从世界矩阵反解出来的全局变换（对应 DragonBones Transform.fromMatrix）。"""

    __slots__ = ("x", "y", "rotation", "skew", "scale_x", "scale_y")

    def __init__(self, x, y, rotation, skew, scale_x, scale_y):
        self.x = x
        self.y = y
        self.rotation = rotation
        self.skew = skew
        self.scale_x = scale_x
        self.scale_y = scale_y


def _decompose(m, backup_scale_x=1.0, backup_scale_y=1.0):
    """Transform.fromMatrix() 的等价实现。

    注意 DragonBones 用的是 Math.atan(b/a) 而非 atan2，并用 backup scale
    的符号决定是否把负缩放进 rotation/skew 里，这里保持一致。
    """
    a, b, c, d, tx, ty = m
    half_pi = math.pi * 0.5
    rotation = _atan_div(b, a)
    skew_x = _atan_div(-c, d)
    if -half_pi < rotation < half_pi:
        cos_r = math.cos(rotation)
        scale_x = a / cos_r if abs(cos_r) > 1e-9 else 1.0
    else:
        sin_r = math.sin(rotation)
        scale_x = b / sin_r if abs(sin_r) > 1e-9 else 1.0
    if -half_pi < skew_x < half_pi:
        cos_s = math.cos(skew_x)
        scale_y = d / cos_s if abs(cos_s) > 1e-9 else 1.0
    else:
        sin_s = math.sin(skew_x)
        scale_y = -c / sin_s if abs(sin_s) > 1e-9 else 1.0
    if backup_scale_x >= 0.0 and scale_x < 0.0:
        scale_x = -scale_x
        rotation -= math.pi
    if backup_scale_y >= 0.0 and scale_y < 0.0:
        scale_y = -scale_y
        skew_x -= math.pi
    return _Global(tx, ty, rotation, skew_x - rotation, scale_x, scale_y)


# ============================================================================
# Transform（骨骼绑定姿势 / 显示变换）
# ============================================================================
class _Transform(object):
    """DragonBones Transform：位置、旋转、斜切、缩放。角度统一转成弧度。"""

    __slots__ = ("x", "y", "rotation", "skew", "scale_x", "scale_y")

    def __init__(self, raw=None, scale=1.0):
        raw = raw if isinstance(raw, dict) else {}
        self.x = _f(raw.get("x")) * scale
        self.y = _f(raw.get("y")) * scale
        # DragonBones 导出同时给 skX/skY（角度）；老格式可能给 rotate/skew。
        if "skX" in raw or "skY" in raw:
            skew_x = _f(raw.get("skX")) * DEG
            skew_y = _f(raw.get("skY")) * DEG
            self.rotation = skew_y
            self.skew = skew_x - skew_y
        else:
            self.rotation = _f(raw.get("rotate")) * DEG
            self.skew = _f(raw.get("skew")) * DEG
        self.scale_x = _f(raw.get("scX"), 1.0)
        self.scale_y = _f(raw.get("scY"), 1.0)

    def matrix(self):
        return _mat_trs(
            self.x, self.y, self.rotation, self.skew, self.scale_x, self.scale_y
        )

    def __repr__(self):  # pragma: no cover - 调试用
        return "_Transform(x=%.3f, y=%.3f, rot=%.1fdeg, skew=%.1fdeg, sc=(%.3f,%.3f))" % (
            self.x,
            self.y,
            self.rotation / DEG,
            self.skew / DEG,
            self.scale_x,
            self.scale_y,
        )


# ============================================================================
# 缓动
# ============================================================================
def _parse_ease(raw):
    """把一帧的缓动信息解析成采样器可用的描述。

    返回 None 表示阶跃（DragonBones TweenType.None = 保持当前帧值）。
    曲线的 control points 在解析阶段就预采样成查找表，避免每帧反复迭代求解。
    """
    curve = raw.get("curve")
    if isinstance(curve, (list, tuple)) and len(curve) >= 4:
        return ("curve", _make_curve_lut(_f(curve[0]), _f(curve[1]), _f(curve[2]), _f(curve[3])))
    if "tweenEasing" in raw and raw.get("tweenEasing") is not None:
        easing = _f(raw.get("tweenEasing"), -2.0)
        if easing == -2.0:  # noTween 哨兵，与 runtime 一致
            return None
        if abs(easing) < 1e-6:
            return ("line",)
        if easing < 0.0:
            return ("quadin", -easing)
        return ("quadout", easing)
    return None


def _make_curve_lut(x1, y1, x2, y2, samples=64):
    """把三次贝塞尔缓动曲线预采样成 [(x, y), ...] 查找表（u 均匀采样）。"""
    table = []
    for index in range(samples + 1):
        u = index / float(samples)
        inv = 1.0 - u
        x = 3.0 * inv * inv * u * x1 + 3.0 * inv * u * u * x2 + u * u * u
        y = 3.0 * inv * inv * u * y1 + 3.0 * inv * u * u * y2 + u * u * u
        table.append((x, y))
    return tuple(table)


def _bezier_ease(t, table):
    """沿 x 从预采样表插值出 y（等价于沿贝塞尔曲线解 x 得到 y）。"""
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    low, high = 0, len(table) - 1
    while low + 1 < high:
        mid = (low + high) // 2
        if table[mid][0] <= t:
            low = mid
        else:
            high = mid
    x0, y0 = table[low]
    x1, y1 = table[high]
    if x1 <= x0:
        return y1
    return y0 + (y1 - y0) * ((t - x0) / (x1 - x0))


def _ease_at(ease, progress):
    """按缓动描述把 0..1 的进度映射成 0..1 的插值权重。"""
    if progress <= 0.0:
        return 0.0
    if progress >= 1.0:
        return 1.0
    if ease is None:  # 阶跃：整个区间保持当前帧的值
        return 0.0
    kind = ease[0]
    if kind == "line":
        return progress
    if kind == "curve":
        return _bezier_ease(progress, ease[1])
    if kind == "quadin":
        value = progress * progress
        return (value - progress) * ease[1] + progress
    if kind == "quadout":
        value = 1.0 - (1.0 - progress) * (1.0 - progress)
        return (value - progress) * ease[1] + progress
    return progress


# ============================================================================
# 骨骼时间轴
# ============================================================================
class _Timeline(object):
    """一条骨骼时间轴（translate / rotate / scale）。

    关键帧按累计帧位置存放：keys = [(start, duration, values, ease, tween_rotate, clockwise), ...]
    values 是 2 元组:
        translate -> (dx, dy)         单位: DragonBones 单位
        rotate    -> (d_rotation, d_skew)  单位: 弧度
        scale     -> (mul_x, mul_y)
    """

    __slots__ = ("kind", "keys")

    def __init__(self, kind, frames):
        self.kind = kind
        self.keys = []
        time = 0.0
        for raw in frames or []:
            if not isinstance(raw, dict):
                raw = {}
            duration = _f(raw.get("duration"))
            values = self._values(raw)
            ease = _parse_ease(raw)
            tween_rotate = _f(raw.get("tweenRotate"))
            clockwise = raw.get("clockwise") if "clockwise" in raw else None
            self.keys.append((time, duration, values, ease, tween_rotate, clockwise))
            time += duration

    def _values(self, raw):
        if self.kind == "translate":
            return (_f(raw.get("x")), _f(raw.get("y")))
        if self.kind == "rotate":
            return (_f(raw.get("rotate")) * DEG, _f(raw.get("skew")) * DEG)
        return (_f(raw.get("x"), 1.0), _f(raw.get("y"), 1.0))

    @property
    def total(self):
        if not self.keys:
            return 0.0
        start, duration, _v, _e, _tr, _cw = self.keys[-1]
        return start + duration

    def sample(self, time):
        """在 time（帧）处采样；无关键帧返回 None。"""
        keys = self.keys
        if not keys:
            return None
        if time <= keys[0][0]:
            return keys[0][2]
        for index in range(len(keys) - 1):
            start, duration, values, ease, tween_rotate, clockwise = keys[index]
            next_key = keys[index + 1]
            if time >= next_key[0]:
                continue
            if duration <= 0.0:
                return next_key[2]
            progress = (time - start) / duration
            weight = _ease_at(ease, progress)
            return self._lerp(
                values, next_key[2], weight, tween_rotate, clockwise
            )
        return keys[-1][2]

    def _lerp(self, current, target, weight, tween_rotate, clockwise):
        if self.kind == "rotate":
            delta_rotation = target[0] - current[0]
            if tween_rotate:
                # tweenRotate 是「额外圈数」，正值 = 顺时针（本数据 y 向下）
                delta_rotation += tween_rotate * math.pi * 2.0
            elif clockwise is True and delta_rotation < 0.0:
                delta_rotation += math.pi * 2.0
            elif clockwise is False and delta_rotation > 0.0:
                delta_rotation -= math.pi * 2.0
            return (
                current[0] + delta_rotation * weight,
                current[1] + (target[1] - current[1]) * weight,
            )
        return (
            current[0] + (target[0] - current[0]) * weight,
            current[1] + (target[1] - current[1]) * weight,
        )


class _StepTimeline(object):
    """阶跃时间轴（slot 的 displayFrame / colorFrame）。"""

    __slots__ = ("frames",)

    def __init__(self, frames, value_fn):
        self.frames = []  # [(start, duration, value)]
        time = 0.0
        for raw in frames or []:
            if not isinstance(raw, dict):
                raw = {}
            duration = _f(raw.get("duration"))
            self.frames.append((time, duration, value_fn(raw)))
            time += duration

    def sample(self, time):
        """返回 time 处生效的值；没有任何帧返回 None。"""
        frames = self.frames
        if not frames:
            return None
        value = frames[0][2]
        for start, _duration, each in frames:
            if time >= start:
                value = each
            else:
                break
        return value


def _display_value(raw):
    """displayFrame: 5.5 用 value, 旧格式用 displayIndex（-1 = 隐藏）。"""
    value = raw.get("value")
    if value is None:
        value = raw.get("displayIndex")
    if isinstance(value, dict):
        value = value.get("value", value.get("displayIndex"))
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _color_value(raw):
    """colorFrame: value 可能是嵌套 dict，也可能是平铺的 aM/rM/gM/bM（百分比 0..100）。"""
    value = raw.get("value")
    if isinstance(value, dict):
        raw_color = value
    else:
        raw_color = raw
    if not isinstance(raw_color, dict):
        return None
    color = {}
    for key in ("aM", "rM", "gM", "bM"):
        if key in raw_color:
            color[key] = _f(raw_color.get(key), 100.0)
    for key in ("aO", "rO", "gO", "bO"):
        if key in raw_color:
            color[key] = _f(raw_color.get(key), 0.0)
    return color or None


# ============================================================================
# 静态数据对象
# ============================================================================
class _Bone(object):
    __slots__ = (
        "name",
        "parent",
        "rest",
        "rest_matrix",
        "inherit_translation",
        "inherit_rotation",
        "inherit_scale",
        "inherit_reflection",
    )

    def __init__(self, name, parent, rest, raw=None):
        self.name = name
        self.parent = parent
        self.rest = rest
        self.rest_matrix = rest.matrix()
        raw = raw if isinstance(raw, dict) else {}
        # DragonBones 5.5 的骨骼可以只继承部分父变换；缺省全部为 True。
        self.inherit_translation = bool(raw.get("inheritTranslation", True))
        self.inherit_rotation = bool(raw.get("inheritRotation", True))
        self.inherit_scale = bool(raw.get("inheritScale", True))
        self.inherit_reflection = bool(raw.get("inheritReflection", True))


class _Display(object):
    """skin 里的一个显示对象（贴图名字 + 相对骨骼的局部变换 + pivot）。"""

    __slots__ = ("name", "path", "transform", "matrix", "pivot_x", "pivot_y")

    def __init__(self, raw):
        self.name = str(raw.get("name") or "")
        path = raw.get("path") or raw.get("name") or ""
        self.path = str(path)
        self.transform = _Transform(raw.get("transform"))
        self.matrix = self.transform.matrix()
        pivot = raw.get("pivot")
        if isinstance(pivot, dict):
            pivot_u = _f(pivot.get("x"), 0.5)
            pivot_v = _f(pivot.get("y"), 0.5)
        elif isinstance(pivot, (list, tuple)) and len(pivot) >= 2:
            pivot_u = _f(pivot[0], 0.5)
            pivot_v = _f(pivot[1], 0.5)
        else:
            pivot_u = pivot_v = 0.5
        self.pivot_x = pivot_u
        self.pivot_y = pivot_v


class _Slot(object):
    __slots__ = (
        "name",
        "parent",
        "display_index",
        "color",
        "displays",
        "blend_mode",
        "z_order",
    )

    def __init__(self, raw, displays):
        self.name = str(raw.get("name") or "")
        self.parent = raw.get("parent")
        self.display_index = int(_f(raw.get("displayIndex"), 0.0))
        self.color = raw.get("color") if isinstance(raw.get("color"), dict) else {}
        self.displays = displays
        self.blend_mode = raw.get("blendMode")
        self.z_order = int(_f(raw.get("z"), 0.0))


class _Animation(object):
    __slots__ = (
        "name",
        "duration",
        "play_times",
        "bones",
        "slot_display",
        "slot_color",
    )

    def __init__(self, raw):
        self.name = str(raw.get("name") or "")
        self.duration = max(0.0, _f(raw.get("duration")))
        self.play_times = int(_f(raw.get("playTimes"), 0.0))
        # 骨骼名 -> {kind: _Timeline}
        self.bones = {}
        for bone_raw in raw.get("bone") or []:
            if not isinstance(bone_raw, dict):
                continue
            name = bone_raw.get("name")
            if not name:
                continue
            timelines = {}
            for key, kind in (
                ("translateFrame", "translate"),
                ("rotateFrame", "rotate"),
                ("scaleFrame", "scale"),
            ):
                frames = bone_raw.get(key)
                if isinstance(frames, (list, tuple)) and frames:
                    timelines[kind] = _Timeline(kind, frames)
            if timelines:
                self.bones[name] = timelines
        # slot 名 -> _StepTimeline
        self.slot_display = {}
        self.slot_color = {}
        for slot_raw in raw.get("slot") or []:
            if not isinstance(slot_raw, dict):
                continue
            name = slot_raw.get("name")
            if not name:
                continue
            display_frames = slot_raw.get("displayFrame")
            if display_frames is None:
                display_frames = slot_raw.get("frame")  # 旧字段名
            if isinstance(display_frames, (list, tuple)) and display_frames:
                self.slot_display[name] = _StepTimeline(display_frames, _display_value)
            color_frames = slot_raw.get("colorFrame")
            if isinstance(color_frames, (list, tuple)) and color_frames:
                self.slot_color[name] = _StepTimeline(color_frames, _color_value)


class _Armature(object):
    """一个 armature 的解析结果（骨骼、槽位、皮肤、动画、aabb）。"""

    __slots__ = (
        "name",
        "fps",
        "aabb",
        "size",
        "anchor",
        "bones",
        "bone_order",
        "slots",
        "animations",
        "animation_order",
        "default_animation",
        "_region_probe",  # DBModel 注入: 贴图名 -> 裁剪信息（无 aabb 时估算用）
    )

    def __init__(self, raw, default_fps=30.0):
        self.name = str(raw.get("name") or "")
        self.fps = _f(raw.get("frameRate"), default_fps) or default_fps
        if self.fps <= 0.0:
            self.fps = 30.0

        aabb = raw.get("aabb") if isinstance(raw.get("aabb"), dict) else None
        if aabb and _f(aabb.get("width")) > 0.0 and _f(aabb.get("height")) > 0.0:
            self.aabb = {
                "x": _f(aabb.get("x")),
                "y": _f(aabb.get("y")),
                "width": _f(aabb.get("width")),
                "height": _f(aabb.get("height")),
            }
        else:
            self.aabb = None

        # ---- 骨骼 ----
        self.bones = {}
        for bone_raw in raw.get("bone") or []:
            if not isinstance(bone_raw, dict):
                continue
            name = bone_raw.get("name")
            if not name:
                continue
            parent = bone_raw.get("parent")
            if parent not in ("", None) and parent not in self.bones:
                # 父骨骼可能稍后出现，先记录名字，稍后统一补
                pass
            self.bones[name] = _Bone(
                name,
                parent if parent else None,
                _Transform(bone_raw.get("transform")),
                bone_raw,
            )
        self.bone_order = self._order_bones()

        # ---- 皮肤（默认取第一套）----
        skin_displays = {}
        skins = raw.get("skin") or []
        if isinstance(skins, (list, tuple)):
            for skin in skins:
                if not isinstance(skin, dict):
                    continue
                for skin_slot in skin.get("slot") or []:
                    if not isinstance(skin_slot, dict):
                        continue
                    slot_name = skin_slot.get("name")
                    if not slot_name or slot_name in skin_displays:
                        continue
                    displays = []
                    for display_raw in skin_slot.get("display") or []:
                        if not isinstance(display_raw, dict):
                            displays.append(None)
                            continue
                        try:
                            displays.append(_Display(display_raw))
                        except Exception:
                            displays.append(None)
                    skin_displays[slot_name] = displays

        # ---- 槽位（列表顺序 = 绘制顺序）----
        self.slots = []
        for slot_raw in raw.get("slot") or []:
            if not isinstance(slot_raw, dict):
                continue
            name = slot_raw.get("name")
            if not name:
                continue
            self.slots.append(_Slot(slot_raw, skin_displays.get(name, [])))

        # 没有 z 字段时按槽位列表顺序；有 z 时按 z 排序（稳定）。
        if any(slot.z_order for slot in self.slots):
            self.slots.sort(key=lambda s: s.z_order)

        # ---- 动画 ----
        self.animations = {}
        self.animation_order = []
        for anim_raw in raw.get("animation") or []:
            if not isinstance(anim_raw, dict):
                continue
            anim = _Animation(anim_raw)
            if not anim.name:
                continue
            if anim.duration <= 0.0:
                anim.duration = self._guess_duration(anim)
            self.animations[anim.name] = anim
            self.animation_order.append(anim.name)
        self.default_animation = (
            self.animation_order[0] if self.animation_order else None
        )

        # ---- aabb 兜底：没有 aabb 时用第一帧所有可见 slot 的四边形并集 ----
        if self.aabb is None:
            self.aabb = self._compute_aabb()
        self.size = (self.aabb["width"], self.aabb["height"])
        self.anchor = (
            self.aabb["x"] + self.aabb["width"] * 0.5,
            self.aabb["y"] + self.aabb["height"],
        )

    # -- 内部 --
    def _order_bones(self):
        """父在前、子在后的顺序（容忍父骨骼缺失/环）。"""
        order = []
        state = {}
        bones = self.bones
        for name in bones:
            if state.get(name):
                continue
            stack = []
            current = name
            while current is not None and not state.get(current):
                state[current] = 1  # 访问中
                stack.append(current)
                parent = bones[current].parent
                if parent not in bones or parent in state:
                    break
                current = parent
            for each in reversed(stack):
                order.append(each)
                state[each] = 2
        # 环/异常兜底：补上所有未输出的骨骼
        for name in bones:
            if name not in order:
                order.append(name)
        return order

    @staticmethod
    def _guess_duration(anim):
        total = 0.0
        for timelines in anim.bones.values():
            for timeline in timelines.values():
                total = max(total, timeline.total)
        for timeline in anim.slot_display.values():
            if timeline.frames:
                start, duration, _v = timeline.frames[-1]
                total = max(total, start + duration)
        for timeline in anim.slot_color.values():
            if timeline.frames:
                start, duration, _v = timeline.frames[-1]
                total = max(total, start + duration)
        return total

    def _compute_aabb(self):
        """没有 aabb 时，用绑定姿势下所有可见 slot 的矩形并集估算。"""
        min_x = min_y = float("inf")
        max_x = max_y = float("-inf")
        for slot in self.slots:
            if slot.display_index < 0 or slot.display_index >= len(slot.displays):
                continue
            display = slot.displays[slot.display_index]
            if display is None:
                continue
            bone = self.bones.get(slot.parent)
            if bone is None:
                continue
            region = getattr(self, "_region_probe", None)
            if not callable(region):
                continue
            rect = region(display.path)
            if not rect:
                continue
            width, height, frame_w, frame_h, frame_x, frame_y = rect
            pivot_x = display.pivot_x * frame_w + frame_x
            pivot_y = display.pivot_y * frame_h + frame_y
            matrix = _mat_mul(
                bone.rest_matrix,
                _mat_mul(display.matrix, _mat_translate(-pivot_x, -pivot_y)),
            )
            for u, v in ((0, 0), (width, 0), (width, height), (0, height)):
                px, py = _mat_apply(matrix, u, v)
                min_x = min(min_x, px)
                min_y = min(min_y, py)
                max_x = max(max_x, px)
                max_y = max(max_y, py)
        if min_x == float("inf"):
            return {"x": -32.0, "y": -64.0, "width": 64.0, "height": 64.0}
        return {
            "x": min_x,
            "y": min_y,
            "width": max(1.0, max_x - min_x),
            "height": max(1.0, max_y - min_y),
        }


# ============================================================================
# 图集区域
# ============================================================================
class _Region(object):
    """atlas SubTexture 的裁剪信息。"""

    __slots__ = ("x", "y", "width", "height", "frame_x", "frame_y", "frame_w", "frame_h", "rotated")

    def __init__(self, raw, atlas_scale=1.0):
        self.x = int(_f(raw.get("x")))
        self.y = int(_f(raw.get("y")))
        self.width = max(0, int(_f(raw.get("width"))))
        self.height = max(0, int(_f(raw.get("height"))))
        self.rotated = bool(raw.get("rotated"))
        has_frame = "frameX" in raw or "frameY" in raw
        if has_frame:
            self.frame_w = max(0, int(_f(raw.get("frameWidth"), self.width)))
            self.frame_h = max(0, int(_f(raw.get("frameHeight"), self.height)))
            self.frame_x = int(_f(raw.get("frameX")))
            self.frame_y = int(_f(raw.get("frameY")))
        else:
            self.frame_w = self.width
            self.frame_h = self.height
            self.frame_x = 0
            self.frame_y = 0


# ============================================================================
# DBModel
# ============================================================================
class DBModel(object):
    """一套 DragonBones 资源（一个目录）解析后的只读模型。

    由 assets.db(key) 加载/缓存，可被任意多个 DBPlayer 共享。
    """

    def __init__(self, dir_path, key=None):
        self.dir_path = os.path.abspath(str(dir_path))
        self.key = key or self._infer_key()

        self.meta = _read_json(os.path.join(self.dir_path, "meta.json")) or {}
        skeleton = _read_json(os.path.join(self.dir_path, "skeleton.json"))
        if skeleton is None:
            raise FileNotFoundError(
                "DragonBones skeleton.json 不存在或无法解析: %s" % self.dir_path
            )
        self.skeleton = skeleton
        self._atlas_raw = _read_json(os.path.join(self.dir_path, "atlas.json")) or {}

        # 图集：名字 -> _Region
        self.atlas = {}
        self.texture_scale = 1.0
        self._parse_atlas()
        # 纹理（失败也不致命：没有贴图就什么都不画）
        self.texture = self._load_texture()
        self.texture_size = (
            self.texture.get_size() if self.texture is not None else (0, 0)
        )
        self._crops = {}
        # 逐槽位「旋转+缩放+染色」结果缓存，按量化后的角度/缩放/颜色索引，
        # 让同一模型的大量实例（例如一片僵尸）复用同一张贴图变换结果。
        self._xform_cache = {}
        self._xform_pixels = 0

        # 全部 armature
        default_fps = _f(self.skeleton.get("frameRate"), 30.0) or 30.0
        self.armatures = {}
        self.armature_order = []
        for armature_raw in self.skeleton.get("armature") or []:
            if not isinstance(armature_raw, dict):
                continue
            try:
                armature = _Armature(armature_raw, default_fps)
            except Exception:
                continue
            if not armature.name:
                continue
            armature._region_probe = self._probe_region
            if armature.aabb is None:  # 解析时无法探图集，这里补算
                armature.aabb = armature._compute_aabb()
                armature.size = (armature.aabb["width"], armature.aabb["height"])
                armature.anchor = (
                    armature.aabb["x"] + armature.aabb["width"] * 0.5,
                    armature.aabb["y"] + armature.aabb["height"],
                )
            self.armatures[armature.name] = armature
            self.armature_order.append(armature.name)
        if not self.armatures:
            raise ValueError("DragonBones skeleton 中没有可用 armature: %s" % self.dir_path)

        self.armature_hint = self._meta_armature_hint()
        self._armature = self._pick_armature(self.armature_hint)
        self._sync_armature_fields()

    # ------------------------------------------------------------------
    # 加载辅助
    # ------------------------------------------------------------------
    def _infer_key(self):
        """key 优先取 meta 的 key/prefab，否则用目录名。"""
        meta = _read_json(os.path.join(self.dir_path, "meta.json")) or {}
        for field in ("key", "prefab", "path"):
            value = meta.get(field)
            if isinstance(value, str) and value:
                return value
        return os.path.basename(self.dir_path.rstrip("\\/"))

    def _parse_atlas(self):
        raw_atlas = self._atlas_raw
        scale = _f(raw_atlas.get("scale"), 1.0)
        self.texture_scale = scale if scale > 0.0 else 1.0
        subtextures = raw_atlas.get("SubTexture")
        if not isinstance(subtextures, (list, tuple)):
            subtextures = raw_atlas.get("subTexture")
        if not isinstance(subtextures, (list, tuple)):
            return
        for raw in subtextures:
            if not isinstance(raw, dict):
                continue
            name = raw.get("name")
            if not name:
                continue
            try:
                region = _Region(raw, self.texture_scale)
            except Exception:
                continue
            if region.width > 0 and region.height > 0:
                self.atlas[str(name)] = region

    def _probe_region(self, name):
        """给 _Armature._compute_aabb 用：返回 (w, h, frame_w, frame_h, frame_x, frame_y)。"""
        region = self.atlas.get(name)
        if region is None:
            return None
        return (
            region.width,
            region.height,
            region.frame_w,
            region.frame_h,
            region.frame_x,
            region.frame_y,
        )

    def _load_texture(self):
        candidates = []
        image_path = self._atlas_raw.get("imagePath")
        if isinstance(image_path, str) and image_path:
            candidates.append(
                os.path.join(self.dir_path, os.path.basename(image_path))
            )
        for name in (
            "texture.png",
            "texture.PNG",
            "texture.webp",
            "texture.jpg",
            "texture.bin",  # 抓包工具落盘时可能是 AVIF/PNG 原始字节，交给 Pillow 识别
        ):
            candidates.append(os.path.join(self.dir_path, name))
        for path in candidates:
            if not os.path.isfile(path):
                continue
            surface = _load_surface(path)
            if surface is not None:
                return surface
        return None

    def _meta_armature_hint(self):
        meta = self.meta
        name = meta.get("armature")
        if isinstance(name, str) and name in self.armatures:
            return name
        for arm_info in meta.get("armatures") or []:
            if isinstance(arm_info, dict):
                each = arm_info.get("name")
                if isinstance(each, str) and each in self.armatures:
                    return each
        # dbdump 旧版 meta: nodes[].comps[].arm
        for node in meta.get("nodes") or []:
            if not isinstance(node, dict):
                continue
            for comp in node.get("comps") or []:
                if isinstance(comp, dict):
                    each = comp.get("arm")
                    if isinstance(each, str) and each in self.armatures:
                        return each
        return None

    def _pick_armature(self, name=None):
        if isinstance(name, str) and name in self.armatures:
            return self.armatures[name]
        if self.armature_hint in self.armatures:
            return self.armatures[self.armature_hint]
        if self.armature_order:
            return self.armatures[self.armature_order[0]]
        raise ValueError("DragonBones 没有可用 armature: %s" % self.dir_path)

    def _sync_armature_fields(self):
        armature = self._armature
        self.armature_name = armature.name
        self.animations = list(armature.animation_order)
        self.size = armature.size
        self.aabb = dict(armature.aabb)
        self.anchor = armature.anchor
        self.fps = armature.fps
        self.default_animation = armature.default_animation
        meta_default = self.meta.get("default_animation")
        if isinstance(meta_default, str) and meta_default in armature.animations:
            self.default_animation = meta_default
        root_scale = self.meta.get("root_scale")
        if isinstance(root_scale, (list, tuple)) and len(root_scale) >= 2:
            self.root_scale = (_f(root_scale[0], 1.0), _f(root_scale[1], 1.0))
        else:
            self.root_scale = (1.0, 1.0)

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------
    @classmethod
    def load(cls, dir_path, armature=None, key=None):
        """加载一套 DragonBones 资源；armature 可指定要使用的骨架名字。"""
        model = cls(dir_path, key=key)
        if armature is not None:
            model.use_armature(armature)
        return model

    def use_armature(self, name):
        """切换当前 armature（同一目录里多套骨架时用，例如僵尸变体）。"""
        armature = self._pick_armature(name)
        if armature is not self._armature:
            self._armature = armature
            self._sync_armature_fields()
        return self.armature_name

    def get_armature(self, name=None):
        """按名字取 armature；name 为 None 时返回当前 armature。"""
        if name is None:
            return self._armature
        return self.armatures.get(name) or self._pick_armature(name)

    def sprite(self, name):
        """取 atlas 里某个贴图名的裁剪 Surface（缓存）。缺图返回 None。"""
        name = str(name)
        if name in self._crops:
            return self._crops[name]
        surface = None
        region = self.atlas.get(name)
        if region is not None and self.texture is not None:
            surface = self._crop_region(region)
        self._crops[name] = surface
        return surface

    def _crop_region(self, region):
        try:
            texture_rect = self.texture.get_rect()
            rect = pygame.Rect(region.x, region.y, region.width, region.height)
            rect = rect.clip(texture_rect)
            if rect.width <= 0 or rect.height <= 0:
                return None
            surface = self.texture.subsurface(rect).copy()
            if region.rotated:
                surface = pygame.transform.rotate(surface, 90)
            return surface
        except Exception:
            return None

    def __repr__(self):  # pragma: no cover - 调试用
        return "<DBModel key=%r armature=%r anims=%s size=%s>" % (
            self.key,
            self.armature_name,
            self.animations,
            self.size,
        )

    # ------------------------------------------------------------------
    # 内部绘制辅助（供 DBPlayer 使用）
    # ------------------------------------------------------------------
    def region_size(self, name):
        region = self.atlas.get(str(name))
        if region is None:
            return None
        return (region.width, region.height, region.frame_w, region.frame_h,
                region.frame_x, region.frame_y)

    def transformed_sprite(self, name, flipped, angle_deg, scale_x, scale_y,
                           red=1.0, green=1.0, blue=1.0):
        """返回“垂直翻转(可选) + 缩放 + 旋转 + RGB 乘数”后的贴图（带缓存）。

        角度按 0.5°、缩放按 1/256、颜色按 1/255 量化做缓存 key——这些量在
        连续帧之间变化很慢，缓存命中率很高，能省掉大量 pygame.transform 调用。
        """
        key = (
            name,
            bool(flipped),
            int(round(angle_deg * 2.0)),
            int(round(scale_x * 256.0)),
            int(round(scale_y * 256.0)),
            int(round(red * 255.0)),
            int(round(green * 255.0)),
            int(round(blue * 255.0)),
        )
        cache = self._xform_cache
        cached = cache.get(key)
        if cached is not None:
            return cached

        base = self.sprite(name)
        if base is None:
            return None
        if flipped:
            try:
                base = pygame.transform.flip(base, False, True)
            except Exception:
                return None
        image = _transform_image(base, scale_x, scale_y, angle_deg)
        if image is None:
            return None
        if abs(red - 1.0) > 0.002 or abs(green - 1.0) > 0.002 or abs(blue - 1.0) > 0.002:
            try:
                image = _apply_color_mult(image, red, green, blue)
            except Exception:
                pass

        width, height = image.get_size()
        pixels = width * height
        if pixels <= 512 * 512:
            if self._xform_pixels + pixels > 6_000_000:  # ~24MB 上限
                cache.clear()
                self._xform_pixels = 0
            cache[key] = image
            self._xform_pixels += pixels
        return image


def _load_surface(path):
    """加载纹理：pygame 优先，失败时用 Pillow 兜底（AVIF/怪 PNG）。"""
    if pygame is not None:
        try:
            surface = pygame.image.load(path)
            try:
                return surface.convert_alpha()
            except Exception:
                return surface
        except Exception:
            pass
    try:
        from PIL import Image  # type: ignore

        image = Image.open(path)
        image = image.convert("RGBA")
        data = image.tobytes()
        if pygame is None:
            return None
        surface = pygame.image.fromstring(data, image.size, "RGBA")
        try:
            surface = surface.convert_alpha()
        except Exception:
            pass
        return surface
    except Exception:
        return None


# ============================================================================
# DBPlayer
# ============================================================================
class DBPlayer(object):
    """一个 DragonBones 动画播放器：推进时间、计算骨骼矩阵、逐槽位绘制。"""

    def __init__(self, model, anim="Idle", loop=True, speed=1.0, armature=None):
        self.model = model
        self._armature = model.get_armature(armature) if armature else model.get_armature()
        self.speed = _f(speed, 1.0)
        self._time = 0.0  # 单位: 帧
        self._loop = bool(loop)
        self._finished = False
        self._anim_name = None
        self._anim = None
        self._duration = 0.0
        self.set_anim(anim if anim else "Idle", loop=loop, restart=True)

    # ------------------------------------------------------------------
    # 属性
    # ------------------------------------------------------------------
    @property
    def finished(self):
        """非循环动画播放到末尾后为 True。"""
        return self._finished

    @property
    def anim_name(self):
        return self._anim_name

    @property
    def anim(self):
        return self._anim_name

    @property
    def speed(self):
        return self._speed

    @speed.setter
    def speed(self, value):
        try:
            self._speed = max(0.0, float(value))
        except (TypeError, ValueError):
            self._speed = 1.0

    @property
    def fps(self):
        return self._armature.fps if self._armature is not None else 30.0

    @property
    def duration(self):
        """当前动画时长（秒）。"""
        return self._duration / self.fps if self.fps > 0 else 0.0

    @property
    def time(self):
        """当前播放位置（秒）。"""
        return self._time / self.fps if self.fps > 0 else 0.0

    # ------------------------------------------------------------------
    # 动画切换 / 时间推进
    # ------------------------------------------------------------------
    def set_anim(self, name, loop=True, restart=True):
        """切换动画；名字不存在时回退到第一个可用动画。返回实际使用的名字。"""
        armature = self._armature
        chosen = None
        if isinstance(name, str):
            if name in armature.animations:
                chosen = name
            else:
                lowered = name.lower()
                for each in armature.animation_order:
                    if each.lower() == lowered:
                        chosen = each
                        break
        previous = self._anim_name
        if chosen is None:
            chosen = armature.animation_order[0] if armature.animation_order else None
        if chosen is None:
            self._anim = None
            self._anim_name = None
            self._duration = 0.0
            self._loop = bool(loop)
            self._finished = True
            return None
        self._anim = armature.animations.get(chosen)
        self._anim_name = chosen
        self._duration = max(0.0, self._anim.duration) if self._anim else 0.0
        self._loop = bool(loop)
        if restart or previous != chosen or previous is None:
            self._time = 0.0
        elif self._duration > 0.0:
            self._time = min(self._time, self._duration)
        self._finished = False
        if self._duration <= 0.0:
            # 静态动画（只有 1 帧 / display 切换）: 立即算播完（循环时仍算未播完）
            self._finished = not self._loop
        return chosen

    def update(self, dt):
        """按秒推进动画。dt 非法/负数会被忽略。"""
        try:
            dt = float(dt)
        except (TypeError, ValueError):
            return
        if dt <= 0.0 or dt != dt:
            return
        if self._anim is None:
            return
        duration = self._duration
        if duration <= 0.0:
            self._time = 0.0
            return
        self._time += dt * self.fps * self._speed
        if self._time < 0.0:
            self._time = 0.0
        if self._time < duration:
            return
        if self._loop:
            self._time %= duration
        else:
            self._time = duration
            self._finished = True

    # ------------------------------------------------------------------
    # 计算
    # ------------------------------------------------------------------
    def _compute_bone_world(self, time):
        """返回 {骨骼名: 数据空间（y 向下）世界矩阵}。

        DragonBones 运行时内部是 y 向上的：局部矩阵 = F·M·F（F = diag(1,-1)），
        骨架按 Bone._updateGlobalTransformMatrix 的继承规则组合，最后再翻回
        y 向下给绘制用。
        """
        armature = self._armature
        timelines = self._anim.bones if self._anim is not None else {}
        world_r = {}
        globals_r = {}
        scales_r = {}

        def parent_global(name):
            """按需分解父骨骼矩阵（只有带 inherit 标志的子骨骼才会用到）。"""
            cached = globals_r.get(name)
            if cached is None:
                backup = scales_r.get(name, (1.0, 1.0))
                cached = _decompose(world_r[name], backup[0], backup[1])
                globals_r[name] = cached
            return cached

        for name in armature.bone_order:
            bone = armature.bones[name]
            rest = bone.rest
            offset_x = offset_y = 0.0
            offset_rotation = offset_skew = 0.0
            offset_scale_x = offset_scale_y = 1.0
            bone_timelines = timelines.get(name)
            if bone_timelines:
                timeline = bone_timelines.get("translate")
                if timeline is not None:
                    values = timeline.sample(time)
                    if values:
                        offset_x, offset_y = values
                timeline = bone_timelines.get("rotate")
                if timeline is not None:
                    values = timeline.sample(time)
                    if values:
                        offset_rotation, offset_skew = values
                timeline = bone_timelines.get("scale")
                if timeline is not None:
                    values = timeline.sample(time)
                    if values:
                        offset_scale_x, offset_scale_y = values

            # 绑定姿势 + 动画增量（数据空间，y 向下）
            pose_x = rest.x + offset_x
            pose_y = rest.y + offset_y
            pose_rot = rest.rotation + offset_rotation
            pose_skew = rest.skew + offset_skew
            pose_sx = rest.scale_x * offset_scale_x
            pose_sy = rest.scale_y * offset_scale_y

            # 转到运行时约定（y 向上）：位置/旋转/斜切取反
            local_x = pose_x
            local_y = -pose_y
            local_rot = -pose_rot
            local_skew = -pose_skew
            local = _mat_trs(local_x, local_y, local_rot, local_skew, pose_sx, pose_sy)

            parent_name = bone.parent
            parent_matrix = world_r.get(parent_name) if parent_name else None
            if parent_matrix is None:
                matrix = local
            elif bone.inherit_scale:
                # 继承父缩放：局部矩阵直接 concat 父矩阵。
                if not bone.inherit_rotation:
                    local_rot = local_rot - parent_global(parent_name).rotation
                    local = _mat_trs(
                        local_x, local_y, local_rot, local_skew, pose_sx, pose_sy
                    )
                matrix = _mat_mul(parent_matrix, local)
                if not bone.inherit_translation:
                    matrix = (matrix[0], matrix[1], matrix[2], matrix[3], local_x, local_y)
            else:
                # 不继承缩放：位置和旋转分别“组装”，不再 concat 父矩阵。
                matrix_x, matrix_y = local_x, local_y
                if bone.inherit_translation:
                    matrix_x, matrix_y = _mat_apply(parent_matrix, local_x, local_y)
                matrix_rot = local_rot
                matrix_skew = local_skew
                if bone.inherit_rotation:
                    parent = parent_global(parent_name)
                    matrix_rot = local_rot + parent.rotation
                    if parent.scale_x < 0.0:
                        matrix_rot += math.pi
                    if _mat_det(parent_matrix) < 0.0:
                        matrix_rot -= local_rot * 2.0
                        if bone.inherit_reflection:
                            matrix_skew += math.pi
                matrix = _mat_trs(
                    matrix_x, matrix_y, matrix_rot, matrix_skew, pose_sx, pose_sy
                )
            world_r[name] = matrix
            scales_r[name] = (pose_sx, pose_sy)

        # 翻回数据空间（y 向下）供绘制使用
        return {name: _mat_conj(matrix) for name, matrix in world_r.items()}

    def _slot_display_index(self, slot, time):
        index = slot.display_index
        if self._anim is not None:
            timeline = self._anim.slot_display.get(slot.name)
            if timeline is not None:
                value = timeline.sample(time)
                if value is not None:
                    index = value
        return index

    def _slot_color(self, slot, time):
        """返回 alpha/rgb 乘数 (0..1)，缺省 1。"""
        multiplier = [1.0, 1.0, 1.0, 1.0]  # a, r, g, b
        raw = slot.color
        if raw:
            multiplier[0] = _f(raw.get("aM"), 100.0) / 100.0
            multiplier[1] = _f(raw.get("rM"), 100.0) / 100.0
            multiplier[2] = _f(raw.get("gM"), 100.0) / 100.0
            multiplier[3] = _f(raw.get("bM"), 100.0) / 100.0
        if self._anim is not None:
            timeline = self._anim.slot_color.get(slot.name)
            if timeline is not None:
                color = timeline.sample(time)
                if color:
                    if "aM" in color:
                        multiplier[0] = color["aM"] / 100.0
                    if "rM" in color:
                        multiplier[1] = color["rM"] / 100.0
                    if "gM" in color:
                        multiplier[2] = color["gM"] / 100.0
                    if "bM" in color:
                        multiplier[3] = color["bM"] / 100.0
        return multiplier

    # ------------------------------------------------------------------
    # 绘制
    # ------------------------------------------------------------------
    def draw(self, surf, x, y, scale=1.0, flip=False, alpha=255, anchor=None):
        """把当前帧画到 surf 上。

        (x, y) 是脚底中心（默认 anchor = armature aabb 底边中点）。
        scale 为整体缩放；flip=True 水平镜像；alpha 为整体不透明度 0..255。
        """
        if surf is None or self._armature is None:
            return
        try:
            view_scale = float(scale)
        except (TypeError, ValueError):
            view_scale = 1.0
        if abs(view_scale) < 1e-6:
            return
        try:
            alpha = max(0, min(255, int(alpha)))
        except (TypeError, ValueError):
            alpha = 255
        if alpha == 0:
            return

        armature = self._armature
        anchor_x, anchor_y = anchor if anchor is not None else self.model.anchor
        screen_scale_x = -view_scale if flip else view_scale
        screen_scale_y = view_scale
        # DB 坐标为 y 向下，和 pygame 一致，不需要翻 y。
        view = (
            screen_scale_x,
            0.0,
            0.0,
            screen_scale_y,
            x - screen_scale_x * anchor_x,
            y - screen_scale_y * anchor_y,
        )

        try:
            bone_world = self._compute_bone_world(self._time)
        except Exception:
            return

        for slot in armature.slots:
            try:
                self._draw_slot(surf, slot, bone_world, view, alpha)
            except Exception:
                # 单个槽位异常不能影响整帧（未支持的字段/坏数据）
                continue

    def _draw_slot(self, surf, slot, bone_world, view, alpha):
        model = self.model
        display_index = self._slot_display_index(slot, self._time)
        if display_index is None or display_index < 0:
            return
        if display_index >= len(slot.displays):
            return
        display = slot.displays[display_index]
        if display is None:
            return
        bone_matrix = bone_world.get(slot.parent)
        if bone_matrix is None:
            return
        region = model.atlas.get(display.path)
        if region is None:
            return
        image = model.sprite(display.path)
        if image is None:
            return

        color = self._slot_color(slot, self._time)
        color_alpha = color[0]
        if color_alpha <= 0.001:
            return

        pivot_x = display.pivot_x * region.frame_w + region.frame_x
        pivot_y = display.pivot_y * region.frame_h + region.frame_y

        # 纹理像素坐标 -> 屏幕坐标
        matrix = _mat_mul(view, bone_matrix)
        matrix = _mat_mul(matrix, display.matrix)
        matrix = _mat_mul(matrix, _mat_translate(-pivot_x, -pivot_y))

        width, height = image.get_size()
        a_x, a_y = matrix[0], matrix[1]  # 纹理 +x 方向的屏幕向量（每像素）
        b_x, b_y = matrix[2], matrix[3]  # 纹理 +y 方向的屏幕向量（每像素）
        origin_x, origin_y = matrix[4], matrix[5]  # 纹理 (0,0) 的屏幕位置

        determinant = a_x * b_y - a_y * b_x
        flipped = determinant < 0.0
        if flipped:
            # 行列为负定（镜像/负缩放）：垂直翻转贴图，再把 +y 轴取反
            origin_x += height * b_x
            origin_y += height * b_y
            b_x, b_y = -b_x, -b_y

        center_x = origin_x + 0.5 * width * a_x + 0.5 * height * b_x
        center_y = origin_y + 0.5 * width * a_y + 0.5 * height * b_y

        scale_x = math.hypot(a_x, a_y)
        scale_y = math.hypot(b_x, b_y)
        if scale_x <= 1e-6 or scale_y <= 1e-6:
            return

        angle = math.degrees(math.atan2(a_y, a_x))
        red, green, blue = color[1], color[2], color[3]
        try:
            image = model.transformed_sprite(
                display.path, flipped, angle, scale_x, scale_y, red, green, blue
            )
        except Exception:
            image = None
        if image is None:
            return

        final_alpha = int(alpha * max(0.0, min(1.0, color_alpha)))
        if final_alpha < 255:
            try:
                image = image.copy()
                image.set_alpha(final_alpha)
            except Exception:
                return

        blend_flags = 0
        if slot.blend_mode == "add":
            blend_flags = pygame.BLEND_ADD
        elif slot.blend_mode == "multiply":
            blend_flags = pygame.BLEND_MULT
        elif slot.blend_mode == "subtract":
            blend_flags = pygame.BLEND_SUB

        rect = image.get_rect()
        rect.center = (int(round(center_x)), int(round(center_y)))
        if blend_flags:
            surf.blit(image, rect, special_flags=blend_flags)
        else:
            surf.blit(image, rect)

    def __repr__(self):  # pragma: no cover - 调试用
        return "<DBPlayer anim=%r t=%.1f/%.1f finished=%s>" % (
            self._anim_name,
            self._time,
            self._duration,
            self._finished,
        )


# ============================================================================
# 贴图变换辅助
# ============================================================================
def _transform_image(image, scale_x, scale_y, angle_deg):
    """按 (scale_x, scale_y, 角度) 变换贴图；角度为屏幕坐标系（y 向下）中的旋转角。"""
    if image is None:
        return None
    width, height = image.get_size()
    if width <= 0 or height <= 0:
        return None
    target_w = max(1, int(round(width * scale_x)))
    target_h = max(1, int(round(height * scale_y)))
    if (target_w, target_h) != (width, height):
        try:
            if target_w < width or target_h < height:
                image = pygame.transform.smoothscale(image, (target_w, target_h))
            else:
                image = pygame.transform.scale(image, (target_w, target_h))
        except Exception:
            try:
                image = pygame.transform.scale(image, (target_w, target_h))
            except Exception:
                return None
    if abs(angle_deg) > 0.01:
        try:
            image = pygame.transform.rotozoom(image, -angle_deg, 1.0)
        except Exception:
            try:
                image = pygame.transform.rotate(image, -angle_deg)
            except Exception:
                return None
    return image


def _apply_color_mult(image, red, green, blue):
    """把 RGB 乘数应用到贴图（保持 alpha 不变）。"""
    if image is None:
        return None
    if image.get_flags() & pygame.SRCALPHA:
        target = image.copy()
    else:
        target = image.convert_alpha()
    mask = pygame.Surface(target.get_size(), pygame.SRCALPHA)
    mask.fill(
        (
            int(max(0, min(255, round(red * 255)))),
            int(max(0, min(255, round(green * 255)))),
            int(max(0, min(255, round(blue * 255)))),
            255,
        )
    )
    target.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    return target


__all__ = ["DBModel", "DBPlayer"]
