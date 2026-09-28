"""#165: the echo hound through ordinary `chaos play --ordinary --haunt`.

A real nonwizard terminal game through the launcher: no #setsanity, no wizard
commands. Every key is chosen from the rendered screen alone
(haunt_explorer.Player): leave the 4x3 start room without backtracking, then
pace back and forth in the first larger room. The run directory's event
stream and receipts are read only for the assertions.

Why leave first: the shadow trial runs once per game, and in the start room
the trial's evasive player cannot get away from the hound, so pacing there
spends the one trial on a rejection (#190).
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
from haunt_explorer import DELTA, Player

TELEGRAPH = "Something has learned the rhythm of your footsteps."
PACK = ROOT / "chaos/packs/footsteps.lua"


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

    def count(self, game, event):
        return sum(e["event"] == event for e in game.events())

    def decided(self, game):
        return any(d in ("accepted", "rejected") for d in self.haunting(game))

    def test_ordinary_haunt_trial_telegraph_hound_control_restore_expiry(self):
        options = ["--ordinary", "--haunt", "--max-runtime", "300"]
        game = self.game("haunt", options)
        game.start()
        self.assertFalse(game.wizard)
        installed = (game.run / "haunting.lua").read_bytes()
        self.assertEqual(installed, PACK.read_bytes())
        player = Player(game)
        self.assertEqual(len(player.start_room), 12, player.screen.text())

        # 1. Leave the start room without ever standing on a square twice.
        player.leave()
        self.assertEqual(len(player.visited), len(set(player.visited)))
        self.assertGreater(len(player.room(player.me())), len(player.start_room))
        self.assertEqual(self.count(game, "backtrack"), 0)
        self.assertEqual(self.haunting(game), [])

        # 2. Pace back and forth in the larger room: natural backtracking.
        self.assertTrue(player.pace(lambda: self.decided(game)), self.haunting(game))
        self.assertGreater(self.count(game, "backtrack"), 0)

        # Shadow trial: the Dreamlands receipt is written before admission.
        report = json.loads((game.run / "dreamlands.json").read_text())
        self.assertEqual(report["sandboxed"], 1, report)
        self.assertEqual(report["accepted"], 1, report)
        self.assertEqual(report["escaped"], 1, report)
        self.assertEqual(self.haunting(game), ["pre_admitted", "accepted"])
        self.assertEqual((game.run / "haunting-used.lua").read_bytes(), installed)
        accepted = [
            e
            for e in game.events()
            if e["event"] == "haunting" and e["detail"] == "accepted"
        ][0]
        self.assertEqual((accepted["spent"], accepted["sanity"]), (2, 100))

        # 3. The telegraph is on screen, before any hound step.
        self.assertIn(TELEGRAPH, player.screen.line(0))
        self.assertEqual(self.count(game, "haunt_step"), 0)

        # 4. The hound is on the map: the player's own ';' look names it.
        names = [player.farlook(d) for d in player.find("d")]
        self.assertTrue(any("echo hound" in n for n in names), names)

        # 5. Ordinary movement control: each open step moves the '@' exactly
        # as asked, and the hound is seen following the trail.
        _, lo, hi, back, forth = player.pace_line()
        moved = 0
        for key in ([forth] * hi + [back] * (lo + hi) + [forth] * lo) * 3:
            if self.count(game, "haunt_step") and moved >= 4:
                break
            before, after = player.step(key)
            dx, dy = DELTA[key]
            if after != before:
                self.assertEqual(after, (before[0] + dx, before[1] + dy))
                moved += 1
        self.assertGreaterEqual(moved, 4)
        self.assertGreater(self.count(game, "haunt_step"), 0)

        # 6. Save and restore mid-haunt through the launcher: restore only
        # verifies the installed pack; no second trial and no second debit.
        self.assertEqual(game.save(), 0)
        game.launcher_fresh = False
        game.start()
        player = Player(game)
        self.assertEqual(self.haunting(game), ["pre_admitted", "accepted"])
        self.assertEqual(json.loads((game.run / "dreamlands.json").read_text()), report)
        restored = [
            e
            for e in game.events()
            if e["event"] == "session" and e["detail"] == "restore"
        ]
        self.assertEqual(len(restored), 1)
        self.assertEqual(restored[0]["spent"], 2)

        # 7. Expiry: the admitted haunt ends 60 moves after admission.
        for _ in range(90):
            if "expired" in self.haunting(game):
                break
            player.step("s")
            self.assertNotIn("You die", player.screen.line(0))
        self.assertEqual(self.haunting(game), ["pre_admitted", "accepted", "expired"])
        expired = [e for e in game.events() if e["detail"] == "expired"][0]
        self.assertGreaterEqual(expired["turn"], accepted["turn"] + 60)
        steps = self.count(game, "haunt_step")
        for _ in range(3):
            player.step("s")
        self.assertEqual(self.count(game, "haunt_step"), steps)

        # 8. The post-mortem reveal narrates the haunt and when it ended.
        self.assertEqual(game.quit(), 0)
        dump = "".join(
            p.read_text(errors="replace") for p in (game.game / "dumplog").iterdir()
        )
        section = dump[dump.index("The Crawling Chaos remembers.") :]
        self.assertIn("a haunting was admitted.", section)
        self.assertIn(f"Ended: its hunt ended on turn {expired['turn']}.", section)
        # The launcher's free arrival omen is the other admission (cost 0).
        self.assertRegex(
            (game.game / "xlogfile").read_text(),
            r":chaos_admitted=2:chaos_delivered=2:chaos_spent=2\n$",
        )

    def test_without_haunt_flag_no_candidate_and_no_haunting(self):
        # The same screen-driven walk and pacing, without --haunt: stock play.
        game = self.game("control", ["--ordinary", "--max-runtime", "120"])
        game.start()
        player = Player(game)
        player.leave()
        player.pace(lambda: False, limit=20)
        self.assertGreater(self.count(game, "backtrack"), 0)
        self.assertEqual(game.quit(), 0)
        self.assertFalse((game.run / "haunting.lua").exists())
        self.assertFalse((game.run / "haunting-used.lua").exists())
        self.assertFalse((game.run / "dreamlands.json").exists())
        self.assertEqual(self.haunting(game), [])
        self.assertNotIn(TELEGRAPH.encode(), bytes(game.raw))
        self.assertTrue(re.search(rb"Really quit", bytes(game.raw)))
        # Only the launcher's free arrival omen was admitted: nothing spent.
        self.assertRegex((game.game / "xlogfile").read_text(), r":chaos_spent=0\n$")


if __name__ == "__main__":
    unittest.main()
