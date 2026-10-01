"""ENGINE-UNIT: opt-in safe-point admit once; not gameplay."""

from pathlib import Path
import json
import os
import subprocess
import tempfile
import unittest

from chaos.next_use_envelope import publish_envelope
from artifact_hygiene import RetainOnFailure, track

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


class NextUseSafeAdmitTests(RetainOnFailure):
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
        folder = track(self, tempfile.mkdtemp(prefix="nyarl-next-use-safe-run-"))
        os.chmod(folder, 0o700)
        host = dict(HOST)
        host["move"] = move
        publish_envelope(folder, ROW, host)
        return folder

    def publish_f(self, move=40):
        folder = track(self, tempfile.mkdtemp(prefix="nyarl-next-use-safe-run-"))
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
        companion=None,
    ):
        if run is None:
            run = HOST["run"]
        env = dict(os.environ)
        env.pop("NYARLATHACK_TEST_COMPANION", None)
        if companion is not None:
            env["NYARLATHACK_TEST_COMPANION"] = companion
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
            env=env,
        )
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        return json.loads(p.stdout)

    def test_missing_game_identity_rejects_before_telegraph_or_debit(self):
        row = self.run_case(self.publish(), identity=0)
        self.assertEqual(row["active"], 0)
        self.assertEqual(row["admitted"], 0)
        self.assertEqual(row["telegraph"], 0)
        self.assertEqual(row["caller_spent"], row["caller_spent_before"])

    def test_terminal_requires_closed_journal_and_strictly_fresh_origin(self):
        for wrapper, expected in (("try", 0), ("on_safe", 1)):
            with self.subTest(wrapper=wrapper):
                row = self.run_case(self.publish(), polls=3, wrapper=wrapper)
                self.assertEqual(row["future_open"], expected)
                self.assertEqual(row["terminal_seq"], 20)
                self.assertEqual(row["count"], 1)

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

    def test_policy_boundaries_restore_and_temporary_journal_gate(self):
        result = subprocess.run(
            [str(self.binary), "policy"], capture_output=True, text=True, timeout=5
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout), {"policy_checks": 1})

    def test_attempt_identity_is_saved_for_admission_and_rejection(self):
        for mode in ("ok", "fail"):
            with self.subTest(telegraph=mode):
                row = self.run_case(self.publish(), telegraph=mode)
                self.assertEqual(row["count"], 1)
                self.assertEqual(row["ordinal"], 1)
                self.assertEqual(row["last_program_id"], HOST["id"])
                self.assertEqual(row["second_admitted"], 0)
        row = self.run_case(self.publish(), at_safe=6)
        self.assertEqual(row["count"], 0)  # pending is not a settled attempt

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

    # #200 (A): the origin may be from an earlier level; the program is
    # installed on the level of the safe point, where its effect lands.
    def test_origin_on_earlier_level_admits_on_this_level(self):
        row = self.run_case(self.publish(), dlevel=2)
        self.assertEqual(
            (row["rejected"], row["admitted"], row["telegraph"]), (0, 1, 1)
        )
        self.assertEqual(row["level_token"], 100002)

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
        row = self.run_case(self.publish(), at_move=341)
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

    def test_production_origin_on_earlier_level_admits(self):
        folder = self.publish()
        row = self.run_case(folder, wrapper="on_safe", dlevel=2)
        self.assertEqual((row["admitted"], row["caller_spent"]), (1, 1))
        self.assertEqual([r.get("kind") for r in self.rows(folder)], [2])

    def test_production_late_schedule_rejects(self):
        row = self.run_case(self.publish(), wrapper="on_safe", at_safe=8)
        self.assertEqual(row["admitted"], 0)
        self.assertEqual(row["caller_spent"], 0)

    def test_production_stale_origin_clock_rejects(self):
        row = self.run_case(self.publish(), wrapper="on_safe", at_move=341)
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

    def test_production_newer_second_origin_rebinds_only_that_family(self):
        # #177 option 1: the engine's newer F origin (root 20) replaces the
        # published F origin (root 13); the matching W origin stays bound.
        folder = self.rewrite_wf(self.publish())
        row = self.run_case(folder, wrapper="on_safe", evidence="wf_wrong_f")
        self.assertEqual(row["admitted"], 1)
        self.assertEqual(row["rebound"], 2)
        self.assertEqual(row["caller_spent"], 2)
        self.assertEqual(row["telegraph"], 1)
        receipt = (Path(folder) / "next_use-receipt.jsonl").read_text()
        self.assertIn(
            '"origins":[{"family":"W","published":10,"bound":10},'
            '{"family":"F","published":13,"bound":20}]',
            receipt,
        )

    def rebind_case(self, evidence, **changes):
        # The newer engine origin is at move 45; admit after it (move 50).
        folder = self.publish()
        changes.setdefault("at_move", 50)
        row = self.run_case(folder, wrapper="on_safe", evidence=evidence, **changes)
        return folder, row

    def rows(self, folder):
        path = Path(folder) / "next_use-receipt.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text().splitlines()]

    def test_rebind_newer_same_family_admits_and_records_both_origins(self):
        folder, row = self.rebind_case("rebind_w")
        self.assertEqual(
            (row["admitted"], row["rebound"], row["telegraph"], row["reasons"]),
            (1, 1, 1, 0),
        )
        self.assertEqual(row["caller_spent"], 1)
        rows = self.rows(folder)
        self.assertEqual([row.get("kind") for row in rows], [2])
        self.assertEqual(
            rows[0]["origins"], [{"family": "W", "published": 10, "bound": 20}]
        )

    # #200 (C): a second whistle refreshes the origin on whatever level it
    # happened; the program is installed on the safe point's level.
    def test_rebind_to_newer_origin_on_other_level_admits(self):
        folder, row = self.rebind_case("rebind_other_level")
        self.assertEqual(
            (row["admitted"], row["rebound"], row["telegraph"], row["reasons"]),
            (1, 1, 1, 0),
        )
        self.assertEqual(
            self.rows(folder)[0]["origins"],
            [{"family": "W", "published": 10, "bound": 20}],
        )
        # A and C together: published and newer origins both on level 2, the
        # safe point on level 3.
        folder, row = self.rebind_case("rebind_other_level", dlevel=3)
        self.assertEqual((row["admitted"], row["rebound"]), (1, 1))
        self.assertEqual(row["level_token"], 100003)

    def test_rebind_rejects_origin_noted_after_the_safe_point(self):
        _, row = self.rebind_case("rebind_w", at_move=44)
        self.assertEqual((row["admitted"], row["rebound"], row["telegraph"]), (0, 0, 0))

    def test_rebind_lifetime_is_measured_from_the_bound_origin(self):
        # Published origin at move 40 has expired at 341; the newer origin
        # (move 45) is still within its lifetime, so the engine rebinds.
        _, row = self.rebind_case("rebind_w", at_move=341)
        self.assertEqual((row["admitted"], row["rebound"]), (1, 1))
        # Past the bound origin's own lifetime: expired, no rebind.
        _, row = self.rebind_case("rebind_w", at_move=346)
        self.assertEqual((row["admitted"], row["rebound"]), (0, 0))
        self.assertEqual(row["telegraph"], 0)
        self.assertEqual(row["caller_spent"], 0)

    def test_no_rebind_cases_reject_before_telegraph(self):
        cases = {
            "rebind_not_delivered": "origin_unbound",
            "rebind_wrong_family": "origin_superseded",
            "rebind_wrong_fact": "origin_superseded",
            "rebind_wrong_run": "origin_superseded",
            "stale": "origin_superseded",
        }
        for evidence, reason in cases.items():
            with self.subTest(evidence=evidence):
                folder, row = self.rebind_case(evidence)
                self.assertEqual(
                    (row["admitted"], row["rebound"], row["telegraph"]),
                    (0, 0, 0),
                )
                self.assertEqual(row["caller_spent"], 0)
                self.assertEqual(row["rejected"], 1)
                self.assertTrue(row["reasons"] & REASON_BITS[reason], row)
                rows = self.rows(folder)
                self.assertEqual([r.get("decision") for r in rows], ["rejected"], rows)
                self.assertIn(reason, rows[0]["reasons"])
                self.assertNotIn("origins", rows[0])

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

        folder = Path(track(self, tempfile.mkdtemp(prefix="nyarl-safe-mutant-")))
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


