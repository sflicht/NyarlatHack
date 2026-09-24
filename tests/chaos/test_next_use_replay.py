"""ENGINE-UNIT: next-use replay rejects skipped/tampered records."""

import hashlib
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

    def test_zero_delta_records_use_persisted_sequence_not_carrier_buffer(self):
        for mode in (
            "zero_delta_live",
            "zero_delta_restored_boundary",
            "zero_delta_restored_decision",
        ):
            with self.subTest(mode=mode):
                row = self.run_mode(mode)[0]
                self.assertEqual(row["restored"], int(mode != "zero_delta_live"))
                self.assertEqual(row["status"], 0)
                self.assertEqual(
                    (row["past"], row["future"], row["duplicate"]), (1, 1, 1)
                )
                self.assertEqual(row["unchanged"], 1)

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

    def test_replay_applies_w_quiet_once(self):
        row = self.run_mode("apply_w")[0]
        self.assertEqual(row["status"], 0)
        self.assertEqual(row["second"], 1)
        declared = b'{"next_use_intent_v":2,"op":"quiet","state":0}'
        self.assertEqual(row["intent_sha"], hashlib.sha256(declared).hexdigest())

    def test_replay_applies_f_once(self):
        row = self.run_mode("apply_f")[0]
        self.assertEqual(row["status"], 0)
        self.assertEqual(row["second"], 1)
        declared = b'{"next_use_intent_v":2,"op":"fountain_refresh","state":0}'
        self.assertEqual(row["intent_sha"], hashlib.sha256(declared).hexdigest())

    def test_replay_applies_two_slot_w_then_blocks_repeat(self):
        row = self.run_mode("apply_wf")[0]
        self.assertEqual(row["status"], 0)
        self.assertEqual(row["second"], 1)
        declared = b'{"next_use_intent_v":2,"op":"quiet","state":0}'
        self.assertEqual(row["intent_sha"], hashlib.sha256(declared).hexdigest())

    def test_replay_after_save_restore_applies_once(self):
        row = self.run_mode("apply_w_save")[0]
        self.assertEqual(row["restored"], 1)
        self.assertEqual(row["status"], 0)
        self.assertEqual(row["second"], 1)
        declared = b'{"next_use_intent_v":2,"op":"quiet","state":0}'
        self.assertEqual(row["intent_sha"], hashlib.sha256(declared).hexdigest())

    def test_independently_wrong_intent_digest_is_blocked(self):
        row = self.run_mode("apply_w_bad_intent")[0]
        self.assertEqual(row["status"], 1)
        self.assertEqual(row["second"], 1)


if __name__ == "__main__":
    unittest.main()
