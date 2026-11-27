"""D4 gate coverage: every generated product must be reached by a ``--check`` step.

Why this file exists
--------------------
Between 2026-11-24 and 2026-11-26 the repository grew ten data compilers
(``level_playability``, ``plant_levels``, ``minigame_rules``, ``level_extra_rules`` …)
and twice during that window a product was already stale while ``check_all`` was
green, simply because nobody had added a Step for the new table.  The gate could
not notice a product it had never heard of.  This file turns "product ⇒ step" into
something a test can fail.

The rules
---------
R01 **Registry, not guesswork.**  ``PRODUCTS`` lists every file under
    ``native/generated`` that ships as a product and the module that writes it.
    The list is hand-written because a reader and a writer look identical from the
    outside (``level_playability.py`` *reads* ``level_mechanics.json`` through a
    ``DEFAULT_MECH`` constant exactly the way ``mechanics.py`` *writes* it), but
    every entry is verified against that module's own source: the module must
    declare the path in one of its own constants.  A registry entry that no
    compiler declares is a lie and fails the suite.
R02 **A registered file missing from disk is fine; an unregistered file on disk is
    not.**  Orphans are how the next unguarded table will appear, so they fail and
    are named one by one.
R03 **``compiler`` products need a Step.**  The Step must invoke that module with
    ``--check``; the module name is what ties product to step, never the step label
    (``level mechanics`` ↔ ``level_mechanics.json`` ↔ ``mechanics.py``).
R04 **.md reports are not gated.**  Reports are rendered by the same compiler run
    that rewrites the JSON, so guarding them would double-count; they are listed as
    ``report`` and deliberately exempt.
R05 **Not every product can be byte-gated.**  ``coverage.json`` / ``id_overlap.json``
    come from a ``--check`` that verifies pinned counts and writes nothing; the
    three files without a ``--check`` at all are pinned by unit tests instead.  Those
    roles carry a mandatory note or ``covered_by`` so the exemption is visible, and
    the report names them.
R06 **A hand-off step may not be faked.**  ``mechanic_entity_resolution`` is being
    written by another agent; its Step only counts when it is wrapped in a
    ``Test-Path`` guard that prints a skip.  An unconditional Step for a file that
    does not exist would red the gate for everyone in the meantime.

Run: ``python -m unittest tools.tests.test_gate_coverage -v``
"""

from __future__ import annotations

import ast
import re
import shutil
import subprocess
import unittest
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CONTENTC = REPO / "tools" / "contentc"
GENERATED = REPO / "native" / "generated"
CHECK_ALL = REPO / "tools" / "check_all.ps1"

PRODUCT_EXTENSIONS = (".json", ".pack", ".inc", ".csv")


# --------------------------------------------------------------------------- registry
@dataclass(frozen=True)
class Product:
    """One file under native/generated plus the story of how it is guarded."""

    name: str
    module: str
    role: str
    note: str = ""
    gate: str = ""
    covered_by: str = ""


