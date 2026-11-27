# 卡组（deck）覆盖报告

> 由 `python tools/contentc/decks.py` 生成，不要手改；`--check` 会在报告过期时失败。

## 输入

| 项 | 路径 | 数量 |
|---|---|---|
| 关卡 | `content/levels/*.json` | 1809 |
| 植物注册表 | `content/plants.json` | 409 |
| 美术库 actor 总数 | `PvZ2SHUTTLE/assets/db/MANIFEST.json` | 72 |
| 植物用到的独立 actor | （同上） | 31 |

## 摘要

| 指标 | 数值 |
|---|---|
| 关卡总数 | 1809 |
| 世界数 | 26 |
| deck 槽位总数 | 7194 |
| 平均 deck 大小 | 3.98 |
| deck 去重植物 | 41 |
| deck 为空 | 0 |
| deck 超过 8 张 | 1 |
| 引用 plants.json 之外的 id | 0 |
| 本轮 deck 里有骨骼模型（actor） | 28 |
| 本轮 deck 里只有静态图（png） | 13 |
| 本轮 deck 里无任何美术 | 0 |

## 美术三档

- `actor`：植物 `art` 命中 `<assets>/db/MANIFEST.json` 的 actor key，有骨骼动画，算“真模型”。
- `png`：植物 `art` 是 `<assets>` 下真实存在的 png，只能静态贴图，动不了。
- `none`：两者都没有，只能画色块。

全部 409 株植物：`actor` 134 / `png` 36 / `none` 239；但独立 actor 只有 31 个——134 株“有模型”里大量是同一套骨骼换皮，真正的独立模型数是后者。

## 模型复用（一个 actor 顶多株植物）

美术库里共 72 个 actor，植物只用到其中 31 个；134 株“有模型”的植物分布在这 31 套骨骼上，其中 103 株没有独占模型。下表只列被 2 株以上植物共用的 actor（按株数降序）。

| actor | 植物数 | 植物 id |
|---|---|---|
| `plants/SunflowerPLANT` | 13 | `birthsunflower`、`darktwinsunflower`、`fused_birthsunflower`、`fused_darktwinsunflower`、`fused_darktwinsunflower_2`、`fused_primalsunflower`、`fused_reinforcemint`、`fused_reinforcemint_2`、`fused_suntower`、`oxygenalgae`、`primalsunflower`、`reinforcemint`、`sunflower` |
| `plants/GatlingPeaPLANT` | 12 | `fused_fusiongatling`、`fused_fusiongatling_2`、`fused_fusiongatling_3`、`fused_fusiongatling_4`、`fused_fusiongatling_5`、`fused_hollyknight`、`fused_hollyknight_2`、`fused_megagatling`、`fused_megagatling_2`、`fused_punkshocker`、`gatling`、`hollyknight` |
| `plants/WallnutPLANT` | 12 | `fused_chardguard`、`fused_chardguard_2`、`fused_endurian`、`fused_endurian_2`、`fused_explodeonut1`、`fused_explodeonut1_2`、`fused_gumnut`、`fused_powervine`、`fused_powervine_2`、`primalwallnut`、`unused_46`、`wallnut` |
| `plants/KernelPultPLANT` | 11 | `fused_hollybarrierleaf`、`fused_hollybarrierleaf_2`、`fused_lemonaider`、`fused_lemonaider_2`、`fused_magnetshroom`、`fused_magnetshroom_2`、`hollybarrierleaf`、`kernelpult`、`kernelpult1`、`lemonaider`、`unused_45` |
| `plants/CabbagePultPLANT` | 9 | `cabbagepult`、`fused_peppermint`、`fused_peppermint_2`、`fused_rabbagepult`、`fused_rabbagepult_2`、`fused_strawburst`、`fused_strawburst_2`、`fused_turkeypult`、`fused_turkeypult_2` |
| `plants/PeashooterPLANT` | 9 | `fused_poisonpeashooter`、`fused_poisonpeashooter_2`、`fused_primalpeashooter`、`fused_primalpeashooter_2`、`fused_slingpea`、`fused_slingpea_2`、`fused_tumbleweed`、`fused_tumbleweed_2`、`peashooter` |
| `plants/SpikeweedPLANT` | 8 | `fused_cactus1`、`fused_cactus1_2`、`fused_iceweed`、`fused_iceweed_2`、`fused_pokra1`、`fused_pokra1_2`、`fused_spikerock`、`spikeweed` |
| `plants/UmbrellaLeafPLANT` | 7 | `fused_draftodil1`、`fused_draftodil1_2`、`fused_magnetfruit`、`fused_magnetfruit_2`、`fused_sweetpotato1`、`fused_sweetpotato1_2`、`umbrellaleaf` |
| `plants/BonkChoyPLANT` | 6 | `ambershroom`、`bonkchoy`、`fused_headbutterlettuce`、`fused_headbutterlettuce_2`、`headbutter`、`unused_43` |
| `plants/CherryBombPLANT` | 4 | `cherry_bomb`、`fused_puffball`、`fused_stickybombrice`、`fused_stickybombrice_2` |
| `plants/FumeShroomPLANT` | 4 | `fumeshroom`、`fused_coldsnapdragon`、`fused_coldsnapdragon_2`、`gloomvine` |
| `plants/PotatoMinePLANT` | 4 | `fused_olivepit`、`fused_olivepit_2`、`potatomine`、`primalpotatomine` |
| `plants/WinterMelonPLANT` | 4 | `fused_wintergeddon`、`fused_wintermelon`、`fused_wintermelon_2`、`wintermelon` |
| `plants/ChomperPLANT` | 3 | `chomper`、`fused_snappea1`、`fused_snappea1_2` |
| `plants/HomingThistlePLANT` | 3 | `homingthistle`、`magnetfruit`、`sungun` |
| `plants/RepeaterPLANT` | 3 | `fused_repeater1`、`repeater`、`repeater1` |
| `plants/SnowPeaPLANT` | 3 | `fused_snowpea`、`fused_snowpea_2`、`snowpea` |
| `plants/SplitPeaPLANT` | 3 | `fused_shadowpeashooter`、`fused_shadowpeashooter_2`、`splitpea` |
| `plants/BloomerangPLANT` | 2 | `bloomerang`、`bloomerang1` |
| `plants/StarFruitPLANT` | 2 | `starfruit`、`starfruit_barrage` |
| `plants/TorchwoodPLANT` | 2 | `citron`、`torchwood` |

