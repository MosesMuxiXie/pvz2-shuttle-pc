# PvZ2 SHUTTLE — Windows 复刻版 · 设计与协作契约

> 目标：在 Windows 上用 Python/pygame 复刻《植物大战僵尸2 SHUTTLE 版》的可玩体验：
> SHUTTLE 启动器 → 主菜单 → 世界地图 → 关卡战斗 → 图鉴/设置/存档。
> 素材与数值来自真实 PvZ2（Cocos 线上包，已通过 CDP 提取），启动器界面复刻自 SHUTTLE APK。

## 运行环境

- Python: `C:\Users\xiemu\.dsh\dsh-runtimes\dsh-next-primary-runtime\dependencies\python\python.exe`
- 已安装 pygame-ce 2.5.8 / Pillow 12.3.0 (AVIF 支持) / websocket-client
- 游戏根目录：`D:\OneDrive\文档\pvz_shuttle\PvZ2SHUTTLE`
- 启动：`<python> main.py`，打包入口同。
- 代理（下载用）：`$env:HTTP_PROXY="http://127.0.0.1:7897"`、`$env:HTTPS_PROXY="http://127.0.0.1:7897"`

## 目录与归属（只改自己的文件）

```
PvZ2SHUTTLE/
  main.py            [lead]
  game/
    config.py        [lead]  常量/窗口/路径
    app.py           [lead]  App 状态机、资源/数据/存档持有者
    assets.py        [lead]  图片/字体/音效/DragonBones 模型加载
    data.py          [lead]  内容 JSON → dataclass
    save.py          [lead]  存档读写
    audio.py         [lead]  音乐/音效封装（可空实现）
    dragonbones.py   [renderer] DragonBones 5.5 解析 + pygame 渲染
    engine/
      board.py       [gameplay] 草坪网格几何、格子占用、种植/铲除
      entities.py    [gameplay] Plant/Zombie/Projectile/Sun/LawnMower 实体
      level.py       [gameplay] LevelSession：战斗编排、胜负、波次、掉落
      waves.py       [gameplay] 波次导演（从关卡数据生成）
      combat.py      [gameplay] 伤害/碰撞/子弹命中/僵尸啃食
    screens/
      base.py        [ui] Screen 基类
      launcher.py    [ui] SHUTTLE 启动器（复刻 APK 布局）
      menu.py        [ui] 主菜单
      worldmap.py    [ui] 世界地图 + 关卡选择
      almanac.py     [ui] 图鉴（植物/僵尸）
      settings.py    [ui] 设置
      level_screen.py[ui] 战斗界面（HUD/卡槽/暂停/胜负）
      widgets.py     [ui] 按钮/滚动条/文本等控件
  content/
    plants.json      [content]
    zombies.json     [content]
    worlds.json      [content]
    levels/<world>_<n>.json  [content]
    almanac.json     [content]   （植物/僵尸图鉴文案，中文为主）
  assets/
    ui/              [art]  bg_home.jpg launcher.png 图标 按钮 字体
    db/<key>/{skeleton.json,atlas.json,texture.png,meta.json} [art]
    world/<world>.png[w art] 世界地图背景
    lawn/<world>.png [art]   战斗草坪背景（可选，缺省用 ui/lawn_day.png）
    audio/*.ogg      [art]   音乐/音效（缺省静音）
  tools/             [art/content] 提取脚本
  tests/             [各 owner] 自测脚本
```

## Screen 契约（所有界面统一）

```python
class Screen:
    def __init__(self, app): self.app = app
    def enter(self): ...          # 进入时调用
    def exit(self): ...
    def handle(self, event): ...  # pygame 事件
    def update(self, dt): ...
    def draw(self, surf): ...
```

`app.switch(screen_name_or_instance)` 切换；`app.assets` `app.data` `app.save` `app.font(size)` `app.quit()`。

## App API（lead 实现）

```python
app.screen_obj                # 当前 Screen 实例（注意：app.screen 是 pygame 显示 Surface）
app.switch(name_or_screen)    # "launcher"/"menu"/"worldmap"/"almanac"/"settings"/"level"
app.start_level(world_id, level_index)
app.finish_level(world_id, level_index, won)
app.assets.image(key) -> pygame.Surface        # 缓存
app.assets.db(key) -> DBModel                  # DragonBones 模型（renderer 提供）
app.assets.dbplayer(key, anim) -> DBPlayer|None
app.assets.font(size, bold=False) -> Font      # 中文字体
app.assets.sound(key) / app.audio.play(key) / app.audio.music(key)
app.data.plants: dict[str, PlantDef]
app.data.zombies: dict[str, ZombieDef]
app.data.worlds: list[WorldDef]
app.data.levels(world_id) -> list[LevelDef]
app.save: SaveData
app.updates: UpdateChecker  # app.updates.done/.result/.latest_ver，启动器可用作"前往更新"
```

## 数据 schema

