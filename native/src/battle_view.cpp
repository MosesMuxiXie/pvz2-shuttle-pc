#include "battle_view.hpp"
#include "actor_view.hpp"
#include "assets.hpp"
#include "audio/audio_runtime.hpp"
#include "content/model.hpp" // the pack lookups need the complete ContentPack, not catalog.hpp's fwd decl
#include "drag_plant.hpp"    // T50: drag-to-plant state machine (SDL-free, unit tested)
#include "engine/armor.hpp"  // S5.11: armor layer -> gear armature
#include "sdl_support.hpp"
#include "text.hpp"
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <map>
#include <memory>
#include <set>
#include <string>
#include <vector>

namespace pvz {
namespace {
constexpr float boardX = 190, boardY = 120, cellW = 100, cellH = 100;
constexpr float plantScale = 0.62f;
constexpr float zombieScale = 0.58f;
constexpr float armorScale = 0.58f;
const SDL_Color cream{244, 236, 205, 255};
const SDL_Color ink{26, 32, 26, 255};
const SDL_Color leaf{126, 196, 108, 255};
const SDL_Color gold{255, 214, 92, 255};

void color(SDL_Renderer* r, Uint8 red, Uint8 green, Uint8 blue, Uint8 alpha = 255) {
    sdl::require(SDL_SetRenderDrawColor(r, red, green, blue, alpha), "set battle color");
}
void rect(SDL_Renderer* r, float x, float y, float w, float h, SDL_Color tint) {
    color(r, tint.r, tint.g, tint.b, tint.a);
    const SDL_FRect box{x, y, w, h};
    sdl::require(SDL_RenderFillRect(r, &box), "draw battle rectangle");
}
void circle(SDL_Renderer* r, float x, float y, int radius, SDL_Color tint) {
    color(r, tint.r, tint.g, tint.b, tint.a);
    for (int dy = -radius; dy <= radius; ++dy) {
        const auto dx = std::sqrt(static_cast<float>(radius * radius - dy * dy));
        sdl::require(SDL_RenderLine(r, x - dx, y + static_cast<float>(dy), x + dx,
                                    y + static_cast<float>(dy)),
                     "draw battle circle");
    }
}
std::string zhName(const Catalog& catalog, const std::string& type) {
    const auto found = catalog.plants.find(type);
    if (found == catalog.plants.end())
        return type;
    const auto raw = found->second.raw.find("name_zh");
    if (raw != found->second.raw.end() && raw->is_string())
        return raw->get<std::string>();
    return found->second.name.empty() ? type : found->second.name;
}
std::string plantArt(const Catalog& catalog, const std::string& type) {
    const auto found = catalog.plants.find(type);
    return found == catalog.plants.end() ? std::string{} : found->second.art;
}
std::string zombieArt(const Catalog& catalog, const std::string& type) {
    const auto found = catalog.zombies.find(type);
    return found == catalog.zombies.end() ? std::string{} : found->second.art;
}
/// The pack key the resolver joins the SHUTTLE index on. Empty without a rules pack.
std::string plantPopAnim(const Catalog& catalog, const std::string& type) {
    if (!catalog.rules)
        return {};
    const auto* definition = catalog.rules->findPlant(type);
    return definition == nullptr ? std::string{} : definition->popAnim;
}
std::string zombiePopAnim(const Catalog& catalog, const std::string& type) {
    if (!catalog.rules)
        return {};
    const auto* definition = catalog.rules->findZombie(type);
    return definition == nullptr ? std::string{} : definition->popAnim;
}
std::string firstAnimation(AssetCache& cache, const std::string& model,
                           std::initializer_list<const char*> candidates, std::string* error = nullptr) {
    if (model.empty())
        return {};
    const auto asset = cache.tryModel(model, {}, error);
    if (asset.model == nullptr)
        return {};
    for (const char* name : candidates)
        if (db::findAnimation(asset.model->armature, name) != nullptr)
            return name;
    return asset.model->armature.defaultAnimation;
}
// Artwork is optional at runtime: a broken model falls back to the shape stand-in and is
// reported once, so one bad export never takes the whole battle view down.
std::string reportOnce(std::set<std::string>& reported, std::string message) {
    if (!message.empty() && reported.insert(message).second)
        std::fprintf(stderr, "warning: %s\n", message.c_str());
    return message;
}
/// Every reason `World::plant()` can return, plus the empty string for success. Keeping the
/// mapping here (rather than in the kernel) means the engine never carries UI text.
std::string localized(const std::string& code) {
    if (code.empty())
        return "已种植。";
    if (code == "cell occupied")
        return "这个格子已经有植物了。";
    if (code == "cooling down")
        return "这张卡还在冷却。";
    if (code == "not enough sun")
        return "阳光不够。";
    if (code == "cell out of bounds")
        return "超出草坪范围。";
    if (code == "not-in-deck")
        return "这张卡不在本关卡组。";
    if (code == "level finished")
        return "这一局已经结束了。";
    if (code == "too many plants")
        return "场上的植物太多了。";
    if (code.rfind("unknown plant", 0) == 0)
        return "这里还没有这种植物。";
    return code;
}
std::string statusText(const std::string& status) {
    if (status == "playing")
        return "战斗中";
    if (status == "won")
        return "关卡完成";
    if (status == "lost")
        return "已失守";
    return status;
}
std::string clockText(std::uint64_t ticks) {
    const auto total = static_cast<long long>(ticks / 60);
    char buffer[32];
    std::snprintf(buffer, sizeof(buffer), "%lld:%02lld", total / 60, total % 60);
    return buffer;
}
/// The seed bank shows the level deck; a level without one falls back to the four cards the
/// preview has always shipped, because an empty bank leaves the player with nothing to click.
std::vector<std::string> deckOf(const Catalog& catalog, const LevelDefinition& level) {
    std::vector<std::string> deck;
    for (const auto& card : level.deck)
        if (catalog.plants.find(card) != catalog.plants.end())
            deck.push_back(card);
    if (!deck.empty())
        return deck;
    for (const char* card : {"sunflower", "peashooter", "wallnut", "potatomine"})
        if (catalog.plants.find(card) != catalog.plants.end())
            deck.emplace_back(card);
    return deck;
}
float cardStep(std::size_t count) {
    return count <= 7 ? 148.0f : std::max(112.0f, 1120.0f / static_cast<float>(count));
}
float cardBody(std::size_t count) { return std::min(138.0f, cardStep(count) - 8.0f); }
std::uint64_t ticksOf(double seconds) {
    return static_cast<std::uint64_t>(seconds / engine::World::stepSeconds + 0.5);
}
sdl::Texture loadLawn(SDL_Renderer* renderer, const std::filesystem::path& assetRoot) {
    const auto lawnPath = assetRoot / "lawn" / "frontyard.png";
    if (!std::filesystem::is_regular_file(lawnPath))
        throw std::runtime_error(pathUtf8(lawnPath) + ": missing battle lawn");
    return sdl::texture(renderer, lawnPath);
}
} // namespace

/// Owns the rendering side of a battle: one `engine::World`, one surface, one deck.
/// Both entry points (`--play` and `--play-script`) draw through this class, so the
/// screenshot a test compares is the same view a player sees.
class BattleScene {
  public:
    BattleScene(const Catalog& catalog, const LevelDefinition& level, const std::filesystem::path& assetRoot,
                bool headless, const char* title, std::uint32_t seed)
        : catalog_(catalog), level_(level), world_(std::make_unique<engine::World>(catalog, level, seed)),
          seed_(seed), display_(headless, title),
          lawn_(loadLawn(display_.renderer.get(), assetRoot)),
          sunArt_(sdl::texture(display_.renderer.get(), assetRoot / "ui/sun.png")),
          panelArt_(sdl::texture(display_.renderer.get(), assetRoot / "ui/panel.png")),
          assets_(display_.renderer.get(), assetRoot),
          text_(display_.renderer.get(), assetRoot / "ui/font_zh.ttc"),
          deck_(deckOf(catalog, level)), started_(headless) {
        for (const auto& card : deck_) {
            std::string error;
            plantIdle_[card] = firstAnimation(assets_, plantModel(card), {"Idle", "Idle1", "Idle2"},
                                              &error);
            reportOnce(reported_, error);
        }
        plantShoot_["peashooter"] =
            firstAnimation(assets_, plantModel("peashooter"), {"Shoot", "Idle", "Idle1"});
        message_ = "先点一张卡，再点草坪格子。";
        previousNs_ = SDL_GetTicksNS();
        // A screenshot run attaches in `headless` mode, which never opens a device: the pixels
        // below stay byte-identical whether or not this build has a sound card.
        attachAudio(assetRoot, headless);
        playAudioMusicForWorld(level_.world);
    }

