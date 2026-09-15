"""Task 5b: linked native merging and complete Andromalius ritual."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from gameplay_support import ROOT
from native_rng import controlled_rng_objects, verify_native_fixture


@unittest.skipUnless(
    os.environ.get("NYARLATHACK_GAME_TESTS") == "1", "real game opt-in"
)
class CurioCarrierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert (ROOT / ".chaos-build").read_text().strip() == "1"
        cls.artifacts = Path(
            os.environ.get("CURIO_CARRIER_ARTIFACTS")
            or tempfile.mkdtemp(prefix="curio5b-carrier-")
        )
        cls.artifacts.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                "objcopy",
                "--redefine-sym",
                "main=original_game_main",
                str(ROOT / "sys/unix/unixmain.o"),
                str(cls.artifacts / "unixmain.o"),
            ],
            check=True,
        )
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
        cls.exe = cls.artifacts / "curio-carrier"
        command = [
            "cc",
            "-g",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-DCHAOS",
            "-isystem",
            str(ROOT / "include"),
            str(ROOT / "tests/chaos/curio_carrier.c"),
            *map(str, objects),
            "-lncursesw",
            "-ltinfo",
            "-lm",
            *subprocess.check_output(
                ["pkg-config", "--libs", "lua5.4"], text=True
            ).split(),
            "-o",
            str(cls.exe),
        ]
        (cls.artifacts / "build-command.json").write_text(json.dumps(command, indent=2))
        result = subprocess.run(command, capture_output=True, text=True, timeout=45)
        (cls.artifacts / "build.log").write_text(result.stdout + result.stderr)
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)

    def test_merging(self):
        verify_native_fixture(self, self.exe, self.artifacts)

    def test_ritual(self):
        cases = [(0, 0, order, 0) for order in (0, 1)]
        cases += [
            (tag, variant, order, noise)
            for tag in (1, 2, 255)
            for variant in range(7)
            for order in (0, 1)
            for noise in (0, 1, 2)
        ]
        for case in cases:
            with self.subTest(case=case):
                result = subprocess.run(
                    [str(self.exe), "ritual", *map(str, case)],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                (
                    self.artifacts / ("ritual-" + "-".join(map(str, case)) + ".log")
                ).write_text(result.stdout + result.stderr)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
