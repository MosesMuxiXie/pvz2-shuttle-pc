#pragma once

// The settings screen: three volume buses and a mute switch, plus the headless entry point the
// CLI and the render test use.
//
// Shape follows `menu_view` / `level_select_view` on purpose - one screen, one `run*Screen()`
// function, one snapshot helper - so the chain can be checked from the command line. The part that
// has rules (key handling, JSON, save shape) lives in `audio/audio_settings.hpp` and is SDL-free;
// this file only turns that state into pixels.

#include "audio/audio_settings.hpp"
#include "progress.hpp"

#include <filesystem>
#include <nlohmann/json.hpp>

namespace pvz {

struct SettingsOptions {
  /// Holds `ui/font_zh.ttc`.
  std::filesystem::path assetRoot;
  /// Starting values: what the save remembered, or the defaults on a fresh install.
  SettingsState state;
  /// Optional frame capture; `.png` writes PNG, anything else BMP (same rule as `--menu`).
  std::filesystem::path snapshot;
  /// >0 renders this many frames headlessly and returns; 0 runs the interactive window.
  int frames = 0;
};

struct SettingsResult {
  SettingsState state;
  int rows = kSettingsRowCount;
  int frames = 0;
  /// Whether `Esc` closed the screen (false on a headless run, which has no input).
  bool closed = false;

  /// `{"master":N,"music":N,"sfx":N,"muted":bool}` - one line, same shape as the save block.
  nlohmann::json json() const { return audioSettingsJson(state.audio); }
};

/// Draws the settings screen. Headless (`frames > 0`) renders that many frames with SDL's software
/// renderer and returns without polling for input; the result carries the values the caller should
/// write to the save.
SettingsResult runSettingsScreen(const SettingsOptions& options);

/// Headless entry point used by the CLI and the render test: opens the screen for `frames` frames,
/// writes `snapshot` when not empty, applies the result to the process-wide audio runtime, and
/// returns the JSON line. Kept separate so a caller never has to build `SettingsOptions` by hand.
nlohmann::json renderSettingsHeadless(const std::filesystem::path& assetRoot, int frames,
                                      const std::filesystem::path& snapshot,
                                      const AudioSettings& start = {});

}  // namespace pvz
