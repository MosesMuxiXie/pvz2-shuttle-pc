#include "assets.hpp"
#include "catalog.hpp"
#include <stdexcept>
#include <utility>

namespace pvz {
AssetCache::AssetCache(SDL_Renderer* renderer, std::filesystem::path root)
    : renderer_(renderer), root_(std::move(root)) {
    if (!std::filesystem::is_directory(root_))
        throw std::runtime_error(pathUtf8(root_) + ": missing asset root");
}
SDL_Texture* AssetCache::texture(const std::string& relative) {
    const auto found = textures_.find(relative);
    if (found != textures_.end())
        return found->second.get();
    const auto path = root_ / std::filesystem::path(relative);
    auto loaded = sdl::Texture(sdl::texture(renderer_, path));
    SDL_Texture* raw = loaded.get();
    textures_.emplace(relative, std::move(loaded));
    return raw;
}
AssetCache::ModelAsset AssetCache::model(const std::string& relative, const std::string& armature) {
    const std::string key = armature.empty() ? relative : relative + "#" + armature;
    const auto found = models_.find(key);
    if (found != models_.end())
        return {&found->second.model, texture(found->second.textureKey)};
    Entry entry;
    entry.model = db::loadModel(root_ / std::filesystem::path(relative), armature);
    const auto relativeTexture = std::filesystem::relative(entry.model.texture, root_).generic_string();
    entry.textureKey = relativeTexture.empty() ? entry.model.texture.generic_string() : relativeTexture;
    const auto inserted = models_.emplace(key, std::move(entry));
    return {&inserted.first->second.model, texture(inserted.first->second.textureKey)};
}
AssetCache::ModelAsset AssetCache::tryModel(const std::string& relative, const std::string& armature,
                                           std::string* error) {
    const std::string key = armature.empty() ? relative : relative + "#" + armature;
    if (const auto failed = failures_.find(key); failed != failures_.end()) {
        if (error != nullptr)
            *error = failed->second;
        return {};
    }
    try {
        return model(relative, armature);
    } catch (const std::exception& failure) {
        failures_.emplace(key, failure.what());
        if (error != nullptr)
            *error = failure.what();
        return {};
    }
}
const ShuttleArtIndex& AssetCache::shuttleIndex() const {
    if (!shuttle_)
        shuttle_ = loadShuttleIndex(root_);
    return *shuttle_;
}
ArtResolution AssetCache::art(const std::string& artKey, const std::string& popAnim) {
    const std::string key = artKey + '\x1f' + popAnim;
    if (const auto cached = artCache_.find(key); cached != artCache_.end())
        return cached->second;
    const auto resolution = resolveArt(root_, shuttleIndex(), artKey, popAnim);
    artCache_.emplace(key, resolution);
    if (!resolution.hit())
        missingArt_.insert(key);
    return resolution;
}
const db::Sprite* findSprite(const db::Atlas& atlas, const db::Display& display) {
    const auto tryKey = [&atlas](const std::string& key) -> const db::Sprite* {
        if (key.empty())
            return nullptr;
        const auto found = atlas.sprites.find(key);
        return found == atlas.sprites.end() ? nullptr : &found->second;
    };
    if (const auto* sprite = tryKey(display.path))
        return sprite;
    if (const auto* sprite = tryKey(display.name))
        return sprite;
    const std::filesystem::path path(display.path);
    if (const auto* sprite = tryKey(path.filename().generic_string()))
        return sprite;
    if (const auto* sprite = tryKey(path.stem().generic_string()))
        return sprite;
    return nullptr;
}
} // namespace pvz
