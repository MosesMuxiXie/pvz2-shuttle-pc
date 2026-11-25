#pragma once
// Minimal DragonBones 5.5 reader and evaluator for the baked actor atlases under assets/db.
// It covers what the shipped models actually use: bone transforms, per-bone translate/rotate/
// scale timelines, slot display/colour timelines and trimmed texture atlases. Meshes, IK,
// constraints, bones' inherit* flags and event timelines are parsed past but not simulated.
#include <filesystem>
#include <map>
#include <string>
#include <vector>

namespace pvz::db {
struct Transform {
    float x = 0, y = 0;
    float rotation = 0; // degrees
    float skewX = 0, skewY = 0; // degrees
    float scaleX = 1, scaleY = 1;
};
struct Matrix {
    float a = 1, b = 0, c = 0, d = 1, tx = 0, ty = 0;
};
struct Point {
    float x = 0, y = 0;
};
Matrix matrixOf(const Transform& transform);
Matrix operator*(const Matrix& parent, const Matrix& child);
Point apply(const Matrix& matrix, Point point);

struct Display {
    std::string name, path;
    Transform transform;
};
struct Slot {
    std::string name, boneName;
    int bone = -1;
    int displayIndex = 0;
    float red = 255, green = 255, blue = 255, alpha = 255;
    std::vector<Display> displays;
};
struct Bone {
    std::string name, parentName;
    int parent = -1;
    Transform transform;
};
struct Bounds {
    float x = 0, y = 0, width = 0, height = 0;
};
struct Frame {
    int start = 0, duration = 0;
    float x = 0, y = 0, rotation = 0, scaleX = 1, scaleY = 1;
    bool step = false;
    bool curve = false;
    float curveX1 = 0.5f, curveY1 = 0.0f, curveX2 = 0.5f, curveY2 = 1.0f;
};
struct Keys {
    bool present = false;
    std::vector<Frame> frames;
};
struct BoneTimeline {
    int bone = -1;
    Keys translate, rotate, scale;
};
struct SlotTimeline {
    int slot = -1;
    std::vector<std::pair<int, int>> display; // (start frame, display index)
    std::vector<std::pair<int, float>> alpha; // (start frame, 0..1)
};
struct Animation {
    std::string name;
    float frameRate = 24;
    int duration = 0;
    std::vector<BoneTimeline> bones;
    std::vector<SlotTimeline> slots;
};
struct Armature {
    std::string name;
    float frameRate = 24;
    Bounds bounds;
    std::vector<Bone> bones;
    std::vector<Slot> slots;
    std::map<std::string, Animation> animations;
    std::string defaultAnimation;
};
struct Sprite {
    float x = 0, y = 0, width = 0, height = 0;
    float offsetX = 0, offsetY = 0; // -frameX, -frameY
    float frameWidth = 0, frameHeight = 0; // 0 when the sprite was not trimmed
};
struct Atlas {
    std::string image;
    int width = 0, height = 0;
    std::map<std::string, Sprite> sprites;
};
struct Model {
    std::filesystem::path root, texture;
    std::string key;
    Armature armature;
    std::map<std::string, Armature> armatures;
    Atlas atlas;

    const Armature* findArmature(const std::string& name) const;
    const Animation* findAnimation(const std::string& animation) const;
};
Model loadModel(const std::filesystem::path& directory, const std::string& preferredArmature = {});

struct Pose {
    std::vector<Matrix> bones;  // world matrix of every bone
    std::vector<Matrix> slots;  // world matrix of every slot (bone * display transform)
    std::vector<int> display;   // resolved display index per slot, -1 when hidden
    std::vector<float> alpha;   // resolved alpha multiplier per slot
    int indexOfBone(const Armature& armature, const std::string& name) const;
};
Pose evaluate(const Model& model, const Armature& armature, const std::string& animation, float seconds);
inline Pose evaluate(const Model& model, const std::string& animation, float seconds) {
    return evaluate(model, model.armature, animation, seconds);
}
std::vector<std::string> animationNames(const Armature& armature);
const Animation* findAnimation(const Armature& armature, const std::string& animation);
} // namespace pvz::db
