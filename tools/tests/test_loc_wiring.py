"""Static checks that the B6b localisation wiring is really in the drawing path.

The runtime tests (`almanac_render`, `garden_render`, `achievements`, `daily`, `level_badges`)
prove the *models* carry real strings. This module proves the other half: that no screen still
hands a raw localisation key to `TextRenderer::draw` while a table is available, and that the
fallback chain (content -> LawnStrings -> humanize) is intact.

It is a text scan on purpose. The screens are SDL programs; a source scan is the only cheap way to
state "this call site resolves before it draws", and a regression here is one line away from
shipping `ACHIEVE_ALL_IN_JEST_TITLE` to a player.

Run: python -m unittest tools.tests.test_loc_wiring -v
"""

from __future__ import annotations

import io
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "native" / "src"

# The five call sites B6b routed through LawnStrings, and the field each one has to fill.
# `level_select_view.cpp` is the sixth site but its wiring is the badge `wired` flag, not a key
# lookup (a chip is already Chinese), so it is scanned but never asked for `loc::resolve`.
WIRED = {
    "achievements_view.cpp": "row.title",
    "daily_view.cpp": "row.title",
    "almanac_view.cpp": "entry.name",
    "garden_view.cpp": "item.title",
    "worldmap.cpp": "world.nameZh",
}

# Every file the bare-key scan reads, wired or not.
SCANNED = sorted(set(WIRED) | {"level_select_view.cpp"})

# A draw call may still print a key only where the key *is* the honest answer: a panel that says
# "the table has no row for this" has to show which row it looked for, a screen header shows the
# world id the caller asked for, and the two almanac fact rows compare the resolved text against the
# key to decide between "普通" and "只有分级键 …". Keyed by (file, identifier) -> why.
ALLOWED_RAW_KEY_DRAWS = {
    ("almanac_view.cpp", "descKey"): "fallback line when no table row and no content blurb",
    ("almanac_view.cpp", "costKey"): "`costValue == current->costKey` picks the 只有分级键 wording",
    ("almanac_view.cpp", "hpKey"): "`hpValue == current->hpKey` as above",
    ("garden_view.cpp", "titleKey"): "`标题键 <key>` line above the resolved title",
    ("worldmap_view.cpp", "world.id"): "a world with no table row and no content name shows its id",
    ("level_select_view.cpp", "worldId"): "screen header names the world the caller asked for",
}

DRAW = re.compile(r"\btext\.draw(?:Centered)?\(")
KEY_LIKE = re.compile(r"\b(descKey|titleKey|nameKey|valueKey|costKey|hpKey|worldId|world\.id)\b")


def read(name: str) -> str:
    with io.open(SRC / name, encoding="utf-8") as handle:
        return handle.read()


def draw_lines(text: str) -> list[tuple[int, str]]:
    """Every line that feeds `TextRenderer::draw`, with its 1-based number.

    A draw call may be wrapped over several lines, so the search covers the call line and the seven
    lines under it - enough for the `text.draw(x, y, size, colour,` + a nested ternary shape used in
    this tree (the almanac fact rows need six lines before their last `+ costKey` operand).
    """
    lines = text.splitlines()
    found: list[tuple[int, str]] = []
    for index, line in enumerate(lines):
        if not DRAW.search(line):
            continue
        block = " ".join(lines[index : index + 8])
        found.append((index + 1, block))
    return found


class LocWiringTest(unittest.TestCase):
    def test_every_wired_site_calls_resolve(self) -> None:
        for name, needle in WIRED.items():
            with self.subTest(file=name):
                text = read(name)
                self.assertIn("loc::resolve(", text, f"{name} does not call loc::resolve")
                self.assertIn(needle, text, f"{name} no longer carries `{needle}`")

    def test_views_load_the_table_from_the_generated_tree(self) -> None:
        # `loc::load` takes a content root and probes `<root>/native/generated/`; each screen has to
        # derive that root from something it already holds rather than from the process CWD.
        for name in ("achievements_view.cpp", "daily_view.cpp", "almanac_view.cpp", "garden_view.cpp"):
            with self.subTest(file=name):
                text = read(name)
                self.assertIn("loc::load(", text)
                self.assertIn("parent_path()", text)
        worldmap = read("worldmap.cpp")
        self.assertIn("loc::load(contentDir.string())", worldmap)
        # `content/worlds.json` stays the first source: the table only fills what it left blank.
        self.assertIn("if (!world.nameZh.empty()) continue;", worldmap)
        # Worlds the content list does not name are found under the almanac heading `ALM_<WORLD>`.
        self.assertIn('"ALM_" + id', worldmap)

    def test_humanize_is_only_a_fallback(self) -> None:
        for name in ("achievements_view.cpp", "daily_view.cpp"):
            with self.subTest(file=name):
                text = read(name)
                # `row.title = loc::resolve(...)` then `if (row.title.empty()) row.title =
                # humanizeGameKey(...)` - the order is the contract.
                resolve_at = text.index("row.title = loc::resolve(")
                humanize_at = text.index("row.title = humanizeGameKey(")
                self.assertLess(resolve_at, humanize_at, f"{name} humanizes before it resolves")
                self.assertIn("if (row.title.empty()) row.title = humanizeGameKey(", text)

    def test_no_draw_call_renders_a_bare_key(self) -> None:
        offenders: list[str] = []
        for name in SCANNED:
            for line_no, block in draw_lines(read(name)):
                for token in KEY_LIKE.findall(block):
                    if (name, token) in ALLOWED_RAW_KEY_DRAWS:
                        continue
                    offenders.append(f"{name}:{line_no}: draws `{token}` unresolved")
        self.assertEqual([], offenders, "unresolved localisation keys reach the renderer")

    def test_known_fallbacks_stay_documented(self) -> None:
        # Every allow-list entry has to still be a real draw site: a stale entry would silently
        # whitelist a future regression in that file.
        for name, token, why in sorted(
            (name, token, why) for (name, token), why in ALLOWED_RAW_KEY_DRAWS.items()
        ):
            with self.subTest(file=name, token=token):
                self.assertTrue(why)
                text = read(name)
                self.assertTrue(
                    any(token in block for _, block in draw_lines(text)),
                    f"{name} no longer draws `{token}`; drop it from the allow-list",
                )

    def test_badge_wired_flag_is_published(self) -> None:
        header = read("level_badges.hpp")
        self.assertIn("bool wired = false;", header)
        self.assertIn("bool badgeWired(const std::string& kind);", header)
        impl = read("level_badges.cpp")
        for kind in ("vasebreaker", "rail", "conveyor", "protecttheplant"):
            with self.subTest(kind=kind):
                self.assertIn(f'"{kind}"', impl)
        view = read("level_select_view.cpp")
        self.assertIn('item["wired"] = !kind.empty() && badgeWired(kind);', view)
        self.assertIn("（未接入）", view)


if __name__ == "__main__":
    unittest.main()