### plants.json (list)
```json
{"id":"peashooter","name_zh":"豌豆射手","name_en":"Peashooter","cost":100,"cooldown":5.0,
 "hp":300,"family":"Peashooter","art":"plants/PeashooterPLANT",
 "behavior":"shoot","damage":20,"interval":1.4,"projectile":"pea","rows":[0],"pierce":false,
 "tags":["day"],"desc_zh":"...","almanac_no":1}
```
behavior ∈ `shoot`(直线子弹, rows 相对行偏移) | `lob`(抛射, 越障) | `produce`(产阳光 sun_value/sun_interval) |
`wall`(纯阻挡) | `instant`(落地爆炸 damage/radius) | `chomp`(吞噬) | `fume`(近程穿透) |
`mine`(埋雷) | `support`(buff) | `boomerang`。
可选字段：`sun_value`,`sun_interval`,`splash`,`slow`,`pierce`,`armor_pierce`,`melee_range`,`delay`。

### zombies.json (list)
```json
{"id":"mummy","name_zh":"木乃伊僵尸","name_en":"Mummy Zombie","hp":190,"speed":0.185,
 "eat_dps":100,"armor":[{"hp":370,"art":"Cone"}],"behavior":"walk",
 "art":"zombies/BasicZOMBIE","armature":"BasicZombie"|null,"cost":100,"desc_zh":"..."}
```
behavior ∈ `walk` | `jump`(撑杆跳) | `steal`(偷阳光) | `summon` | `gargantuar`(巨人不吃植物直接砸) | `fly`。
`speed` 用 PvZ2 的 WalkSPS（格/秒近似：0.185 ≈ 1 格/5.4s）。

### worlds.json (list)
```json
{"id":"frontyard","name_zh":"前院","name_en":"Frontyard","order":1,"levels":10,
 "map":"world/frontyard.png","lawn":"lawn/frontyard.png","unlock_after":null,
 "desc_zh":"...","bg_tint":[255,255,255]}
```

### levels/<world>_<n>.json
```json
{"id":"frontyard_1","world":"frontyard","index":1,"title":"第 1 天",
 "sun":250,"deck":["sunflower","peashooter","wallnut"],
 "waves":[{"delay":18.0,"flag":false,"zombies":[{"type":"basic","row":2}]}],
 "flags":1,"seed_bank":6}
```
`zombies` 可给 `row`(0-4) 或 `rows`(列表)；省略则随机行。`delay` 为该波距上一波的秒数。

### almanac.json
```json
{"plants":{"peashooter":{"desc":"...","tip":"..."}},"zombies":{"basic":{"desc":"..."}}}
```

## DragonBones 渲染契约（renderer 实现）

```python
class DBModel:      # 由 assets.db(key) 加载
    key: str
    armature_name: str
    animations: list[str]
    size: tuple[float,float]      # 根 aabb
class DBPlayer:
    def __init__(self, model, anim="Idle", loop=True, speed=1.0)
    def set_anim(self, name, loop=True, restart=True)
    def update(self, dt)
    def draw(self, surf, x, y, scale=1.0, flip=False, alpha=255)
    @property finished: bool
```
- DragonBones 5.5 JSON：`armature[i].bone/slot/skin/animation`；atlas `SubTexture[]`（含 frameX/Y/W/H 裁剪）。
- 用 Pillow 解码 `texture.png`，pygame 画每个 slot 的四边形（先忽略 mesh 变形，可后续加）。
- 锚点：角色脚底中心 = draw 的 (x,y)。
- 缺失模型时 `assets.db` 返回占位（灰块），不得崩溃。

## 美术规范

- `assets/db/<key>/` 每个角色一套；key 用 prefab 路径（`plants/PeashooterPLANT`）。
- 纹理统一转 PNG（RGBA），保留原始尺寸。
- 草坪/世界地图背景 1280x720（或等比可缩放）。
- 中文字体：使用系统 `C:\Windows\Fonts\msyh.ttc`（微软雅黑）或 `simhei.ttf`；assets/ui/font_zh.ttf 复制一份。

## 战斗画面基准（1280x720）

- 草坪 5 行 × 9 列，格子 100x116，起点 x=190, y=120。行 0 在上。
- 僵尸从 x=1280 左侧…（右侧）进入，向左走；越过 x=150 判负（触发小推车后再越线判负）。
- 小推车每行 1 个，位于 x=140。
- 阳光：初始 50；天降阳光每 8-10 秒；点击收集。向日葵每 24 秒产 25。
- 卡槽在顶部，植物卡显示费用与冷却遮罩。

## 测试

- 每 owner 提交 `tests/test_<模块>.py`，可在无窗口（SDL_VIDEODRIVER=dummy）下运行：
  `<python> tests/test_engine.py` 打印 PASS/FAIL，退出码 0/1。
- 集成测试由 lead 跑：启动画面截图 + 进入关卡模拟 60 秒不崩溃。

## 协作规则

1. 只改自己归属的文件；需要改契约先告诉 lead。
2. 每个交付点给 lead 发一条简报：完成了什么、怎么验证、阻塞点。
3. 不要下载/引入受版权限制之外的东西；素材只从已提取的 Cocos 包/APK 中来。
4. 时间优先：先跑通，再美化。占位资源可以，但不能崩溃。
