"""Task 2 only: native saved record and explicit format rejection, no hooks."""

import os
import hashlib
from pathlib import Path
import shutil
import subprocess
import struct
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
        # Frozen Game inherits its environment: official runner or env -i only.
        self.assertNotIn("NETHACKDIR", os.environ)
        self.assertNotIn("HACKDIR", os.environ)
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
        retained = {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (g.game / "save").iterdir()
        }
        self.assertTrue(retained)
        for name in ("dnethack", "nhdat"):
            shutil.copy2(ROOT / "dnethackdir" / name, g.game / name)
        g.start()
        self.assertIn(b"Configuration incompatibility", g.raw)
        self.assertFalse(
            any(
                e["event"] == "session" and e["detail"] == "restore" for e in g.events()
            )
        )
        self.assertEqual(
            {
                p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in (g.game / "save").iterdir()
            },
            retained,
        )
        self.assertEqual(g.quit(), 0)

    def test_current_invalid_chaos_save_preserved_without_resumption(self):
        # Synthetic native save-entry faults, NOT old-save compatibility proof.
        for fault in ("future", "mask", "version", "haunt", "curio"):
            with self.subTest(fault=fault):
                original = self.game("fault-source-" + fault, ROOT / "dnethackdir")
                shutil.copy2(self.exe, original.game / "dnethack")
                (original.game / "chaos-save-fault").write_text(fault)
                original.start()
                # unixmain uses UID + plname; getlock adds .0 and writes hackpid.
                # Calibrate ownership on the live source before it saves/exits.
                basename = f"{os.getuid()}wizard"
                source_lock = original.game / (basename + ".0")
                lock_bytes = source_lock.read_bytes()
                self.assertEqual(
                    struct.unpack("i", lock_bytes[: struct.calcsize("i")])[0],
                    original.pid,
                )
                (original.root / "owned-lock-before-save.bin").write_bytes(lock_bytes)
                self.assertEqual(original.save(), 0)
                saves = list((original.game / "save").iterdir())
                self.assertEqual(len(saves), 1)
                before = saves[0].read_bytes()
                digest = hashlib.sha256(before).hexdigest()
                (original.root / "native.savefile").write_bytes(before)
                rejected = self.game("fault-reject-" + fault, ROOT / "dnethackdir")
                target = rejected.game / "save" / saves[0].name
                shutil.copy2(saves[0], target)
                # Real other-session naming, not an unrelated arbitrary file.
                sentinels = {
                    rejected.game / f"{os.getuid()}OtherSession.0": struct.pack(
                        "i", os.getpid()
                    ),
                    rejected.game
                    / f"{os.getuid()}OtherSession.1": b"other-session-level-sentinel",
                }
                for path, contents in sentinels.items():
                    path.write_bytes(contents)
                self.assertFalse(list(rejected.game.glob(basename + ".*")))
                # start() is synchronous; rejection may exit before it returns.
                # This is a postcondition, not a pre-reject lock observation.
                text = rejected.start()
                self.assertEqual(rejected.finish(text), 1)
                self.assertIn(b"save file preserved", rejected.raw)
                self.assertFalse(rejected.events(), "no resumed/new gameplay")
                self.assertEqual(
                    hashlib.sha256(target.read_bytes()).hexdigest(), digest
                )
                self.assertEqual(
                    hashlib.sha256(saves[0].read_bytes()).hexdigest(), digest
                )
                self.assertTrue(target.stat().st_mode & 0o400)
                self.assertEqual(
                    [
                        p.name
                        for p in rejected.game.glob(basename + ".*")
                        if p.suffix[1:].isdecimal()
                    ],
                    [],
                    "rejection must clear this session's lock/level paths",
                )
                for path, contents in sentinels.items():
                    self.assertEqual(
                        path.read_bytes(), contents, "other session must survive"
                    )

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
