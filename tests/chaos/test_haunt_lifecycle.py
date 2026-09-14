"""Real linked lifecycle: transport admission and ongoing rules are distinct."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(
    os.environ.get("NYARLATHACK_GAME_TESTS") == "1", "real game opt-in"
)
class HauntLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="nyarl-haunt-lifecycle-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name)
        subprocess.run(
            [
                "objcopy",
                "--redefine-sym",
                "main=original_game_main",
                str(ROOT / "sys/unix/unixmain.o"),
                str(cls.root / "unixmain.o"),
            ],
            check=True,
        )
        objects = (
            sorted((ROOT / "src").glob("*.o"))
            + [
                ROOT / "sys/unix/unixres.o",
                ROOT / "sys/unix/unixunix.o",
                cls.root / "unixmain.o",
                ROOT / "sys/share/ioctl.o",
                ROOT / "sys/share/unixtty.o",
            ]
            + sorted((ROOT / "win/tty").glob("*.o"))
            + sorted((ROOT / "win/curses").glob("*.o"))
        )
        cls.exe = cls.root / "lifecycle"
        subprocess.run(
            [
                "cc",
                "-g",
                "-DCHAOS",
                "-I" + str(ROOT / "include"),
                str(ROOT / "tests/chaos/haunt_lifecycle.c"),
                *map(str, objects),
                "-lncursesw",
                "-ltinfo",
                "-lm",
                *subprocess.check_output(
                    ["pkg-config", "--libs", "lua5.4"], text=True
                ).split(),
                "-o",
                str(cls.exe),
            ],
            check=True,
            timeout=45,
        )

    def check(self, failed_log):
        env = dict(os.environ)
        env.pop("NYARLATHACK_RUN_DIR", None)
        args = [str(self.exe)]
        if failed_log:
            run = self.root / "run"
            run.mkdir(mode=0o700)
            env["NYARLATHACK_RUN_DIR"] = str(run)
            args.append(str(run / "events.jsonl"))
        result = subprocess.run(
            args, env=env, capture_output=True, text=True, timeout=10
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(
            "history maintained; level expiry permanent; deadline maintained",
            result.stdout,
        )

    def test_absent_run_directory_keeps_lifecycle(self):
        self.check(False)

    def test_failed_event_log_keeps_lifecycle(self):
        self.check(True)
