# OBB 解包流水线

SHUTTLE 的 OBB 是 PopCap RSB（`1bsr`）容器，内部资源组为 RSG（`pgsr`）v4，
数据流使用 **Zstandard** 压缩（不是旧版的 zlib）。

| 脚本 | 作用 |
| --- | --- |
| `obb_dump.py` | 解析 1BSR 头/子组表，按索引解压每个 RSG 的 data/image 流到 `work/obb_raw/<idx>_<name>/` |
| `split_packages.py` | 将 `0684_PACKAGES` 的 data 流按 4 KiB 对齐的 `RTON` 魔数切分为独立包 |
| `rton_convert.py` | 解码 RTON（跳过 4 字节 `RTON` 魔数；版本号在对象内部） |
| `bake_audio.py` | 解析 Wwise BNK（BKHD/DIDX/DATA），提取 WEM，调用 vgmstream/FFmpeg 转 OGG |
| `verify_full_levels.py` | 校验 1809 个关卡的波次/卡组/标题完整性 |

注意：本目录脚本是根据公开格式资料独立实现的，未包含 pyvz2（GPL-3.0）源码。
