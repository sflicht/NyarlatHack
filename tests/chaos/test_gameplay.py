"""Opt-in tests of actual linked C physics and terminal game processes.
Run after make install CHAOS=1 with NYARLATHACK_GAME_TESTS=1.
"""

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from gameplay_support import Game, ROOT


@unittest.skipUnless(
    os.environ.get("NYARLATHACK_GAME_TESTS") == "1",
    "opt-in actual game tests: NYARLATHACK_GAME_TESTS=1",
)
class GameplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.artifacts = Path(tempfile.mkdtemp(prefix="nyarlathack-acceptance-"))
        cls.clock = cls.artifacts / "clock.so"
        cls.current = ROOT / "dnethackdir"
        cls.stock = Path(
            os.environ.get(
                "NYARLATHACK_STOCK_DIR",
                "/home/hermes/.local/share/nyarlathack/baselines/ff37b3a7a",
            )
        )
        assert (ROOT / ".chaos-build").read_text().strip() == "1", (
            "build CHAOS=1 before these tests"
        )
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
        print("GAMEPLAY_ARTIFACTS=" + str(cls.artifacts), flush=True)

    def game(self, name, source=None, observe=True, wizard=False):
        g = Game(
            source or self.current, self.clock, observe, wizard, self.artifacts / name
        )
        self.addCleanup(g.close)
        return g

    def test_real_linked_hunger_and_ward_effects_expire(self):
        b = self.artifacts / "linked"
        b.mkdir()
        subprocess.run(
            [
                "objcopy",
                "--redefine-sym",
                "main=original_game_main",
                str(ROOT / "sys/unix/unixmain.o"),
                str(b / "unixmain.o"),
            ],
            check=True,
            timeout=20,
        )
        objects = (
            sorted((ROOT / "src").glob("*.o"))
            + [
                ROOT / "sys/unix/unixres.o",
                ROOT / "sys/unix/unixunix.o",
                b / "unixmain.o",
                ROOT / "sys/share/ioctl.o",
                ROOT / "sys/share/unixtty.o",
            ]
            + sorted((ROOT / "win/tty").glob("*.o"))
            + sorted((ROOT / "win/curses").glob("*.o"))
        )
        subprocess.run(
            [
                "cc",
                "-g",
                "-DCHAOS",
                "-I" + str(ROOT / "include"),
                str(ROOT / "tests/chaos/game_rules.c"),
                *map(str, objects),
                "-lncursesw",
                "-ltinfo",
                "-lm",
                "-o",
                str(b / "rules"),
            ],
            check=True,
            timeout=45,
        )
        p = subprocess.run(
            [str(b / "rules")], capture_output=True, text=True, timeout=15
        )
        (b / "result.txt").write_text(p.stdout + p.stderr)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("real gethungry", p.stdout)
        self.assertIn("real onscary", p.stdout)

    def test_stock_inactive_and_on_empty_equal(self):
        games = []
        for name, source, observe in [
            ("stock", self.stock, False),
            ("inactive", self.current, False),
            ("empty", self.current, True),
        ]:
            g = self.game(name, source, observe)
            g.start()
            g.wait_turns(12)
            self.assertEqual(g.quit(), 0)
            games.append(g)
        for g in games[1:]:
            self.assertEqual(g.inputs, games[0].inputs)
            self.assertEqual(g.raw, games[0].raw)
            self.assertEqual(
                (g.game / "xlogfile").read_bytes(),
                (games[0].game / "xlogfile").read_bytes(),
            )
        self.assertTrue(games[2].events())
        self.assertFalse(any(e["event"] == "ack" for e in games[2].events()))

    def test_real_save_active_and_pending_roundtrip(self):
        g = self.game("save-roundtrip", wizard=True)
        g.start()
        g.request("ward_efficacy", 1, 2, 10)
        g.sanity(60)
        accepted = [
            e for e in g.events() if e["event"] == "ack" and e["status"] == "accepted"
        ]
        self.assertEqual([e["id"] for e in accepted], [1])
        g.request("hunger_rate", 2, 3, 5)
        self.assertEqual(g.save(), 0)
        self.assertTrue(list((g.game / "save").iterdir()))
        g.start()
        restored = [
            e
            for e in g.events()
            if e["event"] == "session" and e["detail"] == "restore"
        ]
        self.assertEqual(len(restored), 1)
        self.assertEqual(
            (
                restored[0]["spent"],
                restored[0]["reserved"],
                restored[0]["last_id"],
                restored[0]["safe"],
            ),
            (4, 4, 1, 2),
        )
        g.sanity(40)
        accepted = [
            e for e in g.events() if e["event"] == "ack" and e["status"] == "accepted"
        ]
        self.assertEqual([e["id"] for e in accepted], [1, 2])
        self.assertEqual(accepted[-1]["spent"], 7)
        g.wait_turns(12)
        self.assertEqual(g.quit(), 0)
        self.assertEqual(
            {e["detail"] for e in g.events() if e["event"] == "expiry"},
            {"ward_efficacy", "hunger_rate"},
        )
        self.assertEqual((g.events()[-1]["spent"], g.events()[-1]["reserved"]), (7, 0))

    def test_accepted_hunger_schedule_replays_in_real_game(self):
        first = self.game("replay-source", wizard=True)
        p = subprocess.run(
            [
                "python3",
                "-m",
                "chaos",
                "pack",
                "hunger",
                "--run-dir",
                str(first.run),
                "--at",
                "2",
                "--install-only",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(p.returncode, 0, p.stderr)
        first.start()
        first.sanity(60)
        first.wait_turns(7)
        self.assertEqual(first.quit(), 0)
        self.assertTrue(
            any(
                e["event"] == "ack"
                and e["status"] == "accepted"
                and e["mutation"] == "hunger_rate"
                for e in first.events()
            )
        )
        second = self.game("replay-target", wizard=True)
        p = subprocess.run(
            [
                "python3",
                "-m",
                "chaos",
                "replay",
                str(first.run / "whispers.jsonl"),
                "--accepted-events",
                str(first.run / "events.jsonl"),
                "--run-dir",
                str(second.run),
                "--max-runtime",
                ".1",
                "--poll",
                ".01",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(p.stdout)["submitted"], 1)
        second.start()
        second.sanity(60)
        second.wait_turns(7)
        self.assertEqual(second.quit(), 0)
        self.assertEqual(first.inputs, second.inputs)
        self.assertEqual(first.raw, second.raw)
        self.assertEqual(first.events(), second.events())
        self.assertEqual(
            (first.game / "xlogfile").read_bytes(),
            (second.game / "xlogfile").read_bytes(),
        )

    def test_incompatible_saves_rejected_both_directions(self):
        for name, source, target in [
            ("on-off", self.current, self.stock),
            ("off-on", self.stock, self.current),
        ]:
            with self.subTest(direction=name):
                g = self.game(name, source, wizard=True)
                g.start()
                self.assertEqual(g.save(), 0)
                for filename in ("dnethack", "nhdat"):
                    shutil.copy2(target / filename, g.game / filename)
                g.start()
                self.assertIn(b"Configuration incompatibility", g.raw)
                self.assertFalse(
                    any(
                        e["event"] == "session" and e["detail"] == "restore"
                        for e in g.events()
                    )
                )
                self.assertEqual(g.quit(), 0)
