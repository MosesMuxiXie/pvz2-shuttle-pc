#include "text.hpp"
#include "catalog.hpp"
#include "sdl_support.hpp"
#include <algorithm>
#include <cmath>
#include <cstring>
#include <ft2build.h>
#include FT_FREETYPE_H
#include <fstream>
#include <iterator>
#include <stdexcept>

namespace pvz {
namespace {
constexpr int kAtlasWidth = 1024;
constexpr int kAtlasHeight = 1024;
std::string freetypeError(FT_Error error) {
    const char* text = FT_Error_String(error);
    return text != nullptr ? std::string(text) : "FreeType error " + std::to_string(error);
}
} // namespace
std::vector<std::uint32_t> decodeUtf8(const std::string& text) {
    std::vector<std::uint32_t> out;
    out.reserve(text.size());
    std::size_t i = 0;
    while (i < text.size()) {
        const auto lead = static_cast<unsigned char>(text[i]);
        std::uint32_t codepoint = 0;
        std::size_t extra = 0;
        if (lead < 0x80) {
            codepoint = lead;
        } else if ((lead & 0xE0) == 0xC0) {
            codepoint = lead & 0x1Fu;
            extra = 1;
        } else if ((lead & 0xF0) == 0xE0) {
            codepoint = lead & 0x0Fu;
            extra = 2;
        } else if ((lead & 0xF8) == 0xF0) {
            codepoint = lead & 0x07u;
            extra = 3;
        } else {
            out.push_back(0xFFFD);
            i += 1;
            continue;
        }
        if (i + extra >= text.size()) {
            out.push_back(0xFFFD);
            break;
        }
        bool valid = true;
        for (std::size_t k = 1; k <= extra; ++k) {
            const auto byte = static_cast<unsigned char>(text[i + k]);
            if ((byte & 0xC0) != 0x80) {
                valid = false;
                break;
            }
            codepoint = (codepoint << 6) | (byte & 0x3Fu);
        }
        i += extra + 1;
        out.push_back(valid ? codepoint : 0xFFFD);
    }
    return out;
}
TextRenderer::TextRenderer(SDL_Renderer* renderer, const std::filesystem::path& fontFile)
    : renderer_(renderer), font_(fontFile) {
    if (!std::filesystem::is_regular_file(fontFile))
        throw std::runtime_error(pathUtf8(fontFile) + ": missing font file");
    // FreeType opens by byte path, which fails for non-ANSI directories, so hand it the bytes instead.
    {
        std::ifstream stream(fontFile, std::ios::binary);
        if (!stream)
            throw std::runtime_error(pathUtf8(fontFile) + ": cannot read font file");
        fontData_.assign(std::istreambuf_iterator<char>(stream), std::istreambuf_iterator<char>());
    }
    if (fontData_.empty())
        throw std::runtime_error(pathUtf8(fontFile) + ": empty font file");
    auto* library = static_cast<FT_Library>(nullptr);
    if (FT_Init_FreeType(&library) != 0)
        throw std::runtime_error(pathUtf8(fontFile) + ": cannot initialise FreeType");
    library_ = library;
    FT_Face chosen = nullptr;
    int chosenIndex = 0;
    FT_Error lastError = 0;
    // Probe the collection faces and keep the first that covers both Latin and CJK.
    for (int index = 0; index < 32; ++index) {
        FT_Face face = nullptr;
        const FT_Error error = FT_New_Memory_Face(library, fontData_.data(), static_cast<FT_Long>(fontData_.size()),
                                                  index, &face);
        if (error != 0) {
            lastError = error;
            break;
        }
        const bool hasCjk = FT_Get_Char_Index(face, 0x4E2D) != 0;
        const bool hasLatin = FT_Get_Char_Index(face, 'A') != 0;
        if (hasCjk && hasLatin) {
            if (chosen != nullptr)
                FT_Done_Face(chosen);
            chosen = face;
            chosenIndex = index;
            break;
        }
        if (chosen == nullptr) {
            chosen = face;
            chosenIndex = index;
            continue;
        }
        FT_Done_Face(face);
    }
    if (chosen == nullptr)
        throw std::runtime_error(pathUtf8(fontFile) + ": no usable face in font (" + freetypeError(lastError) + ")");
    face_ = chosen;
    faceIndex_ = chosenIndex;
    atlas_ = SDL_CreateTexture(renderer_, SDL_PIXELFORMAT_RGBA32, SDL_TEXTUREACCESS_STREAMING, kAtlasWidth,
                               kAtlasHeight);
    if (atlas_ == nullptr)
        throw std::runtime_error("create glyph atlas: " + std::string(SDL_GetError()));
    sdl::require(SDL_SetTextureBlendMode(atlas_, SDL_BLENDMODE_BLEND), "set glyph blend mode");
    sdl::require(SDL_SetTextureScaleMode(atlas_, SDL_SCALEMODE_LINEAR), "set glyph scale mode");
    pixels_.assign(static_cast<std::size_t>(kAtlasWidth) * kAtlasHeight * 4, 0);
    sdl::require(SDL_UpdateTexture(atlas_, nullptr, pixels_.data(), kAtlasWidth * 4), "clear glyph atlas");
}
TextRenderer::~TextRenderer() {
    if (atlas_ != nullptr)
        SDL_DestroyTexture(atlas_);
    if (face_ != nullptr)
        FT_Done_Face(static_cast<FT_Face>(face_));
    if (library_ != nullptr)
        FT_Done_FreeType(static_cast<FT_Library>(library_));
}
void TextRenderer::prepare(int pixelSize) {
    if (ascents_.count(pixelSize) != 0)
        return;
    auto* face = static_cast<FT_Face>(face_);
    const FT_Error error = FT_Set_Pixel_Sizes(face, 0, static_cast<FT_UInt>(pixelSize));
    if (error != 0)
        throw std::runtime_error("set font size " + std::to_string(pixelSize) + ": " + freetypeError(error));
    ascents_[pixelSize] = static_cast<float>(face->size->metrics.ascender) / 64.0f;
    heights_[pixelSize] = static_cast<float>(face->size->metrics.height) / 64.0f;
}
float TextRenderer::ascent(int pixelSize) {
    prepare(pixelSize);
    return ascents_[pixelSize];
}
float TextRenderer::lineHeight(int pixelSize) {
    prepare(pixelSize);
    return heights_[pixelSize];
}
void TextRenderer::upload(int x, int y, int w, int h) {
    const SDL_Rect rect{x, y, w, h};
    sdl::require(SDL_UpdateTexture(atlas_, &rect,
                                   &pixels_[(static_cast<std::size_t>(y) * kAtlasWidth + static_cast<std::size_t>(x)) * 4],
                                   kAtlasWidth * 4),
                 "upload glyph");
}
TextRenderer::Glyph& TextRenderer::glyph(std::uint32_t codepoint, int pixelSize) {
    const auto key = std::make_pair(pixelSize, codepoint);
    const auto found = glyphs_.find(key);
    if (found != glyphs_.end())
        return found->second;
    prepare(pixelSize);
    auto* face = static_cast<FT_Face>(face_);
    Glyph fresh;
    if (FT_Load_Char(face, static_cast<FT_ULong>(codepoint), FT_LOAD_RENDER) != 0) {
        fresh.advance = pixelSize / 2;
        return glyphs_.emplace(key, fresh).first->second;
    }
    const FT_GlyphSlot slot = face->glyph;
    fresh.advance = static_cast<int>(slot->advance.x >> 6);
    fresh.bearingX = slot->bitmap_left;
    fresh.bearingY = slot->bitmap_top;
    const int width = static_cast<int>(slot->bitmap.width);
    const int height = static_cast<int>(slot->bitmap.rows);
    if (width == 0 || height == 0) {
        fresh.empty = true;
        return glyphs_.emplace(key, fresh).first->second;
    }
    if (penX_ + width + 1 > kAtlasWidth) {
        penX_ = 1;
        penY_ += rowHeight_ + 1;
        rowHeight_ = 0;
    }
    if (penY_ + height + 1 > kAtlasHeight)
        throw std::runtime_error("glyph atlas is full");
    fresh.empty = false;
    fresh.x = penX_;
    fresh.y = penY_;
    fresh.w = width;
    fresh.h = height;
    for (int row = 0; row < height; ++row) {
        const unsigned char* source = slot->bitmap.buffer + static_cast<std::ptrdiff_t>(row) * slot->bitmap.pitch;
        std::uint8_t* target = &pixels_[(static_cast<std::size_t>(penY_ + row) * kAtlasWidth +
                                        static_cast<std::size_t>(penX_)) *
                                       4];
        for (int column = 0; column < width; ++column) {
            target[column * 4 + 0] = 255;
            target[column * 4 + 1] = 255;
            target[column * 4 + 2] = 255;
            target[column * 4 + 3] = source[column];
        }
    }
    upload(penX_, penY_, width, height);
    penX_ += width + 1;
    rowHeight_ = std::max(rowHeight_, height);
    return glyphs_.emplace(key, fresh).first->second;
}
const TextRenderer::Glyph& TextRenderer::cachedGlyph(std::uint32_t codepoint, int pixelSize) {
    return glyph(codepoint, pixelSize);
}
float TextRenderer::draw(float x, float y, int pixelSize, SDL_Color color, const std::string& utf8) {
    sdl::require(SDL_SetTextureColorMod(atlas_, color.r, color.g, color.b), "set glyph colour");
    sdl::require(SDL_SetTextureAlphaMod(atlas_, color.a), "set glyph alpha");
    const float baseline = y + ascent(pixelSize);
    float pen = x;
    for (const auto codepoint : decodeUtf8(utf8)) {
        const Glyph& g = cachedGlyph(codepoint, pixelSize);
        if (!g.empty) {
            const SDL_FRect source{static_cast<float>(g.x), static_cast<float>(g.y), static_cast<float>(g.w),
                                   static_cast<float>(g.h)};
            const SDL_FRect target{pen + static_cast<float>(g.bearingX),
                                   baseline - static_cast<float>(g.bearingY), static_cast<float>(g.w),
                                   static_cast<float>(g.h)};
            sdl::require(SDL_RenderTexture(renderer_, atlas_, &source, &target), "draw glyph");
        }
        pen += static_cast<float>(g.advance);
    }
    return pen - x;
}
float TextRenderer::drawCentered(float centerX, float y, int pixelSize, SDL_Color color,
                                 const std::string& utf8) {
    const float advance = width(utf8, pixelSize);
    draw(centerX - advance / 2.0f, y, pixelSize, color, utf8);
    return advance;
}
float TextRenderer::width(const std::string& utf8, int pixelSize) {
    float total = 0;
    for (const auto codepoint : decodeUtf8(utf8))
        total += static_cast<float>(cachedGlyph(codepoint, pixelSize).advance);
    return total;
}
} // namespace pvz
