#include "shop_view.hpp"

#include "engine/plantfood.hpp"  // generatedDir(): where shop_unlock.json lives

#include <algorithm>
#include <chrono>
#include <cstdlib>
#include <stdexcept>

#ifdef PVZ_ENABLE_DESKTOP
#include <SDL3/SDL.h>
#include <SDL3_image/SDL_image.h>

#include "sdl_support.hpp"
#include "text.hpp"
#endif

namespace pvz {
namespace {

#ifdef PVZ_ENABLE_DESKTOP
struct Palette {
    SDL_Color page{24, 26, 32, 255};
    SDL_Color panel{34, 37, 45, 255};
    SDL_Color row{41, 45, 55, 255};
    SDL_Color rowSelected{58, 74, 96, 255};
    SDL_Color ink{236, 238, 242, 255};
    SDL_Color muted{150, 156, 168, 255};
    SDL_Color good{130, 214, 140, 255};
    SDL_Color warn{236, 190, 100, 255};
    SDL_Color bad{230, 120, 120, 255};
    SDL_Color accent{120, 190, 235, 255};
};

const Palette& palette() {
    static const Palette p;
    return p;
}

void fill(SDL_Renderer* renderer, const SDL_FRect& rect, SDL_Color color) {
    sdl::require(SDL_SetRenderDrawColor(renderer, color.r, color.g, color.b, color.a),
                 "set draw colour");
    sdl::require(SDL_RenderFillRect(renderer, &rect), "fill rectangle");
}

void border(SDL_Renderer* renderer, const SDL_FRect& rect, SDL_Color color) {
    sdl::require(SDL_SetRenderDrawColor(renderer, color.r, color.g, color.b, color.a),
                 "set draw colour");
    sdl::require(SDL_RenderRect(renderer, &rect), "draw rectangle");
}

/// PNG when the name says so, the SDL BMP fallback otherwise. Local copy so this screen does not
/// have to link `menu_view.cpp` just to save a picture.
void saveSnapshot(SDL_Renderer* renderer, const std::filesystem::path& path) {
    if (path.extension() == ".png" || path.extension() == ".PNG") {
        sdl::Surface pixels(SDL_RenderReadPixels(renderer, nullptr), SDL_DestroySurface);
        sdl::require(bool(pixels), "read frame");
        sdl::require(IMG_SavePNG(pixels.get(), pathUtf8(path).c_str()),
                     pathUtf8(path) + ": save snapshot");
        return;
    }
    sdl::snapshot(renderer, path);
}

std::string clipped(TextRenderer& text, const std::string& value, float size, float maxWidth) {
    if (text.width(value, size) <= maxWidth) return value;
    std::string out;
    for (char c : value) {
        std::string candidate = out;
        candidate.push_back(c);
        candidate += "…";
        if (text.width(candidate, size) > maxWidth) break;
        out.push_back(c);
    }
    return out + "…";
}

/// `PVZ_ASSET_ROOT` wins; otherwise walk up to three directories looking for the two layouts this
/// project's machines use: `<dir>/assets/ui/font_zh.ttc` (a content tree that carries its art) and
/// `<dir>/PvZ2SHUTTLE/assets/ui/font_zh.ttc` (the launcher checkout next to the repo).
std::filesystem::path defaultAssetRoot(const std::filesystem::path& contentRoot) {
    if (const char* configured = std::getenv("PVZ_ASSET_ROOT")) {
        if (configured[0] != '\0') return std::filesystem::path(configured);
    }
    // Canonicalise first: a relative `content` has no parent, and `""/assets` would silently miss
    // the art even though the caller is standing in the repository root.
    std::error_code error;
    const std::filesystem::path absolute = std::filesystem::weakly_canonical(contentRoot, error);
    std::filesystem::path root = (error ? contentRoot : absolute).parent_path();
    for (int level = 0; level < 3 && !root.empty(); ++level) {
        if (std::filesystem::is_regular_file(root / "assets" / "ui" / "font_zh.ttc", error)) {
            return root / "assets";
        }
        if (std::filesystem::is_regular_file(root / "PvZ2SHUTTLE" / "assets" / "ui" / "font_zh.ttc",
                                             error)) {
            return root / "PvZ2SHUTTLE" / "assets";
        }
        root = root.parent_path();
    }
    return contentRoot.parent_path() / "assets";
}
#endif  // PVZ_ENABLE_DESKTOP

std::filesystem::path unlockFile() {
    const std::filesystem::path generated = engine::generatedDir();
    if (generated.empty()) {
        throw std::runtime_error(
            "shop screen: shop_unlock.json was not found; set PVZ_GENERATED_DIR or run from the "
            "repository root");
    }
    return generated / "shop_unlock.json";
}

Shop loadShop(const std::filesystem::path& contentRoot) {
    return Shop::load(contentRoot, unlockFile());
}

Progress loadOrEmpty(const std::filesystem::path& progressFile) {
    if (progressFile.empty()) return Progress{};
    return loadProgress(progressFile);
}

std::int64_t nowSeconds() {
    return static_cast<std::int64_t>(
        std::chrono::duration_cast<std::chrono::seconds>(
            std::chrono::system_clock::now().time_since_epoch())
            .count());
}

Json buyResultJson(const BuyResult& result) {
    Json granted = Json::array();
    for (const Grant& grant : result.granted) {
        Json entry{{"kind", grantKindName(grant.kind)}};
        if (!grant.text.empty()) entry["id"] = grant.text;
        if (grant.value.is_number()) entry["value"] = grant.value;
        granted.push_back(std::move(entry));
    }
    return Json{{"ok", result.ok},
                {"itemId", result.itemId},
                {"reason", result.reason},
                {"coinsSpent", result.coinsSpent},
                {"granted", std::move(granted)}};
}

#ifdef PVZ_ENABLE_DESKTOP
/// Draws one frame of the shop. Split out so the loop below reads as keys-then-draw.
void drawShop(SDL_Renderer* renderer, TextRenderer& text, const Shop& shop, const Progress& progress,
              const ShopLayout& layout, const Json* lastResult) {
    const Palette& p = palette();
    sdl::require(SDL_SetRenderDrawColor(renderer, p.page.r, p.page.g, p.page.b, p.page.a), "clear");
    sdl::require(SDL_RenderClear(renderer), "clear");

    // Header: title on the left, wallet on the right. Coins and gems are the two counters a shop
    // row can pay out, so both are always visible even when only coins can be spent.
    text.draw(40.0f, 22.0f, 30, p.ink, "商店");
    const std::string wallet =
        "金币 " + std::to_string(progress.coins) + "    宝石 " + std::to_string(progress.gems);
    const float walletWidth = text.width(wallet, 20);
    text.draw(1240.0f - walletWidth, 30.0f, 20, p.warn, wallet);

    // Tab strip: five tabs, the current one underlined in the accent colour.
    float tabX = 40.0f;
    for (std::size_t i = 0; i < shopTabs().size(); ++i) {
        const auto& tab = shopTabs()[i];
        const bool current = static_cast<int>(i) == layout.tabIndex;
        const float width = text.width(tab.label, 20) + 24.0f;
        SDL_FRect box{tabX, 66.0f, width, 32.0f};
        fill(renderer, box, current ? p.rowSelected : p.panel);
        if (current) border(renderer, box, p.accent);
        text.draw(tabX + 12.0f, 72.0f, 20, current ? p.ink : p.muted, tab.label);
        tabX += width + 8.0f;
    }
    text.draw(tabX + 8.0f, 74.0f, 16, p.muted,
              "共 " + std::to_string(layout.total) + " 行 · 第 " + std::to_string(layout.page + 1) +
                  "/" + std::to_string(layout.pages) + " 页");

    // List: at most kShopPageSize rows, the cursor's row highlighted.
    const float listLeft = 40.0f;
    const float listTop = 112.0f;
    const float listWidth = 760.0f;
    const float rowHeight = 56.0f;
    for (int i = layout.first; i < layout.first + layout.count; ++i) {
        const ShopRow& row = layout.rows[static_cast<std::size_t>(i)];
        const bool selected = i == layout.cursor;
        const float y = listTop + static_cast<float>(i - layout.first) * rowHeight;
        SDL_FRect box{listLeft, y, listWidth, rowHeight - 6.0f};
        fill(renderer, box, selected ? p.rowSelected : p.row);
        if (selected) border(renderer, box, p.accent);

        const SDL_Color labelColor = row.affordable ? p.ink : p.muted;
        text.draw(listLeft + 14.0f, y + 8.0f, 20, labelColor,
                  clipped(text, row.label, 20, listWidth - 260.0f));

        // Price on the right of the row; "免费" instead of "0 金币" for the six free rows.
        const std::string price = row.currency == "free"
                                      ? std::string("免费")
                                      : (std::to_string(row.price) + " " + row.currency);
        const float priceWidth = text.width(price, 18);
        text.draw(listLeft + listWidth - priceWidth - 14.0f, y + 8.0f, 18,
                  row.currency == "coin" ? p.warn : p.muted, price);

        // Status word on the row itself. The full sentence lives in the detail panel; the list only
        // needs to separate "can buy" from "cannot", and why it cannot is never hidden.
        const std::string status = row.affordable ? "可购买" : (row.owned ? "已拥有" : "不可购买");
        text.draw(listLeft + 14.0f, y + 32.0f, 15, row.affordable ? p.good : p.bad, status);
    }
    if (layout.count == 0) {
        text.draw(listLeft + 14.0f, listTop + 8.0f, 20, p.muted, "此分页没有商品");
    }

    // Detail panel: the selected row, its price, and — when it cannot be bought — the exact
    // sentence `purchase()` would return. This is the requirement that a refused row must say why.
    SDL_FRect panel{listLeft + listWidth + 20.0f, 112.0f, 380.0f, 460.0f};
    fill(renderer, panel, p.panel);
    border(renderer, panel, p.muted);
    if (layout.total > 0) {
        const ShopRow& row = layout.rows[static_cast<std::size_t>(layout.cursor)];
        float y = 128.0f;
        text.draw(panel.x + 16.0f, y, 24, p.ink, clipped(text, row.label, 24, 348.0f));
        y += 40.0f;
        text.draw(panel.x + 16.0f, y, 15, p.muted, clipped(text, row.id, 15, 348.0f));
        y += 34.0f;
        const std::string price = row.currency == "free"
                                      ? std::string("免费")
                                      : (std::to_string(row.price) + " " + row.currency);
        text.draw(panel.x + 16.0f, y, 20, p.warn, "价格 " + price);
        y += 38.0f;
        text.draw(panel.x + 16.0f, y, 18, row.affordable ? p.good : p.bad,
                  row.affordable ? "现在可以购买" : "现在不能购买");
        y += 34.0f;
        if (!row.affordable) {
            text.draw(panel.x + 16.0f, y, 15, p.muted, "原因");
            y += 24.0f;
            // Wrap the sentence by hand: the refusal strings carry the price and the shortfall, so
            // truncating them would hide exactly the number the player needs.
            std::string rest = row.reason;
            while (!rest.empty() && y < 520.0f) {
                std::string line;
                for (char c : rest) {
                    std::string candidate = line;
                    candidate.push_back(c);
                    if (text.width(candidate, 16) > 348.0f) break;
                    line.push_back(c);
                }
                if (line.empty()) line = rest.substr(0, 1);
                text.draw(panel.x + 16.0f, y, 16, row.unmodelled ? p.warn : p.ink, line);
                rest = rest.substr(line.size());
                y += 22.0f;
            }
        }
    }

    // Footer: keys, then the standing note about server-side currencies.
    text.draw(40.0f, 612.0f, 16, p.muted,
              "↑↓ 移动    Tab / ←→ 切换分页    Enter 购买    Esc 退出");
    text.draw(40.0f, 640.0f, 15, p.warn,
              "宝石与薄荷币由服务器结算，本客户端不能支付；不可购买的行都会写明原因");
    text.draw(40.0f, 664.0f, 15, p.muted,
              "目录 " + std::to_string(shop.size()) + " 行 · 可购买 " +
                  std::to_string(shop.buyable()) + " 行");

    if (lastResult != nullptr) {
        const bool ok = lastResult->value("ok", false);
        const std::string line =
            ok ? ("已购买 " + lastResult->value("itemId", std::string()) + "，花费 " +
                  std::to_string(lastResult->value("coinsSpent", 0)) + " 金币")
               : ("购买失败：" + lastResult->value("reason", std::string()));
        text.draw(40.0f, 584.0f, 16, ok ? p.good : p.bad, clipped(text, line, 16, 1200.0f));
    }
}
#endif  // PVZ_ENABLE_DESKTOP

}  // namespace

Json renderShopHeadless(const std::filesystem::path& contentRoot,
                        const std::filesystem::path& progressFile, int frames,
                        const std::filesystem::path& snapshot, int tab, int cursor) {
    const Shop shop = loadShop(contentRoot);
    const Progress progress = loadOrEmpty(progressFile);
    ShopLayout layout = shopLayout(shop, progress, tab, cursor);
#ifdef PVZ_ENABLE_DESKTOP
    if (frames > 0 || !snapshot.empty()) {
        const std::filesystem::path assets = defaultAssetRoot(contentRoot);
        const std::filesystem::path fontFile = assets / "ui" / "font_zh.ttc";
        if (!std::filesystem::is_regular_file(fontFile)) {
            throw std::runtime_error(pathUtf8(fontFile) + ": cannot open the Chinese font");
        }
        sdl::Display display(frames > 0, "PvZ 2 SHUTTLE - Shop");
        TextRenderer text(display.renderer.get(), fontFile);
        int drawn = 0;
        bool running = true;
        while (running) {
            SDL_Event event;
            while (SDL_PollEvent(&event)) {
                if (event.type == SDL_EVENT_QUIT) running = false;
                if (event.type == SDL_EVENT_KEY_DOWN && event.key.key == SDLK_ESCAPE) running = false;
            }
            drawShop(display.renderer.get(), text, shop, progress, layout, nullptr);
            if (!snapshot.empty()) saveSnapshot(display.renderer.get(), snapshot);
            SDL_RenderPresent(display.renderer.get());
            ++drawn;
            if (frames > 0 && drawn >= frames) break;
            if (frames <= 0) SDL_Delay(16);
        }
    }
#else
    (void)frames;
    (void)snapshot;
#endif
    return shopJson(shop, progress, layout);
}

Json runShop(const ShopScreenOptions& options) {
    const Shop shop = loadShop(options.contentRoot);
    Progress progress = loadOrEmpty(options.progressFile);
    int tab = options.tab;
    int cursor = options.cursor;
    ShopLayout layout = shopLayout(shop, progress, tab, cursor);
    Json lastResult = Json();
    bool haveResult = false;

#ifdef PVZ_ENABLE_DESKTOP
    const std::filesystem::path assets = options.assetRoot.empty()
                                             ? defaultAssetRoot(options.contentRoot)
                                             : options.assetRoot;
    const std::filesystem::path fontFile = assets / "ui" / "font_zh.ttc";
    if (!std::filesystem::is_regular_file(fontFile)) {
        throw std::runtime_error(pathUtf8(fontFile) + ": cannot open the Chinese font");
    }
    const bool headless = options.frames > 0;
    sdl::Display display(headless, "PvZ 2 SHUTTLE - Shop");
    TextRenderer text(display.renderer.get(), fontFile);
    int drawn = 0;
    bool running = true;
    while (running) {
        SDL_Event event;
        while (SDL_PollEvent(&event)) {
            if (event.type == SDL_EVENT_QUIT) running = false;
            if (event.type != SDL_EVENT_KEY_DOWN) continue;
            const SDL_Keycode key = event.key.key;
            if (key == SDLK_ESCAPE) {
                running = false;
            } else if (key == SDLK_UP) {
                cursor = layout.total == 0 ? 0 : std::max(0, layout.cursor - 1);
            } else if (key == SDLK_DOWN) {
                cursor = layout.total == 0 ? 0 : std::min(layout.total - 1, layout.cursor + 1);
            } else if (key == SDLK_TAB || key == SDLK_RIGHT || key == SDLK_Q || key == SDLK_E) {
                const int tabs = static_cast<int>(shopTabs().size());
                const int step = (key == SDLK_Q) ? -1 : 1;
                tab = ((tab + step) % tabs + tabs) % tabs;
                cursor = 0;
            } else if (key == SDLK_RETURN || key == SDLK_KP_ENTER) {
                if (layout.total > 0) {
                    const ShopRow row = layout.rows[static_cast<std::size_t>(layout.cursor)];
                    const BuyResult result = purchase(shop, row.id, progress);
                    lastResult = buyResultJson(result);
                    haveResult = true;
                    // Only a caller that named a save file gets a write: a preview session must not
                    // touch the disk (the byte-for-byte test leans on this).
                    if (result.ok && !options.progressFile.empty()) {
                        saveProgress(options.progressFile, progress, nowSeconds());
                    }
                }
            }
        }
        layout = shopLayout(shop, progress, tab, cursor);
        drawShop(display.renderer.get(), text, shop, progress, layout,
                 haveResult ? &lastResult : nullptr);
        if (!options.snapshot.empty()) saveSnapshot(display.renderer.get(), options.snapshot);
        SDL_RenderPresent(display.renderer.get());
        ++drawn;
        if (headless && drawn >= options.frames) break;
        if (!headless) SDL_Delay(16);
    }
#else
    (void)options;
#endif
    Json out = shopJson(shop, progress, layout);
    out["lastResult"] = haveResult ? lastResult : Json();
    return out;
}

}  // namespace pvz
