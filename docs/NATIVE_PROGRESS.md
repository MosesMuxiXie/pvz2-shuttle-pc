# Native rebuild progress — 2026-11-17

## Scope and truthfulness

Continues the approved 2026-11-10 design in `superpowers/specs/2026-11-10-native-client-design.md`.
The existing Python release is untouched. **The full replica is not finished.** New implementation
is isolated in `native/`; progress here is evidence of working components, not APK parity.
No original Android gameplay recording was obtained in this session; macOS was not available.

## Delivered

| Area | Implemented | Verification / remaining gap |
|---|---|---|
| Catalog | typed registries, waves, raw metadata, source/mode counts | complete local catalog; malformed fixtures; missing/duplicate IDs and references; Unicode paths |
| Build | C++20, CMake, CTest, pinned dependencies, Windows helper | MSVC 19.44, Windows SDK 10.0.26100; audit-only and desktop Release builds |
| Launcher | PNG loading, logical viewport, resizable window, close, snapshots | independent 4×2 PNG color test, letterboxing, corrupt/missing art, real local launcher image |
| Simulation | 60 Hz ticks, seeded RNG, action/events, economy and first-deck combat | 30/60/120 Hz same state/events; armor, collision, mines, eating, pause, cooldown, shovel, mowers, win/loss |
| First level | fixed four-card start → combat → win/loss → retry | unmodified `frontyard_1` legal-action policy wins at tick 10,799; idle replay loses |
| Artwork | reusable asset cache, FreeType Chinese text, DragonBones runtime | real models for the four starter plants, basic zombie and cone/bucket gear; shared 12-armature zombie skeleton |
| Desktop preview | lawn texture, real DragonBones actors, Chinese HUD, mouse/keys, focus-loss pause | software-rendered fixture and real Windows window start/failure/retry/close |
| Save import | Python v2/v3 → native envelope v1, unknown fields, garden migration | exact backup/source-byte tests, Unicode, mature-time boundary, no-overwrite and malformed input tests |

## Evidence and reproducible checks

- `tools/build_native.ps1 -AuditOnly`: build plus CTest without SDL/artwork.
- `tools/build_native.ps1`: build plus CTest with SDL/software-rendered fixtures.
- `catalog_test` checks real counts and temporary malformed fixtures, not just a total count.
- `simulation_test` checks legal-input victory as well as defeat and frame-rate-independent events.
- `save_test` writes **only temporary fixtures under the build directory**.
- `launcher_test` renders an independently generated CC0 four-color PNG and checks frame pixels;
  linear filtering allows a tolerance of 2 channel values. It does not require proprietary art.
- Local generated images: `build/native-desktop/launcher.png`, `battle.png`; logs and CTest
  results remain under ignored `build/`. They are not bundled or uploaded.
- Checked-in preview from the real asset set: `docs/media/battle-preview.png` (1,280×720 software
  frame: four starter plants, one walking zombie, Chinese HUD, drawn seed packets).
- Real CLI content audit: 26 worlds / 147 plants / 55 zombies / 1,809 levels;
  `original=1646`, `synthesized=163`, `vasebreaker=45`, overlap=42.

## Final local verification

- Audit-only Release: **7/7 CTest cases passed**.
- Desktop Release: **12/12 CTest cases passed** (the previous nine plus `dragonbones`, `assets`,
  `text_render`), including an 1,800-tick battle render with real artwork.
- Final real-asset launcher and battle snapshots regenerated and inspected.
- Idle first-level replay: `lost` at tick 7,988; legal-input victory: tick 10,799.
- The existing local Python `save.json` was also imported into an ignored build-test directory. Original-file SHA-256 remained unchanged, and the backup SHA-256 matched the original. No production save was replaced.
- Final project compilation emitted no compiler warnings; Git whitespace check passed.

## Artwork milestone notes (2026-11-17)

- DragonBones 5.5 skeletons in `assets/db` store a plain rotation as equal `skX`/`skY`; the
  official `rotation + skew` shear corrupts them (sunflower head/face cancel at ±91°). The native
  reader therefore treats the two JSON fields as x-axis and y-axis angles: `a/b` come from `skY`,
  `c/d` from `skX`.
