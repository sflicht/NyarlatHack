"""ENGINE-UNIT: C (broad next-use) runtime after real admit/install.

Each case publishes a real envelope with chaos.next_use_envelope, admits it
through the safe layer and drives the runtime's public entry points. A v2
(single-use) envelope is the control: its rules must not change.
"""

from pathlib import Path
import json
import os
import subprocess
import tempfile
import unittest

from chaos.next_use_envelope import BROAD_USES, publish_envelope

ROOT = Path(__file__).resolve().parents[2]
CALLBACKS = 8  # CHAOS_NEXT_USE_BROAD_CALLBACKS
ROWS = {
    "W": {
        "family": "W",
        "op": "whistle_attention",
        "origin": {
            "root_seq": 10,
            "notice_seq": 11,
            "end_seq": 12,
            "fact": "sound_high",
        },
    },
    "F": {
        "family": "F",
        "op": "fountain_refresh",
        "origin": {
            "root_seq": 10,
            "notice_seq": 11,
            "end_seq": 12,
            "fact": "water_refreshed",
        },
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


class NextUseBroadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = tempfile.TemporaryDirectory(prefix="nyarl-next-use-broad-")
        cls.addClassCleanup(cls.build.cleanup)
        cls.binary = Path(cls.build.name) / "next-use-broad"
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
            str(ROOT / "tests/chaos/next_use_broad.c"),
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

    def run_case(self, family, scenario, broad=True):
        folder = tempfile.mkdtemp(prefix="nyarl-next-use-broad-run-")
        self.addCleanup(lambda: subprocess.run(["rm", "-rf", folder], check=False))
        os.chmod(folder, 0o700)
        publish_envelope(folder, ROWS[family], HOST, repair=True, broad=broad)
        p = subprocess.run(
            [str(self.binary), folder, "40", "7", HOST["run"], family, scenario],
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        rows = [json.loads(line) for line in p.stdout.splitlines() if line]
        admit = rows[0]
        self.assertEqual(admit["result"], 1, rows)
        return admit, {r["step"]: r for r in rows[1:]}, rows[1:]

    def test_broad_telegraph_and_snapshot_version(self):
        for family in "WF":
            with self.subTest(family=family):
                admit, steps, _ = self.run_case(family, "none")
                self.assertEqual(admit["telegraphs"], 1)
                self.assertEqual(admit["telegraph"], f"next-use-v3-{family}")
                self.assertEqual(steps["installed"]["snapshot_v"], 7)
                self.assertEqual(steps["installed"]["broad_uses"], BROAD_USES)
                self.assertEqual(steps["installed"]["broad_active"], 1)

    def test_single_use_control_keeps_v6_and_old_telegraph(self):
        admit, steps, _ = self.run_case("W", "none", broad=False)
        self.assertEqual(admit["telegraph"], "next-use-v2-W")
        self.assertEqual(steps["installed"]["snapshot_v"], 6)
        self.assertEqual(steps["installed"]["broad_uses"], 0)
        self.assertEqual(steps["installed"]["broad_active"], 0)

    def test_repeat_uses_deliver_up_to_the_declared_bound(self):
        for family in "WF":
            with self.subTest(family=family):
                _, steps, _ = self.run_case(family, "repeat")
                self.assertEqual(steps["use1"]["result"], 1)
                self.assertEqual(steps["use1"]["delivered"], 1)
                self.assertEqual(steps["use1"]["phase"], COMMITTED)
                self.assertEqual(steps["use2"]["result"], 1)
                self.assertEqual(steps["use2"]["delivered"], 2)
                # Bound reached between uses: COMPLETED, no third callback.
                self.assertEqual(steps["use2"]["phase"], TERMINATED)
                self.assertEqual(steps["use3"]["result"], 0)
                self.assertEqual(steps["use3"]["callbacks"], 2)

    def test_single_use_control_answers_one_use(self):
        _, steps, _ = self.run_case("F", "repeat", broad=False)
        self.assertEqual(steps["use1"]["result"], 1)
        self.assertEqual(steps["use1"]["phase"], TERMINATED)
        self.assertEqual(steps["use2"]["result"], 0)

    def test_undelivered_uses_stop_at_the_callback_bound(self):
        _, _, rows = self.run_case("F", "quiet-uses")
        self.assertEqual([r["result"] for r in rows[1:]], [1] * CALLBACKS + [0])
        self.assertEqual(rows[CALLBACKS - 1 + 1]["phase"], TERMINATED)
        self.assertTrue(all(r["phase"] == COMMITTED for r in rows[1:CALLBACKS]))
        self.assertTrue(all(r["delivered"] == 0 for r in rows[1:]))

    def test_broad_program_survives_a_level_change(self):
        for family in "WF":
            with self.subTest(family=family):
                _, steps, _ = self.run_case(family, "level")
                self.assertEqual(steps["level2"]["phase"], COMMITTED)
                self.assertEqual(steps["level2-use"]["result"], 1)
                self.assertEqual(steps["level2-use"]["delivered"], 1)

    def test_single_use_control_ends_on_level_change(self):
        _, steps, _ = self.run_case("W", "level", broad=False)
        self.assertEqual(steps["level2"]["phase"], TERMINATED)
        self.assertEqual(steps["level2-use"]["result"], 0)

    def test_open_window_ends_on_leaving_its_level_program_lives(self):
        _, steps, _ = self.run_case("W", "level-window")
        self.assertEqual(steps["window-left-level"]["result"], 1)
        self.assertEqual(steps["window-left-level"]["phase"], COMMITTED)
        self.assertEqual(steps["window-left-level"]["delivered"], 0)
        self.assertEqual(steps["next-level-use"]["result"], 1)
        self.assertEqual(steps["next-level-use"]["delivered"], 1)

    def test_suppressed_whistle_consumes_nothing(self):
        _, steps, _ = self.run_case("W", "suppressed")
        self.assertEqual(steps["suppressed"]["phase"], COMMITTED)
        self.assertEqual(steps["suppressed"]["callbacks"], 0)
        # Nothing is written either: a broad program may see many suppressed
        # whistles, and its private record bound counts only callbacks.
        self.assertEqual(steps["suppressed"]["private"], steps["installed"]["private"])
        self.assertEqual(steps["suppressed"]["slot_w"], steps["installed"]["slot_w"])
        self.assertEqual(steps["suppressed"]["result"], 1)  # still open
        self.assertEqual(steps["after-suppressed"]["result"], 1)
        self.assertEqual(steps["after-suppressed"]["delivered"], 1)

    def test_single_use_control_suppression_consumes_the_program(self):
        _, steps, _ = self.run_case("W", "suppressed", broad=False)
        self.assertEqual(steps["suppressed"]["phase"], TERMINATED)
        self.assertEqual(steps["after-suppressed"]["result"], 0)

    def test_program_expiry_still_applies(self):
        for family in "WF":
            with self.subTest(family=family):
                _, steps, _ = self.run_case(family, "expiry")
                self.assertEqual(steps["expired"]["phase"], TERMINATED)


if __name__ == "__main__":
    unittest.main()
