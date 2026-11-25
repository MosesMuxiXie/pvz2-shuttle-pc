#pragma once
// Reusable asset cache: decoded textures and parsed DragonBones models live for the session.
#include "art_index.hpp"
#include "dragonbones.hpp"
#include "sdl_support.hpp"
#include <cstddef>
#include <filesystem>
#include <map>
#include <optional>
#include <set>
#include <string>

namespace pvz {
class AssetCache {
public:
    AssetCache(SDL_Renderer* renderer, std::filesystem::path root);
    SDL_Texture* texture(const std::string& relative);
    struct ModelAsset {
        const db::Model* model = nullptr;
        SDL_Texture* texture = nullptr;
    };
    ModelAsset model(const std::string& relative, const std::string& armature = {});
    // Same lookup, but a missing or unparsable model reports through error instead of throwing,
    // so a single broken art entry cannot abort a whole frame.
    ModelAsset tryModel(const std::string& relative, const std::string& armature = {},
                        std::string* error = nullptr);
    // Resolves a content `art` key or a pack `popAnim` onto a folder under the asset root:
    // `db/<art>` first, then the SHUTTLE index. A miss is remembered (never re-probed per
    // frame) and exposed through `missingArt()`, so the view can report it instead of drawing
    // nothing.
    ArtResolution art(const std::string& art, const std::string& popAnim = {});
    const ShuttleArtIndex& shuttleIndex() const;
    std::size_t missingArt() const { return missingArt_.size(); }
    std::size_t textureCount() const { return textures_.size(); }
    std::size_t modelCount() const { return models_.size(); }
    const std::filesystem::path& root() const { return root_; }

private:
    SDL_Renderer* renderer_ = nullptr;
    std::filesystem::path root_;
    std::map<std::string, sdl::Texture> textures_;
    std::map<std::string, std::string> failures_;
    struct Entry {
        db::Model model;
        std::string textureKey;
    };
    std::map<std::string, Entry> models_;
    // Loaded on first use: the desktop cache must keep working when the extractor has not
    // written `db/shuttle/index.json` yet.
    mutable std::optional<ShuttleArtIndex> shuttle_;
    std::map<std::string, ArtResolution> artCache_;
    std::set<std::string> missingArt_;
};
// Atlas lookups try the display path, then its shape name and bare basename.
const db::Sprite* findSprite(const db::Atlas& atlas, const db::Display& display);
} // namespace pvz
