"""Admission commit vs receipt-failure; real C, not gameplay."""

import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class NextUseAdmitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="nyarl-admit-")
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.exe = Path(cls.tmp.name) / "admit"
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
            str(ROOT / "tests/chaos/next_use_admit.c"),
            str(ROOT / "src/chaos_next_use.c"),
            str(ROOT / "src/chaos_next_use_admission.c"),
            str(ROOT / "src/chaos_next_use_runtime.c"),
            str(ROOT / "src/chaos_protocol.c"),
            "-Wl,--gc-sections",
            "-lm",
            "-o",
            str(cls.exe),
        ]
        result = subprocess.run(command, capture_output=True, timeout=30)
        if result.returncode:
            raise RuntimeError(result.stderr.decode())

    def run_mode(self, mode):
        p = subprocess.run(
            [str(self.exe), mode], capture_output=True, text=True, timeout=5
        )
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        return json.loads(p.stdout)

    def test_commit_then_install_with_unequal_clocks(self):
        row = self.run_mode("ok")
        self.assertEqual(row["admit"], 0)
        self.assertEqual(row["spent"], 1)
        self.assertEqual(row["cost"], 1)
        self.assertEqual(row["install"], 1)
        self.assertEqual(row["phase"], 3)  # COMMITTED

    def test_receipt_failure_keeps_spend_and_does_not_install(self):
        row = self.run_mode("receipt-fail")
        self.assertEqual(row["admit"], 5)  # RECEIPT_TRANSPORT
        self.assertEqual(row["spent"], 1)
        self.assertEqual(row["install"], 0)
        self.assertEqual(row["phase"], 4)  # TERMINATED

    def test_second_call_does_not_charge_again(self):
        row = self.run_mode("second-call")
        self.assertEqual(row["first"], 0)
        self.assertNotEqual(row["second"], 0)
        self.assertEqual(row["spent"], 1)

    def test_budget_rejection_does_not_change_source_spend(self):
        row = self.run_mode("budget")
        self.assertEqual(row["admit"], 4)  # BUDGET
        self.assertEqual(row["spent"], 12)
        self.assertEqual(row["out_spent"], 0)
