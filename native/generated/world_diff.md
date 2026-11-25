# 世界差异（OBB WorldData ↔ content/worlds.json）
- WorldData 条目：46；client 世界：26；已匹配：22
- 事件总数：costume=7，doodad=6，giftbox=8，key_gate=27，level=1248，plant=231，star_gate=53，upgrade=2，worldgate=17
- 门（star_gate/key_gate/worldgate）：97 条

## 已匹配

| client | OBB 名称 | 关卡事件 | 星门 | 钥匙门 | 世界门 | 地图件 |
| --- | --- | --- | --- | --- | --- | --- |
| beach | beach | 23 | 2 | 3 | 0 | 203 |
| carnival | carnival | 32 | 1 | 0 | 0 | 120 |
| chinesegarden | chinesegarden | 26 | 1 | 0 | 0 | 170 |
| cowboy | cowboy | 24 | 1 | 0 | 0 | 111 |
| dark | dark | 24 | 1 | 0 | 0 | 125 |
| dino | dino | 23 | 1 | 0 | 0 | 366 |
| egypt | egypt | 26 | 0 | 0 | 0 | 201 |
| eighties | eighties | 26 | 1 | 0 | 0 | 186 |
| fairy | fairy | 26 | 1 | 0 | 0 | 79 |
| heian | heian | 25 | 1 | 0 | 0 | 138 |
| kongfu | kongfu | 25 | 2 | 5 | 1 | 54 |
| losantosvice | gta | 15 | 2 | 4 | 0 | 100 |
| lostcity | lostcity | 38 | 2 | 0 | 0 | 347 |
| lunarrainbowmarket | rainbowmarket | 31 | 1 | 0 | 0 | 1 |
| mausoleum | mausoleum | 32 | 1 | 0 | 0 | 97 |
| memorytour | memorytour | 1 | 1 | 0 | 0 | 1 |
| modern | modern | 13 | 1 | 0 | 0 | 185 |
| muji | muji | 29 | 1 | 0 | 0 | 0 |
| pirate | pirate | 27 | 2 | 4 | 0 | 121 |
| plantagenet | plantagenet | 21 | 1 | 0 | 0 | 127 |
| sky | skycity | 35 | 2 | 0 | 0 | 88 |
| steam | steam | 33 | 1 | 0 | 0 | 123 |

## client 有、WorldData 无（依赖合成关卡）

| client | 名称 | 关卡 | 说明 |
| --- | --- | --- | --- |
| frontyard | 前院 | 175 | 前院：由 tutorial + yourhouse 合并而来 |
| future | 未来世界 | 71 | 未来世界：本版 WorldData 无对应条目，关卡为合成 |
| iceage | 冰河世界 | 72 | 冰河世界：本版 WorldData 无对应条目，关卡为合成 |
| renai | 恋爱剧场 | 59 | 恋爱剧场：本版 WorldData 无对应条目，关卡为合成 |

## WorldData 有、client 未接（事件/变体世界）

| OBB 名称 | worldId | 关卡事件 | 星门 | 钥匙门 | 世界门 | 地图件 |
| --- | --- | --- | --- | --- | --- | --- |
| tutorial | 1 | 6 | 1 | 0 | 0 | 12 |
| yourhouse | 78 | 2 | 1 | 0 | 0 | 0 |
| yourhousex | 79 | 50 | 1 | 0 | 1 | 55 |
| kungfu | 80 | 25 | 1 | 0 | 0 | 74 |
| secondanniversary | 82 | 10 | 1 | 0 | 0 | 93 |
| thirdanniversary | 83 | 30 | 2 | 5 | 0 | 182 |
| fourthanniversary | 84 | 30 | 2 | 4 | 0 | 137 |
| epicquest | 85 | 154 | 1 | 0 | 0 | 1 |
| tower | 86 | 100 | 1 | 0 | 0 | 106 |
| thymedevent | 89 | 1 | 1 | 0 | 15 | 1 |
| lny | 90 | 30 | 1 | 0 | 0 | 37 |
| fifthanniversary | 91 | 22 | 1 | 0 | 0 | 196 |
| collab1 | 92 | 20 | 1 | 0 | 0 | 237 |
| collab2 | 93 | 15 | 1 | 0 | 0 | 18 |
| funtime | 94 | 31 | 1 | 0 | 0 | 210 |
| sixthanniversary | 95 | 30 | 1 | 2 | 0 | 58 |
| aprilfools | 97 | 25 | 1 | 0 | 0 | 27 |
| cerydra | 98 | 10 | 1 | 0 | 0 | 2 |
| hysilens | 99 | 10 | 1 | 0 | 0 | 2 |
| atlantis | 100 | 25 | 1 | 0 | 0 | 130 |
| firefly | 101 | 10 | 1 | 0 | 0 | 2 |
| tes12 | 102 | 12 | 1 | 0 | 0 | 49 |
| tes13 | 103 | 25 | 1 | 0 | 0 | 32 |
| element | 104 | 20 | 1 | 0 | 0 | 237 |

## 门与来源（前 40 条）

| OBB 名称 | 类型 | unlockedFrom |
| --- | --- | --- |
| tutorial | star_gate |  |
| cowboy | star_gate |  |
| beach | star_gate |  |
| beach | star_gate | beach_level_16 |
| beach | key_gate |  |
| beach | key_gate |  |
| beach | key_gate |  |
| eighties | star_gate |  |
| dino | star_gate |  |
| dark | star_gate |  |
| modern | star_gate |  |
| heian | star_gate |  |
| plantagenet | star_gate |  |
| skycity | star_gate |  |
| skycity | star_gate | skycity_level_8 |
| kongfu | key_gate |  |
| kongfu | key_gate |  |
| kongfu | worldgate |  |
| kongfu | key_gate |  |
| kongfu | key_gate |  |
| kongfu | key_gate |  |
| kongfu | star_gate |  |
| kongfu | star_gate | kongfu_level_8 |
| steam | star_gate |  |
| muji | star_gate |  |
| memorytour | star_gate |  |
| fairy | star_gate |  |
| pirate | key_gate |  |
| pirate | key_gate |  |
| pirate | key_gate |  |
| pirate | key_gate |  |
| pirate | star_gate |  |
| pirate | star_gate | pirate_level_10 |
| lostcity | star_gate |  |
| lostcity | star_gate | lostcity_level_16 |
| carnival | star_gate |  |
| yourhouse | star_gate |  |
| yourhousex | worldgate |  |
| yourhousex | star_gate | yourhouse_revenge |
| kungfu | star_gate | kongfu_level_boss |

（其余 57 条略）
