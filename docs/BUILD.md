# 构建与素材生成

## 1. 环境

- Windows 10/11 x64（构建 Windows 包）或 macOS 11+（本机运行）
- Python 3.12
- `pip install -r requirements.txt`（pygame-ce、Pillow、numpy）
- 可选：PyInstaller 6.22.3（打 Windows exe）
- 可选：Inno Setup 6（打 Windows 安装程序）
- 可选：FFmpeg、vgmstream-cli（音频转码）
- 可选：Google Chrome（CDP 烘焙 Gardendless 动画）

## 2. 准备原始素材（不随仓库提供）

1. 从 SHUTTLE 官方发布页获取 `PvZ 2 SHUTTLE v26.10.1.apk` 与 `main.460.com.ea.game.pvz2_shu.obb`；
2. 从 Gardendless 网页版（`https://play.pvzge.com/`）准备 CDP 可访问的浏览器；
3. 将 SHUTTLE 素材包解压为 `Renders/`（立绘/世界图），音乐为 `Music/`（可选，OBB 音频已足够）；
4. 将 APK 解出 `lib/arm64-v8a/libPVZ2.so`（仅分析用，不参与运行）。

## 3. 解包 OBB（生成 `work/obb_packages/`）

```bash
python tools/obb/obb_dump.py <obb路径> work/obb_raw
python tools/obb/split_packages.py work/obb_raw work/obb_packages
python tools/obb/rton_convert.py work/obb_raw work/obb_json
```

`obb_dump.py` 依据 1BSR/RSG v4 头字段解压 Zstandard 数据流；
`split_packages.py` 按 4 KiB 对齐切分 `PACKAGES` 组中的 RTON；
`rton_convert.py` 将 RTON 转为 JSON。

## 4. 重建内容（`content/`）

```bash
python tools/obb_build_content_v2.py      # 26 世界 / 1809 关
python tools/add_new_worlds_content.py    # 新植物/僵尸/世界
python tools/build_fusions.py             # 85 融合
python tools/build_shop.py                # 585 商品
python tools/build_garden.py              # 花园
python tools/build_meta_content.py        # 星章/砸罐子/Boss/商店
python tools/validate_all.py
```

## 5. 烘焙动画与美术（`assets/`）

需要 Chrome 打开 `play.pvzge.com` 并开启 CDP（默认 9333 端口）：

```bash
python tools/bake_actors.py --port 9333
python tools/bake_ui.py --port 9333
python tools/import_renders.py
python tools/import_plantagenet.py
python tools/import_missing_worlds.py
python tools/gen_missing_world_art.py
```

## 6. 音频（`assets/audio`）

```bash
python tools/obb/bake_audio.py <OBB路径> assets/audio/obb
```

流程：解析 Wwise BNK → 提取 `.wem` → `vgmstream-cli` 转 WAV → FFmpeg 转 OGG。

## 7. 测试与运行

```bash
python main.py
python main.py --selftest
python tools/validate_all.py
```

## 8. 打包

Windows：

```powershell
.\tools\build_exe.ps1
```

macOS 通用包（Windows 交叉组装，需预下载 python-build-standalone 两套运行时）：

```bash
python packaging/macos/build_mac_app.py
```

安装程序（Windows）：

```bash
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\PvZ2SHUTTLE.iss
```
