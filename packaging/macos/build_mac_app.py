"""Assemble a universal (Intel + Apple Silicon) macOS .app bundle for PvZ2SHUTTLE.

Runs on Windows: builds the bundle from two per-arch CPython runtimes from
python-build-standalone plus the universal2 pygame-ce wheel, then zips it with
Unix permissions preserved and an installer .command script.

Usage: python work/mac/build_mac_app.py
"""
import os
import plistlib
import shutil
import struct
import sys
import zipfile
from pathlib import Path

MAC = Path(__file__).resolve().parent
PROJECT = MAC.parent.parent / "PvZ2SHUTTLE"
APP_NAME = "PvZ 2 SHUTTLE"
BUNDLE = MAC / "PvZ2SHUTTLE.app"
VERSION = (PROJECT / "VERSION").read_text(encoding="utf-8").strip()

COPY_ITEMS = ["main.py", "game", "assets", "content", "VERSION", "README.md"]


def fresh_dir(p: Path):
    if p.exists():
        shutil.rmtree(p)
    p.mkdir(parents=True)


def copy_app_tree(res: Path):
    app_dir = res / "app"
    fresh_dir(app_dir)
    for item in COPY_ITEMS:
        src = PROJECT / item
        dst = app_dir / item
        if src.is_dir():
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)
    # keep a copy of the engine document for reference
    design = PROJECT / "game" / "DESIGN.md"
    if design.exists():
        shutil.copy2(design, app_dir / "DESIGN.md")


def copy_runtimes(res: Path):
    for arch in ("arm64", "x86_64"):
        src = MAC / f"py-{arch}" / "python"
        dst = res / f"py-{arch}"
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst, symlinks=False)


def copy_pygame(res: Path):
    lib = res / "lib"
    fresh_dir(lib)
    src = MAC / "lib"
    for name in os.listdir(src):
        s = src / name
        d = lib / name
        if s.is_dir():
            shutil.copytree(s, d)
        else:
            shutil.copy2(s, d)


def make_icon(res: Path):
    from PIL import Image

    im = Image.open(PROJECT / "assets" / "ui" / "app_icon.png").convert("RGBA")
    icns = res / "appicon.icns"
    im.save(icns, format="ICNS")
    print("icon:", icns.stat().st_size, "bytes")


def write_launcher(macos: Path):
    script = """#!/bin/bash
# PvZ 2 SHUTTLE — macOS launcher (universal: Apple Silicon + Intel)
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
RES="$(cd "$HERE/../Resources" && pwd)"
ARCH="$(uname -m)"
if [ "$ARCH" = "arm64" ]; then
  PY="$RES/py-arm64/bin/python3.12"
else
  PY="$RES/py-x86_64/bin/python3.12"
fi
if [ ! -x "$PY" ]; then
  /usr/bin/osascript -e 'display alert "PvZ 2 SHUTTLE" message "找不到内置 Python 运行时，请重新解压安装包。" as critical'
  exit 1
fi
cd "$RES/app"
export PYTHONPATH="$RES/lib"
export PYGAME_DETECT_AVX2=1
export PVZ2_SAVE_DIR="$HOME/Library/Application Support/PvZ2SHUTTLE"
exec "$PY" "$RES/app/main.py" "$@"
"""
    p = macos / "PvZ2SHUTTLE"
    p.write_bytes(script.replace("\n", "\r\n").encode("utf-8") if False else script.encode("utf-8"))
    p.chmod(0o755)


def write_plist(contents: Path):
    info = {
        "CFBundleName": "PvZ 2 SHUTTLE",
        "CFBundleDisplayName": APP_NAME,
        "CFBundleIdentifier": "cn.pvz2shuttle.remake",
        "CFBundleExecutable": "PvZ2SHUTTLE",
        "CFBundlePackageType": "APPL",
        "CFBundleSignature": "????",
        "CFBundleVersion": VERSION,
        "CFBundleShortVersionString": VERSION,
        "CFBundleIconFile": "appicon.icns",
        "LSMinimumSystemVersion": "11.0",
        "NSHighResolutionCapable": True,
        "LSApplicationCategoryType": "public.app-category.strategy-games",
        "NSHumanReadableCopyright": "同人复刻，仅供学习交流。PvZ 版权归 EA / PopCap。",
        "LSArchitecturePriority": ["arm64", "x86_64"],
    }
    with open(contents / "Info.plist", "wb") as f:
        plistlib.dump(info, f)
    (contents / "PkgInfo").write_bytes(b"APPL????")


