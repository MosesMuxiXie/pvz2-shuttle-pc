#include "actor_view.hpp"
#include <algorithm>
#include <cstdio>
#include <cstdlib>

namespace pvz {
namespace {
db::Matrix placement(const ActorPose& pose) {
    db::Matrix origin;
    origin.tx = pose.x;
    origin.ty = pose.y;
    db::Matrix offset;
    offset.a = pose.flip ? -pose.scale : pose.scale;
    offset.d = pose.scale;
    return origin * offset;
}
} // namespace
int drawActor(SDL_Renderer* renderer, AssetCache& cache, const ActorPose& pose) {
    if (pose.model.empty())
        return 0;
    const auto asset = cache.tryModel(pose.model, pose.armature);
    if (asset.model == nullptr || asset.texture == nullptr)
        return 0;
    const db::Pose posed = db::evaluate(*asset.model, pose.animation, pose.seconds);
    const auto alpha =
        static_cast<Uint8>(std::clamp(pose.alpha, 0.0f, 1.0f) * static_cast<float>(pose.tint.a));
    sdl::require(SDL_SetTextureColorMod(asset.texture, pose.tint.r, pose.tint.g, pose.tint.b),
                 "set actor tint");
    sdl::require(SDL_SetTextureAlphaMod(asset.texture, alpha), "set actor alpha");
    const db::Matrix world = placement(pose);
    int drawn = 0;
    for (std::size_t index = 0; index < posed.display.size(); ++index) {
        const int display = posed.display[index];
        const auto& slot = asset.model->armature.slots[index];
        if (display < 0 || display >= static_cast<int>(slot.displays.size()))
            continue;
        const auto& sprite = slot.displays[static_cast<std::size_t>(display)];
        const db::Sprite* found = findSprite(asset.model->atlas, sprite);
        if (found == nullptr)
            continue;
        const db::Matrix local = world * posed.slots[index];
        // DragonBones places a sprite by its bottom-left corner with y pointing up; the renderer
        // works in screen space, so the sprite sits one frame height above the pivot.
        const db::Point topLeft = db::apply(local, {found->offsetX, found->offsetY - found->height});
        const db::Point topRight = db::apply(local, {found->offsetX + found->width, found->offsetY - found->height});
        const db::Point bottomLeft = db::apply(local, {found->offsetX, found->offsetY});
        const SDL_FRect source{found->x, found->y, found->width, found->height};
        const SDL_FPoint corner{topLeft.x, topLeft.y};
        const SDL_FPoint right{topRight.x, topRight.y};
        const SDL_FPoint down{bottomLeft.x, bottomLeft.y};
        sdl::require(SDL_RenderTextureAffine(renderer, asset.texture, &source, &corner, &right, &down),
                     "draw actor sprite");
        ++drawn;
    }
    sdl::require(SDL_SetTextureAlphaMod(asset.texture, 255), "reset actor alpha");
    return drawn;
}
float actorHeight(AssetCache& cache, const ActorPose& pose) {
    if (pose.model.empty())
        return 0;
    const auto asset = cache.tryModel(pose.model, pose.armature);
    if (asset.model == nullptr)
        return 0;
    return asset.model->armature.bounds.height * pose.scale;
}
bool actorBonePosition(AssetCache& cache, const ActorPose& pose, const std::string& bone, float& x,
                       float& y) {
    if (pose.model.empty())
        return false;
    const auto asset = cache.tryModel(pose.model, pose.armature);
    if (asset.model == nullptr)
        return false;
    const db::Pose posed = db::evaluate(*asset.model, pose.animation, pose.seconds);
    const int index = posed.indexOfBone(asset.model->armature, bone);
    if (index < 0)
        return false;
    const db::Point point = db::apply(placement(pose) * posed.bones[static_cast<std::size_t>(index)],
                                      {0.0f, 0.0f});
    x = point.x;
    y = point.y;
    return true;
}
} // namespace pvz
