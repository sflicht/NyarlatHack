"""Task 6e: injected original; real drop, levelport, save/restart and pickup.

Handwritten fixture, not admission, natural placement or model authorship.
No claim of movement RNG purity. All command handlers and Game are unmodified.
"""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from gameplay_support import ANSI, Game, ROOT


def assert_preserved(test, baseline, actual, original_id, receipt, seed_count):
    test.assertEqual(actual, baseline, "exact owned record changed")
    test.assertEqual(receipt["owner"], original_id, "original identity changed")
    test.assertEqual(seed_count, "seed\n", "fixture reseeded on restore")


def assert_manual_pickup(test, original_id, before, after, result, output):
    test.assertEqual(
        before["where"], "floor", "comma requires floor owner before entry"
    )
    test.assertEqual(before["autopickup"], 0)
    test.assertEqual(before["floor_chain"], 1)
    test.assertEqual(before["player_floor_chain"], 1)
    test.assertEqual(before["in_inventory"], 0)
    test.assertEqual((before["ux"], before["uy"]), (before["ox"], before["oy"]))
    for receipt in (before, after):
        test.assertEqual(receipt["owner"], original_id)
        test.assertEqual(receipt["object_id"], original_id)
        test.assertEqual(receipt["loaded"], 1)
        test.assertEqual(receipt["tag"], 1)
    test.assertEqual(after["where"], "inventory")
    test.assertEqual(after["in_inventory"], 1)
    test.assertEqual(after["floor_chain"], 0)
    test.assertEqual(after["player_floor_chain"], 0)
    test.assertEqual(result["result"], result["move_standard"])
    test.assertNotIn(b"nothing here to pick up", output.lower())
    test.assertIn(after["letter"].encode() + b" - a Transfer counter.", output)


