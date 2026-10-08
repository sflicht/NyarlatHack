"""The curio window by absolute depth, in a real native game (#item 2).

Real native game, opt-in (NYARLATHACK_GAME_TESTS=1, CHAOS=1 build), wizard
mode for level teleport only, under the test clock (fixed map). The handwritten
offline fixture SOURCE (not model output) is published into the run directory
mid-game, so the engine admits it at the next level change on a level that was
already generated: admission and placement are on different levels.

Each case: admitted on one level, moved to another already-visited level,
SAVED there and restored in a fresh process, then a fresh level inside the
window is generated. The curio is placed exactly once, and no later level
change places another. This is the #239 lesson: state that crosses a save on
a level other than the one it was admitted on must still work.

Under the old window (main DL1-2 admission, DL3+ expiry, Mines never) the
main case expires at depth 3 and the Mines case never admits.
"""

import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from gameplay_support import ANSI, ROOT, Game
from test_curio_gameplay import SOURCE

DLVL = re.compile(rb"Dlvl:(\d+)")


@unittest.skipUnless(
    os.environ.get("NYARLATHACK_GAME_TESTS") == "1", "real game opt-in"
)
class CurioWindowGameplayTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual((ROOT / ".chaos-build").read_text().strip(), "1")
        self.artifacts = Path(tempfile.mkdtemp(prefix="nyarl-curio-window-"))
        print("CURIO_WINDOW_ARTIFACTS=" + str(self.artifacts), flush=True)
        self.clock = self.artifacts / "clock.so"
        subprocess.run(
            [
                "cc",
                "-shared",
                "-fPIC",
                str(ROOT / "tests/chaos/replay_clock.c"),
                "-ldl",
                "-o",
                str(self.clock),
            ],
            check=True,
        )

    def game(self, name):
        game = Game(
            ROOT / "dnethackdir", self.clock, wizard=True, root=self.artifacts / name
        )
        self.addCleanup(game.close)
        return game

    def depth(self, game):
        found = DLVL.findall(ANSI.sub(b"", bytes(game.raw)))
        self.assertTrue(found, "no status line seen")
        return int(found[-1])

    def go(self, game, level):
        """Wizard ^V to a depth in the current dungeon."""
        game.more(game.send(b"\x16"))
        game.more(game.send(str(level) + "\n"))
        self.assertEqual(self.depth(game), level)

    def go_menu(self, game, label, depth):
        """Wizard ^V ? and pick a menu row by its text (another dungeon)."""
        game.send(b"\x16")
        text = game.send("?\n")
        row = re.compile(
            rb"([a-zA-Z]) - +" + re.escape(label) + rb": " + str(depth).encode()
        )
        for _ in range(8):
            m = row.search(text.replace(b"\r", b"\n"))
            if m:
                break
            text = game.send(">")
        else:
            self.fail("menu row not found: " + label.decode())
        text = game.send(m.group(1))
        if b"Level teleport to where" in text:
            text = game.send("\n")
        game.more(text)
        self.assertEqual(self.depth(game), depth)

    def publish(self, game):
        path = game.run / "curio.lua"
        path.write_bytes(SOURCE)
        path.chmod(0o600)

    def curio(self, game):
        return [e["detail"] for e in game.events() if e["event"] == "curio"]

    def save_restore(self, game):
        self.assertEqual(game.save(), 0)
        self.assertEqual(len(list((game.game / "save").iterdir())), 1)
        before = len(game.raw)
        game.start()
        self.assertIn(b"Restoring save file", ANSI.sub(b"", bytes(game.raw[before:])))
        self.assertFalse(list((game.game / "save").iterdir()), "restore consumed save")

    def test_main_admit_depth2_restore_depth3_place_depth4(self):
        game = self.game("main")
        game.start()
        self.go(game, 2)
        self.go(game, 3)
        self.assertEqual(self.curio(game), [])
        self.publish(game)
        self.go(game, 2)  # visited: admitted here, nothing placed
        self.assertIn("admitted", self.curio(game))
        self.go(game, 3)  # visited: no placement; under the old window, expiry
        self.assertNotIn("expired", self.curio(game))
        self.save_restore(game)
        self.assertEqual(self.depth(game), 3)
        self.go(game, 4)  # fresh, depth 4: placed (old window: never)
        self.assertEqual(self.curio(game).count("placed"), 1)
        for level in (5, 6, 3, 7):
            self.go(game, level)
        details = self.curio(game)
        self.assertEqual(details.count("placed"), 1)
        self.assertNotIn("expired", details)
        self.assertEqual((game.run / "curio-used.lua").read_bytes(), SOURCE)
        self.assertEqual(game.quit(), 0)

    # Mines cases run WITHOUT the test clock: under tests/chaos/replay_clock.c
    # (fixed seed and time) generating a Gnomish Mines filler level does not
    # return, on main as well (found here; not this change). The map then
    # varies, so the Mines depths are read from the wizard ^V ? menu.
    def mines_game(self, name):
        noclock = self.artifacts / "noclock.so"
        if not noclock.exists():
            (self.artifacts / "noclock.c").write_text("int nyarl_noclock;\n")
            subprocess.run(
                [
                    "cc",
                    "-shared",
                    "-fPIC",
                    str(self.artifacts / "noclock.c"),
                    "-o",
                    str(noclock),
                ],
                check=True,
            )
        game = Game(
            ROOT / "dnethackdir", noclock, wizard=True, root=self.artifacts / name
        )
        self.addCleanup(game.close)
        return game

    def mines_branch(self, game):
        """Depth of the Mines' first level (the main-dungeon branch level)."""
        game.send(b"\x16")
        text = game.send("?\n")
        m = re.search(rb"Stair to The Gnomish Mines: (\d)", text.replace(b"\r", b"\n"))
        self.assertIsNotNone(m)
        game.more(game.send(b"\x1b"))
        game.more(game.send(b"\x1b"))
        return int(m.group(1))

    # In this dungeon the Mines' first level (depth b, the "Stair to Vlad's
    # Tower" row) sits above the Mines entrance; a numbered ^V from there
    # leads to Vlad's Tower, so the main dungeon is reached by its menu row.
    def mines_top(self, game, b):
        self.go_menu(game, b"Stair to Vlad's Tower", b)

    def main_branch(self, game, b):
        self.go_menu(game, b"Stair to The Gnomish Mines", b)

    def test_main_admit_mines_restore_mines_place(self):
        game = self.mines_game("main-mines")
        game.start()
        b = self.mines_branch(game)  # 2..4
        self.mines_top(game, b)
        self.main_branch(game, b)
        self.assertEqual(self.curio(game), [])
        self.publish(game)
        self.go(game, 1)  # visited main DL1: admitted in the main dungeon
        self.assertIn("admitted", self.curio(game))
        self.mines_top(game, b)  # visited Mines level
        self.save_restore(game)
        self.assertEqual(self.depth(game), b)
        self.assertNotIn("placed", self.curio(game))
        self.go(game, b + 1)  # fresh Mines filler at depth 3..5: placed
        self.assertEqual(self.curio(game).count("placed"), 1)
        for level in (6, b, 7):
            self.go(game, level)
        details = self.curio(game)
        self.assertEqual(details.count("placed"), 1)
        self.assertNotIn("expired", details)
        self.assertEqual((game.run / "curio-used.lua").read_bytes(), SOURCE)
        self.assertEqual(game.quit(), 0)

    def test_mines_admit_main_restore_main_place(self):
        game = self.mines_game("mines-main")
        game.start()
        b = self.mines_branch(game)
        self.mines_top(game, b)
        self.main_branch(game, b)
        self.publish(game)
        self.mines_top(game, b)  # visited Mines level: admitted in the Mines
        details = self.curio(game)
        self.assertIn("admitted", details)
        self.assertNotIn("placed", details)
        self.main_branch(game, b)  # visited main level
        self.save_restore(game)
        self.assertEqual(self.depth(game), b)
        fresh = min({2, 3, 4} - {b})  # unvisited ordinary main level
        self.go(game, fresh)  # fresh main level in the window: placed
        self.assertEqual(self.curio(game).count("placed"), 1)
        for level in (1, 6, b):
            self.go(game, level)
        details = self.curio(game)
        self.assertEqual(details.count("placed"), 1)
        self.assertNotIn("expired", details)
        self.assertEqual(game.quit(), 0)

    def test_mines_depth6_expires_unplaced(self):
        game = self.mines_game("mines-expiry")
        game.start()
        b = self.mines_branch(game)
        self.mines_top(game, b)
        self.main_branch(game, b)
        self.publish(game)
        self.mines_top(game, b)  # admitted at Mines depth b
        self.assertIn("admitted", self.curio(game))
        self.go(game, 6)  # fresh Mines level at depth 6: no placement, expiry
        details = self.curio(game)
        self.assertNotIn("placed", details)
        self.assertIn("expired", details)
        self.go(game, b + 1)  # fresh, in the window, but the chance is gone
        self.assertNotIn("placed", self.curio(game))
        self.assertEqual(game.quit(), 0)

    def test_sokoban_never_places_or_expires(self):
        # Sokoban (depth 3-6 in this map, all special levels) is its own
        # branch: an admitted curio is neither placed nor expired there, and
        # the next fresh main level inside the window takes it.
        game = self.game("sokoban")
        game.start()
        self.publish(game)
        self.go(game, 2)  # fresh DL2: placement is checked before arrival
        self.assertIn("admitted", self.curio(game))
        self.assertNotIn("placed", self.curio(game))
        self.go_menu(game, b"soko2", 4)
        self.go_menu(game, b"soko1", 3)
        details = self.curio(game)
        self.assertNotIn("placed", details)
        self.assertNotIn("expired", details)
        self.go_menu(game, b"Stair to Sokoban", 7)  # depth 7: expiry, unplaced
        self.assertNotIn("placed", self.curio(game))
        self.assertIn("expired", self.curio(game))
        self.assertEqual(game.quit(), 0)