    engine::World& world() { return *world_; }
    const std::vector<std::string>& deck() const { return deck_; }
    bool quit() const { return quit_; }

    void reset() {
        world_ = std::make_unique<engine::World>(catalog_, level_, seed_);
        selected_ = -1;
        shovel_ = false;
        drag_.cancel();
        message_ = "先点一张卡，再点草坪格子。";
        // A fresh world starts a fresh event stream, so the old cursor would skip its first wave.
        audioCursor_ = 0;
    }

    /// The scripted demo the smoke test renders: three plants, all suns collected, 1800 ticks.
    void runDemo() {
        (void)world_->plant("sunflower", 0, 0);
        (void)world_->plant("peashooter", 0, 2);
        for (int i = 0; i < 1800; ++i) {
            if (i % 60 == 0) {
                // Collect by id first: `collect` erases from `suns_`, so iterating the live
                // vector would skip entries (the legacy view had the same shape).
                std::vector<engine::EntityId> ids;
                for (const auto& sun : world_->suns()) ids.push_back(sun.id);
                for (auto id : ids) (void)world_->collect(id);
                if (i > 360) (void)world_->plant("sunflower", 1, 0);
                if (i > 720) (void)world_->plant("peashooter", 1, 2);
                if (i > 1200) (void)world_->plant("wallnut", 1, 5);
            }
            world_->step();
        }
    }

    void pollEvents() {
        SDL_Event event;
        while (SDL_PollEvent(&event)) handleEvent(event);
    }

    void advanceFrame() {
        const auto now = SDL_GetTicksNS();
        const double dt = static_cast<double>(now - previousNs_) / 1e9;
        previousNs_ = now;
        // Audio is drained before the pause check: a paused battle still owes the click that
        // paused it, and the queue has to be topped up or the music stutters.
        audioCursor_ = consumeAudioEvents(world_->events(), audioCursor_);
        pumpAudio();
        if (!started_ || world_->paused() || world_->finished()) return;
        world_->advance(std::min(dt, 0.25));
    }

