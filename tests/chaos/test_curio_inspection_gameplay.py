"""Task 4b: injected native curio, real unchanged Game PTY in both UI modes.

Not natural discovery, admission, model authorship, or actualApply coverage.
"""

import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import unittest

from gameplay_support import ANSI, ROOT, Game
from native_rng import controlled_rng_objects

NAME = b"Terminal counter %s"
TEXT = b"Quiet %s %n. Three marks remain."
SOURCE = b"""return {name='Terminal counter %s',inspect=function(c)
if c.charges~=3 or c.state~=7 then error('context') end
return 'Quiet %s %n. Three marks remain.' end,
apply=function(c) error('Apply must not run') end}
"""


def assert_evidence(test, raw, before, after, receipt, mode):
    test.assertIn(NAME, raw)
    test.assertIn(TEXT, raw)
    test.assertNotIn(b"whistle", raw.lower())
    test.assertNotIn(b"encyclopedia", raw.lower())
    test.assertEqual(before, after, "ddoinv purity snapshot changed")
    test.assertEqual(receipt["return"], 0 if mode else receipt["move_instant"])
    test.assertEqual(receipt["encyclopedias"], 0)
    test.assertEqual(receipt["rng_count"], 0)
    test.assertEqual(receipt["rng_expected"], receipt["rng_actual"])


