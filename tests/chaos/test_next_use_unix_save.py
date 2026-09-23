"""Linked save/exit of an admitted next-use program. Not ordinary play."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from chaos.next_use_envelope import engine_run_hex, publish_envelope
from gameplay_support import Game, ROOT


@unittest.skipUnless(
    os.environ.get("NYARLATHACK_GAME_TESTS") == "1", "real game opt-in"
)
class NextUseUnixSaveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert (ROOT / ".chaos-build").read_text().strip() == "1"
        cls.artifacts = Path(tempfile.mkdtemp(prefix="nyarl-next-use-unix-save-"))
        cls.clock = cls.artifacts / "clock.so"
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
                str(cls.clock),
            ],
            check=True,
            timeout=30,
        )

    def test_save_exit_restore_does_not_readmit(self):
        os.environ["NYARLATHACK_NEXT_USE_ADMIT"] = "1"
        os.environ["NYARLATHACK_OBSERVATIONS"] = "1"
        game = Game(
            ROOT / "dnethackdir",
            self.clock,
            observe=True,
            wizard=True,
            root=self.artifacts / "save",
        )
        self.addCleanup(game.close)
        game.start()
        text = game.send("#wish\n")
        self.assertIn(b"For what do you wish?", text)
        text = game.more(game.send("uncursed tin whistle\n"))
        slot = None
        for line in text.splitlines():
            if b" - " in line and b"whistle" in line.lower():
                slot = line.split(b" - ", 1)[0][-1:]
                break
        self.assertIsNotNone(slot, text)
        text = game.send("a")
        self.assertIn(b"apply", text.lower())
        text = game.more(game.send(slot))
        self.assertIn(b"whistling sound", text)
        notices = [
            event
            for event in game.events()
            if event.get("event") == "observation"
            and event.get("observation", {}).get("stage") == "notice"
            and event["observation"].get("operation") == "whistling"
        ]
        completed = [
            event
            for event in game.events()
            if event.get("event") == "observation"
            and event.get("observation", {}).get("stage") == "completed"
            and event["observation"].get("operation") == "whistling"
        ]
        self.assertEqual(len(notices), 1)
        self.assertEqual(len(completed), 1)
        notice, done = notices[0], completed[0]
        row = {
            "family": "W",
            "op": "quiet",
            "origin": {
                "root_seq": notice["observation"]["root_seq"],
                "notice_seq": notice["seq"],
                "end_seq": done["seq"],
                "fact": notice["observation"]["fact"],
            },
        }
        host = {
            "at": 2,
            "id": 1,
            "level_dlevel": 1,
            "level_dnum": 0,
            "move": notice["turn"],
            "run": engine_run_hex(game.run),
            "variant": 0,
        }
        publish_envelope(game.run, row, host)
        before = game.events()[-1]["spent"]
        text = game.sanity(60)
        self.assertIn(b"The next whistle may call unusual attention.", text)
        text = game.sanity(40)
        self.assertNotIn(b"The next whistle may call unusual attention.", text)
        spent = game.events()[-1]["spent"]
        self.assertEqual(spent, before + 1)
        envelope = game.run / "next_use-envelope.json"
        self.assertTrue(envelope.is_file())
        envelope.unlink()
        self.assertEqual(game.save(), 0)
        self.assertTrue(list((game.game / "save").iterdir()))
        game.start()
        restored = [
            event
            for event in game.events()
            if event.get("event") == "session" and event.get("detail") == "restore"
        ]
        self.assertEqual(len(restored), 1)
        self.assertEqual(restored[0]["spent"], spent)
        text = game.sanity(80)
        self.assertNotIn(b"The next whistle may call unusual attention.", text)
        self.assertEqual(game.events()[-1]["spent"], spent)
        self.assertEqual(game.quit(), 0)