    void drawFrame() {
        const auto snap = world_->snapshot();
        auto* r = display_.renderer.get();
        color(r, 15, 22, 24);
        sdl::require(SDL_RenderClear(r), "clear battle");
        const SDL_FRect full{0, 0, 1280, 720};
        sdl::require(SDL_RenderTexture(r, lawn_.get(), nullptr, &full), "draw lawn");
        sdl::require(SDL_SetRenderDrawBlendMode(r, SDL_BLENDMODE_BLEND), "set blend mode");
        for (int row = 0; row < snap.rows; ++row)
            for (int col = 0; col < snap.cols; ++col) {
                const SDL_FRect tile{boardX + static_cast<float>(col) * cellW,
                                     boardY + static_cast<float>(row) * cellH, cellW, cellH};
                if ((row + col) % 2 == 0) {
                    color(r, 255, 255, 230, 16);
                    sdl::require(SDL_RenderFillRect(r, &tile), "draw tile fill");
                }
                color(r, 20, 44, 24, 56);
                sdl::require(SDL_RenderRect(r, &tile), "draw tile border");
            }
        // T50: the cell under the pointer while a card is being dragged.
        drawDragPreview();
        const float seconds = static_cast<float>(snap.tick) / 60.0f;
        for (const auto& p : snap.plants) {
            const float anchorX = boardX + (static_cast<float>(p.col) + 0.5f) * cellW;
            const float anchorY = boardY + (static_cast<float>(p.row) + 1.0f) * cellH - 14.0f;
            circle(r, anchorX, anchorY + 2, 30, SDL_Color{12, 26, 12, 70});
            ActorPose pose;
            pose.model = plantModel(p.type);
            pose.x = anchorX;
            pose.y = anchorY;
            pose.scale = plantScale;
            pose.seconds = seconds + static_cast<float>(p.id % 7);
            const auto idle = plantIdle_.find(p.type);
            pose.animation = idle == plantIdle_.end() ? std::string{"Idle"} : idle->second;
            if (p.type == "peashooter") {
                const auto shoot = plantShoot_.find("peashooter");
                // `busyTicks` is the ticks left on the plant's next action: the volley is
                // about to leave when it drops under 16.
                if (shoot != plantShoot_.end() && p.busyTicks > 0 && p.busyTicks < 16)
                    pose.animation = shoot->second;
            }
            if (drawActor(r, assets_, pose) == 0)
                circle(r, anchorX, anchorY - 26, 24, SDL_Color{70, 176, 84, 255});
            if (p.hp < p.maxHp * 0.999) {
                rect(r, anchorX - 30, anchorY + 6, 60, 5, SDL_Color{22, 34, 20, 190});
                rect(r, anchorX - 30, anchorY + 6,
                     static_cast<float>(60.0 * p.hp / std::max(p.maxHp, 1.0)), 5,
                     SDL_Color{126, 220, 108, 255});
            }
        }
        for (const auto& z : snap.zombies) {
            const float anchorX = boardX + static_cast<float>(z.x) * cellW;
            const float anchorY = boardY + (static_cast<float>(z.row) + 1.0f) * cellH - 10.0f;
            circle(r, anchorX, anchorY + 2, 30, SDL_Color{12, 18, 14, 84});
            ActorPose pose;
            pose.model = zombieModel(z.type);
            pose.x = anchorX;
            pose.y = anchorY;
            pose.scale = zombieScale;
            pose.flip = true;
            pose.seconds = seconds + static_cast<float>(z.id % 11) * 0.37f;
            const auto walk = zombieWalkOf(z.type);
            pose.animation = walk.empty() ? std::string{"Walk"} : walk;
            const bool armored = z.armor > 0;
            if (drawActor(r, assets_, pose) == 0)
                rect(r, anchorX - 18, anchorY - 60, 36, 60, SDL_Color{112, 140, 104, 255});
            if (armored) {
                ActorPose gear;
                gear.model = pose.model;
                bool metalArmor = false;
                // S5.11: the bone name now comes from the armor layer, not from the zombie id.
                gear.armature = zombieArmorArmature(z, metalArmor);
                gear.scale = armorScale;
                gear.flip = true;
                gear.seconds = pose.seconds;
                float headX = anchorX, headY = anchorY - 120.0f;
                if (actorBonePosition(assets_, pose, "head", headX, headY)) {
                    gear.x = headX;
                    gear.y = headY;
                } else {
                    gear.x = anchorX;
                    gear.y = anchorY - 120.0f;
                }
                if (drawActor(r, assets_, gear) == 0) {
                    // Stand-in shape keyed on the `metallic` flag rather than the zombie id: the
                    // sheet says which armors are metal, so a new metal armor draws right without
                    // another hardcoded name here.
                    if (metalArmor) {
                        rect(r, anchorX - 22, anchorY - 150, 44, 34, SDL_Color{172, 178, 186, 255});
                    } else {
                        rect(r, anchorX - 22, anchorY - 150, 44, 22, SDL_Color{232, 128, 34, 255});
                        rect(r, anchorX - 12, anchorY - 168, 24, 20, SDL_Color{240, 168, 62, 255});
                    }
                }
            }
            const double total = zombieTotal(z);
            const double remaining = z.hp + z.armor;
            rect(r, anchorX - 26, anchorY + 4, 52, 5, SDL_Color{30, 18, 18, 170});
            rect(r, anchorX - 26, anchorY + 4,
                 static_cast<float>(52.0 * std::clamp(remaining / total, 0.0, 1.0)), 5,
                 SDL_Color{226, 82, 62, 255});
        }
        for (const auto& shot : snap.shots) {
            ActorPose pose;
            pose.model = "db/projectiles/Pea0PRJ";
            pose.x = boardX + static_cast<float>(shot.x) * cellW;
            pose.y = boardY + (static_cast<float>(shot.row) + 0.62f) * cellH;
            pose.scale = 0.55f;
            pose.seconds = seconds;
            if (drawActor(r, assets_, pose) == 0)
                circle(r, pose.x, pose.y - 24, 8, SDL_Color{150, 232, 96, 255});
        }
        for (const auto& mower : snap.mowers)
            if (mower.state < 2) {
                const float x = boardX + static_cast<float>(mower.x) * cellW,
                            y = boardY + (static_cast<float>(mower.row) + 0.78f) * cellH;
                rect(r, x - 24, y - 16, 48, 22, SDL_Color{186, 44, 38, 255});
                rect(r, x - 24, y - 2, 48, 6, SDL_Color{120, 24, 22, 255});
                circle(r, x - 14, y + 10, 7, SDL_Color{34, 34, 34, 255});
                circle(r, x + 14, y + 10, 7, SDL_Color{34, 34, 34, 255});
            }
        for (const auto& sun : snap.suns) {
            const float x = boardX + static_cast<float>(sun.x) * cellW;
            const float y = boardY + static_cast<float>(sun.y) * cellH;
            const float pulse = 1.0f + 0.06f * std::sin(seconds * 3.0f + static_cast<float>(sun.id));
            const float size = 54.0f * pulse;
            const SDL_FRect body{x - size / 2, y - size / 2, size, size};
            sdl::require(SDL_RenderTexture(r, sunArt_.get(), nullptr, &body), "draw sun");
        }
        const SDL_FRect topBar{0, 0, 1280, 112};
        // Nine-slice keeps the panel frame from smearing when stretched across the screen.
        sdl::require(SDL_RenderTexture9Grid(r, panelArt_.get(), nullptr, 48, 48, 48, 48, 1.0f, &topBar),
                     "draw HUD panel");
        color(r, 12, 26, 22, 150);
        sdl::require(SDL_RenderFillRect(r, &topBar), "tint HUD panel");
        const SDL_FRect sunIcon{16, 22, 62, 62};
        sdl::require(SDL_RenderTexture(r, sunArt_.get(), nullptr, &sunIcon), "draw sun counter icon");
        text_.draw(86, 26, 34, cream, std::to_string(snap.sun));
        const std::size_t count = deck_.size();
        const float step = cardStep(count), body = cardBody(count);
        for (std::size_t i = 0; i < count; ++i) {
            const auto& card = deck_[i];
            const float x = 150 + static_cast<float>(i) * step;
            const double cost = static_cast<double>(catalog_.plants.at(card).cost);
            const bool affordable = static_cast<double>(snap.sun) >= cost;
            // Drawn packet: rim, body and a hint of shading, so no pre-rendered plant art leaks in.
            rect(r, x - 2, 10, body + 4, 88, SDL_Color{246, 236, 206, 255});
            rect(r, x, 12, body, 84, SDL_Color{96, 66, 38, 255});
            rect(r, x + 3, 15, body - 6, 78, affordable ? SDL_Color{150, 112, 62, 255}
                                                        : SDL_Color{104, 82, 60, 255});
            rect(r, x + 3, 15, body - 6, 40, affordable ? SDL_Color{168, 128, 74, 255}
                                                        : SDL_Color{118, 96, 74, 255});
            if (selected_ == static_cast<int>(i))
                rect(r, x, 12, body, 84, SDL_Color{255, 236, 150, 80});
            const auto model = plantModel(card);
            if (!model.empty()) {
                ActorPose pose;
                pose.model = model;
                pose.x = x + body * 0.26f;
                pose.y = 96;
                pose.scale = 0.3f;
                pose.seconds = seconds;
                const auto idle = plantIdle_.find(card);
                pose.animation = idle == plantIdle_.end() ? std::string{"Idle"} : idle->second;
                if (drawActor(r, assets_, pose) == 0)
                    circle(r, pose.x, pose.y - 24, 16, leaf);
            }
            const std::string name = zhName(catalog_, card);
            const float textX = x + body * 0.5f;
            int nameSize = 17;
            while (nameSize > 11 && text_.width(name, nameSize) > body * 0.45f)
                --nameSize;
            text_.draw(textX, 16, nameSize, SDL_Color{252, 246, 224, 255}, name);
            text_.draw(textX, 44, 15, SDL_Color{255, 232, 168, 255}, std::to_string(catalog_.plants.at(card).cost));
            text_.draw(textX + body * 0.3f, 44, 15, SDL_Color{226, 206, 160, 235}, "阳");
            text_.drawCentered(x + body * 0.5f, 72, 13, SDL_Color{240, 228, 198, 220},
                               std::to_string(i + 1));
            const auto readyTick = world_->cooldown(card);
            const std::uint64_t remaining = readyTick > snap.tick ? readyTick - snap.tick : 0;
            if (remaining > 0) {
                const double fullCooldown = static_cast<double>(ticksOf(catalog_.plants.at(card).cooldown));
                const float fraction =
                    std::clamp(static_cast<float>(static_cast<double>(remaining) / std::max(fullCooldown, 1.0)), 0.0f, 1.0f);
                rect(r, x, 12, body, 84.0f * fraction, SDL_Color{16, 24, 20, 170});
                text_.drawCentered(x + body * 0.5f, 40, 20, cream,
                                   std::to_string((remaining + 59) / 60) + "s");
            }
        }
        text_.draw(748, 18, 18, cream,
                   "第 " + std::to_string(snap.wave) + " / " + std::to_string(snap.waves) + " 波");
        text_.draw(748, 46, 16, SDL_Color{206, 220, 198, 255},
                   "剩余僵尸 " + std::to_string(snap.zombies.size()) + " · 阳光 " + std::to_string(snap.sun));
        text_.draw(748, 72, 15, SDL_Color{184, 198, 176, 255},
                   "状态：" + statusText(snap.status) + " · " + clockText(snap.tick) + " · tick " +
                       std::to_string(snap.tick));
        const SDL_Color shovelTint = shovel_ ? SDL_Color{186, 138, 64, 255} : SDL_Color{58, 74, 62, 235};
        rect(r, 946, 20, 134, 56, shovelTint);
        text_.drawCentered(1013, 26, 20, cream, "铲子");
        text_.drawCentered(1013, 57, 12, SDL_Color{216, 226, 208, 220}, "S");
        const SDL_Color pauseTint =
            world_->paused() ? SDL_Color{164, 96, 58, 255} : SDL_Color{52, 76, 70, 235};
        rect(r, 1092, 20, 154, 56, pauseTint);
        text_.drawCentered(1169, 26, 20, cream, world_->paused() ? "继续" : "暂停");
        text_.drawCentered(1169, 57, 12, SDL_Color{216, 226, 208, 220}, "空格");
        rect(r, 0, 664, 1280, 56, SDL_Color{14, 26, 24, 242});
        text_.draw(20, 670, 16, SDL_Color{206, 220, 198, 255},
                   "1-8 选卡 · 点击阳光收集 · 右键取消 · 空格暂停 · R 重开 · S 铲子");
        text_.draw(20, 692, 16, gold, message_);
        // The resolver counts every actor it could not place; surfacing the number keeps a
        // half-extracted asset tree visible instead of merely quiet.
        std::string footer = "原生战斗内核 · 不写入存档";
        if (assets_.missingArt() > 0)
            footer += " · 缺美术 " + std::to_string(assets_.missingArt());
        text_.draw(880, 680, 14, SDL_Color{150, 168, 148, 210}, footer);
        if (!started_ || world_->paused() || snap.status != "playing") {
            rect(r, 300, 240, 680, 290, SDL_Color{8, 18, 17, 226});
            const std::string title = !started_ ? "前院 · 第 1 天"
                                      : world_->paused() ? "已暂停"
                                      : snap.status == "won" ? "关卡完成"
                                                             : "僵尸吃掉了你的脑子";
            text_.drawCentered(640, 280, 38, SDL_Color{245, 228, 168, 255}, title);
            const std::string subtitle =
                !started_ ? "点击卡组种植 · 初始阳光来自关卡"
                : world_->paused() ? "按空格或点击暂停按钮继续。"
                : snap.status == "won" ? "按 R 重开一局，不保存进度。"
                                       : "按 R 重试，不保存进度。";
            text_.drawCentered(640, 344, 19, SDL_Color{216, 230, 212, 255}, subtitle);
            if (!started_) {
                rect(r, 440, 430, 400, 60, SDL_Color{73, 126, 67, 255});
                text_.drawCentered(640, 444, 26, SDL_Color{250, 245, 215, 255}, "开始 [空格]");
            }
        }
    }

