"""ENGINE-UNIT: ring (W effect) runtime after real admit/install.

Each case publishes a real envelope with chaos.next_use_envelope (ring=True:
next_use_program_v 4, w_effect "ring"), admits it through the safe layer and
drives the runtime's public entry points as chaos_engine.c's ring branch does.
The engine's guard reads are not linked; each scenario passes the guard value
the engine would. C's broad fixture (test_next_use_broad.py) is the v3 control.
"""

from pathlib import Path
from unittest import mock
import json
import os
import subprocess
import tempfile
import unittest

from chaos import next_use_envelope
from chaos.next_use_envelope import BROAD_USES, publish_envelope

ROOT = Path(__file__).resolve().parents[2]
CALLBACKS = 8  # CHAOS_NEXT_USE_BROAD_CALLBACKS
GUARDS = range(1, 9)  # enum chaos_next_use_ring_guard, CONFUSED..WATER_ADJACENT
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
COMMITTED, TERMINATED = 3, 4  # enum chaos_next_use_attempt_phase
SLOT_W_CONSUMED_SUPPRESSED = 6  # enum chaos_next_use_slot_w
SLOT_W_CONSUMED_RANG = 10
NOT_TAKEN, CALLBACK_ONLY, RANG = 0, 1, 2  # fixture ring() result


class RingEnvelopeTests(unittest.TestCase):
    """Director side only: what a ring run writes."""

    def test_w_row_becomes_a_v4_ring_program(self):
        envelope, _ = next_use_envelope.envelope_from_selection(
            ROW, HOST, repair=True, broad=True, ring=True
        )
        self.assertEqual(envelope["next_use_program_v"], 4)
        self.assertEqual(envelope["w_effect"], "ring")
        self.assertEqual(envelope["telegraph"], "next-use-v4-Wr")
        self.assertEqual(envelope["uses"], BROAD_USES)
        self.assertIn(b'op="whistle_ring"', envelope["source"].encode())

    def test_f_row_is_written_exactly_as_under_c(self):
        row = dict(ROW, family="F", op="fountain_refresh")
        row["origin"] = dict(ROW["origin"], fact="water_refreshed")
        ring, _ = next_use_envelope.envelope_from_selection(
            row, HOST, repair=True, broad=True, ring=True
        )
        broad, _ = next_use_envelope.envelope_from_selection(
            row, HOST, repair=True, broad=True
        )
        self.assertEqual(ring, broad)

    def test_c_run_is_unchanged(self):
        envelope, _ = next_use_envelope.envelope_from_selection(
            ROW, HOST, repair=True, broad=True
        )
        self.assertEqual(envelope["next_use_program_v"], 3)
        self.assertNotIn("w_effect", envelope)
        self.assertIn(b'op="whistle_attention"', envelope["source"].encode())

    def test_ring_needs_broad(self):
        with self.assertRaises(ValueError):
            next_use_envelope.envelope_from_selection(
                ROW, HOST, repair=True, broad=False, ring=True
            )
        with self.assertRaises(ValueError):
            next_use_envelope.envelope_from_selection(
                ROW, HOST, repair=True, broad=True, ring=1
            )


class NextUseRingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = tempfile.TemporaryDirectory(prefix="nyarl-next-use-ring-")
        cls.addClassCleanup(cls.build.cleanup)
        cls.binary = Path(cls.build.name) / "next-use-ring"
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
            str(ROOT / "tests/chaos/next_use_ring.c"),
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
        result = subprocess.run(command, capture_output=True, timeout=60)
        if result.returncode:
            raise RuntimeError(result.stderr.decode())

    def run_case(self, scenario, ring=True, journal=False, source_ring=None):
        """source_ring overrides the composed source (mismatch cases only)."""
        folder = tempfile.mkdtemp(prefix="nyarl-next-use-ring-run-")
        self.addCleanup(lambda: subprocess.run(["rm", "-rf", folder], check=False))
        os.chmod(folder, 0o700)
        if source_ring is None:
            publish_envelope(folder, ROW, HOST, repair=True, broad=True, ring=ring)
        else:
            real = next_use_envelope.compose
            with mock.patch.object(
                next_use_envelope,
                "compose",
                lambda row, ring=False: real(row, ring=source_ring),
            ):
                publish_envelope(folder, ROW, HOST, repair=True, broad=True, ring=ring)
        env = dict(os.environ)
        if journal:
            env["NYARL_RING_JOURNAL"] = "1"
        p = subprocess.run(
            [str(self.binary), folder, "40", "7", HOST["run"], scenario],
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
            stdin=subprocess.DEVNULL,
        )
        self.folder = Path(folder)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        rows = [json.loads(line) for line in p.stdout.splitlines() if line]
        admit = rows[0]
        return admit, {r["step"]: r for r in rows[1:]}, rows[1:]

    def journal(self):
        from chaos.next_use_journal import read_journal

        (path,) = self.folder.glob("next_use-journal*.jsonl")
        return path, read_journal(path)

    def test_ring_envelope_admits_as_v8_with_its_telegraph(self):
        admit, steps, _ = self.run_case("deliver")
        self.assertEqual(admit["result"], 1)
        self.assertEqual(admit["telegraphs"], 1)
        self.assertEqual(admit["telegraph"], "next-use-v4-Wr")
        installed = steps["installed"]
        self.assertEqual(installed["snapshot_v"], 8)
        self.assertEqual(installed["w_effect"], 1)
        self.assertEqual(installed["broad_uses"], BROAD_USES)
        self.assertEqual(installed["ring_active"], 1)
        self.assertEqual(installed["broad_active"], 1)

    def test_c_control_is_not_ring(self):
        admit, steps, _ = self.run_case("callback", ring=False)
        self.assertEqual(admit["telegraph"], "next-use-v3-W")
        self.assertEqual(steps["installed"]["snapshot_v"], 7)
        self.assertEqual(steps["installed"]["ring_active"], 0)

    def test_two_rings_reach_the_cap(self):
        _, steps, _ = self.run_case("deliver")
        self.assertEqual(steps["use1"]["result"], RANG)
        self.assertEqual(steps["use1"]["delivered"], 1)
        self.assertEqual(steps["use1"]["slot_w"], SLOT_W_CONSUMED_RANG)
        self.assertEqual(steps["use1"]["phase"], COMMITTED)
        self.assertEqual(steps["use2"]["result"], RANG)
        self.assertEqual(steps["use2"]["delivered"], 2)
        self.assertEqual(steps["use2"]["phase"], TERMINATED)
        self.assertEqual(steps["use3"]["result"], NOT_TAKEN)
        self.assertEqual(steps["use3"]["callbacks"], 2)

    def test_every_guard_holds_and_keeps_the_program_waiting(self):
        _, steps, rows = self.run_case("guards")
        self.assertEqual(len(rows), 1 + len(GUARDS))
        for guard in GUARDS:
            with self.subTest(guard=guard):
                step = steps[f"guard{guard}"]
                self.assertEqual(step["result"], CALLBACK_ONLY)
                self.assertEqual(step["delivered"], 0)
                self.assertEqual(step["slot_w"], SLOT_W_CONSUMED_SUPPRESSED)
                self.assertEqual(step["callbacks"], guard)
                # The eighth guarded use is also the eighth callback: the
                # bound ends the program there, never a guard.
                self.assertEqual(
                    step["phase"], TERMINATED if guard == CALLBACKS else COMMITTED
                )

    def test_guarded_use_spends_no_cap(self):
        _, steps, _ = self.run_case("guard-then-ring")
        self.assertEqual(
            [steps[s]["result"] for s in ("g1", "r1", "g2", "r2", "after")],
            [CALLBACK_ONLY, RANG, CALLBACK_ONLY, RANG, NOT_TAKEN],
        )
        self.assertEqual(steps["r1"]["delivered"], 1)
        self.assertEqual(steps["g2"]["delivered"], 1)
        self.assertEqual(steps["g2"]["phase"], COMMITTED)
        self.assertEqual(steps["r2"]["delivered"], 2)
        self.assertEqual(steps["r2"]["phase"], TERMINATED)
        self.assertEqual(steps["r2"]["callbacks"], 4)

    def test_guarded_uses_stop_at_the_callback_bound(self):
        _, _, rows = self.run_case("guarded-bound")
        uses = rows[1:]
        self.assertEqual([r["result"] for r in uses], [1] * CALLBACKS + [0])
        self.assertTrue(all(r["phase"] == COMMITTED for r in uses[: CALLBACKS - 1]))
        self.assertEqual(uses[CALLBACKS - 1]["phase"], TERMINATED)
        self.assertTrue(all(r["delivered"] == 0 for r in uses))

    def test_ring_answer_refuses_bad_guards_and_roots(self):
        _, steps, _ = self.run_case("bad-guard")
        self.assertEqual(steps["callback"]["result"], 1)
        for step in ("guard-high", "guard-negative", "wrong-root"):
            with self.subTest(step=step):
                self.assertEqual(steps[step]["result"], 0)
                self.assertEqual(steps[step]["delivered"], 0)
        self.assertEqual(steps["right-root"]["result"], 1)
        self.assertEqual(steps["right-root"]["delivered"], 1)
        # One answer per callback.
        self.assertEqual(steps["repeat"]["result"], 0)
        self.assertEqual(steps["repeat"]["delivered"], 1)

    def test_intent_must_match_the_loaded_effect(self):
        # v4 ring program whose source returns whistle_attention.
        admit, steps, _ = self.run_case("callback", ring=True, source_ring=False)
        self.assertEqual(admit["result"], 1)
        self.assertEqual(steps["callback"]["phase"], TERMINATED)
        self.assertEqual(steps["callback"]["delivered"], 0)
        # v3 (C) program whose source returns whistle_ring.
        admit, steps, _ = self.run_case("callback", ring=False, source_ring=True)
        self.assertEqual(admit["result"], 1)
        self.assertEqual(steps["callback"]["phase"], TERMINATED)
        self.assertEqual(steps["callback"]["delivered"], 0)

    def test_matching_intent_leaves_a_ring_answer_pending(self):
        _, steps, _ = self.run_case("callback")
        self.assertEqual(steps["callback"]["result"], 1)
        self.assertEqual(steps["callback"]["phase"], COMMITTED)

    def test_ring_program_survives_a_level_change(self):
        _, steps, _ = self.run_case("level")
        self.assertEqual(steps["level2"]["phase"], COMMITTED)
        self.assertEqual(steps["level2-use"]["result"], RANG)

    def test_program_expiry_still_applies(self):
        _, steps, _ = self.run_case("expiry")
        self.assertEqual(steps["expired"]["phase"], TERMINATED)

    def test_save_restore_keeps_ring_and_resumes_the_journal(self):
        _, steps, _ = self.run_case("restore", journal=True)
        self.assertEqual(steps["use1"]["result"], RANG)
        self.assertEqual(steps["restored"]["result"], 1)
        self.assertEqual(steps["restored"]["snapshot_v"], 8)
        self.assertEqual(steps["restored"]["w_effect"], 1)
        self.assertEqual(steps["restored"]["ring_active"], 1)
        self.assertEqual(steps["restored"]["delivered"], 1)
        self.assertEqual(steps["resumed"]["result"], 1)
        self.assertEqual(steps["use2"]["result"], RANG)
        self.assertEqual(steps["use2"]["phase"], TERMINATED)
        _, trace = self.journal()
        self.assertTrue(trace["structurally_complete"])

    def test_ring_saved_on_a_deeper_level_restores_live(self):
        """#239 on v8: ring, descend, save, restore on the deeper level."""
        _, steps, _ = self.run_case("restore-level", journal=True)
        self.assertEqual(steps["use1"]["result"], RANG)
        # A ring program never arms a level-bound W window.
        self.assertEqual(steps["window"]["w_runtime"], 0)
        self.assertEqual(steps["window"]["armed_level_token"], 0)
        self.assertEqual(steps["window"]["level_token"], 100001)
        self.assertEqual(steps["descended"]["phase"], COMMITTED)
        self.assertEqual(steps["wrong-run"]["result"], 0)
        self.assertEqual(steps["restored"]["result"], 1)
        self.assertEqual(steps["restored"]["phase"], COMMITTED)
        self.assertEqual(steps["restored"]["snapshot_v"], 8)
        self.assertEqual(steps["restored"]["ring_active"], 1)
        self.assertEqual(steps["restored"]["delivered"], 1)
        self.assertEqual(steps["resumed"]["result"], 1)
        self.assertEqual(steps["use2"]["result"], RANG)
        self.assertEqual(steps["use2"]["delivered"], 2)
        self.assertEqual(steps["use2"]["phase"], TERMINATED)
        _, trace = self.journal()
        self.assertTrue(trace["structurally_complete"])

    def test_c_save_restore_still_restores_as_v7(self):
        _, steps, _ = self.run_case("restore", ring=False)
        self.assertEqual(steps["restored"]["result"], 1)
        self.assertEqual(steps["restored"]["snapshot_v"], 7)
        self.assertEqual(steps["restored"]["ring_active"], 0)

    def test_tampered_ring_snapshot_is_refused(self):
        _, steps, _ = self.run_case("tamper")
        self.assertEqual(steps["untampered"]["result"], 1)
        for step in (
            "tamper-effect",
            "tamper-version-v7",
            "tamper-version-v6",
            "tamper-uses",
        ):
            with self.subTest(step=step):
                self.assertEqual(steps[step]["result"], 0)

    def test_reader_accepts_ring_journals(self):
        for scenario in (
            "deliver",
            "guards",
            "guard-then-ring",
            "guarded-bound",
            "level",
            "expiry",
        ):
            with self.subTest(scenario=scenario):
                self.run_case(scenario, journal=True)
                _, trace = self.journal()
                header = trace["records"][0]["data"]["snapshot"]
                self.assertEqual(header["snapshot_v"], 8)
                self.assertEqual(header["w_effect"], 1)

    def test_reader_records_each_guard(self):
        self.run_case("guards", journal=True)
        _, trace = self.journal()
        rows = [
            p["data"]
            for r in trace["records"]
            if r["kind"] == "transition"
            for p in r["data"]["private_records"]
            if p["kind"] == 4 and p["data"]["family"] == 1  # W effect rows
        ]
        self.assertEqual([d["outcome"] for d in rows], [14] * len(GUARDS))
        self.assertEqual([d["suppression"] for d in rows], list(GUARDS))


if __name__ == "__main__":
    unittest.main()
