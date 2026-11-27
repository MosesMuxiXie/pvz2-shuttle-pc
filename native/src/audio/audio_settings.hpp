#pragma once

// The settings screen's model: three volume rows, the cursor, and the bridge between the save
// file and the mixer.
//
// Header-only and SDL-free on purpose. The screen itself lives in `settings_view.cpp` (SDL), but
// every rule this file encodes - what the left/right keys do, what `M` toggles, what the JSON line
// looks like - is a plain function a test can call in an audit build with no sound card and no
// window. Keeping it here also means `pvz_audio_core` needs no extra source file: the model is
// inlined into whoever includes it.

#include "audio/audio_runtime.hpp"
#include "progress.hpp"

#include <algorithm>
#include <string>

namespace pvz {

/// The order the rows are drawn and walked in.
enum class SettingsRow { master = 0, music = 1, sfx = 2 };

inline constexpr int kSettingsRowCount = 3;
/// One press of left/right. 5% is coarse enough that 20 presses cover the whole range and fine
/// enough that a player can hear the difference between neighbouring steps.
inline constexpr int kSettingsStepPercent = 5;

/// Everything the screen needs to draw itself, and everything the save needs to remember.
struct SettingsState {
  AudioSettings audio;
  int row = 0;  ///< 0 master, 1 music, 2 sfx

  int rowIndex() const { return std::clamp(row, 0, kSettingsRowCount - 1); }

  /// The percentage shown on the highlighted row.
  int value() const {
    switch (static_cast<SettingsRow>(rowIndex())) {
      case SettingsRow::master: return audio.master;
      case SettingsRow::music: return audio.music;
      case SettingsRow::sfx: return audio.sfx;
    }
    return audio.master;
  }

  /// Writes `percent` into the highlighted row, clamped to 0..100.
  void setValue(int percent) {
    const int clean = std::clamp(percent, 0, 100);
    switch (static_cast<SettingsRow>(rowIndex())) {
      case SettingsRow::master: audio.master = clean; break;
      case SettingsRow::music: audio.music = clean; break;
      case SettingsRow::sfx: audio.sfx = clean; break;
    }
  }
};

enum class SettingsKey { up, down, left, right, mute, back, none };

struct SettingsStepResult {
  SettingsState state;
  /// The value changed (left/right/mute): the caller plays a click and writes the save.
  bool changed = false;
  /// The cursor moved: the caller plays a click but writes nothing.
  bool moved = false;
  /// `Esc`: the caller leaves the screen.
  bool closed = false;
};

/// One key press. Pure: no SDL, no audio, no file. `left`/`right` move the highlighted bus by
/// `kSettingsStepPercent`, `up`/`down` walk the three rows (wrapping, so the cursor never sticks at
/// an end), `mute` flips `audio.muted` and leaves the three percentages untouched, so unmuting
/// restores exactly what the player picked.
inline SettingsStepResult applySettingsKey(const SettingsState& state, SettingsKey key) {
  SettingsStepResult result;
  result.state = state;
  switch (key) {
    case SettingsKey::up:
      result.state.row = (state.rowIndex() + kSettingsRowCount - 1) % kSettingsRowCount;
      result.moved = true;
      break;
    case SettingsKey::down:
      result.state.row = (state.rowIndex() + 1) % kSettingsRowCount;
      result.moved = true;
      break;
    case SettingsKey::left:
      result.state.setValue(state.value() - kSettingsStepPercent);
      result.changed = result.state.value() != state.value();
      break;
    case SettingsKey::right:
      result.state.setValue(state.value() + kSettingsStepPercent);
      result.changed = result.state.value() != state.value();
      break;
    case SettingsKey::mute:
      result.state.audio.muted = !state.audio.muted;
      result.changed = true;
      break;
    case SettingsKey::back:
      result.closed = true;
      break;
    case SettingsKey::none:
      break;
  }
  return result;
}

/// Pushes the three buses and the mute switch into a runtime. Safe in every mode: a muted or
/// headless runtime keeps the integers and has no backend to forward to.
inline void applyAudioSettings(AudioRuntime& runtime, const AudioSettings& audio) {
  const AudioSettings clean = clampAudioSettings(audio);
  runtime.setVolume(clean.master);
  runtime.setMusicVolume(clean.music);
  runtime.setSfxVolume(clean.sfx);
  runtime.setMuted(clean.muted);
}

/// Pushes into the process-wide runtime (`ambientAudio()`), if one is attached. This is what the
/// settings screen calls after every key so a change is audible before the next frame.
inline void applyAudioSettingsProcess(const AudioSettings& audio) {
  if (AudioRuntime* runtime = ambientAudio(); runtime != nullptr) applyAudioSettings(*runtime, audio);
}

/// Reads back what the runtime currently holds. `muted` comes from the caller's state, not from
/// `AudioRuntime::muted()`: the latter answers "can anything play at all", which is a different
/// question and reports true on a headless run.
inline AudioSettings audioSettingsOf(const AudioRuntime& runtime, bool muted) {
  AudioSettings audio;
  audio.master = runtime.volume();
  audio.music = runtime.musicVolume();
  audio.sfx = runtime.sfxVolume();
  audio.muted = muted;
  return clampAudioSettings(audio);
}

/// The one-line contract the settings screen prints:
/// `{"master":N,"music":N,"sfx":N,"muted":bool}`.
inline std::string settingsJsonLine(const AudioSettings& audio) {
  return audioSettingsJson(audio).dump();
}

}  // namespace pvz
