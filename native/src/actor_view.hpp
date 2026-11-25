#pragma once
// Draws a posed DragonBones armature into an SDL renderer.
#include "assets.hpp"
#include <string>

namespace pvz {
struct ActorPose {
    std::string model;     // asset-relative model directory, e.g. "db/plants/PeashooterPLANT"
    std::string armature;  // empty selects the model's default armature
    std::string animation; // empty selects the default animation
    float seconds = 0;
    float x = 0;
    float y = 0;
    float scale = 1.0f;
    bool flip = false;
    float alpha = 1.0f;
    SDL_Color tint{255, 255, 255, 255};
};
// Returns how many sprites were actually drawn, so callers can fall back to shapes.
int drawActor(SDL_Renderer* renderer, AssetCache& cache, const ActorPose& pose);
// Scaled height of the armature bounds, useful for headroom and hit feedback.
float actorHeight(AssetCache& cache, const ActorPose& pose);
// Screen position of a bone origin in the posed armature.
bool actorBonePosition(AssetCache& cache, const ActorPose& pose, const std::string& bone, float& x,
                       float& y);
} // namespace pvz
