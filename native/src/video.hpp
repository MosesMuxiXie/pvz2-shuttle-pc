#pragma once

#include <SDL3/SDL.h>

#include <stdexcept>
#include <string>

namespace shuttle {

inline void requireSdl(bool success, const std::string& operation) {
    if (!success) {
        throw std::runtime_error(operation + ": " + SDL_GetError());
    }
}

struct VideoSession {
    VideoSession() { requireSdl(SDL_Init(SDL_INIT_VIDEO), "initialize SDL video"); }
    ~VideoSession() { SDL_Quit(); }
    VideoSession(const VideoSession&) = delete;
    VideoSession& operator=(const VideoSession&) = delete;
};

}