def make_installer_scripts(root: Path):
    install = """#!/bin/bash
# PvZ 2 SHUTTLE macOS 安装脚本
set -e
cd "$(dirname "$0")"
APP="PvZ2SHUTTLE.app"
if [ ! -d "$APP" ]; then
  /usr/bin/osascript -e 'display alert "PvZ 2 SHUTTLE" message "缺少 PvZ2SHUTTLE.app，请把压缩包完整解压后再运行本脚本。" as critical'
  exit 1
fi
DEST="/Applications"
if [ ! -w "$DEST" ]; then
  DEST="$HOME/Applications"
  mkdir -p "$DEST"
fi
echo "正在安装到 $DEST ..."
rm -rf "$DEST/$APP"
cp -R "$APP" "$DEST/"
xattr -dr com.apple.quarantine "$DEST/$APP" 2>/dev/null || true
chmod +x "$DEST/$APP/Contents/MacOS/PvZ2SHUTTLE"
echo ""
echo "安装完成：$DEST/$APP"
echo "首次启动若被系统拦截，请右键点击 App → 打开。"
open "$DEST/$APP"
"""
    uninstall = """#!/bin/bash
# PvZ 2 SHUTTLE macOS 卸载脚本
set -e
for DEST in "/Applications" "$HOME/Applications"; do
  if [ -d "$DEST/PvZ2SHUTTLE.app" ]; then
    rm -rf "$DEST/PvZ2SHUTTLE.app"
    echo "已删除 $DEST/PvZ2SHUTTLE.app"
  fi
done
echo "存档保留在 ~/Library/Application Support/PvZ2SHUTTLE（如需彻底删除请手动移除该目录）。"
"""
    for name, text in (
        ("安装 PvZ 2 SHUTTLE.command", install),
        ("Install PvZ2SHUTTLE.command", install),
        ("卸载 PvZ 2 SHUTTLE.command", uninstall),
        ("Uninstall PvZ2SHUTTLE.command", uninstall),
    ):
        p = root / name
        p.write_bytes(text.encode("utf-8"))
        p.chmod(0o755)

    readme = """PvZ 2 SHUTTLE — macOS 通用版（Intel / Apple Silicon）

本压缩包内是已经配置好 Python 与 pygame 的完整游戏，无需另装任何运行库。

安装方法（推荐）
  1. 把本压缩包完整解压到任意目录（不要直接在压缩包里运行）。
  2. 双击「安装 PvZ 2 SHUTTLE.command」（文件名是中文不便时可双击 Install PvZ2SHUTTLE.command，作用相同）。
     - 若系统提示“无法打开，因为无法验证开发者”，请右键该文件 → 打开。
     - 脚本会把 PvZ2SHUTTLE.app 复制到「应用程序」，移除隔离标记并启动游戏。
  3. 以后从「启动台/应用程序」打开 PvZ 2 SHUTTLE 即可。

不安装直接玩
  直接双击 PvZ2SHUTTLE.app。首次打开若被拦截，请右键 → 打开。

卸载
  双击「卸载 PvZ 2 SHUTTLE.command」，或直接把 PvZ2SHUTTLE.app 拖到废纸篓。
  存档位于 ~/Library/Application Support/PvZ2SHUTTLE/save.json。

架构说明
  应用内含 Apple Silicon（arm64）与 Intel（x86_64）两套 Python 运行时，
  启动脚本用 uname -m 自动选择，因此同一个安装包在两种 Mac 上都能原生运行。
  游戏素材与 pygame 使用 universal2 构建。

系统要求
  macOS 11 Big Sur 或更高版本（Intel / Apple Silicon），约 500 MB 磁盘空间。

版权说明
  同人复刻，仅供学习交流，请勿用于商业用途。PvZ 系列版权归 EA / PopCap 所有。
"""
    (root / "README-macOS.txt").write_text(readme, encoding="utf-8")


# ---------------------------------------------------------------- verification
FAT_MAGIC = 0xCAFEBABE
FAT_MAGIC_64 = 0xCAFEBABF
THIN_64 = 0xFEEDFACF
THIN_32 = 0xFEEDFACE
CPUS = {7: "x86", 0x01000007: "x86_64", 12: "arm", 0x0100000C: "arm64"}


def macho_archs(path: Path):
    with open(path, "rb") as f:
        data = f.read(4 * 1024 * 1024)
    if len(data) < 8:
        return None
    be = struct.unpack_from(">I", data, 0)[0]
    if be in (FAT_MAGIC, FAT_MAGIC_64):
        nfat = struct.unpack_from(">I", data, 4)[0]
        if nfat > 8:
            return None
        off = 8
        out = []
        for _ in range(nfat):
            if be == FAT_MAGIC_64:
                cputype, _sub, _o, _s, _al, _r = struct.unpack_from(">IIQQII", data, off)
                off += 32
            else:
                cputype, _sub, _o, _s, _al = struct.unpack_from(">IIIII", data, off)
                off += 20
            out.append(CPUS.get(cputype, hex(cputype)))
        return "fat", out
    le = struct.unpack_from("<I", data, 0)[0]
    if le in (THIN_64, THIN_32):
        cputype, _sub = struct.unpack_from("<II", data, 4)
        return "thin", [CPUS.get(cputype, hex(cputype))]
    if be in (THIN_64, THIN_32):
        cputype, _sub = struct.unpack_from(">II", data, 4)
        return "thin", [CPUS.get(cputype, hex(cputype))]
    return None


