#include "assets.hpp"
#include "dragonbones.hpp"
#include <cmath>
#include <filesystem>
#include <iostream>
#include <stdexcept>
namespace fs = std::filesystem;
namespace {
void require(bool ok, const std::string& message) {
    if (!ok)
        throw std::runtime_error(message);
}
bool finite(const pvz::db::Matrix& matrix) {
    return std::isfinite(matrix.a) && std::isfinite(matrix.b) && std::isfinite(matrix.c) &&
           std::isfinite(matrix.d) && std::isfinite(matrix.tx) && std::isfinite(matrix.ty);
}
} // namespace
int main(int argc, char** argv) {
    try {
        if (argc != 2)
            throw std::runtime_error("expected the assets directory");
        const fs::path assets = argv[1];
        const auto plant = pvz::db::loadModel(assets / "db/plants/PeashooterPLANT");
        require(plant.armature.name == "Peashooter", "unexpected armature name " + plant.armature.name);
        require(plant.atlas.sprites.size() >= 20, "atlas lost subtextures");
        require(pvz::db::findAnimation(plant.armature, "Idle") != nullptr, "missing Idle animation");
        require(pvz::db::findAnimation(plant.armature, "Shoot") != nullptr, "missing Shoot animation");
        require(fs::is_regular_file(plant.texture), "model texture does not exist");
        require(plant.armature.bones.size() >= 4, "peashooter skeleton lost bones: " +
                                                      std::to_string(plant.armature.bones.size()));
        const auto first = pvz::db::evaluate(plant, "Idle", 0.0f);
        const auto later = pvz::db::evaluate(plant, "Idle", 0.6f);
        require(first.bones.size() == plant.armature.bones.size(), "pose bone count mismatch");
        require(first.slots.size() == plant.armature.slots.size(), "pose slot count mismatch");
        require(first.display.size() == plant.armature.slots.size(), "pose display count mismatch");
        for (const auto& matrix : first.bones)
            require(finite(matrix), "non-finite bone matrix");
        bool animated = false;
        for (std::size_t index = 0; index < first.bones.size(); ++index)
            if (std::abs(first.bones[index].tx - later.bones[index].tx) > 1e-4f ||
                std::abs(first.bones[index].ty - later.bones[index].ty) > 1e-4f)
                animated = true;
        require(animated, "Idle animation did not move any bone");
        std::size_t visible = 0;
        for (const int display : first.display)
            if (display >= 0)
                ++visible;
        require(visible > 0, "idle pose hides every slot");
        for (std::size_t index = 0; index < first.display.size(); ++index) {
            const int display = first.display[index];
            require(display < static_cast<int>(plant.armature.slots[index].displays.size()),
                    "display index outside the skin");
        }

        const auto zombie = pvz::db::loadModel(assets / "db/zombies/BasicZOMBIE");
        require(zombie.armature.name == "BasicZombie", "unexpected zombie armature");
        require(zombie.armatures.size() >= 12, "shared zombie skeleton lost armatures");
        require(zombie.findArmature("Cone") != nullptr, "missing Cone armature");
        require(zombie.findArmature("Bucket") != nullptr, "missing Bucket armature");
        require(pvz::db::findAnimation(zombie.armature, "Walk") != nullptr, "missing Walk animation");
        const auto cone = pvz::db::loadModel(assets / "db/zombies/BasicZOMBIE", "Cone");
        require(cone.armature.name == "Cone", "preferred armature was not selected");
        require(!cone.armature.slots.empty(), "Cone armature has no slots");
        require(!cone.armature.slots[0].displays.empty(), "Cone armature has no displays");
        std::size_t resolved = 0;
        for (const auto& slot : cone.armature.slots)
            for (const auto& display : slot.displays)
                if (pvz::findSprite(cone.atlas, display) != nullptr)
                    ++resolved;
        require(resolved > 0, "no Cone armor display resolves into the atlas");
        const auto walking = pvz::db::evaluate(zombie, "Walk", 0.35f);
        require(walking.bones.size() == zombie.armature.bones.size(), "zombie pose bone count mismatch");
        for (const auto& matrix : walking.bones)
            require(finite(matrix), "non-finite zombie bone matrix");
        std::cout << "PASS dragonbones plant=" << plant.armature.name << " bones=" << plant.armature.bones.size()
                  << " sprites=" << plant.atlas.sprites.size() << " zombieArmatures=" << zombie.armatures.size()
                  << " armorDisplays=" << cone.armature.slots[0].displays.size() << '\n';
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "FAIL " << error.what() << '\n';
        return 1;
    }
}
