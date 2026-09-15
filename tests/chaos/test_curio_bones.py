"""Native object streams, not a full savebones/getbones gameplay encounter."""

import hashlib
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
class CurioBonesTests(unittest.TestCase):
    def test_native_bones(self):
        artifacts = Path(
            os.environ.get("CURIO_BONES_ARTIFACTS")
            or tempfile.mkdtemp(prefix="nyarl-curio-bones-")
        )
        artifacts.mkdir(parents=True, exist_ok=True)
        objects = (
            sorted((ROOT / "src").glob("*.o"))
            + [
                ROOT / "sys/unix/unixres.o",
                ROOT / "sys/unix/unixunix.o",
                ROOT / "sys/unix/unixmain.o",
                ROOT / "sys/share/ioctl.o",
                ROOT / "sys/share/unixtty.o",
            ]
            + sorted((ROOT / "win/tty").glob("*.o"))
            + sorted((ROOT / "win/curses").glob("*.o"))
        )
        objects = controlled_rng_objects(objects, artifacts)
        for relative, options in (
            ("sys/unix/unixmain.o", ["--redefine-sym=main=original_game_main"]),
            ("src/invent.o", ["--globalize-symbol=nextgetobj"]),
            ("src/bones.o", ["--globalize-symbol=resetobjs"]),
            ("src/save.o", ["--globalize-symbol=saveobjchn"]),
            (
                "src/restore.o",
                [
                    "--globalize-symbol=restobjchn",
                    "--globalize-symbol=clear_id_mapping",
                ],
            ),
        ):
            original = ROOT / relative
            digest = hashlib.sha256(original.read_bytes()).digest()
            exposed = artifacts / original.name
            subprocess.run(
                ["objcopy", *options, str(original), str(exposed)], check=True
            )
            self.assertEqual(hashlib.sha256(original.read_bytes()).digest(), digest)
            objects = [exposed if obj == original else obj for obj in objects]
        exe = artifacts / "curio-bones"
        command = [
            "cc",
            "-g",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-DCHAOS",
            "-isystem",
            str(ROOT / "include"),
            str(ROOT / "tests/chaos/curio_bones.c"),
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
            self, exe, artifacts, naming_cases=("output", "input", "nested")
        )
