"""Actual terminal game through the offline play supervisor, never a live model."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from chaos.director import Mailbox
from gameplay_support import Game, ROOT


@unittest.skipUnless(
    os.environ.get("NYARLATHACK_GAME_TESTS") == "1", "real game opt-in"
)
class LauncherGameplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(tempfile.mkdtemp(prefix="nyarl-launcher-gameplay-"))
        cls.clock = cls.root / "clock.so"
        subprocess.run(
            [
                "cc",
                "-shared",
                "-fPIC",
                str(ROOT / "tests/chaos/replay_clock.c"),
                "-ldl",
                "-o",
                str(cls.clock),
            ],
            check=True,
            timeout=30,
        )
        print("LAUNCHER_GAMEPLAY_ARTIFACTS=" + str(cls.root), flush=True)

    def game(self, name, options):
        game = Game(
            ROOT / "dnethackdir",
            self.clock,
            root=self.root / name,
            launcher_options=options,
        )
        self.addCleanup(game.close)
        return game

    def accepted(self, game):
        return [
            e
            for e in game.events()
            if e["event"] == "ack" and e["status"] == "accepted"
        ]

    def test_one_command_pack_admission_save_restore_and_cleanup(self):
        game = self.game("pack-restore", [])
        game.start()
        self.assertEqual([e["id"] for e in self.accepted(game)], [1])
        self.assertIn(b"The shadows lean closer.", game.raw)
        with self.assertRaises(ValueError):
            Mailbox(game.run)
        game.wait_turns(2)
        self.assertEqual(game.save(), 0)
        with Mailbox(game.run):
            pass
        self.assertTrue(list((game.game / "save").iterdir()))
        game.start()
        game.wait_turns(2)
        self.assertEqual([e["id"] for e in self.accepted(game)], [1])
        self.assertEqual(game.quit(), 0)
        with Mailbox(game.run):
            pass
        self.assertTrue((game.run / "events.jsonl").is_file())
        self.assertIn(b"director stopped; run data retained", game.raw)

    def test_game_continues_after_director_runtime_expires(self):
        game = self.game("short-director", ["--max-runtime", "0.05"])
        game.start()
        game.wait_turns(3)
        self.assertEqual([e["id"] for e in self.accepted(game)], [1])
        self.assertEqual(game.quit(), 0)
        with Mailbox(game.run):
            pass
