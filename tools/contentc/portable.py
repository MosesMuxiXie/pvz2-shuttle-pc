"""可移植路径：产物里只写相对于工作区的 POSIX 路径。

为什么需要：`native/generated/*.json` 是提交进仓库的产物，且 `--check` 逐字节比对。
第一版把 `str(obb_dir)` 原样写进 `sources`，于是产物里嵌了
`D:\\OneDrive\\文档\\pvz_shuttle\\work\\obb_packages`——换一台机器或换个 clone 目录，
同一份数据算出的产物字节就不同，`--check` 必然报「产物过期」，而且泄露本机目录。
这里统一成 `work/obb_packages` / `content/levels` 这样的工作区相对路径；
落在工作区外的路径退化成最后两段（`obb_packages` 之类），保证可读且不含绝对前缀。
"""

from __future__ import annotations

import pathlib
import os

REPO = pathlib.Path(__file__).resolve().parents[2]
WORKSPACE = REPO.parent.parent


def portable(path: os.PathLike[str] | str) -> str:
    """把路径写成工作区相对的 POSIX 串；不在工作区内时退化成最后两段。"""
    resolved = pathlib.Path(path).resolve()
    # 先试仓库相对：``content/levels`` 在任何 clone 里都一样，跟工作区布局无关。
    # 再试工作区相对：开发时 ``work/obb_packages`` 在仓库外的工作区根。
    # 都不在（例如 clone 里把 PVZ2_OBB_DIR 指到别的机器目录）则只留最后两段。
    for base in (REPO, WORKSPACE):
        try:
            return (resolved.relative_to(base)).as_posix()
        except ValueError:
            continue
    parts = resolved.parts
    return pathlib.PurePosixPath(*parts[-2:]).as_posix() if len(parts) >= 2 else resolved.name
