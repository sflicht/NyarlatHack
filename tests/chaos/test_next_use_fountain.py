"""drinkfountain remap band. Controlled native fate. Not ordinary play."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from chaos.next_use_envelope import engine_run_hex, publish_envelope
from native_rng import controlled_rng_objects

ROOT = Path(__file__).resolve().parents[2]
ROW = {
    "family": "F",
    "op": "fountain_refresh",
    "origin": {
        "root_seq": 10,
        "notice_seq": 11,
        "end_seq": 12,
        "fact": "water_refreshed",
    },
}
HOST = {
    "at": 7,
    "id": 1,
    "level_dlevel": 1,
    "level_dnum": 0,
    "move": 40,
    "run": "ab" * 32,
    "variant": 0,
}


@unittest.skipUnless(
    os.environ.get("NYARLATHACK_GAME_TESTS") == "1", "real game opt-in"
)
class NextUseFountainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(tempfile.mkdtemp(prefix="nyarl-next-use-fountain-"))
        print("NEXT_USE_FOUNTAIN_ARTIFACTS=" + str(cls.root), flush=True)
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
        cls.objects = controlled_rng_objects(objects, cls.root)
        cls.exe = cls.root / "fountain"
        command = [
            "cc",
            "-g",
            "-DCHAOS",
            "-I" + str(ROOT / "include"),
            str(ROOT / "tests/chaos/next_use_fountain.c"),
            *map(str, cls.objects),
            "-lncursesw",
            "-ltinfo",
            "-lm",
            *subprocess.check_output(
                ["pkg-config", "--libs", "lua5.4"], text=True
            ).split(),
            "-o",
            str(cls.exe),
        ]
        result = subprocess.run(command, capture_output=True, timeout=45)
        if result.returncode:
            raise RuntimeError(result.stderr.decode())

    def run_case(self, fate, admit):
        return self.run_mode(fate, "admit" if admit else "none")

    def run_mode(self, fate, mode):
        folder = Path(tempfile.mkdtemp(prefix="nyarl-next-use-fountain-run-"))
        os.chmod(folder, 0o700)
        host = dict(HOST)
        host["run"] = engine_run_hex(folder)
        publish_envelope(folder, ROW, host)
        env = dict(os.environ)
        env["NYARLATHACK_RUN_DIR"] = str(folder)
        env["NYARLATHACK_OBSERVATIONS"] = "1"
        env["TERM"] = "xterm"
        env["COLUMNS"] = "80"
        env["LINES"] = "24"
        p = subprocess.run(
            [str(self.exe), str(fate), mode, str(folder)],
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
            cwd=folder,
        )
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        return json.loads((folder / "result.json").read_text())

    def test_remap_band_refreshes_once(self):
        low = self.run_case(10, True)
        self.assertEqual(low["admit"], 1, low)
        high = self.run_case(18, True)
        self.assertEqual(low["contacted"], 1)
        self.assertEqual(high["contacted"], 1)
        self.assertGreater(low["hunger_delta"], 0)
        self.assertGreater(high["hunger_delta"], 0)
        self.assertGreaterEqual(low["seq_delta"], 3)
        self.assertGreaterEqual(high["seq_delta"], 3)
        self.assertEqual(low["completed_after"], 0)
        self.assertEqual(high["completed_after"], 0)

    def test_adjacent_low_is_natural_not_remap(self):
        row = self.run_case(9, True)
        self.assertEqual(row["contacted"], 1)
        self.assertGreater(row["hunger_delta"], 0)
        self.assertEqual(row["completed_after"], 0)

    def test_adjacent_high_is_native_not_remap(self):
        row = self.run_case(19, True)
        self.assertEqual(row["contacted"], 1)
        self.assertEqual(row["hunger_delta"], 0)

    def test_band_without_admit_is_tepid(self):
        row = self.run_case(10, False)
        self.assertEqual(row["contacted"], 0)
        self.assertEqual(row["hunger_delta"], 0)
        self.assertLess(row["seq_delta"], 3)

    def test_levitation_blocks_remap(self):
        row = self.run_mode(10, "levitate")
        self.assertEqual(row["admit"], 1)
        self.assertEqual(row["hunger_delta"], 0)
        self.assertEqual(row["typ_after"], row["typ_before"])


if __name__ == "__main__":
    unittest.main()