#: role="compiler"     the module has --check and a Step must exist (R03)
#: role="report"       .md report, never gated (R04)
#: role="pinned-only"  --check verifies counts and writes nothing, so no byte gate
#: role="external"     produced outside tools/contentc, gated by the named Step (R05)
#: role="step"         rewritten by another check_all Step, not by a contentc module
#: role="no-check"     producer has no --check; a unit test pins it instead
PRODUCTS: tuple[Product, ...] = (
    Product("armor_report.md", "armors", "report"),
    Product("armors_from_pack.json", "armors", "compiler"),
    Product("board_sizes.json", "geometry", "no-check", note="geometry.py has --out but no --check", covered_by="tools/tests/test_geometry.py"),
    Product("boss_report.md", "bosses", "report"),
    Product("bosses_from_pack.json", "bosses", "compiler"),
    Product("content.pack", "build_content", "compiler"),
    Product("content_fix_candidates.json", "rails", "compiler"),
    Product("coverage.json", "build_content", "pinned-only",
            note="write_coverage runs after the --check early return, so --check writes nothing; the pack's pinned counts are what the gate measures"),
    Product("deck_report.md", "decks", "report"),
    Product("elements.json", "elements_authored", "compiler"),
    Product("engine_smoke.json", "", "external", note="written by tools/engine_smoke.py", gate="engine smoke"),
    Product("fusion_report.md", "fusions", "report"),
    Product("fusions_from_pack.json", "fusions", "compiler"),
    Product("id_mapping.csv", "mapping", "no-check", note="mapping.py has no --check", covered_by="tools/tests/test_mapping.py"),
    Product("id_overlap.json", "build_content", "pinned-only",
            note="same early return as coverage.json: --check never rewrites it"),
    Product("lawn_strings.json", "loc", "compiler"),
    Product("level_extra_rules.json", "level_extra_rules", "compiler"),
    Product("level_mechanics.json", "mechanics", "compiler"),
    Product("level_modules.json", "levelextra", "compiler"),
    Product("level_playability.json", "level_playability", "compiler"),
    Product("loot_binding.json", "loot_binding", "compiler"),
    Product("mapping_report.md", "mapping", "report"),
    Product("metagame.json", "metagame", "compiler"),
    Product("minigame_rules.json", "minigame_rules", "compiler"),
    Product("minigames.json", "minigames", "compiler"),
    Product("original_gaps.json", "original_gaps", "compiler"),
    Product("pack_roster_report.md", "expand", "report"),
    Product("patch_460_9.json", "newin4609", "compiler"),
    Product("plant_blocked.json", "plants_merge", "compiler"),
    Product("plant_families.json", "pfamilies", "compiler"),
    Product("plant_family_table.inc", "plant_family_inc", "compiler"),
    Product("plant_levels.json", "plant_levels", "compiler"),
    Product("plant_playable.json", "plant_playable", "compiler"),
    Product("plantfood_from_pack.json", "plantfood", "compiler"),
    Product("plantfood_report.md", "plantfood", "report"),
    Product("plants_from_pack.json", "expand", "compiler"),
    Product("projectile_report.md", "projectiles", "report"),
    Product("projectiles_from_pack.json", "projectiles", "compiler"),
    Product("rails_report.json", "rails", "compiler"),
    Product("rewards_from_pack.json", "rewards", "compiler"),
    Product("s5_data_gaps.json", "s5scan", "no-check", note="s5scan.py is a one-shot scan without --check", covered_by="tools/tests/test_s5_inventory.py"),
    Product("shop_unlock.json", "shop_unlock", "compiler"),
    Product("spawn_offsets.json", "spawn_offsets", "compiler"),
    Product("vasebreaker.json", "vasebreaker", "compiler"),
    Product("world_diff.md", "worlds", "report"),
    Product("world_gates.json", "worlds", "step",
            note="worlds.py --emit-json rewrites it inside the 'world diff' Step, which compares the fresh render", gate="world diff"),
    Product("zombie_classes.json", "zclasses", "compiler"),
    Product("zombie_family_gaps.json", "zgaps", "compiler"),
    Product("zombie_family_table.inc", "zclasses", "compiler"),
    Product("zombie_roster.json", "zombie_roster", "no-check",
            note="zombie_roster.py has --check, but tools/check_all.ps1 has no step for it yet (out of this task's scope)",
            covered_by="tools/tests/test_zombie_roster.py"),
    # D5 keeps no image, only nine {command, bytes, sha256} rows. The Step parses the
    # table (--list); rendering it needs a desktop exe with the five meta screens, which
    # the gate does not choose for it. battle-snapshot is explicitly unstable, because
    # the renderer's first frame absorbs the load time.
    Product("snapshot_baseline.json", "", "external",
            note="written by tools/snapshot_baseline.py; the Step parses it, images need --check",
            gate="snapshot baseline"),
)

#: modules another agent is still writing: the Step must be a Test-Path guard (R06).
#: A table that lands stops being optional: ``registry()`` folds it in, so its Step has
#: to become a real gate or the suite goes red.
PENDING = (("mechanic_entity_resolution", "mechanic_entity_resolution.json"),)


def landed_pending(pending=PENDING, contentc=CONTENTC):
    """Handoff tables whose compiler has landed: they are compiler products now."""
    return tuple(
        Product(
            name,
            module,
            "compiler",
            note="handoff table that has landed; its Step may stop being a skip (R06)",
        )
        for module, name in pending
        if (contentc / f"{module}.py").is_file()
    )


def registry(pending=PENDING, contentc=CONTENTC):
    """The committed registry plus every handoff table that already landed."""
    return PRODUCTS + landed_pending(pending, contentc)


# --------------------------------------------------------------------------- ast scan
def _tail_of_div_chain(node: ast.AST) -> str | None:
    """``ROOT / "native" / "generated" / "x.json"`` -> ``native/generated/x.json``."""
    parts: list[str] = []
    cur = node
    while isinstance(cur, ast.BinOp) and isinstance(cur.op, ast.Div):
        if not (isinstance(cur.right, ast.Constant) and isinstance(cur.right.value, str)):
            return None
        parts.append(cur.right.value)
        cur = cur.left
    if not parts:
        return None
    text = "/".join(part.strip("/") for part in reversed(parts))
    return text if text.startswith("native/generated/") else None


