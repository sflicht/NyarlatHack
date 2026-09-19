"""Admission commit vs receipt-failure; real C, not gameplay."""

import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
LUA = subprocess.check_output(
    ["pkg-config", "--cflags", "--libs", "lua5.4"], text=True
).split()


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
            str(ROOT / "src/chaos_lua.c"),
            "-Wl,--gc-sections",
            "-lm",
            *LUA,
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

    def test_f_only_admit_install_price_is_one(self):
        row = self.run_mode("f-ok")
        self.assertEqual(row["admit"], 0)
        self.assertEqual(row["spent"], 1)
        self.assertEqual(row["cost"], 1)
        self.assertEqual(row["install"], 1)
        self.assertEqual(row["slot_w"], 0)
        self.assertEqual(row["slot_f"], 1)
        self.assertEqual(row["phase"], 3)

    def test_wf_admit_install_price_is_operation_count(self):
        row = self.run_mode("wf-ok")
        self.assertEqual(row["admit"], 0)
        self.assertEqual(row["spent"], 2)
        self.assertEqual(row["cost"], 2)
        self.assertEqual(row["ops"], 2)
        self.assertEqual(row["install"], 1)
        self.assertEqual(row["slot_w"], 1)
        self.assertEqual(row["slot_f"], 1)

    def test_second_delay_does_not_act(self):
        row = self.run_mode("delay-twice")
        self.assertEqual(row["admit"], 0)
        self.assertEqual(row["install"], 1)
        self.assertFalse(row["second_ready"])
        self.assertFalse(row["second"])

    def test_wrong_family_intent_does_not_act(self):
        row = self.run_mode("wrong-family")
        self.assertEqual(row["install"], 1)
        self.assertFalse(row["acted"])
        self.assertFalse(row["ready"])
        self.assertEqual(row["remap"], 0)

    def test_run_reset_does_not_inherit_slot(self):
        row = self.run_mode("run-reset")
        self.assertEqual(row["install"], 1)
        self.assertFalse(row["ready"])

    def test_ticks_after_consume_do_not_act_or_spend(self):
        row = self.run_mode("ticks")
        self.assertEqual(row["install"], 1)
        self.assertEqual(row["extra"], 0)
        self.assertEqual(row["spent_delta"], 0)

    def test_expired_w_slot_is_not_ready(self):
        row = self.run_mode("expire-w")
        self.assertEqual(row["admit"], 0)
        self.assertEqual(row["install"], 1)
        self.assertFalse(row["ready"])

    def test_consumed_slot_does_not_resurrect(self):
        row = self.run_mode("no-resurrect")
        self.assertEqual(row["install"], 1)
        self.assertFalse(row["reinstall"])
        self.assertFalse(row["ready"])

    def test_quiet_consumes_w_slot(self):
        row = self.run_mode("quiet-w")
        self.assertEqual(row["admit"], 0)
        self.assertEqual(row["install"], 1)
        self.assertFalse(row["second_ready"])

    def test_wf_order_w_then_f(self):
        row = self.run_mode("wf-order")
        self.assertEqual(row["admit"], 0)
        self.assertEqual(row["install"], 1)
        self.assertTrue(row["w"])
        self.assertTrue(row["f"])
        self.assertEqual(row["remap"], 1)

    def test_fw_order_f_then_w(self):
        row = self.run_mode("fw-order")
        self.assertEqual(row["admit"], 0)
        self.assertEqual(row["install"], 1)
        self.assertTrue(row["f"])
        self.assertTrue(row["w"])

    def test_install_failure_after_commit_does_not_rewind(self):
        row = self.run_mode("install-fail")
        self.assertEqual(row["admit"], 0)
        self.assertEqual(row["spent"], 1)
        self.assertEqual(row["install"], 0)
        self.assertEqual(row["phase"], 3)
        self.assertEqual(row["seq"], 3)
        self.assertEqual(row["private"], 0)

    def test_failed_install_does_not_overwrite_active_runtime(self):
        row = self.run_mode("preserve-runtime")
        self.assertEqual(row["first_admit"], 0)
        self.assertEqual(row["first_install"], 1)
        self.assertEqual(row["second_admit"], 0)
        self.assertEqual(row["second_install"], 0)
        self.assertGreater(row["private_before"], 0)
        self.assertEqual(row["private_after"], row["private_before"])
        self.assertEqual(row["first_spent"], 1)
        self.assertEqual(row["second_spent"], 1)

    def test_private_carrier_capacity_rejects_unchanged(self):
        row = self.run_mode("carrier")
        self.assertEqual(row["admit"], 3)  # PRIVATE_CARRIER_RESERVE
        self.assertEqual(row["spent"], 0)
        self.assertEqual(row["out_spent"], 0)
        self.assertEqual(row["count"], 0)

    def test_duplicate_operations_fail_at_parse(self):
        row = self.run_mode("parse-dup")
        self.assertNotEqual(row["parse"], 0)

    def test_malformed_origin_fails_at_parse(self):
        row = self.run_mode("parse-malformed")
        self.assertNotEqual(row["parse"], 0)

    def test_public_bound_rejects_without_overflow(self):
        row = self.run_mode("public-bound")
        self.assertEqual(row["admit"], 0)
        self.assertEqual(row["install"], 1)
        self.assertEqual(row["public"], 0)
        self.assertLessEqual(row["public"], 1)

    def _compile_mutant(self, old, new):
        import shutil

        folder = Path(tempfile.mkdtemp(prefix="nyarl-admit-mutant-"))
        source = folder / "chaos_next_use_admission.c"
        shutil.copy(ROOT / "src/chaos_next_use_admission.c", source)
        text = source.read_text()
        self.assertIn(old, text)
        source.write_text(text.replace(old, new, 1))
        exe = folder / "admit"
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
            str(source),
            str(ROOT / "src/chaos_next_use_runtime.c"),
            str(ROOT / "src/chaos_protocol.c"),
            str(ROOT / "src/chaos_lua.c"),
            "-Wl,--gc-sections",
            "-lm",
            *LUA,
            "-o",
            str(exe),
        ]
        result = subprocess.run(command, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        return exe

    def test_debit_bypass_fails_price_oracle(self):
        exe = self._compile_mutant(
            "commit.budget_state.spent += cost;",
            "/* bypass debit */",
        )
        p = subprocess.run(
            [str(exe), "wf-ok"], capture_output=True, text=True, timeout=5
        )
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        row = json.loads(p.stdout)
        self.assertNotEqual(row["spent"], 2)
