# First Battle and macOS Build Implementation Plan

**Design** [Native client reconstruction](../specs/2026-11-10-native-client-design.md)

Continue on `feature/native-client`. Keep the Python catalog as the reference for existing behavior. Read the native first-battle definition from `content/native/frontyard_1.json` so the observed same-version APK and OBB values can be applied without changing Python levels. Validate macOS packaging on GitHub Actions without running the app on macOS.

1. Add a C++20 fixed-step battle model and tests. Use the 5×9 front-yard board, catalog plants and zombies, and six waves transcribed from the same-version OBB. Test selection, the first sun at 2 seconds, the first wave at 12 seconds, both outcomes and a full win on the native level data.
2. Add native save import and completion writes. Preserve Python v2/v3 JSON fields, including unused data, and keep the input unchanged. Prevent import over an existing native slot and update `frontyard:0` idempotently. Test invalid, existing and Unicode paths.
3. Connect SDL3 selection, battle input and results with procedural graphics. Verify a Windows hidden render and a scripted full win.
4. On an Apple Silicon Actions runner, build `arm64;x86_64` with Apple Clang, bundle the tracked content and produce a CPack DMG. Verify both Mach-O slices and the mounted image structure without executing the app. Keep APK, OBB, saves and local assets outside CI.
