"""Integration seam guards; gameplay execution is a separate acceptance gate."""

import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]


class HookTests(unittest.TestCase):
    def test_real_rule_seams(self):
        self.assertIn(
            "chaos_ward_count(num_wards_at(x,y))", (ROOT / "src/monmove.c").read_text()
        )
        self.assertIn(
            "u.uhunger -= chaos_food(hunger)", (ROOT / "src/eat.c").read_text()
        )

    def test_persistent_player_state(self):
        self.assertIn("struct chaos_state chaos", (ROOT / "include/you.h").read_text())
        self.assertIn(
            "chaos_state_valid(&u.chaos)", (ROOT / "src/restore.c").read_text()
        )

    def test_safe_seams(self):
        for file, hook in [
            ("pray.c", 'chaos_safe("pray")'),
            ("timeout.c", 'chaos_safe("sleep")'),
            ("do.c", 'chaos_safe("level_enter")'),
            ("allmain.c", "chaos_observe()"),
        ]:
            self.assertIn(hook, (ROOT / "src" / file).read_text())

    def test_build_toggle(self):
        self.assertIn("CHAOS ?= 1", (ROOT / "GNUmakefile").read_text())
        self.assertIn("CHAOS", (ROOT / "util/makedefs.c").read_text())