def declared_paths(module: str) -> set[str]:
    """Every native/generated path the module names in a module-level constant."""
    path = CONTENTC / f"{module}.py"
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    found: set[str] = set()
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Name):
                continue
            rel = _tail_of_div_chain(node.value)
            if rel:
                found.add(rel.removeprefix("native/generated/"))
    return found


def module_has_check(module: str) -> bool:
    """True when the module parses a ``--check`` flag of its own.

    Two styles are in use: ``argparse`` (``add_argument("--check", …)``) and a
    hand-rolled argv loop (``elif arg == "--check"``) that ``plant_levels.py``
    needs because it also supports ``--needle``.  Matching the *source text* would
    be wrong: several modules mention ``--check`` in their docstring only.
    """
    tree = ast.parse((CONTENTC / f"{module}.py").read_text(encoding="utf-8-sig"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "add_argument":
            if any(isinstance(arg, ast.Constant) and arg.value == "--check" for arg in node.args):
                return True
        if isinstance(node, ast.Compare):
            for side in [node.left, *node.comparators]:
                if isinstance(side, ast.Constant) and side.value == "--check":
                    return True
    return False


# --------------------------------------------------------------------------- steps
STEP_HEAD = re.compile(r"^\s*Step\s+'([^']+)'\s*\{", re.M)
MODULE_IN_STEP = re.compile(r"tools/contentc/([A-Za-z_0-9]+)\.py")


@dataclass(frozen=True)
class Step:
    name: str
    body: str

    @property
    def modules(self) -> tuple[str, ...]:
        return tuple(MODULE_IN_STEP.findall(self.body))

    @property
    def checks(self) -> bool:
        return "--check" in self.body

    @property
    def guarded(self) -> bool:
        return "Test-Path" in self.body

    @property
    def skips(self) -> bool:
        return "[skip]" in self.body


def parse_steps(text: str) -> list[Step]:
    """Every ``Step '<name>' { ... }`` with its body, by brace matching.

    Braces inside strings and after ``#`` are ignored: the bodies contain
    ``Write-Host '[skip] …'`` and comments, and a naive counter would run past the
    end of the block.
    """
    steps: list[Step] = []
    for match in STEP_HEAD.finditer(text):
        depth = 0
        index = match.end() - 1
        quote: str | None = None
        while index < len(text):
            char = text[index]
            if quote is not None:
                if char == quote:
                    quote = None
            elif char in "'\"":
                quote = char
            elif char == "#":
                newline = text.find("\n", index)
                index = len(text) if newline == -1 else newline
                continue
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    break
            index += 1
        steps.append(Step(match.group(1), text[match.end():index]))
    return steps


def read_steps() -> list[Step]:
    return parse_steps(CHECK_ALL.read_text(encoding="utf-8-sig"))


# --------------------------------------------------------------------------- checks
def orphans(products: tuple[Product, ...], disk: set[str] | None = None) -> list[str]:
    """Files on disk that no registry entry claims (R02)."""
    present = disk if disk is not None else {p.name for p in GENERATED.iterdir() if p.is_file()}
    registered = {p.name for p in products}
    return sorted(name for name in present if name not in registered)


def undeclared(products: tuple[Product, ...]) -> list[str]:
    """Registry entries the claimed module does not name (R01).

    ``external`` and ``step`` products have no contentc writer, so they are exempt;
    everything else must appear in its module's own constants.
    """
    problems: list[str] = []
    for product in products:
        if not product.module or product.role in {"external", "step"}:
            continue
        declared = declared_paths(product.module)
        if product.name not in declared:
            problems.append(
                f"{product.name}: registered to tools/contentc/{product.module}.py, "
                f"but that module never names it (declares: {sorted(declared) or 'nothing'})"
            )
    return problems


def _without_comment(line: str) -> str:
    """Drop a trailing PowerShell line comment so prose cannot satisfy a guard."""
    cut = line.find("#")
    return line if cut < 0 else line[:cut]


def step_invokes_check(body: str, module: str) -> bool:
    """True when one line of the Step runs ``tools/contentc/<module>.py`` *with* ``--check``.

    The same-line rule matters: ``build_content.py --generated 2026-11-20 --check`` is a
    real gate, while a Step that calls the compiler bare and mentions ``--check`` in a
    comment is not.  Comments are stripped first, otherwise the comment above a bare call
    would read as a gate.
    """
    needle = f"tools/contentc/{module}.py"
    for line in body.splitlines():
        code = _without_comment(line)
        if needle in code and "--check" in code:
            return True
    return False


def gate_gaps(products: tuple[Product, ...], steps: list[Step]) -> list[str]:
    """Products whose required gate is missing from the parsed Step list (R03/R05)."""
    gated = {
        module
        for step in steps
        for module in step.modules
        if step_invokes_check(step.body, module)
    }
    step_names = {step.name for step in steps}
    gaps: list[str] = []
    for product in products:
        if product.role == "compiler":
            if not module_has_check(product.module):
                gaps.append(f"{product.name}: tools/contentc/{product.module}.py has no --check, so it cannot be gated")
            elif product.module not in gated:
                gaps.append(
                    f"{product.name}: tools/contentc/{product.module}.py --check is not a Step in tools/check_all.ps1"
                )
        elif product.role in {"external", "step"}:
            if product.gate not in step_names:
                gaps.append(f"{product.name}: expected the '{product.gate}' Step, which tools/check_all.ps1 does not have")
    return gaps


def squash(text: str) -> str:
    """``level mechanics`` / ``level_mechanics`` / ``LevelMechanics`` -> ``levelmechanics``."""
    return re.sub(r"[^a-z0-9]", "", text.lower())


def step_for_module(steps: list[Step], module: str) -> Step | None:
    for step in steps:
        if module in step.modules and step.checks:
            return step
    return None


# --------------------------------------------------------------------------- tests
class ShippedGateTests(unittest.TestCase):
    """The committed check_all.ps1 against the committed registry."""

    @classmethod
    def setUpClass(cls):
        cls.steps = read_steps()

    def test_check_all_parses_into_steps(self):
        self.assertGreaterEqual(len(self.steps), 30, "the Step parser lost blocks")
        names = {step.name for step in self.steps}
        for expected in ("level mechanics", "level playability", "minigame rules", "tool tests"):
            self.assertIn(expected, names)

    def test_step_names_are_unique(self):
        names = [step.name for step in self.steps]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        self.assertEqual(duplicates, [], f"two Steps share a label: {duplicates}")

    def test_registry_covers_every_generated_file(self):
        missing = orphans(registry())
        self.assertEqual(missing, [], "unregistered products under native/generated (add them to PRODUCTS with a gate): " + ", ".join(missing))

    def test_registry_entries_are_named_by_their_compiler(self):
        self.assertEqual(undeclared(registry()), [])

    def test_every_compiler_product_has_a_check_step(self):
        gaps = gate_gaps(registry(), self.steps)
        self.assertEqual(gaps, [], "products with no gate:\n  " + "\n  ".join(gaps))

    def test_each_gated_module_runs_its_own_check(self):
        for product in registry():
            if product.role != "compiler":
                continue
            step = step_for_module(self.steps, product.module)
            self.assertIsNotNone(step, f"{product.name}: no Step runs tools/contentc/{product.module}.py --check")
            self.assertTrue(
                step_invokes_check(step.body, product.module),
                f"{product.name}: the '{step.name}' Step must call the module with --check on the same line",
            )

    def test_removing_one_step_is_reported(self):
        """The guard has to fail on a missing Step, not just pass on a good tree."""
        target = "level_extra_rules"
        pruned = [step for step in self.steps if target not in step.modules]
        gaps = gate_gaps(registry(), pruned)
        self.assertEqual(len(gaps), 1, gaps)
        self.assertIn("level_extra_rules.json", gaps[0])
        self.assertIn("tools/contentc/level_extra_rules.py --check", gaps[0])

    def test_a_new_unregistered_product_is_reported(self):
        disk = {p.name for p in GENERATED.iterdir() if p.is_file()} | {"brand_new_table.json"}
        missing = orphans(registry(), disk)
        self.assertEqual(missing, ["brand_new_table.json"])

    def test_reports_are_never_gated(self):
        reports = {product.name for product in registry() if product.role == "report"}
        self.assertTrue(reports, "the registry lost every report entry")
        for product in registry():
            if product.role == "report":
                self.assertTrue(product.name.endswith(".md"))
                self.assertEqual(product.gate, "", f"{product.name}: a report cannot claim a Step")
        for step in self.steps:
            self.assertNotIn(
                ".md --check",
                step.body,
                f"'{step.name}' gates a report; reports follow the compiler run instead",
            )

    def test_step_labels_line_up_with_module_names(self):
        """``level mechanics`` ↔ ``level_mechanics.json`` ↔ ``mechanics.py`` (R03)."""
        step = step_for_module(self.steps, "mechanics")
        self.assertIsNotNone(step)
        self.assertEqual(squash(step.name), "levelmechanics")
        self.assertEqual(squash(Path("level_mechanics.json").stem), "levelmechanics")
        self.assertIn("level_mechanics.json", declared_paths("mechanics"))

    def test_pinned_only_products_say_why(self):
        pinned = [product for product in registry() if product.role == "pinned-only"]
        self.assertEqual(sorted(p.name for p in pinned), ["coverage.json", "id_overlap.json"])
        for product in pinned:
            self.assertGreater(len(product.note), 20, f"{product.name}: an exemption needs a reason")

    def test_no_check_products_name_the_test_that_pins_them(self):
        unpinned = [product for product in registry() if product.role == "no-check"]
        self.assertTrue(unpinned)
        for product in unpinned:
            self.assertTrue(product.covered_by, f"{product.name}: name the test that pins it")
            self.assertTrue((REPO / product.covered_by).is_file(), f"{product.name}: {product.covered_by} does not exist")

    def test_external_products_name_their_step(self):
        external = [product for product in registry() if product.role in {"external", "step"}]
        self.assertTrue(external)
        names = {step.name for step in self.steps}
        for product in external:
            self.assertTrue(product.gate, f"{product.name}: name the Step that guards it")
            self.assertIn(product.gate, names, f"{product.name}: Step '{product.gate}' is missing")


class PendingHandoffTests(unittest.TestCase):
    """R06: a Step for a file another agent has not landed yet must be guarded."""

    def test_pending_step_exists_and_is_guarded(self):
        steps = read_steps()
        for module, product in PENDING:
            step = step_for_module(steps, module)
            self.assertIsNotNone(step, f"{module}: no Step at all for the pending compiler ({product})")
            self.assertTrue(step.guarded, f"'{step.name}' must be wrapped in Test-Path")
            self.assertTrue(step.skips, f"'{step.name}' must print a skip when the file is absent")

    def test_unguarded_pending_step_would_be_called_a_lie(self):
        """A guard only counts when it is real: the same body without Test-Path fails."""
        fake = [Step("mechanic entity resolution", "python tools/contentc/mechanic_entity_resolution.py --check")]
        self.assertFalse(fake[0].guarded)

    def test_an_absent_handoff_table_is_not_required(self):
        """Before the compiler lands there is nothing to gate, so no gap is reported."""
        pending = (("no_such_compiler_yet", "no_such_table.json"),)
        self.assertEqual(landed_pending(pending), ())
        self.assertEqual(gate_gaps(registry(pending), read_steps()), [])

    def test_a_landed_handoff_table_becomes_a_compiler_product(self):
        """Once the compiler exists the table must have a real gate (R06 second half)."""
        pending = (("mechanics", "level_mechanics.json"),)
        landed = landed_pending(pending)
        self.assertEqual([product.name for product in landed], ["level_mechanics.json"])
        self.assertEqual(landed[0].role, "compiler")
        self.assertEqual(gate_gaps(registry(pending), read_steps()), [])

    def test_a_landed_handoff_without_a_step_is_reported(self):
        """``decks.py`` exists but has no Step, so a table it lands must be named."""
        pending = (("decks", "deck_extra.json"),)
        steps = read_steps()
        baseline = gate_gaps(registry(), steps)
        added = [gap for gap in gate_gaps(registry(pending), steps) if gap not in baseline]
        self.assertEqual(len(added), 1, added)
        self.assertIn("deck_extra.json", added[0])
        self.assertIn("tools/contentc/decks.py --check", added[0])

    def test_a_comment_is_not_a_gate(self):
        """A bare call with ``--check`` only in the comment above it is still ungated."""
        body = "    # python tools/contentc/decks.py --check\n    python tools/contentc/decks.py\n"
        self.assertFalse(step_invokes_check(body, "decks"))


class SyntaxTests(unittest.TestCase):
    """The gate script itself must still parse: a broken check_all is silent otherwise."""

    @unittest.skipUnless(shutil.which("pwsh"), "pwsh not installed")
    def test_check_all_parses_as_powershell(self):
        script = (
            "$e=$null;$t=$null;"
            f"[System.Management.Automation.Language.Parser]::ParseFile('{CHECK_ALL.as_posix()}',[ref]$t,[ref]$e)|Out-Null;"
            "if($e.Count){$e|ForEach-Object{$_.Message};exit 1}else{exit 0}"
        )
        result = subprocess.run(["pwsh", "-NoProfile", "-Command", script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
