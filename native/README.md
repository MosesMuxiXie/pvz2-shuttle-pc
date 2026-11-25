# Native client — foundation and first-level mechanics preview

**Status: development preview, not the complete SHUTTLE replica or a replacement release.**
The existing Python game, assets, save and installers are unchanged. This directory implements
the first stages of the approved native rebuild. Executables do not use Python, Android,
APK shared libraries, or network services at runtime.

## What works

- C++20 / MSVC Windows x64 build, with independent headless and desktop configurations.
- Strict reading of all 26 worlds, 147 plants, 55 zombies and 1,809 local level records.
  Counts distinguish 1,646 `obb`, 163 `obb-synth`, 45 vasebreaker flags and 42 overlapping
  synthesized vasebreaker records. These are **catalog coverage**, not implemented gameplay.
- Path-qualified JSON/type/range/duplicate/reference errors; stable IDs, raw definitions and
  source metadata retained. Unicode paths work at the CLI, JSON loader, PNG loader and importer.
- SDL3 launcher artwork at a 1280×720 logical viewport, resize/letterbox/close, CPU render tests.
- A small DragonBones 5.5 runtime: parses `skeleton.json`/`atlas.json`, evaluates bone translate/
  rotate/scale timelines with linear/step/cubic-bezier easing, resolves skin displays and draws
  textured quads through `SDL_RenderTextureAffine`. Models are cached per armature, and failures
  are cached too, so one missing model cannot abort a frame.
- FreeType text with the bundled `ui/font_zh.ttc`, memory-loaded (non-ANSI paths work), streamed
  into a 1024×1024 glyph atlas, used for the Chinese HUD (names, costs, cooldown seconds, help).
- A playable **frontyard_1 mechanics preview**, fixed four-card deck and original starting sun:
  sunflower, peashooter, wallnut, potato mine; basic/armored zombies; cooldowns, sun collection,
  projectile hits, armor, eating, shovel, single-use mowers, win/loss, pause and retry.
- Fixed 60 Hz simulation; seeded event traces and state comparison at 30/60/120 display Hz.
  A legal-input regression clears the unmodified first level; an idle replay loses.
- Read-only migration of Python v2/v3 saves into a separate versioned native file; exact source
  backup, injected garden clock, unknown fields preserved, no-overwrite atomic creation.

## Build on Windows

Requirements: Visual Studio 2022 **Desktop development with C++**, Windows SDK and CMake 3.24+.
The helper locates Visual Studio's bundled CMake if it is not on PATH:

```powershell
.\tools\build_native.ps1 -AuditOnly
.\tools\build_native.ps1
.\native\run-preview.ps1
.\native\run-preview.ps1 -Launcher
```

`run-preview.ps1` defaults to the existing local `../../PvZ2SHUTTLE/assets` tree relative to
this repository. Override with `-Assets 'D:\my assets'`. No assets are copied or redistributed.
A clean configure downloads SHA-256-pinned source archives for nlohmann/json 3.12.0, SDL 3.2.28,
SDL_image 3.2.4 and FreeType 2.13.3. SDL/image are static; PNG/JPEG decoding uses the bundled stb
backend, and FreeType is built without zlib/bzip2/png/harfbuzz/brotli.
MSVC's normal C/C++ runtime dependency remains; this is not yet a portable release package.

Equivalent headless commands (no SDL dependencies or artwork needed):

```powershell
cmake -S native -B build/native -A x64 -DPVZ_ENABLE_DESKTOP=OFF
cmake --build build/native --config Release
ctest --test-dir build/native -C Release --output-on-failure
.\build\native\Release\PvZ2SHUTTLE.exe --audit-content .\content
.\build\native\Release\PvZ2SHUTTLE.exe --simulate .\content
```

Desktop build:

```powershell
cmake -S native -B build/native-desktop -A x64 -DPVZ_ENABLE_DESKTOP=ON
cmake --build build/native-desktop --config Release
ctest --test-dir build/native-desktop -C Release --output-on-failure
.\build\native-desktop\Release\PvZ2SHUTTLE.exe --play .\content '..\..\PvZ2SHUTTLE\assets'
.\build\native-desktop\Release\PvZ2SHUTTLE.exe --launcher-smoke '..\..\PvZ2SHUTTLE\assets'
.\build\native-desktop\Release\PvZ2SHUTTLE.exe --launcher-snapshot '..\..\PvZ2SHUTTLE\assets' .\build\launcher.bmp
.\build\native-desktop\Release\PvZ2SHUTTLE.exe --battle-snapshot .\content '..\..\PvZ2SHUTTLE\assets' .\build\battle.bmp
```

Smoke/snapshot modes use an SDL software renderer without opening a display. Desktop mode
uses an actual resizable window. `--simulate` emits JSON state and events for an idle seeded
first-level run. It is not a replay of an observed Android session.

## Controls

- Start button / Space: start the fixed-deck first level.
- Click seed card or 1–4, then click a grid square: plant.
- Click a sun: collect. S / Shovel: remove a plant (no refund).
- Space / Pause: pause/resume. Losing focus also pauses.
- Right-click / Escape: cancel the current tool. R: reset to start screen.
- Window close / Alt+F4: exit. Battles do **not** write progress or grant rewards yet.

## Safe old-save import

```powershell
.\build\native\Release\PvZ2SHUTTLE.exe --import-python-save 'D:\old game\save.json' 'D:\new profile\native.json'
.\build\native\Release\PvZ2SHUTTLE.exe --audit-save 'D:\new profile\native.json'
```

The output parent directory must already exist. Import creates `native.json.legacy.json`
containing the **exact original bytes**, then atomically installs `native.json`. Existing
source/destination/backup files are never replaced. Invalid JSON, unsupported versions or
invalid progress fields fail loudly, not by resetting progress. If final installation fails,
the recovery backup is kept. Versionless legacy files are interpreted as Python v2. Unknown
progress/settings/plant IDs are preserved, not discarded. Counters must be JSON integers;
malformed string counters are intentionally rejected. This importer is not Android-save support
and is not yet wired into playable progress/rewards. Always keep your own original backup.

## Known gaps / deliberate non-parity

- Launcher is an artwork viewer, not the original interactive launcher.
- Combat uses real DragonBones models for the four starter plants, the basic zombie and its
  cone/bucket armor, plus a Chinese HUD; the other 143 plants and 51 zombie types, plant-food
  effects and sound are not wired yet. Fixed deck, not full seed chooser.
- Preview waves use exactly the catalog spawns. Python's random 2–3× flag-wave multiplier is
  an unverified approximation and is deliberately not treated as an original APK rule.
- Sun timing, random generator, unit geometry and combat constants still need Android footage
  calibration. The seeded generator is stable within this implementation, not Python RNG parity.
- Only the first-level subset is exposed. Unsupported worlds/plants/zombies and Boss, night,
  minecart, vasebreaker or synthesized modes are rejected, not silently substituted.
- No world navigation, rewards, campaign save writes, bosses, elements, shop/garden UI, online
  services or native installers. Catalog loading does not imply these systems exist.
- Windows x64 was built/tested locally. macOS source/build paths remain **unverified**; no
  Universal 2 binary or DMG is claimed. Windows 10 minimum-version behavior also needs a runner.

Test detail and next work: `../docs/NATIVE_PROGRESS.md`.
