# -*- coding: utf-8 -*-
"""S7 packaging, step 1: install rules, a single version source and an asset-root override.

Everything here mirrors `docs/superpowers/plans/2026-11-24-packaging.md` items 1-5. The
install tree is what `tools/package.ps1` zips, and gate 2 runs the four commands from a
directory that has neither the source tree nor the build tree next to it.
"""
from __future__ import annotations

import io
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]


def patch(rel: str, old: str, new: str) -> None:
    p = ROOT / rel
    text = io.open(p, encoding="utf-8").read()
    if new in text:
        print("skip", rel)
        return
    assert old in text, (rel, old[:60])
    io.open(p, "w", encoding="utf-8", newline="\n").write(text.replace(old, new, 1))
    print("patched", rel)


# 1) version reaches the binary -------------------------------------------------
patch(
    "native/CMakeLists.txt",
    "target_link_libraries(PvZ2SHUTTLE PRIVATE pvz_launcher)",
    "target_link_libraries(PvZ2SHUTTLE PRIVATE pvz_launcher)\n"
    "target_compile_definitions(PvZ2SHUTTLE PRIVATE PVZ_VERSION=\"${PROJECT_VERSION}\")",
)

# 2) install rules -------------------------------------------------------------
patch(
    "native/CMakeLists.txt",
    "target_compile_definitions(PvZ2SHUTTLE PRIVATE PVZ_ENABLE_DESKTOP=1)",
    "target_compile_definitions(PvZ2SHUTTLE PRIVATE PVZ_ENABLE_DESKTOP=1)\n"
    "\n"
    "# S7: the install tree is exactly what `tools/package.ps1` zips, so it has to be a tree\n"
    "# that runs on a machine with no source checkout next to it. Assets come from the\n"
    "# workspace root (`PvZ2SHUTTLE/assets`), generated JSON is runtime data and ships too.\n"
    "install(TARGETS PvZ2SHUTTLE RUNTIME DESTINATION .)\n"
    "set(PVZ_ASSET_SOURCE \"${CMAKE_CURRENT_SOURCE_DIR}/../PvZ2SHUTTLE/assets\")\n"
    "if(EXISTS \"${PVZ_ASSET_SOURCE}\")\n"
    "    install(DIRECTORY \"${PVZ_ASSET_SOURCE}/\" DESTINATION assets)\n"
    "else()\n"
    "    message(WARNING \"S7: ${PVZ_ASSET_SOURCE} is missing; the install tree will have no assets\")\n"
    "endif()\n"
    "install(DIRECTORY \"${CMAKE_CURRENT_SOURCE_DIR}/generated/\" DESTINATION generated FILES_MATCHING PATTERN \"*.json\")\n"
    "install(FILES \"${CMAKE_CURRENT_SOURCE_DIR}/../docs/PROGRESS.md\" DESTINATION . RENAME PROGRESS.md OPTIONAL)\n"
    "install(FILES \"${CMAKE_CURRENT_SOURCE_DIR}/../README.md\" DESTINATION . OPTIONAL)",
)
print("done")
