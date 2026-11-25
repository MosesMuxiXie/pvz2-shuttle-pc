#pragma once
// FreeType-backed UTF-8 text renderer with a lazily packed glyph atlas.
// The shipped Chinese font is a TrueType collection; the best face is picked at load time.
#include <SDL3/SDL.h>
#include <cstdint>
#include <filesystem>
#include <map>
#include <string>
#include <utility>
#include <vector>

namespace pvz {
class TextRenderer {
public:
    TextRenderer(SDL_Renderer* renderer, const std::filesystem::path& fontFile);
    ~TextRenderer();
    TextRenderer(const TextRenderer&) = delete;
    TextRenderer& operator=(const TextRenderer&) = delete;

    float draw(float x, float y, int pixelSize, SDL_Color color, const std::string& utf8);
    float drawCentered(float centerX, float y, int pixelSize, SDL_Color color, const std::string& utf8);
    float width(const std::string& utf8, int pixelSize);
    float lineHeight(int pixelSize);
    float ascent(int pixelSize);
    const std::filesystem::path& fontFile() const { return font_; }
    int faceIndex() const { return faceIndex_; }

private:
    struct Glyph {
        int x = 0, y = 0, w = 0, h = 0;
        int advance = 0, bearingX = 0, bearingY = 0;
        bool empty = true;
    };
    Glyph& glyph(std::uint32_t codepoint, int pixelSize);
    const Glyph& cachedGlyph(std::uint32_t codepoint, int pixelSize);
    void prepare(int pixelSize);
    void upload(int x, int y, int w, int h);

    SDL_Renderer* renderer_ = nullptr;
    std::filesystem::path font_;
    std::vector<std::uint8_t> fontData_;
    void* library_ = nullptr;
    void* face_ = nullptr;
    SDL_Texture* atlas_ = nullptr;
    std::vector<std::uint8_t> pixels_;
    int penX_ = 1, penY_ = 1, rowHeight_ = 0;
    int faceIndex_ = 0;
    std::map<std::pair<int, std::uint32_t>, Glyph> glyphs_;
    std::map<int, float> ascents_;
    std::map<int, float> heights_;
};
std::vector<std::uint32_t> decodeUtf8(const std::string& text);
} // namespace pvz