    void writeSnapshot(const std::filesystem::path& path) {
        sdl::Surface pixels(SDL_RenderReadPixels(display_.renderer.get(), nullptr), SDL_DestroySurface);
        sdl::require(bool(pixels), "read frame");
        // `--snapshot out.png` has to be a real PNG: the CLI names the file and a BMP payload
        // behind a .png extension would break every downstream viewer.
        const auto extension = path.extension().string();
        if (extension == ".png" || extension == ".PNG")
            sdl::require(IMG_SavePNG(pixels.get(), pathUtf8(path).c_str()), pathUtf8(path) + ": save snapshot");
        else
            sdl::require(SDL_SaveBMP(pixels.get(), pathUtf8(path).c_str()), pathUtf8(path) + ": save snapshot");
    }
    void present() { sdl::require(SDL_RenderPresent(display_.renderer.get()), "present battle"); }

  private:
    /// Every model lookup goes through the resolver: `db/<art>` (legacy web export) first, then
    /// the SHUTTLE index joined on the pack's `popAnim`. A miss is reported once, counted by the
    /// asset cache, and drawn as the existing shape stand-in rather than silently skipped.
    std::string modelOf(bool plant, const std::string& type) {
        const std::string art = plant ? plantArt(catalog_, type) : zombieArt(catalog_, type);
        const std::string popAnim =
            plant ? plantPopAnim(catalog_, type) : zombiePopAnim(catalog_, type);
        const auto resolution = assets_.art(art, popAnim);
        if (resolution.hit())
            return resolution.dir;
        reportOnce(reported_, std::string(plant ? "plant " : "zombie ") + type +
                                  ": no artwork for " +
                                  (art.empty() ? std::string{"<no art key>"} : art) +
                                  (popAnim.empty() ? std::string{} : " / " + popAnim));
        return {};
    }
    std::string plantModel(const std::string& type) { return modelOf(true, type); }
    std::string zombieModel(const std::string& type) { return modelOf(false, type); }
    std::string zombieWalkOf(const std::string& type) {
        const auto found = zombieWalk_.find(type);
        if (found != zombieWalk_.end())
            return found->second;
        std::string error;
        const std::string animation =
            firstAnimation(assets_, zombieModel(type), {"Walk", "_Walk", "Idle"}, &error);
        reportOnce(reported_, error);
        return zombieWalk_.emplace(type, animation).first->second;
    }
    /// S5.11: which armature to draw on the head. The armor sheet names the layer
    /// (`zombie_armor_bucket_norm`), but content models declare their armor armatures as
    /// "Cone"/"Bucket" — the sheet's names only exist on SHUTTLE-derived rigs. So the sheet name
    /// is used only when the loaded model really declares that armature; otherwise the content
    /// `armature`; otherwise the pre-S5.11 default. 13 of the 102 armors carry no ArmorLayers at
    /// all (`counts.withoutArmorLayer`) and 45 of the 55 content zombies have no bridge row, so
    /// the content fallback is the common path, not the exception.
    std::string zombieArmorArmature(const engine::ZombieView& z, bool& metallic) {
        metallic = false;
        std::string contentArmature;
        const auto definition = catalog_.zombies.find(z.type);
        if (definition != catalog_.zombies.end()) {
            const Json& raw = definition->second.raw;
            const auto armor = raw.find("armor");
            if (armor != raw.end() && armor->is_array() && !armor->empty()) {
                const Json& first = armor->front();
                if (first.is_object()) {
                    const auto armature = first.find("armature");
                    if (armature != first.end() && armature->is_string())
                        contentArmature = armature->get<std::string>();
                    const auto metal = first.find("metal");
                    if (metal != first.end() && metal->is_boolean()) metallic = metal->get<bool>();
                }
            }
        }
        const auto& table = engine::ArmorTable::shared();
        std::vector<engine::ArmorLayer> layers = table.contentArmorLayers(z.type);
        if (layers.empty()) layers = table.zombieArmorLayers(z.type);
        const std::string fallback = contentArmature.empty() ? std::string{"Cone"} : contentArmature;
        if (layers.empty()) return fallback;
        const engine::ArmorLayer& outer = layers.front(); // sheet order, never sorted
        metallic = metallic || outer.metallic();
        if (!outer.artLayer.empty()) {
            const auto asset = assets_.model(zombieModel(z.type));
            if (asset.model != nullptr && asset.model->findArmature(outer.artLayer) != nullptr)
                return outer.artLayer;
        }
        if (contentArmature.empty())
            reportOnce(reported_, "zombie " + z.type + ": armor layer " +
                                      (outer.artLayer.empty() ? std::string{"<no layer>"} : outer.artLayer) +
                                      " is not in the model, drawing the default cone");
        return fallback;
    }
    double zombieTotal(const engine::ZombieView& z) const {
        const auto definition = catalog_.zombies.find(z.type);
        if (definition == catalog_.zombies.end())
            return std::max(z.maxHp + z.armor, 1.0);
        const double armor = definition->second.armor.empty() ? 0.0 : definition->second.armor.front();
        return std::max(definition->second.hp + armor, 1.0);
    }
    /// The board numbers this view draws with, handed to the drag unit so the preview and the
    /// plant land in the same cell.
    ui::DragGeometry dragGeometry() const {
        ui::DragGeometry geometry;
        geometry.boardX = boardX;
        geometry.boardY = boardY;
        geometry.cellW = cellW;
        geometry.cellH = cellH;
        geometry.cols = world_->cols();
        geometry.rows = world_->rows();
        return geometry;
    }