@unittest.skipUnless(
    os.environ.get("NYARLATHACK_GAME_TESTS") == "1", "real game opt-in"
)
class CurioTransferGameplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.artifacts = Path(tempfile.mkdtemp(prefix="nyarl-curio-transfer-"))
        print("CURIO_TRANSFER_ARTIFACTS=" + str(cls.artifacts), flush=True)
        assert (ROOT / ".chaos-build").read_text().strip() == "1"
        objects = (
            sorted((ROOT / "src").glob("*.o"))
            + [ROOT / "sys/unix" / n for n in ("unixres.o", "unixunix.o", "unixmain.o")]
            + [ROOT / "sys/share" / n for n in ("ioctl.o", "unixtty.o")]
            + sorted((ROOT / "win/tty").glob("*.o"))
            + sorted((ROOT / "win/curses").glob("*.o"))
        )
        cls.protected = (
            objects
            + list((ROOT / "src").glob("*.c"))
            + list((ROOT / "include").glob("*.h"))
            + [p.with_suffix(".c") for p in objects if p.with_suffix(".c").exists()]
            + [ROOT / "dnethackdir" / n for n in ("dnethack", "nhdat", "license")]
            + [ROOT / ".chaos-build"]
            + [
                ROOT / "tests/chaos" / n
                for n in (
                    "gameplay_support.py",
                    "native_rng.py",
                    "native_rng.h",
                    "replay_clock.c",
                    "curio_transfer_gameplay.c",
                    "test_curio_transfer_gameplay.py",
                )
            ]
        )
        cls.before = cls.hashes()
        (cls.artifacts / "protected-before.json").write_text(
            json.dumps(cls.before, indent=2)
        )
        cls.clock = cls.artifacts / "clock.so"
        cls.exe = cls.artifacts / "dnethack"
        commands = [
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
            [
                "cc",
                "-g",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-DCHAOS",
                "-isystem" + str(ROOT / "include"),
                str(ROOT / "tests/chaos/curio_transfer_gameplay.c"),
                *map(str, objects),
                *[
                    "-Wl,--wrap=" + s
                    for s in (
                        "chaos_start",
                        "doapply",
                        "dodrop",
                        "deferred_goto",
                        "dorecover",
                        "dosave",
                        "ddoinv",
                        "dopickup",
                        "dotogglepickup",
                    )
                ],
                "-lncursesw",
                "-ltinfo",
                "-lm",
                *subprocess.check_output(
                    ["pkg-config", "--libs", "lua5.4"], text=True, timeout=10
                ).split(),
                "-o",
                str(cls.exe),
            ],
        ]
        (cls.artifacts / "build-commands.json").write_text(
            json.dumps(commands, indent=2)
        )
        for command in commands:
            p = subprocess.run(command, capture_output=True, text=True, timeout=45)
            with (cls.artifacts / "build.log").open("a") as f:
                f.write(p.stdout + p.stderr)
            if p.returncode:
                raise AssertionError(p.stdout + p.stderr)
        for name in ("curio_transfer_gameplay.c", "test_curio_transfer_gameplay.py"):
            shutil.copy2(ROOT / "tests/chaos" / name, cls.artifacts / name)

    @classmethod
    def hashes(cls):
        return {
            str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.protected
        }

    @classmethod
    def tearDownClass(cls):
        after = cls.hashes()
        (cls.artifacts / "protected-after.json").write_text(json.dumps(after, indent=2))
        assert cls.before == after, "protected engine/driver inputs changed"

    def test_original_unloaded_save_return(self):
        g = Game(
            ROOT / "dnethackdir",
            self.clock,
            wizard=True,
            root=self.artifacts / "unloaded-owner",
        )
        self.addCleanup(g.close)
        shutil.copy2(self.exe, g.game / "dnethack")

        def receipt(name):
            return json.loads((g.game / (name + ".json")).read_text())

        def record(name):
            return (g.game / (name + ".bin")).read_bytes()

        def command_response(name, command):
            start = len(g.raw)
            g.more(g.send(command))
            output = ANSI.sub(b"", bytes(g.raw[start:]))
            (self.artifacts / (name + ".response.bin")).write_bytes(output)
            return output

        def levelport(level):
            text = g.send("#levelport\n")
            self.assertIn(b"To what level", text)
            g.more(g.send(str(level) + "\n"))

        g.start()
        seeded = receipt("seeded")
        letter = seeded["letter"]
        self.assertEqual(seeded["charges"], 3)
        self.assertIn(b"apply", g.send("a").lower())
        g.more(g.send(letter))
        used = receipt("applied-first")
        self.assertEqual((used["charges"], used["state"]), (2, 8))
        baseline = record("applied-first")
        g.send("d")
        g.more(g.send(letter))
        dropped = receipt("dropped")
        self.assertEqual(dropped["where"], "floor")
        self.assertEqual(record("dropped"), baseline)
        levelport(2)
        self.assertEqual(receipt("away")["loaded"], 0)
        self.assertEqual(record("away"), baseline)
        level_files = [
            p for p in g.game.iterdir() if p.is_file() and p.name.endswith(".1")
        ]
        self.assertTrue(level_files, "native unloaded level file missing")
        evidence = self.artifacts / "serialized"
        evidence.mkdir()
        for p in level_files:
            shutil.copy2(p, evidence / p.name)
        self.assertEqual(g.save(), 0)
        self.assertEqual(record("save-entry"), baseline)
        saves = list((g.game / "save").iterdir())
        self.assertTrue(saves)
        for p in saves:
            shutil.copy2(p, evidence / p.name)
        g.start()
        self.assertEqual(receipt("restored")["loaded"], 0)
        self.assertEqual(record("restored"), baseline)
        self.assertEqual(record("restored-start"), baseline)
        self.assertEqual((g.game / "seed-count.txt").read_text(), "seed\n")
        self.assertTrue(
            any(
                e["event"] == "session" and e["detail"] == "restore" for e in g.events()
            )
        )
        levelport(1)
        returned = receipt("returned")
        self.assertEqual(returned["owner"], seeded["owner"])
        self.assertEqual(returned["tag"], 1)
        self.assertEqual(returned["where"], "floor")
        self.assertEqual(record("returned"), baseline)
        seed_count = (g.game / "seed-count.txt").read_text()
        assert_preserved(
            self, baseline, record("returned"), seeded["owner"], returned, seed_count
        )
        # Native @ binding toggles the actual pickup option. Do not set engine
        # flags in the fixture: teleds otherwise auto-picks before comma arrives.
        if returned["autopickup"]:
            toggle_output = command_response("autopickup", "@")
            self.assertIn(b"Autopickup: OFF.", toggle_output)
            self.assertEqual(receipt("autopickup-before")["autopickup"], 1)
            self.assertEqual(receipt("autopickup-after")["autopickup"], 0)
            for name in ("autopickup-before", "autopickup-after"):
                assert_preserved(
                    self,
                    baseline,
                    record(name),
                    seeded["owner"],
                    receipt(name),
                    seed_count,
                )
                self.assertEqual(receipt(name)["floor_chain"], 1)
                self.assertEqual(receipt(name)["in_inventory"], 0)
        else:
            self.assertEqual(returned["autopickup"], 0)
        # Real wizard controlled teleport cursor, then real comma pickup command.
        text = g.send(b"\x14")
        self.assertIn(b"position", text)
        g.more(text)
        dx, dy = returned["ox"] - returned["ux"], returned["oy"] - returned["uy"]
        cursor = (
            ("l" if dx > 0 else "h") * abs(dx)
            + ("j" if dy > 0 else "k") * abs(dy)
            + "."
        )
        teleport_output = command_response("teleport", cursor)
        pickup_output = command_response("manual-1", ",")
        pickup_before, pickup_after = (
            receipt("manual-1-before"),
            receipt("manual-1-after"),
        )
        pickup_result = receipt("manual-1-result")
        for name in ("manual-1-before", "manual-1-after"):
            assert_preserved(
                self, baseline, record(name), seeded["owner"], receipt(name), seed_count
            )
        assert_manual_pickup(
            self,
            seeded["owner"],
            pickup_before,
            pickup_after,
            pickup_result,
            pickup_output,
        )
        self.assertNotIn(b" - a Transfer counter.", teleport_output)
        # Actual repeated comma is a native no-op, rejected by the SAME positive
        # oracle. This is not an invented engine persistence failure.
        noop_output = command_response("manual-2", ",")
        noop_before, noop_after = receipt("manual-2-before"), receipt("manual-2-after")
        noop_result = receipt("manual-2-result")
        self.assertIn(b"There is nothing here to pick up.", noop_output)
        self.assertEqual(noop_result["result"], noop_result["move_cancelled"])
        for name in ("manual-2-before", "manual-2-after"):
            assert_preserved(
                self, baseline, record(name), seeded["owner"], receipt(name), seed_count
            )
            self.assertEqual(receipt(name)["where"], "inventory")
            self.assertEqual(receipt(name)["in_inventory"], 1)
            self.assertEqual(receipt(name)["floor_chain"], 0)
        with self.assertRaisesRegex(AssertionError, "comma requires floor owner"):
            assert_manual_pickup(
                self, seeded["owner"], noop_before, noop_after, noop_result, noop_output
            )
        text = g.send("i")
        self.assertIn(b"Transfer counter", text)
        # Inspect using actual assigned inventory letter, not the pre-drop letter.
        held = receipt("inventory")
        self.assertEqual(held["where"], "inventory")
        self.assertEqual(held["owner"], seeded["owner"])
        self.assertEqual(record("inventory"), baseline)
        text = g.send(held["letter"])
        if b"Do what with" in text:
            self.assertIn(b"I - Describe this item", text)
            text = g.send("I")
        self.assertIn(b"Two uses remain; state eight.", text)
        if b"(end)" in text or b"--More--" in text:
            g.send(b"\x1b")
        g.send("a")
        g.more(g.send(held["letter"]))
        final = receipt("applied-final")
        self.assertEqual((final["charges"], final["state"]), (1, 9))
        self.assertEqual(final["owner"], seeded["owner"])
        self.assertEqual(g.quit(), 0)
        self.assertTrue((g.game / "xlogfile").read_text().strip())
        self.assertFalse((g.run / "whisper.json").exists())
        self.assertEqual(
            [e["detail"] for e in g.events() if e["event"] == "session"],
            ["new", "restore"],
        )
        self.assertTrue(
            all(
                e["spent"] == 0 and e["reserved"] == 0 and e["last_id"] == 0
                for e in g.events()
            )
        )
        self.assertEqual(
            sum(
                e["event"] == "curio"
                and e.get("detail") == "applied requested=0 actual=0"
                for e in g.events()
            ),
            2,
        )
        # Negative controls for the exact identity, bytes, and no-reseed oracles.
        for actual, changed_receipt, count in (
            (baseline, {**returned, "owner": returned["owner"] + 1}, seed_count),
            (baseline + b"changed", returned, seed_count),
            (baseline, returned, "seed\nseed\n"),
        ):
            with self.assertRaises(AssertionError):
                assert_preserved(
                    self, baseline, actual, seeded["owner"], changed_receipt, count
                )
        (self.artifacts / "assertions.json").write_text(
            json.dumps(
                {
                    "unloaded_save_restore_return": True,
                    "native_drop_pickup": True,
                    "native_explicit_comma_pickup": True,
                    "negative_controls": [
                        "owner",
                        "record",
                        "reseed",
                        "native_comma_noop",
                    ],
                    "seeded": seeded,
                    "returned": returned,
                    "manual_before": pickup_before,
                    "manual_after": pickup_after,
                    "manual_result": pickup_result,
                    "noop_before": noop_before,
                    "noop_after": noop_after,
                    "noop_result": noop_result,
                    "final": final,
                },
                indent=2,
            )
        )