- Animation channels are *added* to the setup transform (`translateFrame` offsets, `rotateFrame`
  deltas, `scaleFrame` multipliers); treating them as replacements collapses every Walk cycle.
- Sprites are anchored bottom-left with y up, matching `Transform.toMatrix` placement; this put
  faces back on the sunflower heads and stopped the zombie from splitting apart.
- `BasicZOMBIE` is a shared 12-armature skeleton (Cone/Bucket/FlagZombie/DuckyTube/…); armor is
  drawn by selecting the `Cone`/`Bucket` armature and following its `cone` bone onto the zombie's
  `head` bone. There is no `assets/db/armors` directory — armor art lives in that atlas.
- FreeType cannot open a font path containing non-ANSI characters, so the font is loaded from
  memory (`FT_New_Memory_Face`), and the first TTC face covering both U+4E2D and `A` is used.
- `ui/seedpacket.png` is finished art for one specific plant, not a blank frame; the HUD draws its
  own packet rims instead of stretching that bitmap.

## Important schema findings (do not “fix” by corrupting the source data)

1. One plant uses integer `pierce=0`; remaining records use booleans. Allow only 0/1 integers
   or boolean, not general truthiness.
2. `plantfood` is either a boolean or a skill string, including an empty string for no skill.
3. `extra.boss_zombie` is an original OBB codename such as `zomboss`, **not** a local zombie
   registry reference. Preserve it; actual wave zombie IDs are strictly validated.
4. Dynamic dimensions use `extra.board_rows` / `extra.board_cols`, matching the Python reader.
5. Retain all `extra` properties, including unknown future rules. Loading them is not implementing them.
6. SDL's generated precompiled-header includes broke the local VS/CMake build in the Chinese
   workspace path. The SDL static target disables PCH on MSVC; dependency source is unmodified.

## Mechanics comparison ledger

| Feature | Current behavior | Parity status |
|---|---|---|
| Level start | 150 sun, sunflower/peashooter/wallnut/potatomine, 7 waves | from checked-in first-level JSON |
| Waves | cumulative catalog delays; exact listed spawns, no added flag multiplier | differs from Python's unverified random multiplier; APK evidence pending |
| Sun | first sky sun 4.5 s, then 8 s; sunflower first 6 s then data interval | approximation; no sun-fall animation; exact timing needs footage |
| Projectiles / armor | swept same-row hit, armor before health, nearest target | regression tested; APK hitboxes/timings pending |
| Mine | data-defined arming delay/damage, same-row blast ignoring armor | regression tested; complete original area/animations pending |
| Mower | one per lane, trigger/run/spent, then breach fails | regression tested; physical dimensions/speed need footage |
| Rewards | none, no battle save writes | intentionally disabled until original reward/unlock rules are known |
| Visual/audio | original lawn art, real DragonBones actors for the deck plants and basic/armored zombies, FreeType Chinese HUD | closer, not parity: no plant-food/rare animations, no audio, no projectile rotation, world map still absent |

## Next implementation sequence

1. ~~Introduce reusable native asset cache, Chinese text rendering and actual DragonBones models
   for the first four plants and basic/armored zombies; replace debug actors/HUD.~~ **Done 2026-11-17.**
   Follow-up polish: plant-food animations, projectile arcs, sun-fall motion, eating/shooting state
   animation switching, and the remaining 143 plant / 51 zombie models.
2. Implement seed chooser, navigation and result screen, and connect native profiles through
   explicit tested save transactions (do not infer rewards from the old generic fallback).
3. Extend action replay to JSON input scripts with checkpoints and compare with recorded APK
   timing. Add resize, UI planting/collecting and focus-loss end-to-end checks.
4. Recover/classify original rules for the 163 synthesized records; build a mechanic coverage
   matrix before exposing more worlds. Implement elements, stage modules, specials and bosses.
5. Migrate world map, progression, almanac, shop, garden, fusion and settings, then verified
   online services with certificate verification and offline/error behavior.