def verify(bundle: Path):
    bad = []
    counts = {"fat": 0, "thin": 0}
    for root, _dirs, files in os.walk(bundle):
        for name in files:
            p = Path(root) / name
            try:
                got = macho_archs(p)
            except Exception:
                continue
            if not got:
                continue
            kind, archs = got
            counts[kind] += 1
            rel = p.relative_to(bundle).as_posix()
            if rel.startswith("Contents/Resources/py-arm64/") and archs != ["arm64"]:
                bad.append(f"{rel}: {archs} (expected arm64)")
            elif rel.startswith("Contents/Resources/py-x86_64/") and archs != ["x86_64"]:
                bad.append(f"{rel}: {archs} (expected x86_64)")
            elif rel.startswith("Contents/Resources/lib/") and kind == "fat" and set(archs) != {"arm64", "x86_64"}:
                bad.append(f"{rel}: {archs}")
    print(f"mach-o files: fat={counts['fat']} thin={counts['thin']}")
    if bad:
        print("ARCH PROBLEMS:")
        for b in bad[:20]:
            print("  ", b)
        raise SystemExit(1)


# ----------------------------------------------------------------------- build
def main():
    zip_only = os.environ.get("MAC_ZIP_ONLY") == "1" and BUNDLE.exists()
    if not zip_only:
        fresh_dir(BUNDLE)
        contents = BUNDLE / "Contents"
        macos = contents / "MacOS"
        res = contents / "Resources"
        for d in (macos, res):
            d.mkdir(parents=True)

        print("copying game tree ...")
        copy_app_tree(res)
        print("copying runtimes ...")
        copy_runtimes(res)
        print("copying pygame ...")
        copy_pygame(res)
        print("icon ...")
        make_icon(res)
        write_launcher(macos)
        write_plist(contents)
        make_installer_scripts(MAC)
    else:
        print("zip-only mode: reusing existing bundle")
        make_installer_scripts(MAC)

    print("verifying architectures ...")
    verify(BUNDLE)

    app_size = sum(p.stat().st_size for p in BUNDLE.rglob("*") if p.is_file())
    print(f"bundle size: {app_size / 1e6:.1f} MB")

    # zip with Unix permissions
    zip_path = MAC / f"PvZ2SHUTTLE-{VERSION}-macOS-universal.zip"
    if zip_path.exists():
        zip_path.unlink()
    exec_ext = {".command", ".sh", ".dylib", ".so", ".a", ".pyd"}
    n = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        def add(path: Path, arcname: str, mode: int):
            nonlocal n
            is_dir = path.is_dir()
            info = zipfile.ZipInfo(arcname)
            info.create_system = 3  # unix
            info.external_attr = (mode << 16) | (0x10 if is_dir else 0)
            info.compress_type = zipfile.ZIP_DEFLATED
            if is_dir:
                z.writestr(info, b"")
            else:
                with open(path, "rb") as f:
                    z.writestr(info, f.read())
            n += 1

        add(MAC / "README-macOS.txt", "README-macOS.txt", 0o100644)
        for script in ("安装 PvZ 2 SHUTTLE.command", "Install PvZ2SHUTTLE.command",
                       "卸载 PvZ 2 SHUTTLE.command", "Uninstall PvZ2SHUTTLE.command"):
            add(MAC / script, script, 0o100755)

        def walk(dirp: Path, arcbase: str):
            add(dirp, arcbase + "/", 0o040755)
            for child in sorted(dirp.iterdir(), key=lambda p: p.name):
                arc = arcbase + "/" + child.name
                if child.is_dir():
                    walk(child, arc)
                else:
                    mode = 0o100755 if child.suffix in exec_ext else 0o100644
                    posix = child.as_posix()
                    if child.name == "python3.12" or "/bin/" in posix or "/Contents/MacOS/" in posix:
                        mode = 0o100755
                    # python3.12 binary files under bin/ and any executable script
                    add(child, arc, mode)

        walk(BUNDLE, "PvZ2SHUTTLE.app")
    print(f"zip: {zip_path.name} {zip_path.stat().st_size / 1e6:.1f} MB, {n} entries")


if __name__ == "__main__":
    main()
