# 世界门数据（world_gates.json）：字段口径与分布

generated=sha256:b1f61cd5ef86dedb；source=work/obb_packages/pkg_2107_WorldData.json

门总数 97：star_gate 53、key_gate 27、worldgate 17。

## 一、字段口径

- `stars`：只有 `star_gate` 有值，取自 `m_cost`；**`0` 表示免费**，`null` 表示原表没写。
- `keys`：只有 `key_gate` 有值，取自 `m_cost`（钥匙数 1/3/4/5）；其它 kind 一律 `null`。
- 两个字段互斥：`keys` 与 `stars` 不会同时有值；缺值写 `null` 而不是 `0`，S6 判定时把 `null` 当「不设门槛」，把 `0` 当「门槛为 0」。
- `world` 是 WorldData 的 `m_worldName` 原值；`worldClient` 用 `ALIASES` 归一后的 client id，未收录的原样返回。`target`/`targetClient` 同理（`target` 为 `null` 时 `targetClient` 也是 `null`）。
- `raw` 是 `m_eventList` 里的原始事件对象，未删字段；上面的字段都是它的投影。

## 二、三类门字段表

| kind | 条数 | world 有值 | worldClient 有值 | target 有值 | targetClient 有值 | stars 有值 | stars=null | keys 有值 | keys=null |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `star_gate` | 53 | 53 | 53 | 22 | 22 | 35 | 18 | 0 | 53 |
| `key_gate` | 27 | 27 | 27 | 0 | 0 | 0 | 27 | 27 | 0 |
| `worldgate` | 17 | 17 | 17 | 17 | 17 | 0 | 17 | 0 | 17 |

## 三、`ALIASES` 命中（按 `world` 统计）

| 原始 world | client id | 门数 |
| --- | --- | --- |
| `gta` | `losantosvice` | 6 |
| `kungfu` | `kongfu` | 1 |
| `rainbowmarket` | `lunarrainbowmarket` | 1 |
| `skycity` | `sky` | 2 |
| （未命中别名的世界） | — | 87 |

## 四、钥匙数分布（key_gate 的 `m_cost`）

| keys | 条数 |
| --- | --- |
| `1` | 2 |
| `3` | 7 |
| `4` | 13 |
| `5` | 5 |

## 五、零门世界

WorldData 共 46 个世界，其中 1 个没有任何门事件：

`egypt`

其余 45 个世界有门；`egypt` 也在零门名单里——它只有 level/plant 事件，不是导出漏项。

## 六、复现

```powershell
python tools/contentc/worlds.py
```

所有计数现场计算；`generated` 取 `pkg_2107_WorldData.json` 的 mtime（UTC ISO8601），不用墙钟，因此两次运行字节一致。