6. Run Windows minimum-version and macOS dual-architecture CI/hardware validation; only then
   produce native installers/DMG and switch release entry points.

No Git commit/push or release publication was performed for this development increment.

## S0 + S1 landed (2026-11-20)

The plan is `docs/superpowers/plans/2026-11-20-full-native-replica.md`. Stages S0
(baseline and gates) and S1 (content compiler) are complete and verified:

- **S0.1 baseline**: `docs/PARITY_BASELINE.md` records the build matrix, the content audit,
  the sheet-scale table and the worktree state, so every later stage has something to
  compare against.
- **S0.3 probes removed**: `work/probe_sheets*.py` and friends are gone; `tools/contentc/`
  replaced them. Early OBB-unpacking research probes stay.
- **S0.4 gate**: `pwsh -File tools/check_all.ps1 [-Desktop] [-NoContent] [-AllowMatrixChange]`
  runs content regeneration (`--check`), the audit build + CTest, the 17 Python tool tests,
  the parity matrix and the world diff, then prints `[ok]`/`[fail]` and exits 0/1.
- **S1.2 loader**: `native/src/content/{model.hpp,loader.hpp,loader.cpp}` read the pack with
  strict per-field errors that name the offending entry, keep unknown action kinds instead of
  refusing the run, and record duplicate ids rather than collapsing them.
- **S1.3 compiler**: `tools/contentc/` emits `native/generated/content.pack`
  (`plants=339 zombies=1127 plantActions=668`) deterministically; `--check` pins the counts,
  the 3 dangling references and the exact bytes.
- **S1.4 wiring**: `loadCatalog(content, CatalogOptions{contentPack})` exposes the pack as
  `Catalog::rules` and reports `rules=pack …` / `rules=json (fallback: …)`; the JSON registries
  still drive decks, worlds and levels until the id mapping exists.
- **S1.5 worlds**: `tools/contentc/worlds.py` diffs the 46 WorldData entries against the 26
  client worlds (22 matched, 97 gates: 53 star / 27 key / 17 world) into
  `native/generated/world_diff.md`, pinned by `tools/tests/test_worlds.py`.

Verified: audit **8/8**, desktop **13/13**, Python tools **17/17**, `check_all.ps1` exit 0.

Known data facts that S3 must respect: the pack and `content/*.json` share only 44 plant and
20 zombie ids; 103 client plant ids do not exist in this build's sheets at all. The mapping has
to be an explicit table, not a normalisation rule.

## S2 landed (2026-11-20): data-driven engine

- **`native/src/engine/`** is the new kernel: `world.cpp` owns entities, sun, eating, mowers and
  outcome; `director.cpp` flattens a level's waves into a tick schedule; `registry.cpp` maps the
  eleven plant behaviour families (`shoot, lob, produce, wall, instant, mine, chomp, fume,
  boomerang, support, spike`) and six zombie families (`walk, jump, steal, summon, gargantuar,
  fly`) onto functions; `action_runner.cpp` walks a plant's pack actions; `projectile.cpp` steps
  shots with splash/slow/pierce; `replay.cpp` turns a JSON input script into ticks.
- The four-plant whitelist and the `frontyard` gate in `simulation.cpp` are gone from the new
  path: `--run-level` runs any of the 1809 levels with `--pack` rules, `--script` inputs and
  `--rows/--cols` board overrides. `--simulate` still exercises the old `Battle` for the
  desktop slice until S4 migrates the view.
- **Determinism**: 60 Hz fixed step only; `hash()` is FNV-1a over quantised entity fields.
  Same seed and script give the same hash across runs, and chunked `advance()` reaches the same
  tick and hash as one big advance. Different seeds do *not* change a run yet because every
  shipped spawn names its row — the seed is carried and reported, and becomes behaviour when
  random row selection lands.
- **Gates**: audit **9/9** (new `engine` test), desktop **14/14**, Python tools **17/17**,
  `tools/check_all.ps1` exit 0 with the new smoke step. `tools/engine_smoke.py` runs five fixed
  scenarios twice through the CLI and records hashes in `native/generated/engine_smoke.json`;
  `check_all` fails when that file moves.
