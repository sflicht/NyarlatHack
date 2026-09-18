"""Opt-in tests of actual linked C physics and terminal game processes.
Run after make install CHAOS=1 with NYARLATHACK_GAME_TESTS=1.
"""

import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from gameplay_support import ANSI, Game, ROOT
from native_rng import controlled_rng_objects


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
        objects = controlled_rng_objects(objects, b)
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
                *subprocess.check_output(
                    ["pkg-config", "--libs", "lua5.4"], text=True
                ).split(),
                "-o",
                str(b / "rules"),
            ],
            check=True,
            timeout=45,
        )
        outputs = []
        for name, args in (("control", []), ("ambient-prefix", ["--ambient-prefix"])):
            command = [str(b / "rules"), *args]
            (b / (name + "-command.json")).write_text(json.dumps(command))
            p = subprocess.run(command, capture_output=True, text=True, timeout=15)
            (b / (name + "-result.txt")).write_text(p.stdout + p.stderr)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            self.assertEqual(p.stderr, "")
            self.assertIn(
                "real gethungry: normal=1, admitted hunger=2, expired=1", p.stdout
            )
            self.assertIn(
                "real onscary: protected=1, admitted ward=0, expired=1; engraving retained",
                p.stdout,
            )
            self.assertIn("seed=123 moves=10,15,20,25", p.stdout)
            outputs.append(p.stdout)
        self.assertEqual(outputs[0], outputs[1])

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
        g.request("ambient", 1, 1)
        g.start()
        cosmetic = g.events()[-1]["cosmetic"]
        self.assertEqual(cosmetic["seen"], 1)
        g.request("ward_efficacy", 2, 2, 10)
        g.sanity(60)
        accepted = [
            e for e in g.events() if e["event"] == "ack" and e["status"] == "accepted"
        ]
        self.assertEqual([e["id"] for e in accepted], [1, 2])
        self.assertEqual(accepted[0]["cost"], 0)
        self.assertEqual(accepted[0]["cosmetic_cost"], 1)
        g.request("hunger_rate", 3, 3, 5)
        pending = (g.run / "whisper.json").read_bytes()
        self.assertEqual(g.save(), 0)
        self.assertTrue(list((g.game / "save").iterdir()))
        g.start()
        restored = [
            e
            for e in g.events()
            if e["event"] == "session" and e["detail"] == "restore"
        ]
        self.assertEqual(len(restored), 1)
        self.assertEqual(restored[0]["v"], 3)
        self.assertEqual(restored[0]["cosmetic"], cosmetic)
        self.assertEqual((g.run / "whisper.json").read_bytes(), pending)
        self.assertEqual(
            (
                restored[0]["spent"],
                restored[0]["reserved"],
                restored[0]["last_id"],
                restored[0]["safe"],
            ),
            (4, 4, 2, 2),
        )
        g.sanity(40)
        accepted = [
            e for e in g.events() if e["event"] == "ack" and e["status"] == "accepted"
        ]
        self.assertEqual([e["id"] for e in accepted], [1, 2, 3])
        self.assertEqual(accepted[-1]["cosmetic"], cosmetic)
        self.assertEqual(accepted[-1]["spent"], 7)
        g.wait_turns(12)
        self.assertEqual(g.quit(), 0)
        self.assertEqual(
            {e["detail"] for e in g.events() if e["event"] == "expiry"},
            {"ward_efficacy", "hunger_rate"},
        )
        self.assertEqual((g.events()[-1]["spent"], g.events()[-1]["reserved"]), (7, 0))

    def test_cosmetic_restore_remaining_interval_and_depletion(self):
        """Declared wizard fixture, not ordinary gameplay; no driver-pin edits.

        Existing replay_clock seeds/clock, idle route to native turns 21,50,51,
        101,151 only. Sanity commands alternate 60/40 as existing safe hooks.
        Fresh production State/backend objects simulate lost client history;
        hand requests deliberately test native bounds regardless of preference.
        """
        from chaos.director import State, RandomBackend

        g = self.game("cosmetic-restore", wizard=True)
        g.request("ambient", 1, 1)
        g.start()
        first = next(
            e for e in g.events() if e["event"] == "ack" and e["status"] == "accepted"
        )
        self.assertEqual(
            (first["turn"], first["cosmetic"]), (1, {"seen": 1, "last_turn": 1})
        )

        def turn():
            text = g.more(g.send(b"\x12"))
            values = re.findall(rb"T:(\d+)", text)
            self.assertTrue(values, text)
            return int(values[-1])

        def advance(target):
            remaining = target - turn()
            self.assertGreaterEqual(remaining, 0)
            self.assertLessEqual(remaining, 50)
            g.wait_turns(remaining)
            self.assertEqual(turn(), target)

        def restore(expected):
            self.assertEqual(g.save(), 0)
            g.start()
            row = [e for e in g.events() if e["event"] == "session"][-1]
            self.assertEqual(row["detail"], "restore")
            self.assertEqual(row["cosmetic"], expected)
            # New client/backend cannot replenish the engine-owned snapshot.
            fresh = State()
            fresh.ingest(row)
            for seed in (0, 7):
                candidate = RandomBackend(seed, True).choose(
                    fresh, row["last_id"] + 1, row["safe"] + 1
                )
                if candidate and candidate["mutation"] == "ambient":
                    self.assertFalse(expected["seen"] & (1 << (candidate["value"] - 1)))
            return row

        def attempt(value, sanity, reason, expected):
            before = g.events()[-1]
            request = dict(
                v=1,
                id=before["last_id"] + 1,
                mutation="ambient",
                value=value,
                duration=0,
                telegraph=1,
                at=before["safe"] + 1,
            )
            path = g.run / "whisper.tmp"
            path.write_text(json.dumps(request))
            path.chmod(0o600)
            path.replace(g.run / "whisper.json")
            boundary = turn()
            g.sanity(sanity)
            ack = [e for e in g.events() if e["event"] == "ack"][-1]
            self.assertEqual(
                (ack["id"], ack["at"], ack["turn"]),
                (request["id"], request["at"], boundary),
            )
            self.assertEqual(ack["detail"], reason)
            self.assertEqual(
                ack["status"], "accepted" if reason == "ok" else "rejected"
            )
            self.assertEqual(ack["cosmetic"], expected)
            self.assertEqual(
                (ack["spent"], ack["reserved"], ack["cost"], ack["cosmetic_cost"]),
                (0, 0, 0, 1),
            )

        advance(21)
        restore({"seen": 1, "last_turn": 1})
        attempt(2, 60, "cosmetic_cooldown", {"seen": 1, "last_turn": 1})
        attempt(1, 40, "cosmetic_repeat", {"seen": 1, "last_turn": 1})
        advance(50)
        attempt(2, 60, "cosmetic_cooldown", {"seen": 1, "last_turn": 1})
        advance(51)
        attempt(2, 40, "ok", {"seen": 3, "last_turn": 51})
        restore({"seen": 3, "last_turn": 51})
        attempt(3, 60, "cosmetic_cooldown", {"seen": 3, "last_turn": 51})
        advance(101)
        attempt(3, 40, "ok", {"seen": 7, "last_turn": 101})
        restore({"seen": 7, "last_turn": 101})
        advance(151)
        attempt(1, 60, "cosmetic_budget", {"seen": 7, "last_turn": 101})
        self.assertEqual(g.quit(), 0)

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

    def test_ordinary_bard_reaches_dungeon_without_wizard_mode(self):
        g = Game(
            self.current,
            self.clock,
            observe=True,
            wizard=False,
            ordinary=True,
            root=self.artifacts / "ordinary-bard",
        )
        self.addCleanup(g.close)
        text = g.start()
        visible = ANSI.sub(b"", text)
        self.assertTrue(g.sessions[-1]["ordinary"])
        self.assertFalse(g.sessions[-1]["wizard"])
        self.assertTrue(
            b"Exp:" in visible or b"AC:" in visible or b"Dlvl" in visible,
            visible,
        )
        self.assertEqual(g.quit(), 0)

    def test_next_use_lua_is_consumed_not_admitted(self):
        g = self.game("next-use-candidate", wizard=True)
        source = (
            b"return {\n"
            b"  on_action = function(context)\n"
            b'    return {next_use_intent_v=2, op="quiet", state=0}\n'
            b"  end\n"
            b"}\n"
        )
        path = g.run / "next_use.lua"
        path.write_bytes(source)
        path.chmod(0o600)
        g.start()
        g.wait_turns(2)
        self.assertEqual((g.run / "next_use-used.lua").read_bytes(), source)
        self.assertEqual(g.quit(), 0)
