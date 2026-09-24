"""ENGINE-UNIT: bounded next-use snapshot. Not save/restore."""

import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class NextUseSnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = tempfile.TemporaryDirectory(prefix="nyarl-next-use-snapshot-")
        cls.addClassCleanup(cls.build.cleanup)
        cls.binary = Path(cls.build.name) / "next-use-snapshot"
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
            str(ROOT / "tests/chaos/next_use_snapshot.c"),
            str(ROOT / "src/chaos_next_use.c"),
            str(ROOT / "src/chaos_next_use_admission.c"),
            str(ROOT / "src/chaos_next_use_runtime.c"),
            str(ROOT / "src/chaos_protocol.c"),
            str(ROOT / "src/chaos_lua.c"),
            str(ROOT / "src/chaos_next_use_safe.c"),
            str(ROOT / "src/chaos_next_use_io.c"),
            str(ROOT / "src/chaos_next_use_journal.c"),
            "-Wl,--gc-sections",
            *flags,
            "-lm",
            "-o",
            str(cls.binary),
        ]
        result = subprocess.run(command, capture_output=True, timeout=30)
        if result.returncode:
            raise RuntimeError(result.stderr.decode())
        # Execute the actual native reader/decoder, not the unit mread double.
        # Same extracted-production approach as test_restore_safety; unrelated
        # restore graph and platform cleanup are deliberately not linked here.
        source = (ROOT / "src/restore.c").read_text()
        reader = Path(cls.build.name) / "native-read.c"
        reader.write_text(
            '#include "hack.h"\n#include "chaos_next_use.h"\n#include <errno.h>\n'
            "ssize_t chaos_test_native_read(int, void *, size_t);\n"
            "#define read chaos_test_native_read\n"
            + source[source.index("#ifdef ZEROCOMP\n#define RLESC") :]
        )
        cls.native_binaries = {}
        for zerocomp in (False, True):
            binary = Path(cls.build.name) / f"native-read-{int(zerocomp)}"
            native_command = command[:-2] + [
                "-DNYARL_TEST_NATIVE_READS",
                *(["-DZEROCOMP"] if zerocomp else []),
                str(reader),
                "-o",
                str(binary),
            ]
            result = subprocess.run(native_command, capture_output=True, timeout=30)
            if result.returncode:
                raise RuntimeError(result.stderr.decode())
            cls.native_binaries[zerocomp] = binary

    def test_native_truncation_preserves_bytes_and_live_runtime(self):
        for zerocomp, binary in self.native_binaries.items():
            for state in ("present", "empty"):
                with self.subTest(zerocomp=zerocomp, state=state):
                    result = subprocess.run(
                        [str(binary), "native_truncation", state],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    self.assertEqual(
                        result.returncode, 0, result.stdout + result.stderr
                    )
                    row = json.loads(result.stdout)
                    self.assertGreater(row["truncated"], 4)
                    self.assertEqual(row["positive"], 1)
                    self.assertEqual(row["preserved"], 1)

    def test_native_read_errors_and_shared_decoder_state(self):
        for zerocomp, binary in self.native_binaries.items():
            for mode, expected in (
                ("native_read_error", {"errors_rejected": 1, "unchanged": 1}),
                ("native_interrupted_short_reads", {"interrupted_short_reads": 1}),
                ("native_decoder_state", {"shared_decoder": 1, "fresh_stream": 1}),
            ):
                with self.subTest(zerocomp=zerocomp, mode=mode):
                    result = subprocess.run(
                        [str(binary), mode], capture_output=True, text=True, timeout=10
                    )
                    self.assertEqual(
                        result.returncode, 0, result.stdout + result.stderr
                    )
                    self.assertEqual(json.loads(result.stdout), expected)

    def run_mode(self, mode, *args):
        result = subprocess.run(
            [str(self.binary), mode, *map(str, args)],
            capture_output=True,
            text=True,
            timeout=5,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return [json.loads(line) for line in result.stdout.splitlines() if line]

    def test_legacy_snapshot_cannot_invent_a_witness(self):
        row = self.run_mode("legacy_no_invented_witness")[0]
        self.assertEqual(row, {"tag": "legacy", "read": 0, "unchanged": 1})

    def test_failed_restore_preserves_live_program(self):
        row = self.run_mode("restore_error_is_atomic")[0]
        self.assertEqual(row["restored"], 0)
        self.assertEqual(row["exported"], 1)
        self.assertEqual(row["unchanged"], 1)

    def test_binding_digest_has_independent_literal_encoding(self):
        source_hash = hashlib.sha256(b"return 0").hexdigest()
        literal = f"next-use-bind-v1|1|{source_hash}|40|140|0|1|1|10|110|0|0".encode()
        self.assertEqual(
            self.run_mode("binding_digest")[-1]["binding_sha256"],
            hashlib.sha256(literal).hexdigest(),
        )

    def test_unbound_import_does_not_execute_a_callback(self):
        self.assertEqual(
            self.run_mode("unbound_import_cannot_execute")[0]["unchanged"], 1
        )

    def test_restore_checks_independent_game_identity_before_publication(self):
        row = self.run_mode("wrong_trusted_restore_identity")[0]
        self.assertEqual(row, {"rejected": 1, "unchanged": 1})

    def test_wide_identity_roundtrip_without_narrowing(self):
        self.assertEqual(
            self.run_mode("wide_identity_roundtrip")[-1]["wide_identity_preserved"], 1
        )

    def test_consumed_family_cannot_be_swapped_to_resurrect_it(self):
        self.assertEqual(self.run_mode("family_progress_cannot_swap")[0]["valid"], 0)

    def test_inflight_save_does_not_overwrite_previous_bytes(self):
        row = self.run_mode("inflight_save_refuses_before_write")[0]
        self.assertEqual(row["preserved"], 1)

    @staticmethod
    def binding_digest(**changes):
        # Independent wire grammar, never call the engine binding helper.
        values = dict(
            program_id=1,
            source_sha256=hashlib.sha256(b"return 0").hexdigest(),
            admission_move=40,
            program_expiry=140,
            variant=0,
            run_token=1,
            level_token=1,
            origin_w=10,
            origin_w_deadline=110,
            origin_f=0,
            origin_f_deadline=0,
        )
        values.update({key: value for key, value in changes.items() if key in values})
        literal = "next-use-bind-v1|" + "|".join(map(str, values.values()))
        return hashlib.sha256(literal.encode()).hexdigest()

    def test_invalid_phase_boolean_clock_and_width_semantics(self):
        cases = [
            ("phase", 0),
            ("phase", 99),
            ("phase", 4),
            ("origin_w_live", 2),
            ("origin_f_live", -1),
            ("run_token", 0),
            ("level_token", -1),
            ("program_expiry", 139),
            ("program_expiry", 141),
            ("origin_w", 2147483648),
            ("origin_w_deadline", 2147483648),
            ("activation_monstermoves", 2147483648),
            ("armed_root", 2147483648),
            ("replay_cursor", 2147483648),
            ("next_seq", 0),
            ("termination_emitted", 1),
            ("identity_unsafe", 2),
            ("last_root", -1),
            ("witnessed", 1),
            ("attention_claimed", 1),
            ("delay_until", -1),
            ("origin_f", 20),
            ("slot_w", 0),
        ]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                row = self.run_mode(
                    "snapshot_change",
                    field,
                    value,
                    self.binding_digest(**{field: value}),
                )[-1]
                self.assertEqual(row, {"validated": 0, "imported": 0, "unchanged": 1})

    def test_binding_integrity_is_separate_from_valid_value_semantics(self):
        for field, value in (
            ("origin_w", 11),
            ("origin_w_deadline", 111),
            ("run_token", 2),
            ("level_token", 2),
        ):
            with self.subTest(field=field):
                row = self.run_mode("snapshot_change", field, value, "original")[-1]
                self.assertEqual(row, {"validated": 0, "imported": 0, "unchanged": 1})
                # Positive controls prove the independent digest is accepted;
                # these values are legal in a differently bound snapshot.
                row = self.run_mode(
                    "snapshot_change",
                    field,
                    value,
                    self.binding_digest(**{field: value}),
                )[-1]
                self.assertEqual(row, {"validated": 1, "imported": 1, "unchanged": 0})

    def test_terminal_history_restores_after_departure(self):
        for state in ("pending", "armed", "completed"):
            with self.subTest(state=state):
                self.assertEqual(
                    self.run_mode("departure_roundtrip", state)[0],
                    {
                        "restored": 1,
                        "unchanged": 1,
                        "identity_rejections": 4,
                        "records": 0,
                    },
                )

    def test_active_foreign_level_restore_is_atomic_rejection(self):
        self.assertEqual(
            self.run_mode("active_foreign_level")[0], {"rejected": 1, "unchanged": 1}
        )

    def test_armed_and_ended_capture_metadata_cannot_be_erased(self):
        # 0 is still armed; 1..7 exercise every native end reason.
        for reason in range(8):
            with self.subTest(reason=reason):
                self.assertEqual(
                    self.run_mode("capture_metadata", reason)[0],
                    {"rejected": 6, "total": 6, "unchanged": 1},
                )

    def test_continuation_does_not_restart_private_sequence(self):
        row = self.run_mode("sequence_continuation")[0]
        self.assertEqual(row["after_seq"], row["before_seq"] + 1)

    def test_claimed_undelivered_attention_is_not_regained(self):
        row = self.run_mode("claimed_roundtrip")[0]
        self.assertEqual(row, {"claimed": 1, "ready": 0, "witnessed": 0})

    def test_roundtrip_pending_does_not_readmit(self):
        rows = self.run_mode("roundtrip")
        self.assertEqual(rows[0]["ok"], 1)
        self.assertEqual(rows[0]["slot_w"], 1)
        self.assertEqual(rows[1]["ok"], 0)
        self.assertEqual(rows[2]["ok"], 1)
        self.assertEqual(rows[2]["program_id"], rows[0]["program_id"])
        self.assertEqual(rows[2]["slot_w"], rows[0]["slot_w"])
        self.assertEqual(rows[2]["sha"], rows[0]["sha"])
        self.assertEqual(rows[2]["source_len"], rows[0]["source_len"])

    def test_bad_version_does_not_overwrite_live(self):
        rows = self.run_mode("bad_version")
        self.assertEqual(rows[-1]["validated"], 0)
        self.assertEqual(rows[-1]["imported"], 0)
        self.assertEqual(rows[-1]["live_program"], 1)

    def test_digest_mismatch_does_not_overwrite_live(self):
        rows = self.run_mode("digest_mismatch")
        self.assertEqual(rows[-1]["validated"], 0)
        self.assertEqual(rows[-1]["imported"], 0)
        self.assertEqual(rows[-1]["live_program"], 1)

    def test_consumed_invalid_roundtrip_cannot_revive(self):
        rows = self.run_mode("consumed_invalid")
        after = next(row for row in rows if row["tag"] == "after_invalid")
        imported = next(row for row in rows if row["tag"] == "imported_invalid")
        resurrect = next(row for row in rows if row["tag"] == "resurrect")
        self.assertEqual(after["slot_w"], 5)
        self.assertEqual(imported["slot_w"], 5)
        self.assertEqual(imported["sha"], after["sha"])
        self.assertEqual(resurrect["validated"], 0)

    def test_roundtrip_pending_f(self):
        rows = self.run_mode("roundtrip_f")
        after = next(row for row in rows if row["tag"] == "after_install_f")
        imported = next(row for row in rows if row["tag"] == "after_import_f")
        self.assertEqual(after["slot_w"], 0)
        self.assertEqual(after["slot_f"], 1)
        self.assertEqual(imported["slot_f"], 1)
        self.assertEqual(imported["slot_w"], 0)
        self.assertEqual(imported["sha"], after["sha"])

    def test_file_bytes_roundtrip(self):
        rows = self.run_mode("file")
        after = next(row for row in rows if row["tag"] == "after_file")
        self.assertEqual(after["ok"], 1)
        self.assertEqual(after["slot_w"], 1)

    def test_quiet_roundtrip(self):
        rows = self.run_mode("quiet")
        after = next(row for row in rows if row["tag"] == "imported_quiet")
        self.assertEqual(after["ok"], 1)
        self.assertEqual(after["slot_w"], 3)

    def test_save_restore_quiet(self):
        rows = self.run_mode("save_quiet")
        after = next(row for row in rows if row["tag"] == "after_save_quiet")
        self.assertEqual(after["ok"], 1)
        self.assertEqual(after["slot_w"], 3)

    def test_save_restore_delay(self):
        rows = self.run_mode("save_delay")
        after = next(row for row in rows if row["tag"] == "after_save_delay")
        self.assertEqual(after["ok"], 1)
        self.assertEqual(after["slot_w"], 4)

    def test_delay_roundtrip(self):
        rows = self.run_mode("delay")
        after = next(row for row in rows if row["tag"] == "imported_delay")
        self.assertEqual(after["ok"], 1)
        self.assertEqual(after["slot_w"], 4)

    def test_armed_roundtrip(self):
        rows = self.run_mode("armed")
        after = next(row for row in rows if row["tag"] == "imported_armed")
        self.assertEqual(after["ok"], 1)
        self.assertEqual(after["slot_w"], 2)

    def test_expired_roundtrip(self):
        rows = self.run_mode("expired")
        after = next(row for row in rows if row["tag"] == "imported_expiry")
        self.assertEqual(after["ok"], 1)
        self.assertEqual(after["slot_w"], 7)

    def test_save_restore_expiry(self):
        rows = self.run_mode("save_expiry")
        after = next(row for row in rows if row["tag"] == "after_save_expiry")
        self.assertEqual(after["ok"], 1)
        self.assertEqual(after["slot_w"], 7)

    def test_save_restore_does_not_readmit(self):
        rows = self.run_mode("save_restore")
        after = next(row for row in rows if row["tag"] == "after_save_restore")
        self.assertEqual(after["ok"], 1)
        self.assertEqual(after["slot_w"], 1)

    def test_save_restore_pending_f(self):
        rows = self.run_mode("save_restore_f")
        after = next(row for row in rows if row["tag"] == "after_save_restore_f")
        self.assertEqual(after["ok"], 1)
        self.assertEqual(after["slot_f"], 1)
        self.assertEqual(after["slot_w"], 0)

    def test_empty_save_restores_without_program(self):
        rows = self.run_mode("empty_save")
        after = next(row for row in rows if row["tag"] == "empty_save")
        self.assertEqual(after["restored"], 1)
        self.assertEqual(after["exported"], 0)

    def test_restore_wrong_level_terminates(self):
        rows = self.run_mode("restore_level")
        after = next(row for row in rows if row["tag"] == "after_level")
        self.assertEqual(after["ok"], 1)
        self.assertEqual(after["slot_w"], 8)

    def test_restore_missing_origin_terminates(self):
        rows = self.run_mode("restore_origin")
        after = next(row for row in rows if row["tag"] == "after_origin")
        self.assertEqual(after["ok"], 1)
        self.assertEqual(after["slot_w"], 7)

    def test_restore_wrong_run_terminates(self):
        rows = self.run_mode("restore_run")
        after = next(row for row in rows if row["tag"] == "after_run")
        self.assertEqual(after["ok"], 1)
        self.assertEqual(after["slot_w"], 7)

    def test_restore_settles_candidate_latch(self):
        rows = self.run_mode("restore_latch")
        after = next(row for row in rows if row["tag"] == "restore_latch")
        self.assertEqual(after["restored"], 1)
        self.assertEqual(after["admitted"], 2)
        self.assertEqual(after["safe_admitted"], 0)
        self.assertEqual(after["slot_w"], 1)

    def test_restore_armed_does_not_rebind_companion(self):
        rows = self.run_mode("restore_armed")
        after = next(row for row in rows if row["tag"] == "after_rebind")
        window = next(row for row in rows if row["tag"] == "armed_window")
        self.assertEqual(after["ok"], 1)
        self.assertEqual(after["slot_w"], 2)
        self.assertEqual(after["armed_m_id"], 7)
        self.assertEqual(window["ready"], 1)
        self.assertEqual(window["wrong"], 0)
        self.assertEqual(window["activation"], 40)

    def test_partial_wf_save_keeps_the_other_slot(self):
        rows = self.run_mode("partial_wf")
        after = next(row for row in rows if row["tag"] == "after_w_used")
        restored = next(row for row in rows if row["tag"] == "after_partial_restore")
        detail = next(row for row in rows if row["tag"] == "partial_wf")
        self.assertEqual(after["ok"], 1)
        self.assertEqual(after["slot_w"], 3)
        self.assertEqual(after["slot_f"], 1)
        self.assertEqual(restored["ok"], 1)
        self.assertEqual(restored["slot_f"], 1)
        self.assertEqual(detail["callback"], 1)
        self.assertEqual(detail["run"], 9)
        self.assertEqual(detail["level"], 4)
        self.assertEqual(detail["whistles"], 1)
        self.assertEqual(detail["fountains"], 1)
        self.assertEqual(detail["attention"], 0)

    def test_partial_fw_save_keeps_the_other_slot(self):
        rows = self.run_mode("partial_fw")
        restored = next(row for row in rows if row["tag"] == "after_partial_restore")
        detail = next(row for row in rows if row["tag"] == "partial_fw")
        self.assertEqual(restored["ok"], 1)
        self.assertEqual(restored["slot_w"], 1)
        self.assertEqual(restored["slot_f"], 4)
        self.assertEqual(detail["callback"], 1)


if __name__ == "__main__":
    unittest.main()