- **Scope honesty**: all smoke scenarios end `lost` because nobody plants anything (or, in the
  scripted one, because seven peashooters cannot stop the last flag waves). That is the expected
  S2 baseline — S2 proves the kernel runs and stays deterministic, not that a level is winnable.
  Kill/sun/board numbers are recorded so S4 has something to calibrate against.

Next: **S3** — map the 339 pack plants and 1127 pack zombies onto the 147/55 client ids,
  then grow each behaviour family from its packed actions (`Actions.Type` 410 projectile /
  200 special / 33 explode / 16 sun / 6 plantfood) and derive per-world board geometry from
  `WorldData` (no level currently carries `rows`/`cols`, so every level defaults to 5×9).

## S2 defect round (2026-11-20 20:40): audit findings closed

The S2 kernel was audited read-only (`docs/reviews/2026-11-20-s2-audit.md`, 19 findings) and the
fixes are tracked one-by-one in `docs/reviews/2026-11-20-audit-fixes.md`. What changed:

- **Blocker B1 — jumpers were unbeatable.** Landing was to the *right* of the plant while zombies
  walk left, so a pole vaulter re-jumped forever; `tickZombies` also excluded `jump` from eating.
  Now it lands on the left, eats normally, and has a 2 s cooldown.
- **Deck, mower and spawn rules.** `World::plant` honours `level.deck` (`not-in-deck`) and
  `kMaxPlants`; the mower starts at `kMowerTriggerX` and defeat is any breach past `kLoseX` with
  the mower spent (previously a driving mower let a second zombie through for free).
- **Spawns from behaviours no longer reallocate the zombie vector.** `zombieSummon` queues into
  `pendingSpawns_`, flushed after the iteration.
- **Counters mean one thing each.** `removed` (despawn) no longer inflates `killed`; mower kills and
  leaks are separate; rejected wave spawns are counted and emitted (`wave_spawn_rejected`).
- **Determinism inputs widened.** `hash()` also covers `actionTimer`, `skySunTimer_`,
  `firstSkySunSpawned_`, `sun.expires`, `shot.pierce/splash/slow/owner`, `zombie.speed/family/deathTick`.
- **Time and chill.** `advance()` rejects NaN/Inf/negative/>86400 dt and records
  `time_budget_exceeded` instead of silently dropping time; `shot.slow` (seconds) is converted to
  ticks, so a 3 s chill really lasts 3 s.
- **Board geometry is real.** `tools/contentc/geometry.py` derives 26 world sizes from the original
  stage modules into `native/generated/board_sizes.json`; `CatalogOptions::boardSizes` + CLI
  `--boards` apply them. beach and modern open **6×9**, the other 24 stay 5×9.
- **Replays are validated.** Out-of-order ticks, `plant` without a type and negative `collect` ids
  are rejected; a late input is applied but emits `input_late`.
- **Gates no longer heal themselves.** `tools/check_all.ps1` reads its baselines *before* running
  the generators; `tools/build_native.ps1 -BuildDir` gives parallel agents their own build tree
  (the `.tlog` lock that broke a concurrent audit is gone).
- **Smoke covers 32 scenarios** (26 worlds + 5 probes + 1 win). `beach_23` with a scripted deck
  ends `won` at tick 1538, so the victory branch is proven through the CLI, not only in a unit test.
- **Matrix honesty.** `playable` is derived (referenced by a level *and* family implemented):
  plants 41/147, zombies 47/55. `engine_families` fails closed if the registry table stops parsing.

Known-open, on purpose: legacy `Battle` still diverges from the engine (sky sun 8 s vs 4.5 s+24 s,
mower line -0.25 vs -0.7) and remains the only consumer of `battle_view`; moving the desktop view
to `engine::World` is S4 work. `SpawnOffset.y` is not applied yet (needs a `spawnSun` signature
change) and unknown actions only emit events, with no counter API.

## S3 landed in part (2026-11-20 21:00): ids, geometry, class families, family numbers

What now exists that did not before:

