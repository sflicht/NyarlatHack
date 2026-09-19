"""ENGINE-UNIT: next-use replay rejects skipped/tampered records."""

import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class NextUseReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = tempfile.TemporaryDirectory(prefix="nyarl-next-use-replay-")
        cls.addClassCleanup(cls.build.cleanup)
        cls.binary = Path(cls.build.name) / "next-use-replay"
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
            str(ROOT / "tests/chaos/next_use_replay.c"),
            str(ROOT / "src/chaos_next_use.c"),
            str(ROOT / "src/chaos_next_use_admission.c"),
            str(ROOT / "src/chaos_next_use_runtime.c"),
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

    def run_mode(self, mode):
        result = subprocess.run(
            [str(self.binary), mode], capture_output=True, text=True, timeout=5
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return [json.loads(line) for line in result.stdout.splitlines() if line]

    def test_skipped_cursor_does_not_consume(self):
        row = self.run_mode("skip")[0]
        self.assertEqual(row["status"], 1)
        self.assertEqual(row["slot_w"], 1)

    def test_wrong_digest_does_not_consume(self):
        row = self.run_mode("bad_sha")[0]
        self.assertEqual(row["status"], 1)
        self.assertEqual(row["slot_w"], 1)

    def test_wrong_clock_does_not_consume(self):
        row = self.run_mode("wrong_clock")[0]
        self.assertEqual(row["status"], 1)
        self.assertEqual(row["slot_w"], 1)

    def test_replay_after_expiry_is_blocked(self):
        row = self.run_mode("after_expire")[0]
        self.assertEqual(row["status"], 1)

    def test_save_restore_keeps_pending_and_blocks_skip(self):
        row = self.run_mode("save_replay")[0]
        self.assertEqual(row["restored"], 1)
        self.assertEqual(row["status"], 1)
        self.assertEqual(row["slot_w"], 1)


if __name__ == "__main__":
    unittest.main()
