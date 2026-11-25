#include "dragonbones.hpp"
#include "catalog.hpp"
#include <algorithm>
#include <cmath>
#include <fstream>
#include <stdexcept>
namespace pvz::db {
namespace {
constexpr float kPi = 3.14159265358979323846f;
constexpr float kDegrees = kPi / 180.0f;
Json readJson(const std::filesystem::path& file) {
    std::ifstream in(file, std::ios::binary);
    if (!in)
        throw std::runtime_error(pathUtf8(file) + ": cannot open DragonBones data");
    try {
        Json data;
        in >> data;
        return data;
    } catch (const std::exception& error) {
        throw std::runtime_error(pathUtf8(file) + ": invalid DragonBones JSON (" + error.what() + ")");
    }
}
float number(const Json& object, const char* key, float fallback) {
    const auto it = object.find(key);
    if (it == object.end() || !it->is_number())
        return fallback;
    return it->get<float>();
}
int integer(const Json& object, const char* key, int fallback) {
    const auto it = object.find(key);
    if (it == object.end() || !it->is_number())
        return fallback;
    return it->get<int>();
}
Transform readTransform(const Json& object) {
    Transform out;
    out.x = number(object, "x", 0.0f);
    out.y = number(object, "y", 0.0f);
    out.rotation = number(object, "skY", 0.0f);
    out.skewX = number(object, "skX", 0.0f);
    out.scaleX = number(object, "scX", 1.0f);
    out.scaleY = number(object, "scY", 1.0f);
    return out;
}
enum class Channel { translate, rotate, scale };
void readKeys(Keys& keys, const Json& frames, Channel channel) {
    keys.present = true;
    int start = 0;
    for (const auto& frame : frames) {
        Frame out;
        out.start = start;
        out.duration = integer(frame, "duration", 0);
        start += out.duration;
        if (const auto easing = frame.find("tweenEasing"); easing != frame.end() && easing->is_number()) {
            const float value = easing->get<float>();
            out.step = value == 0.0f;
        }
        if (const auto curve = frame.find("curve"); curve != frame.end() && curve->is_array() && curve->size() == 4) {
            out.curve = true;
            out.curveX1 = (*curve)[0].get<float>();
            out.curveY1 = (*curve)[1].get<float>();
            out.curveX2 = (*curve)[2].get<float>();
            out.curveY2 = (*curve)[3].get<float>();
        }
        switch (channel) {
        case Channel::translate:
            out.x = number(frame, "x", 0.0f);
            out.y = number(frame, "y", 0.0f);
            break;
        case Channel::rotate:
            out.rotation = number(frame, "rotate", 0.0f);
            break;
        case Channel::scale:
            out.scaleX = number(frame, "x", 1.0f);
            out.scaleY = number(frame, "y", 1.0f);
            break;
        }
        keys.frames.push_back(out);
    }
}
struct Sampled {
    float x = 0, y = 0, rotation = 0, scaleX = 1, scaleY = 1;
};
float bezier(float x, const Frame& frame) {
    const float x1 = frame.curveX1, y1 = frame.curveY1, x2 = frame.curveX2, y2 = frame.curveY2;
    const auto bezierX = [x1, x2](float t) {
        const float u = 1.0f - t;
        return 3.0f * u * u * t * x1 + 3.0f * u * t * t * x2 + t * t * t;
    };
    const auto bezierY = [y1, y2](float t) {
        const float u = 1.0f - t;
        return 3.0f * u * u * t * y1 + 3.0f * u * t * t * y2 + t * t * t;
    };
    float low = 0.0f, high = 1.0f, t = std::clamp(x, 0.0f, 1.0f);
    for (int i = 0; i < 26; ++i) {
        const float value = bezierX(t);
        if (std::abs(value - x) < 1e-4f)
            break;
        if (value < x)
            low = t;
        else
            high = t;
        t = (low + high) * 0.5f;
    }
    return bezierY(t);
}
Sampled sample(const Keys& keys, float frame) {
    Sampled out;
    const auto& frames = keys.frames;
    if (frames.empty())
        return out;
    std::size_t index = 0;
    for (std::size_t i = 0; i < frames.size(); ++i) {
        if (frame >= static_cast<float>(frames[i].start))
            index = i;
        else
            break;
    }
    const Frame& first = frames[index];
    out = {first.x, first.y, first.rotation, first.scaleX, first.scaleY};
    if (first.duration <= 0 || index + 1 >= frames.size())
        return out;
    const Frame& next = frames[index + 1];
    float blend = (frame - static_cast<float>(first.start)) / static_cast<float>(first.duration);
    blend = std::clamp(blend, 0.0f, 1.0f);
    if (first.step)
        blend = 0.0f;
    else if (first.curve)
        blend = bezier(blend, first);
    out.x = first.x + (next.x - first.x) * blend;
    out.y = first.y + (next.y - first.y) * blend;
    out.rotation = first.rotation + (next.rotation - first.rotation) * blend;
    out.scaleX = first.scaleX + (next.scaleX - first.scaleX) * blend;
    out.scaleY = first.scaleY + (next.scaleY - first.scaleY) * blend;
    return out;
}
int boneIndex(const std::map<std::string, int>& lookup, const std::string& name) {
    const auto it = lookup.find(name);
    return it == lookup.end() ? -1 : it->second;
}
void readAnimation(Animation& out, const Json& json, const std::map<std::string, int>& bones,
                   const std::map<std::string, int>& slots, float armatureFrameRate) {
    out.name = json.value("name", std::string{});
    out.frameRate = number(json, "frameRate", armatureFrameRate);
    out.duration = integer(json, "duration", 0);
    if (const auto list = json.find("bone"); list != json.end()) {
        for (const auto& entry : *list) {
            BoneTimeline timeline;
            timeline.bone = boneIndex(bones, entry.value("name", std::string{}));
            if (timeline.bone < 0)
                continue;
            if (const auto frames = entry.find("translateFrame"); frames != entry.end())
                readKeys(timeline.translate, *frames, Channel::translate);
            if (const auto frames = entry.find("rotateFrame"); frames != entry.end())
                readKeys(timeline.rotate, *frames, Channel::rotate);
            if (const auto frames = entry.find("scaleFrame"); frames != entry.end())
                readKeys(timeline.scale, *frames, Channel::scale);
            if (timeline.translate.present || timeline.rotate.present || timeline.scale.present)
                out.bones.push_back(std::move(timeline));
        }
    }
    if (const auto list = json.find("slot"); list != json.end()) {
        for (const auto& entry : *list) {
            SlotTimeline timeline;
            timeline.slot = slots.count(entry.value("name", std::string{})) != 0
                                ? slots.at(entry.value("name", std::string{}))
                                : -1;
            if (timeline.slot < 0)
                continue;
            if (const auto frames = entry.find("displayFrame"); frames != entry.end()) {
                int start = 0;
                for (const auto& frame : *frames) {
                    const auto value = frame.find("value");
                    timeline.display.emplace_back(start, value != frame.end() && value->is_number()
                                                             ? value->get<int>()
                                                             : -2); // -2 keeps the previous display
                    start += integer(frame, "duration", 0);
                }
            }
            if (const auto frames = entry.find("colorFrame"); frames != entry.end()) {
                int start = 0;
                for (const auto& frame : *frames) {
                    float alphaValue = -1.0f;
                    if (const auto value = frame.find("value"); value != frame.end() && value->is_object())
                        alphaValue = number(*value, "aM", -1.0f) / 255.0f;
                    timeline.alpha.emplace_back(start, alphaValue);
                    start += integer(frame, "duration", 0);
                }
            }
            if (!timeline.display.empty() || !timeline.alpha.empty())
                out.slots.push_back(std::move(timeline));
        }
    }
}
Armature readArmature(const Json& json, float skeletonFrameRate) {
    Armature out;
    out.name = json.value("name", std::string{});
    out.frameRate = number(json, "frameRate", skeletonFrameRate);
    if (const auto aabb = json.find("aabb"); aabb != json.end() && aabb->is_object()) {
        out.bounds.x = number(*aabb, "x", 0.0f);
        out.bounds.y = number(*aabb, "y", 0.0f);
        out.bounds.width = number(*aabb, "width", 0.0f);
        out.bounds.height = number(*aabb, "height", 0.0f);
    }
    std::map<std::string, int> bones;
    std::map<std::string, int> slots;
    if (const auto list = json.find("bone"); list != json.end()) {
        for (const auto& entry : *list) {
            Bone bone;
            bone.name = entry.value("name", std::string{});
            bone.parentName = entry.value("parent", std::string{});
            if (const auto transform = entry.find("transform"); transform != entry.end())
                bone.transform = readTransform(*transform);
            bones[bone.name] = static_cast<int>(out.bones.size());
            out.bones.push_back(std::move(bone));
        }
        for (auto& bone : out.bones) {
            bone.parent = bone.parentName.empty() ? -1 : boneIndex(bones, bone.parentName);
        }
    }
    if (const auto list = json.find("slot"); list != json.end()) {
        for (const auto& entry : *list) {
            Slot slot;
            slot.name = entry.value("name", std::string{});
            slot.boneName = entry.value("parent", std::string{});
            slot.bone = boneIndex(bones, slot.boneName);
            slot.displayIndex = integer(entry, "displayIndex", 0);
            if (const auto color = entry.find("color"); color != entry.end())
                slot.alpha = number(*color, "aM", 255.0f);
            slots[slot.name] = static_cast<int>(out.slots.size());
            out.slots.push_back(std::move(slot));
        }
    }
    if (const auto skins = json.find("skin"); skins != json.end()) {
        for (const auto& skin : *skins) {
            const auto list = skin.find("slot");
            if (list == skin.end())
                continue;
            for (const auto& entry : *list) {
                const auto name = entry.value("name", std::string{});
                const auto index = slots.find(name);
                if (index == slots.end())
                    continue;
                auto& slot = out.slots[static_cast<std::size_t>(index->second)];
                const auto displays = entry.find("display");
                if (displays == entry.end())
                    continue;
                for (const auto& displayJson : *displays) {
                    Display display;
                    display.name = displayJson.value("name", std::string{});
                    display.path = displayJson.value("path", std::string{});
                    if (const auto transform = displayJson.find("transform"); transform != displayJson.end())
                        display.transform = readTransform(*transform);
                    slot.displays.push_back(std::move(display));
                }
            }
        }
    }
    if (const auto list = json.find("animation"); list != json.end()) {
        for (const auto& entry : *list) {
            Animation animation;
            readAnimation(animation, entry, bones, slots, out.frameRate);
            out.animations[animation.name] = std::move(animation);
        }
    }
    if (const auto actions = json.find("defaultActions"); actions != json.end() && actions->is_array() &&
                                                             !actions->empty()) {
        out.defaultAnimation = (*actions)[0].value("gotoAndPlay", std::string{});
    }
    if (out.defaultAnimation.empty() && !out.animations.empty())
        out.defaultAnimation = out.animations.begin()->first;
    return out;
}
Atlas readAtlas(const Json& json) {
    Atlas out;
    out.image = json.value("imagePath", std::string{});
    out.width = integer(json, "width", 0);
    out.height = integer(json, "height", 0);
    const auto list = json.find("SubTexture");
    if (list == json.end())
        return out;
    for (const auto& entry : *list) {
        Sprite sprite;
        sprite.x = number(entry, "x", 0.0f);
        sprite.y = number(entry, "y", 0.0f);
        sprite.width = number(entry, "width", 0.0f);
        sprite.height = number(entry, "height", 0.0f);
        sprite.frameWidth = number(entry, "frameWidth", 0.0f);
        sprite.frameHeight = number(entry, "frameHeight", 0.0f);
        sprite.offsetX = -number(entry, "frameX", 0.0f);
        sprite.offsetY = -number(entry, "frameY", 0.0f);
        out.sprites[entry.value("name", std::string{})] = sprite;
    }
    return out;
}
} // namespace
Matrix matrixOf(const Transform& transform) {
    // skY is the angle of the x axis, skX the angle of the y axis; equal values are a plain
    // rotation, which is what the exported PvZ2 skeletons use.
    const float xAxis = transform.rotation * kDegrees;
    const float yAxis = transform.skewX * kDegrees;
    Matrix out;
    out.a = std::cos(xAxis) * transform.scaleX;
    out.b = std::sin(xAxis) * transform.scaleX;
    out.c = -std::sin(yAxis) * transform.scaleY;
    out.d = std::cos(yAxis) * transform.scaleY;
    out.tx = transform.x;
    out.ty = transform.y;
    return out;
}
Matrix operator*(const Matrix& parent, const Matrix& child) {
    Matrix out;
    out.a = parent.a * child.a + parent.c * child.b;
    out.b = parent.b * child.a + parent.d * child.b;
    out.c = parent.a * child.c + parent.c * child.d;
    out.d = parent.b * child.c + parent.d * child.d;
    out.tx = parent.a * child.tx + parent.c * child.ty + parent.tx;
    out.ty = parent.b * child.tx + parent.d * child.ty + parent.ty;
    return out;
}
Point apply(const Matrix& matrix, Point point) {
    return {matrix.a * point.x + matrix.c * point.y + matrix.tx,
            matrix.b * point.x + matrix.d * point.y + matrix.ty};
}
const Armature* Model::findArmature(const std::string& name) const {
    const auto it = armatures.find(name);
    return it == armatures.end() ? nullptr : &it->second;
}
const Animation* findAnimation(const Armature& armature, const std::string& name) {
    const auto it = armature.animations.find(name);
    return it == armature.animations.end() ? nullptr : &it->second;
}
const Animation* Model::findAnimation(const std::string& animation) const {
    return db::findAnimation(armature, animation);
}
Model loadModel(const std::filesystem::path& directory, const std::string& preferredArmature) {
    Model model;
    model.root = directory;
    const auto skeleton = readJson(directory / "skeleton.json");
    model.atlas = readAtlas(readJson(directory / "atlas.json"));
    if (std::filesystem::is_regular_file(directory / "meta.json")) {
        const auto meta = readJson(directory / "meta.json");
        model.key = meta.value("key", std::string{});
        if (preferredArmature.empty())
            model.armature.name = meta.value("armature", std::string{});
        else
            model.armature.name = preferredArmature;
    }
    const float skeletonFrameRate = number(skeleton, "frameRate", 24.0f);
    const auto list = skeleton.find("armature");
    if (list == skeleton.end() || !list->is_array() || list->empty())
        throw std::runtime_error(pathUtf8(directory) + ": skeleton.json has no armature");
    for (const auto& entry : *list) {
        Armature armature = readArmature(entry, skeletonFrameRate);
        if (model.armature.name == armature.name)
            model.armature = armature;
        model.armatures[armature.name] = std::move(armature);
    }
    const auto preferred = model.armatures.find(model.armature.name);
    if (preferred == model.armatures.end()) {
        model.armature = model.armatures.begin()->second;
    } else {
        model.armature = preferred->second;
    }
    if (model.armature.name.empty())
        throw std::runtime_error(pathUtf8(directory) + ": empty armature");
    if (!model.atlas.image.empty() && std::filesystem::is_regular_file(directory / model.atlas.image))
        model.texture = directory / model.atlas.image;
    else if (std::filesystem::is_regular_file(directory / "texture.png"))
        model.texture = directory / "texture.png";
    else
        throw std::runtime_error(pathUtf8(directory / "texture.png") + ": missing DragonBones texture");
    return model;
}
std::vector<std::string> animationNames(const Armature& armature) {
    std::vector<std::string> names;
    names.reserve(armature.animations.size());
    for (const auto& entry : armature.animations)
        names.push_back(entry.first);
    return names;
}
int Pose::indexOfBone(const Armature& armature, const std::string& name) const {
    for (std::size_t i = 0; i < armature.bones.size(); ++i)
        if (armature.bones[i].name == name)
            return static_cast<int>(i);
    return -1;
}
Pose evaluate(const Model& model, const Armature& armature, const std::string& animationName, float seconds) {
    (void)model;
    Pose pose;
    const auto& bones = armature.bones;
    std::vector<Transform> local(bones.size());
    for (std::size_t i = 0; i < bones.size(); ++i)
        local[i] = bones[i].transform;
    pose.display.resize(armature.slots.size(), -1);
    pose.alpha.resize(armature.slots.size(), 1.0f);
    for (std::size_t i = 0; i < armature.slots.size(); ++i) {
        pose.display[i] = armature.slots[i].displayIndex;
        pose.alpha[i] = armature.slots[i].alpha / 255.0f;
    }
    const Animation* animation = findAnimation(armature, animationName);
    if (animation == nullptr)
        animation = findAnimation(armature, armature.defaultAnimation);
    if (animation == nullptr && !armature.animations.empty())
        animation = &armature.animations.begin()->second;
    if (animation != nullptr) {
        const float frameRate = animation->frameRate > 0 ? animation->frameRate : armature.frameRate;
        float frame = seconds * frameRate;
        if (animation->duration > 0) {
            frame = std::fmod(frame, static_cast<float>(animation->duration));
            if (frame < 0)
                frame += static_cast<float>(animation->duration);
        }
        for (const auto& timeline : animation->bones) {
            const auto index = static_cast<std::size_t>(timeline.bone);
            Transform& transform = local[index];
            if (timeline.translate.present) {
                const Sampled value = sample(timeline.translate, frame);
                transform.x += value.x;
                transform.y += value.y;
            }
            if (timeline.rotate.present) {
                const Sampled value = sample(timeline.rotate, frame);
                transform.rotation += value.rotation;
            }
            if (timeline.scale.present) {
                const Sampled value = sample(timeline.scale, frame);
                transform.scaleX *= value.scaleX;
                transform.scaleY *= value.scaleY;
            }
        }
        for (const auto& timeline : animation->slots) {
            const auto index = static_cast<std::size_t>(timeline.slot);
            int displayIndex = -2;
            for (const auto& entry : timeline.display)
                if (frame >= static_cast<float>(entry.first) && entry.second != -2)
                    displayIndex = entry.second;
            if (displayIndex != -2)
                pose.display[index] = displayIndex;
            float alphaValue = -1.0f;
            for (const auto& entry : timeline.alpha) {
                if (frame >= static_cast<float>(entry.first) && entry.second >= 0.0f)
                    alphaValue = entry.second;
            }
            if (alphaValue >= 0.0f)
                pose.alpha[index] *= alphaValue;
        }
    }
    std::vector<int> depth(bones.size(), 0);
    for (std::size_t i = 0; i < bones.size(); ++i) {
        int current = static_cast<int>(i), steps = 0;
        while (current >= 0 && steps < static_cast<int>(bones.size())) {
            const int parent = bones[static_cast<std::size_t>(current)].parent;
            if (parent < 0)
                break;
            depth[i] += 1;
            current = parent;
            steps += 1;
        }
    }
    std::vector<std::size_t> order(bones.size());
    for (std::size_t i = 0; i < order.size(); ++i)
        order[i] = i;
    std::stable_sort(order.begin(), order.end(),
                     [&depth](std::size_t left, std::size_t right) { return depth[left] < depth[right]; });
    pose.bones.assign(bones.size(), Matrix{});
    for (const auto index : order) {
        const Matrix localMatrix = matrixOf(local[index]);
        const int parent = bones[index].parent;
        if (parent >= 0 && static_cast<std::size_t>(parent) < pose.bones.size() && parent != static_cast<int>(index))
            pose.bones[index] = pose.bones[static_cast<std::size_t>(parent)] * localMatrix;
        else
            pose.bones[index] = localMatrix;
    }
    pose.slots.assign(armature.slots.size(), Matrix{});
    for (std::size_t i = 0; i < armature.slots.size(); ++i) {
        const auto& slot = armature.slots[i];
        Matrix base;
        if (slot.bone >= 0 && static_cast<std::size_t>(slot.bone) < pose.bones.size())
            base = pose.bones[static_cast<std::size_t>(slot.bone)];
        const int display = pose.display[i];
        if (display >= 0 && static_cast<std::size_t>(display) < slot.displays.size())
            pose.slots[i] = base * matrixOf(slot.displays[static_cast<std::size_t>(display)].transform);
        else
            pose.slots[i] = base;
    }
    return pose;
}
} // namespace pvz::db