- **`native/generated/id_mapping.csv`** — 339 pack plants and 1127 pack zombies each carry a verdict.
  Only 44 plant ids and 20 zombie ids match the shipped content by name; 8 more zombies were adopted from
  `extra.source_codename`, 103 client plants and 27 client zombies have no counterpart in this build at all.
  That is the honest shape of "replicate everything": the client's 147/55 list is a curated subset, so the
  real target is the pack's 339 plant types (235 frameworks) and 1127 zombie types (183 classes).
- **`native/generated/board_sizes.json`** — 26 worlds with evidence. beach and modern are **6×9**; the rest
  are 5×9. `CatalogOptions::boardSizes` applies them, `--boards` overrides at the CLI, and the smoke run
  compares every world against the file. The earlier "6×10" was a sentinel artefact (`GridX=150` spawn
  points) — corrected and pinned by tests.
- **183 `ZombieClass` rows → 6 families** (`zombie_classes.json` + `zombie_family_table.inc`), generated by
  `tools/contentc/zclasses.py` with 13 explicit human overrides for cases the sheets cannot decide
  (pole-vaulting classes carry no jump action at all; `ZombieCakeTank` is a boss vehicle base;
  `ZombieZCorpImp` reuses gargantuar art). `World::spawnZombie` now resolves family as
  **class table > content `behavior` > walk**, so a pack-only type gets a real behaviour instead of `walk`.
- **Plant families read the pack** (`registry.cpp`): pack slot > content JSON > tuning constant, with every
  fallback marked in place. 26 constants still fall back — `wall` and `support` have almost no packed numbers,
  which is recorded rather than papered over.
- **Smoke is 32 scenarios**: 26 worlds (checked against the geometry file), five fixed probes, and `beach_23`
  scripted to victory (`won` at tick 1538). The victory branch is proven through the CLI, not only in a test.
- **Gates**: audit 11/11, desktop 16/16, Python 136 tests, `check_all.ps1 -Desktop` exit 0 both with and
  without `-AllowMatrixChange`.

Lesson worth keeping: restoring a probe file with `Copy-Item` preserves its old mtime, so MSBuild skips the
recompile and runs the probe build while the source looks correct. Touch the file or delete the `.obj`.


## 系统完成度总账（2026-11-20）

见 docs/COMPLETENESS.md：12 个系统的完成度、34 条缺陷（C1–C34，按 blocker/high/medium/low 分级）与 S5–S9 阶段计划。一句话概括：**数据与内核地基已成（90% / 70%），玩法层（Boss/砸罐子/矿车/UI/音频）是剩余主体**。

## S6.1 world map + S5.12 vault closure (2026-11-23 08:40)

- `native/src/worldmap.{hpp,cpp}` (no SDL, in `pvz_catalog`): merges `world_gates.json` (97 gates)
  with `content/worldmap.json` (26 worlds) and counts levels from `content/stars.json` keys.
  Keys and stars are separate currencies; `hasEntryGate` separates "no gate" from "gate demands 0";
  `starsSource` says whether the number came from the sheet, the client file, or nowhere.
  `--worldmap <content> [--progress <file>]` prints the 26 states — the command exists so the model
  has a real caller instead of only unit tests (C41's lesson).
- t30 (wirer) closed the vault evidence gap: trigger window `kEatStartCols + 0.05` (0.40), landing
  0.55, `zombie_hop` carries `from/to/distance/jump`; reverse probe (window back to 1.20) fails with
  `a hop must only start at contact: from 5.698667 is outside the 0.400000-column window around 4.500000`.
  It also surfaced a real bug: the eat scan (1.15) sat behind `tryVault`, and the old 1.20 window only
  worked because it was 0.05 wider. Jump-family zombies now eat at `kEatStartCols`; other families unchanged.
- Gates: audit 19/19, desktop 24/24, Python 296, smoke 32 scenarios 0 diff; strict `check_all.ps1`
  EXIT=0 with the ledger at 19/24/296. Matrix: 世界门 97/97/97, 护甲 102/102/91, 弹道 602/602/593.
- Still open in S6: the desktop world-map screen (T35), real key/coin economy (tracks C46),
  shop purchase path; audit round on the newer modules is pending (team loop escalated).
