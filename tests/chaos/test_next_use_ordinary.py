"""Ordinary bard whistle through play --next-use. Not wizard and not a seed hunt."""

import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest

from gameplay_support import Game, ROOT


def clock(path):
    subprocess.run(
        [
            "cc",
            "-shared",
            "-fPIC",
            "-Wall",
            "-Wextra",
            "-Werror",
            str(ROOT / "tests/chaos/replay_clock.c"),
            "-ldl",
            "-o",
            str(path),
        ],
        check=True,
        timeout=30,
    )


@unittest.skipUnless(
    os.environ.get("NYARLATHACK_GAME_TESTS") == "1",
    "opt-in actual game tests: NYARLATHACK_GAME_TESTS=1",
)
class OrdinaryNextUseTests(unittest.TestCase):
    def test_starting_whistle_admits_once_through_the_launcher(self):
        artifacts = Path(tempfile.mkdtemp(prefix="nyarl-ordinary-next-use-"))
        so = artifacts / "clock.so"
        clock(so)
        game = Game(
            ROOT / "dnethackdir",
            so,
            observe=True,
            wizard=False,
            ordinary=True,
            launcher_fresh=True,
            launcher_options=["--ordinary", "--next-use", "--max-runtime", "90"],
            root=artifacts / "case",
        )
        try:
            game.start()
            game.more(game.send("i"))
            game.send("\x1b")
            applied = game.more(game.send("ag"))
            self.assertIn(b"high whistling sound", applied)
            envelope = game.run / "next_use-envelope.json"
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline and not envelope.exists():
                time.sleep(0.2)
            self.assertTrue(envelope.exists(), "host-built envelope was not published")
            game.more(game.send("#pray\ny"))
            game.send("\x1b")
            game.quit()
        finally:
            game.close()
        self.assertEqual(game.events()[-1]["spent"], 1)
        self.assertEqual(
            len((game.run / "next_use-receipt.jsonl").read_text().splitlines()), 1
        )
        raw = (artifacts / "case" / "terminal.raw").read_bytes()
        self.assertIn(b"The next whistle may call unusual attention.", raw)
        ops = [
            event.get("observation", {}).get("stage")
            for event in game.events()
            if event.get("observation", {}).get("operation") == "whistling"
        ]
        self.assertEqual(ops, ["started", "notice", "completed"])
