#pragma once
#include "catalog.hpp"
#include <SDL3/SDL.h>
#include <SDL3_image/SDL_image.h>
#include <fstream>
#include <memory>
#include <stdexcept>
#include <vector>
namespace pvz::sdl {
template <class T, void (*Destroy)(T*)> using Handle = std::unique_ptr<T, decltype(Destroy)>;
using Surface = Handle<SDL_Surface, SDL_DestroySurface>;
using Window = Handle<SDL_Window, SDL_DestroyWindow>;
using Renderer = Handle<SDL_Renderer, SDL_DestroyRenderer>;
using Texture = Handle<SDL_Texture, SDL_DestroyTexture>;
inline void require(bool ok, const std::string& operation) {
    if (!ok)
        throw std::runtime_error(operation + ": " + SDL_GetError());
}
struct Context {
    explicit Context(bool headless) { require(SDL_Init(headless ? 0 : SDL_INIT_VIDEO), "SDL_Init"); }
    ~Context() { SDL_Quit(); }
};
inline Texture texture(SDL_Renderer* renderer, const std::filesystem::path& file) {
    std::ifstream in(file, std::ios::binary | std::ios::ate);
    if (!in)
        throw std::runtime_error(pathUtf8(file) + ": cannot open artwork");
    const auto size = in.tellg();
    if (size <= 0 || size > 128 * 1024 * 1024)
        throw std::runtime_error(pathUtf8(file) + ": artwork is empty or exceeds 128 MiB");
    std::vector<char> bytes(static_cast<std::size_t>(size));
    in.seekg(0);
    if (!in.read(bytes.data(), static_cast<std::streamsize>(bytes.size())))
        throw std::runtime_error(pathUtf8(file) + ": cannot read artwork");
    auto* stream = SDL_IOFromConstMem(bytes.data(), bytes.size());
    require(stream != nullptr, pathUtf8(file) + ": create image stream");
    Texture out(IMG_LoadTexture_IO(renderer, stream, true), SDL_DestroyTexture);
    require(bool(out), pathUtf8(file) + ": decode artwork");
    require(SDL_SetTextureScaleMode(out.get(), SDL_SCALEMODE_LINEAR), "set image scaling");
    return out;
}
inline void snapshot(SDL_Renderer* renderer, const std::filesystem::path& path) {
    Surface pixels(SDL_RenderReadPixels(renderer, nullptr), SDL_DestroySurface);
    require(bool(pixels), "read frame");
    require(SDL_SaveBMP(pixels.get(), pathUtf8(path).c_str()), pathUtf8(path) + ": save snapshot");
}
struct Display {
    Context context;
    Surface framebuffer{nullptr, SDL_DestroySurface};
    Window window{nullptr, SDL_DestroyWindow};
    Renderer renderer{nullptr, SDL_DestroyRenderer};
    Display(bool headless, const char* title) : context(headless) {
        if (headless) {
            framebuffer.reset(SDL_CreateSurface(1280, 720, SDL_PIXELFORMAT_RGBA32));
            require(bool(framebuffer), "create frame");
            renderer.reset(SDL_CreateSoftwareRenderer(framebuffer.get()));
        } else {
            window.reset(
                SDL_CreateWindow(title, 1280, 720, SDL_WINDOW_RESIZABLE | SDL_WINDOW_HIGH_PIXEL_DENSITY));
            require(bool(window), "create window");
            renderer.reset(SDL_CreateRenderer(window.get(), nullptr));
        }
        require(bool(renderer), "create renderer");
        require(
            SDL_SetRenderLogicalPresentation(renderer.get(), 1280, 720, SDL_LOGICAL_PRESENTATION_LETTERBOX),
            "set logical viewport");
    }
};
} // namespace pvz::sdl
