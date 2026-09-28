"""#165: the echo hound through ordinary `chaos play --ordinary --haunt`.

A real nonwizard terminal game through the launcher: no #setsanity, no wizard
commands. Input is decided only from what the screen shows plus the run
directory's public event stream; the director sidecar is the offline pack.
"""

import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from gameplay_support import Game, ROOT
from artifact_hygiene import RetainOnFailure

TELEGRAPH = b"Something has learned the rhythm of your footsteps."
# Back and forth along one axis, then the other: natural backtracking.
WALK = "lhlhlhjkjkjk" * 4


@unittest.skipUnless(
    os.environ.get("NYARLATHACK_GAME_TESTS") == "1", "real game opt-in"
)
class OrdinaryHauntTests(RetainOnFailure):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(
            cls.track_class_artifacts(tempfile.mkdtemp(prefix="nyarl-haunt-ordinary-"))
        )
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
        print("HAUNT_ORDINARY_ARTIFACTS=" + str(cls.root), flush=True)

    def game(self, name, options):
        game = Game(
            ROOT / "dnethackdir",
            self.clock,
            root=self.root / name,
            ordinary=True,
            launcher_fresh=True,
            launcher_options=options,
        )
        self.addCleanup(game.close)
        return game

    def haunting(self, game):
        return [e["detail"] for e in game.events() if e["event"] == "haunting"]

    def walk_until_admitted(self, game):
        for key in WALK:
            game.more(game.send(key))
            if "accepted" in self.haunting(game) or "rejected" in self.haunting(game):
                return
        self.fail("no haunting decision: " + repr(self.haunting(game)))

    def test_ordinary_haunt_trial_telegraph_hound_control_restore_expiry(self):
        game = self.game("haunt", ["--ordinary", "--haunt", "--max-runtime", "120"])
        game.start()
        self.assertFalse(game.wizard)
        installed = (game.run / "haunting.lua").read_bytes()
        self.assertEqual(installed, (ROOT / "chaos/packs/footsteps.lua").read_bytes())
        self.walk_until_admitted(game)
        # Shadow trial: the Dreamlands receipt is written before admission.
        report = json.loads((game.run / "dreamlands.json").read_text())
        self.assertEqual(report["sandboxed"], 1, report)
        self.assertEqual(report["accepted"], 1, report)
        self.assertEqual(self.haunting(game), ["pre_admitted", "accepted"])
        self.assertEqual((game.run / "haunting-used.lua").read_bytes(), installed)
        accepted = [
            e
            for e in game.events()
            if e["event"] == "haunting" and e["detail"] == "accepted"
        ][0]
        self.assertEqual((accepted["spent"], accepted["sanity"]), (2, 100))
        # Telegraph precedes the spawn, in the terminal.
        self.assertIn(TELEGRAPH, bytes(game.raw))
        # A spawned hound, seen by the player (the event is emitted only when
        # the player can see the designated monster move).
        for key in "." * 10:
            game.more(game.send(key))
            if any(e["event"] == "haunt_step" for e in game.events()):
                break
        self.assertTrue(any(e["event"] == "haunt_step" for e in game.events()))
        # Ordinary movement control: the player's own steps still move them
        # (each return to a remembered square is a new backtrack event).
        before = sum(e["event"] == "backtrack" for e in game.events())
        for key in "hlhl":
            game.more(game.send(key))
        self.assertGreater(
            sum(e["event"] == "backtrack" for e in game.events()), before
        )
        # Save/restore mid-haunt: exactly one admission, no second trial.
        self.assertEqual(game.save(), 0)
        game.launcher_fresh = False
        game.start()
        self.assertEqual(self.haunting(game).count("accepted"), 1)
        self.assertEqual(self.haunting(game).count("pre_admitted"), 1)
        # Expiry: the admitted haunt lasts 60 moves; search until it ends.
        for _ in range(80):
            game.more(game.send("s"))
            if "expired" in self.haunting(game):
                break
            if b"You die" in bytes(game.raw[-2000:]):
                self.fail("died before expiry")
        self.assertIn("expired", self.haunting(game))
        self.assertEqual(game.quit(), 0)
        self.assertEqual(self.haunting(game).count("accepted"), 1)

    def test_without_haunt_flag_no_candidate_and_no_haunting(self):
        game = self.game("control", ["--ordinary", "--max-runtime", "60"])
        game.start()
        for key in WALK[:16]:
            game.more(game.send(key))
        self.assertEqual(game.quit(), 0)
        self.assertFalse((game.run / "haunting.lua").exists())
        self.assertFalse((game.run / "dreamlands.json").exists())
        self.assertEqual(self.haunting(game), [])
        self.assertNotIn(TELEGRAPH, bytes(game.raw))
        self.assertTrue(re.search(rb"Really quit", bytes(game.raw)))


if __name__ == "__main__":
    unittest.main()