    /// Deck index under the pointer, or -1. `cardStep`/the 150..150+step*n band are the same
    /// numbers `drawSeedBank` lays out with, so a card can never be drawn where it cannot be hit.
    int cardAt(float x, float y) const {
        const std::size_t count = deck_.size();
        if (count == 0 || y < 12 || y > 96) return -1;
        const float step = cardStep(count);
        if (x < 150 || x >= 150 + step * static_cast<float>(count)) return -1;
        const auto index = static_cast<int>((x - 150) / step);
        return index >= 0 && index < static_cast<int>(count) ? index : -1;
    }

    /// Pointer moved with the left button held: update the preview cell and its verdict. No world
    /// mutation happens here — a drag that sweeps over ten cells still plants nothing until the
    /// button comes up.
    void updateDragPreview(float x, float y) {
        if (!drag_.active()) return;
        const int card = drag_.state().card;
        if (card < 0 || card >= static_cast<int>(deck_.size())) {
            drag_.cancel();
            return;
        }
        const ui::DragCell cell = dragGeometry().cellAt(x, y);
        drag_.moved(cell, ui::dragRulesFor(*world_, catalog_, deck_[static_cast<std::size_t>(card)], cell));
    }

    /// Left button released over (x, y): plant when the drop is legal, otherwise say why nothing
    /// happened. A refused drop sends no `input` to the world and costs no sun.
    void finishDrag(float x, float y) {
        if (!drag_.active()) return;
        const int card = drag_.state().card;
        if (card < 0 || card >= static_cast<int>(deck_.size())) {
            drag_.cancel();
            return;
        }
        const auto geometry = dragGeometry();
        const ui::DragCell cell = geometry.cellAt(x, y);
        const std::string& id = deck_[static_cast<std::size_t>(card)];
        const int planted = drag_.release(cell, ui::dragRulesFor(*world_, catalog_, id, cell));
        if (planted >= 0) {
            const std::string reason = world_->plant(deck_[static_cast<std::size_t>(planted)], cell.row, cell.col);
            message_ = localized(reason);
            if (reason.empty()) selected_ = -1;
            return;
        }
        // The state machine keeps the verdict of the release, so the HUD can explain it even
        // though the drag itself is over.
        if (geometry.onBoard(x, y)) message_ = ui::dragVerdictText(drag_.state().verdict);
    }

