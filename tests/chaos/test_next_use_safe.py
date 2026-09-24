"""ENGINE-UNIT: opt-in safe-point admit once; not gameplay."""

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
ROW_F = {
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


class NextUseSafeAdmitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = tempfile.TemporaryDirectory(prefix="nyarl-next-use-safe-")
        cls.addClassCleanup(cls.build.cleanup)
        cls.binary = Path(cls.build.name) / "next-use-safe"
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
            str(ROOT / "tests/chaos/next_use_safe.c"),
            str(ROOT / "src/chaos_next_use.c"),
            str(ROOT / "src/chaos_next_use_admission.c"),
            str(ROOT / "src/chaos_next_use_runtime.c"),
            str(ROOT / "src/chaos_next_use_io.c"),
            str(ROOT / "src/chaos_next_use_journal.c"),
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

    def publish(self, move=40):
        folder = tempfile.mkdtemp(prefix="nyarl-next-use-safe-run-")
        os.chmod(folder, 0o700)
        host = dict(HOST)
        host["move"] = move
        publish_envelope(folder, ROW, host)
        return folder

    def publish_f(self, move=40):
        folder = tempfile.mkdtemp(prefix="nyarl-next-use-safe-run-")
        os.chmod(folder, 0o700)
        host = dict(HOST)
        host["move"] = move
        publish_envelope(folder, ROW_F, host)
        return folder

    def rewrite_wf(self, folder):
        path = Path(folder) / "next_use-envelope.json"
        payload = json.loads(path.read_text())
        second = dict(payload["origin_refs"][0])
        second["family"] = "F"
        second["fact"] = "water_refreshed"
        second["root"] = 13
        second["notice_seq"] = 14
        second["end_seq"] = 15
        payload["operations"] = ["W", "F"]
        payload["origin_refs"] = [payload["origin_refs"][0], second]
        payload["cost"] = 2
        payload["telegraph"] = "next-use-v2-WF"
        path.write_text(json.dumps(payload, separators=(",", ":"), sort_keys=True))
        os.chmod(path, 0o600)
        return folder

    def run_case(
        self,
        folder,
        at_safe=7,
        at_move=40,
        dnum=0,
        dlevel=1,
        run=None,
        polls=2,
        enabled=1,
        wrapper="try",
        telegraph="ok",
        budget="valid",
        receipt="ok",
        evidence="valid",
        clock="native",
        identity=1750000001,
    ):
        if run is None:
            run = HOST["run"]
        p = subprocess.run(
            [
                str(self.binary),
                folder,
                str(at_safe),
                str(at_move),
                str(dnum),
                str(dlevel),
                run,
                str(polls),
                str(enabled),
                wrapper,
                telegraph,
                budget,
                receipt,
                evidence,
                clock,
                str(identity),
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        return json.loads(p.stdout)

    def test_missing_game_identity_rejects_before_telegraph_or_debit(self):
        row = self.run_case(self.publish(), identity=0)
        self.assertEqual(row["active"], 0)
        self.assertEqual(row["admitted"], 0)
        self.assertEqual(row["telegraph"], 0)
        self.assertEqual(row["caller_spent"], row["caller_spent_before"])

    def test_admits_once_and_second_poll_is_idle(self):
        row = self.run_case(self.publish())
        self.assertEqual(row["loaded"], 1)
        self.assertEqual(row["admitted"], 1)
        self.assertEqual(row["active"], 1)
        self.assertEqual(row["telegraph"], 1)
        self.assertEqual(row["spent"], 1)
        self.assertEqual(row["second_admitted"], 0)
        self.assertEqual(row["second_telegraph"], 0)
        self.assertEqual(row["second_spent"], 0)
        self.assertEqual(row["run_token"], 1750000001)
        self.assertEqual(row["level_token"], 100001)
        self.assertNotEqual(row["run_token"], 1)
        self.assertNotEqual(row["level_token"], 1)

    def test_disabled_does_not_load(self):
        row = self.run_case(self.publish(), enabled=0)
        self.assertEqual(row["loaded"], 0)
        self.assertEqual(row["admitted"], 0)
        self.assertEqual(row["spent"], 0)

    def test_wrong_run_is_rejected(self):
        row = self.run_case(self.publish(), run="cd" * 32)
        self.assertEqual(row["loaded"], 1)
        self.assertEqual(row["rejected"], 1)
        self.assertEqual(row["admitted"], 0)
        self.assertEqual(row["spent"], 0)

    def test_wrong_level_is_rejected(self):
        row = self.run_case(self.publish(), dlevel=2)
        self.assertEqual(row["rejected"], 1)
        self.assertEqual(row["admitted"], 0)

    def test_late_schedule_is_rejected(self):
        row = self.run_case(self.publish(), at_safe=8)
        self.assertEqual(row["rejected"], 1)
        self.assertEqual(row["admitted"], 0)

    def test_future_schedule_stays_pending(self):
        row = self.run_case(self.publish(), at_safe=6)
        self.assertEqual(row["pending"], 1)
        self.assertEqual(row["admitted"], 0)
        self.assertEqual(row["spent"], 0)

    def test_stale_origin_is_rejected(self):
        row = self.run_case(self.publish(), at_move=141)
        self.assertEqual(row["rejected"], 1)
        self.assertEqual(row["admitted"], 0)

    def test_tampered_source_cannot_be_admitted(self):
        folder = self.publish()
        path = Path(folder) / "next_use-envelope.json"
        payload = json.loads(path.read_text())
        payload["source"] = payload["source"] + " "
        path.write_text(json.dumps(payload, separators=(",", ":"), sort_keys=True))
        os.chmod(path, 0o600)
        row = self.run_case(folder)
        self.assertEqual(row["rejected"], 1)
        self.assertEqual(row["admitted"], 0)

    def test_try_missing_telegraph_does_not_admit(self):
        row = self.run_case(self.publish(), telegraph="none")
        self.assertEqual(row["admitted"], 0)
        self.assertEqual(row["spent"], 0)
        self.assertEqual(row["caller_spent"], 0)

    def test_production_wrapper_admits_and_charges_caller_once(self):
        row = self.run_case(self.publish(), wrapper="on_safe")
        self.assertEqual(row["loaded"], 1)
        self.assertEqual(row["admitted"], 1)
        self.assertEqual(row["active"], 1)
        self.assertEqual(row["telegraph"], 1)
        self.assertEqual(row["caller_spent_before"], 0)
        self.assertEqual(row["caller_spent"], 1)
        self.assertEqual(row["second_admitted"], 0)
        self.assertEqual(row["second_telegraph"], 0)
        self.assertEqual(row["second_caller_spent"], 1)
        self.assertEqual(row["telegraph_spent"], 0)

    def test_production_missing_telegraph_rejects(self):
        row = self.run_case(self.publish(), wrapper="on_safe", telegraph="none")
        self.assertEqual(row["admitted"], 0)
        self.assertEqual(row["caller_spent"], 0)

    def test_production_failed_telegraph_rejects_unchanged(self):
        row = self.run_case(self.publish(), wrapper="on_safe", telegraph="fail")
        self.assertEqual(row["admitted"], 0)
        self.assertEqual(row["active"], 0)
        self.assertEqual(row["caller_spent"], 0)
        self.assertEqual(row["telegraph_spent"], 0)

    def test_production_missing_run_rejects(self):
        row = self.run_case(self.publish(), wrapper="on_safe", run="none")
        self.assertEqual(row["admitted"], 0)
        self.assertEqual(row["caller_spent"], 0)

    def test_production_wrong_run_rejects(self):
        row = self.run_case(self.publish(), wrapper="on_safe", run="cd" * 32)
        self.assertEqual(row["admitted"], 0)
        self.assertEqual(row["caller_spent"], 0)

    def test_production_wrong_level_rejects(self):
        row = self.run_case(self.publish(), wrapper="on_safe", dlevel=2)
        self.assertEqual(row["admitted"], 0)
        self.assertEqual(row["caller_spent"], 0)

    def test_production_late_schedule_rejects(self):
        row = self.run_case(self.publish(), wrapper="on_safe", at_safe=8)
        self.assertEqual(row["admitted"], 0)
        self.assertEqual(row["caller_spent"], 0)

    def test_production_stale_origin_clock_rejects(self):
        row = self.run_case(self.publish(), wrapper="on_safe", at_move=141)
        self.assertEqual(row["admitted"], 0)
        self.assertEqual(row["caller_spent"], 0)

    def test_production_missing_origin_evidence_rejects(self):
        row = self.run_case(self.publish(), wrapper="on_safe", evidence="missing")
        self.assertEqual(row["admitted"], 0)
        self.assertEqual(row["caller_spent"], 0)

    def test_production_incomplete_origin_rejects(self):
        row = self.run_case(self.publish(), wrapper="on_safe", evidence="incomplete")
        self.assertEqual(row["admitted"], 0)
        self.assertEqual(row["caller_spent"], 0)

    def test_production_stale_origin_evidence_rejects(self):
        row = self.run_case(self.publish(), wrapper="on_safe", evidence="stale")
        self.assertEqual(row["admitted"], 0)
        self.assertEqual(row["caller_spent"], 0)

    def test_production_wrong_origin_run_rejects(self):
        row = self.run_case(self.publish(), wrapper="on_safe", evidence="wrong_run")
        self.assertEqual(row["admitted"], 0)
        self.assertEqual(row["caller_spent"], 0)

    def test_production_wrong_origin_level_rejects(self):
        row = self.run_case(self.publish(), wrapper="on_safe", evidence="wrong_level")
        self.assertEqual(row["admitted"], 0)
        self.assertEqual(row["caller_spent"], 0)

    def test_production_wrong_origin_fact_rejects(self):
        row = self.run_case(self.publish(), wrapper="on_safe", evidence="wrong_fact")
        self.assertEqual(row["admitted"], 0)
        self.assertEqual(row["caller_spent"], 0)

    def test_production_invalid_budget_rejects_unchanged(self):
        row = self.run_case(self.publish(), wrapper="on_safe", budget="invalid")
        self.assertEqual(row["admitted"], 0)
        self.assertEqual(row["caller_spent"], 100)
        self.assertEqual(row["budget_valid"], 0)

    def test_production_insufficient_budget_rejects_unchanged(self):
        row = self.run_case(self.publish(), wrapper="on_safe", budget="empty")
        self.assertEqual(row["admitted"], 0)
        self.assertEqual(row["caller_spent"], 12)

    def test_production_receipt_failure_does_not_install(self):
        row = self.run_case(self.publish(), wrapper="on_safe", receipt="fail")
        self.assertEqual(row["active"], 0)
        self.assertEqual(row["admitted"], 0)
        self.assertEqual(row["caller_spent"], 1)

    def test_production_tampered_source_rejects(self):
        folder = self.publish()
        path = Path(folder) / "next_use-envelope.json"
        payload = json.loads(path.read_text())
        payload["source"] = payload["source"] + " "
        path.write_text(json.dumps(payload, separators=(",", ":"), sort_keys=True))
        os.chmod(path, 0o600)
        row = self.run_case(folder, wrapper="on_safe")
        self.assertEqual(row["admitted"], 0)
        self.assertEqual(row["caller_spent"], 0)

    def test_production_shared_spender_does_not_rewind_hunger(self):
        row = self.run_case(self.publish(), wrapper="on_safe", budget="shared")
        self.assertEqual(row["admitted"], 1)
        self.assertEqual(row["caller_spent_before"], 3)
        self.assertEqual(row["caller_spent"], 4)
        self.assertEqual(row["reserved"], 3)
        self.assertEqual(row["hunger_value"], 2)
        self.assertEqual(row["hunger_cost"], 3)
        self.assertEqual(row["hunger_expires"], 100)
        self.assertEqual(row["budget_valid"], 1)
        self.assertEqual(row["second_caller_spent"], 4)

    def test_production_two_origin_without_lookup_rejects_before_telegraph(self):
        row = self.run_case(self.rewrite_wf(self.publish()), wrapper="on_safe")
        self.assertEqual(row["admitted"], 0)
        self.assertEqual(row["active"], 0)
        self.assertEqual(row["caller_spent"], 0)
        self.assertEqual(row["telegraph"], 0)
        self.assertEqual(row["rejected"], 1)

    def test_production_two_origin_both_bound_admits(self):
        row = self.run_case(
            self.rewrite_wf(self.publish()), wrapper="on_safe", evidence="wf"
        )
        self.assertEqual(row["admitted"], 1)
        self.assertEqual(row["active"], 1)
        self.assertEqual(row["caller_spent"], 2)
        self.assertEqual(row["telegraph"], 1)
        self.assertEqual(row["rejected"], 0)

    def test_production_wrong_second_origin_rejects_before_telegraph(self):
        row = self.run_case(
            self.rewrite_wf(self.publish()),
            wrapper="on_safe",
            evidence="wf_wrong_f",
        )
        self.assertEqual(row["admitted"], 0)
        self.assertEqual(row["caller_spent"], 0)
        self.assertEqual(row["telegraph"], 0)
        self.assertEqual(row["rejected"], 1)

    def test_production_f_then_w_bind_order_admits(self):
        row = self.run_case(
            self.rewrite_wf(self.publish()), wrapper="on_safe", evidence="fw"
        )
        self.assertEqual(row["admitted"], 1)
        self.assertEqual(row["caller_spent"], 2)
        self.assertEqual(row["telegraph"], 1)

    def test_production_f_only_admits(self):
        row = self.run_case(self.publish_f(), wrapper="on_safe", evidence="valid_f")
        self.assertEqual(row["admitted"], 1)
        self.assertEqual(row["caller_spent"], 1)
        self.assertEqual(row["telegraph"], 1)

    def test_production_negative_native_clock_rejects(self):
        row = self.run_case(self.publish(), wrapper="on_safe", clock="negative")
        self.assertEqual(row["admitted"], 0)
        self.assertEqual(row["caller_spent"], 0)
        self.assertEqual(row["rejected"], 1)

    def test_production_overflow_native_clock_rejects(self):
        row = self.run_case(
            self.publish(move=2147483497), wrapper="on_safe", clock="overflow"
        )
        self.assertEqual(row["admitted"], 0)
        self.assertEqual(row["caller_spent"], 0)
        self.assertEqual(row["rejected"], 1)

    def test_saturating_native_clock_is_detected(self):
        import shutil

        folder = Path(tempfile.mkdtemp(prefix="nyarl-safe-mutant-"))
        source = folder / "chaos_next_use_safe.c"
        shutil.copy(ROOT / "src/chaos_next_use_safe.c", source)
        text = source.read_text()
        old = (
            "    if (at_safe < 0 || at_safe > 2147483647L\n"
            "        || monstermoves < 0 || monstermoves > 2147483547L) {\n"
            "        res.rejected = 1;\n"
            "        return finish(&res, CHAOS_NEXT_USE_ADMISSION_SCHEMA);\n"
            "    }\n"
        )
        self.assertIn(old, text)
        source.write_text(text.replace(old, "", 1))
        text = source.read_text()
        old_move = "    req.at_move = (int)monstermoves;\n"
        new_move = (
            "    req.at_move = monstermoves > 2147483547L ? 2147483547\n"
            "                  : monstermoves < 0L ? 0 : (int)monstermoves;\n"
        )
        self.assertIn(old_move, text)
        source.write_text(text.replace(old_move, new_move, 1))
        flags = subprocess.check_output(
            ["pkg-config", "--cflags", "--libs", "lua5.4"], text=True
        ).split()
        exe = folder / "next-use-safe"
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
            str(ROOT / "tests/chaos/next_use_safe.c"),
            str(ROOT / "src/chaos_next_use.c"),
            str(ROOT / "src/chaos_next_use_admission.c"),
            str(ROOT / "src/chaos_next_use_runtime.c"),
            str(ROOT / "src/chaos_next_use_io.c"),
            str(ROOT / "src/chaos_next_use_journal.c"),
            str(source),
            str(ROOT / "src/chaos_protocol.c"),
            str(ROOT / "src/chaos_lua.c"),
            "-Wl,--gc-sections",
            *flags,
            "-lm",
            "-o",
            str(exe),
        ]
        result = subprocess.run(command, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        run = self.publish()
        p = subprocess.run(
            [
                str(exe),
                run,
                "7",
                "40",
                "0",
                "1",
                HOST["run"],
                "2",
                "1",
                "on_safe",
                "ok",
                "valid",
                "ok",
                "valid",
                "negative",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        row = json.loads(p.stdout)
        self.assertEqual(row["admitted"], 1)


if __name__ == "__main__":
    unittest.main()
