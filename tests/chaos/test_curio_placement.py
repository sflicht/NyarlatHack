"""Task 3b: controlled-map linked native placement (not real bones files)."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from gameplay_support import ROOT, Game


@unittest.skipUnless(
    os.environ.get("NYARLATHACK_GAME_TESTS") == "1", "real game opt-in"
)
class CurioPlacementTests(unittest.TestCase):
    def test_actual_wizard_goto_level_ordinary_generation(self):
        # Native goto_level and mklev, unlike the controlled fixtures below.
        artifacts = Path(tempfile.mkdtemp(prefix="nyarl-curio-transition-"))
        print("CURIO_TRANSITION_ARTIFACTS=" + str(artifacts), flush=True)
        clock = artifacts / "clock.so"
        subprocess.run(
            [
                "cc",
                "-shared",
                "-fPIC",
                str(ROOT / "tests/chaos/replay_clock.c"),
                "-ldl",
                "-o",
                str(clock),
            ],
            check=True,
        )
        game = Game(
            ROOT / "dnethackdir", clock, wizard=True, root=artifacts / "session"
        )
        self.addCleanup(game.close)
        source = b"return {name='Counter',inspect=function(c) return 'Quiet.' end,apply=function(c) return {text='Quiet.',state=0,sanity_delta=0} end}"
        (game.run / "curio.lua").write_bytes(source)
        (game.run / "curio.lua").chmod(0o600)
        game.start()
        game.more(game.send(b"\x16"))
        game.more(game.send("2\n"))
        placed = [
            e
            for e in game.events()
            if e["event"] == "curio" and e["detail"] == "placed"
        ]
        self.assertEqual(len(placed), 1)
        self.assertEqual(placed[0]["spent"], 1)
        self.assertEqual((game.run / "curio-used.lua").read_bytes(), source)
        # Revisit and a later fresh floor cannot produce a replacement.
        for floor in (1, 2, 3):
            game.more(game.send(b"\x16"))
            game.more(game.send(str(floor) + "\n"))
        self.assertEqual(
            len(
                [
                    e
                    for e in game.events()
                    if e["event"] == "curio" and e["detail"] == "placed"
                ]
            ),
            1,
        )
        self.assertEqual(game.quit(), 0)

    def test_linked_placement(self):
        artifacts = Path(tempfile.mkdtemp(prefix="nyarl-curio-placement-"))
        print("CURIO_PLACEMENT_ARTIFACTS=" + str(artifacts), flush=True)
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
        exe = artifacts / "curio-placement"
        command = [
            "cc",
            "-g",
            "-DCHAOS",
            "-I" + str(ROOT / "include"),
            str(ROOT / "tests/chaos/curio_placement.c"),
            *map(str, objects),
            "-Wl,--wrap=mksobj",
            "-Wl,--wrap=chaos_shadow_active",
            "-Wl,--wrap=getbones",
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
        result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=15)
        (artifacts / "native.txt").write_text(result.stdout + result.stderr)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
