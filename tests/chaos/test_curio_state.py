"""Task 2 only: native saved record and explicit format rejection, no hooks."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from gameplay_support import Game, ROOT


@unittest.skipUnless(
    os.environ.get("NYARLATHACK_GAME_TESTS") == "1", "real game opt-in"
)
class CurioStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert (ROOT / ".chaos-build").read_text().strip() == "1"
        cls.artifacts = Path(tempfile.mkdtemp(prefix="nyarl-curio-state-"))
        print("CURIO_STATE_ARTIFACTS=" + str(cls.artifacts), flush=True)
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
        cls.exe = cls.artifacts / "curio-state"
        subprocess.run(
            [
                "cc",
                "-g",
                "-DCHAOS",
                "-I" + str(ROOT / "include"),
                str(ROOT / "tests/chaos/curio_state.c"),
                *map(str, objects),
                "-Wl,--wrap=dosave",
                "-Wl,--wrap=dorecover",
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
        cls.clock = cls.artifacts / "testclock.so"
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
        )

    def game(self, name, source):
        game = Game(source, self.clock, wizard=True, root=self.artifacts / name)
        self.addCleanup(game.close)
        return game

    def test_native_state_and_feature_discriminator(self):
        p = subprocess.run([str(self.exe)], capture_output=True, text=True, timeout=15)
        (self.artifacts / "native.txt").write_text(p.stdout + p.stderr)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_real_old_chaos_save_rejected(self):
        old = Path(
            os.environ.get(
                "NYARLATHACK_PRECURIO_DIR",
                "/home/hermes/.local/share/nyarlathack/generated-curio/prechange-on",
            )
        )
        self.assertTrue(
            (old / "dnethack").is_file(), "preserved old CHAOS build required"
        )
        g = self.game("old-rejection", old)
        g.start()
        self.assertEqual(g.save(), 0)
        self.assertTrue(list((g.game / "save").iterdir()))
        for name in ("dnethack", "nhdat"):
            shutil.copy2(ROOT / "dnethackdir" / name, g.game / name)
        g.start()
        self.assertIn(b"Configuration incompatibility", g.raw)
        self.assertFalse(
            any(
                e["event"] == "session" and e["detail"] == "restore" for e in g.events()
            )
        )
        self.assertEqual(g.quit(), 0)

    def test_real_nonempty_save_roundtrip(self):
        g = self.game("nonempty-roundtrip", ROOT / "dnethackdir")
        # Only this test executable seeds the record at native save entry.
        shutil.copy2(self.exe, g.game / "dnethack")
        g.start()
        self.assertEqual(g.save(), 0)
        g.start()
        self.assertNotIn(b"Configuration incompatibility", g.raw)
        self.assertTrue((g.game / "curio-restored.bin").is_file())
        self.assertTrue(
            any(
                e["event"] == "session" and e["detail"] == "restore" for e in g.events()
            )
        )
        self.assertEqual(g.quit(), 0)
