"""Actual native object copy/split lifecycle and ordinary controls."""

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
class CurioCopyTests(unittest.TestCase):
    def test_native_copy_split(self):
        artifacts = Path(
            os.environ.get("CURIO_COPY_ARTIFACTS")
            or tempfile.mkdtemp(prefix="nyarl-curio-copy-")
        )
        artifacts.mkdir(parents=True, exist_ok=True)
        print("CURIO_COPY_ARTIFACTS=" + str(artifacts), flush=True)
        subprocess.run(
            [
                "objcopy",
                "--redefine-sym",
                "main=original_game_main",
                str(ROOT / "sys/unix/unixmain.o"),
                str(artifacts / "unixmain.o"),
            ],
            check=True,
        )
        objects = (
            sorted((ROOT / "src").glob("*.o"))
            + [
                ROOT / "sys/unix/unixres.o",
                ROOT / "sys/unix/unixunix.o",
                artifacts / "unixmain.o",
                ROOT / "sys/share/ioctl.o",
                ROOT / "sys/share/unixtty.o",
            ]
            + sorted((ROOT / "win/tty").glob("*.o"))
            + sorted((ROOT / "win/curses").glob("*.o"))
        )
        objects = controlled_rng_objects(objects, artifacts)
        original = ROOT / "src/invent.o"
        exposed = artifacts / "invent.o"
        subprocess.run(
            ["objcopy", "--globalize-symbol=nextgetobj", str(original), str(exposed)],
            check=True,
        )
        objects = [exposed if obj == original else obj for obj in objects]
        exe = artifacts / "curio-copy"
        command = [
            "cc",
            "-g",
            "-rdynamic",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-DCHAOS",
            "-isystem",
            str(ROOT / "include"),
            str(ROOT / "tests/chaos/curio_copy.c"),
            *map(str, objects),
            "-lncursesw",
            "-ltinfo",
            "-lm",
            *subprocess.check_output(
                ["pkg-config", "--libs", "lua5.4"], text=True
            ).split(),
            "-o",
            str(exe),
        ]
        (artifacts / "build-command.txt").write_text(repr(command))
        subprocess.run(command, check=True, timeout=45)
        verify_native_fixture(
            self, exe, artifacts, naming_cases=("split", "nested", "ordinary")
        )
