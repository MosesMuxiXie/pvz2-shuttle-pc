# 元素层：显式标为自创（authored）

**结论：元素与元素反应不是原版 SHUTTLE 机制。** 本数据层把 Python 基线的元素系统编译成可选层，每个元素与每条反应都带 `source: "authored"` 与 `rationale`，**不计入原版复刻口径**，只作为可选玩法开关。

## 一、三份证据（原版没有这套机制）

### 1.1 `ElementReactionModuleProperties` 全是空壳

obb 中引用该类名的文件 21 个，`objclass == "ElementReactionModuleProperties"` 的 objdata 恰好 21 条，**非空 0 条**（全部是 `{}`）。探针：

```powershell
cd work/obb_packages
Select-String -Pattern 'ElementReactionModuleProperties' -List *.json | Measure-Object
```

```python
# objdata 计数（21 条，全部为空）
for p in sorted(OBB.glob('*.json')):
    text = io.open(p, encoding='utf-8-sig').read()
    if 'ElementReactionModuleProperties' not in text:
        continue
    for cls, data in walk_objects(json.loads(text)):
        if cls == 'ElementReactionModuleProperties':
            total += 1; nonempty += bool(data)
```

实测：`objdata=21, nonempty=0`。模块存在，参数一个都没有。

### 1.2 `PlantPropertySheet` 没有 element 字段

`work/obb_packages/pkg_2073_PlantPropertySheet.json` 共 398 个属性对象、**1075 个不同字段名**，字段名中含 `lement` 的 0 个。植物属性里没有「攻击元素」这一维。

### 1.3 关卡 `extra` 没有 element 键

`content/levels/*.json` 共 1809 个关卡，`extra` 的键里含 `element` 的 0 个；关卡数据也没有按元素配置任何东西。

补充：`content/plants.json` 里有 2 条自创字段（`helioscabbage`、`fireflerry` 的顶层 `element: "fire"`），它们同样是本项目自创，不是原版数据，也不在本次编译范围。

## 二、数据层内容

共 5 个元素、10 条无序反应对；`source` 统一为 `authored`，输出 `native/generated/elements.json`（`format: 1`）。

### 2.1 元素

| id | 中文名 | 颜色 | 附着时长 |
|---|---|---|---|
| `water` | 水 | RGB(80, 190, 255) | 5 秒 |
| `fire` | 火 | RGB(255, 120, 40) | 5 秒 |
| `ice` | 冰 | RGB(176, 230, 255) | 2 秒 |
| `thunder` | 雷 | RGB(255, 230, 80) | 5 秒 |
| `wind` | 风 | RGB(48, 224, 208) | 5 秒 |

### 2.2 反应矩阵

| 元素对（无序） | 反应 | 倍率 | 清除 | effects |
|---|---|---|---|---|
| `water` + `fire` | 蒸发 | 2 | `fire` | — |
| `water` + `ice` | 冻结 | 1 | `water`、`ice` | `[{"seconds": 1.5, "type": "freeze"}]` |
| `water` + `thunder` | 感电 | 1 | `water`、`thunder` | `[{"cap": 1000.0, "damage": "attack", "element": "thunder", "radius": 190.0, "type": "aoe"}]` |
| `water` + `wind` | 扩散 | 1 | `water` | `[{"element": "water", "type": "spread"}]` |
| `fire` + `ice` | 融化 | 2（反向 1.5） | `ice` | — |
| `fire` + `thunder` | 超载 | 1 | `fire`、`thunder` | `[{"damage": 40.0, "element": "fire", "radius": 190.0, "type": "aoe"}]` |
| `fire` + `wind` | 扩散 | 1 | `fire` | `[{"element": "fire", "type": "spread"}]` |
| `ice` + `thunder` | 超导 | 1 | `ice`、`thunder` | `[{"mult": 0.75, "seconds": 10.0, "type": "vulnerable"}]` |
| `ice` + `wind` | 扩散 | 1 | `ice` | `[{"element": "ice", "type": "spread"}]` |
| `thunder` + `wind` | 扩散 | 1 | `thunder` | `[{"element": "thunder", "type": "spread"}]` |

## 三、与 Python 基线的差异

| 项 | Python 基线 | 本数据层 | 理由 |
|---|---|---|---|
| 物理（`None`） | 基线的 `ELEMENT_NAME` / `ELEMENT_COLOR` 里有 `None: 物理` / 灰色 | 不生成元素行 | 物理不是元素，只作为「无元素攻击」的占位；数据层只收 5 个真元素 |
| 融化方向 | 反应表里一对一个 `mult: 2.0`，但 `resolve_hit` 里冰打火被改成 1.5 | `mult: 2.0` + `directional: {attack: ice, attached: fire, mult: 1.5}` | 两个倍率都如实保留，由引擎按攻击方向选择 |
| 感电范围伤害 | `effects[0].damage` 是字符串 `"attack"`，运行时才替换为本次攻击力（上限 1000） | 原样保留字符串 `"attack"` 与 `cap`/`radius` | 字符串是动态占位，编译期无法算出具体数值 |
| 默认植物元素 | `DEFAULT_PLANT_ELEMENT` 15 个键（含 `winter_melon` 等 8 个本版不存在的 id） | 不编译 | 本任务只编译元素与反应矩阵；默认归属属于植物侧数据，未纳入 |

## 四、基线的自相矛盾（保留基线行为，不静默改）

1. **融化倍率与反应表不一致**：`_REACTIONS[frozenset((FIRE, ICE))]` 写 `mult: 2.0`，但 `resolve_hit` 用 `spec["name"] == "融化" and element == ICE and other == FIRE` 把反向改成 1.5。表本身是无方向的，方向差只存在于代码分支里 → 数据层用 `directional` 记录，同时保留表值 2.0，不替基线选边。
2. **超导的 `mult: 0.75` 语义含糊**：文档说「目标受到物理伤害 +75%」，而字段名 `mult` 的取值 0.75 读起来像「承伤 ×0.75」。两种解释方向相反（更痛 / 更抗打），基线没有进一步的注释；数据层原样保留 0.75，不擅自改成 1.75。
3. **扩散的附着时长不在数据里**：模块文档说「按元素附着 5 秒（冰为 2 秒减速）」，但 `effects` 只有 `{"type": "spread", "element": …}`，没有秒数字段；时长实际由 `ATTACH_SECONDS` 隐含。数据层保留该形状，并在元素表里给出 `attachSeconds` 供引擎取用。

## 五、口径声明

- 本数据层的元素与反应**全部为自创**，`source` 一律 `authored`，**不计入原版复刻口径**；任何「原版有元素系统」的说法都与 1.1–1.3 的实测不符。
- 是否启用由运行时开关决定；不启用时，攻击元素一律按物理处理（基线 `element_of_plant` 对未知元素返回 `None` 的行为）。
- 生成器 `tools/contentc/elements_authored.py` 的 `--check` 会逐字节校验 `native/generated/elements.json` 与本报告，过期即失败。
