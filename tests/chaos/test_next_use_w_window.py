"""ENGINE-UNIT: W capture window after admit. Not dog_move gameplay."""

from pathlib import Path
import json
import os
import subprocess
import tempfile
import unittest

from chaos.next_use_envelope import publish_envelope

ROOT = Path(__file__).resolve().parents[2]
ROW = {
    "family": "W",
    "op": "whistle_attention",
    "origin": {
        "root_seq": 10,
        "notice_seq": 11,
        "end_seq": 12,
        "fact": "sound_high",
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


class NextUseWhistleWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = tempfile.TemporaryDirectory(prefix="nyarl-next-use-w-")
        cls.addClassCleanup(cls.build.cleanup)
        cls.binary = Path(cls.build.name) / "next-use-w-window"
        flags = subprocess.check_output(
            ["pkg-config", "--cflags", "--libs", "lua5.4"], text=True
        ).split()
        command = [
            "/usr/bin/gcc",
            "-DCHAOS",
            "-ffunction-sections",
            "-fdata-sections",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-Wno-misleading-indentation",
            "-isystem",
            str(ROOT / "include"),
            str(ROOT / "tests/chaos/next_use_w_window.c"),
            str(ROOT / "src/chaos_next_use.c"),
            str(ROOT / "src/chaos_next_use_admission.c"),
            str(ROOT / "src/chaos_next_use_runtime.c"),
            str(ROOT / "src/chaos_next_use_io.c"),
            str(ROOT / "src/chaos_next_use_safe.c"),
            str(ROOT / "src/chaos_protocol.c"),
            str(ROOT / "src/chaos_lua.c"),
            "-Wl,--gc-sections",
            *flags,
            "-lm",
            "-o",
            str(cls.binary),
        ]
        result = subprocess.run(command, capture_output=True, timeout=30)
        if result.returncode:
            raise RuntimeError(result.stderr.decode())

    def test_window_and_one_shot_attention(self):
        folder = tempfile.mkdtemp(prefix="nyarl-next-use-w-run-")
        os.chmod(folder, 0o700)
        publish_envelope(folder, ROW, HOST)
        p = subprocess.run(
            [str(self.binary), folder, "40", "7", HOST["run"]],
            capture_output=True,
            text=True,
            timeout=5,
        )
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        row = json.loads(p.stdout)
        self.assertEqual(row["admitted"], 1)
        self.assertEqual(row["on_action"], 1)
        self.assertEqual(row["ready_early"], 0)
        self.assertEqual(row["ready"], 1)
        self.assertEqual(row["attention"], 1)
        self.assertEqual(row["again"], 0)
        self.assertEqual(row["wrong"], 0)
        self.assertEqual(row["late"], 0)


if __name__ == "__main__":
    unittest.main()
