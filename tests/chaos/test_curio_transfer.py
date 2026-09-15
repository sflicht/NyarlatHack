"""Linked native transfer handlers, not terminal or monster-AI scheduling."""

import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import unittest

from gameplay_support import ROOT
from native_rng import controlled_rng_objects


@unittest.skipUnless(
    os.environ.get("NYARLATHACK_GAME_TESTS") == "1", "real game opt-in"
)
class CurioTransferTests(unittest.TestCase):
    def test_native_physical_lifecycle(self):
        artifacts = Path(tempfile.mkdtemp(prefix="curio6f-native-"))
        print("CURIO_TRANSFER_ARTIFACTS=" + str(artifacts), flush=True)
        originals = (
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
        protected = originals + [ROOT / "dnethackdir/dnethack"]
        before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
        (artifacts / "input-digests.json").write_text(json.dumps(before, indent=2))
        objects = controlled_rng_objects(originals, artifacts)
        for original, options in (
            (ROOT / "sys/unix/unixmain.o", ["--redefine-sym=main=original_game_main"]),
            (ROOT / "src/invent.o", ["--globalize-symbol=nextgetobj"]),
            (
                ROOT / "src/pickup.o",
                [
                    "--globalize-symbol=in_container",
                    "--globalize-symbol=out_container",
                    "--globalize-symbol=current_container",
                ],
            ),
        ):
            exposed = artifacts / original.name
            subprocess.run(
                ["objcopy", *options, str(original), str(exposed)], check=True
            )
            objects = [exposed if p == original else p for p in objects]
        exe = artifacts / "curio-transfer"
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
            str(ROOT / "tests/chaos/curio_transfer.c"),
            *map(str, objects),
            "-Wl,--wrap=mksobj",
            "-Wl,--wrap=getdir",
            "-Wl,--wrap=freeinv",
            "-Wl,--wrap=place_object",
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
        try:
            subprocess.run(command, check=True, timeout=45)
            receipts = []
            controls = {
                "--rng-negative-control": "reseed_count == 0",
                "--raw-rng-negative-control": "rn2(100000) == expected",
                "--record-negative-control": "memcmp",
                "--chain-negative-control": "count == 1",
            }
            cases = list(controls) + [
                f"{flow}:{variant}"
                for flow in (
                    "containers",
                    "receive",
                    "steal",
                    "throw",
                    "carry",
                    "delobj",
                    "useup",
                    "obfree",
                )
                for variant in ("active", "disabled", "depleted", "ordinary")
            ]
            for case in cases:
                with self.subTest(case=case):
                    result = subprocess.run(
                        [str(exe), case],
                        cwd=artifacts,
                        capture_output=True,
                        text=True,
                        timeout=20,
                    )
                    (artifacts / (case.replace(":", "-") + ".txt")).write_text(
                        result.stdout + result.stderr
                    )
                    receipts.append({"case": case, "returncode": result.returncode})
                    if case in controls:
                        self.assertEqual(
                            result.returncode, -signal.SIGABRT, result.stderr
                        )
                        self.assertIn(controls[case], result.stderr)
                    else:
                        self.assertEqual(
                            result.returncode, 0, result.stdout + result.stderr
                        )
                        self.assertIn("PASS " + case, result.stdout)
            (artifacts / "receipts.json").write_text(json.dumps(receipts, indent=2))
            self.assertEqual(len(receipts), len(cases))
        finally:
            after = {
                str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in protected
            }
            (artifacts / "after-digests.json").write_text(json.dumps(after, indent=2))
            self.assertEqual(before, after, "native inputs changed")