## 逐世界覆盖

“有行为族”= 植物 `behavior` 落在 `registry.cpp:486 plantFamilies()` 的 11 族里。

| 世界 | 关卡 | deck 槽位 | 去重植物 | 有行为族 | 真模型 | 仅静态图 | 无美术 | 空 deck | 超 8 张 |
|---|---|---|---|---|---|---|---|---|---|
| beach | 95 | 377 | 8 | 8 | 8 | 0 | 0 | 0 | 0 |
| carnival | 93 | 370 | 15 | 15 | 15 | 0 | 0 | 0 | 0 |
| chinesegarden | 72 | 286 | 19 | 19 | 13 | 6 | 0 | 0 | 1 |
| cowboy | 42 | 168 | 11 | 11 | 11 | 0 | 0 | 0 | 0 |
| dark | 79 | 314 | 9 | 9 | 9 | 0 | 0 | 0 | 0 |
| dino | 63 | 252 | 4 | 4 | 4 | 0 | 0 | 0 | 0 |
| egypt | 84 | 335 | 16 | 16 | 15 | 1 | 0 | 0 | 0 |
| eighties | 72 | 288 | 12 | 12 | 12 | 0 | 0 | 0 | 0 |
| fairy | 50 | 197 | 10 | 10 | 9 | 1 | 0 | 0 | 0 |
| frontyard | 175 | 702 | 23 | 23 | 22 | 1 | 0 | 0 | 0 |
| future | 71 | 280 | 11 | 11 | 11 | 0 | 0 | 0 | 0 |
| heian | 42 | 167 | 7 | 7 | 7 | 0 | 0 | 0 | 0 |
| iceage | 72 | 286 | 7 | 7 | 7 | 0 | 0 | 0 | 0 |
| kongfu | 83 | 330 | 7 | 7 | 7 | 0 | 0 | 0 | 0 |
| losantosvice | 27 | 103 | 13 | 13 | 10 | 3 | 0 | 0 | 0 |
| lostcity | 69 | 272 | 11 | 11 | 11 | 0 | 0 | 0 | 0 |
| lunarrainbowmarket | 126 | 493 | 20 | 20 | 17 | 3 | 0 | 0 | 0 |
| mausoleum | 55 | 220 | 10 | 10 | 10 | 0 | 0 | 0 | 0 |
| memorytour | 11 | 44 | 8 | 8 | 8 | 0 | 0 | 0 | 0 |
| modern | 129 | 515 | 10 | 10 | 10 | 0 | 0 | 0 | 0 |
| muji | 30 | 119 | 6 | 6 | 5 | 1 | 0 | 0 | 0 |
| pirate | 67 | 266 | 13 | 13 | 13 | 0 | 0 | 0 | 0 |
| plantagenet | 49 | 195 | 7 | 7 | 5 | 2 | 0 | 0 | 0 |
| renai | 59 | 240 | 9 | 9 | 9 | 0 | 0 | 0 | 0 |
| sky | 57 | 227 | 6 | 6 | 6 | 0 | 0 | 0 | 0 |
| steam | 37 | 148 | 4 | 4 | 4 | 0 | 0 | 0 | 0 |
| **合计** | 1809 | 7194 | 41 | 41 | 28 | 13 | 0 | 0 | 1 |

## deck 缺真模型的植物

deck 引用到 41 株植物，其中 13 株没有骨骼模型：它们只能出静态图或色块，动作、受击、死亡演出全部缺失。按 deck 引用次数降序。