    /// The border under the pointer while dragging: green = release plants, red = occupied or
    /// still cooling, grey = not enough sun.
    void drawDragPreview() {
        if (!drag_.active()) return;
        const auto& state = drag_.state();
        if (!state.cell.inside() || state.verdict == ui::DragVerdict::offBoard) return;
        SDL_Color tint{};
        switch (state.verdict) {
        case ui::DragVerdict::legal:
            tint = SDL_Color{96, 208, 112, 255};
            break;
        case ui::DragVerdict::noSun:
            tint = SDL_Color{150, 150, 150, 240};
            break;
        default: // occupied / cooling: a refused drop
            tint = SDL_Color{214, 78, 66, 255};
            break;
        }
        auto* r = display_.renderer.get();
        const float x = boardX + static_cast<float>(state.cell.col) * cellW;
        const float y = boardY + static_cast<float>(state.cell.row) * cellH;
        rect(r, x, y, cellW, cellH, SDL_Color{tint.r, tint.g, tint.b, 54});
        rect(r, x, y, cellW, 4, tint);
        rect(r, x, y + cellH - 4, cellW, 4, tint);
        rect(r, x, y, 4, cellH, tint);
        rect(r, x + cellW - 4, y, 4, cellH, tint);
    }

    void handleEvent(const SDL_Event& event) {
        auto* r = display_.renderer.get();
        if (event.type == SDL_EVENT_QUIT || event.type == SDL_EVENT_WINDOW_CLOSE_REQUESTED) {
            quit_ = true;
            return;
        }
        if (event.type == SDL_EVENT_WINDOW_FOCUS_LOST && started_ && !world_->finished())
            world_->pause(true);
        if (event.type == SDL_EVENT_KEY_DOWN && !event.key.repeat) {
            const auto key = event.key.key;
            if (key == SDLK_ESCAPE) {
                selected_ = -1;
                shovel_ = false;
                drag_.cancel();
            } else if (key == SDLK_SPACE) {
                if (!started_)
                    started_ = true;
                else
                    world_->pause(!world_->paused());
            } else if (key == SDLK_R) {
                reset();
            } else if (key == SDLK_S) {
                shovel_ = !shovel_;
                selected_ = -1;
            } else if (key >= SDLK_1 && key <= SDLK_8) {
                const int index = int(key - SDLK_1);
                if (index >= 0 && index < static_cast<int>(deck_.size())) {
                    selected_ = index;
                    shovel_ = false;
                }
            }
            return;
        }
        // T50: dragging a card. Motion only updates the preview; the release decides. Both events
        // carry pointer coordinates in the same window space as a button press, so the same
        // logical-viewport mapping applies.
        if (event.type == SDL_EVENT_MOUSE_MOTION) {
            if (!drag_.active()) return;
            SDL_Event mapped = event;
            sdl::require(SDL_ConvertEventToRenderCoordinates(r, &mapped), "map pointer to logical viewport");
            updateDragPreview(mapped.motion.x, mapped.motion.y);
            return;
        }
        if (event.type == SDL_EVENT_MOUSE_BUTTON_UP && event.button.button == SDL_BUTTON_LEFT) {
            if (!drag_.active()) return;
            SDL_Event mapped = event;
            sdl::require(SDL_ConvertEventToRenderCoordinates(r, &mapped), "map pointer to logical viewport");
            finishDrag(mapped.button.x, mapped.button.y);
            return;
        }
        if (event.type != SDL_EVENT_MOUSE_BUTTON_DOWN)
            return;
        SDL_Event mapped = event;
        sdl::require(SDL_ConvertEventToRenderCoordinates(r, &mapped), "map pointer to logical viewport");
        const float x = mapped.button.x, y = mapped.button.y;
        if (mapped.button.button == SDL_BUTTON_RIGHT) {
            selected_ = -1;
            shovel_ = false;
            drag_.cancel();
            return;
        }
        if (mapped.button.button != SDL_BUTTON_LEFT)
            return;
        if (!started_) {
            if (x >= 440 && x <= 840 && y >= 430 && y <= 490)
                started_ = true;
            return;
        }
        if (x >= 1092 && x <= 1246 && y >= 20 && y <= 76) {
            world_->pause(!world_->paused());
            return;
        }
        if (x >= 946 && x <= 1080 && y >= 20 && y <= 76) {
            shovel_ = !shovel_;
            selected_ = -1;
            return;
        }
        if (world_->paused() || world_->finished())
            return;
        for (const auto& sun : world_->snapshot().suns)
            if (std::hypot(x - (boardX + static_cast<float>(sun.x) * cellW),
                           y - (boardY + static_cast<float>(sun.y) * cellH)) < 30) {
                (void)world_->collect(sun.id);
                return;
            }
        const std::size_t count = deck_.size();
        const float step = cardStep(count);
        if (count > 0 && x >= 150 && x <= 150 + step * static_cast<float>(count) && y >= 12 && y <= 96) {
            const auto index = static_cast<std::size_t>((x - 150) / step);
            if (index < count) {
                selected_ = static_cast<int>(index);
                shovel_ = false;
                // Pressing a card also arms the drag: release on the lawn plants there, release on
                // the card itself leaves the card selected (the click-then-click flow below).
                drag_.begin(static_cast<int>(index));
            }
            return;
        }
        const int col = int(std::floor((x - boardX) / cellW)), row = int(std::floor((y - boardY) / cellH));
        if (col >= 0 && col < world_->cols() && row >= 0 && row < world_->rows()) {
            if (shovel_)
                message_ = world_->shovel(row, col) ? "已铲除，不返还阳光。" : "这里没有植物。";
            else if (selected_ >= 0 && selected_ < static_cast<int>(count)) {
                const std::string reason = world_->plant(deck_[static_cast<std::size_t>(selected_)], row, col);
                message_ = localized(reason);
                if (reason.empty())
                    selected_ = -1;
            } else {
                message_ = "先点一张卡，再点草坪格子。";
            }
        }
    }

