"""ENGINE-UNIT: real admission and runtime install clocks, not gameplay."""

import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class NextUseExpiryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = tempfile.TemporaryDirectory(prefix="nyarl-next-use-expiry-")
        cls.addClassCleanup(cls.build.cleanup)
        cls.binary = Path(cls.build.name) / "next-use-expiry"
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
            str(ROOT / "tests/chaos/next_use_expiry.c"),
            str(ROOT / "src/chaos_next_use.c"),
            str(ROOT / "src/chaos_next_use_admission.c"),
            str(ROOT / "src/chaos_next_use_runtime.c"),
            str(ROOT / "src/chaos_protocol.c"),
            "-Wl,--gc-sections",
            "-lm",
            "-o",
            str(cls.binary),
        ]
        result = subprocess.run(command, capture_output=True, timeout=30)
        if result.returncode:
            raise RuntimeError(result.stderr.decode())

    def run_case(self, at_safe, at_move, origin_root, ttl=100, probe=40, tamper=""):
        command = [
            str(self.binary),
            str(at_safe),
            str(at_move),
            str(origin_root),
            str(ttl),
            str(probe),
        ]
        if tamper:
            command.append(tamper)
        result = subprocess.run(command, capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        rows = [json.loads(line) for line in result.stdout.splitlines() if line]
        self.assertGreaterEqual(len(rows), 2)
        return rows[0], rows[-1]

    def test_separated_clocks_install_at_native_expiry(self):
        admit, runtime = self.run_case(7, 40, 123, probe=40)
        self.assertEqual(admit["admit"], 0)
        self.assertEqual(runtime["install"], 1)
        self.assertEqual(runtime["at_move"], 40)
        self.assertEqual(runtime["at_safe"], 7)
        self.assertEqual(runtime["expiry"], 140)
        self.assertNotEqual(runtime["expiry"], 107)

    def test_equal_clocks_install(self):
        admit, runtime = self.run_case(40, 40, 123, probe=40)
        self.assertEqual(admit["admit"], 0)
        self.assertEqual(runtime["install"], 1)
        self.assertEqual(runtime["expiry"], 140)

    def test_widely_separated_clocks_install(self):
        admit, runtime = self.run_case(1, 1000, 123, probe=1000)
        self.assertEqual(admit["admit"], 0)
        self.assertEqual(runtime["install"], 1)
        self.assertEqual(runtime["expiry"], 1100)
        self.assertEqual(runtime["at_safe"], 1)

    def test_expiry_before_at_and_after(self):
        _, before = self.run_case(7, 40, 123, probe=139)
        _, at = self.run_case(7, 40, 123, probe=140)
        _, after = self.run_case(7, 40, 123, probe=141)
        self.assertEqual(before["install"], 1)
        self.assertEqual(before["preflight"], 1)
        self.assertEqual(at["install"], 1)
        self.assertEqual(at["preflight"], 0)
        self.assertEqual(after["install"], 1)
        self.assertEqual(after["preflight"], 0)

    def test_rejects_negative_move_without_install(self):
        admit, runtime = self.run_case(7, -1, 123, probe=0)
        self.assertNotEqual(admit["admit"], 0)
        self.assertEqual(runtime["install"], 0)
        self.assertEqual(runtime["private"], 0)

    def test_rejects_overflowing_move_without_install(self):
        admit, runtime = self.run_case(7, 2147483548, 123, probe=0)
        self.assertNotEqual(admit["admit"], 0)
        self.assertEqual(runtime["install"], 0)

    def test_rejects_inconsistent_attempt_move(self):
        admit, runtime = self.run_case(7, 40, 123, probe=40, tamper="attempt-move")
        self.assertEqual(admit["admit"], 0)
        self.assertEqual(runtime["install"], 0)
        self.assertEqual(runtime["private"], 0)

    def test_rejects_tampered_safe_index(self):
        admit, runtime = self.run_case(7, 40, 123, probe=40, tamper="safe-index")
        self.assertEqual(admit["admit"], 0)
        self.assertEqual(runtime["install"], 0)
        self.assertEqual(runtime["private"], 0)

    def test_rejects_inconsistent_expiry(self):
        admit, runtime = self.run_case(7, 40, 123, probe=40, tamper="expiry")
        self.assertEqual(admit["admit"], 0)
        self.assertEqual(runtime["install"], 0)
        self.assertEqual(runtime["private"], 0)


if __name__ == "__main__":
    unittest.main()
