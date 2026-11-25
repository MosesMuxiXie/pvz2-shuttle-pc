#pragma once
#include <cstddef>
#include <filesystem>
#include <string>
#include <vector>

namespace pvz::engine {

/// One `FusionPlant` row: placing `source` and `fusion` next to each other yields `result`.
///
/// The sheets name both ingredients and the outcome with the identity they were stored
/// under, so a recipe can mix a pack id with a client id (`akee` + `sprout` ->
/// `fused_draftodil1`). `World::tryFuse` accepts either order and either identity.
struct FusionRecipe {
    std::string source;
    std::string fusion;
    std::string result;
    std::string sound;
    std::string sourceKind; // "pack" | "client": which identity the sheet used
    bool onlyResult = false;
    bool matches(const std::string& a, const std::string& b) const {
        return (a == source && b == fusion) || (a == fusion && b == source);
    }
};

class FusionTable {
  public:
    static constexpr const char* kFileName = "fusions_from_pack.json";

    /// Parse a generated table. Every failure throws `fusion table: <path>: <reason>`.
    static FusionTable load(const std::filesystem::path& file);
    /// The process-wide table from `generatedDir()`, parsed once.
    static const FusionTable& shared();

    bool empty() const { return recipes_.empty(); }
    std::size_t size() const { return recipes_.size(); }
    /// The recipe for an unordered pair, or nullptr when the two plants do not fuse.
    const FusionRecipe* find(const std::string& a, const std::string& b) const;
    const std::vector<FusionRecipe>& recipes() const { return recipes_; }

  private:
    std::vector<FusionRecipe> recipes_;
};

} // namespace pvz::engine