REASON_BITS = {
    "schema": 1 << 0,
    "identity": 1 << 1,
    "run_unavailable": 1 << 2,
    "level_invalid": 1 << 3,
    "budget_state": 1 << 4,
    "missed_index": 1 << 5,
    "run_mismatch": 1 << 6,
    "level_mismatch": 1 << 7,
    "origin_expired": 1 << 8,
    "origin_unbound": 1 << 9,
    "origin_superseded": 1 << 10,
    "source": 1 << 11,
    "telegraph": 1 << 12,
    "budget": 1 << 13,
    "receipt": 1 << 14,
    "internal": 1 << 15,
    "no_companion_in_view": 1 << 16,
}


class NextUseSafeRecordedDecisionTests(unittest.TestCase):
    """#177: the engine records every failing admission check, not a guess."""

    setUpClass = classmethod(NextUseSafeAdmitTests.setUpClass.__func__)
    publish = NextUseSafeAdmitTests.publish
    publish_f = NextUseSafeAdmitTests.publish_f
    run_case = NextUseSafeAdmitTests.run_case

    def receipt_bytes(self, folder):
        path = Path(folder) / "next_use-receipt.jsonl"
        return path.read_bytes() if path.exists() else None

    def decisions(self, folder):
        path = Path(folder) / "next_use-receipt.jsonl"
        if not path.exists():
            return []
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        return [row for row in rows if "next_use_decision_v" in row]

    def assert_reason(self, reason, folder=None, recorded=True, **kwargs):
        folder = folder or self.publish()
        before = self.receipt_bytes(folder)
        row = self.run_case(folder, wrapper="on_safe", **kwargs)
        self.assertEqual(row["admitted"], 0)
        self.assertEqual(row["rejected"], 1)
        self.assertTrue(row["reasons"] & REASON_BITS[reason], row)
        if not recorded:
            # Unparsed envelope or unowned transport: existing bytes untouched.
            self.assertEqual(self.receipt_bytes(folder), before)
            return None
        decisions = self.decisions(folder)
        self.assertEqual(len(decisions), 1, decisions)
        self.assertEqual(decisions[0]["decision"], "rejected")
        self.assertIn(reason, decisions[0]["reasons"])
        self.assertEqual(decisions[0]["next_use_decision_v"], 1)
        return decisions[0]

    def test_admission_writes_no_rejection_row(self):
        folder = self.publish()
        row = self.run_case(folder, wrapper="on_safe")
        self.assertEqual(row["admitted"], 1)
        self.assertEqual(row["reasons"], 0)
        self.assertEqual(self.decisions(folder), [])
        rows = (Path(folder) / "next_use-receipt.jsonl").read_text().splitlines()
        self.assertEqual([json.loads(r)["kind"] for r in rows], [2])

    def test_pending_and_empty_mailbox_write_nothing(self):
        folder = self.publish()
        row = self.run_case(folder, wrapper="on_safe", at_safe=6)
        self.assertEqual(row["pending"], 1)
        self.assertFalse((Path(folder) / "next_use-receipt.jsonl").exists())
        empty = tempfile.mkdtemp(prefix="nyarl-next-use-safe-empty-")
        os.chmod(empty, 0o700)
        row = self.run_case(empty, wrapper="on_safe")
        self.assertEqual(row["loaded"], 0)
        self.assertEqual(sorted(os.listdir(empty)), [])

    def test_unparseable_envelope_is_schema_and_writes_nothing(self):
        folder = self.publish()
        (Path(folder) / "next_use-envelope.json").write_text("{}")
        os.chmod(Path(folder) / "next_use-envelope.json", 0o600)
        self.assert_reason("schema", folder, recorded=False)

    def test_unowned_transport_is_identity_and_keeps_old_receipt(self):
        folder = self.publish()
        path = Path(folder) / "next_use-receipt.jsonl"
        path.write_bytes(b'{"next_use_private_v":1,"kind":2,"seq":2}\n')
        os.chmod(path, 0o600)
        self.assert_reason("identity", folder, recorded=False, identity=0)

    def test_run_unavailable(self):
        self.assert_reason("run_unavailable", run="none")

    def test_level_invalid(self):
        self.assert_reason("level_invalid", dlevel=0)

    def test_budget_state(self):
        self.assert_reason("budget_state", budget="invalid")

    def test_missed_index(self):
        decision = self.assert_reason("missed_index", at_safe=8)
        self.assertEqual((decision["at"], decision["safe"]), (7, 8))

    def test_run_mismatch(self):
        self.assert_reason("run_mismatch", run="cd" * 32)

    def test_level_mismatch_is_never_raised(self):
        # #200 (A): the bit stays in the row format for old receipts, but
        # admission no longer checks the origin's level.
        folder = self.publish()
        row = self.run_case(folder, wrapper="on_safe", dlevel=2, at_move=341)
        self.assertEqual(row["admitted"], 0)
        self.assertFalse(row["reasons"] & REASON_BITS["level_mismatch"], row)
        self.assertNotIn("level_mismatch", self.decisions(folder)[0]["reasons"])

    def test_origin_expired(self):
        decision = self.assert_reason("origin_expired", at_move=341)
        self.assertEqual(decision["move"], 341)

    def test_origin_unbound(self):
        self.assert_reason("origin_unbound", evidence="missing")
        self.assert_reason("origin_unbound", evidence="incomplete")

    def test_origin_superseded(self):
        self.assert_reason("origin_superseded", evidence="stale")

    # #196 (C3): a W program is admitted only with a qualifying companion on
    # screen at the safe point, checked before the telegraph and the charge.
    def test_no_companion_in_view_rejects_before_telegraph_or_charge(self):
        folder = self.publish()
        decision = self.assert_reason(
            "no_companion_in_view", folder, companion="absent"
        )
        self.assertEqual(decision["reasons"], ["no_companion_in_view"])
        row = self.run_case(self.publish(), wrapper="on_safe", companion="absent")
        self.assertEqual(row["telegraph"], 0)
        self.assertEqual(row["active"], 0)
        self.assertEqual(row["caller_spent"], row["caller_spent_before"])
        self.assertEqual(row["telegraph_spent"], -1)
        self.assertEqual(row["reasons"], REASON_BITS["no_companion_in_view"])

    def test_companion_in_view_admits_as_before(self):
        plain = self.run_case(self.publish(), wrapper="on_safe")
        seen = self.run_case(self.publish(), wrapper="on_safe", companion="present")
        self.assertEqual(seen["companion_calls"], 1)
        self.assertEqual(plain["companion_calls"], 0)
        for key in (
            "admitted",
            "active",
            "telegraph",
            "spent",
            "caller_spent",
            "reasons",
            "hunger_cost",
        ):
            self.assertEqual(seen[key], plain[key], key)
        self.assertEqual(seen["admitted"], 1)

    def test_companion_check_ignores_fountain_only_programs(self):
        row = self.run_case(
            self.publish_f(), wrapper="on_safe", evidence="valid_f", companion="absent"
        )
        self.assertEqual(row["companion_calls"], 0)
        self.assertEqual(row["admitted"], 1)

    def test_companion_check_joins_other_reasons(self):
        decision = self.assert_reason(
            "no_companion_in_view", companion="absent", evidence="stale"
        )
        self.assertEqual(
            decision["reasons"], ["origin_superseded", "no_companion_in_view"]
        )

    def test_tampered_source_digest_is_schema(self):
        folder = self.publish()
        path = Path(folder) / "next_use-envelope.json"
        payload = json.loads(path.read_text())
        payload["source"] = payload["source"] + " "
        path.write_text(json.dumps(payload, separators=(",", ":"), sort_keys=True))
        os.chmod(path, 0o600)
        self.assert_reason("schema", folder, recorded=False)

    def test_source(self):
        import hashlib

        folder = self.publish()
        path = Path(folder) / "next_use-envelope.json"
        payload = json.loads(path.read_text())
        payload["source"] = "return ("
        payload["source_sha256"] = hashlib.sha256(b"return (").hexdigest()
        path.write_text(json.dumps(payload, separators=(",", ":"), sort_keys=True))
        os.chmod(path, 0o600)
        self.assert_reason("source", folder)

    def test_telegraph(self):
        self.assert_reason("telegraph", telegraph="fail")

    def test_budget(self):
        self.assert_reason("budget", budget="empty")

    def test_receipt(self):
        self.assert_reason("receipt", receipt="fail")

    def test_all_failing_checks_are_listed(self):
        decision = self.assert_reason(
            "origin_expired", at_safe=8, at_move=341, dlevel=2
        )
        self.assertEqual(decision["reasons"], ["missed_index", "origin_expired"])
