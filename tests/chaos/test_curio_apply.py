"""Task 5a: guarded Apply through actual native command and Sanity paths."""

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
class CurioApplyTests(unittest.TestCase):
    def test_linked_apply(self):
        artifacts = Path(
            os.environ.get("CURIO_APPLY_ARTIFACTS")
            or tempfile.mkdtemp(prefix="nyarl-curio-apply-")
        )
        artifacts.mkdir(parents=True, exist_ok=True)
        print("CURIO_APPLY_ARTIFACTS=" + str(artifacts), flush=True)
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
        exe = artifacts / "curio-apply"
        command = [
            "cc",
            "-g",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-DCHAOS",
            "-isystem",
            str(ROOT / "include"),
            str(ROOT / "tests/chaos/curio_apply.c"),
            *map(str, objects),
            "-Wl,--wrap=change_usanity",
            "-Wl,--wrap=chaos_event",
            "-Wl,--wrap=write",
            "-Wl,--wrap=chaos_lua_curio_apply",
            "-Wl,--wrap=touch_artifact",
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
        verify_native_fixture(self, exe, artifacts)
        for mode in ("receipt-failure", "receipts"):
            with tempfile.TemporaryDirectory(prefix="curio5a-receipts-") as run:
                result = subprocess.run(
                    [str(exe), "--" + mode],
                    env={**os.environ, "NYARLATHACK_RUN_DIR": run},
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                (artifacts / (mode + ".txt")).write_text(result.stdout + result.stderr)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                events = (Path(run) / "events.jsonl").read_text()
                (artifacts / (mode + ".jsonl")).write_text(events)
                records = [json.loads(line) for line in events.splitlines()]
                details = [row["detail"] for row in records if row["event"] == "curio"]
                self.assertEqual(
                    details,
                    []
                    if mode == "receipt-failure"
                    else ["applied requested=-2 actual=-2"] * 3,
                )