| 植物 | 引用次数 | 行为族 | art | 档位 |
|---|---|---|---|---|
| potatochip | 117 | instant | `art/lunarrainbowmarket/potatochip.png` | png |
| begonia | 114 | lob | `art/lunarrainbowmarket/begonia.png` | png |
| missiletoast | 110 | lob | `art/lunarrainbowmarket/missiletoast.png` | png |
| elderbarrier | 58 | wall | `art/chinesegarden/elderbarrier.png` | png |
| gardenia | 55 | shoot | `art/chinesegarden/gardenia.png` | png |
| torpedofruit | 54 | shoot | `art/chinesegarden/torpedofruit.png` | png |
| iris | 48 | shoot | `art/plantagenet/iris.png` | png |
| olivewood | 48 | wall | `art/plantagenet/olivewood.png` | png |
| yuccaguardian | 25 | wall | `art/losantosvice/yuccaguardian.png` | png |
| birdofparadise | 23 | shoot | `art/losantosvice/birdofparadise.png` | png |
| jasmine | 7 | produce | `art/chinesegarden/jasmine.png` | png |
| poppinpoppies | 3 | shoot | `art/losantosvice/poppinpoppies.png` | png |
| seapotatomine | 3 | mine | `art/chinesegarden/seapotatomine.png` | png |

## deck 超过 8 张的关卡

| 关卡 | 世界 | deck 张数 | deck |
|---|---|---|---|
| chinesegarden_68 | chinesegarden | 11 | `sunflower`, `homingthistle`, `iceburg`, `potatomine`, `wallnut`, `sunshroom`, `snowpea`, `jasmine`, `gardenia`, `elderbarrier`, `potatochip` |

## deck 引用但 plants.json 里不存在的 id

（无）每条 deck 里的植物 id 都能在 `content/plants.json` 里找到。

## 空 deck 策略

本版空 deck 共 0 关。策略：空 deck 的关卡按 `seed_bank` 的顺序取默认卡组；`seed_bank` 也为空时，该关单独列入“空 deck 关卡”清单，不参与“去重植物”统计，并在摘要里点名。当前没有这种关卡，所以上面的世界表里每一关的 deck 都是关卡文件自己声明的。

## 结论

1. **有模型不等于有形象。** 注册表 409 株植物里 134 株（33%）能挂到骨骼模型上，但这 134 株只用了 31 套 actor——独立形象只覆盖 31/409（8%），103 株是换皮。另外 36 株只有一张静态 png，239 株连图都没有。
2. **本轮真正被玩到的只有 41 株。** 1809 关的 deck 一共 7194 个槽位，去重后只引用 41 株植物；其中 28 株（68%）有骨骼模型，13 株只有静态图，0 株无美术。也就是说：现有关卡能跑起来的部分，本质上是“少数几株植物反复出现”，美术缺口集中在少数新世界植物上，而不是均匀分布在 409 株里。
3. **对“完整复刻”的含义。** 行为族这一侧是齐的（41/41 株 deck 植物都有已实现的 behavior 族），真正的短板是表现层：没有骨骼模型的植物在引擎里只能当静态贴图或色块，补多少行为代码都换不来它的动作演出。若目标是 1809 关全部可玩到“看起来对”，必须先把 deck 实际引用的缺模型植物补齐，而不是去铺满注册表里的每一株。

建议先补的 id（按 deck 引用频次 top 20；含 deck 未引用的植物，其次数为 0）：

| # | 植物 | 引用次数 | 行为族 | 当前档位 |
|---|---|---|---|---|
| 1 | `potatochip` | 117 | instant | png |
| 2 | `begonia` | 114 | lob | png |
| 3 | `missiletoast` | 110 | lob | png |
| 4 | `elderbarrier` | 58 | wall | png |
| 5 | `gardenia` | 55 | shoot | png |
| 6 | `torpedofruit` | 54 | shoot | png |
| 7 | `iris` | 48 | shoot | png |
| 8 | `olivewood` | 48 | wall | png |
| 9 | `yuccaguardian` | 25 | wall | png |
| 10 | `birdofparadise` | 23 | shoot | png |
| 11 | `jasmine` | 7 | produce | png |
| 12 | `poppinpoppies` | 3 | shoot | png |
| 13 | `seapotatomine` | 3 | mine | png |
| 14 | `ailmint` | 0 | support | none |
| 15 | `akee` | 0 | shoot | none |
| 16 | `akee1` | 0 | lob | none |
| 17 | `aloe` | 0 | shoot | none |
| 18 | `aloes` | 0 | support | none |
| 19 | `appeasemint` | 0 | instant | none |
| 20 | `applemortar` | 0 | lob | none |

缺模型的植物一共 275 株（其中 13 株被 deck 引用），补的顺序建议照这张表的次数走：前几株（`potatochip`、`begonia`、`missiletoast`）占了缺模型引用的大头，先把它们做成 actor，比按世界顺序铺开的收益高得多。

（其余 255 株未列出的缺模型植物不影响 1809 关的可玩性，可最后补。）