@unittest.skipUnless(
    os.environ.get("NYARLATHACK_GAME_TESTS") == "1", "real game opt-in"
)
class CurioInspectionGameplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert (ROOT / ".chaos-build").read_text().strip() == "1"
        cls.artifacts = Path(tempfile.mkdtemp(prefix="nyarl-curio-inspection-tty-"))
        print("CURIO_INSPECTION_TTY_ARTIFACTS=" + str(cls.artifacts), flush=True)
        cls.clock = cls.artifacts / "clock.so"
        commands = [
            [
                "cc",
                "-shared",
                "-fPIC",
                str(ROOT / "tests/chaos/replay_clock.c"),
                "-ldl",
                "-o",
                str(cls.clock),
            ],
            [
                "objcopy",
                "--redefine-sym",
                "main=original_game_main",
                str(ROOT / "sys/unix/unixmain.o"),
                str(cls.artifacts / "unixmain.o"),
            ],
        ]
        for command in commands:
            subprocess.run(command, check=True, timeout=30)
        objects = (
            sorted((ROOT / "src").glob("*.o"))
            + [
                ROOT / "sys/unix/unixres.o",
                ROOT / "sys/unix/unixunix.o",
                cls.artifacts / "unixmain.o",
                ROOT / "sys/share/ioctl.o",
                ROOT / "sys/share/unixtty.o",
            ]
            + sorted((ROOT / "win/tty").glob("*.o"))
            + sorted((ROOT / "win/curses").glob("*.o"))
        )
        objects = controlled_rng_objects(objects, cls.artifacts)
        cls.exe = cls.artifacts / "dnethack"
        protected = [
            *objects,
            ROOT / "src/rnd.o",
            ROOT / "sys/unix/unixmain.o",
            ROOT / "tests/chaos/gameplay_support.py",
            ROOT / "tests/chaos/native_rng.py",
            ROOT / "tests/chaos/native_rng.h",
        ]
        digests = {
            str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in protected
        }
        (cls.artifacts / "compiled-inputs.json").write_text(
            json.dumps(digests, indent=2)
        )
        for name in (
            "curio_inspection_gameplay.c",
            "test_curio_inspection_gameplay.py",
        ):
            shutil.copy2(ROOT / "tests/chaos" / name, cls.artifacts / name)
        command = [
            "cc",
            "-g",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-DCHAOS",
            "-isystem" + str(ROOT / "include"),
            str(ROOT / "tests/chaos/curio_inspection_gameplay.c"),
            *map(str, objects),
            *["-Wl,--wrap=" + s for s in ("chaos_start", "ddoinv", "checkfile")],
            "-lncursesw",
            "-ltinfo",
            "-lm",
            *subprocess.check_output(
                ["pkg-config", "--libs", "lua5.4"], text=True, timeout=10
            ).split(),
            "-o",
            str(cls.exe),
        ]
        commands.append(command)
        (cls.artifacts / "build-commands.json").write_text(
            json.dumps(commands, indent=2)
        )
        result = subprocess.run(command, capture_output=True, text=True, timeout=45)
        (cls.artifacts / "build.log").write_text(result.stdout + result.stderr)
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)
        assert digests == {
            str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in protected
        }, "link changed protected inputs"

    def test_rng_oracle_under_actual_preload(self):
        for mode, assertion in (
            ("--rng-negative-control", "reseed_count == 0"),
            ("--raw-rng-negative-control", "rn2(100000) == expected"),
        ):
            with self.subTest(mode=mode):
                p = subprocess.run(
                    [str(self.exe), mode],
                    capture_output=True,
                    env={**os.environ, "LD_PRELOAD": str(self.clock)},
                    timeout=10,
                )
                (self.artifacts / (mode[2:] + ".log")).write_bytes(p.stdout + p.stderr)
                self.assertEqual(p.returncode, -signal.SIGABRT)
                self.assertIn(assertion.encode(), p.stderr)

    def run_mode(self, mode):
        game = Game(
            ROOT / "dnethackdir",
            self.clock,
            wizard=True,
            root=self.artifacts / ("use-menu" if mode else "direct"),
        )
        self.addCleanup(game.close)
        shutil.copy2(self.exe, game.game / "dnethack")
        (game.game / "fixture-source.lua").write_bytes(SOURCE)
        (game.game / "fixture-mode.txt").write_text(str(mode))
        game.start()
        fixture = json.loads((game.game / "fixture.json").read_text())
        self.assertEqual(fixture["injected"], True)
        self.assertEqual(fixture["mode"], mode)
        letter = fixture["letter"].encode()
        self.assertEqual(len(letter), 1)
        start = len(game.raw)
        inventory = game.send("i")
        self.assertIn(NAME, inventory)
        self.assertIn(letter + b" - a " + NAME, inventory)
        selected = game.send(letter)
        if mode:
            self.assertIn(b"Do what with", selected)
            self.assertIn(b"I - Describe this item", selected)
            self.assertIn(b"a - Apply", selected)
            selected = game.send("I")
        self.assertIn(TEXT, selected)
        # Close only an observed blocking description window, never send Apply.
        receipt_path = game.game / "receipt.json"
        if not receipt_path.exists():
            self.assertTrue(b"(end)" in selected or b"--More--" in selected, selected)
            game.send(b"\x1b")
        self.assertTrue(receipt_path.exists(), "real ddoinv has not returned")
        raw = bytes(game.raw[start:])
        (game.root / "inspection.raw").write_bytes(raw)
        receipt = json.loads(receipt_path.read_text())
        before = (game.game / "before.bin").read_bytes()
        after = (game.game / "after.bin").read_bytes()
        assert_evidence(self, raw, before, after, receipt, mode)
        # Negative controls against the exact captured physical-terminal evidence.
        with self.assertRaises(AssertionError):
            assert_evidence(
                self,
                raw.replace(TEXT, b"WRONG INSPECTION"),
                before,
                after,
                receipt,
                mode,
            )
        with self.assertRaises(AssertionError):
            assert_evidence(self, raw, before, after + b"changed", receipt, mode)
        (game.root / "assertions.json").write_text(
            json.dumps(
                {
                    "mode": mode,
                    "fixture": "injected native WHISTLE, not discovery/admission",
                    "text_negative_control": "rejected",
                    "purity_negative_control": "rejected",
                    "inspection_text": TEXT.decode(),
                    "receipt": receipt,
                    "inspection_plain": ANSI.sub(b"", raw).decode(errors="replace"),
                },
                indent=2,
            )
        )
        self.assertEqual(game.quit(), 0)
        other = self.artifacts / ("direct" if mode else "use-menu")
        if (other / "assertions.json").exists():
            other_raw = (other / "inspection.raw").read_bytes()
            self.assertEqual(raw.count(TEXT), other_raw.count(TEXT))
            self.assertEqual(raw.count(TEXT), 1)
            other_receipt = json.loads((other / "game/receipt.json").read_text())
            for key in (
                "rng_count",
                "rng_expected",
                "rng_actual",
                "moves",
                "sanity",
                "insight",
            ):
                self.assertEqual(receipt[key], other_receipt[key], key)
            # Full outputs intentionally differ: only use-menu has action choices.
            self.assertEqual(b"Describe this item" in raw, bool(mode))
            self.assertEqual(b"Describe this item" in other_raw, not bool(mode))
            (self.artifacts / "mode-comparison.json").write_text(
                json.dumps(
                    {
                        "same_exact_inspect_bytes": True,
                        "same_rng_and_turn_receipts": True,
                        "direct_return": 2,
                        "use_menu_return": 0,
                        "distinct_real_action_menu": True,
                    },
                    indent=2,
                )
            )

    def test_direct_inventory_inspection(self):
        self.run_mode(0)

    def test_item_use_menu_inspection(self):
        self.run_mode(1)