    const Catalog& catalog_;
    const LevelDefinition level_;
    std::unique_ptr<engine::World> world_;
    std::uint32_t seed_ = 1;
    sdl::Display display_;
    // Artwork is resolved before the asset cache and the font on purpose: a missing artwork
    // tree must fail with the lawn diagnostic, not with whichever texture came first.
    sdl::Texture lawn_, sunArt_, panelArt_;
    AssetCache assets_;
    TextRenderer text_;
    std::vector<std::string> deck_;
    std::map<std::string, std::string> plantIdle_, plantShoot_;
    std::map<std::string, std::string> zombieWalk_;
    std::set<std::string> reported_;
    int selected_ = -1;
    /// T50 drag-to-plant: armed by a press on a card, resolved by the release.
    ui::DragController drag_;
    bool shovel_ = false, started_ = false, quit_ = false;
    std::string message_;
    std::uint64_t previousNs_ = 0;
    /// How much of `world_->events()` the audio cursor has already played. The stream only grows,
    /// so an index is enough and a tick is never replayed.
    std::size_t audioCursor_ = 0;
};

namespace {
/// `--play-script` gets no asset directory on the command line, so probe the two layouts the
/// repository and an installed build use (shared with `--art-audit`, which needs the same answer).
std::filesystem::path locateAssets(const std::filesystem::path& contentRoot) {
    return locateAssetRoot(contentRoot);
}
} // namespace

Json playScriptSummary(const engine::World& world, const PlayStats& stats) {
    Json summary = engine::summarize(world);
    summary["planted"] = stats.planted;
    summary["collected"] = stats.collected;
    summary["shoveled"] = stats.shoveled;
    summary["rejectedInputs"] = stats.rejected;
    summary["plants"] = world.plants().size();
    summary["zombies"] = world.zombies().size();
    summary["suns"] = world.suns().size();
    summary["shots"] = world.shots().size();
    summary["seed"] = world.seed();
    return summary;
}

namespace {
/// The same script semantics as `engine::applyInputs`, but every accepted or refused input is
/// counted so `--play-script` can report what the timeline actually did.
void runScriptCounted(engine::World& world, const engine::Script& script, double seconds, PlayStats& stats) {
    std::size_t cursor = 0;
    const auto limit = static_cast<std::uint64_t>(seconds / engine::World::stepSeconds + 0.5);
    const auto apply = [&world, &script, &cursor, &stats]() {
        while (cursor < script.inputs.size() && script.inputs[cursor].tick <= world.tick()) {
            const auto& input = script.inputs[cursor++];
            if (input.op == "plant") {
                if (world.plant(input.type, input.row, input.col).empty())
                    ++stats.planted;
                else
                    ++stats.rejected;
            } else if (input.op == "shovel") {
                if (world.shovel(input.row, input.col))
                    ++stats.shoveled;
                else
                    ++stats.rejected;
            } else if (input.op == "collect") {
                if (input.id == 0) {
                    std::vector<engine::EntityId> ids;
                    for (const auto& sun : world.suns()) ids.push_back(sun.id);
                    for (auto id : ids)
                        if (world.collect(id)) ++stats.collected;
                } else if (world.collect(input.id)) {
                    ++stats.collected;
                }
            } else if (input.op == "spawn") {
                world.spawnZombie(input.type, input.row);
            } else {
                world.event("input_rejected", Json{{"op", input.op}, {"reason", "unknown op"}});
                ++stats.rejected;
            }
        }
    };
    while (!world.finished() && world.tick() < limit) {
        apply();
        world.step();
    }
    apply();
}
} // namespace

void runBattlePreview(const Catalog& catalog, const std::filesystem::path& assetRoot, bool smokeTest,
                      const std::filesystem::path& snapshot) {
    const auto& level = catalog.levels.at("frontyard_1");
    BattleScene scene(catalog, level, assetRoot, smokeTest, "PvZ 2 SHUTTLE - Native battle preview", 1);
    if (smokeTest)
        scene.runDemo();
    while (!scene.quit()) {
        scene.pollEvents();
        scene.advanceFrame();
        scene.drawFrame();
        if (!snapshot.empty())
            scene.writeSnapshot(snapshot);
        scene.present();
        if (smokeTest)
            break;
        SDL_Delay(1);
    }
}

Json runPlayScript(const Catalog& catalog, const std::string& levelId, const engine::Script& script,
                   const PlayScriptOptions& options) {
    const auto found = catalog.levels.find(levelId);
    if (found == catalog.levels.end())
        throw std::runtime_error("unknown level: " + levelId);
    const auto& level = found->second;
    if (options.snapshot.empty()) {
        engine::World world(catalog, level, script.seed);
        PlayStats stats;
        runScriptCounted(world, script, options.seconds, stats);
        return playScriptSummary(world, stats);
    }
    auto assetRoot = options.assetRoot;
    if (assetRoot.empty())
        assetRoot = locateAssets(catalog.levels.at(levelId).file.empty()
                                     ? std::filesystem::path{}
                                     : catalog.levels.at(levelId).file.parent_path().parent_path());
    if (assetRoot.empty())
        throw std::runtime_error("cannot locate battle assets (lawn/frontyard.png); pass --assets <dir>");
    BattleScene scene(catalog, level, assetRoot, true, "PvZ 2 SHUTTLE - play script", script.seed);
    PlayStats stats;
    runScriptCounted(scene.world(), script, options.seconds, stats);
    Json summary = playScriptSummary(scene.world(), stats);
    scene.drawFrame();
    scene.writeSnapshot(options.snapshot);
    summary["snapshot"] = pathUtf8(options.snapshot);
    std::error_code ec;
    const auto bytes = std::filesystem::file_size(options.snapshot, ec);
    summary["snapshotBytes"] = ec ? 0 : static_cast<std::uint64_t>(bytes);
    return summary;
}
} // namespace pvz
